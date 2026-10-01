"""Installed connected-shadow fault matrix for CommonJS, ESM and TypeScript hosts.

Every outcome is read back from files the evaluator does not write: the host's
append-only effect file, the host audit sink, the fake transport's request
log, the durable SQLite ledger and the session journal. The transport is an
offline synthetic protocol fixture; nothing here is provider evidence.
"""
from __future__ import annotations

from contextlib import closing
from datetime import timedelta
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

from jev_integration_evaluator.io import digest, file_hash, read_json
from jev_integration_evaluator.integrations.js_backend import trusted_js_tool_identity
from jev_integration_evaluator import template_node_installation as installer
from test_node_template_connected import (
    PROJECT, _installed_module, _utc, _wait_session_child_exit)
from test_node_template_installation import native_tools
from test_node_template_installed_commonjs import _installed
from test_node_template_installed_upgrade import (
    NODE_SHA256, NPM_CLI_SHA256, NPM_TREE_SHA256, TRUSTED_TYPESCRIPT_TREE_SHA256,
    _observations,
)


TIMEOUT_MS = 1000
LATE_DELAY_MS = 1300
FAULTS = ('none', 'late', 'malformed', 'mistyped', 'transport_reject', 'hold',
          'executor_reject')

_HEADERS = {
    'commonjs': ('const fs = require("node:fs");\n'
                 'const crypto = require("node:crypto");\n'
                 'const seam = require("./host.cjs");\n'
                 'const adapter = require("./jev_adapter.cjs");\n'),
    'module': ('import fs from "node:fs";\n'
               'import crypto from "node:crypto";\n'
               'import adapter from "./jev_adapter.cjs";\n'
               'import {seam} from "./host.mjs";\n'),
}

# One finite fault per process. JEV_FAKE_TRANSPORT_MARKER is a path prefix:
# the bare path logs provider requests/responses, ".audit" the host audit
# sink and ".outcome" what the normal command saw. The effect file is opened
# in append mode so a duplicate effect is counted instead of hidden.
_BODY = '''const fault = process.env.JEV_FIXTURE_FAULT || "none";
if (!%s.includes(fault)) throw Error("fault");
const log = process.env.JEV_FAKE_TRANSPORT_MARKER;
const note = (suffix, line) => { if (log) fs.appendFileSync(log + suffix, line + "\\n"); };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const trusted = () => process.env.JEV_TRUSTED_GRANT_FILE ?
  fs.readFileSync(process.env.JEV_TRUSTED_GRANT_FILE, "utf8").trim() :
  process.env.JEV_TRUSTED_EGRESS_GRANT_SHA256;
const answer = probabilities => Buffer.from(JSON.stringify({model: "jev-1.13.0",
  answers: {choice: {type: "choice", choice: "read", confidence: 1, probabilities}},
  usage: {input_tokens: 1, output_tokens: 1}}));
if (process.env.JEV_RUNTIME_MODE === "shadow") {
  const descriptor = JSON.parse(fs.readFileSync(process.env.JEV_CONNECTED_DESCRIPTOR));
  adapter.initializeConnected(descriptor, {
    audit: {append(event) { note(".audit", event.kind); }},
    verifyAuthority: (kind, sha) => kind === "egress_grant" && sha === trusted(),
    currentEnvironmentDigest: () => crypto.createHash("sha256")
      .update(process.env.TYPESAFE_API_KEY).digest("hex"),
    transport: async () => {
      note("", "request");
      if (fault === "transport_reject") {
        await sleep(1);
        throw Error("synthetic transport rejection");
      }
      if (fault === "hold") await sleep(30000);
      if (fault === "late") await sleep(Number(process.env.JEV_FAKE_TRANSPORT_DELAY_MS));
      note("", "responded");
      if (fault === "malformed")
        return Buffer.from('{"model":"jev-1.13.0","model":"jev-1.13.0"');
      if (fault === "mistyped") return answer({read: 0.5, uncertain: 0.2});
      return answer({read: 1, uncertain: 0});
    }
  });
} else if (process.env.JEV_RUNTIME_MODE !== "off") throw Error("mode");
for (const key of ["NODE_EFFECT_PATH", "NODE_READY_PATH", "NODE_INTEGRATION_PATH"])
  if (!process.env[key]) throw Error("missing path");
globalThis.__jev_probe_effect = (action, item) => {
  fs.appendFileSync(process.env.NODE_EFFECT_PATH, action + ":" + item + "\\n");
  if (fault === "executor_reject") throw Error("synthetic_executor_rejection");
};
async function main() {
  const invocation = process.env.JEV_INVOCATION_ID || "normal";
  const result = await seam({task_id: "task", invocation_id: invocation,
    item: "alpha", permit: true});
  if (result !== "read:alpha") throw Error("seam result");
  fs.writeFileSync(process.env.NODE_READY_PATH, "ready\\n", {flag: "wx"});
  fs.writeFileSync(process.env.NODE_INTEGRATION_PATH, "integration\\n", {flag: "wx"});
  if (process.env.JEV_TRUSTED_GRANT_FILE) {
    for (let i = 0; i < 400 &&
         trusted() === process.env.JEV_TRUSTED_EGRESS_GRANT_SHA256; i++) await sleep(25);
    try {
      await seam({task_id: "task", invocation_id: invocation + "-after-revocation",
        item: "alpha", permit: true});
      note(".outcome", "second:returned");
    } catch (error) { note(".outcome", "second:" + (error.code || error.message)); }
  }
}
main().catch(error => {
  note(".outcome", "main:" + (error.code || error.message));
  process.exitCode = 1;
});
''' % json.dumps(list(FAULTS))


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding='utf-8').splitlines() if path.exists() else []


