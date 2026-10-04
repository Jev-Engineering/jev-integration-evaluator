"""Shared installed journey for a finite-profile stopped generation transfer.

Two separately reviewed and bound hosts of one use case run their normal
installed console under local synthetic TLS shadow and share one durable
ledger. Only the host builder, private reference names, launch environment
and raw-effect readback differ between profiles; they are supplied by the
calling test module. Nothing here reaches a real provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
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
from typing import Callable

import pytest

from jev_integration_evaluator.budget import BudgetDenied
from jev_integration_evaluator.io import InputError, digest, file_hash, read_json
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
from jev_integration_evaluator.template_connected_binding import derive_installed_binding
from jev_integration_evaluator import template_connected_delivery as connected_delivery
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


LIMITS = {'max_calls_per_task': 2, 'max_cost_per_task': 2,
          'max_total_calls': 2, 'max_total_cost': 2,
          'max_in_flight': 1, 'max_tasks': 2}


def synthetic_typed_answers(questions, preferred_label=None):
    """Existing synthetic local protocol shape; never a real Jev result."""
    answers = {}
    for name, question in questions.items():
        if question['type'] == 'noul':
            answers[name] = {'type': 'noul', 'noul': 1.0}
        else:
            labels = list(question['criteria'])
            choice = preferred_label if preferred_label in labels else labels[0]
            answers[name] = {'type': 'choice', 'choice': choice, 'confidence': 1.0,
                'probabilities': {label: float(label == choice) for label in labels}}
    return answers


@dataclass(frozen=True)
class GenerationJourney:
    """Profile-owned inputs; none of these grants authority."""
    host_profile: str
    package: str
    reference_name: str
    public_name: str
    release_name: str
    tasks: tuple[str, str]
    preferred_label: str | None
    other_profiles: tuple[str, ...]
    # (tmp_path, index, version, task, wheelhouse, rows, requirements) ->
    # (host, install_plan, install_receipt)
    install: Callable[..., tuple[dict, dict, dict]]
    # (fresh private folder, task) -> {'environment', 'ready', 'release',
    # 'effects': [(path, raw), ...]}; the last effect is the observed outcome.
    layout: Callable[[Path, str], dict]
    # Independent semantic readback of one generation's raw effect.
    verify: Callable[[dict, str], None]
    # A separately installed, valid host of another finite profile. It is
    # only planned, never launched.
    foreign: 'GenerationJourney | None' = None
    composite: bool = False
    calls_per_generation: int = 1
    replay_headroom: int = 0


def _placements(binding: dict) -> dict:
    return binding['placements'] if 'placements' in binding else {binding['candidate_id']: binding}


def _candidate(binding: dict) -> str:
    return sorted(_placements(binding))[0]


def _origins(binding: dict) -> dict:
    return binding['shared_origins'] if 'shared_origins' in binding else binding['origins']


@contextmanager
def _unsigned_refusal_clock(monkeypatch, cutoff: datetime):
    """Isolate final planner refusal gates without extending any live authority."""
    class InScopeClock:
        @staticmethod
        def now(_timezone):
            return cutoff - timedelta(seconds=1)
    # No launcher, runtime, signer or delivery clock is changed. This context
    # surrounds only the unsigned durable-revocation negative, after every
    # actual launch and transfer has finished.
    with monkeypatch.context() as patch:
        patch.setattr(generation, 'datetime', InScopeClock)
        yield (cutoff - timedelta(seconds=2)).isoformat()


def _scope(status: dict, plan: dict, action: str, cutoff: datetime, public_name: str) -> dict:
    scope = {'schema_version': '1.0', 'kind': 'connected-delivery-scope-v1',
             'run_id': status['run_id'], 'plan_sha256': plan['plan_sha256'],
             'public_key_sha256': plan['reference_sha256'][public_name],
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
    raise AssertionError('independent generation effect missing')


def _exited(session: Path, seconds: float = 25) -> dict:
    deadline = time.monotonic() + seconds
    status = connected_session_status(session)
    while status['process_alive'] and time.monotonic() < deadline:
        time.sleep(.02)
        status = connected_session_status(session)
    assert not status['process_alive']
    return status


def _history(ledger: Path, identity: str, limits: dict = LIMITS) -> tuple[dict, dict]:
    """Read the durable ledger as its only owner; no console may be running."""
    owner = RuntimeLedger(ledger, identity=identity, **limits)
    try:
        return owner.snapshot(), owner.generation_snapshot()
    finally:
        owner.release()


def _durable_identity(ledger: Path) -> str:
    """Read-only SQLite inspection after the console has exited."""
    database = Path(str(ledger) + '.sqlite')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1) as db:
        return json.loads(db.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])[
            'identity']


def _retained_accounting(history: dict) -> dict:
    """Everything a transfer must keep: spend, task tombstones, revocation."""
    return {name: value for name, value in history['state'].items()
            if name not in ('identity', 'generation')}


def _observation(ready: Path, ready_bytes: bytes, effect: Path, raw: bytes) -> dict:
    return {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
            'checks': [{'role': role, 'path': str(path), 'before_sha256': None,
                        'expected_sha256': hashlib.sha256(expected).hexdigest()}
                       for role, path, expected in (
                           ('ready', ready, ready_bytes),
                           ('entrypoint_reached', ready, ready_bytes),
                           ('integration_reachable', effect, raw),
                           ('outcome_verified', effect, raw))]}


def _relabelled(plan: dict, **changes) -> dict:
    changed = dict(plan, **changes)
    changed['plan_sha256'] = digest({key: value for key, value in changed.items()
                                    if key != 'plan_sha256'})
    return changed


def run_generation_journey(tmp_path: Path, monkeypatch, journey: GenerationJourney) -> dict:
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
    private, public = _issuer(tmp_path)
    foreign_directory = tmp_path / 'foreign-issuer'
    foreign_directory.mkdir(mode=0o700)
    foreign_private, _ = _issuer(foreign_directory)
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
            answers = synthetic_typed_answers(request['questions'], journey.preferred_label)
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
    sessions: list[tuple[Path, dict]] = []
    reference_name, public_name = journey.reference_name, journey.public_name
    scope = lambda status, plan, action, expires: _scope(
        status, plan, action, expires, public_name)
    try:
        ledger = tmp_path / 'one-runtime.ledger'
        limits = dict(LIMITS, max_total_calls=2 * journey.calls_per_generation + journey.replay_headroom,
                      max_total_cost=2 * journey.calls_per_generation + journey.replay_headroom)
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(minutes=10)
        hosts = [(journey, '1.0.0', journey.tasks[0]), (journey, '1.0.1', journey.tasks[1])]
        if journey.foreign is not None:
            assert journey.foreign.host_profile != journey.host_profile
            hosts.append((journey.foreign, '1.0.0', journey.foreign.tasks[0]))

        def planned(index: int, observation: dict, environment: dict) -> dict:
            _, install_plan, receipt, binding, _ = installed[index]
            return plan_connected_delivery(install_plan,
                trusted_install_receipt_sha256=receipt['receipt_sha256'],
                trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
                installed_binding=binding, trusted_binding_sha256=binding['binding_sha256'],
                observation=observation, host_profile=hosts[index][0].host_profile,
                launch_environment=environment)

        installed, plans, dependencies, layouts = [], [], [], []
        for index, (shape, version, task) in enumerate(hosts):
            host, install_plan, receipt = shape.install(
                tmp_path, index, version, task, wheelhouse, rows, requirements)
            if shape.composite:
                from jev_integration_evaluator.template_connected_composite_binding import derive_installed_composite_binding
                derive = derive_installed_composite_binding
            else:
                derive = derive_installed_binding
            binding = derive(install_plan['package_plan'],
                install_plan['package_receipt'], install_plan, receipt,
                trusted_package_receipt_sha256=install_plan['package_receipt']['receipt_sha256'],
                trusted_install_receipt_sha256=receipt['receipt_sha256'])
            shared_origins = binding['shared_origins'] if shape.composite else binding['origins']
            placements = binding['placements'] if shape.composite else {binding['candidate_id']: binding}
            assert shared_origins['loader']['wheel_member'] == \
                   shape.package + '/connected_authority.py'
            assert shared_origins['console']['sha256'] == \
                   file_hash(host['target'] / shape.package / 'console.py')
            assert receipt['installed']['distributions'][
                ('jev-independent-registered-dual-connected' if shape.composite else
                 'jev-' + shape.package.replace('_host', '') + '-host-fixture')] == version
            installed.append((host, install_plan, receipt, binding, task))
            site = Path(binding['site']) / shape.package
            dependency = {'files': [{'path': str(site / name),
                'sha256': file_hash(site / name)} for name in ('requirements.lock', 'runtime.json')]}
            dependencies.append(dependency)
            specs, source_bindings = {}, {}
            for candidate, placement in placements.items():
                spec = generation._literal_spec(Path(placement['origins']['adapter']['path']))
                specs[candidate] = digest(spec)
                source_bindings[candidate] = {
                    'reviewed_file_sha256': placement['reviewed_file_sha256'],
                    'applied_file_sha256': placement['applied_file_sha256'],
                    'adapter_path': placement['origins']['adapter']['wheel_member'],
                    'adapter_sha256': placement['origins']['adapter']['sha256']}
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
                'adapters_digest': digest(specs),
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
            layout = shape.layout(folder, task)
            assert shape.release_name in layout['environment']
            environment = {shape.reference_name: str(reference),
                           shape.public_name: str(public),
                           **layout['environment'], 'SSL_CERT_FILE': str(cert)}
            observed_path, observed_raw = layout['effects'][-1]
            plans.append(planned(index, _observation(
                layout['ready'], b'ready\n', observed_path, observed_raw), environment))
            layouts.append(layout)
        assert installed[0][2]['installed']['distributions'] != installed[1][2]['installed']['distributions']
        assert installed[0][3]['site'] != installed[1][3]['site']
        assert installed[0][3]['binding_sha256'] != installed[1][3]['binding_sha256']
        assert plans[0]['plan_sha256'] != plans[1]['plan_sha256']
        assert all(plan['host_profile'] == journey.host_profile for plan in plans[:2])
        unknown_profile = _relabelled(plans[1], host_profile='unregistered-host')
        with pytest.raises(InputError):
            generation._installed(unknown_profile, {'files': []}, limits)
        with pytest.raises(InputError):
            generation._authority(unknown_profile, {}, tmp_path / 'absent-signature')
        with pytest.raises(InputError):
            create_connected_session(tmp_path / 'unknown-profile', unknown_profile,
                approved_plan_sha256=unknown_profile['plan_sha256'])
        dual_selector = _relabelled(plans[1], host_profile='registered-dual-connected-v1')
        with pytest.raises(InputError):
            generation._authority(dual_selector, {}, tmp_path / 'absent-signature')
        with pytest.raises(InputError):
            generation._installed(dual_selector, {'files': []}, limits)
        monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-local-only')

        def launch_and_stop(path: Path, plan: dict, layout: dict, task: str,
                            *, created: dict | None = None) -> dict:
            if created is None:
                created = create_connected_session(path, plan,
                    approved_plan_sha256=plan['plan_sha256'])
            sessions.append((path, plan))
            launch = scope(created, plan, 'launch', cutoff)
            launch_connected_session(path, scope=launch,
                approved_scope_sha256=launch['scope_sha256'])
            _wait(layout['ready'], b'ready\n')
            layout['release'].write_bytes(b'go\n')
            for effect, raw in layout['effects']:
                _wait(effect, raw)
            journey.verify(layout, task)
            status = _exited(path)
            # The source-authored startup owner marker of this generation.
            assert (layout['ready'].parent / 'owner.txt').read_bytes() == \
                   b'one-runtime-startup\n'
            assert layout['release'].with_suffix('.attempt').read_bytes() == b'attempt\n'
            assert all(status['independent_checks'].values())
            stop = scope(status, plan, 'stop', cutoff)
            result = stop_connected_session(path, scope=stop,
                approved_scope_sha256=stop['scope_sha256'])
            assert result['stage'] == 'stopped'
            return result

        def replan(index: int, label: str, *, reuse: dict | None = None,
                   reference: Path | None = None) -> tuple[dict, dict]:
            task = installed[index][4]
            environment = dict(plans[index]['off_provenance']['launch_environment'])
            if reference is not None:
                environment[reference_name] = str(reference)
            if reuse is None:
                folder = tmp_path / label
                folder.mkdir(mode=0o700)
                layout = journey.layout(folder, task)
                environment.update(layout['environment'])
                observed_path, observed_raw = layout['effects'][-1]
                observation = _observation(layout['ready'], b'ready\n',
                                           observed_path, observed_raw)
            else:
                # The retained console keeps the original private effect
                # paths. Only its release path, and so its source-authored
                # attempt marker, is new; the observed effect path stays absent.
                release = tmp_path / (label + '-release.txt')
                environment[journey.release_name] = str(release)
                if journey.composite:
                    environment['DUAL_AUDIT_PATH'] = str(release.with_suffix('.audit.json'))
                layout = {'release': release, 'ready': release.with_suffix('.attempt'),
                          'effects': [(tmp_path / (label + '-new-effect.json'),
                                       reuse['effects'][-1][1])]}
                observation = _observation(layout['ready'], b'attempt\n',
                                           *layout['effects'][-1])
            return planned(index, observation, environment), layout

        first = tmp_path / 'generation-100'
        stopped_first = launch_and_stop(first, plans[0], layouts[0], journey.tasks[0])
        assert len(calls) == journey.calls_per_generation
        old_head = stopped_first['session_head_sha256']
        issued = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        plan_args = dict(trusted_old_head=old_head, old_dependency_plan=dependencies[0],
            new_dependency_plan=dependencies[1], limits=limits, action='upgrade',
            issued_at=issued, expires_at=cutoff.isoformat())
        new_reference = Path(plans[1]['off_provenance']['launch_environment'][reference_name])
        original_reference = new_reference.read_bytes()
        new_reference.write_bytes(original_reference + b'\n')
        with pytest.raises(InputError):
            plan_connected_generation_transfer(first, plans[1], **plan_args)
        assert len(calls) == journey.calls_per_generation
        new_reference.write_bytes(original_reference)
        # A separately signed later egress grant for the same installed bytes
        # is a valid delivery plan but cannot outlive the original cutoff.
        late_manifest = json.loads(original_reference)
        late_manifest['authority']['egress_grant']['expires_at'] = (
            cutoff + timedelta(minutes=1)).isoformat()
        late_manifest['signatures']['egress_grant'] = _issue(private, 'egress_grant',
            digest(late_manifest['authority']['egress_grant']))
        late_reference = tmp_path / 'reference-late.json'
        late_reference.write_text(json.dumps(late_manifest))
        late_reference.chmod(0o600)
        late_plan, _ = replan(1, 'late-egress-effects', reference=late_reference)
        assert late_plan['plan_sha256'] != plans[1]['plan_sha256']
        with pytest.raises(InputError, match='^connected_generation_scope_invalid$'):
            plan_connected_generation_transfer(first, late_plan, **plan_args)
        # The same installed bytes presented under any other finite profile
        # are not a second generation of this host.
        refusals = {}
        for other in (*journey.other_profiles, None):
            assert other != journey.host_profile
            relabelled = _relabelled({key: value for key, value in plans[1].items()
                                      if key != 'host_profile'},
                                     **({} if other is None else {'host_profile': other}))
            with pytest.raises(InputError) as refused:
                plan_connected_generation_transfer(first, relabelled, **plan_args)
            refusals[other] = str(refused.value)
        assert set(refusals.values()) == {'Invalid connected-delivery-plan-v1 contract'}
        if journey.foreign is not None:
            # A genuinely valid installed plan of another finite profile, with
            # the same ledger, issuer key, limits and cutoff, is refused by
            # the controller's own profile comparison.
            assert plans[2]['host_profile'] == journey.foreign.host_profile
            with pytest.raises(InputError, match='^connected_generation_scope_invalid$'):
                plan_connected_generation_transfer(first, plans[2],
                    **dict(plan_args, new_dependency_plan=dependencies[2]))
        assert not (tmp_path / 'generation-101').exists() and len(calls) == journey.calls_per_generation
        # The fixture console records its raw effect in host files. This
        # test-authored, clearly synthetic completed claim uses the real
        # installed placement so effect-claim retention is not vacuous.
        old_identity = _durable_identity(ledger)
        synthetic_claim = (journey.tasks[0], digest({'synthetic': 'generation effect claim'}),
                           'registry:synthetic-generation-effect')
        owner = RuntimeLedger(ledger, identity=old_identity, **limits)
        try:
            console_effects = owner.generation_snapshot()['effects']
            assert all(status == 'completed' for _, status in console_effects)
            actual_claims = []
            if journey.composite:
                request = {'task_id': journey.tasks[0], 'item': 'fixture-one',
                           'intent': 'summarize', 'permit': True, 'approved': True,
                           'allowed': True, 'complete_allowed': True}
                for placement, row in _placements(installed[0][3]).items():
                    operation = ('owner:public_entry' if row['source_file'].endswith('/alpha.py')
                                 else 'owner:handle_job')
                    actual_claim = (journey.tasks[0], digest(request), placement, operation)
                    actual_key = digest([old_identity, digest(journey.tasks[0]),
                                         digest(request), placement, operation])
                    assert [actual_key, 'completed'] in console_effects
                    with pytest.raises(InputError, match='^runtime_effect_already_claimed$'):
                        owner.claim_effect(*actual_claim)
                    actual_claims.append(actual_claim)

            claim_key = owner.claim_effect(*synthetic_claim[:2],
                _candidate(installed[0][3]), synthetic_claim[2])
            owner.complete_effect(claim_key)
        finally:
            owner.release()
        grant = plan_connected_generation_transfer(first, plans[1], **plan_args)
        assert grant['old_placements'] == sorted(_placements(installed[0][3]))
        assert set(grant['new_to_old_placements']) == set(_placements(installed[1][3]))
        assert set(grant['new_to_old_placements'].values()) == set(_placements(installed[0][3]))
        assert grant['old_binding_sha256'] == installed[0][3]['binding_sha256']
        assert grant['new_binding_sha256'] == installed[1][3]['binding_sha256']
        assert grant['old_identity'] == old_identity
        before_snapshot, before_history = _history(ledger, grant['old_identity'], limits)
        assert grant['history_sha256'] == digest(before_history)
        assert before_history['effects'] == sorted(
            console_effects + [[claim_key, 'completed']])
        assert before_snapshot['calls'] == journey.calls_per_generation and before_snapshot['closed_tasks'] == 1
        assert before_snapshot['tasks'] == 1 and before_snapshot['in_flight'] == 0
        assert all(status == 'completed' for _, status in before_history['effects'])
        signature = tmp_path / 'upgrade-signature.txt'
        exact_signature = _issue(private, 'generation_transfer', digest(grant))
        signature.write_text(exact_signature)
        signature.chmod(0o600)
        second = tmp_path / 'generation-101'
        transfer_args = dict(trusted_old_head=old_head,
            approved_new_plan_sha256=plans[1]['plan_sha256'],
            old_dependency_plan=dependencies[0], new_dependency_plan=dependencies[1],
            grant=grant, signature_file=signature)
        signature.write_text('invalid-signature')
        with pytest.raises(InputError, match='transfer_unverified'):
            transfer_connected_generation(first, second, plans[1], **transfer_args)
        assert not second.exists() and len(calls) == journey.calls_per_generation
        # A well-formed P-256 signature over the exact grant by another key.
        signature.write_text(_issue(foreign_private, 'generation_transfer', digest(grant)))
        with pytest.raises(InputError, match='transfer_unverified'):
            transfer_connected_generation(first, second, plans[1], **transfer_args)
        assert not second.exists() and len(calls) == journey.calls_per_generation
        # The trusted issuer's signature over a different grant digest.
        other_grant = dict(grant, history_sha256=digest('another ledger history'))
        assert digest(other_grant) != digest(grant)
        signature.write_text(_issue(private, 'generation_transfer', digest(other_grant)))
        with pytest.raises(InputError, match='transfer_unverified'):
            transfer_connected_generation(first, second, plans[1], **transfer_args)
        assert not second.exists() and len(calls) == journey.calls_per_generation
        # That signature does authenticate the other grant, which is still
        # not the grant derived from the stopped session and its ledger.
        with pytest.raises(InputError, match='exact_grant_required'):
            transfer_connected_generation(first, second, plans[1],
                **dict(transfer_args, grant=other_grant))
        assert not second.exists() and len(calls) == journey.calls_per_generation
        signature.write_text(exact_signature)
        new_reference.write_bytes(original_reference + b'\n')
        with pytest.raises(InputError):
            transfer_connected_generation(first, second, plans[1], **transfer_args)
        assert not second.exists() and len(calls) == journey.calls_per_generation
        new_reference.write_bytes(original_reference)
        # No refusal above changed the durable ledger or its identity.
        assert _history(ledger, grant['old_identity'], limits)[1] == before_history
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
        status_args = dict(grant=grant, signature_file=signature, trusted_old_head=old_head)

        wrong, _ = replan(1, 'wrong-plan-effects')
        wrong_child = tmp_path / 'wrong-plan-child'
        parent = connected_delivery._open(second)[2]['generation_parent']
        assert parent == {'run_id': stopped_first['run_id'],
                          'old_plan_sha256': plans[0]['plan_sha256'],
                          'old_session_head_sha256': old_head, 'grant_sha256': digest(grant),
                          'action': 'upgrade', 'original_expires_at': cutoff.isoformat(),
                          'failure_history': []}
        create_connected_session(wrong_child, wrong,
            approved_plan_sha256=wrong['plan_sha256'], generation_parent=parent)
        with pytest.raises(InputError, match='child_changed'):
            reconcile_connected_generation(first, wrong_child, **status_args)
        assert connected_session_status(wrong_child)['stage'] == 'generation_pending'
        # A child of the approved plan whose recorded parent link differs in
        # any one field is not the child this grant prepared.
        altered_links = {
            'later-cutoff': dict(parent, original_expires_at=(
                cutoff + timedelta(minutes=1)).isoformat()),
            'added-failure': dict(parent, failure_history=['provider_timeout']),
        }
        for label, altered in altered_links.items():
            assert altered != parent
            child = tmp_path / ('altered-parent-' + label)
            created = create_connected_session(child, plans[1],
                approved_plan_sha256=plans[1]['plan_sha256'], generation_parent=altered)
            with pytest.raises(InputError, match='^connected_generation_child_changed$'):
                connected_generation_status(first, child, **status_args)
            with pytest.raises(InputError, match='^connected_generation_child_changed$'):
                reconcile_connected_generation(first, child, **status_args)
            assert connected_session_status(child)['stage'] == 'generation_pending'
            refused = scope(created, plans[1], 'launch', cutoff)
            with pytest.raises(InputError):
                launch_connected_session(child, scope=refused,
                    approved_scope_sha256=refused['scope_sha256'])
            assert connected_session_status(child)['launch_attempts'] == 0
        assert len(calls) == journey.calls_per_generation
        stale = tmp_path / 'stale-child'
        create_connected_session(stale, plans[1],
            approved_plan_sha256=plans[1]['plan_sha256'], generation_parent=parent)
        reconciled = reconcile_connected_generation(first, second, **status_args)
        assert reconciled['child_stage'] == 'installed'
        assert reconciled['run_id'] == stopped_first['run_id']
        # Independent read-back under the new identity: nothing was reset.
        upgraded_snapshot, upgraded_history = _history(ledger, grant['new_identity'], limits)
        assert upgraded_snapshot['calls'] == journey.calls_per_generation and upgraded_snapshot['closed_tasks'] == 1
        assert _retained_accounting(upgraded_history) == _retained_accounting(before_history)
        assert upgraded_history['effects'] == before_history['effects']
        assert upgraded_history['state']['identity'] == grant['new_identity']
        assert upgraded_history['state']['generation']['grant_sha256'] == digest(grant)
        assert reconciled['ledger']['receipt']['before_sha256'] == digest(before_history)
        assert reconciled['ledger']['receipt']['after_sha256'] == digest(upgraded_history)
        with pytest.raises(InputError, match='identity_or_limits_changed'):
            RuntimeLedger(ledger, identity=grant['old_identity'], **limits)
        before = RuntimeLedger(ledger, identity=grant['new_identity'], **limits)
        try:
            with pytest.raises(BudgetDenied, match='shared_task_closed'):
                before.reserve(journey.tasks[0], .1)
            # The retained claim maps the new placement to the original one.
            with pytest.raises(InputError, match='^runtime_effect_already_claimed$'):
                before.claim_effect(*synthetic_claim[:2],
                    _candidate(installed[1][3]), synthetic_claim[2])
            with pytest.raises(InputError,
                               match='^runtime_effect_unregistered_generation_placement$'):
                before.claim_effect(*synthetic_claim[:2], 'unreviewed-placement',
                                    synthetic_claim[2])
            assert before.generation_snapshot() == upgraded_history
        finally:
            before.release()
        # The child cannot extend the original cutoff by scope or by clock.
        current = connected_session_status(second)
        late_scope = scope(current, plans[1], 'launch', cutoff + timedelta(minutes=1))
        with pytest.raises(InputError, match='connected_original_cutoff_expired'):
            launch_connected_session(second, scope=late_scope,
                approved_scope_sha256=late_scope['scope_sha256'])
        class LaterClock:
            @staticmethod
            def now(_timezone):
                return cutoff + timedelta(seconds=1)
        with monkeypatch.context() as patch:
            patch.setattr(connected_delivery, 'datetime', LaterClock)
            expired_scope = scope(current, plans[1], 'launch', cutoff)
            with pytest.raises(InputError, match='connected_original_cutoff_expired'):
                launch_connected_session(second, scope=expired_scope,
                    approved_scope_sha256=expired_scope['scope_sha256'])
        assert connected_session_status(second)['launch_attempts'] == 0
        assert len(calls) == journey.calls_per_generation
        stopped_second = launch_and_stop(second, plans[1], layouts[1], journey.tasks[1],
            created=connected_session_status(second))
        assert stopped_second['run_id'] == stopped_first['run_id']
        assert len(calls) == 2 * journey.calls_per_generation
        current_snapshot, current_history = _history(ledger, grant['new_identity'], limits)
        assert current_snapshot['calls'] == 2 * journey.calls_per_generation and current_snapshot['closed_tasks'] == 2
        assert current_snapshot['tasks'] == 2 and current_snapshot['in_flight'] == 0
        assert {tuple(row) for row in before_history['effects']} <= {
            tuple(row) for row in current_history['effects']}
        assert all(status == 'completed' for _, status in current_history['effects'])
        first_files = {path: path.read_bytes() for path in sorted(
            layouts[0]['ready'].parent.rglob('*')) if path.is_file()}
        retained_plan, retained_layout = replan(0, 'retained-refusal', reuse=layouts[0])
        rollback = plan_connected_generation_transfer(second, retained_plan,
            trusted_old_head=stopped_second['session_head_sha256'],
            old_dependency_plan=dependencies[1], new_dependency_plan=dependencies[0],
            limits=limits, action='rollback',
            issued_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
            expires_at=cutoff.isoformat())
        assert rollback['history_sha256'] == digest(current_history)
        rollback_signature = tmp_path / 'rollback-signature.txt'
        rollback_signature.write_text(_issue(private, 'generation_transfer', digest(rollback)))
        rollback_signature.chmod(0o600)
        retained = tmp_path / 'generation-retained'
        rollback_args = dict(trusted_old_head=stopped_second['session_head_sha256'],
            approved_new_plan_sha256=retained_plan['plan_sha256'],
            old_dependency_plan=dependencies[1], new_dependency_plan=dependencies[0],
            grant=rollback, signature_file=rollback_signature)
        # The upgrade signature never authorizes the reverse transfer.
        with pytest.raises(InputError, match='transfer_unverified'):
            transfer_connected_generation(second, retained, retained_plan,
                **dict(rollback_args, signature_file=signature))
        assert not retained.exists()
        result = transfer_connected_generation(second, retained, retained_plan,
                                               **rollback_args)
        assert result['child']['ledger']['status'] == 'committed'
        assert result['child']['child_stage'] == 'installed'
        assert result['child']['run_id'] == stopped_first['run_id']
        assert rollback['new_identity'] == grant['old_identity']
        assert rollback['old_identity'] == grant['new_identity']
        retained_snapshot, retained_history = _history(ledger, grant['old_identity'], limits)
        assert retained_snapshot['calls'] == 2 * journey.calls_per_generation and retained_snapshot['closed_tasks'] == 2
        if journey.composite:
            assert retained_snapshot['calls'] < limits['max_total_calls']
            assert retained_snapshot['reserved_cost'] < limits['max_total_cost']
            assert not retained_snapshot['suspended']
        assert _retained_accounting(retained_history) == _retained_accounting(current_history)
        assert retained_history['effects'] == current_history['effects']
        assert retained_history['state']['generation']['sequence'] == 2
        assert connected_delivery._open(retained)[2]['generation_parent'][
            'original_expires_at'] == cutoff.isoformat()
        closed = RuntimeLedger(ledger, identity=grant['old_identity'], **limits)
        try:
            for task in journey.tasks:
                with pytest.raises(BudgetDenied, match='shared_task_closed'):
                    closed.reserve(task, .1)
            with pytest.raises(InputError, match='^runtime_effect_already_claimed$'):
                closed.claim_effect(*synthetic_claim[:2],
                    _candidate(installed[0][3]), synthetic_claim[2])
            for actual_claim in actual_claims:
                with pytest.raises(InputError, match='^runtime_effect_already_claimed$'):
                    closed.claim_effect(*actual_claim)
            assert closed.generation_snapshot() == retained_history
        finally:
            closed.release()
        retained_status = connected_session_status(retained)
        retained_scope = scope(retained_status, retained_plan, 'launch', cutoff)
        sessions.append((retained, retained_plan))
        launch_connected_session(retained, scope=retained_scope,
            approved_scope_sha256=retained_scope['scope_sha256'])
        retained_status = _exited(retained)
        assert not retained_layout['effects'][-1][0].exists()
        assert retained_layout['ready'].read_bytes() == b'attempt\n'
        assert not retained_status['independent_checks']['outcome_verified']
        if journey.composite:
            retained_audit = read_json(Path(retained_plan['off_provenance'][
                'launch_environment']['DUAL_AUDIT_PATH']))
            assert retained_audit['audit_types'].count('runtime_route_refusal') == 2
            assert retained_audit['audit_reasons'].count('task_closed_or_budget_suspended') == 2
            assert retained_audit['assessed'] == []

        assert {path: path.read_bytes() for path in sorted(
            layouts[0]['ready'].parent.rglob('*')) if path.is_file()} == first_files
        assert len(calls) == 2 * journey.calls_per_generation
        retained_stop = scope(retained_status, retained_plan, 'stop', cutoff)
        stopped_retained = stop_connected_session(retained, scope=retained_stop,
            approved_scope_sha256=retained_stop['scope_sha256'])
        assert stopped_retained['stage'] == 'stopped'
        after_snapshot, after_history = _history(ledger, grant['old_identity'], limits)
        assert after_snapshot['calls'] == 2 * journey.calls_per_generation and after_snapshot['closed_tasks'] == 2
        assert after_history == retained_history
        for layout, task in zip(layouts, journey.tasks):
            for effect, raw in layout['effects']:
                assert effect.read_bytes() == raw
            journey.verify(layout, task)
        historical = connected_generation_status(first, stale, **status_args)
        assert historical['ledger']['status'] == 'committed'
        assert historical['ledger']['current_generation_grant_sha256'] == digest(rollback)
        with pytest.raises(InputError, match='stale_transfer'):
            reconcile_connected_generation(first, stale, **status_args)
        assert connected_session_status(stale)['stage'] == 'generation_pending'
        revoked = RuntimeLedger(ledger, identity=rollback['new_identity'], **limits)
        revoked.suspend()
        revoked.release()
        prospective, _ = replan(1, 'revoked-transfer-effects')
        with _unsigned_refusal_clock(monkeypatch, cutoff) as issued_at:
            with pytest.raises(InputError, match='^runtime_ledger_revoked$'):
                plan_connected_generation_transfer(retained, prospective,
                    trusted_old_head=stopped_retained['session_head_sha256'],
                    old_dependency_plan=dependencies[0], new_dependency_plan=dependencies[1],
                    limits=limits, action='upgrade', issued_at=issued_at,
                    expires_at=cutoff.isoformat())
        assert len(calls) == 2 * journey.calls_per_generation
        # This terminal negative follows every launch and generation action.
        # Restoring source bytes does not restore an installation receipt
        # after a later interpreter rewrites timestamp-based bytecode.
        installed_source = Path(_origins(installed[1][3])['console']['path'])
        original_source = installed_source.read_bytes()
        installed_source.write_bytes(original_source + b'\n')
        try:
            with pytest.raises(InputError, match='^installed_generation_drift_or_unverified$'):
                generation._installed(plans[1], dependencies[1], limits)
            with pytest.raises(InputError, match='^installed_generation_drift_or_unverified$'):
                plan_connected_generation_transfer(retained, prospective,
                    trusted_old_head=stopped_retained['session_head_sha256'],
                    old_dependency_plan=dependencies[0],
                    new_dependency_plan=dependencies[1], limits=limits, action='upgrade',
                    issued_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
                    expires_at=cutoff.isoformat())
            assert not connected_session_status(second)['installed_sources_current']
            assert len(calls) == 2 * journey.calls_per_generation
            for layout in layouts[:2]:
                for effect, raw in layout['effects']:
                    assert effect.read_bytes() == raw
            # The foreign host was only planned; it never ran.
            assert not any(effect.exists() for layout in layouts[2:]
                           for effect, _ in layout['effects'])
        finally:
            # Cleanup only: no console is launched or generation reauthorized.
            installed_source.write_bytes(original_source)
        assert [claim_key, 'completed'] in after_history['effects']
        return {'calls': len(calls), 'run_id': stopped_first['run_id']}
    finally:
        for path, plan in sessions:
            if path.exists():
                status = connected_session_status(path)
                if status['process_alive']:
                    stop = scope(status, plan, 'stop',
                        datetime.now(timezone.utc)+timedelta(minutes=1))
                    stop_connected_session(path, scope=stop,
                        approved_scope_sha256=stop['scope_sha256'])
        server.shutdown(); server.server_close(); thread.join(timeout=2)
