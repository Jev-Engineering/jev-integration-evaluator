"""Offline exact composite wheel origins; no connected provider request."""
from __future__ import annotations

import importlib.util
import copy
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import platform
import sys
import ssl
import subprocess
from threading import Thread
import time

import pytest

from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.integrations.runtime_lifecycle import HostRuntimeLifecycle, LifecycleError
from jev_integration_evaluator.template_connected_composite_binding import (
    CompositeConnectedBindingError, derive_installed_composite_binding,
)
from jev_integration_evaluator.template_connected_delivery import (
    ConnectedDeliveryError, plan_connected_delivery, create_connected_session,
    launch_connected_session,
    connected_session_status, stop_connected_session,
)
from jev_integration_evaluator.use_case_templates import use_case_matrix


_OPENSSL_ENV = {'LANG': 'C', 'OPENSSL_CONF': os.devnull,
                'OPENSSL_MODULES': '/nonexistent', 'OPENSSL_ENGINES': '/nonexistent'}


def _issuer(root: Path) -> tuple[Path, Path]:
    private, public = root / 'synthetic-issuer-private.pem', root / 'synthetic-public.pem'
    subprocess.run(['/usr/bin/openssl', 'genpkey', '-algorithm', 'EC',
        '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', str(private)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=10, env=_OPENSSL_ENV)
    private.chmod(0o600)
    subprocess.run(['/usr/bin/openssl', 'pkey', '-in', str(private), '-pubout',
        '-out', str(public)], check=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=10, env=_OPENSSL_ENV)
    public.chmod(0o600)
    return private, public


def _issue(private: Path, kind: str, exact: str) -> str:
    signed = subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', str(private)],
        input=(kind + ':' + exact).encode('ascii'), capture_output=True,
        check=True, timeout=10, env=_OPENSSL_ENV)
    return base64.b64encode(signed.stdout).decode('ascii')


def _verifier_identity() -> dict:
    tool = Path('/usr/bin/openssl')
    version = subprocess.run([str(tool), 'version'], capture_output=True,
        check=True, timeout=2, env=_OPENSSL_ENV).stdout.decode('ascii').strip()
    return {'path': str(tool), 'sha256': file_hash(tool), 'version': version}


class _InstalledCheckpoint(Exception):
    pass


def test_dual_connected_matrix_retains_distinct_source_and_pending_gates():
    checkpoints = use_case_matrix()['independent_host_checkpoints']
    assert [row['kind'] for row in checkpoints] == [
        'registered-alpha-connected-shadow-v1',
        'registered-dual-connected-shadow-v1',
        'registered-alpha-connected-windows-shadow-v1']
    dual = checkpoints[1]
    root = Path(__file__).resolve().parents[1] / dual['root']
    for row in dual['placements'].values():
        assert file_hash(root / row['file']) == row['sha256']
    for role, file in (('console', 'src/registered_dual/console.py'),
                       ('loader', 'src/registered_dual/connected_authority.py'),
                       ('project', 'pyproject.toml')):
        assert file_hash(root / file) == dual[role + '_sha256']
    assert dual['canary'] == dual['active'] == 'pending_combined_observed_gate'
    assert dual['upgrade'] == 'pending_connected_upgrade'
    assert dual['rollback'] == 'pending_connected_rollback'
    assert dual['provider'] == 'unobserved' and dual['benefit'] == 'unknown'


@pytest.mark.skipif(not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
                         and sys.implementation.name == 'cpython'
                         and sys.version_info[:2] == (3, 13)),
                    reason='composite installed binding needs Linux x86-64 CPython 3.13')
