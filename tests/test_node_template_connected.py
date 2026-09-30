"""Installed CommonJS connected-shadow protocol with an offline typed transport."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import venv

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash, read_json
from jev_integration_evaluator.template_node_connected import _private_reference, inspect_connected_core
from jev_integration_evaluator.integrations.js_backend import trusted_js_tool_identity
from jev_integration_evaluator.integrations.js_lifecycle import (
    apply_js, plan_js, status_js, verify_js)
from jev_integration_evaluator import template_node_installation as installer
from jev_integration_evaluator import template_js_catalog
from jev_integration_evaluator.template_catalog import materialize_template
from test_js_template_delivery import request_for
from test_node_template_installation import native_tools
from test_node_template_installed_commonjs import _installed
from test_node_template_installed_esm import _copy_reviewed_host, _request as esm_request
from test_node_template_installed_upgrade import (
    NODE_SHA256, NPM_CLI_SHA256, NPM_TREE_SHA256, TRUSTED_TYPESCRIPT_TREE_SHA256,
    _observations,
)


PROJECT = Path(__file__).resolve().parents[1]


def test_connected_raw_gate_reference_rejects_hardlink(tmp_path):
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    raw = private / 'holdout.json'
    raw.write_text('{"evidence_type":"synthetic"}', encoding='utf-8')
    raw.chmod(0o600)
    alias = private / 'other-name.json'
    os.link(raw, alias)
    with pytest.raises(InputError, match='reference unavailable or changed'):
        _private_reference({'path': str(raw), 'sha256': file_hash(raw)}, tmp_path / 'source')
    assert raw.read_text(encoding='utf-8') == '{"evidence_type":"synthetic"}'


def _wait_session_child_exit(session: Path) -> None:
    record = json.loads((session / 'events.jsonl').read_text(encoding='utf-8').splitlines()[-1])
    identity = record['state']['process']
    for _ in range(400):
        try:
            raw = Path(f"/proc/{identity['pid']}/stat").read_text(encoding='ascii')
            fields = raw[raw.rfind(')') + 2:].split()
            if fields[19] != identity['start_ticks'] or fields[0] in ('Z', 'X', 'x'):
                return
        except OSError:
            return
        time.sleep(.05)
    raise AssertionError('owned connected child did not exit within the fault bound')


def _installed_module(tmp_path, fmt, tooling, node, npm):
    work = tmp_path / ('connected-' + fmt)
    work.mkdir(mode=0o700)
    if fmt == 'esm':
        source, _ = _copy_reviewed_host(work / 'source', '1.0.0')
        request, cases = esm_request(source, '1.0.0')
    else:
        source, request = request_for(work, 'typescript')
        cases = [{'id': 'connected-baseline',
                  'request': {'task_id': 'task', 'invocation_id': 'case',
                              'item': 'alpha', 'permit': True},
                  'result': 'read:alpha', 'events': [['read', 'alpha']],
                  'effects': [['read', 'alpha']]}]
    request['implementation_spec']['runtime']['runtime']['model'] = 'jev-1.13.0'
    request['implementation_spec']['verification_sha256'] = digest(cases)
    request['implementation_spec']['verification_cases_count'] = len(cases)
    entry = source / 'start.mjs'
    entry.write_text(
        'import fs from "node:fs";\n'
        'import crypto from "node:crypto";\n'
        'import adapter from "./jev_adapter.cjs";\n'
        'import {seam} from "./host.mjs";\n'
        'if (process.env.JEV_RUNTIME_MODE === "shadow") {\n'
        '  const descriptor = JSON.parse(fs.readFileSync(process.env.JEV_CONNECTED_DESCRIPTOR));\n'
        '  adapter.initializeConnected(descriptor, {\n'
        '    audit: {append() {}},\n'
        '    verifyAuthority: (kind, sha) => kind === "egress_grant" && '
        'sha === process.env.JEV_TRUSTED_EGRESS_GRANT_SHA256,\n'
        '    currentEnvironmentDigest: () => crypto.createHash("sha256")'
        '.update(process.env.TYPESAFE_API_KEY).digest("hex"),\n'
        '    transport: async () => Buffer.from(JSON.stringify({model:"jev-1.13.0", '
        'answers:{choice:{type:"choice",choice:"read",confidence:1, '
        'probabilities:{read:1,uncertain:0}}},usage:{input_tokens:1,output_tokens:1}}))\n'
        '  });\n'
        '} else if (process.env.JEV_RUNTIME_MODE !== "off") throw Error("mode");\n'
        'for (const key of ["NODE_EFFECT_PATH","NODE_READY_PATH","NODE_INTEGRATION_PATH"]) '
        'if (!process.env[key]) throw Error("missing path");\n'
        'globalThis.__jev_probe_effect = (action,item) => '
        'fs.writeFileSync(process.env.NODE_EFFECT_PATH, action+":"+item+"\\n", {flag:"wx"});\n'
        'async function main() {\n'
        '  const result = await seam({task_id:"task",invocation_id:"normal",'
        'item:"alpha",permit:true});\n'
        '  if (result !== "read:alpha") throw Error("seam result");\n'
        '  fs.writeFileSync(process.env.NODE_READY_PATH,"ready\\n",{flag:"wx"});\n'
        '  fs.writeFileSync(process.env.NODE_INTEGRATION_PATH,"integration\\n",{flag:"wx"});\n'
        '}\nmain().catch(() => {process.exitCode = 1;});\n', encoding='utf-8')
    request['entrypoint_sha256'] = file_hash(entry)
    request['reviewed_package_source_sha256'] = digest(template_js_catalog._source_tree(source))
    rendered = tmp_path / (fmt + '-render')
    materialize_template(source, request, rendered, tooling_dir=tooling)
    bundle = tmp_path / (fmt + '-bundle')
    plan = plan_js(source, request['implementation_spec'], bundle, tooling_dir=tooling)
    baseline = verify_js(source, bundle, 'baseline', cases, tooling_dir=tooling,
                         approve_execution=True)
    assert baseline['status'] == 'passed'
    apply_js(source, bundle, plan['bundle_sha256'],
             baseline_sha256=baseline['receipt_sha256'], tooling_dir=tooling)
    modified = verify_js(source, bundle, 'modified', cases, tooling_dir=tooling,
                         baseline_sha256=baseline['receipt_sha256'], approve_execution=True)
    assert modified['status'] == 'passed'
    assert status_js(source, bundle, tooling_dir=tooling,
                     trusted_modified_sha256=modified['receipt_sha256'])['status'] == 'verified'
    parent = tmp_path / (fmt + '-package')
    parent.mkdir(mode=0o700)
    environment_parent = tmp_path / (fmt + '-generations')
    environment_parent.mkdir(mode=0o700)
    package_request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
        'host_root': str(source), 'render_directory': str(rendered),
        'implementation_bundle': str(bundle),
        'trusted_modified_sha256': modified['receipt_sha256'],
        'node': str(node), 'node_sha256': file_hash(node),
        'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
        'npm_tree_sha256': digest(installer._tree(npm.parent.parent)),
        'tooling_directory': str(tooling), 'offline_cache': str(tmp_path / 'cache'),
        'package_directory': str(parent / 'package'),
        'environment_parent': str(environment_parent)}
    package_plan = installer.plan_node_package(package_request)
    package_receipt = installer.build_node_package(package_plan,
        approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_node_install(package_plan, package_receipt,
        trusted_package_receipt_sha256=package_receipt['receipt_sha256'])
    receipt = installer.install_node_package(install_plan,
        approved_plan_sha256=install_plan['plan_sha256'])
    return {'install_plan': install_plan, 'installed': receipt}


@pytest.mark.parametrize('fmt', ['commonjs', 'esm', 'typescript'])
def test_installed_connected_shadow_cli_and_normal_command(tmp_path, fmt):
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
    host = (_installed(tmp_path, 'connected-cjs', '1.0.0', 'alpha', tooling, node, npm,
                       connected_model=True) if fmt == 'commonjs' else
            _installed_module(tmp_path, fmt, tooling, node, npm))
    receipt = host['installed']
    assert receipt['mode'] == 'off' and receipt['runtime_activation_authorized'] is False
    wheel_dir = tmp_path / 'wheel'
    wheel_dir.mkdir(mode=0o700)
    built = subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-build-isolation',
        '--no-deps', '-w', str(wheel_dir), str(PROJECT)], cwd=tmp_path,
        capture_output=True, text=True, timeout=120)
    assert built.returncode == 0, built.stderr[-1000:]
    wheels = list(wheel_dir.glob('jev_integration_evaluator-*.whl'))
    assert len(wheels) == 1
    evaluator = tmp_path / 'evaluator-venv'
    venv.EnvBuilder(with_pip=False, system_site_packages=False).create(evaluator)
    python = evaluator / 'bin/python'
    installed = subprocess.run([sys.executable, '-m', 'pip', '--python', str(python),
        'install', '--no-index', '--find-links', wheelhouse, str(wheels[0])],
        cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert installed.returncode == 0, installed.stderr[-1000:]
    environment = {'PATH': str(node.parent) + ':/usr/bin:/bin', 'PYTHONNOUSERSITE': '1'}

    def invoke(*args, ok=True):
        result = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
            *map(str, args)], cwd=tmp_path, env=environment,
            capture_output=True, text=True, timeout=120)
        if not ok:
            assert result.returncode != 0
            return result
        assert result.returncode == 0, result.stderr[-1000:]
        return json.loads(result.stdout)

    ledger_parent = tmp_path / 'ledger'
    ledger_parent.mkdir(mode=0o700)
    synthetic_key = 'offline-protocol-fixture'
    env_digest = hashlib.sha256(synthetic_key.encode()).hexdigest()
    request = {'schema_version': '1.0', 'kind': 'node-connected-request-v1',
        'install_plan': host['install_plan'],
        'trusted_install_receipt_sha256': receipt['receipt_sha256'],
        'mode': 'shadow', 'endpoint': 'https://api.typesafe.ai/v1/systemone',
        'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
        'environment_digest': env_digest, 'budget_limits': {'max_calls': 2, 'max_cost': 2},
        'ledger_path': str(ledger_parent / 'runtime.sqlite'),
        'egress_grant': None, 'activation': None}
    first_request = tmp_path / 'connected-request-core.json'
    first_request.write_text(json.dumps(request), encoding='utf-8')
    core_file = tmp_path / 'connected-core.json'
    core_result = invoke('template', 'node-connected-core', '--request', first_request,
        '--out', core_file)
    core = read_json(core_file)
    assert core_result['core_sha256'] == digest(core)
    assert inspect_connected_core(request)[0] == core
    grant = {'core_sha256': digest(core), 'mode': 'shadow',
        'endpoint': request['endpoint'], 'credential_ref': request['credential_ref'],
        'model': request['model'], 'environment_digest': env_digest,
        'issued_at': '2026-09-28T00:00:00Z', 'expires_at': '2026-10-01T00:00:00Z'}
    request['egress_grant'] = grant
    request_file = tmp_path / 'connected-request.json'
    request_file.write_text(json.dumps(request), encoding='utf-8')
    descriptor_file = tmp_path / 'connected-descriptor.json'
    planned = invoke('template', 'node-connected-plan', '--request', request_file,
        '--out', descriptor_file)
    descriptor = read_json(descriptor_file)
    assert planned['descriptor_sha256'] == descriptor['descriptor_sha256']
    assert invoke('template', 'node-connected-status', '--request', request_file,
        '--descriptor', descriptor_file,
        '--trusted-descriptor-sha256', descriptor['descriptor_sha256'])['status'] == 'bound_unlaunched'
    invoke('template', 'node-connected-status', '--request', request_file,
        '--descriptor', descriptor_file, '--trusted-descriptor-sha256', '0' * 64, ok=False)
    observation, launch_env, expected = _observations(tmp_path / 'effects', '1.0.0', 'alpha')
    assert observation['kind'] == 'template-delivery-observation-v1'
    observation_file = tmp_path / 'connected-observation.json'
    observation_file.write_text(json.dumps(observation), encoding='utf-8')
    launch_env_file = tmp_path / 'connected-launch-environment.json'
    launch_env_file.write_text(json.dumps(launch_env), encoding='utf-8')
    command_env = {**environment, **launch_env, 'JEV_RUNTIME_MODE': 'shadow',
        'TYPESAFE_API_KEY': synthetic_key,
        'JEV_CONNECTED_DESCRIPTOR': str(descriptor_file),
        'JEV_TRUSTED_EGRESS_GRANT_SHA256': digest(grant)}
    session = tmp_path / 'connected-session'
    created = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
        'template', 'node-connected-session-create', '--session', str(session),
        '--request', str(request_file), '--descriptor', str(descriptor_file),
        '--observation', str(observation_file),
        '--launch-environment', str(launch_env_file),
        '--trusted-descriptor-sha256', descriptor['descriptor_sha256']],
        cwd=tmp_path, env=command_env, capture_output=True, text=True, timeout=35)
    assert created.returncode == 0, created.stderr[-1000:]
    created_status = json.loads(created.stdout)
    assert created_status['stage'] == 'created'
    scope = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
        'reference': 'offline-connected-fixture', 'run_id': created_status['run_id'],
        'plan_sha256': descriptor['descriptor_sha256'],
        'trusted_session_head': created_status['session_head_sha256'],
        'expires_at': '2026-10-01T00:00:00Z', 'revoked': False,
        'grants': {'launch': True, 'stop': True, 'disable': True,
                   'rollback': False, 'upgrade': False}}
    scope['scope_sha256'] = digest(scope)
    scope_path = tmp_path / 'connected-scope.json'
    scope_path.write_text(json.dumps(scope), encoding='utf-8')
    launch_command = [str(evaluator / 'bin/jev-integration-evaluator'),
        'template', 'node-connected-session-launch']
    wrong_scope = subprocess.run([*launch_command, '--session', str(session),
        '--scope', str(scope_path), '--approve-scope-sha256', '0' * 64],
        cwd=tmp_path, env=command_env, capture_output=True, text=True, timeout=35)
    assert wrong_scope.returncode != 0
    assert not Path(launch_env['NODE_EFFECT_PATH']).exists()
    bad_session = tmp_path / 'bad-grant-session'
    bad_created = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
        'template', 'node-connected-session-create', '--session', str(bad_session),
        '--request', str(request_file), '--descriptor', str(descriptor_file),
        '--observation', str(observation_file),
        '--launch-environment', str(launch_env_file),
        '--trusted-descriptor-sha256', descriptor['descriptor_sha256']],
        cwd=tmp_path, env=command_env, capture_output=True, text=True, timeout=35)
    assert bad_created.returncode == 0, bad_created.stderr[-1000:]
    bad_status = json.loads(bad_created.stdout)
    bad_scope = {**scope, 'run_id': bad_status['run_id'],
                 'trusted_session_head': bad_status['session_head_sha256']}
    bad_scope['scope_sha256'] = digest({k: v for k, v in bad_scope.items()
                                         if k != 'scope_sha256'})
    bad_scope_path = tmp_path / 'bad-scope.json'
    bad_scope_path.write_text(json.dumps(bad_scope), encoding='utf-8')
    bad_started = subprocess.run([*launch_command, '--session', str(bad_session),
        '--scope', str(bad_scope_path), '--approve-scope-sha256', bad_scope['scope_sha256']],
        cwd=tmp_path, env={**command_env, 'JEV_TRUSTED_EGRESS_GRANT_SHA256': '0' * 64},
        capture_output=True, text=True, timeout=35)
    assert bad_started.returncode == 0, bad_started.stderr[-1000:]
    _wait_session_child_exit(bad_session)
    assert not Path(launch_env['NODE_EFFECT_PATH']).exists()
    started = subprocess.run([*launch_command, '--session', str(session),
        '--scope', str(scope_path), '--approve-scope-sha256', scope['scope_sha256']],
        cwd=tmp_path, env=command_env, capture_output=True, text=True, timeout=35)
    assert started.returncode == 0, started.stderr[-1000:]
    started_status = json.loads(started.stdout)
    assert started_status['stage'] == 'running' and started_status['attempts']['launch'] == 1
    for _ in range(100):
        if all(Path(row['path']).exists() for row in observation['checks']):
            break
        time.sleep(.05)
    assert Path(launch_env['NODE_EFFECT_PATH']).read_bytes() == expected == b'read:alpha\n'
    assert all(file_hash(Path(row['path'])) == row['expected_sha256']
               for row in observation['checks'])
    assert not (tmp_path / 'effects/provider-response.json').exists()
    observed = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
        'template', 'node-connected-session-observe', '--session', str(session),
        '--trusted-session-head', started_status['session_head_sha256']],
        cwd=tmp_path, env=command_env, capture_output=True, text=True, timeout=35)
    assert observed.returncode == 0, observed.stderr[-1000:]
    observed_status = json.loads(observed.stdout)
    assert observed_status['attempts']['launch'] == 1
    assert observed_status['exec_verified'] is True
    assert all(observed_status['observations'][row['role']] for row in observation['checks'])
    assert all(observed_status['observation_readbacks'][row['role']] == row['expected_sha256']
               for row in observation['checks'])
    _wait_session_child_exit(session)
    stop_scope = {**scope, 'trusted_session_head': observed_status['session_head_sha256']}
    stop_scope['scope_sha256'] = digest({k: v for k, v in stop_scope.items()
                                          if k != 'scope_sha256'})
    stop_scope_path = tmp_path / 'stop-scope.json'
    stop_scope_path.write_text(json.dumps(stop_scope), encoding='utf-8')
    stopped = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
        'template', 'node-connected-session-stop', '--session', str(session),
        '--scope', str(stop_scope_path),
        '--approve-scope-sha256', stop_scope['scope_sha256']],
        cwd=tmp_path, env=command_env, capture_output=True, text=True, timeout=35)
    assert stopped.returncode == 0, stopped.stderr[-1000:]
    stopped_status = json.loads(stopped.stdout)
    assert stopped_status['stage'] == 'stopped'
    effect_path = Path(launch_env['NODE_EFFECT_PATH'])
    effect_path.write_bytes(expected + b'tampered\n')
    changed = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
        'template', 'node-connected-session-observe', '--session', str(session),
        '--trusted-session-head', stopped_status['session_head_sha256']],
        cwd=tmp_path, env=command_env, capture_output=True, text=True, timeout=35)
    assert changed.returncode == 0, changed.stderr[-1000:]
    changed_status = json.loads(changed.stdout)
    assert changed_status['observations']['entrypoint_reached'] is False
    assert changed_status['observation_readbacks']['entrypoint_reached'] == file_hash(effect_path)
    effect_path.write_bytes(expected)
    if fmt == 'commonjs':
        # The first process released its exclusive ledger before the next owner.
        revoked_observation, revoked_paths, _ = _observations(
            tmp_path / 'effects-revoked', '1.0.0', 'alpha')
        assert revoked_observation['kind'] == 'template-delivery-observation-v1'
        revoked_observation_file = tmp_path / 'revoked-observation.json'
        revoked_observation_file.write_text(json.dumps(revoked_observation), encoding='utf-8')
        revoked_paths_file = tmp_path / 'revoked-launch-environment.json'
        revoked_paths_file.write_text(json.dumps(revoked_paths), encoding='utf-8')
        trusted_file = tmp_path / 'trusted-grant.sha256'
        trusted_file.write_text(digest(grant), encoding='ascii')
        os.chmod(trusted_file, 0o600)
        marker = tmp_path / 'fake-transport-started'
        revoke_env = {**command_env, **revoked_paths,
            'JEV_TRUSTED_GRANT_FILE': str(trusted_file),
            'JEV_FAKE_TRANSPORT_MARKER': str(marker),
            'JEV_FAKE_TRANSPORT_DELAY_MS': '500',
            'JEV_INVOCATION_ID': 'revoked-during-response'}
        revoke_session = tmp_path / 'revoke-session'
        revoke_created = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
            'template', 'node-connected-session-create', '--session', str(revoke_session),
            '--request', str(request_file), '--descriptor', str(descriptor_file),
            '--observation', str(revoked_observation_file),
            '--launch-environment', str(revoked_paths_file),
            '--trusted-descriptor-sha256', descriptor['descriptor_sha256']],
            cwd=tmp_path, env=revoke_env, capture_output=True, text=True, timeout=35)
        assert revoke_created.returncode == 0, revoke_created.stderr[-1000:]
        revoke_status = json.loads(revoke_created.stdout)
        revoke_scope = {**scope, 'run_id': revoke_status['run_id'],
            'trusted_session_head': revoke_status['session_head_sha256']}
        revoke_scope['scope_sha256'] = digest({k: v for k, v in revoke_scope.items()
                                                if k != 'scope_sha256'})
        revoke_scope_path = tmp_path / 'revoke-scope.json'
        revoke_scope_path.write_text(json.dumps(revoke_scope), encoding='utf-8')
        revoke_started = subprocess.run([*launch_command, '--session', str(revoke_session),
            '--scope', str(revoke_scope_path),
            '--approve-scope-sha256', revoke_scope['scope_sha256']],
            cwd=tmp_path, env=revoke_env, capture_output=True, text=True, timeout=35)
        assert revoke_started.returncode == 0, revoke_started.stderr[-1000:]
        for _ in range(400):
            if marker.exists():
                break
            time.sleep(.05)
        assert marker.exists(), 'synthetic provider boundary was not reached'
        trusted_file.write_text('0' * 64, encoding='ascii')
        state = {}
        for _ in range(400):
            try:
                with sqlite3.connect(request['ledger_path'], timeout=.1) as database:
                    state = json.loads(database.execute('SELECT payload FROM state').fetchone()[0])
                if state['suspended']:
                    break
            except sqlite3.OperationalError:
                pass
            time.sleep(.05)
        assert Path(revoked_paths['NODE_EFFECT_PATH']).read_bytes() == b'read:alpha\n'
        assert state['suspended'] is True
        trusted_file.write_text(digest(grant), encoding='ascii')
        replay_observation, replay_paths, _ = _observations(
            tmp_path / 'effects-replay', '1.0.0', 'alpha')
        assert replay_observation['kind'] == 'template-delivery-observation-v1'
        replay_observation_file = tmp_path / 'replay-observation.json'
        replay_observation_file.write_text(json.dumps(replay_observation), encoding='utf-8')
        replay_paths_file = tmp_path / 'replay-launch-environment.json'
        replay_paths_file.write_text(json.dumps(replay_paths), encoding='utf-8')
        replay_session = tmp_path / 'replay-session'
        replay_env = {**command_env, **replay_paths,
                      'JEV_INVOCATION_ID': 'after-revocation'}
        replay_created = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
            'template', 'node-connected-session-create', '--session', str(replay_session),
            '--request', str(request_file), '--descriptor', str(descriptor_file),
            '--observation', str(replay_observation_file),
            '--launch-environment', str(replay_paths_file),
            '--trusted-descriptor-sha256', descriptor['descriptor_sha256']],
            cwd=tmp_path, env=replay_env, capture_output=True, text=True, timeout=35)
        assert replay_created.returncode == 0, replay_created.stderr[-1000:]
        replay_status = json.loads(replay_created.stdout)
        replay_scope = {**scope, 'run_id': replay_status['run_id'],
                        'trusted_session_head': replay_status['session_head_sha256']}
        replay_scope['scope_sha256'] = digest({k: v for k, v in replay_scope.items()
                                                if k != 'scope_sha256'})
        replay_scope_path = tmp_path / 'replay-scope.json'
        replay_scope_path.write_text(json.dumps(replay_scope), encoding='utf-8')
        replay_started = subprocess.run([*launch_command, '--session', str(replay_session),
            '--scope', str(replay_scope_path),
            '--approve-scope-sha256', replay_scope['scope_sha256']],
            cwd=tmp_path, env=replay_env, capture_output=True, text=True, timeout=35)
        assert replay_started.returncode == 0, replay_started.stderr[-1000:]
        _wait_session_child_exit(replay_session)
        assert not Path(replay_paths['NODE_EFFECT_PATH']).exists()
    runtime_file = Path(receipt['working_directory']) / 'jev_runtime.cjs'
    runtime_file.write_bytes(runtime_file.read_bytes() + b'\n// drift\n')
    drift = subprocess.run([str(evaluator / 'bin/jev-integration-evaluator'),
        'template', 'node-connected-session-observe', '--session', str(session),
        '--trusted-session-head', changed_status['session_head_sha256']],
        cwd=tmp_path, env=command_env, capture_output=True, text=True, timeout=35)
    assert drift.returncode != 0
    assert Path(launch_env['NODE_EFFECT_PATH']).read_bytes() == expected
