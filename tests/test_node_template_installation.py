"""Native offline Node package/install effects; JS source review is separately anchored."""
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator import template_node_installation as node_install
from jev_integration_evaluator import template_js_catalog
from jev_integration_evaluator import template_node_delivery as node_delivery
from jev_integration_evaluator import template_node_session as node_session
from jev_integration_evaluator.template_catalog import materialize_template
from jev_integration_evaluator.integrations.js_lifecycle import (
    plan_js, verify_js, apply_js, status_js)
from jev_integration_evaluator.integrations.js_backend import trusted_js_tool_identity
from jev_integration_evaluator.io import write_json
from test_js_template_delivery import request_for


@pytest.mark.parametrize('format_name', ['esm', 'commonjs', 'typescript'])
def test_real_source_verified_node_install_and_normal_command(tmp_path, format_name):
    tools = native_tools()
    compiler_name = os.environ.get('JEV_TRUSTED_TYPESCRIPT_PACKAGE')
    compiler_source = Path(compiler_name) if compiler_name else Path('/nonexistent-typescript-package')
    if tools is None or not (compiler_source / 'lib/typescript.js').is_file():
        pytest.skip('native pinned Node/npm and local trusted TypeScript 5.8.3 required')
    node, npm = tools
    tooling = tmp_path / 'tooling'; (tooling / 'node_modules').mkdir(parents=True)
    os.chmod(tooling, 0o700)
    source_tree_sha256 = digest(node_install._tree(compiler_source))
    shutil.copytree(compiler_source, tooling / 'node_modules/typescript')
    assert digest(node_install._tree(tooling / 'node_modules/typescript')) == source_tree_sha256
    assert json.loads((tooling / 'node_modules/typescript/package.json').read_text())['version'] == '5.8.3'
    package_metadata = tooling / 'node_modules/typescript/package.json'
    original_metadata = package_metadata.read_bytes()
    wrong_metadata = json.loads(original_metadata)
    wrong_metadata['version'] = '5.9.3'
    package_metadata.write_text(json.dumps(wrong_metadata), encoding='utf-8')
    with pytest.raises(InputError, match='TypeScript 5.8.3'):
        trusted_js_tool_identity(tooling)
    package_metadata.write_bytes(original_metadata)
    host, source_request = request_for(tmp_path, format_name)
    if format_name != 'typescript':
        source_request['entrypoint'] = ('start.cjs' if format_name == 'commonjs' else 'start.mjs')
        package_json = host / 'package.json'
        package = json.loads(package_json.read_text(encoding='utf-8'))
        package['scripts']['start'] = 'node ' + source_request['entrypoint']
        package_json.write_text(json.dumps(package), encoding='utf-8')
        source_request['package_json_sha256'] = file_hash(package_json)
    entry = host / source_request['entrypoint']
    if format_name == 'commonjs':
        effect_code = ('const fs = require("node:fs");\n'
                       'const seam = require("./host.cjs");\n')
    else:
        effect_code = ('import fs from "node:fs";\n'
                       'import {seam} from "./host.mjs";\n')
    effect_code += (
        'if (process.env.JEV_RUNTIME_MODE !== "off") throw Error("mode");\n'
        'for (const key of ["NODE_EFFECT_PATH","NODE_READY_PATH","NODE_INTEGRATION_PATH"]) '
        'if (!process.env[key]) throw Error("missing path");\n'
        'globalThis.__jev_probe_effect = (action,item) => '
        'fs.writeFileSync(process.env.NODE_EFFECT_PATH, action+":"+item+"\\n", {flag:"wx"});\n'
        'async function main() {\n'
        '  const result = await seam({task_id:"task",invocation_id:"normal",item:"x",permit:true});\n'
        '  if (result !== "read:x") throw Error("seam result");\n'
        '  fs.writeFileSync(process.env.NODE_READY_PATH,"ready\\n",{flag:"wx"});\n'
        '  fs.writeFileSync(process.env.NODE_INTEGRATION_PATH,"integration\\n",{flag:"wx"});\n'
        '  await new Promise(resolve => setTimeout(resolve, 800));\n'
        '}\n')
    effect_code += ('main().catch(() => {process.exitCode = 1;});\n')
    entry.write_text(effect_code, encoding='utf-8')
    source_request['entrypoint_sha256'] = file_hash(entry)
    source_request['reviewed_package_source_sha256'] = digest(template_js_catalog._source_tree(host))
    rendered = tmp_path / 'render'
    materialize_template(host, source_request, rendered, tooling_dir=tooling)
    bundle = tmp_path / 'bundle'
    planned = plan_js(host, source_request['implementation_spec'], bundle, tooling_dir=tooling)
    cases = [dict(id='read', request=dict(task_id='task', invocation_id='one',
                                        item='x', permit=True), result='read:x',
                  events=[['read', 'x']], effects=[['read', 'x']])]
    baseline = verify_js(host, bundle, 'baseline', cases, tooling_dir=tooling,
                         approve_execution=True)
    assert baseline['status'] == 'passed'
    apply_js(host, bundle, planned['bundle_sha256'],
             baseline_sha256=baseline['receipt_sha256'], tooling_dir=tooling)
    modified = verify_js(host, bundle, 'modified', cases, tooling_dir=tooling,
                         baseline_sha256=baseline['receipt_sha256'], approve_execution=True)
    assert modified['status'] == 'passed'
    assert status_js(host, bundle, tooling_dir=tooling,
                     trusted_modified_sha256=modified['receipt_sha256'])['status'] == 'verified'
    for name in ('cache', 'packages', 'generations'):
        path = tmp_path / name; path.mkdir(mode=0o700); os.chmod(path, 0o700)
    request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
               'host_root': str(host), 'render_directory': str(rendered),
               'implementation_bundle': str(bundle),
               'trusted_modified_sha256': modified['receipt_sha256'],
               'node': str(node), 'node_sha256': file_hash(node),
               'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
               'npm_tree_sha256': digest(node_install._tree(npm.parent.parent)),
               'tooling_directory': str(tooling), 'offline_cache': str(tmp_path / 'cache'),
               'package_directory': str(tmp_path / 'packages/package'),
               'environment_parent': str(tmp_path / 'generations')}
    package_plan = node_install.plan_node_package(request)
    assert package_plan['toolchain']['typescript_tree_sha256'] == source_tree_sha256
    os.chmod(tooling, 0o755)
    with pytest.raises(InputError, match='owner-private'):
        node_install.plan_node_package(request)
    os.chmod(tooling, 0o700)
    compiler_sibling = tooling / 'node_modules/typescript/lib/tsc.js'
    original_sibling = compiler_sibling.read_bytes()
    compiler_sibling.write_bytes(original_sibling + b'\n// drift\n')
    with pytest.raises(InputError, match='drift'):
        node_install._check_plan(package_plan)
    compiler_sibling.write_bytes(original_sibling)
    package = node_install.build_node_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = node_install.plan_node_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    installed = node_install.install_node_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert node_install.installation_status(
        install_plan, trusted_receipt_sha256=installed['receipt_sha256'])['status'] == 'installed_recorded'
    effect = tmp_path / 'independent-entrypoint-effect.bin'
    ready = tmp_path / 'independent-ready.bin'
    integration = tmp_path / 'independent-integration.bin'
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [
                       {'role': role, 'path': str(path), 'before_sha256': None,
                        'expected_sha256': __import__('hashlib').sha256(raw).hexdigest()}
                       for role, path, raw in (
                           ('ready', ready, b'ready\n'),
                           ('entrypoint_reached', effect, b'read:x\n'),
                           ('integration_reachable', integration, b'integration\n'))]}
    environment = {'NODE_EFFECT_PATH': str(effect), 'NODE_READY_PATH': str(ready),
                   'NODE_INTEGRATION_PATH': str(integration)}
    descriptor = node_delivery.plan_node_delivery(
        install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
        observation=observation, launch_environment=environment)
    assert node_delivery.validate_node_delivery(descriptor)['status'] == 'verified_unlaunched'
    assert Path(descriptor['command'][1]).is_relative_to(Path(installed['generation_path']) / 'app')
    assert file_hash(Path(descriptor['command'][0])) == descriptor['executable_sha256']
    assert file_hash(Path(descriptor['command'][1])) == descriptor['entrypoint_sha256']
    with pytest.raises(InputError, match='Externally anchored'):
        node_delivery.plan_node_delivery(
            install_plan, trusted_install_receipt_sha256='0' * 64,
            observation=observation, launch_environment=environment)
    with pytest.raises(InputError, match='launch environment'):
        node_delivery.plan_node_delivery(
            install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
            observation=observation, launch_environment={'NODE_OPTIONS': '--require unsafe'})
    for altered in ({**environment, 'NODE_READY_PATH': str(effect)},
                    {**environment, 'NODE_EFFECT_PATH': str(ready)},
                    {**environment, 'NODE_INTEGRATION_PATH': str(effect)},
                    {**environment, 'NODE_EFFECT_PATH': str(Path(installed['generation_path']) / 'app' / 'effect.bin')},
                    {key: value for key, value in environment.items() if key != 'NODE_READY_PATH'}):
        with pytest.raises(InputError, match='does not match observed roles'):
            node_delivery.plan_node_delivery(
                install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
                observation=observation, launch_environment=altered)
    linked_parent = tmp_path / 'linked-output-parent'
    linked_parent.symlink_to(tmp_path, target_is_directory=True)
    linked_effect = str(linked_parent / 'linked-effect.bin')
    with pytest.raises(InputError, match='does not match observed roles'):
        node_delivery.plan_node_delivery(
            install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
            observation=observation,
            launch_environment={**environment, 'NODE_EFFECT_PATH': linked_effect})
    with pytest.raises(InputError, match='linked'):
        node_delivery.plan_node_delivery(
            install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
            observation={**observation, 'checks': [observation['checks'][0],
                {**observation['checks'][1], 'path': linked_effect}, observation['checks'][2]]},
            launch_environment={**environment, 'NODE_EFFECT_PATH': linked_effect})
    for loader in ('LD_PRELOAD', 'LD_LIBRARY_PATH'):
        with pytest.raises(InputError, match='launch environment'):
            node_delivery.plan_node_delivery(
                install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
                observation=observation, launch_environment={loader: '/tmp/unsafe.so'})
    with pytest.raises(InputError, match='parent traversal'):
        node_delivery.plan_node_delivery(
            install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
            observation={**observation, 'checks': [
                {**observation['checks'][0], 'path': str(tmp_path / 'alias' / '..' / ready.name)},
                *observation['checks'][1:]]}, launch_environment=environment)
    with pytest.raises(InputError, match='parent traversal'):
        node_delivery.plan_node_delivery(
            install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
            observation={**observation, 'checks': [
                {**observation['checks'][0], 'path': str(Path(installed['generation_path']) / 'app' / '..' / 'ready.bin')},
                *observation['checks'][1:]]}, launch_environment=environment)
    with pytest.raises(InputError, match='observation'):
        node_delivery.plan_node_delivery(
            install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
            observation={**observation, 'checks': [
                {**observation['checks'][0], 'path': str(Path(installed['generation_path']) / 'app')},
                *observation['checks'][1:]]}, launch_environment=environment)
    run = subprocess.run(descriptor['command'], cwd=descriptor['working_directory'],
                         env={'PATH': '/usr/bin:/bin', 'JEV_RUNTIME_MODE': 'off', **environment},
                         capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stderr
    assert effect.read_bytes() == b'read:x\n'
    assert ready.read_bytes() == b'ready\n'
    assert integration.read_bytes() == b'integration\n'
    for row in observation['checks']:
        assert file_hash(Path(row['path'])) == row['expected_sha256']
    with pytest.raises(InputError, match='observation baseline'):
        node_delivery.validate_node_delivery(descriptor)

    supervised_paths = {key: tmp_path / ('supervised-' + key + '.bin') for key in environment}
    supervised_observation = {'schema_version': '1.0',
        'kind': 'template-delivery-observation-v1', 'checks': [
            {**row, 'path': str(supervised_paths[next(key for key, value in environment.items()
                                                     if value == row['path'])])}
            for row in observation['checks']]}
    supervised_env = {key: str(path) for key, path in supervised_paths.items()}
    supervised = node_delivery.plan_node_delivery(install_plan,
        trusted_install_receipt_sha256=installed['receipt_sha256'],
        observation=supervised_observation, launch_environment=supervised_env)
    owned_session = tmp_path / 'node-session'
    created = node_session.create_node_session(owned_session, supervised)
    assert created['stage'] == 'created' and created['current_installation'] == 'current_verified'
    def scope(result, action, selected=supervised):
        value = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
                 'reference': 'independent-native-test-operator', 'run_id': result['run_id'],
                 'plan_sha256': selected['descriptor_sha256'],
                 'trusted_session_head': result['session_head_sha256'],
                 'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                 'revoked': False, 'grants': {name: name == action for name in
                     ('launch', 'stop', 'disable', 'upgrade', 'rollback')}}
        value['scope_sha256'] = digest(value)
        return value
    if format_name == 'esm':
        # Exercise the installed Node command through two real waiting-child
        # interruptions. Neither helper receives the release byte.
        for interruption in ('before_identity', 'before_release'):
            fault_paths = {key: tmp_path / f'{interruption}-{key}.bin'
                           for key in environment}
            fault_observation = {'schema_version': '1.0',
                'kind': 'template-delivery-observation-v1', 'checks': [
                    {**row, 'path': str(fault_paths[next(key for key, value in environment.items()
                                                       if value == row['path'])])}
                    for row in observation['checks']]}
            fault_descriptor = node_delivery.plan_node_delivery(
                install_plan, trusted_install_receipt_sha256=installed['receipt_sha256'],
                observation=fault_observation,
                launch_environment={key: str(path) for key, path in fault_paths.items()})
            fault_session = tmp_path / ('node-session-' + interruption)
            fault_created = node_session.create_node_session(fault_session, fault_descriptor)
            fault_scope = scope(fault_created, 'launch', fault_descriptor)
            if interruption == 'before_identity':
                original_append = node_session._append
                def interrupt_append(directory, rows, event, state):
                    if event == 'launched':
                        raise RuntimeError('injected_before_identity')
                    return original_append(directory, rows, event, state)
                node_session._append = interrupt_append
            else:
                original_write = os.write
                def interrupt_release(fd, raw):
                    if raw == b'G':
                        raise RuntimeError('injected_before_release')
                    return original_write(fd, raw)
                node_session.os.write = interrupt_release
            try:
                with pytest.raises(RuntimeError, match='injected_before_'):
                    node_session.launch_node_session(
                        fault_session, scope=fault_scope,
                        approved_scope_sha256=fault_scope['scope_sha256'])
            finally:
                if interruption == 'before_identity':
                    node_session._append = original_append
                else:
                    node_session.os.write = original_write
            pending = node_session.node_session_status(fault_session)
            assert pending['stage'] == ('launch_pending' if interruption ==
                'before_identity' else 'running')
            assert pending['pending'] == 'launch'
            assert pending['run_id'] == fault_created['run_id']
            assert not any(path.exists() for path in fault_paths.values())
            recovered = node_session.resume_node_session(
                fault_session, trusted_session_head=pending['session_head_sha256'])
            assert recovered['attempts']['launch'] == 1
            assert not any(path.exists() for path in fault_paths.values())
            if interruption == 'before_identity':
                assert recovered['stage'] == 'created'
                retry_scope = scope(recovered, 'launch', fault_descriptor)
                retried = node_session.launch_node_session(
                    fault_session, scope=retry_scope,
                    approved_scope_sha256=retry_scope['scope_sha256'])
                for _ in range(150):
                    if all(path.is_file() for path in fault_paths.values()):
                        break
                    time.sleep(.01)
                for row in fault_observation['checks']:
                    assert file_hash(Path(row['path'])) == row['expected_sha256']
                stop_scope = scope(retried, 'stop', fault_descriptor)
                stopped = node_session.stop_node_session(
                    fault_session, scope=stop_scope,
                    approved_scope_sha256=stop_scope['scope_sha256'], grace_seconds=0)
                assert stopped['stage'] == 'stopped' and not stopped['process_alive']
            else:
                assert recovered['stage'] == 'blocked_recovery'
                retry_scope = scope(recovered, 'launch', fault_descriptor)
                with pytest.raises(InputError, match='launch_blocked'):
                    node_session.launch_node_session(
                        fault_session, scope=retry_scope,
                        approved_scope_sha256=retry_scope['scope_sha256'])
                for _ in range(100):
                    if not node_session.node_session_status(fault_session)['process_alive']:
                        break
                    time.sleep(.01)
                assert not node_session.node_session_status(fault_session)['process_alive']
                assert not any(path.exists() for path in fault_paths.values())
    launch_scope = scope(created, 'launch')
    source_file = host / 'package.json'
    unchanged_source = source_file.read_bytes()
    source_file.write_bytes(unchanged_source + b'\n')
    with pytest.raises(InputError):
        node_session.launch_node_session(owned_session, scope=launch_scope,
            approved_scope_sha256=launch_scope['scope_sha256'])
    assert node_session.node_session_status(owned_session)['stage'] == 'created'
    assert not any(path.exists() for path in supervised_paths.values())
    source_file.write_bytes(unchanged_source)
    running = node_session.launch_node_session(owned_session, scope=launch_scope,
        approved_scope_sha256=launch_scope['scope_sha256'])
    observed = running
    for _ in range(150):
        observed = node_session.observe_node_session(owned_session,
            trusted_session_head=observed['session_head_sha256'])
        if observed['observations']['integration_reachable']:
            break
        time.sleep(.01)
    assert observed['process_alive']
    assert all(value for name, value in observed['observations'].items()
               if name != 'outcome_verified')
    for row in supervised_observation['checks']:
        assert file_hash(Path(row['path'])) == row['expected_sha256']
    disable_scope = scope(observed, 'disable')
    disabled = node_session.stop_node_session(owned_session, scope=disable_scope,
        approved_scope_sha256=disable_scope['scope_sha256'], disable=True, grace_seconds=0)
    assert disabled['stage'] == 'disabled' and not disabled['process_alive']
    assert node_session.node_session_status(owned_session,
        trusted_session_head=disabled['session_head_sha256'])['run_id'] == created['run_id']


