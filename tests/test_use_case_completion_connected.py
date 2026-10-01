"""Independent E raw-completion host through an installed synthetic shadow console."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import ssl
import subprocess
import sys
from threading import Thread
import time

import pytest

from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator.template_connected_delivery import (
    ConnectedDeliveryError, connected_session_status, create_connected_session,
    launch_connected_session, plan_connected_delivery, stop_connected_session,
)
from jev_integration_evaluator.integrations.lifecycle import rollback_implementation
from tests.test_connected_installed_binding import _issuer, _issue, _verifier_identity
from tests.test_template_installation import _metadata
from tests.test_use_case_completion_host import PROFILE, _applied, _expected
from tests.test_reusable_templates import fixture_module


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='E connected installed fixture requires Linux x86-64 CPython 3.13')
LOADER = Path(__file__).parent / 'independent_hosts/completion_connected/connected_authority.py'


def _scope(status: dict, plan: dict, action: str) -> dict:
    scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
             'run_id': status['run_id'], 'plan_sha256': plan['plan_sha256'],
             'public_key_sha256': plan['reference_sha256']['E_AUTH_PUBKEY_FILE'],
             'trusted_session_head': status['session_head_sha256'], 'action': action,
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()}
    scope['scope_sha256'] = digest(scope)
    validate_contract(scope, 'connected-delivery-scope-v1')
    return scope


def _observation(folder: Path) -> tuple[dict, dict]:
    first_state, first_receipt = _expected('completion-one')
    second_state, second_receipt = _expected('completion-two')
    expected = (('ready', folder / 'ready.txt', b'ready\n'),
                ('entrypoint_reached', folder / 'state-completion-one.json', first_state),
                ('integration_reachable', folder / 'receipt-completion-one.json', first_receipt),
                ('outcome_verified', folder / 'receipt-completion-two.json', second_receipt))
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                               'expected_sha256': hashlib.sha256(raw).hexdigest()}
                              for role, path, raw in expected]}
    paths = {'E_RAW_STATE_TEMPLATE': str(folder / 'state-{task_id}.json'),
             'E_EFFECT_RECEIPT_TEMPLATE': str(folder / 'receipt-{task_id}.json'),
             'E_READY_PATH': str(folder / 'ready.txt')}
    return observation, paths


def _installed(tmp_path: Path, host: dict, wheelhouse: Path) -> tuple[dict, dict]:
    wheels = sorted(wheelhouse.glob('*.whl'))
    assert wheels
    configuration = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    request = {'schema_version': '1.0', 'host_root': str(host['target']),
               'implementation_bundle': str(host['bundle']),
               'trusted_modified_receipt_sha256': host['modified']['receipt_sha256'],
               'template_directory': str(host['template']),
               'reviewed_package_source_sha256': digest(installer._tree(host['target'])),
               'reviewed_configuration_sha256': digest(configuration),
               'interpreter': sys.executable,
               'build_tools': {name: importlib.metadata.version(name)
                               for name in ('pip', 'setuptools', 'wheel')},
               'wheelhouse': str(wheelhouse),
               'wheels': [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels],
               'requirements': [{'name': name, 'version': version, 'wheel': path.name,
                                 'sha256': file_hash(path)} for path in wheels
                                for name, version in [_metadata(path)]],
               'package_directory': str(tmp_path / 'package'),
               'environment_parent': str(tmp_path / 'environments'),
               'console_script': 'completion-host', 'configuration': configuration,
               'secret_references': {}}
    (tmp_path / 'environments').mkdir(mode=0o700)
    package_plan = installer.plan_package(request)
    package_receipt = installer.build_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_install(package_plan, package_receipt)
    receipt = installer.install_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'
    return install_plan, receipt


def _grant(report: dict, receipt: dict, public: Path, endpoint: str,
           dependency: dict, limits: dict, adapter_spec: dict, cert: Path) -> tuple[dict, dict]:
    source_bindings = {report['candidate_id']: {
        'reviewed_file_sha256': report['reviewed_file_sha256'],
        'applied_file_sha256': report['applied_file_sha256'],
        'adapter_path': report['origins']['adapter']['wheel_member'],
        'adapter_sha256': report['origins']['adapter']['sha256']}}
    environment_digest = digest({
        'python': str(Path(receipt['installed']['python']).resolve()),
        'version': list(sys.version_info[:3]),
        'implementation': platform.python_implementation(),
        'openssl': ssl.OPENSSL_VERSION,
        'signature_verifier': _verifier_identity(),
        'public_key_sha256': file_hash(public), 'cert_sha256': file_hash(cert),
        'credential_present': True})
    config = {'endpoint': endpoint, 'credential_ref': 'env:TYPESAFE_API_KEY',
              'model': 'jev-1.13.0', 'environment_digest': environment_digest,
              'source_root': report['site'], 'source_plan': report['source_plan'],
              'source_bindings': source_bindings, 'installed_binding': report}
    source_identity = {'root': report['site'], 'plan': report['source_plan'],
                       'bindings': source_bindings,
                       'installed_binding_sha256': report['binding_sha256']}
    now = datetime.now(timezone.utc)
    grant = {'endpoint': endpoint, 'credential_ref': config['credential_ref'],
             'model': config['model'], 'environment_digest': environment_digest,
             'source_digest': digest(source_identity),
             'dependency_digest': digest(dependency), 'budget_digest': digest(limits),
             'adapters_digest': digest({report['candidate_id']: digest(adapter_spec)}),
             'mode': 'shadow', 'issued_at': (now - timedelta(minutes=1)).isoformat(),
             'expires_at': (now + timedelta(minutes=6)).isoformat()}
    return config, grant


def _wait(path: Path, expected: bytes, seconds: float = 20) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if path.is_file() and path.read_bytes() == expected:
            return
        time.sleep(.02)
    raise AssertionError('independent E raw effect missing')


def test_e_source_bound_installed_connected_shadow_raw_completion(tmp_path, monkeypatch):
    wheelhouse_name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not wheelhouse_name:
        pytest.skip('exact private offline wheelhouse required')
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    host = _applied(tmp_path, 'connected-e', '1.0.0',
                    ('completion-one', 'completion-two'), LOADER)
    install_plan, receipt = _installed(tmp_path, host, wheelhouse)
    package_plan, package_receipt = install_plan['package_plan'], install_plan['package_receipt']
    report = derive_installed_binding(package_plan, package_receipt, install_plan, receipt,
        trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
        trusted_install_receipt_sha256=receipt['receipt_sha256'])
    assert report['source_file'] == 'completion_host/host_raw_completion.py'
    assert report['origins']['loader']['wheel_member'] == 'completion_host/connected_authority.py'
    assert all(Path(item['path']).is_file() for item in report['source_plan']['files'])
    adapter_tree = ast.parse(Path(report['origins']['adapter']['path']).read_text())
    adapter_spec = ast.literal_eval(next(node.value for node in adapter_tree.body
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'SPEC' for target in node.targets)))
    dependency = {'files': [{'path': str(Path(report['site']) / 'completion_host' / name),
                             'sha256': file_hash(Path(report['site']) / 'completion_host' / name)}
                            for name in ('requirements.lock', 'runtime.json')]}
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
              'max_total_calls': 2, 'max_total_cost': 2,
              'max_in_flight': 1, 'max_tasks': 2}
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
            if response_mode['value'] == 'timeout':
                time.sleep(3)
            answers = {}
            for name, question in request['questions'].items():
                if question['type'] == 'noul':
                    answers[name] = {'type': 'noul', 'noul': 1.0}
                else:
                    labels = list(question['criteria'])
                    choice = labels[0]
                    answers[name] = {'type': 'choice', 'choice': choice,
                                     'confidence': 1.0,
                                     'probabilities': {label: float(label == choice)
                                                       for label in labels}}
            model = (request['model'] if response_mode['value'] != 'wrong_model'
                     else request['model'] + '-wrong')
            result = (b'{}' if response_mode['value'] == 'malformed' else
                      json.dumps({'model': model, 'answers': answers,
                                  'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode())
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(result))); self.end_headers()
            try: self.wfile.write(result)
            except (BrokenPipeError, ssl.SSLError): pass

    cert, cert_key = tmp_path / 'loopback.crt', tmp_path / 'loopback.key'
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
    active_sessions: list[tuple[Path, dict]] = []
    try:
        endpoint = f'https://127.0.0.1:{server.server_port}/v1/systemone'
        config, grant = _grant(report, receipt, public, endpoint,
                               dependency, limits, adapter_spec, cert)
        oracle = fixture_module('examples/coding-agent/completion_oracle.py', 'connected_e_oracle')
        for label, expected_calls in (('valid', 2), ('wrong-model', 1),
                                      ('malformed', 1), ('timeout', 1),
                                      ('duplicate', 0)):
            response_mode['value'] = label.replace('-', '_')
            before_calls = len(calls)
            folder = tmp_path / ('effects-' + label)
            folder.mkdir(mode=0o700)
            observation, effect_env = _observation(folder)
            grant['issued_at'] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            grant['expires_at'] = (datetime.now(timezone.utc) + timedelta(minutes=6)).isoformat()
            manifest = {'schema_version': '1.0', 'mode': 'shadow',
                        'connected_config': config,
                        'authority': {'egress_grant': grant, 'activation': None},
                        'ledger_path': str(tmp_path / ('ledger-' + label)),
                        'signatures': {'installed_binding': _issue(private, 'installed_binding',
                                                                   report['binding_sha256']),
                                       'egress_grant': _issue(private, 'egress_grant', digest(grant))}}
            reference = tmp_path / ('reference-' + label + '.json')
            reference.write_text(json.dumps(manifest), encoding='utf-8'); reference.chmod(0o600)
            launch_env = {'E_CONNECTED_REF': str(reference), 'E_AUTH_PUBKEY_FILE': str(public),
                          **effect_env, 'E_TASKS': 'duplicate' if label == 'duplicate' else 'two',
                          'SSL_CERT_FILE': str(cert)}
            common = dict(trusted_install_receipt_sha256=receipt['receipt_sha256'],
                          trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
                          installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
                          observation=observation, host_profile='completion-e-v1')
            if label == 'valid':
                with pytest.raises(ConnectedDeliveryError, match='connected_host_references_required'):
                    plan_connected_delivery(install_plan, **common,
                        launch_environment={**launch_env, 'D_CONNECTED_REF': str(reference)})
            plan = plan_connected_delivery(install_plan, **common, launch_environment=launch_env)
            validate_contract(plan, 'connected-delivery-plan-v1')
            session = tmp_path / ('session-' + label)
            created = create_connected_session(session, plan,
                approved_plan_sha256=plan['plan_sha256'])
            active_sessions.append((session, plan))
            scope = _scope(created, plan, 'launch')
            wrong_key = dict(scope, public_key_sha256='0' * 64)
            wrong_key['scope_sha256'] = digest({k: v for k, v in wrong_key.items()
                                                if k != 'scope_sha256'})
            with pytest.raises(ConnectedDeliveryError, match='exact_expiring_connected_scope_required'):
                launch_connected_session(session, scope=wrong_key,
                    approved_scope_sha256=wrong_key['scope_sha256'])
            monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')
            if label == 'valid':
                monkeypatch.delenv('TYPESAFE_API_KEY')
                with pytest.raises(ConnectedDeliveryError, match='connected_credential_unavailable'):
                    launch_connected_session(session, scope=scope,
                        approved_scope_sha256=scope['scope_sha256'])
                assert connected_session_status(session)['launch_attempts'] == 0
                monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')
            original = reference.read_bytes()
            reference.write_bytes(original + b'\n')
            assert not connected_session_status(session)['private_references_current']
            with pytest.raises(ConnectedDeliveryError, match='connected_plan_or_reference_drift'):
                launch_connected_session(session, scope=scope,
                    approved_scope_sha256=scope['scope_sha256'])
            reference.write_bytes(original)
            assert connected_session_status(session)['private_references_current']
            launched = launch_connected_session(session, scope=scope,
                approved_scope_sha256=scope['scope_sha256'])
            assert launched['launch_attempts'] == 1
            if label == 'duplicate':
                deadline = time.monotonic() + 20
                while connected_session_status(session)['process_alive'] and time.monotonic() < deadline:
                    time.sleep(.05)
                assert not connected_session_status(session)['process_alive']
                assert len(calls) == before_calls and list(folder.iterdir()) == []
                with pytest.raises(ConnectedDeliveryError):
                    launch_connected_session(session, scope=scope,
                        approved_scope_sha256=scope['scope_sha256'])
                stop = _scope(connected_session_status(session), plan, 'stop')
                assert stop_connected_session(session, scope=stop,
                    approved_scope_sha256=stop['scope_sha256'])['stage'] == 'stopped'
                drift_session = tmp_path / 'session-source-drift'
                drift_created = create_connected_session(drift_session, plan,
                    approved_plan_sha256=plan['plan_sha256'])
                drift_scope = _scope(drift_created, plan, 'launch')
                installed_source = Path(report['origins']['host']['path'])
                installed_source.write_bytes(installed_source.read_bytes() + b'\n')
                assert not connected_session_status(drift_session)['installed_sources_current']
                with pytest.raises(InputError, match='installed_generation_drift_or_unverified'):
                    launch_connected_session(drift_session, scope=drift_scope,
                        approved_scope_sha256=drift_scope['scope_sha256'])
                assert connected_session_status(drift_session)['launch_attempts'] == 0
                continue
            _wait(folder / 'ready.txt', b'ready\n')
            first_state, first_receipt = _expected('completion-one')
            _wait(folder / 'state-completion-one.json', first_state)
            _wait(folder / 'receipt-completion-one.json', first_receipt)
            status = connected_session_status(session)
            assert status['independent_checks']['integration_reachable']
            assert not status['independent_checks']['outcome_verified']
            objective = {'task_id': 'completion-one', 'allowed_fields': ['task_id', 'status',
                         'revision', 'labels', 'unrequested'], 'required_status': 'closed',
                         'required_labels': ['verified'], 'required_unrequested': []}
            assert oracle.exact_goal(json.loads(first_state), objective)
            assert not oracle.exact_goal({**json.loads(first_state), 'labels': []}, objective)
            assert not oracle.exact_goal({**json.loads(first_state), 'executor_success': True}, objective)
            deadline = time.monotonic() + 10
            while len(calls) < before_calls + 1 and time.monotonic() < deadline:
                time.sleep(.02)
            assert len(calls) == before_calls + 1
            second_state, second_receipt = _expected('completion-two')
            _wait(folder / 'state-completion-two.json', second_state)
            _wait(folder / 'receipt-completion-two.json', second_receipt)
            deadline = time.monotonic() + 10
            while len(calls) < before_calls + expected_calls and time.monotonic() < deadline:
                time.sleep(.02)
            assert expected_calls <= len(calls) - before_calls <= 2
            assert connected_session_status(session)['independent_checks']['outcome_verified']
            assert oracle.exact_goal(json.loads(second_state), {**objective, 'task_id': 'completion-two'})
            deadline = time.monotonic() + 20
            while connected_session_status(session)['process_alive'] and time.monotonic() < deadline:
                time.sleep(.05)
            assert not connected_session_status(session)['process_alive']
            assert Path(str(tmp_path / ('ledger-' + label)) + '.sqlite').is_file()
            stop = _scope(connected_session_status(session), plan, 'stop')
            assert stop_connected_session(session, scope=stop,
                approved_scope_sha256=stop['scope_sha256'])['stage'] == 'stopped'
        assert 5 <= len(calls) <= 8
    finally:
        for session, plan in active_sessions:
            if session.exists():
                status = connected_session_status(session)
                if status['process_alive']:
                    stop = _scope(status, plan, 'stop')
                    stop_connected_session(session, scope=stop,
                        approved_scope_sha256=stop['scope_sha256'])
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    assert rollback_implementation(host['target'], host['bundle'],
        host['applied']['rollback_digest'])['status'] == 'rolled_back'
