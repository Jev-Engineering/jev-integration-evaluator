"""Installed source-bound L graph shadow through the normal console and SQLite."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
import sys
from threading import Thread
from threading import Event
import time

import pytest

from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator.template_connected_delivery import (
    ConnectedDeliveryError, connected_session_status, create_connected_session,
    launch_connected_session, plan_connected_delivery, stop_connected_session,
)
from jev_integration_evaluator.integrations.lifecycle import rollback_implementation
from tests.test_connected_installed_binding import _issuer, _issue
from tests.test_template_installation import _metadata
from tests.test_use_case_graph_bind import PROFILE
from tests.test_use_case_graph_bound_installed import _applied, _installed
from tests.test_use_case_graph_installed import _expected


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='L connected installed fixture requires Linux x86-64 CPython 3.13')
LOADER = Path(__file__).parent / 'independent_hosts/graph_connected/connected_authority.py'


def _scope(state: dict, plan: dict, action: str) -> dict:
    scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
             'run_id': state['run_id'], 'plan_sha256': plan['plan_sha256'],
             'public_key_sha256': plan['reference_sha256']['L_AUTH_PUBKEY_FILE'],
             'trusted_session_head': state['session_head_sha256'], 'action': action,
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
    scope['scope_sha256'] = digest(scope)
    validate_contract(scope, 'connected-delivery-scope-v1')
    return scope


def _effects(second_task: str = 'graph-two') -> tuple[bytes, bytes]:
    first = json.loads(_expected())
    first['task_id'] = 'graph-one'
    prior = first['receipt']
    second_receipt = dict(prior, revision_before=1, revision_after=2)
    second = dict(first, task_id=second_task, revision=2,
                  receipt=second_receipt, merges=[prior, second_receipt],
                  audits=[prior, second_receipt])
    encoded = lambda value: (json.dumps(value, sort_keys=True,
                                        separators=(',', ':')) + '\n').encode()
    return encoded(first), encoded(second)


def _observation(folder: Path, *, second_task: str = 'graph-two') -> tuple[dict, bytes, bytes]:
    first, second = _effects(second_task)
    checks = [('ready', folder / 'ready.txt', b'ready\n'),
              ('entrypoint_reached', folder / 'first.json', first),
              ('integration_reachable', folder / 'first.json', first),
              ('outcome_verified', folder / 'second.json', second)]
    return ({'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
             'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                         'expected_sha256': hashlib.sha256(raw).hexdigest()}
                        for role, path, raw in checks]}, first, second)


def _wait(path: Path, expected: bytes, seconds: float = 20) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.is_file() and path.read_bytes() == expected:
            return
        time.sleep(.02)
    raise AssertionError('independent graph effect missing')


def _database(path: Path, first: bytes, second: bytes) -> None:
    initial, final = json.loads(first), json.loads(second)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        assert db.execute('SELECT value FROM revision').fetchall() == [(2,)]
        assert db.execute('SELECT key, name, jurisdiction, registry_id, provenance '
                          'FROM entities ORDER BY key').fetchall() == [
            ('left', 'Acme', 'US', 'one', 'registry-left'),
            ('right', 'Acme', 'US', 'one', 'registry-right')]
        assert [json.loads(row[0]) for row in db.execute(
            'SELECT receipt FROM audit ORDER BY id')] == final['audits']
        assert [json.loads(row[0]) for row in db.execute(
            'SELECT receipt FROM merges ORDER BY id')] == final['merges']
    assert initial['receipt'] == initial['audits'][0] == final['audits'][0]
    assert final['receipt'] == final['audits'][1]
    assert final['receipt']['sources'] == ['registry-left', 'registry-right']


def _ledger(path: Path) -> dict | None:
    database = Path(str(path) + '.sqlite')
    if not database.is_file():
        return None
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1) as db:
        row = db.execute('SELECT payload FROM state WHERE id=1').fetchone()
    return json.loads(row[0]) if row else None


def test_l_source_bound_installed_connected_shadow_graph_sqlite(tmp_path, monkeypatch):
    wheelhouse_name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not wheelhouse_name:
        pytest.skip('exact private offline wheelhouse required')
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    wheels = sorted(wheelhouse.glob('*.whl'))
    assert wheels
    rows = [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels]
    requirements = [{'name': name, 'version': version, 'wheel': path.name,
                     'sha256': file_hash(path)}
                    for path in wheels for name, version in [_metadata(path)]]
    environments = tmp_path / 'environments'
    environments.mkdir(mode=0o700)
    host = _applied(tmp_path, 'connected-l', '1.0.0', LOADER)
    install_plan, receipt = _installed(tmp_path, host, wheelhouse, rows,
                                       requirements, environments, 'connected-package')
    package_plan, package_receipt = install_plan['package_plan'], install_plan['package_receipt']
    report = derive_installed_binding(package_plan, package_receipt, install_plan, receipt,
        trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
        trusted_install_receipt_sha256=receipt['receipt_sha256'])
    assert report['source_file'] == 'graph_host/host_graph_consumer.py'
    assert report['origins']['loader']['wheel_member'] == 'graph_host/connected_authority.py'
    assert all(Path(row['path']).is_file() for row in report['source_plan']['files'])
    adapter_tree = ast.parse(Path(report['origins']['adapter']['path']).read_text())
    adapter_spec = ast.literal_eval(next(node.value for node in adapter_tree.body
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'SPEC' for target in node.targets)))
    dependency = {'files': [{'path': str(Path(report['site']) / 'graph_host' / name),
                             'sha256': file_hash(Path(report['site']) / 'graph_host' / name)}
                            for name in ('requirements.lock', 'runtime.json')]}
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
              'max_total_calls': 2, 'max_total_cost': 2,
              'max_in_flight': 1, 'max_tasks': 2}
    private, public = _issuer(tmp_path)
    calls: list[dict] = []
    response_mode = {'value': 'valid'}
    release_response = Event()

    class SyntheticTypeSafe(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            request = json.loads(raw)
            calls.append({'path': self.path, 'sha256': hashlib.sha256(raw).hexdigest()})
            if response_mode['value'] == 'hold_first':
                release_response.wait(timeout=12)
            answers = {}
            for name, question in request['questions'].items():
                if question['type'] == 'noul':
                    answers[name] = {'type': 'noul', 'noul': 1.0}
                else:
                    labels = list(question['criteria'])
                    choice = 'same' if 'same' in labels else labels[0]
                    answers[name] = {'type': 'choice', 'choice': choice,
                                     'confidence': 1.0,
                                     'probabilities': {label: float(label == choice)
                                                       for label in labels}}
            model = request['model'] if response_mode['value'] == 'valid' else request['model'] + '-wrong'
            result = json.dumps({'model': model, 'answers': answers,
                                 'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(result)))
            self.end_headers()
            self.wfile.write(result)

    cert, cert_key = tmp_path / 'loopback.crt', tmp_path / 'loopback.key'
    generated = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-nodes', '-keyout', str(cert_key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
        '-addext', 'subjectAltName=IP:127.0.0.1', '-days', '1'],
        capture_output=True, timeout=20)
    assert generated.returncode == 0
    cert.chmod(0o600); cert_key.chmod(0o600)
    server = ThreadingHTTPServer(('127.0.0.1', 0), SyntheticTypeSafe)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(str(cert), str(cert_key))
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    active: list[tuple[Path, dict]] = []
    try:
        endpoint = f'https://127.0.0.1:{server.server_port}/v1/systemone'
        bindings = {report['candidate_id']: {
            'reviewed_file_sha256': report['reviewed_file_sha256'],
            'applied_file_sha256': report['applied_file_sha256'],
            'adapter_path': report['origins']['adapter']['wheel_member'],
            'adapter_sha256': report['origins']['adapter']['sha256']}}
        from tests.test_use_case_retrieval_connected import _grant
        config, grant = _grant(report, receipt, public, endpoint, dependency, limits, adapter_spec)
        assert config['source_bindings'] == bindings
        config['environment_digest'] = digest({**_environment(report, receipt, public, cert)})
        grant['environment_digest'] = config['environment_digest']

        def one_run(label: str, *, mode: str = 'valid', tasks: str = 'two',
                    approval: str = '1', expected_revision: str = '0') -> tuple[Path, dict]:
            folder = tmp_path / ('effects-' + label)
            folder.mkdir(mode=0o700)
            second_task = 'graph-two' if tasks == 'two' else 'graph-one'
            observation, first, second = _observation(folder, second_task=second_task)
            ledger = tmp_path / ('ledger-' + label)
            reference = tmp_path / ('reference-' + label + '.json')
            now = datetime.now(timezone.utc)
            local_grant = dict(grant, issued_at=(now - timedelta(minutes=1)).isoformat(),
                               expires_at=(now + timedelta(minutes=5)).isoformat())
            manifest = {'schema_version': '1.0', 'mode': 'shadow',
                        'connected_config': config,
                        'authority': {'egress_grant': local_grant, 'activation': None},
                        'ledger_path': str(ledger),
                        'signatures': {'installed_binding': _issue(private, 'installed_binding',
                                                                   report['binding_sha256']),
                                       'egress_grant': _issue(private, 'egress_grant', digest(local_grant))}}
            reference.write_text(json.dumps(manifest), encoding='utf-8')
            reference.chmod(0o600)
            launch_env = {'L_CONNECTED_REF': str(reference),
                          'L_AUTH_PUBKEY_FILE': str(public),
                          'GRAPH_DB_PATH': str(folder / 'graph.sqlite'),
                          'GRAPH_EFFECT_PATH': str(folder / 'first.json'),
                          'GRAPH_SECOND_EFFECT_PATH': str(folder / 'second.json'),
                          'GRAPH_READY_PATH': str(folder / 'ready.txt'),
                          'L_TASKS': tasks, 'L_HOLD': '1',
                          'L_RELEASE_PATH': str(folder / 'release.txt'),
                          'L_APPROVAL': approval, 'L_EXPECTED_REVISION': expected_revision,
                          'SSL_CERT_FILE': str(cert)}
            common = dict(trusted_install_receipt_sha256=receipt['receipt_sha256'],
                          trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
                          installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
                          observation=observation)
            if label == 'valid':
                with pytest.raises(ConnectedDeliveryError, match='connected_host_references_required'):
                    plan_connected_delivery(install_plan, **common,
                        launch_environment={**launch_env,
                            'D_CONNECTED_REF': str(reference)}, host_profile='graph-l-v1')
                with pytest.raises(ConnectedDeliveryError, match='connected_host_references_required'):
                    plan_connected_delivery(install_plan, **common,
                        launch_environment={k: v for k, v in launch_env.items()
                                            if k != 'L_AUTH_PUBKEY_FILE'},
                        host_profile='graph-l-v1')
                with pytest.raises(ConnectedDeliveryError, match='connected_host_profile_binding_mismatch'):
                    plan_connected_delivery(install_plan, **common,
                        launch_environment={'REGISTERED_ALPHA_CONNECTED_REF': str(reference),
                            'REGISTERED_ALPHA_AUTH_PUBKEY_FILE': str(public)},
                        host_profile=None)
            plan = plan_connected_delivery(install_plan, **common,
                launch_environment=launch_env, host_profile='graph-l-v1')
            assert plan['host_profile'] == 'graph-l-v1'
            validate_contract(plan, 'connected-delivery-plan-v1')
            session = tmp_path / ('session-' + label)
            created = create_connected_session(session, plan,
                approved_plan_sha256=plan['plan_sha256'])
            active.append((session, plan))
            scope = _scope(created, plan, 'launch')
            if label == 'valid':
                monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
                with pytest.raises(ConnectedDeliveryError, match='connected_credential_unavailable'):
                    launch_connected_session(session, scope=scope,
                        approved_scope_sha256=scope['scope_sha256'])
                assert connected_session_status(session)['launch_attempts'] == 0
                wrong_key = dict(scope, public_key_sha256='0' * 64)
                wrong_key['scope_sha256'] = digest({k: v for k, v in wrong_key.items()
                                                  if k != 'scope_sha256'})
                with pytest.raises(ConnectedDeliveryError, match='exact_expiring_connected_scope_required'):
                    launch_connected_session(session, scope=wrong_key,
                        approved_scope_sha256=wrong_key['scope_sha256'])
                original = reference.read_bytes()
                reference.write_bytes(original + b'\n')
                assert not connected_session_status(session)['private_references_current']
                with pytest.raises(ConnectedDeliveryError, match='connected_plan_or_reference_drift'):
                    launch_connected_session(session, scope=scope,
                        approved_scope_sha256=scope['scope_sha256'])
                reference.write_bytes(original)
                assert connected_session_status(session)['private_references_current']
            monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')
            prior_calls = len(calls)
            response_mode['value'] = mode
            launched = launch_connected_session(session, scope=scope,
                approved_scope_sha256=scope['scope_sha256'])
            assert launched['launch_attempts'] == 1
            if approval == '0' or expected_revision != '0' or tasks == 'duplicate':
                deadline = time.monotonic() + 15
                while connected_session_status(session)['process_alive'] and time.monotonic() < deadline:
                    time.sleep(.05)
                assert not (folder / 'first.json').exists()
                assert not (folder / 'second.json').exists()
                if (folder / 'graph.sqlite').exists():
                    with sqlite3.connect(folder / 'graph.sqlite') as db:
                        assert db.execute('SELECT name FROM sqlite_master WHERE type="table"').fetchall() == []
            else:
                _wait(folder / 'ready.txt', b'ready\n')
                _wait(folder / 'first.json', first)
                before = connected_session_status(session)
                assert before['process_alive']
                assert before['independent_checks']['integration_reachable']
                assert not before['independent_checks']['outcome_verified']
                deadline = time.monotonic() + 10
                while len(calls) == prior_calls and time.monotonic() < deadline:
                    time.sleep(.02)
                assert len(calls) == prior_calls + 1
                if mode != 'hold_first':
                    while time.monotonic() < deadline:
                        snapshot = _ledger(ledger)
                        if snapshot is not None and snapshot['calls'] == 1 and not snapshot['inflight']:
                            break
                        time.sleep(.02)
                    else:
                        raise AssertionError('first graph shadow reservation did not settle')
                (folder / 'release.txt').write_bytes(b'go\n')
                _wait(folder / 'second.json', second)
                if mode == 'hold_first':
                    assert len(calls) == prior_calls + 1
                    snapshot = _ledger(ledger)
                    assert snapshot is not None and snapshot['calls'] == 1
                    release_response.set()
                deadline = time.monotonic() + 20
                while connected_session_status(session)['process_alive'] and time.monotonic() < deadline:
                    time.sleep(.05)
                assert not connected_session_status(session)['process_alive']
                _database(folder / 'graph.sqlite', first, second)
                assert len(calls) - prior_calls == (1 if mode == 'hold_first' else 2)
                assert calls[-1]['path'] == '/v1/systemone'
                snapshot = _ledger(ledger)
                assert snapshot is not None
                assert snapshot['calls'] == (1 if mode == 'hold_first' else 2)
                assert len(snapshot['tasks']) == 2
                assert not snapshot['inflight']
            status = connected_session_status(session)
            stop = _scope(status, plan, 'stop')
            stopped = stop_connected_session(session, scope=stop,
                approved_scope_sha256=stop['scope_sha256'])
            assert stopped['stage'] == 'stopped'
            return folder, status

        valid, valid_status = one_run('valid')
        wrong, wrong_status = one_run('wrong-model', mode='wrong_model')
        held, _ = one_run('inflight-budget', mode='hold_first')
        assert (valid / 'first.json').read_bytes() == (wrong / 'first.json').read_bytes()
        assert (valid / 'second.json').read_bytes() == (wrong / 'second.json').read_bytes()
        assert valid_status['run_id'] != wrong_status['run_id']
        denied, _ = one_run('approval-denied', approval='0')
        conflict, _ = one_run('revision-conflict', expected_revision='1')
        duplicate, _ = one_run('duplicate-task', tasks='duplicate')
        assert not (denied / 'first.json').exists()
        assert not (conflict / 'first.json').exists()
        assert not (duplicate / 'first.json').exists()
        installed_host = Path(report['origins']['host']['path'])
        original_host = installed_host.read_bytes()
        drift = tmp_path / 'drift-effects'
        drift.mkdir(mode=0o700)
        installed_host.write_bytes(original_host + b'\n')
        try:
            with pytest.raises(InputError):
                plan_connected_delivery(install_plan,
                    trusted_install_receipt_sha256=receipt['receipt_sha256'],
                    trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
                    installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
                    observation=_observation(drift)[0],
                    launch_environment={'L_CONNECTED_REF': str(tmp_path / 'reference-valid.json'),
                                        'L_AUTH_PUBKEY_FILE': str(public),
                                        'GRAPH_DB_PATH': str(drift / 'graph.sqlite'),
                                        'GRAPH_EFFECT_PATH': str(drift / 'first.json'),
                                        'GRAPH_SECOND_EFFECT_PATH': str(drift / 'second.json'),
                                        'GRAPH_READY_PATH': str(drift / 'ready.txt')},
                    host_profile='graph-l-v1')
        finally:
            installed_host.write_bytes(original_host)
    finally:
        for session, plan in active:
            if session.exists():
                status = connected_session_status(session)
                if status['process_alive']:
                    stop = _scope(status, plan, 'stop')
                    stop_connected_session(session, scope=stop,
                        approved_scope_sha256=stop['scope_sha256'])
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    assert rollback_implementation(host['target'], host['bundle'],
        host['applied']['rollback_digest'])['status'] == 'rolled_back'


def _environment(report: dict, receipt: dict, public: Path, cert: Path) -> dict:
    import platform
    from tests.test_connected_installed_binding import _verifier_identity
    return {'python': str(Path(receipt['installed']['python']).resolve()),
            'version': list(sys.version_info[:3]),
            'implementation': platform.python_implementation(),
            'openssl': ssl.OPENSSL_VERSION,
            'signature_verifier': _verifier_identity(),
            'public_key_sha256': file_hash(public),
            'cert_sha256': file_hash(cert), 'credential_present': True}
