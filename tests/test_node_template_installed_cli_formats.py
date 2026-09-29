"""Installed CLI supervision of independently verified CommonJS and TypeScript hosts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import venv

import pytest

from jev_integration_evaluator.io import digest, file_hash, read_json
from jev_integration_evaluator import template_node_installation as installer
from jev_integration_evaluator import template_js_catalog
from jev_integration_evaluator.integrations.js_backend import trusted_js_tool_identity
from test_node_template_installation import native_tools
from test_node_template_installed_upgrade import (
    NODE_SHA256, NPM_CLI_SHA256, NPM_TREE_SHA256,
    TRUSTED_TYPESCRIPT_TREE_SHA256, _observations, _scope,
)
from test_node_template_installed_commonjs import _installed as installed_commonjs
from test_node_template_installed_upgrade import _installed as installed_typescript


PROJECT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('format_name', ('commonjs', 'typescript'))
def test_installed_cli_source_verified_off_mode_format(tmp_path, format_name):
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
    (tmp_path / 'generations').mkdir(mode=0o700)

    builder = installed_commonjs if format_name == 'commonjs' else installed_typescript
    host = builder(tmp_path, 'cli-host', '1.0.0', 'alpha', tooling, node, npm,
                   prepare_only=True)
    source = host['source']
    request = host['request']
    assert request['format'] == format_name
    assert request['reviewed_package_source_sha256'] == digest(template_js_catalog._source_tree(source))

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
            assert run.returncode != 0
            return run
        assert run.returncode == 0, run.stderr[-1000:]
        return json.loads(run.stdout)

    def private_json(name, value):
        path = tmp_path / name
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            json.dump(value, stream)
        return path

    request_file = private_json('template-request.json', request)
    spec_file = private_json('implementation-spec.json', request['implementation_spec'])
    cases_file = private_json('verification-cases.json', host['cases'])
    rendered = tmp_path / 'cli-render'
    materialized = invoke('template', 'materialize', '--repo', source,
        '--request', request_file, '--tooling', tooling, '--out', rendered)
    lock = read_json(rendered / 'template-lock.json')
    assert lock['format'] == format_name
    assert lock['source_sha256'] == request['implementation_spec']['source']['sha256']
    assert read_json(rendered / 'render-status.json')['status'] == 'complete'
    assert materialized['status'] == 'materialized'
    bundle = tmp_path / 'cli-bundle'
    js_common = ('--repo', source, '--bundle', bundle, '--tooling', tooling)
    planned_js = invoke('js-plan', *js_common, '--spec', spec_file)
    baseline = invoke('js-verify', *js_common, '--phase', 'baseline',
        '--cases', cases_file, '--approve-execution')
    assert baseline['status'] == 'passed'
    invoke('js-apply', *js_common, '--approve', '0' * 64,
        '--baseline-sha256', baseline['receipt_sha256'], ok=False)
    assert file_hash(source / request['implementation_spec']['source']['file']) == lock['source_sha256']
    applied = invoke('js-apply', *js_common, '--approve', planned_js['bundle_sha256'],
        '--baseline-sha256', baseline['receipt_sha256'])
    assert applied['status'] == 'applied_unverified'
    modified = invoke('js-verify', *js_common, '--phase', 'modified',
        '--cases', cases_file, '--baseline-sha256', baseline['receipt_sha256'],
        '--approve-execution')
    assert modified['status'] == 'passed'
    assert invoke('js-status', *js_common,
        '--trusted-modified-sha256', modified['receipt_sha256'])['status'] == 'verified'

    # The installed evaluator now owns each CLI stage from source render to launch.
    cli_packages = tmp_path / 'cli-packages'
    cli_generations = tmp_path / 'cli-generations'
    cli_packages.mkdir(mode=0o700)
    cli_generations.mkdir(mode=0o700)
    package_request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
        'host_root': str(source), 'render_directory': str(rendered),
        'implementation_bundle': str(bundle),
        'trusted_modified_sha256': modified['receipt_sha256'],
        'node': str(node), 'node_sha256': file_hash(node),
        'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
        'npm_tree_sha256': digest(installer._tree(npm.parent.parent)),
        'tooling_directory': str(tooling), 'offline_cache': str(tmp_path / 'cache'),
        'package_directory': str(cli_packages / 'package'),
        'environment_parent': str(cli_generations)}
    package_request_file = private_json('package-request.json', package_request)
    package_plan = tmp_path / 'package-plan.json'
    planned = invoke('template', 'node-package-plan', '--request', package_request_file,
        '--out', package_plan)
    reviewed_plan = read_json(package_plan)
    assert planned['plan_sha256'] == reviewed_plan['plan_sha256']
    invoke('template', 'node-package-build', '--plan', package_plan,
        '--approve-plan-sha256', '0' * 64, ok=False)
    assert not Path(package_request['package_directory']).exists()
    packaged = invoke('template', 'node-package-build', '--plan', package_plan,
        '--approve-plan-sha256', reviewed_plan['plan_sha256'])
    package_receipt = Path(package_request['package_directory']) / 'package-receipt.json'
    assert packaged['receipt_sha256'] == read_json(package_receipt)['receipt_sha256']
    assert invoke('template', 'node-package-status', '--plan', package_plan,
        '--trusted-receipt-sha256', packaged['receipt_sha256'])['status'] == 'packaged_recorded'
    install_plan = tmp_path / 'install-plan.json'
    install_planned = invoke('template', 'node-install-plan', '--package-plan', package_plan,
        '--package-receipt', package_receipt,
        '--trusted-package-receipt-sha256', packaged['receipt_sha256'], '--out', install_plan)
    reviewed_install = read_json(install_plan)
    assert install_planned['plan_sha256'] == reviewed_install['plan_sha256']
    invoke('template', 'node-install', '--plan', install_plan,
        '--approve-plan-sha256', '0' * 64, ok=False)
    generation = cli_generations / ('jev-node-env-' + reviewed_install['plan_sha256'][:24])
    assert not generation.exists()
    cli_installed = invoke('template', 'node-install', '--plan', install_plan,
        '--approve-plan-sha256', reviewed_install['plan_sha256'])
    cli_receipt = read_json(generation / 'install-receipt.json')
    assert cli_installed['receipt_sha256'] == cli_receipt['receipt_sha256']
    cli_entry = Path(cli_receipt['command'][1])
    assert cli_entry.is_relative_to(generation / 'app')
    assert file_hash(cli_entry) == cli_receipt['entrypoint_sha256']
    assert invoke('template', 'node-install-status', '--plan', install_plan,
        '--trusted-receipt-sha256', cli_installed['receipt_sha256'])['status'] == 'installed_recorded'
    assert invoke('template', 'node-package-status', '--plan', package_plan,
        '--trusted-receipt-sha256', '0' * 64)['status'] != 'packaged_recorded'
    assert invoke('template', 'node-install-status', '--plan', install_plan,
        '--trusted-receipt-sha256', '0' * 64)['status'] != 'installed_recorded'

    observation, launch_env, expected = _observations(tmp_path / 'effects', '1.0.0', 'alpha')
    observation_file = private_json('observation.json', observation)
    launch_env_file = private_json('launch-env.json', launch_env)
    descriptor_file = tmp_path / 'descriptor.json'
    descriptor_result = invoke('template', 'node-delivery-plan', '--install-plan', install_plan,
        '--trusted-install-receipt-sha256', cli_installed['receipt_sha256'],
        '--observation', observation_file, '--launch-environment', launch_env_file,
        '--out', descriptor_file)
    descriptor = read_json(descriptor_file)
    assert descriptor_result['descriptor_sha256'] == descriptor['descriptor_sha256']
    assert not (tmp_path / 'effects/effect.bin').exists()
    session_dir = tmp_path / 'cli-session'
    created = invoke('template', 'node-session-create', '--session', session_dir,
        '--descriptor', descriptor_file)
    launch = _scope(created, 'launch', descriptor)
    scope_file = private_json('launch-scope.json', launch)
    invoke('template', 'node-launch', '--session', session_dir, '--scope', scope_file,
        '--approve-scope-sha256', '0' * 64, ok=False)
    assert not Path(launch_env['NODE_EFFECT_PATH']).exists()
    running = invoke('template', 'node-launch', '--session', session_dir,
        '--scope', scope_file, '--approve-scope-sha256', launch['scope_sha256'])
    for _ in range(150):
        observed = invoke('template', 'node-observe', '--session', session_dir,
            '--trusted-session-head', running['session_head_sha256'])
        running = observed
        if observed['observations']['integration_reachable']:
            break
        time.sleep(.02)
    else:
        raise AssertionError('installed ' + format_name + ' CLI effect not observed')
    assert Path(launch_env['NODE_EFFECT_PATH']).read_bytes() == expected == b'read:alpha\n'
    assert all(file_hash(Path(row['path'])) == row['expected_sha256']
               for row in descriptor['observation']['checks'])
    assert observed['observations']['entrypoint_reached']
    stop = _scope(observed, 'stop', descriptor)
    stop_file = private_json('stop-scope.json', stop)
    stopped = invoke('template', 'node-stop', '--session', session_dir,
        '--scope', stop_file, '--approve-scope-sha256', stop['scope_sha256'])
    assert stopped['stage'] == 'stopped' and stopped['run_id'] == created['run_id']
    assert invoke('template', 'node-status', '--session', session_dir,
        '--trusted-session-head', stopped['session_head_sha256'])['stage'] == 'stopped'
