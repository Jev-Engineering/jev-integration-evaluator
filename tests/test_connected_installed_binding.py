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
import ssl
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator.template_connected_delivery import (
    ConnectedDeliveryError, plan_connected_delivery, create_connected_session,
    launch_connected_session, connected_session_status, stop_connected_session)
from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
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