def test_two_reviewed_connected_origins_derive_from_off_install(tmp_path, monkeypatch):
    wheelhouse_name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not wheelhouse_name:
        pytest.skip('explicit owner-private offline wheelhouse required')
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    fixture = Path(__file__).resolve().parent / 'independent_hosts/registered_dual_connected'
    driver_path = fixture / 'installed_journey.py'
    module_spec = importlib.util.spec_from_file_location('connected_dual_install_driver', driver_path)
    driver = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(driver)
    actual_install = installer.install_composite_package
    captured = {}

    def inspect_on_install(plan, **kwargs):
        receipt = actual_install(plan, **kwargs)
        package_plan, package_receipt = plan['package_plan'], plan['package_receipt']
        report = derive_installed_composite_binding(package_plan, package_receipt, plan,
            receipt, trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
            trusted_install_receipt_sha256=receipt['receipt_sha256'])
        captured.update(report=report, plan=plan, receipt=receipt)
        raise _InstalledCheckpoint

    monkeypatch.setattr(installer, 'install_composite_package', inspect_on_install)
    with pytest.raises(_InstalledCheckpoint):
        driver.run_offline(tmp_path / 'run', wheelhouse, tmp_path / 'anchors')
    report = captured['report']
    assert report['kind'] == 'connected-installed-composite-binding-v1'
    assert len(report['candidate_ids']) == len(report['placements']) == 2
    assert set(report['placements']) == set(report['candidate_ids'])
    assert report['shared_origins']['console']['wheel_member'] == 'registered_dual/console.py'
    assert report['shared_origins']['loader']['wheel_member'] == 'registered_dual/connected_authority.py'
    assert {row['path'] for row in report['source_plan']['files']} == {
        origin['path'] for origin in report['shared_origins'].values()} | {
        origin['path'] for placement in report['placements'].values()
        for origin in placement['origins'].values()} | {report['reviewed_project_path']}
    reference, public = tmp_path / 'dual-reference.json', tmp_path / 'dual-public.pem'
    reference.write_text('{}', encoding='utf-8')
    public.write_bytes(b'not-an-issuer-key')
    reference.chmod(0o600); public.chmod(0o600)
    ready, effect = tmp_path / 'dual-ready', tmp_path / 'dual-effect'
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                               'expected_sha256': hashlib.sha256(expected).hexdigest()}
                              for role, path, expected in (
                                  ('ready', ready, b'ready'),
                                  ('entrypoint_reached', ready, b'ready'),
                                  ('integration_reachable', effect, b'effect'),
                                  ('outcome_verified', effect, b'effect'))]}
    connected_plan = plan_connected_delivery(captured['plan'],
        trusted_install_receipt_sha256=captured['receipt']['receipt_sha256'],
        trusted_package_receipt_sha256=captured['plan']['package_receipt']['receipt_sha256'],
        installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
        observation=observation,
        launch_environment={'REGISTERED_DUAL_CONNECTED_REF': str(reference),
                            'REGISTERED_DUAL_AUTH_PUBKEY_FILE': str(public),
                            'DUAL_PERMIT': '0'},
        host_profile='registered-dual-connected-v1')
    assert connected_plan['host_profile'] == 'registered-dual-connected-v1'
    assert connected_plan['requested_mode'] == 'shadow'
    adapters = {}
    for name, placement in report['placements'].items():
        origin = placement['origins']['adapter']['path']
        spec = importlib.util.spec_from_file_location('installed_dual_' + name.replace('-', '_'), origin)
        adapter = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(adapter)
        adapters[name] = adapter
    source_bindings = {name: {
        'reviewed_file_sha256': placement['reviewed_file_sha256'],
        'applied_file_sha256': placement['applied_file_sha256'],
        'adapter_path': placement['origins']['adapter']['wheel_member'],
        'adapter_sha256': placement['origins']['adapter']['sha256']}
        for name, placement in report['placements'].items()}
    config = {'endpoint': 'https://127.0.0.1:9/v1/systemone',
              'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
              'environment_digest': '1' * 64, 'source_root': report['site'],
              'source_plan': report['source_plan'], 'source_bindings': source_bindings,
              'installed_binding': report}
    dependency = {'files': [{'path': str(Path(report['site']) / 'registered_dual' / name),
                             'sha256': file_hash(Path(report['site']) / 'registered_dual' / name)}
                            for name in ('requirements.lock', 'runtime.json')]}
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
              'max_total_calls': 2, 'max_total_cost': 2,
              'max_in_flight': 1, 'max_tasks': 2}
    source_identity = {'root': report['site'], 'plan': report['source_plan'],
                       'bindings': source_bindings,
                       'installed_binding_sha256': report['binding_sha256']}
    now = datetime.now(timezone.utc)
    grant = {'endpoint': config['endpoint'], 'credential_ref': config['credential_ref'],
             'model': config['model'], 'environment_digest': config['environment_digest'],
             'source_digest': digest(source_identity), 'dependency_digest': digest(dependency),
             'budget_digest': digest(limits),
             'adapters_digest': digest({name: digest(module.SPEC)
                                        for name, module in adapters.items()}),
             'mode': 'shadow', 'issued_at': (now - timedelta(minutes=1)).isoformat(),
             'expires_at': (now + timedelta(minutes=2)).isoformat()}
    class Audit:
        def append(self, _record):
            pass
    monkeypatch.setenv('TYPESAFE_API_KEY', 'local-synthetic-startup-only')
    with HostRuntimeLifecycle(adapters, budget_limits=limits, audit_log=Audit(),
                              dependency_plan=dependency, startup_mode='shadow',
                              connected_config=config,
                              authority={'egress_grant': grant, 'activation': None},
                              verify_authority=lambda kind, exact: (kind == 'installed_binding'
                                  and exact == report['binding_sha256']) or (kind == 'egress_grant'
                                  and exact == digest(grant)),
                              current_environment_digest=lambda: '1' * 64,
                              ledger_path=tmp_path / 'shared-connected-ledger') as runtime:
        first, second = (runtime.router(name, {'task_id': 'same-stable-task'})
                         for name in report['candidate_ids'])
        assert first.budget_coordinator is second.budget_coordinator is runtime.coordinator
    canary_grant = {**grant, 'mode': 'canary'}
    with pytest.raises(LifecycleError, match='connected_composite_combined_gate_required'):
        HostRuntimeLifecycle(adapters, budget_limits=limits, audit_log=Audit(),
            dependency_plan=dependency, startup_mode='canary', connected_config=config,
            authority={'egress_grant': canary_grant, 'activation': None},
            verify_authority=lambda kind, exact: (kind == 'installed_binding'
                and exact == report['binding_sha256']) or (kind == 'egress_grant'
                and exact == digest(canary_grant)),
            current_environment_digest=lambda: '1' * 64,
            ledger_path=tmp_path / 'unqualified-canary-ledger')
    first_name, second_name = report['candidate_ids']
    wrong_origin = copy.deepcopy(report)
    wrong_origin['placements'][first_name]['origins']['adapter'] = copy.deepcopy(
        report['placements'][second_name]['origins']['adapter'])
    wrong_origin['binding_sha256'] = digest({key: value for key, value in
        wrong_origin.items() if key != 'binding_sha256'})
    wrong_config = {**config, 'installed_binding': wrong_origin}
    wrong_source = {**source_identity,
                    'installed_binding_sha256': wrong_origin['binding_sha256']}
    wrong_grant = {**grant, 'source_digest': digest(wrong_source)}
    with pytest.raises(LifecycleError, match='connected_source_binding_mismatch'):
        HostRuntimeLifecycle(adapters, budget_limits=limits, audit_log=Audit(),
            dependency_plan=dependency, startup_mode='shadow',
            connected_config=wrong_config,
            authority={'egress_grant': wrong_grant, 'activation': None},
            verify_authority=lambda kind, exact: (kind == 'installed_binding'
                and exact == wrong_origin['binding_sha256']) or (kind == 'egress_grant'
                and exact == digest(wrong_grant)),
            current_environment_digest=lambda: '1' * 64,
            ledger_path=tmp_path / 'wrong-origin-ledger')
    kwargs = {'trusted_package_receipt_sha256': captured['plan']['package_receipt']['receipt_sha256'],
              'trusted_install_receipt_sha256': captured['receipt']['receipt_sha256']}
    with pytest.raises(CompositeConnectedBindingError, match='composite_receipt_or_generation_unverified'):
        derive_installed_composite_binding(captured['plan']['package_plan'],
            captured['plan']['package_receipt'], captured['plan'], captured['receipt'],
            **{**kwargs, 'trusted_install_receipt_sha256': '0' * 64})
    host = Path(next(iter(report['placements'].values()))['origins']['host']['path'])
    alias = tmp_path / 'linked-installed-host.py'
    os.link(host, alias)
    try:
        # The off install status independently catches the added hardlink
        # before the later per-origin check can run.
        with pytest.raises(CompositeConnectedBindingError, match='composite_receipt_or_generation_unverified'):
            derive_installed_composite_binding(captured['plan']['package_plan'],
                captured['plan']['package_receipt'], captured['plan'], captured['receipt'], **kwargs)
    finally:
        alias.unlink()
    _normal_installed_dual_shadow(tmp_path, monkeypatch, report, captured,
                                  adapters, source_bindings, dependency)


