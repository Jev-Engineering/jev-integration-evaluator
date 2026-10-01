"""Source-bound D retrieval through an installed synthetic connected shadow console."""
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
import sqlite3
import ssl
import subprocess
import sys
from threading import Thread
import time

import pytest

from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import canonical, digest, file_hash
from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator.template_connected_delivery import (
    ConnectedDeliveryError, connected_session_status, create_connected_session,
    launch_connected_session, plan_connected_delivery, stop_connected_session,
)
from jev_integration_evaluator.integrations.lifecycle import rollback_implementation
from tests.test_connected_installed_binding import _issuer, _issue, _verifier_identity
from tests.test_template_installation import _metadata
from tests.test_use_case_retrieval_bound_installed import _applied, _installed
from tests.test_use_case_retrieval_host import PROFILE, _expected_effect


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='D connected installed fixture requires Linux x86-64 CPython 3.13')
LOADER = Path(__file__).parent / 'independent_hosts/retrieval_connected/connected_authority.py'


def _scope(created: dict, plan: dict, action: str) -> dict:
    scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
             'run_id': created['run_id'], 'plan_sha256': plan['plan_sha256'],
             'public_key_sha256': plan['reference_sha256']['D_AUTH_PUBKEY_FILE'],
             'trusted_session_head': created['session_head_sha256'], 'action': action,
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
    scope['scope_sha256'] = digest(scope)
    validate_contract(scope, 'connected-delivery-scope-v1')
    return scope


def _observation(folder: Path, corpus: Path) -> tuple[dict, bytes]:
    raw = _expected_effect(corpus)
    ready = folder / 'ready.txt'
    first = folder / 'retrieval-one.json'
    second = folder / 'retrieval-two.json'
    return ({'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
             'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                         'expected_sha256': hashlib.sha256(value).hexdigest()}
                        for role, path, value in (
                            ('ready', ready, b'ready\n'),
                            ('entrypoint_reached', first, raw),
                            ('integration_reachable', first, raw),
                            ('outcome_verified', second, raw))]}, raw)


def _grant(report: dict, receipt: dict, public: Path, endpoint: str,
           dependency: dict, limits: dict, adapter_spec: dict) -> tuple[dict, dict]:
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
        'public_key_sha256': file_hash(public),
        'cert_sha256': None, 'credential_present': True})
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
             'expires_at': (now + timedelta(minutes=5)).isoformat()}
    return config, grant


def _wait(path: Path, expected: bytes, seconds: float = 20) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.is_file() and path.read_bytes() == expected:
            return
        time.sleep(0.02)
    raise AssertionError('independent D effect missing')


def _ledger(path: Path) -> dict | None:
    database = Path(str(path) + '.sqlite')
    if not database.is_file():
        return None
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1) as db:
        row = db.execute('SELECT payload FROM state WHERE id=1').fetchone()
    return json.loads(row[0]) if row else None


