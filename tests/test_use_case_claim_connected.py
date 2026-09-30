"""Reviewed M citation consumer through an installed local-TLS shadow console."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
from threading import Thread
import time

import pytest

from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator.template_connected_delivery import (
    ConnectedDeliveryError, connected_session_status, create_connected_session,
    launch_connected_session, plan_connected_delivery, stop_connected_session,
)
from jev_integration_evaluator.integrations.lifecycle import rollback_implementation
from tests.test_connected_installed_binding import _issuer, _issue
from tests.test_template_installation import _metadata
from tests.test_use_case_claim_bound_installed import _applied, _installed
from tests.test_use_case_claim_host import PROFILE, _expected
from tests.test_use_case_retrieval_connected import _grant, _wait


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='M connected installed fixture requires Linux x86-64 CPython 3.13')
LOADER = Path(__file__).parent / 'independent_hosts/claim_connected/connected_authority.py'


def _scope(status: dict, plan: dict, action: str) -> dict:
    value = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
             'run_id': status['run_id'], 'plan_sha256': plan['plan_sha256'],
             'public_key_sha256': plan['reference_sha256']['M_AUTH_PUBKEY_FILE'],
             'trusted_session_head': status['session_head_sha256'], 'action': action,
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
    value['scope_sha256'] = digest(value)
    validate_contract(value, 'connected-delivery-scope-v1')
    return value


def _observation(folder: Path) -> dict:
    first_support, first_audit, _ = _expected('claim-one')
    _, _, second_claim = _expected('claim-two')
    return {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
            'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                        'expected_sha256': hashlib.sha256(raw).hexdigest()}
                       for role, path, raw in (
                           ('ready', folder / 'ready.txt', b'ready\n'),
                           ('entrypoint_reached', folder / 'claim-one/support.json', first_support),
                           ('integration_reachable', folder / 'claim-one/audit.json', first_audit),
                           ('outcome_verified', folder / 'claim-two/claim.json', second_claim))]}


def test_m_installed_connected_shadow_preserves_raw_claim_provenance(tmp_path, monkeypatch):
    name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not name:
        pytest.skip('exact private offline wheelhouse required')
    wheelhouse = Path(name).resolve(strict=True)
    wheels = sorted(wheelhouse.glob('*.whl'))
    assert wheels
    rows = [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels]
    requirements = [{'name': name, 'version': version, 'wheel': path.name,
                     'sha256': file_hash(path)}
                    for path in wheels for name, version in [_metadata(path)]]
    environments = tmp_path / 'environments'
    environments.mkdir(mode=0o700)
    host = _applied(tmp_path, 'connected-m', '1.0.0', LOADER)
    install_plan, receipt = _installed(tmp_path, host, wheelhouse, rows,
                                      requirements, environments, 'connected-package')
    package_plan, package_receipt = install_plan['package_plan'], install_plan['package_receipt']
    report = derive_installed_binding(package_plan, package_receipt, install_plan, receipt,
        trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
        trusted_install_receipt_sha256=receipt['receipt_sha256'])
    assert report['source_file'] == 'claim_host/host_claim_support.py'
    assert report['origins']['loader']['wheel_member'] == 'claim_host/connected_authority.py'
    tree = ast.parse(Path(report['origins']['adapter']['path']).read_text())
    adapter_spec = ast.literal_eval(next(node.value for node in tree.body
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'SPEC' for target in node.targets)))
    dependency = {'files': [{'path': str(Path(report['site']) / 'claim_host' / name),
                            'sha256': file_hash(Path(report['site']) / 'claim_host' / name)}
                           for name in ('requirements.lock', 'runtime.json')]}
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
              'max_total_calls': 2, 'max_total_cost': 2, 'max_in_flight': 1, 'max_tasks': 2}
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
            answers = {}
            for name, question in request['questions'].items():
                if question['type'] == 'noul':
                    answers[name] = {'type': 'noul', 'noul': 1.0}
                else:
                    labels = list(question['criteria'])
                    choice = 'supported' if 'supported' in labels else labels[0]
                    answers[name] = {'type': 'choice', 'choice': choice, 'confidence': 1.0,
                                     'probabilities': {label: float(label == choice)
                                                       for label in labels}}
            model = request['model'] if response_mode['value'] == 'valid' else request['model'] + '-wrong'
            payload = json.dumps({'model': model, 'answers': answers,
                                 'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    cert, cert_key = tmp_path / 'cert.pem', tmp_path / 'cert-key.pem'
    generated = subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048',
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
    sessions: list[tuple[Path, dict]] = []
    try:
        endpoint = f'https://127.0.0.1:{server.server_port}/v1/systemone'
        config, grant = _grant(report, receipt, public, endpoint, dependency, limits, adapter_spec)
        # The issuer binds the exact owner-private trust certificate separately.
        from tests.test_connected_installed_binding import _verifier_identity
        import platform
        config['environment_digest'] = digest({
            'python': str(Path(receipt['installed']['python']).resolve()),
            'version': list(sys.version_info[:3]), 'implementation': platform.python_implementation(),
            'openssl': ssl.OPENSSL_VERSION, 'signature_verifier': _verifier_identity(),
            'public_key_sha256': file_hash(public), 'cert_sha256': file_hash(cert),
            'credential_present': True})
        grant['environment_digest'] = config['environment_digest']
        monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')

        for label, minimum_calls in (('valid', 2), ('wrong-model', 1)):
            response_mode['value'] = 'valid' if label == 'valid' else 'wrong'
            prior_calls = len(calls)
            folder = tmp_path / ('effects-' + label)
            folder.mkdir(mode=0o700)
            for task in ('claim-one', 'claim-two'):
                (folder / task).mkdir(mode=0o700)
            ledger = tmp_path / ('ledger-' + label)
            reference = tmp_path / ('reference-' + label + '.json')
            grant['issued_at'] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            grant['expires_at'] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            manifest = {'schema_version': '1.0', 'mode': 'shadow', 'connected_config': config,
                        'authority': {'egress_grant': grant, 'activation': None},
                        'ledger_path': str(ledger),
                        'signatures': {'installed_binding': _issue(private, 'installed_binding',
                                                                   report['binding_sha256']),
                                       'egress_grant': _issue(private, 'egress_grant', digest(grant))}}
            reference.write_text(json.dumps(manifest), encoding='utf-8')
            reference.chmod(0o600)
            environment = {'M_CONNECTED_REF': str(reference), 'M_AUTH_PUBKEY_FILE': str(public),
                           'M_EFFECT_DIRECTORY': str(folder), 'M_READY_PATH': str(folder / 'ready.txt'),
                           'M_RELEASE_PATH': str(folder / 'release.txt'), 'M_HOLD': '1',
                           'M_TASKS': 'two', 'M_CLAIM_SCENARIO': 'accept', 'M_APPROVAL': '1',
                           'SSL_CERT_FILE': str(cert)}
            common = dict(trusted_install_receipt_sha256=receipt['receipt_sha256'],
                          trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
                          installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
                          observation=_observation(folder), host_profile='claim-m-v1')
            if label == 'valid':
                for wrong in ({k: v for k, v in environment.items() if k != 'M_CONNECTED_REF'},
                              {**environment, 'M_TASKS': 'unbounded'},
                              {**environment, 'M_CLAIM_SCENARIO': 'invented'},
                              {**environment, 'M_APPROVAL': 'model-decides'}):
                    with pytest.raises(ConnectedDeliveryError, match='connected_host_references_required'):
                        plan_connected_delivery(install_plan, **common, launch_environment=wrong)
                with pytest.raises(ConnectedDeliveryError, match='connected_mode_requires_observed_gate'):
                    plan_connected_delivery(install_plan, **common,
                        launch_environment=environment, requested_mode='active')
            plan = plan_connected_delivery(install_plan, **common, launch_environment=environment)
            session = tmp_path / ('session-' + label)
            created = create_connected_session(session, plan, approved_plan_sha256=plan['plan_sha256'])
            sessions.append((session, plan))
            launch = _scope(created, plan, 'launch')
            launch_connected_session(session, scope=launch, approved_scope_sha256=launch['scope_sha256'])
            _wait(folder / 'ready.txt', b'ready\n')
            for member, raw in zip(('support.json', 'audit.json', 'claim.json'), _expected('claim-one')):
                _wait(folder / 'claim-one' / member, raw)
            status = connected_session_status(session)
            assert status['process_alive']
            assert status['independent_checks']['integration_reachable']
            assert not status['independent_checks']['outcome_verified']
            deadline = time.monotonic() + 10
            while len(calls) < prior_calls + minimum_calls and time.monotonic() < deadline:
                time.sleep(.02)
            assert minimum_calls <= len(calls) - prior_calls <= 2
            assert calls[-1]['path'] == '/v1/systemone'
            (folder / 'release.txt').write_bytes(b'go\n')
            for member, raw in zip(('support.json', 'audit.json', 'claim.json'), _expected('claim-two')):
                _wait(folder / 'claim-two' / member, raw)
            assert connected_session_status(session)['independent_checks']['outcome_verified']
            deadline = time.monotonic() + 20
            while connected_session_status(session)['process_alive'] and time.monotonic() < deadline:
                time.sleep(.05)
            assert not connected_session_status(session)['process_alive']
            assert Path(str(ledger) + '.sqlite').is_file()
            stop = _scope(connected_session_status(session), plan, 'stop')
            assert stop_connected_session(session, scope=stop,
                approved_scope_sha256=stop['scope_sha256'])['stage'] == 'stopped'
    finally:
        for session, plan in sessions:
            if session.exists() and connected_session_status(session)['process_alive']:
                stop = _scope(connected_session_status(session), plan, 'stop')
                stop_connected_session(session, scope=stop, approved_scope_sha256=stop['scope_sha256'])
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    assert rollback_implementation(host['target'], host['bundle'],
        host['applied']['rollback_digest'])['status'] == 'rolled_back'
