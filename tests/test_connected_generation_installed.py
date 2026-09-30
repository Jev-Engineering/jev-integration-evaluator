"""Two reviewed installed Alpha generations and one durable synthetic ledger."""
from __future__ import annotations

import ast
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import ssl
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
from jev_integration_evaluator.budget import BudgetDenied
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator.template_connected_delivery import (
    create_connected_session, launch_connected_session, plan_connected_delivery,
    connected_session_status, stop_connected_session)
from jev_integration_evaluator import template_connected_delivery as connected_delivery
from jev_integration_evaluator.template_connected_generation import (
    plan_connected_generation_transfer, transfer_connected_generation,
    connected_generation_status, reconcile_connected_generation)
from jev_integration_evaluator import template_connected_generation as generation


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Installed(Exception):
    pass


def _install(tmp_path: Path, wheelhouse: Path, source_name: str, monkeypatch):
    fixture = Path(__file__).resolve().parent / 'independent_hosts' / source_name
    driver = _module('generation_install_' + source_name,
                     Path(__file__).resolve().parent /
                     'independent_hosts/registered_alpha/installed_journey.py')
    driver.ROOT = fixture
    qualifier = _module('generation_review_' + source_name, fixture / 'qualification.py')
    driver.source_matched_request = qualifier.source_matched_request
    captured = {}
    original = installer.install_package
    def after_install(plan, **kwargs):
        receipt = original(plan, **kwargs)
        captured['plan'] = plan
        captured['receipt'] = receipt
        captured['binding'] = derive_installed_binding(plan['package_plan'],
            plan['package_receipt'], plan, receipt,
            trusted_package_receipt_sha256=plan['package_receipt']['receipt_sha256'],
            trusted_install_receipt_sha256=receipt['receipt_sha256'])
        raise _Installed()
    with monkeypatch.context() as patch:
        patch.setattr(installer, 'install_package', after_install)
        with pytest.raises(_Installed):
            driver.run_offline(tmp_path / ('run-' + source_name), wheelhouse,
                               tmp_path / ('anchors-' + source_name))
    return captured


def _scope(result: dict, plan: dict, action: str, cutoff: datetime) -> dict:
    scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
             'run_id': result['run_id'], 'plan_sha256': plan['plan_sha256'],
             'public_key_sha256': plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'],
             'trusted_session_head': result['session_head_sha256'],
             'action': action, 'expires_at': cutoff.isoformat()}
    scope['scope_sha256'] = digest(scope)
    return scope


def _wait_effect(session: Path, effect: Path, expected: bytes, release: Path) -> dict:
    deadline = time.monotonic() + 30
    release.write_bytes(b'go\n')
    while not effect.is_file() and time.monotonic() < deadline:
        time.sleep(.02)
    assert effect.read_bytes() == expected
    current = connected_session_status(session)
    while current['process_alive'] and time.monotonic() < deadline:
        time.sleep(.02)
        current = connected_session_status(session)
    assert not current['process_alive']
    return current


