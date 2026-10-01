"""Offline installed-origin and local synthetic protocol checks; no provider request."""
from __future__ import annotations

import importlib.util
import ast
import hashlib
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import platform
import shutil
import sqlite3
import ssl
import subprocess
import sys
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator.template_connected_delivery import (
    ConnectedDeliveryError, plan_connected_delivery, create_connected_session,
    launch_connected_session, connected_session_status, stop_connected_session,
    resume_connected_session)
from jev_integration_evaluator.io import InputError, canonical, digest, file_hash
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
from jev_integration_evaluator.robustness import request_fingerprint
from jev_integration_evaluator.template_catalog import prepare_template_binding
from jev_integration_evaluator.use_case_templates import use_case_matrix


class _InstalledCheckpoint(Exception):
    pass


def test_connected_ledger_restart_retains_charges_without_invented_revocation(tmp_path):
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
              'max_total_calls': 2, 'max_total_cost': 2,
              'max_in_flight': 1, 'max_tasks': 2}
    path = tmp_path / 'shared-ledger'
    first = RuntimeLedger(path, identity='installed-scope', **limits)
    reservation = first.reserve('first-task', 1)
    first.suspend(durable=False)  # normal shutdown before shadow future drains
    first.settle(reservation, actual_cost=0)
    first.close_task('first-task')
    first.release()

    restarted = RuntimeLedger(path, identity='installed-scope', **limits)
    assert restarted.snapshot()['calls'] == 1
    assert restarted.snapshot()['closed_tasks'] == 1
    reservation = restarted.reserve('second-task', 1)
    restarted.settle(reservation, actual_cost=0)
    restarted.close_task('second-task')
    restarted.suspend()  # explicit durable revocation remains a restart latch
    restarted.release()
    with pytest.raises(InputError, match='runtime_ledger_revoked'):
        RuntimeLedger(path, identity='installed-scope', **limits)


def test_connected_ledger_overrun_remains_durably_revoked(tmp_path):
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
              'max_total_calls': 2, 'max_total_cost': 2,
              'max_in_flight': 1, 'max_tasks': 2}
    path = tmp_path / 'overrun-ledger'
    ledger = RuntimeLedger(path, identity='installed-scope', **limits)
    reservation = ledger.reserve('first-task', 0.5)
    ledger.settle(reservation, actual_cost=1)
    ledger.release()
    with pytest.raises(InputError, match='runtime_ledger_revoked'):
        RuntimeLedger(path, identity='installed-scope', **limits)


_OPENSSL_ENV = {'LANG': 'C', 'OPENSSL_CONF': os.devnull,
                'OPENSSL_MODULES': '/nonexistent', 'OPENSSL_ENGINES': '/nonexistent'}


def _issuer(tmp_path: Path) -> tuple[Path, Path]:
    private, public = tmp_path / 'issuer-private.pem', tmp_path / 'issuer-public.pem'
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
    return {'path': str(tool), 'sha256': hashlib.sha256(tool.read_bytes()).hexdigest(),
            'version': version}


def test_alpha_checkpoint_is_separate_from_six_use_case_rows():
    matrix = use_case_matrix()
    assert [row['id'] for row in matrix['rows']] == ['C', 'L', 'D', 'E', 'M', 'H']
    assert next(row for row in matrix['rows'] if row['id'] == 'C')['provider'] == 'pending'
    checkpoint = matrix['independent_host_checkpoints'][0]
    root = Path(__file__).resolve().parents[1] / checkpoint['root']
    for name, relative in (('host', 'src/registered_alpha/host.py'),
                           ('console', 'src/registered_alpha/console.py'),
                           ('loader', 'src/registered_alpha/connected_authority.py'),
                           ('project', 'pyproject.toml')):
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == checkpoint[name + '_sha256']
    assert checkpoint['provider'] == 'unobserved'
    assert checkpoint['benefit'] == 'unknown'


