"""Two real, source-verified TypeScript host generations under one Node session."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator import template_js_catalog
from jev_integration_evaluator import template_node_delivery as delivery
from jev_integration_evaluator import template_node_installation as installer
from jev_integration_evaluator import template_node_session as session
from jev_integration_evaluator.integrations.js_backend import trusted_js_tool_identity
from jev_integration_evaluator.integrations.js_lifecycle import (
    apply_js, plan_js, rollback_js, status_js, verify_js)
from jev_integration_evaluator.template_catalog import materialize_template
from test_js_template_delivery import request_for
from test_node_template_installation import native_tools

TRUSTED_TYPESCRIPT_TREE_SHA256 = '774ce18bba737b3bbaffec66946dfd9948afaac993cf7e8e3ece871536d6e42b'
NODE_SHA256 = '41a74efb34cbde5c7632cdac0cf8bd1a14d0b8d73dc1e82755014d9a9ce70f5c'
NPM_CLI_SHA256 = '8e5f6f3429f8cdbe693cdc29904e9d5a7b127a494bd15c804bd54c7403bfcbe7'
NPM_TREE_SHA256 = '7f40e9604a44a7425237cc420ab4d407a7baed5121f2434c6fb4fcdea0de3263'


def _scope(status: dict, action: str, descriptor: dict, *, extra: str | None = None) -> dict:
    value = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
             'reference': 'independent-node-upgrade-fixture-operator',
             'run_id': status['run_id'], 'plan_sha256': descriptor['descriptor_sha256'],
             'trusted_session_head': status['session_head_sha256'],
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
             'revoked': False, 'grants': {name: name == action for name in
                 ('launch', 'stop', 'disable', 'upgrade', 'rollback')}}
    if action == 'upgrade':
        value['upgrade_plan_sha256'] = extra
    if action == 'rollback':
        value['rollback_digest'] = extra
    value['scope_sha256'] = digest(value)
    return value


def _observations(parent: Path, version: str, item: str) -> tuple[dict, dict, bytes]:
    parent.mkdir(mode=0o700)
    paths = {'NODE_EFFECT_PATH': parent / 'effect.bin',
             'NODE_READY_PATH': parent / 'ready.bin',
             'NODE_INTEGRATION_PATH': parent / 'integration.bin'}
    marker = ':v2' if version == '1.0.1' else ''
    effect = f'read:{item}{marker}\n'.encode()
    checks = [{'role': role, 'path': str(paths[key]), 'before_sha256': None,
               'expected_sha256': hashlib.sha256(raw).hexdigest()}
              for key, role, raw in (
                  ('NODE_READY_PATH', 'ready', b'ready\n'),
                  ('NODE_EFFECT_PATH', 'entrypoint_reached', effect),
                  ('NODE_INTEGRATION_PATH', 'integration_reachable', b'integration\n'))]
    return ({'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
             'checks': checks}, {key: str(path) for key, path in paths.items()}, effect)


def _installed(tmp_path: Path, name: str, version: str, item: str,
               tooling: Path, node: Path, npm: Path, *, prepare_only: bool = False) -> dict:
    work = tmp_path / name
    work.mkdir(mode=0o700)
    source, request = request_for(work, 'typescript')
    host_ts = source / 'host.ts'
    if version == '1.0.1':
        old_behavior = ("events.push(['read', request.item]); "
                        "globalThis.__jev_probe_effect?.('read', request.item); "
                        "return 'read:' + request.item;")
        new_behavior = ("events.push(['read', request.item]); "
                        "globalThis.__jev_probe_effect?.('read', request.item + ':v2'); "
                        "return 'read:' + request.item + ':v2';")
        text = host_ts.read_text(encoding='utf-8')
        assert text.count(old_behavior) == 1
        host_ts.write_text(text.replace(old_behavior, new_behavior), encoding='utf-8')
        request['implementation_spec']['source']['sha256'] = file_hash(host_ts)
    reviewed_host_source = host_ts.read_bytes()
    marker = ':v2' if version == '1.0.1' else ''
    package_path, lock_path = source / 'package.json', source / 'package-lock.json'
    package, lock = (json.loads(path.read_text()) for path in (package_path, lock_path))
    package['version'] = lock['version'] = lock['packages']['']['version'] = version
    package_path.write_text(json.dumps(package), encoding='utf-8')
    lock_path.write_text(json.dumps(lock), encoding='utf-8')
    entry = source / 'start.mjs'
    entry.write_text(
        'import fs from "node:fs";\n'
        'import {seam} from "./host.mjs";\n'
        'if (process.env.JEV_RUNTIME_MODE !== "off") throw Error("mode");\n'
        'for (const key of ["NODE_EFFECT_PATH","NODE_READY_PATH","NODE_INTEGRATION_PATH"]) '
        'if (!process.env[key]) throw Error("missing path");\n'
        'globalThis.__jev_probe_effect = (action,item) => '
        'fs.writeFileSync(process.env.NODE_EFFECT_PATH, action+":"+item+"\\n", '
        '{flag:"wx"});\n'
        'async function main() {\n'
        f'  const result = await seam({{task_id:"task",invocation_id:"normal-{version}",'
        f'item:"{item}",permit:true}});\n'
        f'  if (result !== "read:{item}{marker}") '
        'throw Error("seam result");\n'
        '  fs.writeFileSync(process.env.NODE_READY_PATH,"ready\\n",{flag:"wx"});\n'
        '  fs.writeFileSync(process.env.NODE_INTEGRATION_PATH,"integration\\n",{flag:"wx"});\n'
        '  await new Promise(resolve => setTimeout(resolve, 800));\n'
        '}\nmain().catch(() => {process.exitCode = 1;});\n', encoding='utf-8')
    request['entrypoint_sha256'] = file_hash(entry)
    request['package_json_sha256'] = file_hash(package_path)
    request['package_lock_sha256'] = file_hash(lock_path)
    request['reviewed_package_source_sha256'] = digest(template_js_catalog._source_tree(source))
    cases = [{'id': 'normal-' + version,
              'request': {'task_id': 'task', 'invocation_id': 'case-' + version,
                          'item': item, 'permit': True},
              'result': 'read:' + item + marker,
              'events': [['read', item]],
              'effects': [['read', item + marker]]}]
    request['implementation_spec']['verification_sha256'] = digest(cases)
    request['implementation_spec']['verification_cases_count'] = len(cases)
    if prepare_only:
        return {'source': source, 'request': request, 'cases': cases}
    rendered = tmp_path / (name + '-render')
    materialize_template(source, request, rendered, tooling_dir=tooling)
    bundle = tmp_path / (name + '-bundle')
    planned = plan_js(source, request['implementation_spec'], bundle, tooling_dir=tooling)
    baseline = verify_js(source, bundle, 'baseline', cases, tooling_dir=tooling,
                         approve_execution=True)
    assert baseline['status'] == 'passed'
    apply_js(source, bundle, planned['bundle_sha256'],
             baseline_sha256=baseline['receipt_sha256'], tooling_dir=tooling)
    modified = verify_js(source, bundle, 'modified', cases, tooling_dir=tooling,
                         baseline_sha256=baseline['receipt_sha256'], approve_execution=True)
    assert modified['status'] == 'passed'
    verified = status_js(source, bundle, tooling_dir=tooling,
                         trusted_modified_sha256=modified['receipt_sha256'])
    assert verified['status'] == 'verified'
    compiled_sha256 = file_hash(source / 'host.mjs')
    package_parent = tmp_path / (name + '-packages')
    environment_parent = tmp_path / 'generations'
    package_parent.mkdir(mode=0o700)
    environment_parent.mkdir(mode=0o700, exist_ok=True)
    request_install = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
        'host_root': str(source), 'render_directory': str(rendered),
        'implementation_bundle': str(bundle),
        'trusted_modified_sha256': modified['receipt_sha256'],
        'node': str(node), 'node_sha256': file_hash(node),
        'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
        'npm_tree_sha256': digest(installer._tree(npm.parent.parent)),
        'tooling_directory': str(tooling), 'offline_cache': str(tmp_path / 'cache'),
        'package_directory': str(package_parent / 'package'),
        'environment_parent': str(environment_parent)}
    package_plan = installer.plan_node_package(request_install)
    wrong = source / 'package.json'
    original = wrong.read_bytes()
    wrong.write_bytes(original + b'\n')
    with pytest.raises(InputError, match='drift|changed'):
        installer._check_plan(package_plan)
    wrong.write_bytes(original)
    package_receipt = installer.build_node_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_node_install(package_plan, package_receipt,
        trusted_package_receipt_sha256=package_receipt['receipt_sha256'])
    installed = installer.install_node_package(install_plan,
        approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan,
        trusted_receipt_sha256=installed['receipt_sha256'])['status'] == 'installed_recorded'
    assert installed['command'][0] == str(node)
    assert Path(installed['command'][1]).is_relative_to(Path(installed['generation_path']) / 'app')
    assert file_hash(Path(installed['command'][1])) == installed['entrypoint_sha256']
    assert package_plan['toolchain']['node_sha256'] == file_hash(node)
    assert package_plan['toolchain']['npm_tree_sha256'] == digest(installer._tree(npm.parent.parent))
    assert package_plan['toolchain']['typescript_tree_sha256'] == digest(
        installer._tree(tooling / 'node_modules/typescript'))
    return {'source': source, 'bundle': bundle, 'rollback_digest': verified['rollback_digest'],
            'reviewed_host_source': reviewed_host_source,
            'host_ts_sha256': file_hash(host_ts), 'compiled_sha256': compiled_sha256,
            'install_plan': install_plan, 'installed': installed, 'version': version,
            'item': item}


def _observe(path: Path, status: dict) -> dict:
    for _ in range(150):
        status = session.observe_node_session(path,
            trusted_session_head=status['session_head_sha256'])
        if status['observations']['integration_reachable']:
            return status
        time.sleep(.01)
    raise AssertionError('installed Node integration effect not observed')


def test_real_installed_typescript_upgrade_and_retained_rollback(tmp_path, monkeypatch):
    tools = native_tools()
    compiler_name = os.environ.get('JEV_TRUSTED_TYPESCRIPT_PACKAGE')
    compiler = Path(compiler_name) if compiler_name else Path('/nonexistent-typescript-package')
    if tools is None or not (compiler / 'lib/typescript.js').is_file():
        pytest.skip('pinned Linux Node/npm and trusted TypeScript 5.8.3 required')
    node, npm = tools
    assert file_hash(node) == NODE_SHA256
    assert file_hash(npm) == NPM_CLI_SHA256
    assert digest(installer._tree(npm.parent.parent)) == NPM_TREE_SHA256
    tooling = tmp_path / 'tooling'
    (tooling / 'node_modules').mkdir(parents=True)
    os.chmod(tooling, 0o700)
    reviewed_compiler = digest(installer._tree(compiler))
    assert reviewed_compiler == TRUSTED_TYPESCRIPT_TREE_SHA256
    shutil.copytree(compiler, tooling / 'node_modules/typescript')
    assert digest(installer._tree(tooling / 'node_modules/typescript')) == reviewed_compiler
    identity = trusted_js_tool_identity(tooling)
    assert identity['compiler_version'] == '5.8.3'
    cache = tmp_path / 'cache'
    cache.mkdir(mode=0o700)
    old = _installed(tmp_path, 'version-one', '1.0.0', 'x', tooling, node, npm)
    new = _installed(tmp_path, 'version-two', '1.0.1', 'y', tooling, node, npm)
    assert old['host_ts_sha256'] != new['host_ts_sha256']
    assert old['compiled_sha256'] != new['compiled_sha256']
    for host in (old, new):
        app = Path(host['installed']['generation_path']) / 'app'
        assert file_hash(app / 'host.ts') == host['host_ts_sha256']
        assert file_hash(app / 'host.mjs') == host['compiled_sha256']
    assert old['installed']['generation_id'] != new['installed']['generation_id']
    assert old['installed']['source_sha256'] != new['installed']['source_sha256']

    def descriptor(host: dict, name: str) -> tuple[dict, dict, bytes]:
        observation, environment, effect = _observations(tmp_path / name,
                                                           host['version'], host['item'])
        with pytest.raises(InputError, match='Externally anchored'):
            delivery.plan_node_delivery(host['install_plan'],
                trusted_install_receipt_sha256='0' * 64,
                observation=observation, launch_environment=environment)
        plan = delivery.plan_node_delivery(host['install_plan'],
            trusted_install_receipt_sha256=host['installed']['receipt_sha256'],
            observation=observation, launch_environment=environment)
        assert delivery.validate_node_delivery(plan)['status'] == 'verified_unlaunched'
        return plan, environment, effect

    old_plan, old_env, old_effect = descriptor(old, 'old-effects')
    new_plan, new_env, new_effect = descriptor(new, 'new-effects')
    path = tmp_path / 'node-session'
    created = session.create_node_session(path, old_plan)
    launch = _scope(created, 'launch', old_plan)
    original_append = session._append

    def interrupt_before_release(directory, rows, event, state):
        if event == 'launched':
            raise RuntimeError('typescript-before-release')
        return original_append(directory, rows, event, state)

    # Interrupted start: intent is journaled, the child is never released.
    monkeypatch.setattr(session, '_append', interrupt_before_release)
    with pytest.raises(RuntimeError, match='typescript-before-release'):
        session.launch_node_session(path, scope=launch,
            approved_scope_sha256=launch['scope_sha256'])
    monkeypatch.setattr(session, '_append', original_append)
    pending = session.node_session_status(path)
    assert pending['pending'] == 'launch' and pending['run_id'] == created['run_id']
    assert pending['attempts']['launch'] == 1
    assert not any(Path(value).exists() for value in old_env.values())
    with pytest.raises(InputError):
        session.launch_node_session(path, scope=launch,
            approved_scope_sha256=launch['scope_sha256'])
    with pytest.raises(InputError):
        session.resume_node_session(path, trusted_session_head='0' * 64)
    recovered = session.resume_node_session(path,
        trusted_session_head=pending['session_head_sha256'])
    assert recovered['stage'] == 'created' and recovered['run_id'] == created['run_id']
    assert recovered['generation_id'] == old['installed']['generation_id']
    assert not any(Path(value).exists() for value in old_env.values())
    app = Path(old['installed']['generation_path']) / 'app'
    assert file_hash(app / 'host.ts') == old['host_ts_sha256']
    assert file_hash(app / 'host.mjs') == old['compiled_sha256']
    with pytest.raises(InputError):
        session.launch_node_session(path, scope=launch,
            approved_scope_sha256=launch['scope_sha256'])
    launch = _scope(recovered, 'launch', old_plan)
    running = session.launch_node_session(path, scope=launch,
        approved_scope_sha256=launch['scope_sha256'])
    assert running['attempts']['launch'] == 2
    observed = _observe(path, running)
    assert Path(old_env['NODE_EFFECT_PATH']).read_bytes() == old_effect
    assert all(file_hash(Path(row['path'])) == row['expected_sha256']
               for row in old_plan['observation']['checks'])
    stop = _scope(observed, 'stop', old_plan)
    stopped = session.stop_node_session(path, scope=stop,
        approved_scope_sha256=stop['scope_sha256'], grace_seconds=0)
    assert stopped['stage'] == 'stopped' and not stopped['process_alive']

    upgrade = _scope(stopped, 'upgrade', old_plan,
                     extra=new_plan['descriptor_sha256'])
    old_source = old['source'] / 'package.json'
    original_source = old_source.read_bytes()
    old_source.write_bytes(original_source + b'\n')
    with pytest.raises(InputError):
        session.upgrade_node_session(path, new_plan, scope=upgrade,
            approved_scope_sha256=upgrade['scope_sha256'])
    assert session.node_session_status(path)['stage'] == 'stopped'
    old_source.write_bytes(original_source)
    installed_entry = Path(new['installed']['command'][1])
    reviewed = installed_entry.read_bytes()
    installed_entry.write_bytes(reviewed + b'\n// drift\n')
    with pytest.raises(InputError):
        session.upgrade_node_session(path, new_plan, scope=upgrade,
            approved_scope_sha256=upgrade['scope_sha256'])
    assert session.node_session_status(path)['stage'] == 'stopped'
    assert not Path(new_env['NODE_EFFECT_PATH']).exists()
    installed_entry.write_bytes(reviewed)
    with pytest.raises(InputError):
        session.upgrade_node_session(path, new_plan, scope=upgrade,
            approved_scope_sha256='0' * 64)
    upgraded = session.upgrade_node_session(path, new_plan, scope=upgrade,
        approved_scope_sha256=upgrade['scope_sha256'])
    assert upgraded['stage'] == 'upgrade_staged'
    assert upgraded['run_id'] == created['run_id']
    launch_new = _scope(upgraded, 'launch', new_plan)
    running_new = session.launch_node_session(path, scope=launch_new,
        approved_scope_sha256=launch_new['scope_sha256'])
    observed_new = _observe(path, running_new)
    assert Path(new_env['NODE_EFFECT_PATH']).read_bytes() == new_effect
    assert old_effect != new_effect
    assert all(file_hash(Path(row['path'])) == row['expected_sha256']
               for row in new_plan['observation']['checks'])
    disable = _scope(observed_new, 'disable', new_plan)
    disabled = session.stop_node_session(path, scope=disable,
        approved_scope_sha256=disable['scope_sha256'], disable=True, grace_seconds=0)
    assert disabled['stage'] == 'disabled' and not disabled['process_alive']
    rollback = _scope(disabled, 'rollback', new_plan,
                      extra=disabled['previous_generation_rollback_digest'])
    restored = session.rollback_node_session(path, scope=rollback,
        approved_scope_sha256=rollback['scope_sha256'])
    assert restored['stage'] == 'rolled_back'
    assert restored['generation_id'] == old['installed']['generation_id']
    assert restored['run_id'] == created['run_id']
    assert not restored['observations']['launched']
    assert Path(old['installed']['generation_path']).is_dir()
    assert Path(new['installed']['generation_path']).is_dir()
    assert Path(old_env['NODE_EFFECT_PATH']).read_bytes() == old_effect
    assert Path(new_env['NODE_EFFECT_PATH']).read_bytes() == new_effect
    old_relaunch = _scope(restored, 'launch', old_plan)
    with pytest.raises(InputError):
        session.launch_node_session(path, scope=old_relaunch,
            approved_scope_sha256=old_relaunch['scope_sha256'])
    assert session.node_session_status(path)['generation_id'] == old['installed']['generation_id']
    for host in (new, old):
        result = rollback_js(host['source'], host['bundle'], host['rollback_digest'],
                             tooling_dir=tooling)
        assert result['status'] == 'rolled_back'
        assert (host['source'] / 'host.ts').read_bytes() == host['reviewed_host_source']
        assert not (host['source'] / 'host.mjs').exists()
