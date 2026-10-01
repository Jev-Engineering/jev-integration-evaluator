"""Installed CLI recovery of an interrupted Node install, then a usable host.

A real offline install of a source-verified CommonJS host is interrupted after
its owned copy and before its completion record. The installed evaluator CLI
classifies it, removes exactly that owned generation under a separately
approved recovery digest, and a fresh approved install then runs the normal
off-mode command with its raw effect. A previously installed generation and its
unlaunched session stay untouched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import venv

import pytest

from jev_integration_evaluator.io import digest, file_hash, read_json
from jev_integration_evaluator import template_node_installation as installer
from jev_integration_evaluator.integrations.js_backend import trusted_js_tool_identity
from test_node_template_installation import native_tools
from test_node_template_installed_upgrade import (
    NODE_SHA256, NPM_CLI_SHA256, NPM_TREE_SHA256,
    TRUSTED_TYPESCRIPT_TREE_SHA256, _observations, _scope,
)
from test_node_template_installed_commonjs import _installed as installed_commonjs


PROJECT = Path(__file__).resolve().parents[1]


def _state(base: Path, skip: tuple[Path, ...] = ()) -> dict:
    """Bytes, mode, inode and mtime of every entry; links are not followed."""
    rows = {}
    for folder, directories, names in os.walk(base, followlinks=False):
        directories[:] = [name for name in directories if Path(folder) / name not in skip]
        for name in directories + names:
            path = Path(folder) / name
            if path in skip:
                continue
            info = path.lstat()
            identity = (stat.S_IMODE(info.st_mode), info.st_ino)
            if stat.S_ISLNK(info.st_mode):
                rows[str(path)] = ('link', os.readlink(path), identity)
            elif stat.S_ISDIR(info.st_mode):
                rows[str(path)] = ('directory', identity)
            else:
                rows[str(path)] = ('file', path.read_bytes(), identity, info.st_mtime_ns)
    return rows


def test_installed_cli_recovers_interrupted_install_and_host_runs(tmp_path, monkeypatch):
    tools = native_tools()
    compiler_name = os.environ.get('JEV_TRUSTED_TYPESCRIPT_PACKAGE')
    wheelhouse = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    compiler = Path(compiler_name) if compiler_name else Path('/nonexistent-typescript-package')
    if tools is None or not wheelhouse or not (compiler / 'lib/typescript.js').is_file():
        pytest.skip('pinned Linux Node/npm, trusted TypeScript and offline wheelhouse required')
    node, npm = tools
    assert file_hash(node) == NODE_SHA256
    assert file_hash(npm) == NPM_CLI_SHA256
    assert digest(installer._tree(npm.parent.parent)) == NPM_TREE_SHA256
    assert digest(installer._tree(compiler)) == TRUSTED_TYPESCRIPT_TREE_SHA256
    tooling = tmp_path / 'trusted-tooling'
    (tooling / 'node_modules').mkdir(parents=True)
    os.chmod(tooling, 0o700)
    shutil.copytree(compiler, tooling / 'node_modules/typescript')
    assert trusted_js_tool_identity(tooling)['compiler_version'] == '5.8.3'
    (tmp_path / 'cache').mkdir(mode=0o700)
    generations = tmp_path / 'generations'
    generations.mkdir(mode=0o700)

    # A source-verified host with one completed, retained installed generation.
    retained = installed_commonjs(tmp_path, 'host', '1.0.0', 'alpha', tooling, node, npm)
    retained_root = Path(retained['installed']['generation_path'])
    assert retained_root.parent == generations

    wheel_dir = tmp_path / 'wheel'
    wheel_dir.mkdir(mode=0o700)
    built = subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-build-isolation',
        '--no-deps', '-w', str(wheel_dir), str(PROJECT)], cwd=tmp_path,
        capture_output=True, text=True, timeout=90)
    assert built.returncode == 0, built.stderr[-1000:]
    wheels = list(wheel_dir.glob('jev_integration_evaluator-*.whl'))
    assert len(wheels) == 1
    evaluator = tmp_path / 'evaluator-venv'
    venv.EnvBuilder(with_pip=False, system_site_packages=False).create(evaluator)
    python = evaluator / 'bin/python'
    result = subprocess.run([sys.executable, '-m', 'pip', '--python', str(python),
        'install', '--no-index', '--find-links', wheelhouse, str(wheels[0])],
        cwd=tmp_path, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr[-1000:]
    environment = {'PATH': str(node.parent) + ':/usr/bin:/bin',
                   'PYTHONNOUSERSITE': '1', 'JEV_RUNTIME_MODE': 'off'}
    origin = subprocess.run([str(python), '-I', '-c',
        'import jev_integration_evaluator as x; print(x.__file__)'],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    assert origin.returncode == 0
    assert Path(origin.stdout.strip()).is_relative_to(evaluator / 'lib/python3.13/site-packages')

    def invoke(*args, ok=True):
        run = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
            *map(str, args)], cwd=tmp_path, env=environment,
            capture_output=True, text=True, timeout=120)
        if not ok:
            assert run.returncode == 2 and run.stdout == ''
            return json.loads(run.stderr)
        assert run.returncode == 0, run.stderr[-1000:]
        return json.loads(run.stdout)

    def private_json(name, value):
        path = tmp_path / name
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            json.dump(value, stream)
        return path

    # The retained generation is selected by an unlaunched installed session.
    retained_plan = private_json('retained-install-plan.json', retained['install_plan'])
    retained_digest = retained['installed']['receipt_sha256']
    kept_observation, kept_env, _ = _observations(tmp_path / 'retained-effects', '1.0.0', 'alpha')
    kept_descriptor = tmp_path / 'retained-descriptor.json'
    invoke('template', 'node-delivery-plan', '--install-plan', retained_plan,
        '--trusted-install-receipt-sha256', retained_digest,
        '--observation', private_json('retained-observation.json', kept_observation),
        '--launch-environment', private_json('retained-launch-env.json', kept_env),
        '--out', kept_descriptor)
    kept_session = tmp_path / 'retained-session'
    selected = invoke('template', 'node-session-create', '--session', kept_session,
        '--descriptor', kept_descriptor)
    assert selected['stage'] == 'created'
    assert selected['current_installation'] == 'current_verified'

    # A second package and generation of the same verified source, CLI-owned.
    cli_packages = tmp_path / 'cli-packages'
    cli_packages.mkdir(mode=0o700)
    package_request = dict(retained['install_plan']['package_plan']['request'],
                           package_directory=str(cli_packages / 'package'))
    package_plan = tmp_path / 'package-plan.json'
    planned = invoke('template', 'node-package-plan',
        '--request', private_json('package-request.json', package_request),
        '--out', package_plan)
    packaged = invoke('template', 'node-package-build', '--plan', package_plan,
        '--approve-plan-sha256', planned['plan_sha256'])
    package_receipt = cli_packages / 'package/package-receipt.json'
    install_plan = tmp_path / 'install-plan.json'
    install_planned = invoke('template', 'node-install-plan', '--package-plan', package_plan,
        '--package-receipt', package_receipt,
        '--trusted-package-receipt-sha256', packaged['receipt_sha256'], '--out', install_plan)
    reviewed_install = read_json(install_plan)
    approved_install = install_planned['plan_sha256']
    assert approved_install == reviewed_install['plan_sha256']
    assert approved_install != retained['install_plan']['plan_sha256']
    generation = generations / ('jev-node-env-' + approved_install[:24])
    intent = installer._intent_path(generation)
    history = installer._recovery_path(generation)
    owned = (generation, intent, history, generations / '.jev-node-locks')
    assert generation != retained_root and not generation.exists()

    def untouched():
        return (_state(generations, skip=owned), _state(cli_packages),
                _state(retained['source']), _state(kept_session),
                _state(tmp_path / 'host-packages'))
    before = untouched()

    # Lock files and the evaluator's own bytecode cache are not host state.
    volatile = (generations / '.jev-node-locks', evaluator)
    # Interrupt the real install after its owned copy, before its completion record.
    record = installer._record

    def stop_before_complete(root, plan_sha256, event):
        if event == 'install_complete':
            raise RuntimeError('injected install interruption')
        return record(root, plan_sha256, event)
    with monkeypatch.context() as patch:
        patch.setattr(installer, '_record', stop_before_complete)
        with pytest.raises(RuntimeError, match='injected install interruption'):
            installer.install_node_package(reviewed_install,
                                           approved_plan_sha256=approved_install)
    entry = generation / 'app/start.cjs'
    assert file_hash(entry) == file_hash(retained['source'] / 'start.cjs')
    assert not (generation / 'install-receipt.json').exists()
    journal = installer._journal(generation, approved_install)
    assert [row['event'] for row in journal] == ['install_started']
    interrupted = _state(tmp_path, skip=volatile)

    # Status classifies it; neither status nor a retried install recovers it.
    assert invoke('template', 'node-install-status', '--plan', install_plan) == {
        'schema_version': '1.0', 'status': 'install_interrupted_review_required'}
    refused = invoke('template', 'node-install', '--plan', install_plan,
        '--approve-plan-sha256', approved_install, ok=False)
    assert refused['status'] == 'rejected' and 'already exists' in refused['message']
    assert 'interrupt' not in invoke('template', 'node-install-status',
        '--plan', retained_plan, '--trusted-receipt-sha256', retained_digest)['status']
    assert _state(tmp_path, skip=volatile) == interrupted

    # Read-only recovery plan, then the separately approved owned removal.
    recovery_file = tmp_path / 'recovery-plan.json'
    recovery_planned = invoke('template', 'node-install-recovery-plan',
        '--plan', install_plan, '--out', recovery_file)
    recovery = read_json(recovery_file)
    assert recovery_planned == {'schema_version': '1.0', 'status': 'recovery_planned',
        'mode': 'off', 'recovery_sha256': recovery['recovery_sha256'],
        'generation_sha256': recovery['generation_sha256'],
        'recovery_journal_head': None}
    assert stat.S_IMODE(recovery_file.stat().st_mode) == 0o600
    assert recovery['target'] == 'generation' and recovery['stage'] == 'journal_recorded'
    assert recovery['root'] == str(generation) and recovery['journal'] == journal
    assert recovery['step_plan_sha256'] == approved_install
    assert recovery['generation_sha256'] == installer._owned_snapshot(
        generation, nested_links=False)[0]
    interrupted = _state(tmp_path, skip=volatile)
    for wrong in (('--approve-plan-sha256', approved_install,
                   '--approve-recovery-sha256', approved_install),
                  ('--approve-plan-sha256', recovery['recovery_sha256'],
                   '--approve-recovery-sha256', recovery['recovery_sha256']),
                  ('--approve-plan-sha256', approved_install,
                   '--approve-recovery-sha256', '0' * 64)):
        rejected = invoke('template', 'node-install-recover', '--plan', install_plan,
            '--recovery-plan', recovery_file, *wrong, ok=False)
        assert rejected['status'] == 'rejected' and 'approval required' in rejected['message']
    # The retained generation's plan cannot be used to remove this one, and a
    # completed generation has nothing to recover.
    rejected = invoke('template', 'node-install-recover', '--plan', retained_plan,
        '--recovery-plan', recovery_file,
        '--approve-plan-sha256', retained['install_plan']['plan_sha256'],
        '--approve-recovery-sha256', recovery['recovery_sha256'], ok=False)
    assert 'bound to another step or root' in rejected['message']
    rejected = invoke('template', 'node-install-recovery-plan', '--plan', retained_plan,
        '--out', tmp_path / 'retained-recovery-plan.json', ok=False)
    assert 'has a receipt; recovery refused' in rejected['message']
    assert not (tmp_path / 'retained-recovery-plan.json').exists()
    assert _state(tmp_path, skip=volatile) == interrupted

    recovered = invoke('template', 'node-install-recover', '--plan', install_plan,
        '--recovery-plan', recovery_file, '--approve-plan-sha256', approved_install,
        '--approve-recovery-sha256', recovery['recovery_sha256'])
    assert recovered['status'] == 'owned_incomplete_generation_removed'
    assert recovered['recovery_sha256'] == recovery['recovery_sha256'] and recovered['mode'] == 'off'
    assert not generation.exists() and not intent.exists()
    rows = installer._recovery_rows(generation)
    assert [row['event'] for row in rows] == ['recovery_started', 'recovery_complete']
    assert rows[0]['detail']['journal'] == journal      # the interrupted attempt is retained
    assert rows[1]['record_sha256'] == recovered['recovery_journal_head']
    assert invoke('template', 'node-install-status', '--plan', install_plan) == {
        'schema_version': '1.0', 'status': 'absent', 'recovered_attempts': 1,
        'recovery_journal_head': recovered['recovery_journal_head']}
    replayed = invoke('template', 'node-install-recover', '--plan', install_plan,
        '--recovery-plan', recovery_file, '--approve-plan-sha256', approved_install,
        '--approve-recovery-sha256', recovery['recovery_sha256'], ok=False)
    assert 'requires a recorded interruption' in replayed['message']

    # Nothing outside the owned generation changed; the retained one is still selected.
    assert untouched() == before
    assert invoke('template', 'node-install-status', '--plan', retained_plan,
        '--trusted-receipt-sha256', retained_digest)['status'] == 'installed_recorded'
    still = invoke('template', 'node-status', '--session', kept_session,
        '--trusted-session-head', selected['session_head_sha256'])
    assert still['stage'] == 'created' and still['run_id'] == selected['run_id']
    assert still['current_installation'] == 'current_verified'
    assert not any(Path(path).exists() for path in kept_env.values())

    # A fresh, newly approved install of the same plan completes and the host runs.
    history_bytes = history.read_bytes()
    cli_installed = invoke('template', 'node-install', '--plan', install_plan,
        '--approve-plan-sha256', approved_install)
    cli_receipt = read_json(generation / 'install-receipt.json')
    assert cli_installed['receipt_sha256'] == cli_receipt['receipt_sha256']
    assert Path(cli_receipt['command'][1]) == entry
    assert invoke('template', 'node-install-status', '--plan', install_plan,
        '--trusted-receipt-sha256', cli_installed['receipt_sha256'])['status'] == 'installed_recorded'
    assert history.read_bytes() == history_bytes
    observation, launch_env, expected = _observations(tmp_path / 'effects', '1.0.0', 'alpha')
    descriptor_file = tmp_path / 'descriptor.json'
    invoke('template', 'node-delivery-plan', '--install-plan', install_plan,
        '--trusted-install-receipt-sha256', cli_installed['receipt_sha256'],
        '--observation', private_json('observation.json', observation),
        '--launch-environment', private_json('launch-env.json', launch_env),
        '--out', descriptor_file)
    descriptor = read_json(descriptor_file)
    assert descriptor['command'] == cli_receipt['command']
    session_dir = tmp_path / 'cli-session'
    created = invoke('template', 'node-session-create', '--session', session_dir,
        '--descriptor', descriptor_file)
    launch = _scope(created, 'launch', descriptor)
    assert not Path(launch_env['NODE_EFFECT_PATH']).exists()
    running = invoke('template', 'node-launch', '--session', session_dir,
        '--scope', private_json('launch-scope.json', launch),
        '--approve-scope-sha256', launch['scope_sha256'])
    for _ in range(150):
        observed = invoke('template', 'node-observe', '--session', session_dir,
            '--trusted-session-head', running['session_head_sha256'])
        running = observed
        if observed['observations']['integration_reachable']:
            break
        time.sleep(.02)
    else:
        raise AssertionError('installed CommonJS effect not observed after recovery')
    assert Path(launch_env['NODE_EFFECT_PATH']).read_bytes() == expected == b'read:alpha\n'
    assert all(file_hash(Path(row['path'])) == row['expected_sha256']
               for row in descriptor['observation']['checks'])
    assert observed['observations']['entrypoint_reached']
    stop = _scope(observed, 'stop', descriptor)
    stopped = invoke('template', 'node-stop', '--session', session_dir,
        '--scope', private_json('stop-scope.json', stop),
        '--approve-scope-sha256', stop['scope_sha256'])
    assert stopped['stage'] == 'stopped' and stopped['run_id'] == created['run_id']
    assert not any(Path(path).exists() for path in kept_env.values())
    assert _state(retained_root) == {key: value for key, value in before[0].items()
                                     if key.startswith(str(retained_root) + '/')}
