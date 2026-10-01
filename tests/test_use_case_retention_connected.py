"""Installed H shadow decisions retain independently pinned raw source bytes."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import sqlite3
import ssl
import subprocess
import sys
from threading import Thread
import time

import pytest

from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.integrations.lifecycle import rollback_implementation
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator.template_connected_delivery import (
    ConnectedDeliveryError, connected_session_status, create_connected_session,
    launch_connected_session, plan_connected_delivery, stop_connected_session)
from tests.test_connected_installed_binding import _issuer, _issue, _verifier_identity
from tests.test_template_installation import _metadata
from tests.test_use_case_retention_bind import PROFILE
from tests.test_use_case_retention_bound_installed import _applied, _installed, _expected
from tests.test_use_case_retrieval_connected import _grant, _wait

pytestmark = pytest.mark.skipif(not PROFILE, reason='H connected requires Linux CPython 3.13')
LOADER = Path(__file__).parent / 'independent_hosts/retention_connected/connected_authority.py'


def _scope(status: dict, plan: dict, action: str) -> dict:
    value = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
             'run_id': status['run_id'], 'plan_sha256': plan['plan_sha256'],
             'public_key_sha256': plan['reference_sha256']['H_AUTH_PUBKEY_FILE'],
             'trusted_session_head': status['session_head_sha256'], 'action': action,
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
    value['scope_sha256'] = digest(value)
    validate_contract(value, 'connected-delivery-scope-v1')
    return value


def _observation(folder: Path, raw: bytes) -> dict:
    return {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
            'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                        'expected_sha256': hashlib.sha256(value).hexdigest()}
                       for role, path, value in (
                           ('ready', folder / 'ready.txt', b'ready\n'),
                           ('entrypoint_reached', folder / 'retention-one.json', raw),
                           ('integration_reachable', folder / 'retention-one.json', raw),
                           ('outcome_verified', folder / 'retention-two.json', raw))]}


def _state(ledger: Path) -> dict:
    with sqlite3.connect(f'file:{ledger}.sqlite?mode=ro', uri=True) as db:
        return json.loads(db.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])


def test_h_installed_connected_shadow_preserves_pins_and_explicit_choice(tmp_path, monkeypatch):
    name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not name:
        pytest.skip('exact private offline wheelhouse required')
    wheelhouse = Path(name).resolve(strict=True)
    wheels = sorted(wheelhouse.glob('*.whl'))
    assert wheels
    rows = [{'filename': p.name, 'sha256': file_hash(p)} for p in wheels]
    requirements = [{'name': n, 'version': v, 'wheel': p.name, 'sha256': file_hash(p)}
                    for p in wheels for n, v in [_metadata(p)]]
    environments = tmp_path / 'environments'
    environments.mkdir(mode=0o700)
    host = _applied(tmp_path, 'connected-h', '1.0.0', LOADER)
    install_plan, receipt = _installed(tmp_path, host, wheelhouse, rows,
                                      requirements, environments, 'connected-package')
    package_plan, package_receipt = install_plan['package_plan'], install_plan['package_receipt']
    report = derive_installed_binding(package_plan, package_receipt, install_plan, receipt,
        trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
        trusted_install_receipt_sha256=receipt['receipt_sha256'])
    assert report['source_file'] == 'retention_host/host_retention_consumer.py'
    assert report['origins']['loader']['wheel_member'] == 'retention_host/connected_authority.py'
    tree = ast.parse(Path(report['origins']['adapter']['path']).read_text())
    adapter_spec = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'SPEC' for t in n.targets)))
    dependency = {'files': [{'path': str(Path(report['site']) / 'retention_host' / member),
                            'sha256': file_hash(Path(report['site']) / 'retention_host' / member)}
                           for member in ('requirements.lock', 'runtime.json')]}
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2, 'max_total_calls': 2,
              'max_total_cost': 2, 'max_in_flight': 1, 'max_tasks': 2}
    private, public = _issuer(tmp_path)
    calls: list[dict] = []
    response_mode = {'value': 'valid'}

    class SyntheticTypeSafe(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            request = json.loads(raw)
            calls.append({'path': self.path, 'sha256': hashlib.sha256(raw).hexdigest()})
            mode = response_mode['value']
            if mode == 'timeout':
                time.sleep(3)
            answers = {}
            for name, question in request['questions'].items():
                if question['type'] == 'noul':
                    answers[name] = {'type': 'noul', 'noul': 1.0}
                else:
                    labels = list(question['criteria'])
                    choice = labels[0]
                    answers[name] = {'type': 'choice', 'choice': choice, 'confidence': 1.0,
                                     'probabilities': {label: float(label == choice) for label in labels}}
            model = request['model'] + '-wrong' if mode == 'wrong' else request['model']
            payload = json.dumps({'model': model, 'answers': answers,
                                 'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
            if mode == 'malformed':
                payload = b'{not-json'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (OSError, ssl.SSLError):
                pass

    cert, cert_key = tmp_path / 'cert.pem', tmp_path / 'cert-key.pem'
    generated = subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-nodes', '-keyout', str(cert_key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
        '-addext', 'subjectAltName=IP:127.0.0.1', '-days', '1'], capture_output=True, timeout=20)
    assert generated.returncode == 0
    cert.chmod(0o600); cert_key.chmod(0o600)
    server = ThreadingHTTPServer(('127.0.0.1', 0), SyntheticTypeSafe)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(str(cert), str(cert_key))
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sessions: list[tuple[Path, dict]] = []
    expected_raw, expected_items = _expected()
    try:
        endpoint = f'https://127.0.0.1:{server.server_port}/v1/systemone'
        config, grant = _grant(report, receipt, public, endpoint, dependency, limits, adapter_spec)
        config['environment_digest'] = digest({
            'python': str(Path(receipt['installed']['python']).resolve()),
            'version': list(sys.version_info[:3]), 'implementation': platform.python_implementation(),
            'openssl': ssl.OPENSSL_VERSION, 'signature_verifier': _verifier_identity(),
            'public_key_sha256': file_hash(public), 'cert_sha256': file_hash(cert),
            'credential_present': True})
        grant['environment_digest'] = config['environment_digest']
        monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')
        for label in ('valid', 'wrong', 'malformed', 'timeout', 'duplicate', 'revoke'):
            response_mode['value'] = label
            prior_calls = len(calls)
            folder = tmp_path / ('effects-' + label)
            folder.mkdir(mode=0o700)
            ledger = tmp_path / ('ledger-' + label)
            reference = tmp_path / ('reference-' + label + '.json')
            grant['issued_at'] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            grant['expires_at'] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            manifest = {'schema_version': '1.0', 'mode': 'shadow', 'connected_config': config,
                        'authority': {'egress_grant': grant, 'activation': None}, 'ledger_path': str(ledger),
                        'signatures': {'installed_binding': _issue(private, 'installed_binding', report['binding_sha256']),
                                       'egress_grant': _issue(private, 'egress_grant', digest(grant))}}
            original_reference = json.dumps(manifest).encode()
            reference.write_bytes(original_reference); reference.chmod(0o600)
            environment = {'H_CONNECTED_REF': str(reference), 'H_AUTH_PUBKEY_FILE': str(public),
                           'H_COMMAND': '/prune', 'H_EFFECT_DIRECTORY': str(folder),
                           'H_READY_PATH': str(folder / 'ready.txt'), 'H_RELEASE_PATH': str(folder / 'release.txt'),
                           'H_HOLD': '1', 'H_TASKS': 'duplicate' if label == 'duplicate' else 'two',
                           'SSL_CERT_FILE': str(cert)}
            common = dict(trusted_install_receipt_sha256=receipt['receipt_sha256'],
                          trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
                          installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
                          observation=_observation(folder, expected_raw), host_profile='retention-h-v1')
            if label == 'valid':
                for field in ('H_CONNECTED_REF', 'H_AUTH_PUBKEY_FILE', 'H_EFFECT_DIRECTORY',
                              'H_READY_PATH', 'H_RELEASE_PATH'):
                    with pytest.raises(ConnectedDeliveryError, match='connected_host_references_required'):
                        plan_connected_delivery(install_plan, **common,
                            launch_environment={k: v for k, v in environment.items() if k != field})
                with pytest.raises(ConnectedDeliveryError, match='connected_host_references_required'):
                    plan_connected_delivery(install_plan, **common,
                        launch_environment={**environment, 'H_TASKS': 'unbounded'})
                for choice in ('/compact', '', '/unknown'):
                    with pytest.raises(ConnectedDeliveryError, match='connected_retention_requires_explicit_prune'):
                        plan_connected_delivery(install_plan, **common,
                            launch_environment={**environment, 'H_COMMAND': choice})
                with pytest.raises(ConnectedDeliveryError, match='connected_mode_requires_observed_gate'):
                    plan_connected_delivery(install_plan, **common, launch_environment=environment,
                                            requested_mode='active')
            plan = plan_connected_delivery(install_plan, **common, launch_environment=environment)
            if label == 'valid':
                missing = tmp_path / 'session-missing-credential'
                missing_status = create_connected_session(missing, plan,
                    approved_plan_sha256=plan['plan_sha256'])
                missing_scope = _scope(missing_status, plan, 'launch')
                with monkeypatch.context() as no_credential:
                    no_credential.delenv('TYPESAFE_API_KEY')
                    with pytest.raises(ConnectedDeliveryError, match='connected_credential_unavailable'):
                        launch_connected_session(missing, scope=missing_scope,
                            approved_scope_sha256=missing_scope['scope_sha256'])
                assert not connected_session_status(missing)['process_alive']
                assert len(calls) == prior_calls and not (folder / 'retention-one.json').exists()
            session = tmp_path / ('session-' + label)
            created = create_connected_session(session, plan, approved_plan_sha256=plan['plan_sha256'])
            sessions.append((session, plan))
            scope = _scope(created, plan, 'launch')
            launch_connected_session(session, scope=scope, approved_scope_sha256=scope['scope_sha256'])
            if label != 'duplicate':
                _wait(folder / 'ready.txt', b'ready\n')
                _wait(folder / 'retention-one.json', expected_raw)
                assert json.loads((folder / 'retention-one.json').read_bytes()) == expected_items
                assert connected_session_status(session)['process_alive']
                deadline = time.monotonic() + 10
                while (len(calls) <= prior_calls or _state(ledger)['inflight']) and time.monotonic() < deadline:
                    time.sleep(.02)
                assert len(calls) - prior_calls == 1
                assert _state(ledger)['calls'] == 1 and _state(ledger)['inflight'] == {}
                if label == 'timeout':
                    records = [json.loads(line) for line in
                               (folder / 'timeout-events.jsonl').read_text().splitlines()]
                    assert records and all(record == {'type': 'assessment_error',
                        'error_class': 'EvaluationTimeoutError'} for record in records)
                if label == 'revoke':
                    reference.write_bytes(original_reference + b'\n')
                (folder / 'release.txt').write_bytes(b'go\n')
            deadline = time.monotonic() + 20
            while connected_session_status(session)['process_alive'] and time.monotonic() < deadline:
                time.sleep(.05)
            assert not connected_session_status(session)['process_alive']
            if label in ('duplicate', 'revoke'):
                assert not (folder / 'retention-two.json').exists()
                assert len(calls) - prior_calls <= 1
                assert not connected_session_status(session)['independent_checks']['outcome_verified']
            else:
                _wait(folder / 'retention-two.json', expected_raw)
                assert connected_session_status(session)['independent_checks']['outcome_verified']
                state = _state(ledger)
                assert 1 <= state['calls'] <= 2 and state['inflight'] == {}
                assert len(state['tasks']) == 2
                if label == 'valid':
                    assert state['calls'] == 2 and len(calls) - prior_calls == 2
            if label == 'revoke':
                reference.write_bytes(original_reference)
                assert (folder / 'retention-one.json').read_bytes() == expected_raw
                assert _state(ledger)['calls'] == 1
            scope = _scope(connected_session_status(session), plan, 'stop')
            assert stop_connected_session(session, scope=scope,
                approved_scope_sha256=scope['scope_sha256'])['stage'] == 'stopped'
        # Drift is the last installed-generation case. Restoring file bytes does
        # not make the old installed generation valid for another launch.
        source = Path(report['origins']['host']['path'])
        original_source = source.read_bytes()
        try:
            source.write_bytes(original_source + b'\n# synthetic source drift\n')
            with pytest.raises(InputError):
                plan_connected_delivery(install_plan, **common, launch_environment=environment)
        finally:
            source.write_bytes(original_source)
    finally:
        for session, plan in sessions:
            if session.exists() and connected_session_status(session)['process_alive']:
                scope = _scope(connected_session_status(session), plan, 'stop')
                stop_connected_session(session, scope=scope, approved_scope_sha256=scope['scope_sha256'])
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    assert rollback_implementation(host['target'], host['bundle'],
        host['applied']['rollback_digest'])['status'] == 'rolled_back'
