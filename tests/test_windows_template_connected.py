"""Installed native Windows connected shadow, with a separate synthetic issuer."""
from __future__ import annotations

import ast
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
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
import jsonschema

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.template_catalog import materialize_template, prepare_template_binding
from jev_integration_evaluator.integrations.lifecycle import apply_implementation, plan_implementation
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.windows_template_plan import (
    plan_windows_template_package, build_windows_template_package,
)
from jev_integration_evaluator.windows_template_install import (
    plan_windows_template_install, install_windows_template_package,
)
from jev_integration_evaluator.windows_template_connected_binding import (
    current_origin, derive_windows_installed_binding,
)
from jev_integration_evaluator.windows_template_connected_delivery import (
    WindowsConnectedDeliveryError, _reference, plan_windows_connected_delivery,
    create_windows_connected_session, launch_windows_connected_session,
    windows_connected_session_status, observe_windows_connected_session,
    stop_windows_connected_session,
)
from jev_integration_evaluator.windows_connected_verify import cng_identity
from jev_integration_evaluator.windows_template_owned import (
    create_private_directory, write_private_bytes_exclusive,
    write_private_json_exclusive,
)
from jev_integration_evaluator import windows_template_session as native_session


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
_ISSUER = Path(r'C:\Program Files\Git\usr\bin\openssl.exe')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _installed_connected_cli(installed: dict, cwd: Path, *args: str,
                             synthetic_credential: str | None = None) -> dict:
    """Run the installed evaluator console outside source with a clean off env."""
    python = Path(installed['installed']['python'])
    executable = python.parent / 'jev-integration-evaluator.exe'
    assert executable.is_file(), 'Installed evaluator console is required'
    env = native_session._environment(cwd, python, {})
    for name in ('PROCESSOR_ARCHITECTURE', 'PROCESSOR_ARCHITEW6432'):
        if name in os.environ:
            env[name] = os.environ[name]
    if synthetic_credential is not None:
        env['TYPESAFE_API_KEY'] = synthetic_credential
    result = subprocess.run([str(executable), 'windows-connected', *args],
                            cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=600,
                            check=False)
    assert result.returncode == 0, 'Installed connected CLI stage failed'
    return json.loads(result.stdout)


def _cli_input(owner: dict, name: str, value: dict) -> str:
    write_private_json_exclusive(owner, name, value)
    return str(Path(owner['path']) / name)


def _issued_key(tmp_path: Path) -> tuple[Path, bytes]:
    assert _ISSUER.is_file(), 'Declared synthetic issuer unavailable'
    private, public = tmp_path / 'issuer-private.pem', tmp_path / 'issuer-public.pem'
    for command in ([str(_ISSUER), 'genpkey', '-algorithm', 'EC',
                     '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', str(private)],
                    [str(_ISSUER), 'pkey', '-in', str(private), '-pubout', '-out', str(public)]):
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=10, check=False)
        assert result.returncode == 0
    return private, public.read_bytes()


def _issue(private: Path, kind: str, exact: str) -> str:
    result = subprocess.run([str(_ISSUER), 'dgst', '-sha256', '-sign', str(private)],
                            input=(kind + ':' + exact).encode('ascii'),
                            capture_output=True, timeout=10, check=False)
    assert result.returncode == 0
    return base64.b64encode(result.stdout).decode('ascii')