def native_tools():
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        return None
    node = shutil.which('node')
    if not node:
        return None
    node = Path(node).resolve()
    npm = node.parent.parent / 'lib/node_modules/npm/bin/npm-cli.js'
    if not npm.is_file():
        return None
    versions = (subprocess.run([str(node), '--version'], capture_output=True, text=True).stdout.strip(),
                subprocess.run([str(node), str(npm), '--version'], capture_output=True, text=True).stdout.strip())
    return (node, npm) if versions == ('v24.18.0', '11.16.0') else None


@pytest.mark.parametrize('extension', ['mjs', 'cjs'])
def test_offline_owned_package_install_and_drift(tmp_path, monkeypatch, extension):
    tools = native_tools()
    if tools is None:
        pytest.skip('native pinned Node v24.18.0/npm 11.16.0 absent')
    node, npm = tools
    npm_root = npm.parent.parent
    npm_tree_sha256 = digest(node_install._tree(npm_root))
    host = tmp_path / 'host'; host.mkdir()
    entry = f'start.{extension}'
    (host / entry).write_text('process.stdout.write("off\\n");\n', encoding='utf-8')
    (host / 'package.json').write_text(json.dumps({'name': 'offline-fixture', 'version': '1.0.0',
                               'scripts': {'start': 'node ' + entry}}), encoding='utf-8')
    (host / 'package-lock.json').write_text(json.dumps({'name': 'offline-fixture',
                               'version': '1.0.0', 'lockfileVersion': 3,
                               'packages': {'': {'name': 'offline-fixture', 'version': '1.0.0'}}}),
                               encoding='utf-8')
    source = {path.name: file_hash(path) for path in host.iterdir()}
    for name in ('cache', 'render', 'bundle', 'tooling', 'packages', 'generations'):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
    request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
               'host_root': str(host), 'render_directory': str(tmp_path / 'render'),
               'implementation_bundle': str(tmp_path / 'bundle'),
               'trusted_modified_sha256': 'a' * 64, 'node': str(node),
               'node_sha256': file_hash(node), 'npm_cli': str(npm),
               'npm_cli_sha256': file_hash(npm), 'npm_tree_sha256': npm_tree_sha256,
               'tooling_directory': str(tmp_path / 'tooling'),
               'offline_cache': str(tmp_path / 'cache'),
               'package_directory': str(tmp_path / 'packages' / 'package'),
               'environment_parent': str(tmp_path / 'generations')}
    toolchain = {'node': str(node), 'node_sha256': file_hash(node),
                 'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
                 'npm_root': str(npm_root), 'npm_tree_sha256': npm_tree_sha256,
                 'node_version': 'v24.18.0', 'npm_version': '11.16.0', 'tooling': {}}
    plan = {'schema_version': '1.0', 'kind': 'node-package-plan-v1',
            'request': request, 'render_lock_sha256': 'b' * 64,
            'implementation_plan_sha256': 'c' * 64,
            'applied_source_files': source, 'applied_source_sha256': digest(source),
            'offline_cache_sha256': digest({}), 'toolchain': toolchain,
            'configuration_sha256': 'd' * 64, 'secret_references_sha256': 'e' * 64,
            'package_profile_sha256': 'f' * 64, 'format': 'esm' if extension == 'mjs' else 'commonjs',
            'entrypoint': entry, 'mode': 'off', 'runtime_activation_authorized': False}
    plan['plan_sha256'] = digest(plan)
    # The source/render/modified-receipt verifier needs trusted TS 5.8.3.
    # This fixture replaces only that upstream read-only planner so the real
    # native npm effect and owned generation can be tested without it.
    monkeypatch.setattr(node_install, 'plan_node_package',
                        lambda actual, _allow_existing_output=False: plan if actual == request else None)
    with pytest.raises(InputError, match='approval'):
        node_install.build_node_package(plan, approved_plan_sha256='0' * 64)
    package = node_install.build_node_package(plan, approved_plan_sha256=plan['plan_sha256'])
    assert node_install.package_status(plan, trusted_receipt_sha256=package['receipt_sha256'])['status'] == 'packaged_recorded'
    package_root = Path(package['package_directory'])
    os.chmod(package_root, 0o755)
    with pytest.raises(InputError, match='identity or permissions'):
        node_install.package_status(plan, trusted_receipt_sha256=package['receipt_sha256'])
    os.chmod(package_root, 0o700)
    staged_entry = Path(package['package_directory']) / 'app' / entry
    original = staged_entry.read_bytes()
    staged_entry.write_text('changed\n', encoding='utf-8')
    with pytest.raises(InputError, match='drift'):
        node_install.package_status(plan, trusted_receipt_sha256=package['receipt_sha256'])
    staged_entry.write_bytes(original)
    with pytest.raises(InputError, match='Externally anchored'):
        node_install.plan_node_install(plan, package, trusted_package_receipt_sha256='0' * 64)
    install_plan = node_install.plan_node_install(
        plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    with pytest.raises(InputError, match='approval'):
        node_install.install_node_package(install_plan, approved_plan_sha256='0' * 64)
    receipt = node_install.install_node_package(install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert receipt['command'][0] == str(node) and receipt['mode'] == 'off'
    assert receipt['launch_status'] == 'not_started'
    assert node_install.installation_status(install_plan, trusted_receipt_sha256=receipt['receipt_sha256'])['status'] == 'installed_recorded'
    generation_root = Path(receipt['generation_path'])
    os.chmod(generation_root, 0o755)
    with pytest.raises(InputError, match='identity or permissions'):
        node_install.installation_status(install_plan, trusted_receipt_sha256=receipt['receipt_sha256'])
    os.chmod(generation_root, 0o700)
    installed_entry = Path(receipt['command'][1])
    installed_entry.write_text('changed\n', encoding='utf-8')
    with pytest.raises(InputError, match='drift'):
        node_install.installation_status(install_plan, trusted_receipt_sha256=receipt['receipt_sha256'])
    interrupted_request = dict(request, package_directory=str(tmp_path / 'packages' / 'interrupted'))
    interrupted_plan = dict(plan, request=interrupted_request)
    interrupted_plan['plan_sha256'] = digest({k: v for k, v in interrupted_plan.items()
                                              if k != 'plan_sha256'})
    monkeypatch.setattr(node_install, 'plan_node_package',
                        lambda actual, _allow_existing_output=False:
                        plan if actual == request else interrupted_plan if actual == interrupted_request else None)
    original_safe_new = node_install._safe_new
    def interrupted_create(path):
        if extension == 'cjs':
            original_safe_new(path)
        raise RuntimeError('injected interruption at directory creation')
    monkeypatch.setattr(node_install, '_safe_new', interrupted_create)
    with pytest.raises(RuntimeError, match='injected interruption'):
        node_install.build_node_package(
            interrupted_plan, approved_plan_sha256=interrupted_plan['plan_sha256'])
    interrupted = node_install.package_status(interrupted_plan)
    assert interrupted == {'status': 'build_interrupted_review_required',
                           'stage': 'directory_created' if extension == 'cjs' else 'intent_recorded'}
    markerless_root = Path(interrupted_request['package_directory'])
    markerless_root.mkdir(exist_ok=True)
    os.chmod(markerless_root, 0o755)
    with pytest.raises(InputError, match='identity or permissions'):
        node_install.package_status(interrupted_plan)
    os.chmod(markerless_root, 0o700)
    (markerless_root / 'app').mkdir()
    with pytest.raises(InputError, match='markerless package root'):
        node_install.package_status(interrupted_plan)
    with pytest.raises((FileExistsError, InputError)):
        node_install.build_node_package(
            interrupted_plan, approved_plan_sha256=interrupted_plan['plan_sha256'])


def test_missing_trusted_typescript_fails_before_output(tmp_path):
    tools = native_tools()
    if tools is None:
        pytest.skip('native pinned Node v24.18.0/npm 11.16.0 absent')
    node, npm = tools
    npm_tree_sha256 = digest(node_install._tree(npm.parent.parent))
    for name in ('host', 'render', 'bundle', 'tooling', 'cache', 'packages', 'generations'):
        (tmp_path / name).mkdir(mode=0o700)
        os.chmod(tmp_path / name, 0o700)
    request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
               'host_root': str(tmp_path / 'host'), 'render_directory': str(tmp_path / 'render'),
               'implementation_bundle': str(tmp_path / 'bundle'),
               'trusted_modified_sha256': 'a' * 64,
               'node': str(node), 'node_sha256': file_hash(node),
               'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
               'npm_tree_sha256': npm_tree_sha256,
               'tooling_directory': str(tmp_path / 'tooling'),
               'offline_cache': str(tmp_path / 'cache'),
               'package_directory': str(tmp_path / 'packages' / 'new'),
               'environment_parent': str(tmp_path / 'generations')}
    with pytest.raises(InputError, match='tooling|compiler'):
        node_install.plan_node_package(request)
    assert not (tmp_path / 'packages' / 'new').exists()


def test_npm_loaded_sibling_module_drift_rejected(tmp_path):
    tools = native_tools()
    if tools is None:
        pytest.skip('native pinned Node v24.18.0/npm 11.16.0 absent')
    node, npm = tools
    root = tmp_path / 'npm'
    shutil.copytree(npm.parent.parent, root, symlinks=True)
    npm_copy = root / 'bin/npm-cli.js'
    tree_sha256 = digest(node_install._tree(root))
    sibling = root / 'lib/cli.js'  # Loaded directly by npm-cli.js.
    sibling.write_bytes(sibling.read_bytes() + b'\n// drift\n')
    host = tmp_path / 'host'; host.mkdir()
    tooling = tmp_path / 'tooling'; tooling.mkdir(mode=0o700); os.chmod(tooling, 0o700)
    request = {'node': str(node), 'node_sha256': file_hash(node),
               'npm_cli': str(npm_copy), 'npm_cli_sha256': file_hash(npm_copy),
               'npm_tree_sha256': tree_sha256, 'tooling_directory': str(tooling)}
    with pytest.raises(InputError, match='npm package modules changed'):
        node_install._toolchain(request, host)


def test_install_intent_classifies_pre_marker_interruption(tmp_path, monkeypatch):
    if platform.system() != 'Linux':
        pytest.skip('native Linux intent journal required')
    parent = tmp_path / 'generations'; parent.mkdir(mode=0o700)
    os.chmod(parent, 0o700)
    root = parent / 'jev-node-env-interrupted'
    plan = {'plan_sha256': 'a' * 64}
    monkeypatch.setattr(node_install, '_check_install', lambda _: root)
    node_install._intent(root, plan['plan_sha256'], 'node-generation-intent-v1', create=True)
    assert node_install.installation_status(plan) == {
        'status': 'install_interrupted_review_required', 'stage': 'intent_recorded'}
    root.mkdir(mode=0o700)
    assert node_install.installation_status(plan) == {
        'status': 'install_interrupted_review_required', 'stage': 'directory_created'}
    original_ismount = os.path.ismount
    with monkeypatch.context() as patch:
        patch.setattr(os.path, 'ismount',
                      lambda path: Path(path) == root or original_ismount(path))
        with pytest.raises(InputError, match='identity or permissions'):
            node_install.installation_status(plan)
    os.chmod(root, 0o755)
    with pytest.raises(InputError, match='identity or permissions'):
        node_install.installation_status(plan)
    os.chmod(root, 0o700)
    (root / 'app').mkdir()
    with pytest.raises(InputError, match='markerless generation root'):
        node_install.installation_status(plan)


@pytest.mark.parametrize('kind', ['package', 'generation'])
def test_status_rejects_dangling_root_symlink_and_uncommitted_intent(tmp_path, monkeypatch, kind):
    if platform.system() != 'Linux':
        pytest.skip('native Linux ownership checks required')
    parent = tmp_path / 'outputs'; parent.mkdir(mode=0o700)
    os.chmod(parent, 0o700)
    root = parent / 'dangling'
    plan = {'plan_sha256': 'a' * 64, 'request': {'package_directory': str(root)}}
    if kind == 'package':
        monkeypatch.setattr(node_install, '_check_plan', lambda _: None)
        status = node_install.package_status
    else:
        monkeypatch.setattr(node_install, '_check_install', lambda _: root)
        status = node_install.installation_status
    root.symlink_to(parent / 'missing', target_is_directory=True)
    with pytest.raises(InputError, match='root is a symlink'):
        status(plan)
    root.unlink()
    node_install._intent_path(root).with_suffix('.tmp').write_bytes(b'incomplete')
    with pytest.raises(InputError, match='intent precommit incomplete'):
        status(plan)


@pytest.mark.parametrize('format_name', ['esm', 'commonjs'])
def test_planner_binds_render_lock_and_full_applied_source(tmp_path, monkeypatch, format_name):
    tools = native_tools()
    if tools is None:
        pytest.skip('native pinned Node v24.18.0/npm 11.16.0 absent')
    node, npm = tools
    npm_root = npm.parent.parent
    npm_tree_sha256 = digest(node_install._tree(npm_root))
    host, source_request = request_for(tmp_path, format_name)
    source = host / source_request['implementation_spec']['source']['file']
    profile = template_js_catalog._package(host, source_request, format_name)
    render = tmp_path / 'render'; render.mkdir(mode=0o700)
    bundle = tmp_path / 'bundle'; bundle.mkdir(mode=0o700)
    for name in ('cache', 'packages', 'generations', 'tooling'):
        (tmp_path / name).mkdir(mode=0o700)
        os.chmod(tmp_path / name, 0o700)
    os.chmod(render, 0o700)
    os.chmod(bundle, 0o700)
    tool_identity = {'node_path': str(node), 'node_sha256': file_hash(node),
                     'compiler_path': str(tmp_path / 'tooling' / 'typescript.js'),
                     'compiler_sha256': '1' * 64, 'compiler_version': '5.8.3'}
    tool_identity.update({key: '2' * 64 for key in ('transformer_sha256', 'runtime_sha256',
                           'probe_sha256', 'emitter_sha256', 'backend_sha256', 'lifecycle_sha256')})
    toolchain = {'node': str(node), 'node_sha256': file_hash(node),
                 'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
                 'npm_root': str(npm_root), 'npm_tree_sha256': npm_tree_sha256,
                 'node_version': 'v24.18.0', 'npm_version': '11.16.0', 'tooling': tool_identity}
    manifest = template_js_catalog.inspect_js_template()
    resources = {'template-manifest.json': {k: v for k, v in manifest.items() if k != 'manifest_sha256'},
                 'template-request.json': source_request,
                 'implementation-spec.json': source_request['implementation_spec'],
                 'package-profile.json': profile}
    for name, value in resources.items():
        write_json(render / name, value)
    resource_hashes = {name: file_hash(render / name) for name in resources}
    original_source = source.read_text(encoding='utf-8')
    source.write_text(original_source + '\n// reviewed applied fixture\n', encoding='utf-8')
    generated = {source.name: file_hash(source)}
    js_plan = {'spec_sha256': digest(source_request['implementation_spec']),
               'tooling': tool_identity, 'format': format_name,
               'generated_sha256': generated, 'contract_digest': '3' * 64}
    write_json(bundle / 'plan.json', js_plan)
    write_json(bundle / 'modified-receipt.json', {'plan_sha256': '3' * 64, 'status': 'passed'})
    lock = {'schema_version': '1.0', 'status': 'materialized',
            'template_id': 'javascript.recipe-c', 'template_version': '1.0.0',
            'manifest_sha256': manifest['manifest_sha256'],
            'evaluator_version': manifest['evaluator_version'],
            'renderer_sha256': file_hash(Path(template_js_catalog.__file__)),
            'tooling': tool_identity, 'request_sha256': digest(source_request),
            'spec_sha256': digest(source_request['implementation_spec']),
            'candidate_id': source_request['implementation_spec']['candidate_id'],
            'format': format_name, 'source_sha256': source_request['implementation_spec']['source']['sha256'],
            'generated_sha256': file_hash(source), 'emitted_sha256': None,
            'package': profile, 'configuration_sha256': source_request['reviewed_configuration_sha256'],
            'secret_references_sha256': digest({}), 'lifecycle': manifest['lifecycle'],
            'target_modified': False, 'target_executed': False,
            'owned_resources': resource_hashes,
            'planner': {'command': 'js-plan', 'spec': 'implementation-spec.json',
                        'tooling': str(tmp_path / 'tooling'), 'output': 'new external private bundle'}}
    lock['lock_sha256'] = digest(lock)
    write_json(render / 'template-lock.json', lock)
    write_json(render / 'render-status.json', {'schema_version': '1.0', 'status': 'complete',
               'lock_sha256': lock['lock_sha256'], 'resources': resource_hashes})
    request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
               'host_root': str(host), 'render_directory': str(render),
               'implementation_bundle': str(bundle),
               'trusted_modified_sha256': file_hash(bundle / 'modified-receipt.json'),
               'node': str(node), 'node_sha256': file_hash(node),
               'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
               'npm_tree_sha256': npm_tree_sha256,
               'tooling_directory': str(tmp_path / 'tooling'),
               'offline_cache': str(tmp_path / 'cache'),
               'package_directory': str(tmp_path / 'packages' / 'new'),
               'environment_parent': str(tmp_path / 'generations')}
    monkeypatch.setattr(node_install, '_toolchain', lambda *_: toolchain)
    monkeypatch.setattr(node_install.js_lifecycle, 'status_js', lambda *args, **kwargs: {'status': 'verified'})
    plan = node_install.plan_node_package(request)
    assert plan['applied_source_files'][source.name] == file_hash(source)
    assert plan['format'] == format_name and not Path(request['package_directory']).exists()
    (host / 'unreviewed.js').write_text('new file\n', encoding='utf-8')
    with pytest.raises(InputError, match='source drift'):
        node_install.plan_node_package(request)
