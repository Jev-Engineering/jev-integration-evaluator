"""Independent pinned ESM recipe C, installed normal command and owned rollback."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest

from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import InputError, digest, file_hash, read_json
from jev_integration_evaluator import template_js_catalog
from jev_integration_evaluator import template_node_delivery as delivery
from jev_integration_evaluator import template_node_installation as installer
from jev_integration_evaluator import template_node_session as session
from jev_integration_evaluator.integrations.js_backend import trusted_js_tool_identity
from jev_integration_evaluator.integrations.js_lifecycle import (
    apply_js, plan_js, rollback_js, status_js, verify_js,
)
from jev_integration_evaluator.template_catalog import materialize_template
from test_node_template_installation import native_tools
from test_node_template_installed_upgrade import (
    NPM_CLI_SHA256, NPM_TREE_SHA256, NODE_SHA256,
    TRUSTED_TYPESCRIPT_TREE_SHA256, _observe, _observations, _scope,
)


ROOT = Path(__file__).parent / 'independent_hosts/esm_recipe_c'
PROJECT = Path(__file__).resolve().parents[1]
FILES = ('host.mjs', 'start.mjs', 'package.json', 'package-lock.json')


def _copy_reviewed_host(target: Path, version: str) -> tuple[Path, dict]:
    if version not in ('1.0.0', '1.0.1'):
        raise ValueError('unsupported ESM source version')
    review = json.loads((ROOT / 'review-v1.json').read_text(encoding='utf-8'))
    validate_contract(review, 'independent-esm-recipe-c-review-v1')
    source = ROOT if version == '1.0.0' else ROOT / 'versions/1.0.1'
    for filename in FILES:
        original = source / filename
        if original.is_symlink() or file_hash(original) != review['versions'][version][filename]:
            raise ValueError('reviewed ESM source bytes changed: ' + filename)
    target.mkdir(mode=0o700)
    for filename in FILES:
        original = source / filename
        shutil.copyfile(original, target / filename)
        if file_hash(target / filename) != review['versions'][version][filename]:
            raise ValueError('copied ESM source bytes changed: ' + filename)
    return target, review


def test_pinned_esm_source_drift_refuses_before_copy(tmp_path, monkeypatch):
    alternate = tmp_path / 'alternate-review-source'
    shutil.copytree(ROOT, alternate)
    host = alternate / 'host.mjs'
    host.write_bytes(host.read_bytes() + b'\n// unreviewed source edit\n')
    monkeypatch.setattr(sys.modules[__name__], 'ROOT', alternate)
    target = tmp_path / 'target'
    with pytest.raises(ValueError, match='reviewed ESM source bytes changed'):
        _copy_reviewed_host(target, '1.0.0')
    assert not target.exists()


def _request(source: Path, version: str) -> tuple[dict, list[dict]]:
    item = 'alpha' if version == '1.0.0' else 'beta'
    marker = '' if version == '1.0.0' else ':v2'
    cases = [{'id': 'normal-' + version,
              'request': {'task_id': 'esm-task', 'invocation_id': 'case-' + version,
                          'item': item, 'permit': True},
              'result': 'read:' + item + marker,
              'events': [['read', item]], 'effects': [['read', item + marker]]}]
    spec = {'schema_version': '1.0', 'recipe_id': 'javascript.C',
            'candidate_id': 'independent-reviewed-esm-recipe-c',
            'source': {'file': 'host.mjs', 'sha256': file_hash(source / 'host.mjs'),
                       'symbol': 'seam', 'original': 'original'},
            'bindings': {'registry': 'hostRegistry', 'gate': 'hostGate',
                         'validate': 'hostValidate', 'blocked': 'hostBlocked',
                         'evidence': 'hostEvidence', 'baseline_action': 'hostBaseline'},
            'runtime': {'registered_action_ids': ['read'],
                        'questions': {'choice': {'type': 'choice',
                                                 'criteria': {'read': 'Read',
                                                              'uncertain': 'Unclear'}}},
                        'primary_question': 'choice',
                        'label_actions': {'read': 'read', 'uncertain': None},
                        'runtime': {'mode': 'off', 'canary_scope': 'synthetic',
                                    'cost_upper_bound': 1, 'timeout_ms': 40,
                                    'model': 'model-v1'}},
            'verification_sha256': digest(cases), 'verification_cases_count': len(cases)}
    configuration = {'mode': 'off', 'credential_ref': None}
    request = {'schema_version': '1.0', 'template_id': 'javascript.recipe-c',
               'template_version': '1.0.0', 'backend': 'javascript',
               'profile': 'flat-async-recipe-c-v1', 'format': 'esm',
               'implementation_spec': spec, 'entrypoint': 'start.mjs',
               'package_json_sha256': file_hash(source / 'package.json'),
               'package_lock_sha256': file_hash(source / 'package-lock.json'),
               'entrypoint_sha256': file_hash(source / 'start.mjs'),
               'reviewed_package_source_sha256': digest(template_js_catalog._source_tree(source)),
               'configuration': configuration, 'secret_references': {},
               'reviewed_configuration_sha256': digest({'configuration': configuration,
                                                         'secret_references': {}})}
    return request, cases


def test_installed_evaluator_cli_materializes_pinned_esm(tmp_path):
    tools = native_tools()
    compiler_name = os.environ.get('JEV_TRUSTED_TYPESCRIPT_PACKAGE')
    wheelhouse_name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    compiler = Path(compiler_name) if compiler_name else Path('/nonexistent-typescript-package')
    if tools is None or not wheelhouse_name or not (compiler / 'lib/typescript.js').is_file():
        pytest.skip('pinned native Node/npm, external TypeScript and offline wheelhouse required')
    assert digest(installer._tree(compiler)) == TRUSTED_TYPESCRIPT_TREE_SHA256
    tooling = tmp_path / 'trusted-tooling'
    (tooling / 'node_modules').mkdir(parents=True)
    os.chmod(tooling, 0o700)
    shutil.copytree(compiler, tooling / 'node_modules/typescript')
    assert trusted_js_tool_identity(tooling)['compiler_version'] == '5.8.3'
    source, _ = _copy_reviewed_host(tmp_path / 'source', '1.0.0')
    request, _ = _request(source, '1.0.0')
    wheel_dir = tmp_path / 'evaluator-wheel'
    wheel_dir.mkdir(mode=0o700)
    built = subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-build-isolation',
                            '--no-deps', '-w', str(wheel_dir), str(PROJECT)],
                           cwd=tmp_path, capture_output=True, text=True, timeout=90)
    assert built.returncode == 0, built.stderr[-1000:]
    wheels = list(wheel_dir.glob('jev_integration_evaluator-*.whl'))
    assert len(wheels) == 1
    evaluator = tmp_path / 'evaluator-venv'
    venv.EnvBuilder(with_pip=False, system_site_packages=False).create(evaluator)
    python = evaluator / 'bin/python'
    installed = subprocess.run([sys.executable, '-m', 'pip', '--python', str(python),
        'install', '--no-index', '--find-links', wheelhouse_name, str(wheels[0])],
        cwd=tmp_path, capture_output=True, text=True, timeout=90)
    assert installed.returncode == 0, installed.stderr[-1000:]
    environment = {'PATH': str(tools[0].parent) + ':/usr/bin:/bin',
                   'PYTHONNOUSERSITE': '1', 'JEV_RUNTIME_MODE': 'off'}
    origin = subprocess.run([str(python), '-I', '-c',
        'import jev_integration_evaluator as x; print(x.__file__)'],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    assert origin.returncode == 0
    assert Path(origin.stdout.strip()).is_relative_to(evaluator / 'lib/python3.13/site-packages')
    request_path = tmp_path / 'esm-request.json'
    request_path.write_text(json.dumps(request), encoding='utf-8')
    rendered = tmp_path / 'installed-render'
    result = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
        'template', 'materialize', '--repo', str(source), '--request', str(request_path),
        '--tooling', str(tooling), '--out', str(rendered)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-1000:]
    lock = read_json(rendered / 'template-lock.json')
    assert lock['format'] == 'esm'
    assert lock['source_sha256'] == request['implementation_spec']['source']['sha256']
    assert read_json(rendered / 'render-status.json')['status'] == 'complete'


def _installed(tmp_path: Path, name: str, version: str,
               tooling: Path, node: Path, npm: Path) -> dict:
    source, review = _copy_reviewed_host(tmp_path / name, version)
    request, cases = _request(source, version)
    reviewed_host = (source / 'host.mjs').read_bytes()
    rendered = tmp_path / (name + '-render')
    materialize_template(source, request, rendered, tooling_dir=tooling)
    bundle = tmp_path / (name + '-bundle')
    planned = plan_js(source, request['implementation_spec'], bundle, tooling_dir=tooling)
    baseline = verify_js(source, bundle, 'baseline', cases, tooling_dir=tooling,
                         approve_execution=True)
    assert baseline['status'] == 'passed'
    applied = apply_js(source, bundle, planned['bundle_sha256'],
                       baseline_sha256=baseline['receipt_sha256'], tooling_dir=tooling)
    assert applied['status'] == 'applied_unverified'
    modified = verify_js(source, bundle, 'modified', cases, tooling_dir=tooling,
                         baseline_sha256=baseline['receipt_sha256'], approve_execution=True)
    assert modified['status'] == 'passed'
    verified = status_js(source, bundle, tooling_dir=tooling,
                         trusted_modified_sha256=modified['receipt_sha256'])
    assert verified['status'] == 'verified'
    package_parent = tmp_path / (name + '-packages')
    package_parent.mkdir(mode=0o700)
    package_request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
        'host_root': str(source), 'render_directory': str(rendered),
        'implementation_bundle': str(bundle),
        'trusted_modified_sha256': modified['receipt_sha256'],
        'node': str(node), 'node_sha256': file_hash(node),
        'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
        'npm_tree_sha256': digest(installer._tree(npm.parent.parent)),
        'tooling_directory': str(tooling), 'offline_cache': str(tmp_path / 'cache'),
        'package_directory': str(package_parent / 'package'),
        'environment_parent': str(tmp_path / 'generations')}
    package_plan = installer.plan_node_package(package_request)
    package_receipt = installer.build_node_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_node_install(package_plan, package_receipt,
        trusted_package_receipt_sha256=package_receipt['receipt_sha256'])
    installed = installer.install_node_package(install_plan,
        approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan,
        trusted_receipt_sha256=installed['receipt_sha256'])['status'] == 'installed_recorded'
    generation = Path(installed['generation_path'])
    entry = generation / 'app/start.mjs'
    assert installed['command'] == [str(node), str(entry)]
    assert file_hash(entry) == installed['entrypoint_sha256'] == review['versions'][version]['start.mjs']
    assert file_hash(generation / 'app/host.mjs') == file_hash(source / 'host.mjs')
    assert entry != source / 'start.mjs' and not generation.is_relative_to(ROOT)
    assert json.loads((generation / 'app/package.json').read_text())['scripts']['start'] == 'node start.mjs'
    assert package_plan['toolchain']['node_sha256'] == NODE_SHA256
    assert package_plan['toolchain']['npm_tree_sha256'] == NPM_TREE_SHA256
    assert package_plan['toolchain']['typescript_tree_sha256'] == TRUSTED_TYPESCRIPT_TREE_SHA256
    return {'source': source, 'bundle': bundle, 'reviewed_host': reviewed_host,
            'rollback_digest': verified['rollback_digest'], 'install_plan': install_plan,
            'installed': installed, 'version': version,
            'item': 'alpha' if version == '1.0.0' else 'beta'}


def test_installed_esm_recipe_c_upgrade_and_owned_rollback(tmp_path, monkeypatch):
    tools = native_tools()
    compiler_name = os.environ.get('JEV_TRUSTED_TYPESCRIPT_PACKAGE')
    compiler = Path(compiler_name) if compiler_name else Path('/nonexistent-typescript-package')
    if tools is None or not (compiler / 'lib/typescript.js').is_file():
        pytest.skip('pinned native Node/npm and external trusted TypeScript 5.8.3 required')
    node, npm = tools
    assert file_hash(node) == NODE_SHA256
    assert file_hash(npm) == NPM_CLI_SHA256
    assert digest(installer._tree(npm.parent.parent)) == NPM_TREE_SHA256
    assert digest(installer._tree(compiler)) == TRUSTED_TYPESCRIPT_TREE_SHA256
    tooling = tmp_path / 'tooling'
    (tooling / 'node_modules').mkdir(parents=True)
    os.chmod(tooling, 0o700)
    shutil.copytree(compiler, tooling / 'node_modules/typescript')
    assert digest(installer._tree(tooling / 'node_modules/typescript')) == TRUSTED_TYPESCRIPT_TREE_SHA256
    assert trusted_js_tool_identity(tooling)['compiler_version'] == '5.8.3'
    (tmp_path / 'cache').mkdir(mode=0o700)
    (tmp_path / 'generations').mkdir(mode=0o700)
    old = _installed(tmp_path, 'esm-one', '1.0.0', tooling, node, npm)
    new = _installed(tmp_path, 'esm-two', '1.0.1', tooling, node, npm)
    assert old['installed']['generation_id'] != new['installed']['generation_id']
    assert old['installed']['source_sha256'] != new['installed']['source_sha256']
    assert file_hash(old['source'] / 'host.mjs') != file_hash(new['source'] / 'host.mjs')

    def descriptor(host: dict, name: str) -> tuple[dict, dict, bytes]:
        observation, environment, effect = _observations(tmp_path / name,
            host['version'], host['item'])
        plan = delivery.plan_node_delivery(host['install_plan'],
            trusted_install_receipt_sha256=host['installed']['receipt_sha256'],
            observation=observation, launch_environment=environment)
        assert delivery.validate_node_delivery(plan)['status'] == 'verified_unlaunched'
        return plan, environment, effect

    first, first_env, first_effect = descriptor(old, 'esm-old-effects')
    second, second_env, second_effect = descriptor(new, 'esm-new-effects')
    assert first_effect == b'read:alpha\n' and second_effect == b'read:beta:v2\n'
    path = tmp_path / 'esm-session'
    created = session.create_node_session(path, first)
    launch = _scope(created, 'launch', first)
    original_append = session._append

    def interrupt_before_release(directory, rows, event, state):
        if event == 'launched':
            raise RuntimeError('esm-before-release')
        return original_append(directory, rows, event, state)

    monkeypatch.setattr(session, '_append', interrupt_before_release)
    with pytest.raises(RuntimeError, match='esm-before-release'):
        session.launch_node_session(path, scope=launch,
            approved_scope_sha256=launch['scope_sha256'])
    monkeypatch.setattr(session, '_append', original_append)
    pending = session.node_session_status(path)
    assert pending['pending'] == 'launch' and pending['run_id'] == created['run_id']
    assert not Path(first_env['NODE_EFFECT_PATH']).exists()
    recovered = session.resume_node_session(path,
        trusted_session_head=pending['session_head_sha256'])
    assert recovered['stage'] == 'created' and recovered['run_id'] == created['run_id']
    launch = _scope(recovered, 'launch', first)
    observed = _observe(path, session.launch_node_session(path, scope=launch,
        approved_scope_sha256=launch['scope_sha256']))
    assert observed['observations']['entrypoint_reached']
    assert Path(first_env['NODE_EFFECT_PATH']).read_bytes() == first_effect
    stop = _scope(observed, 'stop', first)
    stopped = session.stop_node_session(path, scope=stop,
        approved_scope_sha256=stop['scope_sha256'], grace_seconds=0)
    assert stopped['stage'] == 'stopped'
    upgrade = _scope(stopped, 'upgrade', first, extra=second['descriptor_sha256'])
    changed = new['source'] / 'package.json'
    exact = changed.read_bytes()
    changed.write_bytes(exact + b'\n')
    with pytest.raises(InputError):
        session.upgrade_node_session(path, second, scope=upgrade,
            approved_scope_sha256=upgrade['scope_sha256'])
    changed.write_bytes(exact)
    assert session.node_session_status(path)['stage'] == 'stopped'
    assert not Path(second_env['NODE_EFFECT_PATH']).exists()
    upgraded = session.upgrade_node_session(path, second, scope=upgrade,
        approved_scope_sha256=upgrade['scope_sha256'])
    assert upgraded['stage'] == 'upgrade_staged' and upgraded['run_id'] == created['run_id']
    launch_new = _scope(upgraded, 'launch', second)
    observed_new = _observe(path, session.launch_node_session(path, scope=launch_new,
        approved_scope_sha256=launch_new['scope_sha256']))
    assert Path(second_env['NODE_EFFECT_PATH']).read_bytes() == second_effect
    disable = _scope(observed_new, 'disable', second)
    disabled = session.stop_node_session(path, scope=disable,
        approved_scope_sha256=disable['scope_sha256'], disable=True, grace_seconds=0)
    assert disabled['stage'] == 'disabled' and not disabled['process_alive']
    rollback = _scope(disabled, 'rollback', second,
        extra=disabled['previous_generation_rollback_digest'])
    restored = session.rollback_node_session(path, scope=rollback,
        approved_scope_sha256=rollback['scope_sha256'])
    assert restored['stage'] == 'rolled_back'
    assert restored['generation_id'] == old['installed']['generation_id']
    assert restored['run_id'] == created['run_id']
    stale_launch = _scope(restored, 'launch', first)
    with pytest.raises(InputError):
        session.launch_node_session(path, scope=stale_launch,
            approved_scope_sha256=stale_launch['scope_sha256'])
    assert Path(first_env['NODE_EFFECT_PATH']).read_bytes() == first_effect
    assert Path(second_env['NODE_EFFECT_PATH']).read_bytes() == second_effect
    assert all(Path(host['installed']['generation_path']).is_dir() for host in (old, new))
    for host in (new, old):
        result = rollback_js(host['source'], host['bundle'], host['rollback_digest'],
                             tooling_dir=tooling)
        assert result['status'] == 'rolled_back'
        assert (host['source'] / 'host.mjs').read_bytes() == host['reviewed_host']