def test_two_installed_connected_generations_keep_one_ledger_and_retained_rollback(
        tmp_path, monkeypatch):
    wheelhouse = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
            and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)
            and wheelhouse and Path(wheelhouse).is_dir()):
        pytest.skip('requires Linux CPython 3.13 and reviewed offline wheelhouse')
    from test_connected_installed_binding import _issuer, _issue, _verifier_identity
    private, public = _issuer(tmp_path)
    cert, cert_key = tmp_path / 'loopback.crt', tmp_path / 'loopback.key'
    generated = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-nodes', '-keyout', str(cert_key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
        '-addext', 'subjectAltName=IP:127.0.0.1', '-days', '1'],
        capture_output=True, timeout=20)
    assert generated.returncode == 0
    cert.chmod(0o600); cert_key.chmod(0o600)
    calls = []
    class LocalTypeSafe(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            request = json.loads(raw)
            calls.append(hashlib.sha256(raw).hexdigest())
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
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response))); self.end_headers()
            self.wfile.write(response)
    server = ThreadingHTTPServer(('127.0.0.1', 0), LocalTypeSafe)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(cert_key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sessions = []
    try:
        installed = [_install(tmp_path, Path(wheelhouse), name, monkeypatch) for name in
                     ('registered_alpha_connected', 'registered_alpha_connected_103')]
        assert installed[0]['binding']['wheel_sha256'] != installed[1]['binding']['wheel_sha256']
        assert installed[0]['binding']['site'] != installed[1]['binding']['site']
        ledger_path = tmp_path / 'shared-runtime.ledger'
        limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
                  'max_total_calls': 2, 'max_total_cost': 2,
                  'max_in_flight': 1, 'max_tasks': 2}
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(minutes=8)
        plans, dependencies = [], []
        for index, row in enumerate(installed):
            binding, install_plan, install_receipt = (row[name] for name in
                ('binding', 'plan', 'receipt'))
            source = Path(binding['site']) / 'registered_alpha'
            dependency = {'files': [{'path': str(source / name),
                                     'sha256': hashlib.sha256((source / name).read_bytes()).hexdigest()}
                                    for name in ('requirements.lock', 'runtime.json')]}
            dependencies.append(dependency)
            adapter = ast.parse(Path(binding['origins']['adapter']['path']).read_bytes())
            spec = ast.literal_eval(next(n.value for n in adapter.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'SPEC' for t in n.targets)))
            source_bindings = {binding['candidate_id']: {
                'reviewed_file_sha256': binding['reviewed_file_sha256'],
                'applied_file_sha256': binding['applied_file_sha256'],
                'adapter_path': binding['origins']['adapter']['wheel_member'],
                'adapter_sha256': binding['origins']['adapter']['sha256']}}
            environment_digest = digest({
                'python': str(Path(install_receipt['installed']['python']).resolve()),
                'version': list(sys.version_info[:3]), 'implementation': platform.python_implementation(),
                'openssl': ssl.OPENSSL_VERSION, 'credential_present': True,
                'cert_sha256': hashlib.sha256(cert.read_bytes()).hexdigest(),
                'signature_verifier': _verifier_identity(),
                'public_key_sha256': hashlib.sha256(public.read_bytes()).hexdigest()})
            config = {'endpoint': f'https://127.0.0.1:{server.server_port}/v1/systemone',
                      'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
                      'environment_digest': environment_digest, 'source_root': binding['site'],
                      'source_plan': binding['source_plan'], 'source_bindings': source_bindings,
                      'installed_binding': binding}
            egress = {'endpoint': config['endpoint'], 'credential_ref': config['credential_ref'],
                      'model': config['model'], 'environment_digest': environment_digest,
                      'source_digest': digest({'root': binding['site'], 'plan': binding['source_plan'],
                                               'bindings': source_bindings,
                                               'installed_binding_sha256': binding['binding_sha256']}),
                      'dependency_digest': digest(dependency), 'budget_digest': digest(limits),
                      'adapters_digest': digest({binding['candidate_id']: digest(spec)}),
                      'mode': 'shadow', 'issued_at': (now-timedelta(minutes=1)).isoformat(),
                      'expires_at': cutoff.isoformat()}
            reference = tmp_path / f'connected-{index}.json'
            reference.write_text(json.dumps({'schema_version': '1.0', 'mode': 'shadow',
                'connected_config': config, 'authority': {'egress_grant': egress, 'activation': None},
                'ledger_path': str(ledger_path), 'signatures': {
                    'installed_binding': _issue(private, 'installed_binding', binding['binding_sha256']),
                    'egress_grant': _issue(private, 'egress_grant', digest(egress))}}))
            reference.chmod(0o600)
            task_id = f'generation-task-{index}'
            effect = tmp_path / f'effect-{index}.jsonl'
            ready, release = tmp_path / f'ready-{index}.bin', tmp_path / f'release-{index}.bin'
            expected_effect = (json.dumps({'task_id': task_id, 'action': 'inspect',
                                           'item': 'fixture-one'}, sort_keys=True,
                                          separators=(',', ':')) + '\n').encode()
            observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                            'expected_sha256': hashlib.sha256(expected).hexdigest()}
                           for role, path, expected in (
                               ('ready', ready, b'in-flight\n'),
                               ('entrypoint_reached', ready, b'in-flight\n'),
                               ('integration_reachable', effect, expected_effect),
                               ('outcome_verified', effect, expected_effect))]}
            plan = plan_connected_delivery(install_plan,
                trusted_install_receipt_sha256=install_receipt['receipt_sha256'],
                trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
                installed_binding=binding, trusted_binding_sha256=binding['binding_sha256'],
                observation=observation,
                launch_environment={'REGISTERED_ALPHA_CONNECTED_REF': str(reference),
                    'REGISTERED_ALPHA_AUTH_PUBKEY_FILE': str(public),
                    'REGISTERED_ALPHA_PERMIT': '1', 'REGISTERED_ALPHA_TASK_ID': task_id,
                    'REGISTERED_ALPHA_AUDIT': str(tmp_path / f'audit-{index}.jsonl'),
                    'REGISTERED_ALPHA_EFFECTS': str(effect), 'REGISTERED_ALPHA_HOLD': '1',
                    'REGISTERED_ALPHA_READY': str(ready),
                    'REGISTERED_ALPHA_RELEASE': str(release), 'SSL_CERT_FILE': str(cert)})
            plans.append((plan, effect, ready, release, expected_effect))

        first = tmp_path / 'session-102'; sessions.append((first, plans[0][0]))
        created = create_connected_session(first, plans[0][0],
            approved_plan_sha256=plans[0][0]['plan_sha256'])
        scope = _scope(created, plans[0][0], 'launch', cutoff)
        monkeypatch.setenv('TYPESAFE_API_KEY', 'offline-synthetic-only')
        launch_connected_session(first, scope=scope, approved_scope_sha256=scope['scope_sha256'])
        deadline = time.monotonic() + 30
        while not plans[0][2].is_file() and time.monotonic() < deadline:
            time.sleep(.02)
        assert plans[0][2].read_bytes() == b'in-flight\n'
        while len(calls) < 1 and time.monotonic() < deadline:
            time.sleep(.02)
        assert len(calls) == 1
        _wait_effect(first, plans[0][1], plans[0][4], plans[0][3])
        current = connected_session_status(first)
        stop_scope = _scope(current, plans[0][0], 'stop', cutoff)
        stopped = stop_connected_session(first, scope=stop_scope,
                                         approved_scope_sha256=stop_scope['scope_sha256'])
        assert stopped['stage'] == 'stopped'
        old_head = stopped['session_head_sha256']
        new_reference = Path(plans[1][0]['off_provenance']['launch_environment'][
            'REGISTERED_ALPHA_CONNECTED_REF'])
        original_reference = new_reference.read_bytes()
        late_manifest = json.loads(original_reference)
        late_manifest['authority']['egress_grant']['expires_at'] = (
            cutoff + timedelta(minutes=1)).isoformat()
        late_manifest['signatures']['egress_grant'] = _issue(private, 'egress_grant',
            digest(late_manifest['authority']['egress_grant']))
        new_reference.write_text(json.dumps(late_manifest))
        late_plan = plan_connected_delivery(installed[1]['plan'],
            trusted_install_receipt_sha256=installed[1]['receipt']['receipt_sha256'],
            trusted_package_receipt_sha256=installed[1]['plan']['package_receipt']['receipt_sha256'],
            installed_binding=installed[1]['binding'],
            trusted_binding_sha256=installed[1]['binding']['binding_sha256'],
            observation=plans[1][0]['off_provenance']['observation'],
            launch_environment=plans[1][0]['off_provenance']['launch_environment'])
        with pytest.raises(InputError, match='connected_generation_scope_invalid'):
            plan_connected_generation_transfer(first, late_plan,
                trusted_old_head=old_head, old_dependency_plan=dependencies[0],
                new_dependency_plan=dependencies[1], limits=limits, action='upgrade',
                issued_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
                expires_at=cutoff.isoformat())
        new_reference.write_bytes(original_reference)
        issued = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        grant = plan_connected_generation_transfer(first, plans[1][0],
            trusted_old_head=old_head, old_dependency_plan=dependencies[0],
            new_dependency_plan=dependencies[1], limits=limits, action='upgrade',
            issued_at=issued, expires_at=cutoff.isoformat())
        signature = tmp_path / 'transfer-signature.txt'
        from test_connected_installed_binding import _issue as issue
        signature.write_text(issue(private, 'generation_transfer', digest(grant)))
        signature.chmod(0o600)
        second = tmp_path / 'session-103'; sessions.append((second, plans[1][0]))
        transfer_args = dict(trusted_old_head=old_head,
            approved_new_plan_sha256=plans[1][0]['plan_sha256'],
            old_dependency_plan=dependencies[0], new_dependency_plan=dependencies[1],
            grant=grant, signature_file=signature)
        signature.write_text('invalid-signature')
        with pytest.raises(InputError, match='transfer_unverified'):
            transfer_connected_generation(first, second, plans[1][0], **transfer_args)
        assert not second.exists() and len(calls) == 1
        signature.write_text(issue(private, 'generation_transfer', digest(grant)))
        held = RuntimeLedger(ledger_path, identity=grant['old_identity'], **limits)
        with pytest.raises(InputError, match='owned_by_another_process'):
            transfer_connected_generation(first, second, plans[1][0], **transfer_args)
        assert not second.exists()  # Planning cannot capture a live owner's history.
        held.release()
        def lost_controller_ack(*_args, **_kwargs):
            raise RuntimeError('synthetic controller exit after durable ledger commit')
        with monkeypatch.context() as patch:
            patch.setattr(generation, 'reconcile_connected_generation', lost_controller_ack)
            with pytest.raises(RuntimeError, match='controller exit'):
                transfer_connected_generation(first, second, plans[1][0], **transfer_args)
        pending = connected_generation_status(first, second, grant=grant,
            signature_file=signature, trusted_old_head=old_head)
        assert pending['ledger']['status'] == 'committed'
        assert pending['child_stage'] == 'generation_pending'
        recovered = reconcile_connected_generation(first, second, grant=grant,
            signature_file=signature, trusted_old_head=old_head)
        assert recovered['child_stage'] == 'installed'
        assert recovered['run_id'] == created['run_id']
        assert connected_generation_status(first, second, grant=grant,
            signature_file=signature, trusted_old_head=old_head)['ledger']['status'] == 'committed'
        wrong_env = dict(plans[1][0]['off_provenance']['launch_environment'])
        wrong_env['REGISTERED_ALPHA_TASK_ID'] = 'unapproved-plan-task'
        wrong_observation = copy.deepcopy(plans[1][0]['off_provenance']['observation'])
        for check in wrong_observation['checks']:
            check['path'] = str(tmp_path / ('unapproved-' + check['role'] + '.bin'))
            check['before_sha256'] = None
        wrong_plan = plan_connected_delivery(installed[1]['plan'],
            trusted_install_receipt_sha256=installed[1]['receipt']['receipt_sha256'],
            trusted_package_receipt_sha256=installed[1]['plan']['package_receipt']['receipt_sha256'],
            installed_binding=installed[1]['binding'],
            trusted_binding_sha256=installed[1]['binding']['binding_sha256'],
            observation=wrong_observation,
            launch_environment=wrong_env)
        wrong_child = tmp_path / 'session-wrong-plan'
        wrong_parent = copy.deepcopy(connected_delivery._open(second)[2]['generation_parent'])
        create_connected_session(wrong_child, wrong_plan,
            approved_plan_sha256=wrong_plan['plan_sha256'], generation_parent=wrong_parent)
        with pytest.raises(InputError, match='child_changed'):
            reconcile_connected_generation(first, wrong_child, grant=grant,
                signature_file=signature, trusted_old_head=old_head)
        assert connected_session_status(wrong_child)['stage'] == 'generation_pending'
        upgraded = RuntimeLedger(ledger_path, identity=grant['new_identity'], **limits)
        assert upgraded.snapshot()['calls'] == 1
        assert upgraded.snapshot()['closed_tasks'] == 1
        assert upgraded.generation_snapshot()['effects'] == []
        assert recovered['ledger']['receipt']['after_sha256'] == digest(upgraded.generation_snapshot())
        with pytest.raises(BudgetDenied, match='shared_task_closed'):
            upgraded.reserve('generation-task-0', .1)
        upgraded.release()
        current = connected_session_status(second)
        late_scope = _scope(current, plans[1][0], 'launch', cutoff + timedelta(minutes=1))
        with pytest.raises(InputError, match='connected_original_cutoff_expired'):
            launch_connected_session(second, scope=late_scope,
                approved_scope_sha256=late_scope['scope_sha256'])
        class LaterClock:
            @staticmethod
            def now(_timezone):
                return cutoff + timedelta(seconds=1)
        with monkeypatch.context() as patch:
            patch.setattr(connected_delivery, 'datetime', LaterClock)
            expired_scope = _scope(current, plans[1][0], 'launch', cutoff)
            with pytest.raises(InputError, match='connected_original_cutoff_expired'):
                launch_connected_session(second, scope=expired_scope,
                    approved_scope_sha256=expired_scope['scope_sha256'])
        assert connected_session_status(second)['launch_attempts'] == 0
        scope = _scope(current, plans[1][0], 'launch', cutoff)
        launch_connected_session(second, scope=scope, approved_scope_sha256=scope['scope_sha256'])
        deadline = time.monotonic() + 30
        while (not plans[1][2].is_file() or plans[1][2].read_bytes() != b'in-flight\n') and time.monotonic() < deadline:
            time.sleep(.02)
        assert plans[1][2].read_bytes() == b'in-flight\n'
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(.02)
        assert len(calls) == 2
        _wait_effect(second, plans[1][1], plans[1][4], plans[1][3])
        current = connected_session_status(second)
        stop_scope = _scope(current, plans[1][0], 'stop', cutoff)
        stopped = stop_connected_session(second, scope=stop_scope,
                                         approved_scope_sha256=stop_scope['scope_sha256'])
        assert stopped['stage'] == 'stopped'
        assert len(calls) == 2
        final = RuntimeLedger(ledger_path, identity=grant['new_identity'], **limits)
        snapshot = final.generation_snapshot()
        assert final.snapshot()['calls'] == 2
        assert final.snapshot()['closed_tasks'] == 2
        assert snapshot['effects'] == []  # Alpha records raw host effects outside the ledger.
        final.release()
        retained_ready = tmp_path / 'retained-ready.bin'
        retained_release = tmp_path / 'retained-release.bin'
        retained_effect = tmp_path / 'retained-effect.jsonl'
        retained_expected = (json.dumps({'task_id': 'generation-task-retained',
            'action': 'inspect', 'item': 'fixture-one'}, sort_keys=True,
            separators=(',', ':')) + '\n').encode()
        retained_observation = {'schema_version': '1.0',
            'kind': 'template-delivery-observation-v1',
            'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                        'expected_sha256': hashlib.sha256(expected).hexdigest()}
                       for role, path, expected in (
                           ('ready', retained_ready, b'in-flight\n'),
                           ('entrypoint_reached', retained_ready, b'in-flight\n'),
                           ('integration_reachable', retained_effect, retained_expected),
                           ('outcome_verified', retained_effect, retained_expected))]}
        retained_env = dict(plans[0][0]['off_provenance']['launch_environment'])
        retained_env.update({'REGISTERED_ALPHA_TASK_ID': 'generation-task-retained',
            'REGISTERED_ALPHA_AUDIT': str(tmp_path / 'retained-audit.jsonl'),
            'REGISTERED_ALPHA_EFFECTS': str(retained_effect),
            'REGISTERED_ALPHA_READY': str(retained_ready),
            'REGISTERED_ALPHA_RELEASE': str(retained_release)})
        retained_plan = plan_connected_delivery(installed[0]['plan'],
            trusted_install_receipt_sha256=installed[0]['receipt']['receipt_sha256'],
            trusted_package_receipt_sha256=installed[0]['plan']['package_receipt']['receipt_sha256'],
            installed_binding=installed[0]['binding'],
            trusted_binding_sha256=installed[0]['binding']['binding_sha256'],
            observation=retained_observation, launch_environment=retained_env)
        rollback = plan_connected_generation_transfer(second, retained_plan,
            trusted_old_head=stopped['session_head_sha256'],
            old_dependency_plan=dependencies[1], new_dependency_plan=dependencies[0],
            limits=limits, action='rollback',
            issued_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
            expires_at=cutoff.isoformat())
        rollback_signature = tmp_path / 'rollback-signature.txt'
        rollback_signature.write_text(issue(private, 'generation_transfer', digest(rollback)))
        rollback_signature.chmod(0o600)
        retained = tmp_path / 'session-retained'; sessions.append((retained, retained_plan))
        rollback_result = transfer_connected_generation(second, retained, retained_plan,
            trusted_old_head=stopped['session_head_sha256'],
            approved_new_plan_sha256=retained_plan['plan_sha256'],
            old_dependency_plan=dependencies[1], new_dependency_plan=dependencies[0],
            grant=rollback, signature_file=rollback_signature)
        assert rollback_result['child']['ledger']['status'] == 'committed'
        assert rollback_result['child']['run_id'] == created['run_id']
        restored = RuntimeLedger(ledger_path, identity=grant['old_identity'], **limits)
        assert restored.snapshot()['calls'] == 2
        assert restored.snapshot()['closed_tasks'] == 2
        assert restored.generation_snapshot()['effects'] == snapshot['effects']
        restored.release()
        assert rollback['new_identity'] == grant['old_identity']
        assert rollback['old_identity'] == grant['new_identity']
        assert rollback['history_sha256'] == digest(snapshot)
        stale = tmp_path / 'session-stale-transfer'
        create_connected_session(stale, plans[1][0],
            approved_plan_sha256=plans[1][0]['plan_sha256'], generation_parent=wrong_parent)
        historical = connected_generation_status(first, stale, grant=grant,
            signature_file=signature, trusted_old_head=old_head)
        assert historical['ledger']['status'] == 'committed'
        assert historical['ledger']['current_generation_grant_sha256'] == digest(rollback)
        with pytest.raises(InputError, match='stale_transfer'):
            reconcile_connected_generation(first, stale, grant=grant,
                signature_file=signature, trusted_old_head=old_head)
        assert connected_session_status(stale)['stage'] == 'generation_pending'
    finally:
        for path, plan in sessions:
            if path.exists():
                current = connected_session_status(path)
                if current['process_alive'] and current['stage'] in ('running','stop_pending'):
                    scope = _scope(current, plan, 'stop', datetime.now(timezone.utc)+timedelta(minutes=1))
                    stop_connected_session(path, scope=scope,
                                           approved_scope_sha256=scope['scope_sha256'])
        server.shutdown(); server.server_close(); thread.join(timeout=2)