def _normal_installed_dual_shadow(tmp_path, monkeypatch, report, captured,
                                  adapters, source_bindings, dependency):
    """Synthetic issuer and local TLS protocol through the installed console."""
    private, public = _issuer(tmp_path)
    reference = tmp_path / 'permitted-dual-reference.json'
    cert, cert_key = tmp_path / 'dual-loopback.crt', tmp_path / 'dual-loopback.key'
    subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-nodes', '-keyout', str(cert_key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
        '-addext', 'subjectAltName=IP:127.0.0.1', '-days', '1'],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=20, env=_OPENSSL_ENV)
    cert.chmod(0o600); cert_key.chmod(0o600)
    calls = []
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
                    choice = 'summarize' if 'summarize' in labels else labels[0]
                    answers[name] = {'type': 'choice', 'choice': choice,
                                     'confidence': 1.0,
                                     'probabilities': {label: float(label == choice)
                                                       for label in labels}}
            response_model = (request['model'] if response_mode['value'] == 'valid'
                              else request['model'] + '-wrong')
            response = json.dumps({'model': response_model, 'answers': answers,
                                   'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response))); self.end_headers()
            self.wfile.write(response)

    server = ThreadingHTTPServer(('127.0.0.1', 0), SyntheticTypeSafe)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(cert_key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    release = tmp_path / 'dual-release'
    try:
        install_plan, install_receipt = captured['plan'], captured['receipt']
        limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
                  'max_total_calls': 2, 'max_total_cost': 2,
                  'max_in_flight': 1, 'max_tasks': 1}
        environment = digest({
            'python': str(Path(install_receipt['installed']['python']).resolve()),
            'version': list(sys.version_info[:3]),
            'implementation': platform.python_implementation(),
            'openssl': ssl.OPENSSL_VERSION,
            'signature_verifier': _verifier_identity(),
            'public_key_sha256': file_hash(public), 'cert_sha256': file_hash(cert),
            'credential_present': True})
        config = {'endpoint': f'https://127.0.0.1:{server.server_port}/v1/systemone',
                  'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
                  'environment_digest': environment, 'source_root': report['site'],
                  'source_plan': report['source_plan'], 'source_bindings': source_bindings,
                  'installed_binding': report}
        identity = {'root': report['site'], 'plan': report['source_plan'],
                    'bindings': source_bindings,
                    'installed_binding_sha256': report['binding_sha256']}
        now = datetime.now(timezone.utc)
        grant = {'endpoint': config['endpoint'], 'credential_ref': config['credential_ref'],
                 'model': config['model'], 'environment_digest': environment,
                 'source_digest': digest(identity),
                 'dependency_digest': digest(dependency),
                 'budget_digest': digest(limits),
                 'adapters_digest': digest({name: digest(module.SPEC)
                                            for name, module in adapters.items()}),
                 'mode': 'shadow',
                 'issued_at': (now - timedelta(minutes=1)).isoformat(),
                 'expires_at': (now + timedelta(minutes=5)).isoformat()}
        manifest = {'schema_version': '1.0', 'mode': 'shadow', 'connected_config': config,
                    'authority': {'egress_grant': grant, 'activation': None},
                    'ledger_path': str(tmp_path / 'dual-permitted-ledger'),
                    'signatures': {'installed_binding': _issue(private, 'installed_binding',
                                                               report['binding_sha256']),
                                   'egress_grant': _issue(private, 'egress_grant', digest(grant))}}
        reference.write_text(json.dumps(manifest), encoding='utf-8')
        reference.chmod(0o600)
        ready = tmp_path / 'dual-ready'
        alpha_effect, queue_effect = tmp_path / 'alpha-effect.jsonl', tmp_path / 'queue-effect.jsonl'
        audit = tmp_path / 'dual-audit.json'
        task = 'dual-connected-shadow-task'
        alpha_expected = (json.dumps({'action': 'inspect', 'item': 'fixture-one',
                                      'task_id': task}, sort_keys=True,
                                     separators=(',', ':')) + '\n').encode()
        queue_expected = (json.dumps({'item': 'fixture-one', 'operation': 'enqueue',
                                      'task_id': task}, sort_keys=True,
                                     separators=(',', ':')) + '\n').encode()
        observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                       'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                                   'expected_sha256': hashlib.sha256(expected).hexdigest()}
                                  for role, path, expected in (
                                      ('ready', ready, b'dual-ready\n'),
                                      ('entrypoint_reached', ready, b'dual-ready\n'),
                                      ('integration_reachable', alpha_effect, alpha_expected),
                                      ('outcome_verified', queue_effect, queue_expected))]}
        connected_plan = plan_connected_delivery(install_plan,
            trusted_install_receipt_sha256=install_receipt['receipt_sha256'],
            trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
            installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
            observation=observation,
            launch_environment={'REGISTERED_DUAL_CONNECTED_REF': str(reference),
                'REGISTERED_DUAL_AUTH_PUBKEY_FILE': str(public),
                'DUAL_PERMIT': '1', 'DUAL_TASK_ID': task, 'DUAL_AUDIT_PATH': str(audit),
                'REGISTERED_ALPHA_EFFECTS': str(alpha_effect),
                'WORK_QUEUE_EFFECTS': str(queue_effect), 'DUAL_HOLD': '1',
                'DUAL_READY_PATH': str(ready), 'DUAL_RELEASE_PATH': str(release),
                'DUAL_REPEAT': '1', 'SSL_CERT_FILE': str(cert)},
            host_profile='registered-dual-connected-v1')
        session = tmp_path / 'permitted-dual-session'
        created = create_connected_session(session, connected_plan,
            approved_plan_sha256=connected_plan['plan_sha256'])
        scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
                 'run_id': created['run_id'], 'plan_sha256': connected_plan['plan_sha256'],
                 'public_key_sha256': connected_plan['reference_sha256'][
                     'REGISTERED_DUAL_AUTH_PUBKEY_FILE'],
                 'trusted_session_head': created['session_head_sha256'], 'action': 'launch',
                 'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
        scope['scope_sha256'] = digest(scope)
        wrong_key = {**scope, 'public_key_sha256': '0' * 64}
        wrong_key['scope_sha256'] = digest({key: value for key, value in
                                          wrong_key.items() if key != 'scope_sha256'})
        with pytest.raises(ConnectedDeliveryError, match='exact_expiring_connected_scope_required'):
            launch_connected_session(session, scope=wrong_key,
                approved_scope_sha256=wrong_key['scope_sha256'])
        monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
        with pytest.raises(ConnectedDeliveryError, match='connected_credential_unavailable'):
            launch_connected_session(session, scope=scope,
                approved_scope_sha256=scope['scope_sha256'])
        assert connected_session_status(session)['launch_attempts'] == 0
        monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-loopback-only')
        launched = launch_connected_session(session, scope=scope,
            approved_scope_sha256=scope['scope_sha256'])
        assert launched['requested_mode'] == 'shadow' and launched['launch_attempts'] == 1
        deadline = time.monotonic() + 12
        while not ready.is_file() and time.monotonic() < deadline:
            time.sleep(.02)
        assert ready.read_bytes() == b'dual-ready\n'
        assert alpha_effect.read_bytes() == alpha_expected
        assert queue_effect.read_bytes() == queue_expected
        assert len(calls) == 2 and all(row['path'] == '/v1/systemone' for row in calls)
        running = connected_session_status(session)
        assert running['process_alive'] and all(running['independent_checks'].values())
        release.write_bytes(b'go\n')
        while connected_session_status(session)['process_alive'] and time.monotonic() < deadline:
            time.sleep(.02)
        assert not connected_session_status(session)['process_alive']
        audit_data = json.loads(audit.read_text())
        assert sorted(audit_data['assessed']) == report['candidate_ids']
        assert len(set(audit_data['tokens'])) == 1
        assert len(set(audit_data['task_hashes'])) == 1
        assert audit_data['calls'] == 2
        assert sorted(audit_data['repeat_results']) == [
            'duplicate_queue_job', 'duplicate_task_effect']
        current = connected_session_status(session)
        stop_scope = {**scope, 'trusted_session_head': current['session_head_sha256'],
                      'action': 'stop'}
        stop_scope['scope_sha256'] = digest({key: value for key, value in
                                           stop_scope.items() if key != 'scope_sha256'})
        stopped = stop_connected_session(session, scope=stop_scope,
            approved_scope_sha256=stop_scope['scope_sha256'])
        assert stopped['stage'] == 'stopped' and not stopped['process_alive']

        # A new owner-private ledger and task exercise the real client response
        # validator. The host's deterministic effects must still complete.
        response_mode['value'] = 'wrong_model'
        fault_task = 'dual-connected-wrong-model'
        fault_ready, fault_release = tmp_path / 'fault-ready', tmp_path / 'fault-release'
        fault_alpha = tmp_path / 'fault-alpha.jsonl'
        fault_queue = tmp_path / 'fault-queue.jsonl'
        fault_audit = tmp_path / 'fault-audit.json'
        fault_alpha_expected = (json.dumps({'action': 'inspect', 'item': 'fixture-one',
            'task_id': fault_task}, sort_keys=True, separators=(',', ':')) + '\n').encode()
        fault_queue_expected = (json.dumps({'item': 'fixture-one', 'operation': 'enqueue',
            'task_id': fault_task}, sort_keys=True, separators=(',', ':')) + '\n').encode()
        fault_observation = {'schema_version': '1.0',
            'kind': 'template-delivery-observation-v1',
            'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                        'expected_sha256': hashlib.sha256(expected).hexdigest()}
                       for role, path, expected in (
                           ('ready', fault_ready, b'dual-ready\n'),
                           ('entrypoint_reached', fault_ready, b'dual-ready\n'),
                           ('integration_reachable', fault_alpha, fault_alpha_expected),
                           ('outcome_verified', fault_queue, fault_queue_expected))]}
        fault_manifest = {**manifest, 'ledger_path': str(tmp_path / 'dual-fault-ledger')}
        reference.write_text(json.dumps(fault_manifest), encoding='utf-8')
        fault_environment = dict(connected_plan['off_provenance']['launch_environment'])
        fault_environment.update({'DUAL_TASK_ID': fault_task, 'DUAL_AUDIT_PATH': str(fault_audit),
            'REGISTERED_ALPHA_EFFECTS': str(fault_alpha),
            'WORK_QUEUE_EFFECTS': str(fault_queue),
            'DUAL_READY_PATH': str(fault_ready), 'DUAL_RELEASE_PATH': str(fault_release),
            'DUAL_REPEAT': '0'})
        fault_plan = plan_connected_delivery(install_plan,
            trusted_install_receipt_sha256=install_receipt['receipt_sha256'],
            trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
            installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
            observation=fault_observation, launch_environment=fault_environment,
            host_profile='registered-dual-connected-v1')
        fault_session = tmp_path / 'wrong-model-dual-session'
        fault_created = create_connected_session(fault_session, fault_plan,
            approved_plan_sha256=fault_plan['plan_sha256'])
        fault_scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
            'run_id': fault_created['run_id'], 'plan_sha256': fault_plan['plan_sha256'],
            'public_key_sha256': fault_plan['reference_sha256'][
                'REGISTERED_DUAL_AUTH_PUBKEY_FILE'],
            'trusted_session_head': fault_created['session_head_sha256'], 'action': 'launch',
            'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
        fault_scope['scope_sha256'] = digest(fault_scope)
        launch_connected_session(fault_session, scope=fault_scope,
            approved_scope_sha256=fault_scope['scope_sha256'])
        fault_deadline = time.monotonic() + 12
        try:
            while not fault_ready.is_file() and time.monotonic() < fault_deadline:
                time.sleep(.02)
            assert fault_ready.read_bytes() == b'dual-ready\n'
            assert fault_alpha.read_bytes() == fault_alpha_expected
            assert fault_queue.read_bytes() == fault_queue_expected
            assert 3 <= len(calls) <= 4
        finally:
            fault_release.write_bytes(b'go\n')
        while connected_session_status(fault_session)['process_alive'] and time.monotonic() < fault_deadline:
            time.sleep(.02)
        assert not connected_session_status(fault_session)['process_alive']
        fault_audit_data = json.loads(fault_audit.read_text())
        assert 'assessment_error' in fault_audit_data['audit_types']
        assert 'evaluation_or_audit_failure' in fault_audit_data['audit_reasons']
        assert len(set(fault_audit_data['tokens'])) == 1
        assert 1 <= fault_audit_data['calls'] <= 2
        fault_current = connected_session_status(fault_session)
        fault_stop_scope = {**fault_scope,
            'trusted_session_head': fault_current['session_head_sha256'], 'action': 'stop'}
        fault_stop_scope['scope_sha256'] = digest({key: value for key, value in
            fault_stop_scope.items() if key != 'scope_sha256'})
        fault_stopped = stop_connected_session(fault_session, scope=fault_stop_scope,
            approved_scope_sha256=fault_stop_scope['scope_sha256'])
        assert fault_stopped['stage'] == 'stopped'
        public.chmod(0o644)
        assert not connected_session_status(fault_session)['private_references_current']
        public.chmod(0o600)
        linked_public = tmp_path / 'linked-dual-public.pem'
        os.link(public, linked_public)
        try:
            assert not connected_session_status(fault_session)['private_references_current']
        finally:
            linked_public.unlink()
    finally:
        if not release.exists():
            release.write_bytes(b'go\n')
        server.shutdown(); server.server_close(); thread.join(timeout=5)