def _installed(tmp_path: Path, wheelhouse: Path) -> tuple[dict, dict, dict, dict]:
    fixture = Path(__file__).parent / 'independent_hosts/registered_alpha_connected_windows'
    target = tmp_path / 'host'
    shutil.copytree(fixture, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    source = target / 'qualification.py'
    module_spec = importlib.util.spec_from_file_location('alpha_windows_qualification', source)
    qualification = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(qualification)
    request, console_binding = qualification.source_matched_request(target)
    prepared = prepare_template_binding(target, request, console_binding)
    spec = prepared['request']['implementation_spec']
    template = tmp_path / 'template'
    materialize_template(target, prepared['request'], template)
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, request['reviewed_inventory'],
                                  spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed', (
        baseline['passed_cases'], baseline['file_identity_valid'],
        [(row['status'], row.get('diagnostic'),
          None if row.get('observation') is None else row['observation']['outcome']['exception'],
          None if row.get('observation') is None else row['observation']['network_attempts_denied'],
          None if row.get('observation') is None else row['observation']['calls']) for row in
         json.loads(Path(baseline['receipt_path']).read_text())['results']])
    apply_implementation(target, bundle, planned['bundle_digest'],
                         baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified', (
        modified['passed_cases'], modified['file_identity_valid'],
        [(row['mode'], row['status'], row['assertions'],
          None if row['observation'] is None else row['observation']['network_attempts_denied'])
         for row in json.loads(Path(modified['receipt_path']).read_text())['results']])
    sources = {p.relative_to(target).as_posix(): _sha(p) for p in target.rglob('*')
               if p.is_file() and not any(part in {'__pycache__', 'build', 'dist'}
                                          for part in p.relative_to(target).parts)}
    wheels = {p.name: _sha(p) for p in wheelhouse.glob('*.whl')}
    output, environments = tmp_path / 'packages', tmp_path / 'environments'
    output.mkdir(); environments.mkdir()
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    package_request = {'host_root': str(target), 'reviewed_source_files': sources,
                       'implementation_bundle': str(bundle),
                       'trusted_modified_receipt_sha256': modified['receipt_sha256'],
                       'template_directory': str(template), 'wheelhouse': str(wheelhouse),
                       'reviewed_wheels': wheels, 'output_parent': str(output),
                       'environment_parent': str(environments),
                       'console_script': console_binding['script'],
                       'interpreter': sys.executable, 'configuration': config,
                       'reviewed_configuration_sha256': digest(config)}
    package_plan = plan_windows_template_package(package_request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    report = derive_windows_installed_binding(
        package_plan, package, install_plan, installed,
        trusted_package_receipt_sha256=package['receipt_sha256'],
        trusted_install_receipt_sha256=installed['receipt_sha256'])
    return install_plan, installed, report, spec


def _scope(session: dict, plan: dict, private: Path, action: str, *,
           duration_minutes: int = 3) -> dict:
    scope = {'schema_version': '1.0', 'kind': 'windows-connected-delivery-scope-v1',
             'run_id': session['run_id'], 'plan_sha256': plan['plan_sha256'],
             'session_sha256': session['session_sha256'],
             'public_key_sha256': plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'],
             'action': action,
             'expires_at': (datetime.now(timezone.utc) +
                            timedelta(minutes=duration_minutes)).isoformat()}
    scope['scope_sha256'] = digest(scope)
    scope['issuer_signature'] = _issue(private, 'scope', scope['scope_sha256'])
    return scope


def _read_when_closed(path: Path, *, timeout: float = 30) -> bytes:
    """Wait for a private native writer's exclusive handle to close."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return path.read_bytes()
        except (FileNotFoundError, PermissionError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.02)


def _synthetic_shadow(tmp_path: Path, monkeypatch, install_plan: dict,
                      installed: dict, report: dict, config: dict,
                      grant: dict, private: Path, public: bytes) -> None:
    """One permitted installed shadow call against an explicitly local TLS fixture."""
    cert_key = tmp_path / 'loopback-key.pem'
    cert = tmp_path / 'loopback-cert.pem'
    generated = subprocess.run([
        str(_ISSUER), 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
        '-keyout', str(cert_key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
        '-addext', 'subjectAltName=IP:127.0.0.1', '-days', '1'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=30, check=False)
    assert generated.returncode == 0, 'Local synthetic TLS certificate setup failed'
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
                    selected = 'summarize' if 'summarize' in labels else labels[0]
                    answers[name] = {'type': 'choice', 'choice': selected,
                                     'confidence': 1.0,
                                     'probabilities': {label: float(label == selected)
                                                       for label in labels}}
            resolved_model = (request['model'] if response_mode['value'] == 'valid'
                              else 'unapproved-model')
            response = json.dumps({'model': resolved_model, 'answers': answers,
                                   'usage': {'input_tokens': 1,
                                             'output_tokens': 1}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    server = ThreadingHTTPServer(('127.0.0.1', 0), SyntheticTypeSafe)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(cert_key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    launched = fault_launched = None
    session = plan = fault_session = fault_plan = None
    try:
        references = create_private_directory(tmp_path / 'loopback-references')
        observations = create_private_directory(tmp_path / 'loopback-observations')
        ref_root = Path(references['path'])
        obs_root = Path(observations['path'])
        public_path = ref_root / 'public.pem'
        cert_path = ref_root / 'cert.pem'
        reference = ref_root / 'connected.json'
        write_private_bytes_exclusive(references, public_path.name, public)
        write_private_bytes_exclusive(references, cert_path.name, cert.read_bytes())
        connected_config = dict(config)
        connected_config['endpoint'] = f'https://127.0.0.1:{server.server_port}/v1/systemone'
        connected_config['environment_digest'] = digest({
            'python': str(Path(installed['installed']['python']).resolve()),
            'version': list(sys.version_info[:3]),
            'implementation': platform.python_implementation(),
            'openssl': ssl.OPENSSL_VERSION,
            'signature_verifier_sha256': _sha(Path(report['site']) /
                'jev_integration_evaluator' / 'windows_connected_verify.py'),
            'cng': cng_identity(),
            'public_key_sha256': hashlib.sha256(public).hexdigest(),
            'cert_sha256': hashlib.sha256(cert_path.read_bytes()).hexdigest(),
            'credential_present': True})
        now = datetime.now(timezone.utc)
        connected_grant = {**grant,
            'endpoint': connected_config['endpoint'],
            'environment_digest': connected_config['environment_digest'],
            'issued_at': (now - timedelta(minutes=1)).isoformat(),
            'expires_at': (now + timedelta(minutes=90)).isoformat()}
        manifest = {'schema_version': '1.0', 'mode': 'shadow',
                    'connected_config': connected_config,
                    'authority': {'egress_grant': connected_grant, 'activation': None},
                    'ledger_path': str(obs_root / 'runtime-ledger'),
                    'signatures': {
                        'installed_binding': _issue(private, 'installed_binding',
                                                    report['binding_sha256']),
                        'egress_grant': _issue(private, 'egress_grant',
                                               digest(connected_grant))}}
        write_private_bytes_exclusive(references, reference.name,
            json.dumps(manifest, sort_keys=True).encode('utf-8'))
        task_id = 'alpha-loopback-shadow'
        ready = obs_root / 'ready.txt'
        entrypoint = obs_root / 'entrypoint.txt'
        integration = obs_root / 'integration.txt'
        effect = obs_root / ('effect-' + task_id + '.json')
        release = obs_root / 'release.txt'
        expected_effect = (json.dumps({'task_id': task_id, 'action': 'inspect',
                                       'item': 'fixture-one'}, sort_keys=True,
                                      separators=(',', ':')) + '\n').encode()
        empty = hashlib.sha256(b'').hexdigest()
        observation = {'checks': [
            {'role': role, 'path': str(path), 'before_sha256': empty,
             'after_sha256': hashlib.sha256(expected).hexdigest()}
            for role, path, expected in (
                ('ready', ready, b'in-flight\n'),
                ('entrypoint_reached', entrypoint, b'entrypoint reached\n'),
                ('integration_reachable', integration, b'integration reachable\n'),
                ('outcome_verified', effect, expected_effect))]}
        environment = {
            'REGISTERED_ALPHA_CONNECTED_REF': str(reference),
            'REGISTERED_ALPHA_AUTH_PUBKEY_FILE': str(public_path),
            'REGISTERED_ALPHA_REFERENCE_ACL_SHA256': references['acl_sha256'],
            'REGISTERED_ALPHA_OBSERVATION_ACL_SHA256': observations['acl_sha256'],
            'REGISTERED_ALPHA_PERMIT': '1',
            'REGISTERED_ALPHA_HOLD': '1',
            'REGISTERED_ALPHA_AUDIT': str(obs_root / 'audit.json'),
            'REGISTERED_ALPHA_EFFECTS': str(obs_root / 'effects.json'),
            'REGISTERED_ALPHA_TASK_ID': task_id,
            'REGISTERED_ALPHA_READY': str(ready),
            'REGISTERED_ALPHA_RELEASE': str(release),
            'REGISTERED_ALPHA_ENTRYPOINT': str(entrypoint),
            'REGISTERED_ALPHA_INTEGRATION': str(integration),
            'SSL_CERT_FILE': str(cert_path)}
        plan = plan_windows_connected_delivery(
            install_plan,
            trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
            trusted_install_receipt_sha256=installed['receipt_sha256'],
            installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
            reference_owner=references, observation_owner=observations,
            launch_environment=environment, observation=observation)
        session = create_windows_connected_session(tmp_path / 'loopback-session',
                                                    plan, install_plan, report)
        launch_scope = _scope(session, plan, private, 'launch', duration_minutes=30)
        launched = launch_windows_connected_session(session, plan, install_plan,
            report, scope=launch_scope,
            approved_scope_sha256=launch_scope['scope_sha256'])
        deadline = time.monotonic() + 30
        while not ready.is_file() and time.monotonic() < deadline:
            time.sleep(.02)
        assert _read_when_closed(ready) == b'in-flight\n'
        while not calls and time.monotonic() < deadline:
            time.sleep(.02)
        assert len(calls) == 1 and calls[0]['path'] == '/v1/systemone'
        live = observe_windows_connected_session(session, plan, install_plan, report,
            approved_identity_sha256=launched['identity_sha256'], role='ready')
        assert live['status'] == 'matched' and live['job_assigned_count'] >= 1
        assert not effect.exists(), 'Host remains held while assessment is observed'
        write_private_bytes_exclusive(observations, release.name, b'go\n')
        deadline = time.monotonic() + 30
        while not effect.is_file() and time.monotonic() < deadline:
            time.sleep(.02)
        assert _read_when_closed(effect) == expected_effect
        assert _read_when_closed(entrypoint) == b'entrypoint reached\n'
        assert _read_when_closed(integration) == b'integration reachable\n'
        while native_session._owned_process(launched)[0] and time.monotonic() < deadline:
            time.sleep(.02)
        observed = observe_windows_connected_session(session, plan, install_plan,
            report, approved_identity_sha256=launched['identity_sha256'],
            role='outcome_verified')
        assert observed['status'] == 'matched'
        assert len(calls) == 1

        # A second stable task uses the same installed generation and durable
        # ledger. Its local TLS server returns an unpinned model, so the host
        # still performs only its preauthorised baseline action.
        assert not native_session._owned_process(launched)[0]
        response_mode['value'] = 'wrong_model'
        fault_task = 'alpha-wrong-model'
        fault_ready = obs_root / 'fault-ready.txt'
        fault_entrypoint = obs_root / 'fault-entrypoint.txt'
        fault_integration = obs_root / 'fault-integration.txt'
        fault_effect = obs_root / ('effect-' + fault_task + '.json')
        fault_release = obs_root / 'fault-release.txt'
        fault_observation = {'checks': [
            {'role': role, 'path': str(path), 'before_sha256': empty,
             'after_sha256': hashlib.sha256(expected).hexdigest()}
            for role, path, expected in (
                ('ready', fault_ready, b'in-flight\n'),
                ('entrypoint_reached', fault_entrypoint, b'entrypoint reached\n'),
                ('integration_reachable', fault_integration,
                 b'integration reachable\n'),
                ('outcome_verified', fault_effect, expected_effect.replace(
                    task_id.encode(), fault_task.encode())))]}
        fault_environment = dict(environment)
        fault_environment.update({
            'REGISTERED_ALPHA_TASK_ID': fault_task,
            'REGISTERED_ALPHA_READY': str(fault_ready),
            'REGISTERED_ALPHA_RELEASE': str(fault_release),
            'REGISTERED_ALPHA_ENTRYPOINT': str(fault_entrypoint),
            'REGISTERED_ALPHA_INTEGRATION': str(fault_integration),
            'REGISTERED_ALPHA_AUDIT': str(obs_root / 'fault-audit.json'),
        })
        fault_plan = plan_windows_connected_delivery(
            install_plan,
            trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
            trusted_install_receipt_sha256=installed['receipt_sha256'],
            installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
            reference_owner=references, observation_owner=observations,
            launch_environment=fault_environment, observation=fault_observation)
        fault_session = create_windows_connected_session(
            tmp_path / 'wrong-model-session', fault_plan, install_plan, report)
        fault_scope = _scope(fault_session, fault_plan, private, 'launch',
                             duration_minutes=30)
        fault_launched = launch_windows_connected_session(
            fault_session, fault_plan, install_plan, report,
            scope=fault_scope, approved_scope_sha256=fault_scope['scope_sha256'])
        deadline = time.monotonic() + 30
        while not fault_ready.is_file() and time.monotonic() < deadline:
            time.sleep(.02)
        assert _read_when_closed(fault_ready) == b'in-flight\n'
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(.02)
        assert len(calls) == 2 and calls[1]['path'] == '/v1/systemone'
        write_private_bytes_exclusive(observations, fault_release.name, b'go\n')
        while not fault_effect.is_file() and time.monotonic() < deadline:
            time.sleep(.02)
        assert _read_when_closed(fault_effect) == expected_effect.replace(
            task_id.encode(), fault_task.encode())
        while native_session._owned_process(fault_launched)[0] and time.monotonic() < deadline:
            time.sleep(.02)
        assert not native_session._owned_process(fault_launched)[0]
        fault_observed = observe_windows_connected_session(
            fault_session, fault_plan, install_plan, report,
            approved_identity_sha256=fault_launched['identity_sha256'],
            role='outcome_verified')
        assert fault_observed['status'] == 'matched'
    finally:
        for current_session, current_plan, current_launch in (
                (fault_session, fault_plan, fault_launched),
                (session, plan, launched)):
            if current_launch is not None:
                stop_scope = _scope(current_session, current_plan, private, 'stop',
                                    duration_minutes=30)
                stopped = stop_windows_connected_session(
                    current_session, current_plan, install_plan, report,
                    scope=stop_scope,
                    approved_scope_sha256=stop_scope['scope_sha256'],
                    approved_identity_sha256=current_launch['identity_sha256'])
                assert stopped['status'] == 'stopped' and not stopped['process_alive']
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_native_connected_installed_hard_block_and_replay(tmp_path, monkeypatch):
    wheelhouse_name = os.environ.get('JEV_WINDOWS_TEMPLATE_WHEELHOUSE')
    if not wheelhouse_name:
        pytest.skip('Explicit reviewed native Windows offline wheelhouse required')
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    verification_owner = create_private_directory(tmp_path / 'verification-effects')
    monkeypatch.setenv('REGISTERED_ALPHA_PROBE_EFFECTS_DIR',
                       verification_owner['path'])
    monkeypatch.setenv('REGISTERED_ALPHA_OBSERVATION_ACL_SHA256',
                       verification_owner['acl_sha256'])
    install_plan, installed, report, spec = _installed(tmp_path, wheelhouse)
    assert report['kind'] == 'windows-connected-installed-binding-v1'
    assert set(report['origins']) == {'host', 'adapter', 'console', 'loader'}
    cli_owner = create_private_directory(tmp_path / 'cli-inputs')
    cli_package_plan = _cli_input(cli_owner, 'package-plan.json',
                                  install_plan['package_plan'])
    cli_package_receipt = _cli_input(cli_owner, 'package-receipt.json',
                                     install_plan['package_receipt'])
    cli_install_plan = _cli_input(cli_owner, 'install-plan.json', install_plan)
    cli_install_receipt = _cli_input(cli_owner, 'install-receipt.json', installed)
    cli_bind_dir = tmp_path / 'cli-binding'
    cli_binding = _installed_connected_cli(installed, tmp_path, 'bind',
        '--package-plan', cli_package_plan,
        '--package-receipt', cli_package_receipt,
        '--install-plan', cli_install_plan,
        '--install-receipt', cli_install_receipt,
        '--trusted-package-receipt-sha256',
        install_plan['package_receipt']['receipt_sha256'],
        '--trusted-install-receipt-sha256', installed['receipt_sha256'],
        '--output-dir', str(cli_bind_dir))
    assert cli_binding['status'] == 'written'
    assert cli_binding['binding_sha256'] == report['binding_sha256']
    assert json.loads((cli_bind_dir / 'binding.json').read_text()) == report
    loader_origin = report['origins']['loader']
    assert current_origin(loader_origin)
    installed_alias = tmp_path / 'installed-loader-hardlink.py'
    os.link(loader_origin['path'], installed_alias)
    try:
        assert not current_origin(loader_origin), 'Installed hardlink must void live origin'
    finally:
        installed_alias.unlink()
    assert current_origin(loader_origin)
    private, public = _issued_key(tmp_path)
    references = create_private_directory(tmp_path / 'references')
    observation_owner = create_private_directory(tmp_path / 'observations')
    public_path = Path(references['path']) / 'public.pem'
    write_private_bytes_exclusive(references, public_path.name, public)
    reference_alias = tmp_path / 'public-key-hardlink.pem'
    os.link(public_path, reference_alias)
    try:
        with pytest.raises(WindowsConnectedDeliveryError,
                           match='windows_connected_reference_invalid'):
            _reference(public_path, references)
    finally:
        reference_alias.unlink()
    assert _reference(public_path, references) == hashlib.sha256(public).hexdigest()
    site = Path(report['site'])
    adapter_tree = ast.parse(Path(report['origins']['adapter']['path']).read_text())
    adapter_spec = ast.literal_eval(next(node.value for node in adapter_tree.body
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'SPEC' for target in node.targets)))
    dependency = {'files': [{'path': str(site / 'registered_alpha' / name),
                             'sha256': _sha(site / 'registered_alpha' / name)}
                            for name in ('requirements.lock', 'runtime.json')]}
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
              'max_total_calls': 2, 'max_total_cost': 2,
              'max_in_flight': 1, 'max_tasks': 2}
    source_bindings = {report['candidate_id']: {
        'reviewed_file_sha256': report['reviewed_file_sha256'],
        'applied_file_sha256': report['applied_file_sha256'],
        'adapter_path': report['origins']['adapter']['wheel_member'],
        'adapter_sha256': report['origins']['adapter']['sha256']}}
    verifier = site / 'jev_integration_evaluator' / 'windows_connected_verify.py'
    environment_digest = digest({
        'python': str(Path(installed['installed']['python']).resolve()),
        'version': list(sys.version_info[:3]),
        'implementation': platform.python_implementation(),
        'openssl': ssl.OPENSSL_VERSION,
        'signature_verifier_sha256': _sha(verifier),
        'cng': cng_identity(),
        'public_key_sha256': hashlib.sha256(public).hexdigest(),
        'cert_sha256': None, 'credential_present': True})
    config = {'endpoint': 'https://127.0.0.1:9/v1/systemone',
              'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
              'environment_digest': environment_digest, 'source_root': report['site'],
              'source_plan': report['source_plan'], 'source_bindings': source_bindings,
              'installed_binding': report}
    connected_schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas' /
                                   'host-runtime-connected-v1.schema.json').read_text(encoding='utf-8'))
    jsonschema.validate(config, connected_schema)
    invalid_config = json.loads(json.dumps(config))
    invalid_config['installed_binding']['origins']['host'].pop('acl_sha256')
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid_config, connected_schema)
    identity = {'root': report['site'], 'plan': report['source_plan'],
                'bindings': source_bindings,
                'installed_binding_sha256': report['binding_sha256']}
    now = datetime.now(timezone.utc)
    grant = {'endpoint': config['endpoint'], 'credential_ref': config['credential_ref'],
             'model': config['model'], 'environment_digest': environment_digest,
             'source_digest': digest(identity), 'dependency_digest': digest(dependency),
             'budget_digest': digest(limits),
             'adapters_digest': digest({report['candidate_id']: digest(adapter_spec)}),
             'mode': 'shadow', 'issued_at': (now - timedelta(minutes=1)).isoformat(),
             'expires_at': (now + timedelta(minutes=30)).isoformat()}
    signatures = {kind: _issue(private, kind, exact)
                  for kind, exact in {'installed_binding': report['binding_sha256'],
                                      'egress_grant': digest(grant)}.items()}
    ledger = Path(observation_owner['path']) / 'runtime-ledger'
    manifest = {'schema_version': '1.0', 'mode': 'shadow',
                'connected_config': config,
                'authority': {'egress_grant': grant, 'activation': None},
                'ledger_path': str(ledger), 'signatures': signatures}
    reference = Path(references['path']) / 'connected.json'
    write_private_bytes_exclusive(references, reference.name,
                                  json.dumps(manifest, sort_keys=True).encode('utf-8'))
    obs_root = Path(observation_owner['path'])
    ready = obs_root / 'ready.txt'
    entrypoint = obs_root / 'entrypoint.txt'
    integration = obs_root / 'integration.txt'
    effect = obs_root / 'effect-alpha-native-one.json'
    outcome = (json.dumps({'task_id': 'alpha-native-one', 'action': 'inspect',
                           'item': 'fixture-one'}, sort_keys=True,
                          separators=(',', ':')) + '\n').encode()
    empty = hashlib.sha256(b'').hexdigest()
    observation = {'checks': [{'role': role, 'path': str(path), 'before_sha256': empty,
                               'after_sha256': hashlib.sha256(raw).hexdigest()}
                              for role, path, raw in (
                                  ('ready', ready, b'in-flight\n'),
                                  ('entrypoint_reached', entrypoint, b'entrypoint reached\n'),
                                  ('integration_reachable', integration, b'integration reachable\n'),
                                  ('outcome_verified', effect, outcome))]}
    environment = {'REGISTERED_ALPHA_CONNECTED_REF': str(reference),
                   'REGISTERED_ALPHA_AUTH_PUBKEY_FILE': str(public_path),
                   'REGISTERED_ALPHA_REFERENCE_ACL_SHA256': references['acl_sha256'],
                   'REGISTERED_ALPHA_OBSERVATION_ACL_SHA256': observation_owner['acl_sha256'],
                   'REGISTERED_ALPHA_PERMIT': '0',
                   'REGISTERED_ALPHA_AUDIT': str(obs_root / 'audit.json'),
                   'REGISTERED_ALPHA_EFFECTS': str(obs_root / 'effects.json'),
                   'REGISTERED_ALPHA_TASK_ID': 'alpha-native-one',
                   'REGISTERED_ALPHA_READY': str(ready),
                   'REGISTERED_ALPHA_ENTRYPOINT': str(entrypoint),
                   'REGISTERED_ALPHA_INTEGRATION': str(integration)}
    plan = plan_windows_connected_delivery(
        install_plan, trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
        trusted_install_receipt_sha256=installed['receipt_sha256'],
        installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
        reference_owner=references, observation_owner=observation_owner,
        launch_environment=environment, observation=observation)
    cli_reference_owner = _cli_input(cli_owner, 'reference-owner.json', references)
    cli_observation_owner = _cli_input(cli_owner, 'observation-owner.json',
                                       observation_owner)
    cli_launch_environment = _cli_input(cli_owner, 'launch-environment.json',
                                        environment)
    cli_observation = _cli_input(cli_owner, 'observation.json', observation)
    cli_plan_dir = tmp_path / 'cli-plan'
    cli_plan = _installed_connected_cli(installed, tmp_path, 'plan',
        '--install-plan', cli_install_plan,
        '--binding', str(cli_bind_dir / 'binding.json'),
        '--trusted-package-receipt-sha256',
        install_plan['package_receipt']['receipt_sha256'],
        '--trusted-install-receipt-sha256', installed['receipt_sha256'],
        '--trusted-binding-sha256', report['binding_sha256'],
        '--reference-owner', cli_reference_owner,
        '--observation-owner', cli_observation_owner,
        '--launch-environment', cli_launch_environment,
        '--observation', cli_observation,
        '--output-dir', str(cli_plan_dir))
    assert cli_plan['status'] == 'written'
    assert cli_plan['plan_sha256'] == plan['plan_sha256']
    assert json.loads((cli_plan_dir / 'plan.json').read_text()) == plan
    cli_session_dir = tmp_path / 'cli-session'
    configured = _installed_connected_cli(installed, tmp_path, 'configure',
        '--install-plan', cli_install_plan,
        '--binding', str(cli_bind_dir / 'binding.json'),
        '--plan', str(cli_plan_dir / 'plan.json'),
        '--session-dir', str(cli_session_dir))
    assert configured['status'] == 'created'
    assert (cli_session_dir / 'session.json').is_file()
    pending = create_windows_connected_session(tmp_path / 'pending-session',
                                                plan, install_plan, report)
    write_private_json_exclusive(pending['owned_directory'], 'launch-intent.json',
        {'session_sha256': pending['session_sha256'],
         'job': 'Local\\jev-template-' + pending['run_id'],
         'status': 'launch_pending'})
    assert windows_connected_session_status(pending, plan, install_plan,
        report)['status'] == 'blocked_recovery'
    pending_scope = _scope(pending, plan, private, 'launch', duration_minutes=30)
    with pytest.raises(WindowsConnectedDeliveryError, match='launch_already_attempted'):
        launch_windows_connected_session(pending, plan, install_plan, report,
            scope=pending_scope,
            approved_scope_sha256=pending_scope['scope_sha256'])
    session = json.loads((cli_session_dir / 'session.json').read_text())
    launch_scope = _scope(session, plan, private, 'launch')
    wrong = dict(launch_scope, issuer_signature=base64.b64encode(b'wrong').decode())
    with pytest.raises(WindowsConnectedDeliveryError, match='scope_signature_invalid'):
        launch_windows_connected_session(session, plan, install_plan, report,
            scope=wrong, approved_scope_sha256=wrong['scope_sha256'])
    assert windows_connected_session_status(session, plan, install_plan, report)['status'] == 'created'
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-startup-only')
    launch_scope = _scope(session, plan, private, 'launch', duration_minutes=30)
    cli_launch_scope = _cli_input(cli_owner, 'hard-launch-scope.json', launch_scope)
    cli_launch = _installed_connected_cli(installed, tmp_path, 'launch',
        '--install-plan', cli_install_plan,
        '--binding', str(cli_bind_dir / 'binding.json'),
        '--plan', str(cli_plan_dir / 'plan.json'),
        '--session', str(cli_session_dir / 'session.json'),
        '--scope', cli_launch_scope,
        '--approve-scope-sha256', launch_scope['scope_sha256'],
        synthetic_credential='synthetic-startup-only')
    launched = json.loads((cli_session_dir / 'launch-identity.json').read_text())
    assert cli_launch['status'] == 'launched'
    assert cli_launch['identity_sha256'] == launched['identity_sha256']
    deadline = time.monotonic() + 15
    while native_session._owned_process(launched)[0] and time.monotonic() < deadline:
        time.sleep(.05)
    status = windows_connected_session_status(session, plan, install_plan, report,
        trusted_identity_sha256=launched['identity_sha256'])
    assert status['status'] == 'exited_unverified'
    cli_status = _installed_connected_cli(installed, tmp_path, 'status',
        '--install-plan', cli_install_plan,
        '--binding', str(cli_bind_dir / 'binding.json'),
        '--plan', str(cli_plan_dir / 'plan.json'),
        '--session', str(cli_session_dir / 'session.json'),
        '--approved-identity-sha256', launched['identity_sha256'])
    assert cli_status['status'] == status['status']
    assert cli_status['receipt_trust'] == 'externally_anchored'
    assert Path(str(ledger) + '.sqlite').is_file(), 'Installed console must own durable ledger'
    assert not effect.exists(), 'Hard permit blocks all host effects'
    entry = _installed_connected_cli(installed, tmp_path, 'observe',
        '--install-plan', cli_install_plan,
        '--binding', str(cli_bind_dir / 'binding.json'),
        '--plan', str(cli_plan_dir / 'plan.json'),
        '--session', str(cli_session_dir / 'session.json'),
        '--approved-identity-sha256', launched['identity_sha256'],
        '--role', 'entrypoint_reached')
    assert entry['status'] == 'matched'
    with pytest.raises(WindowsConnectedDeliveryError, match='launch_already_attempted'):
        launch_windows_connected_session(session, plan, install_plan, report,
            scope=launch_scope, approved_scope_sha256=launch_scope['scope_sha256'])
    stop_scope = _scope(session, plan, private, 'stop', duration_minutes=30)
    cli_stop_scope = _cli_input(cli_owner, 'hard-stop-scope.json', stop_scope)
    stopped = _installed_connected_cli(installed, tmp_path, 'stop',
        '--install-plan', cli_install_plan,
        '--binding', str(cli_bind_dir / 'binding.json'),
        '--plan', str(cli_plan_dir / 'plan.json'),
        '--session', str(cli_session_dir / 'session.json'),
        '--scope', cli_stop_scope,
        '--approve-scope-sha256', stop_scope['scope_sha256'],
        '--approved-identity-sha256', launched['identity_sha256'])
    assert stopped['status'] == 'stopped' and not stopped['process_alive']
    assert private not in [Path(value) for value in environment.values()]
    _synthetic_shadow(tmp_path, monkeypatch, install_plan, installed, report,
                      config, grant, private, public)