def _ledger(path: str) -> dict:
    """Read the durable state after its exclusive owner process has exited."""
    for _ in range(200):
        try:
            # Close explicitly: an open reader would block the next exclusive owner.
            with closing(sqlite3.connect(path, timeout=.1)) as database:
                rows = database.execute('SELECT payload FROM state WHERE id=1').fetchall()
            assert len(rows) == 1
            return json.loads(rows[0][0])
        except sqlite3.OperationalError:
            time.sleep(.05)
    raise AssertionError('durable ledger stayed locked after its owner exited')


def _journal(session: Path) -> list[dict]:
    return [json.loads(raw) for raw in
            (session / 'events.jsonl').read_text(encoding='utf-8').splitlines()]


@pytest.mark.parametrize('fmt', ['commonjs', 'esm', 'typescript'])
def test_installed_connected_fault_matrix(tmp_path, fmt):
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
    if fmt == 'commonjs':
        host = _installed(tmp_path, 'fault-cjs', '1.0.0', 'alpha', tooling, node, npm,
                          connected_model=True, entry_text=_HEADERS['commonjs'] + _BODY)
    else:
        host = _installed_module(tmp_path, fmt, tooling, node, npm,
                                 entry_text=_HEADERS['module'] + _BODY,
                                 timeout_ms=TIMEOUT_MS)
    receipt = host['installed']
    assert receipt['mode'] == 'off' and receipt['runtime_activation_authorized'] is False
    assert Path(receipt['command'][1]).read_text(encoding='utf-8').endswith(_BODY)
    bundle = Path(host['install_plan']['package_plan']['request']['implementation_bundle'])
    reviewed_spec = read_json(bundle / 'spec.json')
    candidate = reviewed_spec['candidate_id']
    assert reviewed_spec['runtime']['runtime']['timeout_ms'] == TIMEOUT_MS < LATE_DELAY_MS
    assert reviewed_spec['runtime']['runtime']['cost_upper_bound'] == 1

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
    installed = subprocess.run([sys.executable, '-m', 'pip', '--python',
        str(evaluator / 'bin/python'), 'install', '--no-index', '--find-links',
        wheelhouse, str(wheels[0])], cwd=tmp_path, capture_output=True, text=True,
        timeout=120)
    assert installed.returncode == 0, installed.stderr[-1000:]
    cli = str(evaluator / 'bin/jev-integration-evaluator')
    environment = {'PATH': str(node.parent) + ':/usr/bin:/bin', 'PYTHONNOUSERSITE': '1'}
    synthetic_key = 'offline-protocol-fixture'
    env_digest = hashlib.sha256(synthetic_key.encode()).hexdigest()

    def run(*args, env=environment):
        return subprocess.run([cli, *map(str, args)], cwd=tmp_path, env=env,
                              capture_output=True, text=True, timeout=120)

    def invoke(*args, env=environment):
        result = run(*args, env=env)
        assert result.returncode == 0, result.stderr[-1000:]
        return json.loads(result.stdout)

    def bind(name: str) -> dict:
        """One reviewed descriptor and one private durable ledger per fault."""
        parent = tmp_path / ('ledger-' + name)
        parent.mkdir(mode=0o700)
        request = {'schema_version': '1.0', 'kind': 'node-connected-request-v1',
            'install_plan': host['install_plan'],
            'trusted_install_receipt_sha256': receipt['receipt_sha256'],
            'mode': 'shadow', 'endpoint': 'https://api.typesafe.ai/v1/systemone',
            'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
            'environment_digest': env_digest,
            'budget_limits': {'max_calls': 2, 'max_cost': 2},
            'ledger_path': str(parent / 'runtime.sqlite'),
            'egress_grant': None, 'activation': None}
        core_request = parent / 'request-core.json'
        core_request.write_text(json.dumps(request), encoding='utf-8')
        core = invoke('template', 'node-connected-core', '--request', core_request,
                      '--out', parent / 'core.json')
        grant = {'core_sha256': core['core_sha256'], 'mode': 'shadow',
            'endpoint': request['endpoint'], 'credential_ref': request['credential_ref'],
            'model': request['model'], 'environment_digest': env_digest,
            'issued_at': _utc(timedelta(days=-1)), 'expires_at': _utc(timedelta(days=1))}
        request['egress_grant'] = grant
        request_file = parent / 'request.json'
        request_file.write_text(json.dumps(request), encoding='utf-8')
        descriptor_file = parent / 'descriptor.json'
        planned = invoke('template', 'node-connected-plan', '--request', request_file,
                         '--out', descriptor_file)
        descriptor = read_json(descriptor_file)
        assert planned['descriptor_sha256'] == descriptor['descriptor_sha256']
        assert not Path(request['ledger_path']).exists()
        return {'request_file': request_file, 'descriptor_file': descriptor_file,
                'descriptor': descriptor, 'grant': grant,
                'ledger': request['ledger_path']}

    def scope_for(binding: dict, status: dict) -> dict:
        scope = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
            'reference': 'offline-connected-fault-fixture', 'run_id': status['run_id'],
            'plan_sha256': binding['descriptor']['descriptor_sha256'],
            'trusted_session_head': status['session_head_sha256'],
            'expires_at': _utc(timedelta(days=1)), 'revoked': False,
            'grants': {'launch': True, 'stop': True, 'disable': False,
                       'rollback': False, 'upgrade': False}}
        scope['scope_sha256'] = digest(scope)
        return scope

    def create(binding: dict, name: str, *, invocation: str, fault: str = 'none',
               extra: dict | None = None) -> dict:
        observation, paths, expected = _observations(
            tmp_path / ('effects-' + name), '1.0.0', 'alpha')
        assert expected == b'read:alpha\n'
        work = tmp_path / ('run-' + name)
        work.mkdir(mode=0o700)
        (work / 'observation.json').write_text(json.dumps(observation), encoding='utf-8')
        (work / 'launch-environment.json').write_text(json.dumps(paths), encoding='utf-8')
        env = {**environment, **paths, 'JEV_RUNTIME_MODE': 'shadow',
            'TYPESAFE_API_KEY': synthetic_key,
            'JEV_TRUSTED_EGRESS_GRANT_SHA256': digest(binding['grant']),
            'JEV_FAKE_TRANSPORT_MARKER': str(work / 'transport.log'),
            'JEV_FIXTURE_FAULT': fault, 'JEV_INVOCATION_ID': invocation,
            **(extra or {})}
        session = tmp_path / ('session-' + name)
        status = invoke('template', 'node-connected-session-create', '--session', session,
            '--request', binding['request_file'], '--descriptor', binding['descriptor_file'],
            '--observation', work / 'observation.json',
            '--launch-environment', work / 'launch-environment.json',
            '--trusted-descriptor-sha256', binding['descriptor']['descriptor_sha256'], env=env)
        assert status['stage'] == 'created'
        scope_path = work / 'launch-scope.json'
        scope_path.write_text(json.dumps(scope_for(binding, status)), encoding='utf-8')
        return {'session': session, 'env': env, 'status': status, 'scope': scope_path,
                'observation': observation, 'work': work,
                'effect': Path(paths['NODE_EFFECT_PATH']),
                'ready': Path(paths['NODE_READY_PATH']),
                'integration': Path(paths['NODE_INTEGRATION_PATH']),
                'requests': work / 'transport.log', 'audit': work / 'transport.log.audit',
                'outcome': work / 'transport.log.outcome'}

    def launch(case: dict):
        return run('template', 'node-connected-session-launch', '--session', case['session'],
                   '--scope', case['scope'],
                   '--approve-scope-sha256', read_json(case['scope'])['scope_sha256'],
                   env=case['env'])

    def start(binding: dict, name: str, **options) -> dict:
        case = create(binding, name, **options)
        started = launch(case)
        assert started.returncode == 0, started.stderr[-1000:]
        case['started'] = json.loads(started.stdout)
        assert case['started']['attempts']['launch'] == 1
        return case

    def finish(case: dict) -> dict:
        _wait_session_child_exit(case['session'])
        return case

    def observe(case: dict) -> dict:
        return invoke('template', 'node-connected-session-observe', '--session',
            case['session'], '--trusted-session-head',
            case['started']['session_head_sha256'], env=case['env'])

    def refused_at_startup(binding: dict, name: str, invocation: str) -> None:
        """A later owner on an unresolved or suspended ledger starts nothing."""
        before = _ledger(binding['ledger'])
        replay = finish(start(binding, name, invocation=invocation))
        assert not replay['effect'].exists() and not replay['ready'].exists()
        assert _lines(replay['requests']) == [] and _lines(replay['audit']) == []
        assert _lines(replay['outcome']) == []
        assert _ledger(binding['ledger']) == before

    def invocation_key(invocation: str) -> str:
        return digest(['task', invocation, candidate])

    # (e) Reviewed configuration drift after install is refused at launch,
    # before the journal records a launch, a child exists or a ledger is made.
    clean = bind('clean')
    first = create(clean, 'first', invocation='inv-1')
    rendered = Path(host['install_plan']['package_plan']['request']['render_directory'])
    reviewed_request = rendered / 'template-request.json'
    reviewed_bytes = reviewed_request.read_bytes()
    assert any(row['role'] == 'reviewed_configuration' and
               row['path'] == str(reviewed_request) and
               row['sha256'] == hashlib.sha256(reviewed_bytes).hexdigest()
               for row in clean['descriptor']['source_plan']['files'])
    promoted = json.loads(reviewed_bytes)
    assert promoted['configuration'] == {'mode': 'off', 'credential_ref': None}
    promoted['configuration'] = {'mode': 'shadow', 'credential_ref': 'env:TYPESAFE_API_KEY'}
    for drifted in (json.dumps(promoted).encode(), reviewed_bytes + b'\n'):
        reviewed_request.write_bytes(drifted)
        refused = launch(first)
        assert refused.returncode != 0
        assert synthetic_key not in refused.stdout + refused.stderr
        assert [row['event'] for row in _journal(first['session'])] == ['created']
        assert not first['effect'].exists() and not Path(clean['ledger']).exists()
        assert _lines(first['requests']) == []
    reviewed_request.write_bytes(reviewed_bytes)

    # Normal shadow: the unchanged scope still matches the journal head.
    started = launch(first)
    assert started.returncode == 0, started.stderr[-1000:]
    first['started'] = json.loads(started.stdout)
    assert first['started']['stage'] == 'running'
    journal = _journal(first['session'])
    assert [row['event'] for row in journal] == [
        'created', 'launch_pending', 'launched', 'running']
    assert journal[-1]['state']['attempts'] == {'launch': 1, 'stop': 0}
    finish(first)
    assert first['effect'].read_bytes() == b'read:alpha\n'
    observed = observe(first)
    assert observed['exec_verified'] is True and all(observed['observations'].values())
    assert observed['observation_readbacks'] == {
        row['role']: row['expected_sha256'] for row in first['observation']['checks']}
    assert _lines(first['requests']) == ['request', 'responded']
    assert _lines(first['audit']) == ['assessment_intent', 'baseline_intent', 'shadow_result']
    assert _lines(first['outcome']) == []
    state = _ledger(clean['ledger'])
    assert (state['calls'], state['cost'], state['pending'], state['suspended']) == (
        1, 1, [], False)
    assert state['invocations'] == [invocation_key('inv-1')]
    assert state['limits']['max_calls'] == 2 and state['limits']['max_cost'] == 2

    # Duplicate effect: a second process replaying the settled invocation
    # identity is refused before any provider request or effect.
    duplicate = finish(start(clean, 'duplicate', invocation='inv-1'))
    assert _lines(duplicate['outcome']) == ['main:effect_replay_denied']
    assert not duplicate['effect'].exists() and not duplicate['ready'].exists()
    assert _lines(duplicate['requests']) == [] and _lines(duplicate['audit']) == []
    assert _ledger(clean['ledger']) == state
    assert first['effect'].read_bytes() == b'read:alpha\n'

    # (c) Grant revoked mid-run: the completed baseline stays, the next seam
    # call is refused without a provider request, and the ledger suspends.
    trusted_file = tmp_path / 'trusted-grant.sha256'
    trusted_file.write_text(digest(clean['grant']), encoding='ascii')
    os.chmod(trusted_file, 0o600)
    revoked = start(clean, 'revoked', invocation='inv-2',
                    extra={'JEV_TRUSTED_GRANT_FILE': str(trusted_file)})
    assert revoked['started']['stage'] == 'running'
    for _ in range(400):
        if revoked['integration'].exists():
            break
        time.sleep(.05)
    assert revoked['integration'].read_bytes() == b'integration\n'
    assert _lines(revoked['outcome']) == []
    trusted_file.write_text('0' * 64, encoding='ascii')
    finish(revoked)
    assert _lines(revoked['outcome']) == ['second:connected_authority_expired_or_revoked']
    assert revoked['effect'].read_bytes() == b'read:alpha\n'
    assert _lines(revoked['requests']) == ['request', 'responded']
    assert _lines(revoked['audit']) == ['assessment_intent', 'baseline_intent', 'shadow_result']
    state = _ledger(clean['ledger'])
    assert (state['calls'], state['cost'], state['pending'], state['suspended']) == (
        2, 2, [], True)
    assert state['invocations'] == [invocation_key('inv-1'), invocation_key('inv-2')]
    trusted_file.write_text(digest(clean['grant']), encoding='ascii')
    refused_at_startup(clean, 'after-revocation', 'inv-3')

    # (b) Timeout, then a well-formed response that arrives late: discarded,
    # the charge and its unresolved reservation are retained.
    late_binding = bind('late')
    late = finish(start(late_binding, 'late', invocation='late-1', fault='late',
                        extra={'JEV_FAKE_TRANSPORT_DELAY_MS': str(LATE_DELAY_MS)}))
    assert late['effect'].read_bytes() == b'read:alpha\n'
    assert all(observe(late)['observations'].values())
    assert _lines(late['requests']) == ['request', 'responded']
    assert _lines(late['audit']) == ['assessment_intent', 'baseline_intent', 'shadow_failed']
    assert _lines(late['outcome']) == []
    state = _ledger(late_binding['ledger'])
    assert (state['calls'], state['cost'], state['suspended']) == (1, 1, False)
    assert state['pending'] == ['provider:' + digest(['task', 1])]
    assert state['invocations'] == [invocation_key('late-1')]
    refused_at_startup(late_binding, 'late-replay', 'late-2')
    assert late['effect'].read_bytes() == b'read:alpha\n'

    # (b) Malformed bytes, a well-formed but invalid typed answer, and
    # (a) an asynchronously rejected provider call: none becomes a result.
    for fault, requests in (('malformed', ['request', 'responded']),
                            ('mistyped', ['request', 'responded']),
                            ('transport_reject', ['request'])):
        binding = bind(fault)
        case = finish(start(binding, fault, invocation=fault + '-1', fault=fault))
        assert case['effect'].read_bytes() == b'read:alpha\n'
        assert case['ready'].read_bytes() == b'ready\n'
        assert _lines(case['requests']) == requests
        assert _lines(case['audit']) == [
            'assessment_intent', 'baseline_intent', 'shadow_failed']
        assert _lines(case['outcome']) == []
        state = _ledger(binding['ledger'])
        assert (state['calls'], state['cost'], state['suspended']) == (1, 1, False)
        assert state['pending'] == ['provider:' + digest(['task', 1])]
        assert state['invocations'] == [invocation_key(fault + '-1')]

    # (a) The host executor rejects asynchronously after its effect: the
    # normal command fails, nothing retries, and the unsettled invocation
    # blocks a later process from replaying the effect.
    rejected_binding = bind('executor')
    rejected = finish(start(rejected_binding, 'executor', invocation='exec-1',
                            fault='executor_reject'))
    assert rejected['effect'].read_bytes() == b'read:alpha\n'
    assert not rejected['ready'].exists() and not rejected['integration'].exists()
    assert _lines(rejected['outcome']) == ['main:synthetic_executor_rejection']
    assert _lines(rejected['requests']) == ['request', 'responded']
    assert _lines(rejected['audit']) == [
        'assessment_intent', 'baseline_intent', 'shadow_result']
    state = _ledger(rejected_binding['ledger'])
    assert (state['calls'], state['cost'], state['suspended']) == (1, 1, False)
    assert state['pending'] == ['effect:' + invocation_key('exec-1')]
    refused_at_startup(rejected_binding, 'executor-replay', 'exec-1')
    assert rejected['effect'].read_bytes() == b'read:alpha\n'

    # (a) Cancellation by the owning supervisor while the provider call is
    # still open: the stop is journaled, the response never arrives, and the
    # reservation stays charged and unresolved.
    held_binding = bind('hold')
    held = start(held_binding, 'hold', invocation='hold-1', fault='hold')
    assert held['started']['stage'] == 'running'
    for _ in range(400):
        if held['integration'].exists() and _lines(held['requests']) == ['request']:
            break
        time.sleep(.05)
    assert held['integration'].read_bytes() == b'integration\n'
    stop_scope = held['work'] / 'stop-scope.json'
    stop_scope.write_text(json.dumps(scope_for(held_binding, held['started'])),
                          encoding='utf-8')
    stopped = invoke('template', 'node-connected-session-stop', '--session',
        held['session'], '--scope', stop_scope,
        '--approve-scope-sha256', read_json(stop_scope)['scope_sha256'], env=held['env'])
    assert stopped['stage'] == 'stopped' and stopped['process_alive'] is False
    assert stopped['attempts'] == {'launch': 1, 'stop': 1}
    assert [row['event'] for row in _journal(held['session'])][-2:] == [
        'stop_pending', 'stopped']
    assert held['effect'].read_bytes() == b'read:alpha\n'
    assert _lines(held['requests']) == ['request']
    assert _lines(held['audit'])[:2] == ['assessment_intent', 'baseline_intent']
    assert 'shadow_result' not in _lines(held['audit'])
    state = _ledger(held_binding['ledger'])
    assert (state['calls'], state['cost'], state['suspended']) == (1, 1, False)
    assert state['pending'] == ['provider:' + digest(['task', 1])]
    assert state['invocations'] == [invocation_key('hold-1')]