def test_connected_alpha_102_has_separate_source_review(tmp_path):
    if not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
            and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)):
        pytest.skip('source-bound Alpha fixture requires Linux CPython 3.13')
    root = Path(__file__).resolve().parent / 'independent_hosts/registered_alpha_connected'
    target = tmp_path / 'host'
    shutil.copytree(root, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    module_spec = importlib.util.spec_from_file_location(
        'alpha_connected_qualification', target / 'qualification.py')
    qualification = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(qualification)
    request, binding = qualification.source_matched_request(target)
    prepared = prepare_template_binding(target, request, binding)
    assert prepared['request']['implementation_spec']['entrypoint_binding']['kind'] == 'single-request-v1'
    assert 'connected_authority' in (target / 'src/registered_alpha/console.py').read_text()
    assert '1.0.2' in (target / 'pyproject.toml').read_text()
    loader = target / 'src/registered_alpha/connected_authority.py'
    loader.write_bytes(loader.read_bytes() + b'\n# changed after source review\n')
    with pytest.raises(InputError, match='connected_alpha_source_review_changed'):
        qualification.source_matched_request(target)


def test_connected_alpha_102_authenticates_exact_grant_and_revocation(tmp_path, monkeypatch):
    if sys.platform != 'linux':
        pytest.skip('owner-private host authority requires Linux')
    source = (Path(__file__).resolve().parent / 'independent_hosts/registered_alpha_connected'
              / 'src/registered_alpha/connected_authority.py')
    module_spec = importlib.util.spec_from_file_location('alpha_connected_authority', source)
    authority = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(authority)
    private, public = _issuer(tmp_path)
    ledger = tmp_path / 'ledger.db'
    exact = 'a' * 64
    signature = _issue(private, 'installed_binding', exact)
    manifest = {'schema_version': '1.0', 'mode': 'shadow',
                'connected_config': {'exact': 'source'}, 'authority': {'exact': 'grant'},
                'ledger_path': str(ledger),
                'signatures': {'installed_binding': signature}}
    reference = tmp_path / 'connected.json'
    reference.write_text(json.dumps(manifest), encoding='utf-8'); reference.chmod(0o600)
    monkeypatch.setenv('REGISTERED_ALPHA_CONNECTED_REF', str(reference))
    monkeypatch.setenv('REGISTERED_ALPHA_AUTH_PUBKEY_FILE', str(public))
    monkeypatch.setenv('REGISTERED_ALPHA_AUTH_PUBKEY_SHA256', hashlib.sha256(public.read_bytes()).hexdigest())
    monkeypatch.setenv('REGISTERED_ALPHA_CONNECTED_REF_SHA256', hashlib.sha256(reference.read_bytes()).hexdigest())
    options = authority.options()
    assert options['verify_authority']('installed_binding', exact) is True
    assert options['verify_authority']('installed_binding', 'b' * 64) is False
    public.chmod(0o644)
    assert options['verify_authority']('installed_binding', exact) is False
    public.chmod(0o600)
    linked = tmp_path / 'linked-public.pem'
    os.link(public, linked)
    assert options['verify_authority']('installed_binding', exact) is False
    linked.unlink()
    original_public = public.read_bytes()
    public.write_bytes(b'changed-key')
    assert options['verify_authority']('installed_binding', exact) is False
    public.write_bytes(original_public)
    assert options['verify_authority']('installed_binding', exact) is True
    original_identity = authority._openssl_identity
    authority._openssl_identity = lambda: {'path': '/changed', 'sha256': '0' * 64,
                                            'version': 'OpenSSL 3.changed'}
    assert options['verify_authority']('installed_binding', exact) is False
    authority._openssl_identity = original_identity
    manifest['signatures'] = {}
    reference.write_text(json.dumps(manifest), encoding='utf-8')
    assert options['verify_authority']('installed_binding', exact) is False


@pytest.mark.parametrize('fixture_name', ['registered_alpha', 'registered_alpha_connected'])
def test_alpha_installed_binding_uses_exact_wheel_and_installed_origins(
        tmp_path, monkeypatch, fixture_name):
    wheelhouse = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
            and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)
            and wheelhouse and Path(wheelhouse).is_dir()):
        pytest.skip('requires Linux CPython 3.13 and reviewed offline wheelhouse')
    source = Path(__file__).resolve().parent / 'independent_hosts/registered_alpha/installed_journey.py'
    module_spec = importlib.util.spec_from_file_location('alpha_installed_binding_driver', source)
    driver = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(driver)
    driver.ROOT = Path(__file__).resolve().parent / 'independent_hosts' / fixture_name
    actual_install = installer.install_package
    observed = {}

    def inspect_on_install(plan, **kwargs):
        receipt = actual_install(plan, **kwargs)
        package_plan = plan['package_plan']
        package_receipt = plan['package_receipt']
        observed['report'] = derive_installed_binding(
            package_plan, package_receipt, plan, receipt,
            trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
            trusted_install_receipt_sha256=receipt['receipt_sha256'])
        observed['install_plan'] = plan
        observed['install_receipt'] = receipt
        raise _InstalledCheckpoint

    monkeypatch.setattr(installer, 'install_package', inspect_on_install)
    with pytest.raises(_InstalledCheckpoint):
        driver.run_offline(tmp_path / 'run', Path(wheelhouse), tmp_path / 'anchors')
    report = observed['report']
    assert report['kind'] == 'connected-installed-binding-v1'
    assert report['source_file'].startswith('src/')
    assert report['origins']['host']['wheel_member'] == 'registered_alpha/host.py'
    assert report['origins']['console']['wheel_member'] == 'registered_alpha/console.py'
    assert ('loader' in report['origins']) is (fixture_name == 'registered_alpha_connected')
    assert all(Path(row['path']).is_file() for row in report['source_plan']['files'])
    if fixture_name == 'registered_alpha_connected':
        private, public = _issuer(tmp_path)
        reference = tmp_path / 'connected-ref.json'
        ready, effect = tmp_path / 'ready.bin', tmp_path / 'effect.bin'
        audit = tmp_path / 'audit.jsonl'
        observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                       'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                                   'expected_sha256': hashlib.sha256(expected).hexdigest()}
                                  for role, path, expected in (
                                      ('ready', ready, b'ready'),
                                      ('entrypoint_reached', ready, b'ready'),
                                      ('integration_reachable', effect, b'effect'),
                                      ('outcome_verified', effect, b'effect'))]}
        installed_plan = observed['install_plan']
        installed_receipt = observed['install_receipt']
        adapter_tree = ast.parse(Path(report['origins']['adapter']['path']).read_text())
        adapter_spec = ast.literal_eval(next(node.value for node in adapter_tree.body
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 'SPEC' for target in node.targets)))
        dependency = {'files': [{'path': str(Path(report['site']) / 'registered_alpha' / name),
                                 'sha256': hashlib.sha256((Path(report['site']) / 'registered_alpha' / name).read_bytes()).hexdigest()}
                                for name in ('requirements.lock', 'runtime.json')]}
        limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
                  'max_total_calls': 2, 'max_total_cost': 2,
                  'max_in_flight': 1, 'max_tasks': 2}
        source_bindings = {report['candidate_id']: {
            'reviewed_file_sha256': report['reviewed_file_sha256'],
            'applied_file_sha256': report['applied_file_sha256'],
            'adapter_path': report['origins']['adapter']['wheel_member'],
            'adapter_sha256': report['origins']['adapter']['sha256']}}
        environment_digest = digest({
            'python': str(Path(installed_receipt['installed']['python']).resolve()),
            'version': list(sys.version_info[:3]),
            'implementation': platform.python_implementation(),
            'openssl': ssl.OPENSSL_VERSION, 'cert_sha256': None,
            'signature_verifier': _verifier_identity(),
            'public_key_sha256': hashlib.sha256(public.read_bytes()).hexdigest(),
            'credential_present': True})
        config = {'endpoint': 'https://127.0.0.1:9/v1/systemone',
                  'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
                  'environment_digest': environment_digest, 'source_root': report['site'],
                  'source_plan': report['source_plan'], 'source_bindings': source_bindings,
                  'installed_binding': report}
        source_identity = {'root': report['site'], 'plan': report['source_plan'],
                           'bindings': source_bindings,
                           'installed_binding_sha256': report['binding_sha256']}
        now = datetime.now(timezone.utc)
        grant = {'endpoint': config['endpoint'], 'credential_ref': config['credential_ref'],
                 'model': config['model'], 'environment_digest': environment_digest,
                 'source_digest': digest(source_identity),
                 'dependency_digest': digest(dependency),
                 'budget_digest': digest(limits),
                 'adapters_digest': digest({report['candidate_id']: digest(adapter_spec)}),
                 'mode': 'shadow',
                 'issued_at': (now - timedelta(minutes=1)).isoformat(),
                 'expires_at': (now + timedelta(minutes=5)).isoformat()}
        signatures = {name: _issue(private, name, exact)
                      for name, exact in {'installed_binding': report['binding_sha256'],
                                          'egress_grant': digest(grant)}.items()}
        ledger = tmp_path / 'runtime.ledger'
        manifest = {'schema_version': '1.0', 'mode': 'shadow',
                    'connected_config': config,
                    'authority': {'egress_grant': grant, 'activation': None},
                    'ledger_path': str(ledger), 'signatures': signatures}
        reference.write_text(json.dumps(manifest), encoding='utf-8'); reference.chmod(0o600)
        connected_plan = plan_connected_delivery(installed_plan,
            trusted_install_receipt_sha256=installed_receipt['receipt_sha256'],
            trusted_package_receipt_sha256=installed_plan['package_receipt']['receipt_sha256'],
            installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
            observation=observation,
            launch_environment={'REGISTERED_ALPHA_CONNECTED_REF': str(reference),
                                'REGISTERED_ALPHA_AUTH_PUBKEY_FILE': str(public),
                                'REGISTERED_ALPHA_PERMIT': '0',
                                'REGISTERED_ALPHA_AUDIT': str(audit),
                                'REGISTERED_ALPHA_EFFECTS': str(effect)})
        # The omitted profile is the original serialized Alpha plan, including
        # its canonical bytes and digest. Existing approval/scope hashes retain
        # the same representation after the finite D selector was added.
        legacy = {'schema_version': '1.0', 'kind': 'connected-delivery-plan-v1',
                  'off_provenance': connected_plan['off_provenance'],
                  'installed_binding': report,
                  'trusted_binding_sha256': report['binding_sha256'],
                  'trusted_package_receipt_sha256': installed_plan['package_receipt']['receipt_sha256'],
                  'reference_sha256': {
                      'REGISTERED_ALPHA_CONNECTED_REF': file_hash(reference),
                      'REGISTERED_ALPHA_AUTH_PUBKEY_FILE': file_hash(public)},
                  'requested_mode': 'shadow', 'provider_reachable': None,
                  'runtime_activation_authorized': False}
        legacy['plan_sha256'] = digest(legacy)
        assert canonical(connected_plan) == canonical(legacy)
        assert 'host_profile' not in connected_plan
        created = create_connected_session(tmp_path / 'connected-session', connected_plan,
            approved_plan_sha256=connected_plan['plan_sha256'])
        assert created['stage'] == 'installed' and created['launch_attempts'] == 0
        scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
                 'run_id': created['run_id'], 'plan_sha256': connected_plan['plan_sha256'],
                 'public_key_sha256': connected_plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'],
                 'trusted_session_head': created['session_head_sha256'], 'action': 'launch',
                 'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
        scope['scope_sha256'] = digest(scope)
        wrong_key_scope = dict(scope, public_key_sha256='0' * 64)
        wrong_key_scope['scope_sha256'] = digest({k: v for k, v in wrong_key_scope.items()
                                                  if k != 'scope_sha256'})
        with pytest.raises(ConnectedDeliveryError, match='exact_expiring_connected_scope_required'):
            launch_connected_session(tmp_path / 'connected-session', scope=wrong_key_scope,
                approved_scope_sha256=wrong_key_scope['scope_sha256'])
        monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
        with pytest.raises(ConnectedDeliveryError, match='connected_credential_unavailable'):
            launch_connected_session(tmp_path / 'connected-session', scope=scope,
                approved_scope_sha256=scope['scope_sha256'])
        assert connected_session_status(tmp_path / 'connected-session')['launch_attempts'] == 0
        monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-startup-only')
        launched = launch_connected_session(tmp_path / 'connected-session', scope=scope,
            approved_scope_sha256=scope['scope_sha256'])
        assert launched['launch_attempts'] == 1 and launched['requested_mode'] == 'shadow'
        deadline = time.monotonic() + 5
        while connected_session_status(tmp_path / 'connected-session')['process_alive'] and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not connected_session_status(tmp_path / 'connected-session')['process_alive']
        assert Path(str(ledger) + '.sqlite').is_file(), 'normal installed console must construct its durable connected runtime'
        assert not effect.exists(), 'host hard block must prevent effects and provider attempt'
        current = connected_session_status(tmp_path / 'connected-session')
        duplicate = dict(scope, trusted_session_head=current['session_head_sha256'])
        duplicate['scope_sha256'] = digest({k: v for k, v in duplicate.items() if k != 'scope_sha256'})
        with pytest.raises(ConnectedDeliveryError, match='connected_launch_already_attempted'):
            launch_connected_session(tmp_path / 'connected-session', scope=duplicate,
                approved_scope_sha256=duplicate['scope_sha256'])
        stop_scope = dict(duplicate, action='stop')
        stop_scope['scope_sha256'] = digest({k: v for k, v in stop_scope.items() if k != 'scope_sha256'})
        stopped = stop_connected_session(tmp_path / 'connected-session', scope=stop_scope,
            approved_scope_sha256=stop_scope['scope_sha256'])
        assert stopped['stage'] == 'stopped' and not stopped['process_alive']
        plan_file = tmp_path / 'connected-session' / 'plan.json'
        original_plan = plan_file.read_bytes()
        altered_plan = json.loads(original_plan)
        altered_plan['reference_sha256']['REGISTERED_ALPHA_CONNECTED_REF'] = '0' * 64
        plan_file.write_text(json.dumps(altered_plan), encoding='utf-8')
        with pytest.raises(ConnectedDeliveryError, match='connected_session_plan_changed'):
            connected_session_status(tmp_path / 'connected-session')
        plan_file.write_bytes(original_plan)
        public.chmod(0o644)
        assert not connected_session_status(tmp_path / 'connected-session')['private_references_current']
        public.chmod(0o600)
        linked_public = tmp_path / 'linked-public.pem'
        os.link(public, linked_public)
        assert not connected_session_status(tmp_path / 'connected-session')['private_references_current']
        linked_public.unlink()
        linked_origin = tmp_path / 'linked-installed-host.py'
        os.link(report['origins']['host']['path'], linked_origin)
        assert not connected_session_status(tmp_path / 'connected-session')['installed_sources_current']
        linked_origin.unlink()
        assert connected_session_status(tmp_path / 'connected-session')['installed_sources_current']

        cert, cert_key = tmp_path / 'loopback.crt', tmp_path / 'loopback.key'
        generated = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-nodes', '-keyout', str(cert_key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
            '-addext', 'subjectAltName=IP:127.0.0.1', '-days', '1'],
            capture_output=True, timeout=20)
        assert generated.returncode == 0, 'local synthetic TLS fixture generation failed'
        cert.chmod(0o600); cert_key.chmod(0o600)
        calls = []
        response_mode = {'value': 'valid'}

        class SyntheticTypeSafe(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                request = json.loads(raw)
                calls.append({'path': self.path, 'request_sha256': hashlib.sha256(raw).hexdigest()})
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
                resolved_model = (request['model'] if response_mode['value'] == 'valid'
                                  else request['model'] + '-wrong')
                response = json.dumps({'model': resolved_model, 'answers': answers,
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
        try:
            config['endpoint'] = f'https://127.0.0.1:{server.server_port}/v1/systemone'
            config['environment_digest'] = digest({**{
                'python': str(Path(installed_receipt['installed']['python']).resolve()),
                'version': list(sys.version_info[:3]),
                'implementation': platform.python_implementation(),
                'openssl': ssl.OPENSSL_VERSION, 'credential_present': True},
                'cert_sha256': hashlib.sha256(cert.read_bytes()).hexdigest(),
                'signature_verifier': _verifier_identity(),
                'public_key_sha256': hashlib.sha256(public.read_bytes()).hexdigest()})
            grant['endpoint'] = config['endpoint']
            grant['environment_digest'] = config['environment_digest']
            grant['issued_at'] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            grant['expires_at'] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            manifest['ledger_path'] = str(tmp_path / 'loopback-runtime.ledger')
            manifest['signatures']['egress_grant'] = _issue(private, 'egress_grant', digest(grant))
            reference.write_text(json.dumps(manifest), encoding='utf-8')
            loop_ready, loop_release = tmp_path / 'loop-ready.bin', tmp_path / 'loop-release.bin'
            loop_effect, loop_audit = tmp_path / 'loop-effect.jsonl', tmp_path / 'loop-audit.jsonl'
            task_id = 'alpha-loopback-shadow'
            expected_effect = (json.dumps({'task_id': task_id, 'action': 'inspect',
                                           'item': 'fixture-one'}, sort_keys=True,
                                          separators=(',', ':')) + '\n').encode()
            loop_observation = {'schema_version': '1.0',
                'kind': 'template-delivery-observation-v1',
                'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                            'expected_sha256': hashlib.sha256(expected).hexdigest()}
                           for role, path, expected in (
                               ('ready', loop_ready, b'in-flight\n'),
                               ('entrypoint_reached', loop_ready, b'in-flight\n'),
                               ('integration_reachable', loop_effect, expected_effect),
                               ('outcome_verified', loop_effect, expected_effect))]}
            loop_plan = plan_connected_delivery(installed_plan,
                trusted_install_receipt_sha256=installed_receipt['receipt_sha256'],
                trusted_package_receipt_sha256=installed_plan['package_receipt']['receipt_sha256'],
                installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
                observation=loop_observation,
                launch_environment={'REGISTERED_ALPHA_CONNECTED_REF': str(reference),
                    'REGISTERED_ALPHA_AUTH_PUBKEY_FILE': str(public),
                    'REGISTERED_ALPHA_PERMIT': '1',
                    'REGISTERED_ALPHA_TASK_ID': task_id,
                    'REGISTERED_ALPHA_AUDIT': str(loop_audit),
                    'REGISTERED_ALPHA_EFFECTS': str(loop_effect),
                    'REGISTERED_ALPHA_HOLD': '1',
                    'REGISTERED_ALPHA_READY': str(loop_ready),
                    'REGISTERED_ALPHA_RELEASE': str(loop_release),
                    'SSL_CERT_FILE': str(cert)})
            loop_session = tmp_path / 'loopback-session'
            created = create_connected_session(loop_session, loop_plan,
                approved_plan_sha256=loop_plan['plan_sha256'])
            loop_scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
                'run_id': created['run_id'], 'plan_sha256': loop_plan['plan_sha256'],
                'public_key_sha256': loop_plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'],
                'trusted_session_head': created['session_head_sha256'], 'action': 'launch',
                'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
            loop_scope['scope_sha256'] = digest(loop_scope)
            launch_connected_session(loop_session, scope=loop_scope,
                approved_scope_sha256=loop_scope['scope_sha256'])
            deadline = time.monotonic() + 10
            while (not loop_ready.is_file() or loop_ready.read_bytes() != b'in-flight\n') and time.monotonic() < deadline:
                time.sleep(0.02)
            assert loop_ready.read_bytes() == b'in-flight\n'
            in_flight = connected_session_status(loop_session)
            assert in_flight['process_alive'] and in_flight['independent_checks']['ready']
            assert not in_flight['independent_checks']['outcome_verified']
            while len(calls) < 1 and time.monotonic() < deadline:
                time.sleep(0.02)
            assert len(calls) == 1, 'local synthetic response must arrive before host release'
            loop_release.write_bytes(b'go\n')
            while not loop_effect.is_file() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert loop_effect.read_bytes() == expected_effect
            result = connected_session_status(loop_session)
            assert result['independent_checks']['outcome_verified']
            assert result['provider_reachable'] is None and result['observed_benefit'] is None
            assert len(calls) == 1 and calls[0]['path'] == '/v1/systemone'
            # The effect is fsynced before console teardown releases the
            # exclusive shared ledger owner. A restart needs that release.
            shutdown_deadline = time.monotonic() + 20
            while result['process_alive'] and time.monotonic() < shutdown_deadline:
                time.sleep(0.02)
                result = connected_session_status(loop_session)
            assert result['process_alive'] is False

            # A malformed pinned-model response is a real client protocol
            # rejection. The same installed generation and ledger restart with
            # a new stable task; the host still executes only its baseline.
            response_mode['value'] = 'wrong_model'
            fault_task = 'alpha-wrong-model'
            fault_ready, fault_release = tmp_path / 'fault-ready.bin', tmp_path / 'fault-release.bin'
            fault_effect, fault_audit = tmp_path / 'fault-effect.jsonl', tmp_path / 'fault-audit.jsonl'
            fault_expected = (json.dumps({'task_id': fault_task, 'action': 'inspect',
                                          'item': 'fixture-one'}, sort_keys=True,
                                         separators=(',', ':')) + '\n').encode()
            fault_observation = {'schema_version': '1.0',
                'kind': 'template-delivery-observation-v1',
                'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                            'expected_sha256': hashlib.sha256(expected).hexdigest()}
                           for role, path, expected in (
                               ('ready', fault_ready, b'in-flight\n'),
                               ('entrypoint_reached', fault_ready, b'in-flight\n'),
                               ('integration_reachable', fault_effect, fault_expected),
                               ('outcome_verified', fault_effect, fault_expected))]}
            fault_environment = dict(loop_plan['off_provenance']['launch_environment'])
            fault_environment.update({'REGISTERED_ALPHA_TASK_ID': fault_task,
                'REGISTERED_ALPHA_AUDIT': str(fault_audit),
                'REGISTERED_ALPHA_EFFECTS': str(fault_effect),
                'REGISTERED_ALPHA_READY': str(fault_ready),
                'REGISTERED_ALPHA_RELEASE': str(fault_release)})
            fault_plan = plan_connected_delivery(installed_plan,
                trusted_install_receipt_sha256=installed_receipt['receipt_sha256'],
                trusted_package_receipt_sha256=installed_plan['package_receipt']['receipt_sha256'],
                installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
                observation=fault_observation, launch_environment=fault_environment)
            fault_session = tmp_path / 'wrong-model-session'
            fault_created = create_connected_session(fault_session, fault_plan,
                approved_plan_sha256=fault_plan['plan_sha256'])
            fault_scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
                'run_id': fault_created['run_id'], 'plan_sha256': fault_plan['plan_sha256'],
                'public_key_sha256': fault_plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'],
                'trusted_session_head': fault_created['session_head_sha256'], 'action': 'launch',
                'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
            fault_scope['scope_sha256'] = digest(fault_scope)
            launch_connected_session(fault_session, scope=fault_scope,
                approved_scope_sha256=fault_scope['scope_sha256'])
            deadline = time.monotonic() + 10
            while (not fault_ready.is_file() or fault_ready.read_bytes() != b'in-flight\n') and time.monotonic() < deadline:
                time.sleep(0.02)
            assert fault_ready.read_bytes() == b'in-flight\n'
            while len(calls) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            assert len(calls) == 2, 'malformed local response must arrive before host release'
            fault_release.write_bytes(b'go\n')
            while not fault_effect.is_file() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert fault_effect.read_bytes() == fault_expected
            assert len(calls) == 2 and calls[1]['path'] == '/v1/systemone'
            assert connected_session_status(fault_session)['independent_checks']['outcome_verified']
        finally:
            for name in ('loop_session', 'fault_session'):
                session = locals().get(name)
                if session is not None and session.exists():
                    current = connected_session_status(session)
                    if current['stage'] in ('running', 'stop_pending'):
                        final_scope = {'schema_version': '1.0',
                            'kind': 'connected-delivery-scope-v1', 'run_id': current['run_id'],
                            'plan_sha256': current['plan_sha256'],
                            'public_key_sha256': (loop_plan if name == 'loop_session' else fault_plan)
                                ['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'],
                            'trusted_session_head': current['session_head_sha256'],
                            'action': 'stop',
                            'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
                        final_scope['scope_sha256'] = digest(final_scope)
                        stopped = stop_connected_session(session, scope=final_scope,
                            approved_scope_sha256=final_scope['scope_sha256'])
                        assert not stopped['process_alive']
            server.shutdown(); server.server_close(); thread.join(timeout=2)


# Installed Alpha connected fault schedules (issue #57, acceptance criterion 4).
# Everything below is offline synthetic local-TLS evidence against a loopback
# server. It makes no provider request and establishes no provider operation,
# canary/active eligibility or benefit.

def _alpha_effect(task_id: str) -> bytes:
    """The independently authored baseline effect line for one Alpha task."""
    return (json.dumps({'task_id': task_id, 'action': 'inspect', 'item': 'fixture-one'},
                       sort_keys=True, separators=(',', ':')) + '\n').encode()


def _alpha_scope(current: dict, plan: dict, action: str) -> dict:
    scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
             'run_id': current['run_id'], 'plan_sha256': plan['plan_sha256'],
             'public_key_sha256': plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'],
             'trusted_session_head': current['session_head_sha256'], 'action': action,
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
    scope['scope_sha256'] = digest(scope)
    return scope


def _alpha_ledger(path: Path) -> tuple[dict, list]:
    """Read the durable ledger rows through a separate read-only connection.

    Call this only while the owner is quiescent: held at the host's in-flight
    point after its last audit record, or exited. The owner commits with a
    zero busy timeout, so a reader's shared lock during a commit would make
    that commit fail closed and change the schedule under test.
    """
    database = Path(str(path) + '.sqlite')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        row = db.execute('SELECT payload FROM state WHERE id=1').fetchone()
        effects = [list(item) for item in db.execute(
            'SELECT identity,status FROM effects ORDER BY identity')]
    return json.loads(row[0]), effects


def _alpha_journal(session: Path) -> list[dict]:
    return [json.loads(line) for line in
            (session / 'events.jsonl').read_text(encoding='utf-8').splitlines()]


def _alpha_audit(path: Path) -> list[str]:
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert all(set(row) == {'record_sha256'} for row in rows)
    return [row['record_sha256'] for row in rows]


def _alpha_live_group(pid: int) -> list[int]:
    """Live processes in the supervised child's own session or process group."""
    live = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / 'stat').read_text(encoding='ascii', errors='replace')
        except OSError:
            continue
        fields = raw[raw.rfind(')') + 2:].split()  # state, ppid, pgrp, session, ...
        if fields[0] not in ('Z', 'X', 'x') and str(pid) in (entry.name, fields[2], fields[3]):
            live.append(int(entry.name))
    return live


def _alpha_wait(predicate, seconds: float, message: str):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError(message)


@pytest.fixture(scope='module')
def alpha_connected_faults(tmp_path_factory):
    """One installed Alpha 1.0.2 connected host and one loopback TLS server."""
    wheelhouse = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
            and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)
            and wheelhouse and Path(wheelhouse).is_dir()):
        pytest.skip('requires Linux CPython 3.13 and reviewed offline wheelhouse')
    tmp_path = tmp_path_factory.mktemp('alpha-connected-faults')
    source = Path(__file__).resolve().parent / 'independent_hosts/registered_alpha/installed_journey.py'
    module_spec = importlib.util.spec_from_file_location('alpha_connected_fault_driver', source)
    driver = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(driver)
    driver.ROOT = Path(__file__).resolve().parent / 'independent_hosts/registered_alpha_connected'
    actual_install = installer.install_package
    observed = {}

    def inspect_on_install(plan, **kwargs):
        receipt = actual_install(plan, **kwargs)
        observed['report'] = derive_installed_binding(
            plan['package_plan'], plan['package_receipt'], plan, receipt,
            trusted_package_receipt_sha256=plan['package_receipt']['receipt_sha256'],
            trusted_install_receipt_sha256=receipt['receipt_sha256'])
        observed['install_plan'], observed['install_receipt'] = plan, receipt
        raise _InstalledCheckpoint

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(installer, 'install_package', inspect_on_install)
        with pytest.raises(_InstalledCheckpoint):
            driver.run_offline(tmp_path / 'run', Path(wheelhouse), tmp_path / 'anchors')
    report = observed['report']
    install_plan, install_receipt = observed['install_plan'], observed['install_receipt']
    adapter_tree = ast.parse(Path(report['origins']['adapter']['path']).read_text())
    adapter_spec = ast.literal_eval(next(node.value for node in adapter_tree.body
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'SPEC' for target in node.targets)))
    site = Path(report['site']) / 'registered_alpha'
    dependency = {'files': [{'path': str(site / name), 'sha256': file_hash(site / name)}
                            for name in ('requirements.lock', 'runtime.json')]}
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
              'max_total_calls': 2, 'max_total_cost': 2,
              'max_in_flight': 1, 'max_tasks': 2}
    source_bindings = {report['candidate_id']: {
        'reviewed_file_sha256': report['reviewed_file_sha256'],
        'applied_file_sha256': report['applied_file_sha256'],
        'adapter_path': report['origins']['adapter']['wheel_member'],
        'adapter_sha256': report['origins']['adapter']['sha256']}}
    private, public = _issuer(tmp_path)
    cert, cert_key = tmp_path / 'loopback.crt', tmp_path / 'loopback.key'
    generated = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-nodes', '-keyout', str(cert_key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
        '-addext', 'subjectAltName=IP:127.0.0.1', '-days', '1'],
        capture_output=True, timeout=20)
    assert generated.returncode == 0, 'local synthetic TLS fixture generation failed'
    cert.chmod(0o600); cert_key.chmod(0o600)
    calls: list[dict] = []
    answered: list[int] = []
    control = {'mode': 'valid'}
    release_response = Event()

    class SyntheticTypeSafe(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            request = json.loads(raw)
            index = len(calls)
            # The body is the synthetic fixture request; no header is retained.
            calls.append({'path': self.path, 'request': request,
                          'received': time.monotonic()})
            if control['mode'] == 'hold':
                # Bounded: the test releases this after its read-back, and the
                # fixture teardown releases it unconditionally.
                release_response.wait(timeout=45)
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
            response = json.dumps({'model': request['model'], 'answers': answers,
                                   'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
            except (OSError, ssl.SSLError):
                return  # The client already timed out or was stopped.
            answered.append(index)

    server = ThreadingHTTPServer(('127.0.0.1', 0), SyntheticTypeSafe)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(cert_key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f'https://127.0.0.1:{server.server_port}/v1/systemone'
    environment_digest = digest({
        'python': str(Path(install_receipt['installed']['python']).resolve()),
        'version': list(sys.version_info[:3]),
        'implementation': platform.python_implementation(),
        'openssl': ssl.OPENSSL_VERSION,
        'cert_sha256': file_hash(cert),
        'signature_verifier': _verifier_identity(),
        'public_key_sha256': file_hash(public),
        'credential_present': True})
    source_identity = {'root': report['site'], 'plan': report['source_plan'],
                       'bindings': source_bindings,
                       'installed_binding_sha256': report['binding_sha256']}
    active: list[tuple[Path, dict]] = []
    provenance = {'candidate_id': adapter_spec['candidate_id'],
                  'experiment_id': adapter_spec['experiment_id'],
                  'source_location': {key: adapter_spec['source'][key]
                                      for key in ('file', 'symbol', 'source_sha256')}}

    def schedule(label: str, *, task_id: str, ledger: Path | None = None,
                 effect: Path | None = None, hold: str = '1',
                 credential_ref: str = 'env:TYPESAFE_API_KEY') -> SimpleNamespace:
        folder = tmp_path / ('faults-' + label)
        folder.mkdir(mode=0o700)
        ready, release = folder / 'ready.bin', folder / 'release.bin'
        audit, reference = folder / 'audit.jsonl', folder / 'connected-ref.json'
        effect = effect or folder / 'effect.jsonl'
        ledger = ledger or folder / 'runtime.ledger'
        before = effect.read_bytes() if effect.exists() else None
        # The only transition this session may produce is one appended baseline
        # line for its task. For a replayed task that line would be a duplicate.
        expected = (before or b'') + _alpha_effect(task_id)
        config = {'endpoint': endpoint, 'credential_ref': credential_ref,
                  'model': 'jev-1.13.0', 'environment_digest': environment_digest,
                  'source_root': report['site'], 'source_plan': report['source_plan'],
                  'source_bindings': source_bindings, 'installed_binding': report}
        now = datetime.now(timezone.utc)
        grant = {'endpoint': endpoint, 'credential_ref': credential_ref,
                 'model': config['model'], 'environment_digest': environment_digest,
                 'source_digest': digest(source_identity),
                 'dependency_digest': digest(dependency), 'budget_digest': digest(limits),
                 'adapters_digest': digest({report['candidate_id']: digest(adapter_spec)}),
                 'mode': 'shadow', 'issued_at': (now - timedelta(minutes=1)).isoformat(),
                 'expires_at': (now + timedelta(minutes=5)).isoformat()}
        manifest = {'schema_version': '1.0', 'mode': 'shadow', 'connected_config': config,
                    'authority': {'egress_grant': grant, 'activation': None},
                    'ledger_path': str(ledger),
                    'signatures': {
                        'installed_binding': _issue(private, 'installed_binding',
                                                    report['binding_sha256']),
                        'egress_grant': _issue(private, 'egress_grant', digest(grant))}}
        reference.write_text(json.dumps(manifest), encoding='utf-8')
        reference.chmod(0o600)
        observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
            'checks': [{'role': role, 'path': str(path), 'before_sha256': prior,
                        'expected_sha256': hashlib.sha256(value).hexdigest()}
                       for role, path, prior, value in (
                           ('ready', ready, None, b'in-flight\n'),
                           ('entrypoint_reached', ready, None, b'in-flight\n'),
                           ('integration_reachable', effect,
                            None if before is None else hashlib.sha256(before).hexdigest(),
                            expected),
                           ('outcome_verified', effect,
                            None if before is None else hashlib.sha256(before).hexdigest(),
                            expected))]}
        plan = plan_connected_delivery(install_plan,
            trusted_install_receipt_sha256=install_receipt['receipt_sha256'],
            trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
            installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
            observation=observation,
            launch_environment={'REGISTERED_ALPHA_CONNECTED_REF': str(reference),
                                'REGISTERED_ALPHA_AUTH_PUBKEY_FILE': str(public),
                                'REGISTERED_ALPHA_PERMIT': '1',
                                'REGISTERED_ALPHA_TASK_ID': task_id,
                                'REGISTERED_ALPHA_AUDIT': str(audit),
                                'REGISTERED_ALPHA_EFFECTS': str(effect),
                                'REGISTERED_ALPHA_HOLD': hold,
                                'REGISTERED_ALPHA_READY': str(ready),
                                'REGISTERED_ALPHA_RELEASE': str(release),
                                'SSL_CERT_FILE': str(cert)})
        session = folder / 'session'
        created = create_connected_session(session, plan,
                                           approved_plan_sha256=plan['plan_sha256'])
        active.append((session, plan))
        return SimpleNamespace(task_id=task_id, folder=folder, ready=ready, release=release,
                               audit=audit, reference=reference, effect=effect, ledger=ledger,
                               before=before, expected=expected, plan=plan, session=session,
                               created=created,
                               launch_scope=_alpha_scope(created, plan, 'launch'))

    def launch(run: SimpleNamespace) -> dict:
        launched = launch_connected_session(run.session, scope=run.launch_scope,
            approved_scope_sha256=run.launch_scope['scope_sha256'])
        assert launched['launch_attempts'] == 1 and launched['requested_mode'] == 'shadow'
        return launched

    def wait_exit(run: SimpleNamespace, seconds: float = 30) -> dict:
        _alpha_wait(lambda: not connected_session_status(run.session)['process_alive'],
                    seconds, 'installed Alpha console did not exit within its bound')
        return connected_session_status(run.session)

    def stop(run: SimpleNamespace, current: dict | None = None) -> dict:
        current = current or connected_session_status(run.session)
        scope = _alpha_scope(current, run.plan, 'stop')
        result = stop_connected_session(run.session, scope=scope,
                                        approved_scope_sha256=scope['scope_sha256'])
        deadline = time.monotonic() + 10
        while result['stage'] != 'stopped' and time.monotonic() < deadline:
            time.sleep(0.05)
            result = resume_connected_session(
                run.session, trusted_session_head=result['session_head_sha256'])
        return result

    def audit_hash(record: dict) -> str:
        # The reviewed Alpha console stores only this hash of each audit record.
        serialized = json.dumps({**record, 'evidence_type': 'observed'},
                                sort_keys=True, default=str).encode('utf-8')
        return hashlib.sha256(serialized).hexdigest()

    def comparison_hash(task_id: str, proposed: str, reason: str) -> str:
        return audit_hash({**provenance, 'type': 'shadow_comparison',
                           'task_id_hash': digest(task_id), 'baseline': 'inspect',
                           'proposed': proposed, 'reason': reason,
                           'agreement': proposed == 'inspect',
                           'counterfactual_outcome': 'unknown; not a rescue/regression'})

    def error_hash(task_id: str, request: dict, error_class: str) -> str:
        request_hash = digest({
            'ordered_request': request_fingerprint(request['state'], request['questions'],
                                                   request['model']),
            'policy_version': adapter_spec['runtime']['policy_version'],
            'allowed_actions': ['inspect', 'summarize'], 'scope': None,
            'label_actions': adapter_spec['label_actions']})
        return audit_hash({**provenance, 'type': 'assessment_error',
                           'task_id_hash': digest(task_id), 'request_hash': request_hash,
                           'error_class': error_class, 'mode': 'shadow'})

    def settled(task_ids: list[str], calls_per_task: dict[str, int], *,
                closed: bool = True) -> dict:
        """The documented durable state after settled, nonrefundable reservations."""
        bound = float(adapter_spec['runtime']['cost_upper_bound'])
        return {'limits': limits, 'inflight': {},
                'calls': sum(calls_per_task.values()),
                'cost': bound * sum(calls_per_task.values()),
                'revoked': False, 'overruns': 0,
                'tasks': {digest(task): {'calls': calls_per_task[task],
                                         'reserved_cost': bound * calls_per_task[task],
                                         'closed': closed} for task in task_ids}}

    def accounting(state: dict) -> dict:
        assert set(state) == {'identity', 'ledger_path', 'limits', 'tasks', 'inflight',
                              'calls', 'cost', 'revoked', 'overruns'}
        return {key: value for key, value in state.items()
                if key not in ('identity', 'ledger_path')}

    host = SimpleNamespace(schedule=schedule, launch=launch, wait_exit=wait_exit, stop=stop,
                           calls=calls, answered=answered, control=control,
                           release_response=release_response, adapter_spec=adapter_spec,
                           public=public, comparison_hash=comparison_hash,
                           error_hash=error_hash, settled=settled, accounting=accounting)
    try:
        yield host
    finally:
        release_response.set()
        for session, plan in active:
            if session.exists():
                current = connected_session_status(session)
                if current['process_alive'] and current['stage'] in ('running', 'stop_pending'):
                    scope = _alpha_scope(current, plan, 'stop')
                    stop_connected_session(session, scope=scope,
                                           approved_scope_sha256=scope['scope_sha256'])
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def _alpha_reach_hold(host, run, prior_calls: int) -> None:
    """Drive one launched session to its host-owned in-flight point."""
    _alpha_wait(lambda: run.ready.is_file() and run.ready.read_bytes() == b'in-flight\n',
                20, 'installed Alpha console did not reach its in-flight point')
    _alpha_wait(lambda: len(host.calls) == prior_calls + 1, 10,
                'local synthetic request did not arrive before host release')
    assert host.calls[-1]['path'] == '/v1/systemone'
    assert host.calls[-1]['request']['questions'] == host.adapter_spec['questions']
    assert host.calls[-1]['request']['state'] == {'item_kind': 'fixture', 'intent': 'inspect'}
    assert host.calls[-1]['request']['model'] == 'jev-1.13.0'


def _alpha_release_valid(host, run, prior_calls: int) -> dict:
    """Finish a held valid-response session; return its final durable state."""
    _alpha_reach_hold(host, run, prior_calls)
    # The worker settles its reservation, then appends the assessment and the
    # comparison. Both records are awaited before the single ledger read and
    # before the host is allowed to commit its effect.
    _alpha_wait(lambda: len(_alpha_audit(run.audit)) == 2, 15,
                'assessment and comparison audit records missing')
    assert not _alpha_ledger(run.ledger)[0]['inflight']
    # The synthetic response proposes summarize with full confidence. Shadow
    # records the disagreement and the host still commits only its baseline.
    assert _alpha_audit(run.audit)[1] == host.comparison_hash(
        run.task_id, 'summarize', 'bounded_proposal_not_execution_authorization')
    assert (run.effect.read_bytes() if run.effect.exists() else None) == run.before
    run.release.write_bytes(b'go\n')
    _alpha_wait(lambda: run.effect.is_file() and run.effect.read_bytes() == run.expected,
                20, 'independent Alpha baseline effect missing')
    finished = host.wait_exit(run)
    assert finished['independent_checks']['outcome_verified']
    assert finished['provider_reachable'] is None and finished['observed_benefit'] is None
    assert len(host.calls) == prior_calls + 1
    assert len(_alpha_audit(run.audit)) == 2
    return finished


def test_alpha_installed_connected_actual_provider_timeout(alpha_connected_faults, monkeypatch):
    host = alpha_connected_faults
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')
    timeout_s = host.adapter_spec['runtime']['configuration']['timeout_ms'] / 1000
    assert timeout_s == 2.0
    task = 'alpha-actual-timeout'
    run = host.schedule('actual-timeout', task_id=task)
    prior_calls, prior_answered = len(host.calls), len(host.answered)
    host.release_response.clear()
    host.control['mode'] = 'hold'
    try:
        host.launch(run)
        _alpha_reach_hold(host, run, prior_calls)
        held = connected_session_status(run.session)
        assert held['process_alive'] and held['independent_checks']['ready']
        assert not held['independent_checks']['outcome_verified']
        # The reservation is committed before provider I/O and is settled only
        # when the adapter's fixed transport timeout fires; the error and the
        # comparison records follow that settlement. The server is still
        # withholding its response at that point.
        _alpha_wait(lambda: len(_alpha_audit(run.audit)) == 2, 15,
                    'timeout audit records missing')
        waited = time.monotonic() - host.calls[-1]['received']
        # Not exact: the server timestamp follows the client's completed send,
        # so the client read timeout may have started marginally earlier.
        assert waited >= timeout_s - 0.5
        assert len(host.answered) == prior_answered
        assert _alpha_audit(run.audit) == [
            host.error_hash(task, host.calls[-1]['request'], 'EvaluationTimeoutError'),
            host.comparison_hash(task, 'inspect', 'evaluation_or_audit_failure')]
        assert host.accounting(_alpha_ledger(run.ledger)[0]) == host.settled(
            [task], {task: 1}, closed=False)
        assert not run.effect.exists()
        run.release.write_bytes(b'go\n')
        _alpha_wait(lambda: run.effect.is_file() and run.effect.read_bytes() == run.expected,
                    20, 'independent Alpha baseline effect missing after timeout')
        finished = host.wait_exit(run)
        # The withheld response was never sent while the console was alive.
        assert len(host.answered) == prior_answered
    finally:
        host.release_response.set()
        host.control['mode'] = 'valid'
    assert finished['independent_checks']['outcome_verified']
    assert finished['provider_reachable'] is None and finished['observed_benefit'] is None
    assert run.effect.read_bytes() == _alpha_effect(task)
    assert len(host.calls) == prior_calls + 1
    assert len(_alpha_audit(run.audit)) == 2
    state, effects = _alpha_ledger(run.ledger)
    # One nonrefundable call for the timed-out request and a closed task. The
    # effect journal is empty because shadow runs the original baseline itself
    # and claims no connected effect.
    assert host.accounting(state) == host.settled([task], {task: 1})
    assert effects == []
    assert host.stop(run)['stage'] == 'stopped'
    assert run.effect.read_bytes() == _alpha_effect(task)


def test_alpha_installed_connected_stop_during_held_response(alpha_connected_faults, monkeypatch):
    host = alpha_connected_faults
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')
    timeout_s = host.adapter_spec['runtime']['configuration']['timeout_ms'] / 1000
    task = 'alpha-stop-in-flight'
    run = host.schedule('stop-in-flight', task_id=task)
    prior_calls, prior_answered = len(host.calls), len(host.answered)
    host.release_response.clear()
    host.control['mode'] = 'hold'
    try:
        launched = host.launch(run)
        _alpha_reach_hold(host, run, prior_calls)
        # The launch result already carries the current head, so the stop is
        # delivered while the provider response is still withheld.
        stopped = host.stop(run, launched)
        dead_after = time.monotonic() - host.calls[-1]['received']
        assert stopped['stage'] == 'stopped' and not stopped['process_alive']
        # This schedule is only the in-flight one when the owned process was
        # gone before the adapter timeout could settle the reservation.
        assert dead_after < timeout_s, 'stop was not delivered inside the adapter timeout window'
        assert len(host.answered) == prior_answered
        journal = _alpha_journal(run.session)
        assert [row['event'] for row in journal] == [
            'created', 'launch_pending', 'launched', 'running', 'stop_pending', 'stopped']
        pid = journal[-1]['state']['process']['pid']
        assert _alpha_live_group(pid) == []
        # Not success-shaped: the host was stopped before its commit.
        assert stopped['independent_checks'] == {
            'ready': True, 'entrypoint_reached': True,
            'integration_reachable': False, 'outcome_verified': False}
        assert stopped['pending'] is None and stopped['launch_attempts'] == 1
        assert not run.effect.exists()
        assert _alpha_audit(run.audit) == []
        state, effects = _alpha_ledger(run.ledger)
        # The call was charged and its reservation is still unresolved: a
        # terminated owner can neither settle it nor close the task.
        unresolved = host.settled([task], {task: 1}, closed=False)
        bound = float(host.adapter_spec['runtime']['cost_upper_bound'])
        assert list(state['inflight'].values()) == [[digest(task), bound]]
        assert {**host.accounting(state), 'inflight': {}} == unresolved
        assert effects == []
        database = Path(str(run.ledger) + '.sqlite').read_bytes()
    finally:
        host.release_response.set()
        host.control['mode'] = 'valid'
    # The stopped session cannot be launched again.
    current = connected_session_status(run.session)
    again = _alpha_scope(current, run.plan, 'launch')
    with pytest.raises(ConnectedDeliveryError, match='connected_launch_already_attempted'):
        launch_connected_session(run.session, scope=again,
                                 approved_scope_sha256=again['scope_sha256'])
    # A new session for the same task and ledger starts the normal console,
    # which refuses the unresolved history at startup: no provider request,
    # no effect and no change to the durable rows.
    replay = host.schedule('stop-in-flight-restart', task_id=task, ledger=run.ledger,
                           effect=run.effect, hold='0')
    host.launch(replay)
    finished = host.wait_exit(replay)
    assert finished['independent_checks'] == {
        'ready': False, 'entrypoint_reached': False,
        'integration_reachable': False, 'outcome_verified': False}
    assert not run.effect.exists() and not replay.ready.exists()
    assert _alpha_audit(replay.audit) == []
    assert len(host.calls) == prior_calls + 1
    assert Path(str(run.ledger) + '.sqlite').read_bytes() == database
    assert _alpha_ledger(run.ledger) == (state, effects)
    assert host.stop(replay)['stage'] == 'stopped'


def test_alpha_installed_connected_missing_secret_and_reference(alpha_connected_faults, monkeypatch):
    host = alpha_connected_faults
    task = 'alpha-prerequisites'
    run = host.schedule('prerequisites', task_id=task)
    prior_calls = len(host.calls)

    def untouched() -> dict:
        """Nothing was attempted: no intent, process, request, ledger or effect."""
        current = connected_session_status(run.session)
        assert [row['event'] for row in _alpha_journal(run.session)] == ['created']
        assert current['session_head_sha256'] == run.created['session_head_sha256']
        assert current['stage'] == 'installed' and current['launch_attempts'] == 0
        assert current['pending'] is None and not current['process_alive']
        assert not any(current['independent_checks'].values())
        assert len(host.calls) == prior_calls
        for path in (run.effect, run.ready, run.release, run.audit, run.ledger,
                     Path(str(run.ledger) + '.sqlite')):
            assert not path.exists()
        return current

    def refused(code: str) -> None:
        with pytest.raises(ConnectedDeliveryError, match=code):
            launch_connected_session(run.session, scope=run.launch_scope,
                                     approved_scope_sha256=run.launch_scope['scope_sha256'])

    # Missing secret: the credential is required at launch, before the durable
    # launch intent. Absent and empty values are both refused.
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    refused('connected_credential_unavailable')
    untouched()
    monkeypatch.setenv('TYPESAFE_API_KEY', '')
    refused('connected_credential_unavailable')
    untouched()
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')
    # Missing prerequisite: each owner-private reference file is absent in
    # turn while the credential is present.
    for path in (run.reference, host.public):
        aside = path.with_name(path.name + '.absent')
        path.rename(aside)
        try:
            refused('connected_private_reference_invalid')
            assert not untouched()['private_references_current']
        finally:
            aside.rename(path)
        assert untouched()['private_references_current']
    # The refusals consumed nothing: the unchanged launch scope still starts
    # the same session once the prerequisites are back.
    host.launch(run)
    _alpha_release_valid(host, run, prior_calls)
    assert run.effect.read_bytes() == _alpha_effect(task)
    state, effects = _alpha_ledger(run.ledger)
    assert host.accounting(state) == host.settled([task], {task: 1})
    assert effects == []
    assert host.stop(run)['stage'] == 'stopped'

    # Unresolvable secret reference: an otherwise identical, correctly signed
    # owner reference names a credential source the runtime does not register.
    # The supervisor launches the normal console, whose connected startup
    # refuses it before a ledger, provider request or host effect exists.
    other = host.schedule('unresolvable-credential', task_id='alpha-unresolvable',
                          credential_ref='env:REGISTERED_ALPHA_UNREGISTERED')
    host.launch(other)
    finished = host.wait_exit(other)
    assert not any(finished['independent_checks'].values())
    assert finished['private_references_current'] and finished['installed_sources_current']
    assert len(host.calls) == prior_calls + 1
    assert sorted(path.name for path in other.folder.iterdir()) == [
        'connected-ref.json', 'session']
    current = connected_session_status(other.session)
    again = _alpha_scope(current, other.plan, 'launch')
    with pytest.raises(ConnectedDeliveryError, match='connected_launch_already_attempted'):
        launch_connected_session(other.session, scope=again,
                                 approved_scope_sha256=again['scope_sha256'])
    assert host.stop(other)['stage'] == 'stopped'
    assert not other.effect.exists() and len(host.calls) == prior_calls + 1


def test_alpha_installed_connected_repeat_execution(alpha_connected_faults, monkeypatch):
    host = alpha_connected_faults
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')
    task = 'alpha-repeat'
    run = host.schedule('repeat', task_id=task)
    prior_calls = len(host.calls)
    host.launch(run)
    _alpha_release_valid(host, run, prior_calls)
    first_line = _alpha_effect(task)
    assert run.effect.read_bytes() == first_line
    state, effects = _alpha_ledger(run.ledger)
    assert host.accounting(state) == host.settled([task], {task: 1})
    assert effects == []
    database = Path(str(run.ledger) + '.sqlite').read_bytes()
    journal = _alpha_journal(run.session)
    assert [row['event'] for row in journal] == [
        'created', 'launch_pending', 'launched', 'running']

    def unchanged() -> None:
        assert _alpha_journal(run.session) == journal
        assert run.effect.read_bytes() == first_line
        assert len(host.calls) == prior_calls + 1
        assert Path(str(run.ledger) + '.sqlite').read_bytes() == database
        assert len(_alpha_audit(run.audit)) == 2

    # A second launch attempt of the same session: the consumed scope no
    # longer names the current head, and a fresh exact scope is still refused.
    with pytest.raises(ConnectedDeliveryError, match='exact_expiring_connected_scope_required'):
        launch_connected_session(run.session, scope=run.launch_scope,
                                 approved_scope_sha256=run.launch_scope['scope_sha256'])
    unchanged()
    current = connected_session_status(run.session)
    again = _alpha_scope(current, run.plan, 'launch')
    with pytest.raises(ConnectedDeliveryError, match='connected_launch_already_attempted'):
        launch_connected_session(run.session, scope=again,
                                 approved_scope_sha256=again['scope_sha256'])
    unchanged()
    resumed = resume_connected_session(run.session,
                                       trusted_session_head=current['session_head_sha256'])
    assert resumed['launch_attempts'] == 1 and resumed['stage'] == 'running'
    unchanged()
    stopped = host.stop(run)
    assert stopped['stage'] == 'stopped' and stopped['launch_attempts'] == 1
    again = _alpha_scope(stopped, run.plan, 'launch')
    with pytest.raises(ConnectedDeliveryError, match='connected_launch_already_attempted'):
        launch_connected_session(run.session, scope=again,
                                 approved_scope_sha256=again['scope_sha256'])
    assert run.effect.read_bytes() == first_line and len(host.calls) == prior_calls + 1

    # A second run of the same task ID is a new session on the same durable
    # ledger and effect file. The closed task is refused before any reservation,
    # so there is no provider request, no audit record and no second effect.
    replay = host.schedule('repeat-same-task', task_id=task, ledger=run.ledger,
                           effect=run.effect, hold='0')
    assert replay.before == first_line and replay.expected == first_line * 2
    host.launch(replay)
    finished = host.wait_exit(replay)
    assert not any(finished['independent_checks'].values())
    assert run.effect.read_bytes() == first_line
    assert not replay.ready.exists() and _alpha_audit(replay.audit) == []
    assert len(host.calls) == prior_calls + 1
    # Charges are retained, not reset and not incremented.
    assert _alpha_ledger(run.ledger) == (state, effects)
    assert host.stop(replay)['stage'] == 'stopped'

    # A later, different task on the same ledger adds to the retained charge.
    next_task = 'alpha-repeat-next'
    following = host.schedule('repeat-next-task', task_id=next_task, ledger=run.ledger,
                              effect=run.effect)
    host.launch(following)
    _alpha_release_valid(host, following, prior_calls + 1)
    assert run.effect.read_bytes() == first_line + _alpha_effect(next_task)
    next_state, next_effects = _alpha_ledger(run.ledger)
    assert next_state['identity'] == state['identity']
    assert host.accounting(next_state) == host.settled(
        [task, next_task], {task: 1, next_task: 1})
    assert next_effects == []
    assert host.stop(following)['stage'] == 'stopped'
    assert len(host.calls) == prior_calls + 2