def _failure_events(folder: Path) -> list[dict]:
    path = folder / 'failure-events.jsonl'
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_d_source_bound_installed_connected_shadow_raw_retrieval(tmp_path, monkeypatch):
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
    host = _applied(tmp_path, 'connected-d', '1.0.0', LOADER)
    install_plan, receipt = _installed(tmp_path, host, wheelhouse, rows,
                                       requirements, environments, 'connected-package')
    package_plan, package_receipt = install_plan['package_plan'], install_plan['package_receipt']
    report = derive_installed_binding(package_plan, package_receipt, install_plan, receipt,
        trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
        trusted_install_receipt_sha256=receipt['receipt_sha256'])
    assert report['source_file'] == 'retrieval_host/host_retrieval_handoff.py'
    assert report['origins']['loader']['wheel_member'] == 'retrieval_host/connected_authority.py'
    assert all(Path(row['path']).is_file() for row in report['source_plan']['files'])
    adapter_tree = ast.parse(Path(report['origins']['adapter']['path']).read_text())
    adapter_spec = ast.literal_eval(next(node.value for node in adapter_tree.body
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'SPEC' for target in node.targets)))
    dependency = {'files': [{'path': str(Path(report['site']) / 'retrieval_host' / name),
                             'sha256': file_hash(Path(report['site']) / 'retrieval_host' / name)}
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
                # Longer than the adapter's fixed 2000 ms transport budget.
                time.sleep(3)
            answers = {}
            for name, question in request['questions'].items():
                if question['type'] == 'noul':
                    answers[name] = {'type': 'noul', 'noul': 1.0}
                else:
                    labels = list(question['criteria'])
                    choice = 'supports' if 'supports' in labels else labels[0]
                    answers[name] = {'type': 'choice', 'choice': choice,
                                     'confidence': 1.0,
                                     'probabilities': {label: float(label == choice)
                                                       for label in labels}}
            model = (request['model'] if response_mode['value'] != 'wrong_model'
                     else request['model'] + '-wrong')
            result = (b'{not-json' if response_mode['value'] == 'malformed' else
                      json.dumps({'model': model, 'answers': answers,
                                  'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode())
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(result)))
            self.end_headers()
            try:
                self.wfile.write(result)
            except (OSError, ssl.SSLError):
                pass

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
    active_sessions: list[tuple[Path, dict]] = []
    try:
        endpoint = f'https://127.0.0.1:{server.server_port}/v1/systemone'
        config, grant = _grant(report, receipt, public, endpoint, dependency, limits, adapter_spec)
        config['environment_digest'] = digest({
            'python': str(Path(receipt['installed']['python']).resolve()),
            'version': list(sys.version_info[:3]),
            'implementation': platform.python_implementation(),
            'openssl': ssl.OPENSSL_VERSION,
            'signature_verifier': _verifier_identity(),
            'public_key_sha256': file_hash(public),
            'cert_sha256': file_hash(cert), 'credential_present': True})
        grant['environment_digest'] = config['environment_digest']

        def one_run(label: str, expected_calls: int, *,
                    mode: str = 'valid') -> tuple[dict, Path]:
            assert mode in ('valid', 'wrong_model', 'malformed', 'timeout', 'revoke_ref')
            # The three fault schedules hold after the first committed effect
            # and before the second task routes, so each provider attempt and
            # its ledger reservation can be read back exactly.
            between_tasks = mode in ('malformed', 'timeout', 'revoke_ref')
            response_mode['value'] = 'valid' if mode == 'revoke_ref' else mode
            previous_calls = len(calls)
            folder = tmp_path / ('effects-' + label)
            folder.mkdir(mode=0o700)
            observation, raw = _observation(folder, host['corpus'])
            ledger = tmp_path / ('ledger-' + label)
            reference = tmp_path / ('reference-' + label + '.json')
            grant['issued_at'] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            grant['expires_at'] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            manifest = {'schema_version': '1.0', 'mode': 'shadow',
                        'connected_config': config,
                        'authority': {'egress_grant': grant, 'activation': None},
                        'ledger_path': str(ledger),
                        'signatures': {'installed_binding': _issue(private, 'installed_binding',
                                                                   report['binding_sha256']),
                                       'egress_grant': _issue(private, 'egress_grant', digest(grant))}}
            reference.write_text(json.dumps(manifest), encoding='utf-8')
            reference.chmod(0o600)
            launch_env = {'D_CONNECTED_REF': str(reference),
                          'D_AUTH_PUBKEY_FILE': str(public),
                          'D_CORPUS_PATH': str(host['corpus']),
                          'D_EFFECT_DIRECTORY': str(folder),
                          'D_TASKS': 'two', 'D_HOLD': '1',
                          'D_RELEASE_PATH': str(folder / 'release.txt'),
                          'SSL_CERT_FILE': str(cert)}
            if between_tasks:
                launch_env['D_HOLD_POINT'] = 'between-tasks'
            if label == 'valid':
                common = dict(
                    trusted_install_receipt_sha256=receipt['receipt_sha256'],
                    trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
                    installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
                    observation=observation)
                # The hold point is a finite selector, and a between-task hold
                # without an explicit hold and release path is refused.
                for wrong in ({**launch_env, 'D_HOLD_POINT': 'model-decides'},
                              {**launch_env, 'D_HOLD_POINT': 'between-tasks', 'D_HOLD': '0'},
                              {k: v for k, v in {**launch_env,
                                                 'D_HOLD_POINT': 'between-tasks'}.items()
                               if k != 'D_HOLD'},
                              {k: v for k, v in {**launch_env,
                                                 'D_HOLD_POINT': 'between-tasks'}.items()
                               if k != 'D_RELEASE_PATH'},
                              {**launch_env, 'D_TASKS': 'unbounded'},
                              {**launch_env, 'D_HOLD': 'yes'},
                              # Each private reference is required by name.
                              *({k: v for k, v in launch_env.items() if k != missing}
                                for missing in ('D_CONNECTED_REF', 'D_AUTH_PUBKEY_FILE',
                                                'D_CORPUS_PATH'))):
                    with pytest.raises(ConnectedDeliveryError,
                                       match='connected_host_references_required'):
                        plan_connected_delivery(install_plan, **common,
                            launch_environment=wrong, host_profile='retrieval-d-v1')
                assert plan_connected_delivery(install_plan, **common,
                    launch_environment={**launch_env, 'D_HOLD_POINT': 'pre-commit'},
                    host_profile='retrieval-d-v1')['host_profile'] == 'retrieval-d-v1'
                with pytest.raises(ConnectedDeliveryError, match='connected_host_references_required'):
                    plan_connected_delivery(install_plan, **common,
                        launch_environment={**launch_env,
                            'REGISTERED_ALPHA_CONNECTED_REF': str(reference)},
                        host_profile='retrieval-d-v1')
                alpha_names = {'REGISTERED_ALPHA_CONNECTED_REF': str(reference),
                               'REGISTERED_ALPHA_AUTH_PUBKEY_FILE': str(public),
                               'REGISTERED_ALPHA_EFFECTS': str(folder)}
                with pytest.raises(ConnectedDeliveryError, match='connected_host_profile_binding_mismatch'):
                    plan_connected_delivery(install_plan, **common,
                        launch_environment=alpha_names)
            plan = plan_connected_delivery(install_plan,
                trusted_install_receipt_sha256=receipt['receipt_sha256'],
                trusted_package_receipt_sha256=package_receipt['receipt_sha256'],
                installed_binding=report, trusted_binding_sha256=report['binding_sha256'],
                observation=observation, launch_environment=launch_env,
                host_profile='retrieval-d-v1')
            assert plan['host_profile'] == 'retrieval-d-v1'
            validate_contract(plan, 'connected-delivery-plan-v1')
            session = tmp_path / ('session-' + label)
            created = create_connected_session(session, plan,
                approved_plan_sha256=plan['plan_sha256'])
            active_sessions.append((session, plan))
            wrong_profile = dict(plan, host_profile='registered-alpha-v1')
            wrong_profile['plan_sha256'] = digest({k: v for k, v in wrong_profile.items()
                                                   if k != 'plan_sha256'})
            with pytest.raises(InputError):
                create_connected_session(tmp_path / ('wrong-' + label), wrong_profile,
                    approved_plan_sha256=wrong_profile['plan_sha256'])
            launch = _scope(created, plan, 'launch')
            wrong_key = dict(launch, public_key_sha256='0' * 64)
            wrong_key['scope_sha256'] = digest({k: v for k, v in wrong_key.items()
                                                if k != 'scope_sha256'})
            with pytest.raises(ConnectedDeliveryError, match='exact_expiring_connected_scope_required'):
                launch_connected_session(session, scope=wrong_key,
                    approved_scope_sha256=wrong_key['scope_sha256'])
            monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')
            if label == 'valid':
                # A missing credential is refused before any launch attempt,
                # provider request or retrieval effect.
                with monkeypatch.context() as no_credential:
                    no_credential.delenv('TYPESAFE_API_KEY')
                    with pytest.raises(ConnectedDeliveryError,
                                       match='connected_credential_unavailable'):
                        launch_connected_session(session, scope=launch,
                            approved_scope_sha256=launch['scope_sha256'])
                unlaunched = connected_session_status(session)
                assert unlaunched['launch_attempts'] == 0 and not unlaunched['process_alive']
                assert len(calls) == previous_calls and list(folder.iterdir()) == []
            original_reference = reference.read_bytes()
            reference.write_bytes(original_reference + b'\n')
            assert not connected_session_status(session)['private_references_current']
            with pytest.raises(ConnectedDeliveryError, match='connected_plan_or_reference_drift'):
                launch_connected_session(session, scope=launch,
                    approved_scope_sha256=launch['scope_sha256'])
            assert connected_session_status(session)['launch_attempts'] == 0
            reference.write_bytes(original_reference)
            assert connected_session_status(session)['private_references_current']
            launched = launch_connected_session(session, scope=launch,
                approved_scope_sha256=launch['scope_sha256'])
            assert launched['launch_attempts'] == 1
            if between_tasks:
                _wait(folder / 'retrieval-one.json', raw)
                held = connected_session_status(session)
                assert held['process_alive']
                assert held['independent_checks']['integration_reachable']
                assert not held['independent_checks']['ready']
                assert not held['independent_checks']['outcome_verified']
                # Exactly one provider attempt, settled in the durable ledger,
                # before the second task is released.
                deadline = time.monotonic() + 10
                snapshot = None
                while time.monotonic() < deadline:
                    snapshot = _ledger(ledger)
                    if (len(calls) == previous_calls + 1 and snapshot is not None
                            and snapshot['calls'] == 1 and not snapshot['inflight']):
                        break
                    time.sleep(0.02)
                else:
                    raise AssertionError('first D shadow reservation did not settle')
                assert len(calls) == previous_calls + 1
                assert calls[-1]['path'] == '/v1/systemone'
                expected_event = None
                if mode in ('malformed', 'timeout'):
                    expected_event = {'type': 'assessment_error', 'error_class': (
                        'JSONDecodeError' if mode == 'malformed' else 'EvaluationTimeoutError')}
                    deadline = time.monotonic() + 5
                    while not _failure_events(folder) and time.monotonic() < deadline:
                        time.sleep(0.02)
                    assert _failure_events(folder) == [expected_event]
                else:
                    assert _failure_events(folder) == []
                # The failed assessment did not change the committed effect and
                # nothing of the second task exists while it is held.
                assert (folder / 'retrieval-one.json').read_bytes() == raw
                assert not (folder / 'ready.txt').exists()
                assert not (folder / 'retrieval-two.json').exists()
                if mode == 'revoke_ref':
                    reference.write_bytes(original_reference + b'\n')
                    assert not connected_session_status(session)['private_references_current']
                (folder / 'release.txt').write_bytes(b'go\n')
                if mode != 'revoke_ref':
                    _wait(folder / 'ready.txt', b'ready\n')
                    _wait(folder / 'retrieval-two.json', raw)
                    assert connected_session_status(session)['independent_checks']['outcome_verified']
                deadline = time.monotonic() + 20
                while connected_session_status(session)['process_alive'] and time.monotonic() < deadline:
                    time.sleep(0.05)
                finished = connected_session_status(session)
                assert not finished['process_alive']
                snapshot = _ledger(ledger)
                assert snapshot is not None and not snapshot['inflight']
                if mode == 'revoke_ref':
                    # The second task fails closed before its route: no second
                    # effect, no readiness marker and no further provider call.
                    assert not (folder / 'ready.txt').exists()
                    assert not (folder / 'retrieval-two.json').exists()
                    assert not finished['independent_checks']['outcome_verified']
                    assert len(calls) == previous_calls + 1
                    assert snapshot['calls'] == 1
                    assert _failure_events(folder) == []
                    reference.write_bytes(original_reference)
                    assert connected_session_status(session)['private_references_current']
                else:
                    assert len(calls) == previous_calls + 2
                    assert calls[-1]['path'] == '/v1/systemone'
                    assert snapshot['calls'] == 2
                    assert len(snapshot['tasks']) == 2
                    assert _failure_events(folder) == [expected_event] * 2
                    assert (folder / 'retrieval-two.json').read_bytes() == raw
                # The deterministic host effect is the unassisted baseline in
                # every schedule: the conflict is withheld with all passages.
                assert (folder / 'retrieval-one.json').read_bytes() == raw
                assert (folder / 'owner.txt').read_bytes() == b'one-runtime-startup\n'
                for task in (('retrieval-one',) if mode == 'revoke_ref'
                             else ('retrieval-one', 'retrieval-two')):
                    effect = json.loads((folder / (task + '.json')).read_bytes())
                    assert effect['answer']['disposition'] == 'withheld_conflict'
                    assert effect['answer']['answer'] is None
                    assert effect['selected_ids'] == ['hit', 'counter', 'maybe']
                    assert [item['source_id'] for item in effect['answer']['passages']] == [
                        'registry-one', 'registry-two', 'registry-three']
                    validate_contract(effect['answer'], 'retrieval-answer-handoff-v1')
                assert sorted(path.name for path in folder.iterdir()) == sorted(
                    ['owner.txt', 'release.txt', 'retrieval-one.json']
                    + ([] if mode == 'revoke_ref' else ['ready.txt', 'retrieval-two.json'])
                    + (['failure-events.jsonl'] if expected_event else []))
                stop_scope = _scope(connected_session_status(session), plan, 'stop')
                stopped = stop_connected_session(session, scope=stop_scope,
                    approved_scope_sha256=stop_scope['scope_sha256'])
                assert stopped['stage'] == 'stopped'
                return plan, folder
            _wait(folder / 'ready.txt', b'ready\n')
            _wait(folder / 'retrieval-one.json', raw)
            before_release = connected_session_status(session)
            assert before_release['process_alive']
            assert before_release['independent_checks']['integration_reachable']
            assert not before_release['independent_checks']['outcome_verified']
            deadline = time.monotonic() + 10
            while len(calls) < previous_calls + expected_calls and time.monotonic() < deadline:
                time.sleep(0.02)
            assert expected_calls <= len(calls) - previous_calls <= 2
            assert calls[-1]['path'] == '/v1/systemone'
            (folder / 'release.txt').write_bytes(b'go\n')
            _wait(folder / 'retrieval-two.json', raw)
            assert connected_session_status(session)['independent_checks']['outcome_verified']
            for task in ('retrieval-one', 'retrieval-two'):
                effect = json.loads((folder / (task + '.json')).read_bytes())
                assert effect['answer']['disposition'] == 'withheld_conflict'
                assert effect['answer']['answer'] is None
                assert [item['source_id'] for item in effect['answer']['passages']] == [
                    'registry-one', 'registry-two', 'registry-three']
                validate_contract(effect['answer'], 'retrieval-answer-handoff-v1')
            deadline = time.monotonic() + 20
            while connected_session_status(session)['process_alive'] and time.monotonic() < deadline:
                time.sleep(0.05)
            assert not connected_session_status(session)['process_alive']
            assert Path(str(ledger) + '.sqlite').is_file()
            stop_scope = _scope(connected_session_status(session), plan, 'stop')
            stopped = stop_connected_session(session, scope=stop_scope,
                approved_scope_sha256=stop_scope['scope_sha256'])
            assert stopped['stage'] == 'stopped'
            return plan, folder

        first_plan, first_folder = one_run('valid', 2)
        second_plan, second_folder = one_run('wrong-model', 1, mode='wrong_model')
        assert first_plan['plan_sha256'] != second_plan['plan_sha256']
        assert (first_folder / 'retrieval-one.json').read_bytes() == \
               (second_folder / 'retrieval-one.json').read_bytes()
        # The second shadow future can already be sent when a malformed first
        # response suspends routing.  Both schedules retain the baseline effect.
        assert len(calls) in (3, 4)
        calls_before_faults = len(calls)
        _, malformed = one_run('malformed-response', 2, mode='malformed')
        _, timed_out = one_run('actual-timeout', 2, mode='timeout')
        _, revoked = one_run('revoked-reference', 1, mode='revoke_ref')
        assert len(calls) == calls_before_faults + 5
        baseline = (first_folder / 'retrieval-one.json').read_bytes()
        assert baseline == (first_folder / 'retrieval-two.json').read_bytes()
        for fault in (malformed, timed_out):
            assert (fault / 'retrieval-one.json').read_bytes() == baseline
            assert (fault / 'retrieval-two.json').read_bytes() == baseline
        assert (revoked / 'retrieval-one.json').read_bytes() == baseline
        assert not (revoked / 'retrieval-two.json').exists()
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
