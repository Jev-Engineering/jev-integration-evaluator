"""Two freshly bound D hosts share one installed synthetic connected ledger."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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

from jev_integration_evaluator.budget import BudgetDenied
from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator.template_connected_delivery import (
    connected_session_status, create_connected_session, launch_connected_session,
    plan_connected_delivery, stop_connected_session,
)
from jev_integration_evaluator.template_connected_generation import (
    connected_generation_status, plan_connected_generation_transfer,
    reconcile_connected_generation, transfer_connected_generation,
)
from jev_integration_evaluator import template_connected_generation as generation
from tests.test_connected_installed_binding import _issuer, _issue, _verifier_identity
from tests.test_template_installation import _metadata
from tests.test_use_case_retrieval_bound_installed import _applied, _installed
from tests.test_use_case_retrieval_connected import LOADER
from tests.test_use_case_retrieval_host import PROFILE, _expected_effect


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='D connected generation needs Linux x86-64 CPython 3.13')


def _scope(status: dict, plan: dict, action: str, cutoff: datetime) -> dict:
    scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
             'run_id': status['run_id'], 'plan_sha256': plan['plan_sha256'],
             'public_key_sha256': plan['reference_sha256']['D_AUTH_PUBKEY_FILE'],
             'trusted_session_head': status['session_head_sha256'],
             'action': action, 'expires_at': cutoff.isoformat()}
    scope['scope_sha256'] = digest(scope)
    return scope


def _wait(path: Path, expected: bytes, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.is_file() and path.read_bytes() == expected:
            return
        time.sleep(.02)
    raise AssertionError('independent retrieval generation effect missing')


def test_bound_d_connected_upgrade_and_retained_rollback(tmp_path, monkeypatch):
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
    private, public = _issuer(tmp_path)
    cert, cert_key = tmp_path / 'loopback.crt', tmp_path / 'loopback.key'
    generated = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-nodes', '-keyout', str(cert_key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
        '-addext', 'subjectAltName=IP:127.0.0.1', '-days', '1'],
        capture_output=True, timeout=20)
    assert generated.returncode == 0
    cert.chmod(0o600); cert_key.chmod(0o600)
    calls: list[str] = []

    class LocalTypeSafe(BaseHTTPRequestHandler):
        def log_message(self, *_args):
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
                    choice = 'supports' if 'supports' in labels else labels[0]
                    answers[name] = {'type': 'choice', 'choice': choice,
                                     'confidence': 1.0,
                                     'probabilities': {label: float(label == choice)
                                                       for label in labels}}
            result = json.dumps({'model': request['model'], 'answers': answers,
                'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(result)))
            self.end_headers()
            self.wfile.write(result)

    server = ThreadingHTTPServer(('127.0.0.1', 0), LocalTypeSafe)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(str(cert), str(cert_key))
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sessions = []
    try:
        installed = []
        for index, (version, task) in enumerate((('1.0.0', 'retrieval-one'),
                                                  ('1.0.1', 'retrieval-two'))):
            host = _applied(tmp_path, f'bound-d-{index}', version, LOADER,
                            generation_task=task)
            install_plan, receipt = _installed(tmp_path, host, wheelhouse, rows,
                requirements, environments, f'package-d-{index}')
            binding = derive_installed_binding(install_plan['package_plan'],
                install_plan['package_receipt'], install_plan, receipt,
                trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
                trusted_install_receipt_sha256=receipt['receipt_sha256'])
            assert binding['origins']['loader']['wheel_member'] == \
                   'retrieval_host/connected_authority.py'
            assert binding['origins']['console']['sha256'] == \
                   file_hash(host['target'] / 'retrieval_host/console.py')
            installed.append((host, install_plan, receipt, binding, task))
        assert installed[0][3]['wheel_sha256'] != installed[1][3]['wheel_sha256']
        ledger = tmp_path / 'one-runtime.ledger'
        limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
                  'max_total_calls': 2, 'max_total_cost': 2,
                  'max_in_flight': 1, 'max_tasks': 2}
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(minutes=8)
        plans, dependencies, effects = [], [], []
        for index, (host, install_plan, receipt, binding, task) in enumerate(installed):
            site = Path(binding['site']) / 'retrieval_host'
            dependency = {'files': [{'path': str(site / name),
                'sha256': file_hash(site / name)} for name in ('requirements.lock', 'runtime.json')]}
            dependencies.append(dependency)
            tree = ast.parse(Path(binding['origins']['adapter']['path']).read_bytes())
            spec = ast.literal_eval(next(node.value for node in tree.body
                if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == 'SPEC'
                    for target in node.targets)))
            source_bindings = {binding['candidate_id']: {
                'reviewed_file_sha256': binding['reviewed_file_sha256'],
                'applied_file_sha256': binding['applied_file_sha256'],
                'adapter_path': binding['origins']['adapter']['wheel_member'],
                'adapter_sha256': binding['origins']['adapter']['sha256']}}
            environment_digest = digest({
                'python': str(Path(receipt['installed']['python']).resolve()),
                'version': list(sys.version_info[:3]),
                'implementation': platform.python_implementation(),
                'openssl': ssl.OPENSSL_VERSION, 'credential_present': True,
                'cert_sha256': file_hash(cert), 'signature_verifier': _verifier_identity(),
                'public_key_sha256': file_hash(public)})
            config = {'endpoint': f'https://127.0.0.1:{server.server_port}/v1/systemone',
                'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
                'environment_digest': environment_digest, 'source_root': binding['site'],
                'source_plan': binding['source_plan'], 'source_bindings': source_bindings,
                'installed_binding': binding}
            egress = {'endpoint': config['endpoint'], 'credential_ref': config['credential_ref'],
                'model': config['model'], 'environment_digest': environment_digest,
                'source_digest': digest({'root': binding['site'],
                    'plan': binding['source_plan'], 'bindings': source_bindings,
                    'installed_binding_sha256': binding['binding_sha256']}),
                'dependency_digest': digest(dependency), 'budget_digest': digest(limits),
                'adapters_digest': digest({binding['candidate_id']: digest(spec)}),
                'mode': 'shadow', 'issued_at': (now-timedelta(minutes=1)).isoformat(),
                'expires_at': cutoff.isoformat()}
            reference = tmp_path / f'reference-{index}.json'
            reference.write_text(json.dumps({'schema_version': '1.0', 'mode': 'shadow',
                'connected_config': config, 'authority': {'egress_grant': egress,
                'activation': None}, 'ledger_path': str(ledger), 'signatures': {
                'installed_binding': _issue(private, 'installed_binding', binding['binding_sha256']),
                'egress_grant': _issue(private, 'egress_grant', digest(egress))}}))
            reference.chmod(0o600)
            folder = tmp_path / f'effects-{index}'
            folder.mkdir(mode=0o700)
            raw = _expected_effect(host['corpus'])
            effect = folder / (task + '.json')
            ready = folder / 'ready.txt'
            observation = {'schema_version': '1.0',
                'kind': 'template-delivery-observation-v1', 'checks': [
                    {'role': role, 'path': str(path), 'before_sha256': None,
                     'expected_sha256': hashlib.sha256(expected).hexdigest()}
                    for role, path, expected in (
                        ('ready', ready, b'ready\n'),
                        ('entrypoint_reached', ready, b'ready\n'),
                        ('integration_reachable', effect, raw),
                        ('outcome_verified', effect, raw))]}
            plan = plan_connected_delivery(install_plan,
                trusted_install_receipt_sha256=receipt['receipt_sha256'],
                trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
                installed_binding=binding, trusted_binding_sha256=binding['binding_sha256'],
                observation=observation, host_profile='retrieval-d-v1',
                launch_environment={'D_CONNECTED_REF': str(reference),
                    'D_AUTH_PUBKEY_FILE': str(public), 'D_CORPUS_PATH': str(host['corpus']),
                    'D_EFFECT_DIRECTORY': str(folder), 'D_TASKS': 'two',
                    'D_HOLD': '1', 'D_RELEASE_PATH': str(folder / 'release.txt'),
                    'SSL_CERT_FILE': str(cert)})
            plans.append(plan)
            effects.append((effect, ready, folder / 'release.txt', raw))
        assert plans[0]['plan_sha256'] != plans[1]['plan_sha256']
        unknown_profile = dict(plans[1], host_profile='unregistered-host')
        unknown_profile['plan_sha256'] = digest({key: value for key, value in
            unknown_profile.items() if key != 'plan_sha256'})
        with pytest.raises(InputError):
            generation._installed(unknown_profile, {'files': []}, limits)
        with pytest.raises(InputError):
            generation._authority(unknown_profile, {}, tmp_path / 'absent-signature')
        with pytest.raises(InputError):
            create_connected_session(tmp_path / 'unknown-profile', unknown_profile,
                approved_plan_sha256=unknown_profile['plan_sha256'])
        dual_selector = dict(plans[1], host_profile='registered-dual-connected-v1')
        dual_selector['plan_sha256'] = digest({key: value for key, value in
            dual_selector.items() if key != 'plan_sha256'})
        with pytest.raises(InputError, match='profile_not_supported'):
            generation._authority(dual_selector, {}, tmp_path / 'absent-signature')
        with pytest.raises(InputError):
            generation._installed(dual_selector, {'files': []}, limits)
        monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')

        def launch_and_stop(path: Path, plan: dict, effect_row: tuple,
                            *, created: dict | None = None) -> dict:
            if created is None:
                created = create_connected_session(path, plan,
                    approved_plan_sha256=plan['plan_sha256'])
            sessions.append((path, plan))
            scope = _scope(created, plan, 'launch', cutoff)
            launch_connected_session(path, scope=scope,
                approved_scope_sha256=scope['scope_sha256'])
            effect, ready, release, raw = effect_row
            _wait(ready, b'ready\n')
            release.write_bytes(b'go\n')
            _wait(effect, raw)
            answer = json.loads(effect.read_bytes())['answer']
            assert answer['disposition'] == 'withheld_conflict'
            assert answer['answer'] is None
            assert [row['source_id'] for row in answer['passages']] == [
                'registry-one', 'registry-two', 'registry-three']
            deadline = time.monotonic() + 25
            status = connected_session_status(path)
            while status['process_alive'] and time.monotonic() < deadline:
                time.sleep(.02)
                status = connected_session_status(path)
            assert not status['process_alive']
            stop = _scope(status, plan, 'stop', cutoff)
            result = stop_connected_session(path, scope=stop,
                approved_scope_sha256=stop['scope_sha256'])
            assert result['stage'] == 'stopped'
            return result

        first = tmp_path / 'generation-100'
        stopped_first = launch_and_stop(first, plans[0], effects[0])
        assert len(calls) == 1
        old_head = stopped_first['session_head_sha256']
        issued = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        new_reference = Path(plans[1]['off_provenance']['launch_environment'][
            'D_CONNECTED_REF'])
        original_reference = new_reference.read_bytes()
        new_reference.write_bytes(original_reference + b'\n')
        with pytest.raises(InputError):
            plan_connected_generation_transfer(first, plans[1],
                trusted_old_head=old_head, old_dependency_plan=dependencies[0],
                new_dependency_plan=dependencies[1], limits=limits, action='upgrade',
                issued_at=issued, expires_at=cutoff.isoformat())
        assert len(calls) == 1
        new_reference.write_bytes(original_reference)
        corpus = installed[1][0]['corpus']
        original_corpus = corpus.read_bytes()
        corpus.write_bytes(original_corpus + b'\n')
        with pytest.raises(InputError):
            plan_connected_generation_transfer(first, plans[1],
                trusted_old_head=old_head, old_dependency_plan=dependencies[0],
                new_dependency_plan=dependencies[1], limits=limits, action='upgrade',
                issued_at=issued, expires_at=cutoff.isoformat())
        assert len(calls) == 1
        corpus.write_bytes(original_corpus)
        grant = plan_connected_generation_transfer(first, plans[1],
            trusted_old_head=old_head, old_dependency_plan=dependencies[0],
            new_dependency_plan=dependencies[1], limits=limits, action='upgrade',
            issued_at=issued, expires_at=cutoff.isoformat())
        assert grant['old_placements'] == [installed[0][3]['candidate_id']]
        assert grant['new_to_old_placements'] == {
            installed[1][3]['candidate_id']: installed[0][3]['candidate_id']}
        signature = tmp_path / 'upgrade-signature.txt'
        signature.write_text(_issue(private, 'generation_transfer', digest(grant)))
        signature.chmod(0o600)
        second = tmp_path / 'generation-101'
        transfer_args = dict(trusted_old_head=old_head,
            approved_new_plan_sha256=plans[1]['plan_sha256'],
            old_dependency_plan=dependencies[0], new_dependency_plan=dependencies[1],
            grant=grant, signature_file=signature)
        signature.write_text('invalid-signature')
        with pytest.raises(InputError, match='transfer_unverified'):
            transfer_connected_generation(first, second, plans[1], **transfer_args)
        assert not second.exists() and len(calls) == 1
        signature.write_text(_issue(private, 'generation_transfer', digest(grant)))
        new_reference.write_bytes(original_reference + b'\n')
        with pytest.raises(InputError):
            transfer_connected_generation(first, second, plans[1], **transfer_args)
        assert not second.exists() and len(calls) == 1
        new_reference.write_bytes(original_reference)
        def lost_ack(*_args, **_kwargs):
            raise RuntimeError('synthetic controller exit after durable transfer')
        with monkeypatch.context() as patch:
            patch.setattr(generation, 'reconcile_connected_generation', lost_ack)
            with pytest.raises(RuntimeError, match='controller exit'):
                transfer_connected_generation(first, second, plans[1], **transfer_args)
        pending = connected_generation_status(first, second, grant=grant,
            signature_file=signature, trusted_old_head=old_head)
        assert pending['ledger']['status'] == 'committed'
        assert pending['child_stage'] == 'generation_pending'
        def replan(index: int, label: str, *, reuse_effect_directory: Path | None = None):
            host, install_plan, receipt, binding, task = installed[index]
            folder = reuse_effect_directory or tmp_path / label
            if reuse_effect_directory is None:
                folder.mkdir(mode=0o700)
                effect, ready, release = folder / (task + '.json'), \
                    folder / 'ready.txt', folder / 'release.txt'
                ready_bytes = b'ready\n'
            else:
                release = tmp_path / (label + '-release.txt')
                ready = release.with_suffix('.attempt')
                effect = tmp_path / (label + '-new-effect.json')
                ready_bytes = b'attempt\n'
            raw = _expected_effect(host['corpus'])
            observation = {'schema_version': '1.0',
                'kind': 'template-delivery-observation-v1', 'checks': [
                    {'role': role, 'path': str(path), 'before_sha256': None,
                    'expected_sha256': hashlib.sha256(expected).hexdigest()}
                    for role, path, expected in (
                        ('ready', ready, ready_bytes),
                        ('entrypoint_reached', ready, ready_bytes),
                        ('integration_reachable', effect, raw),
                        ('outcome_verified', effect, raw))]}
            launch_environment = dict(plans[index]['off_provenance']['launch_environment'])
            launch_environment['D_EFFECT_DIRECTORY'] = str(folder)
            launch_environment['D_RELEASE_PATH'] = str(release)
            candidate = plan_connected_delivery(install_plan,
                trusted_install_receipt_sha256=receipt['receipt_sha256'],
                trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
                installed_binding=binding, trusted_binding_sha256=binding['binding_sha256'],
                observation=observation, host_profile='retrieval-d-v1',
                launch_environment=launch_environment)
            return candidate, (effect, ready, release, raw)

        wrong, _ = replan(1, 'wrong-plan-effects')
        wrong_child = tmp_path / 'wrong-plan-child'
        parent = generation.delivery._open(second)[2]['generation_parent']
        create_connected_session(wrong_child, wrong,
            approved_plan_sha256=wrong['plan_sha256'], generation_parent=parent)
        with pytest.raises(InputError, match='child_changed'):
            reconcile_connected_generation(first, wrong_child, grant=grant,
                signature_file=signature, trusted_old_head=old_head)
        assert connected_session_status(wrong_child)['stage'] == 'generation_pending'
        stale = tmp_path / 'stale-child'
        create_connected_session(stale, plans[1],
            approved_plan_sha256=plans[1]['plan_sha256'], generation_parent=parent)
        reconciled = reconcile_connected_generation(first, second, grant=grant,
            signature_file=signature, trusted_old_head=old_head)
        assert reconciled['child_stage'] == 'installed'
        assert reconciled['run_id'] == stopped_first['run_id']
        before = RuntimeLedger(ledger, identity=grant['new_identity'], **limits)
        assert before.snapshot()['calls'] == 1
        with pytest.raises(BudgetDenied, match='shared_task_closed'):
            before.reserve('retrieval-one', .1)
        before.release()
        stopped_second = launch_and_stop(second, plans[1], effects[1],
            created=connected_session_status(second))
        assert len(calls) == 2
        current = RuntimeLedger(ledger, identity=grant['new_identity'], **limits)
        assert current.snapshot()['calls'] == 2
        assert current.snapshot()['closed_tasks'] == 2
        current.release()
        first_effect_directory = effects[0][0].parent
        original_effect_files = {path.name: path.read_bytes()
            for path in first_effect_directory.iterdir() if path.is_file()}
        retained_plan, retained_effects = replan(0, 'retained-refusal',
            reuse_effect_directory=first_effect_directory)
        rollback = plan_connected_generation_transfer(second, retained_plan,
            trusted_old_head=stopped_second['session_head_sha256'],
            old_dependency_plan=dependencies[1], new_dependency_plan=dependencies[0],
            limits=limits, action='rollback',
            issued_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
            expires_at=cutoff.isoformat())
        rollback_signature = tmp_path / 'rollback-signature.txt'
        rollback_signature.write_text(_issue(private, 'generation_transfer', digest(rollback)))
        rollback_signature.chmod(0o600)
        retained = tmp_path / 'generation-retained'
        result = transfer_connected_generation(second, retained, retained_plan,
            trusted_old_head=stopped_second['session_head_sha256'],
            approved_new_plan_sha256=retained_plan['plan_sha256'],
            old_dependency_plan=dependencies[1], new_dependency_plan=dependencies[0],
            grant=rollback, signature_file=rollback_signature)
        assert result['child']['ledger']['status'] == 'committed'
        assert result['child']['run_id'] == stopped_first['run_id']
        retained_ledger = RuntimeLedger(ledger, identity=grant['old_identity'], **limits)
        assert retained_ledger.snapshot()['calls'] == 2
        assert retained_ledger.snapshot()['closed_tasks'] == 2
        retained_ledger.release()
        assert rollback['new_identity'] == grant['old_identity']
        assert rollback['old_identity'] == grant['new_identity']
        retained_status = connected_session_status(retained)
        retained_scope = _scope(retained_status, retained_plan, 'launch', cutoff)
        sessions.append((retained, retained_plan))
        launch_connected_session(retained, scope=retained_scope,
            approved_scope_sha256=retained_scope['scope_sha256'])
        deadline = time.monotonic() + 25
        retained_status = connected_session_status(retained)
        while retained_status['process_alive'] and time.monotonic() < deadline:
            time.sleep(.02)
            retained_status = connected_session_status(retained)
        assert not retained_status['process_alive']
        assert not retained_effects[0].exists()
        assert retained_effects[1].read_bytes() == b'attempt\n'
        assert {path.name: path.read_bytes() for path in first_effect_directory.iterdir()
                if path.is_file()} == original_effect_files
        assert len(calls) == 2
        retained_stop = _scope(retained_status, retained_plan, 'stop', cutoff)
        stopped_retained = stop_connected_session(retained, scope=retained_stop,
            approved_scope_sha256=retained_stop['scope_sha256'])
        assert stopped_retained['stage'] == 'stopped'
        after_refusal = RuntimeLedger(ledger, identity=grant['old_identity'], **limits)
        assert after_refusal.snapshot()['calls'] == 2
        assert after_refusal.snapshot()['closed_tasks'] == 2
        after_refusal.release()
        assert effects[0][0].read_bytes() == _expected_effect(installed[0][0]['corpus'])
        assert effects[1][0].read_bytes() == _expected_effect(installed[1][0]['corpus'])
        historical = connected_generation_status(first, stale, grant=grant,
            signature_file=signature, trusted_old_head=old_head)
        assert historical['ledger']['status'] == 'committed'
        with pytest.raises(InputError, match='stale_transfer'):
            reconcile_connected_generation(first, stale, grant=grant,
                signature_file=signature, trusted_old_head=old_head)
        assert connected_session_status(stale)['stage'] == 'generation_pending'
        revoked = RuntimeLedger(ledger, identity=rollback['new_identity'], **limits)
        revoked.suspend()
        revoked.release()
        prospective, _ = replan(1, 'revoked-transfer-effects')
        refused = tmp_path / 'revoked-child'
        with pytest.raises(InputError, match='runtime_ledger_revoked'):
            plan_connected_generation_transfer(retained, prospective,
                trusted_old_head=stopped_retained['session_head_sha256'],
                old_dependency_plan=dependencies[0], new_dependency_plan=dependencies[1],
                limits=limits, action='upgrade',
                issued_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
                expires_at=cutoff.isoformat())
        assert not refused.exists()
        assert len(calls) == 2
    finally:
        for path, plan in sessions:
            if path.exists():
                status = connected_session_status(path)
                if status['process_alive']:
                    scope = _scope(status, plan, 'stop',
                        datetime.now(timezone.utc)+timedelta(minutes=1))
                    stop_connected_session(path, scope=scope,
                        approved_scope_sha256=scope['scope_sha256'])
        server.shutdown(); server.server_close(); thread.join(timeout=2)
