"""Offline contract tests. Mock transport and grants are not live authority."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import threading
import time
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import sqlite3
import json
import multiprocessing
import os
from pathlib import Path
from dataclasses import asdict
from types import SimpleNamespace

import pytest
import jsonschema

from jev_integration_evaluator.budget import BudgetDenied
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.integrations import runtime_lifecycle
from jev_integration_evaluator.integrations.runtime_lifecycle import HostRuntimeLifecycle, LifecycleError
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.runtime import SafeRouter, HostGate
from jev_integration_evaluator.integrations.host import Context, PolicyBlock, UseFallback
from jev_integration_evaluator.runtime import Thresholds
from jev_integration_evaluator.budget import BudgetCoordinator
from jev_integration_evaluator.robustness import request_fingerprint
from jev_integration_evaluator.study import freeze_study
from scripts.v12_fixtures import all_gate_study


LIMITS = dict(max_calls_per_task=2, max_cost_per_task=1, max_total_calls=2,
              max_total_cost=1, max_in_flight=2, max_tasks=4)
AUDIT = SimpleNamespace(append=lambda event: None)


def plan(path):
    path.write_text('owned test bytes', encoding='utf-8')
    return {'files': [{'path': str(path.absolute()),
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]}


def adapter(name):
    config = load_config()['runtime']
    spec = {'candidate_id': name, 'source': {'file': 'host.py'},
            'runtime': {'configuration': config,
            'policy_version': 'reviewed-v1', 'canary_scope': 'workflow', 'task_field': 'task_id'}}
    def create_router(client, *, budget_coordinator, audit_log, runtime_config=None, activation=None):
        return SafeRouter(client, runtime_config or config, policy_version='reviewed-v1',
            canary_scope='workflow', budget_coordinator=budget_coordinator,
            audit_log=audit_log, activation=activation, require_expiring_activation=True,
            require_runtime_binding=True)
    return SimpleNamespace(SPEC=spec, create_router=create_router)


def imported_adapter(path, spec):
    path.write_text(
        'from jev_integration_evaluator.runtime import SafeRouter\n'
        f'SPEC = {spec!r}\n'
        'def create_router(client, *, budget_coordinator, audit_log, runtime_config=None, activation=None):\n'
        "    return SafeRouter(client, runtime_config or SPEC['runtime']['configuration'],\n"
        "        policy_version=SPEC['runtime']['policy_version'], activation=activation,\n"
        "        canary_scope=SPEC['runtime']['canary_scope'], budget_coordinator=budget_coordinator,\n"
        '        audit_log=audit_log, require_expiring_activation=True, require_runtime_binding=True)\n',
        encoding='utf-8')
    module_spec = importlib.util.spec_from_file_location(
        '_jev_fixture_' + hashlib.sha256(str(path).encode()).hexdigest(), path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def connected(tmp_path, monkeypatch, *, mode='shadow', verifier=lambda kind, sha: True):
    class Remote:
        is_remote = True
        def __init__(self, **kwargs):
            self.endpoint = kwargs['endpoint']
        def evaluate(self, *args):
            raise AssertionError('No provider I/O in startup tests')
    monkeypatch.setattr(runtime_lifecycle, 'TypeSafeHTTPClient', Remote)
    adapters = {'a': adapter('a'), 'b': adapter('b')}
    dependency = plan(tmp_path / 'dependency.lock')
    source = plan(tmp_path / 'host.py')
    for item in adapters.values():
        item.SPEC['source']['file_sha256'] = source['files'][0]['sha256']
    adapters = {name: imported_adapter(tmp_path / f'generated_{name}.py', item.SPEC)
                for name, item in adapters.items()}
    adapter_files = {name: {'path': str((tmp_path / f'generated_{name}.py').absolute()),
                            'sha256': hashlib.sha256((tmp_path / f'generated_{name}.py').read_bytes()).hexdigest()}
                     for name in adapters}
    source['files'].extend(adapter_files.values())
    config = {'endpoint': 'https://api.typesafe.ai/v1/systemone',
              'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
              'environment_digest': digest('test-environment'),
              'source_root': str(tmp_path.absolute()), 'source_plan': source,
              'source_bindings': {name: {
                  'reviewed_file_sha256': source['files'][0]['sha256'],
                  'applied_file_sha256': source['files'][0]['sha256'],
                  'adapter_path': f'generated_{name}.py',
                  'adapter_sha256': adapter_files[name]['sha256']} for name in adapters}}
    now = datetime.now(timezone.utc)
    grant = {'endpoint': config['endpoint'], 'credential_ref': config['credential_ref'],
             'model': config['model'], 'environment_digest': config['environment_digest'],
             'source_digest': digest({'root': str(tmp_path.absolute()), 'plan': source,
                                      'bindings': config['source_bindings']}),
             'dependency_digest': digest(dependency),
             'budget_digest': digest(LIMITS),
             'adapters_digest': digest({k: digest(v.SPEC) for k, v in adapters.items()}),
             'mode': mode, 'issued_at': (now-timedelta(minutes=1)).isoformat(),
             'expires_at': (now+timedelta(minutes=2)).isoformat()}
    return dict(adapters=adapters, budget_limits=LIMITS, audit_log=AUDIT,
                dependency_plan=dependency, startup_mode=mode, connected_config=config,
                authority={'egress_grant': grant, 'activation': None},
                verify_authority=verifier,
                current_environment_digest=lambda: config['environment_digest'],
                ledger_path=tmp_path / 'workflow.ledger')


def test_off_needs_no_credentials_and_connected_shadow_is_explicit(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas' /
                         'host-runtime-connected-v1.schema.json').read_text(encoding='utf-8'))
    jsonschema.validate(args['connected_config'], schema)
    jsonschema.validate(args['authority'], schema)
    jsonschema.validate(HostRuntimeLifecycle.qualification_inputs(), schema)
    with HostRuntimeLifecycle(**args) as host:
        jsonschema.validate(host.mode_status(), schema)
        assert host.mode_status()['effective_mode'] == 'shadow'
        assert host.router('a', {'task_id': 'task'}).client.is_remote
        assert host.router('a', {'task_id': 'task'}).budget_coordinator is host.router('b', {'task_id': 'task'}).budget_coordinator
        assert not host.qualification_inputs()['release_gate_complete']
    with HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS, audit_log=AUDIT,
                              dependency_plan=args['dependency_plan']) as off:
        assert off.mode_status()['effective_mode'] == 'off'
        assert not off.router('a', {'task_id': 'task'}).client.is_remote


def test_missing_verifier_or_gate_rejects_connected_modes(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    for mode in ('canary', 'active'):
        changed = copy.copy(args)
        changed['startup_mode'] = mode
        changed['authority'] = {'egress_grant': {**args['authority']['egress_grant'], 'mode': mode},
                                'activation': None}
        with pytest.raises(LifecycleError, match='connected_activation_evidence_required'):
            HostRuntimeLifecycle(**changed)
    args['verify_authority'] = None
    with pytest.raises(LifecycleError, match='connected_configuration_or_authority_required'):
        HostRuntimeLifecycle(**args)


def test_grant_expiry_authentication_and_binding(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    args['verify_authority'] = lambda kind, sha: False
    with pytest.raises(LifecycleError, match='connected_egress_grant_unverified'):
        HostRuntimeLifecycle(**args)
    args['verify_authority'] = lambda kind, sha: True
    args['authority']['egress_grant']['expires_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    with pytest.raises(LifecycleError, match='connected_egress_grant_expired'):
        HostRuntimeLifecycle(**args)
    args['authority']['egress_grant']['expires_at'] = (datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat()
    args['adapters']['a'].SPEC['runtime']['policy_version'] = 'changed'
    with pytest.raises(LifecycleError, match='connected_egress_binding_mismatch'):
        HostRuntimeLifecycle(**args)


@pytest.mark.parametrize('model', ['jev-latest', 'jev-1.14.0-preview', 'unknown-1.0'])
def test_unqualified_model_pin_is_rejected_at_startup(tmp_path, monkeypatch, model):
    args = connected(tmp_path, monkeypatch)
    args['connected_config']['model'] = model
    with pytest.raises(LifecycleError, match='connected_configuration_or_authority_required'):
        HostRuntimeLifecycle(**args)


def test_environment_mismatch_rejected_at_startup(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    args['current_environment_digest'] = lambda: digest('other')
    with pytest.raises(LifecycleError, match='connected_environment_drift'):
        HostRuntimeLifecycle(**args)


def test_connected_adapter_requires_authenticated_import_origin(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    module = args['adapters']['a']
    args['adapters']['a'] = SimpleNamespace(SPEC=module.SPEC,
                                            create_router=module.create_router)
    with pytest.raises(LifecycleError, match='connected_source_binding_mismatch'):
        HostRuntimeLifecycle(**args)


@pytest.mark.skipif(os.name == 'nt', reason='fork is unavailable on Windows')
def test_inherited_connected_router_and_ledger_reject_fork(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    with HostRuntimeLifecycle(**args) as host:
        router = host.router('a', {'task_id': 'task'})
        queue = multiprocessing.get_context('fork').Queue()
        def inherited_child():
            try:
                host.coordinator.reserve('child-task', .1)
                queue.put('ledger-accepted')
            except InputError as exc:
                queue.put(str(exc))
            decision = router.route(task_id='child-task', state={'marker': 1},
                questions={'q': {'type': 'choice', 'instructions': 'Choose a reviewed action',
                                 'criteria': {'inspect': 'inspect', 'stop': 'stop'}}},
                primary_question='q', evidence_question=None, baseline_action='stop',
                gate=HostGate(('inspect', 'stop')), label_actions={
                    'inspect': 'inspect', 'stop': 'stop'}, estimated_cost_upper_bound=.001)
            queue.put(decision.source)
        process = multiprocessing.get_context('fork').Process(target=inherited_child)
        process.start()
        process.join(timeout=10)
        assert process.exitcode == 0
        assert queue.get(timeout=2) == 'runtime_ledger_forked'
        assert queue.get(timeout=2) == 'baseline'


def test_connected_source_drift_suspends_and_revokes(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    with HostRuntimeLifecycle(**args) as host:
        (tmp_path / 'host.py').write_text('changed', encoding='utf-8')
        with pytest.raises(LifecycleError, match='runtime_source_or_configuration_drift'):
            host.router('a', {'task_id': 'task'})
        assert host.mode_status()['effective_mode'] == 'off'
    with pytest.raises(InputError, match='runtime_ledger_revoked'):
        RuntimeLedger(args['ledger_path'], identity=host.coordinator.identity, **LIMITS)


def test_source_plan_must_cover_reviewed_placement(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    args['adapters']['a'].SPEC['source']['file'] = 'unrelated.py'
    with pytest.raises(LifecycleError, match='connected_source_binding_missing'):
        HostRuntimeLifecycle(**args)


def test_source_binding_mapping_tamper_requires_new_authenticated_grant(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    args['connected_config']['source_bindings']['a']['adapter_path'] = 'generated_b.py'
    with pytest.raises(LifecycleError, match='connected_source_binding_mismatch'):
        HostRuntimeLifecycle(**args)


def test_adapter_drift_after_callback_blocks_provider_io(tmp_path, monkeypatch):
    args = connected(tmp_path, monkeypatch)
    with HostRuntimeLifecycle(**args) as host:
        router = host.router('a', {'task_id': 'task'})
        calls = []
        host._client.evaluate = lambda *a: calls.append('provider')
        args['adapters']['a'].SPEC['runtime']['policy_version'] = 'changed'
        decision = router.route(task_id='task', state={'marker': 1},
            questions={'q': {'type': 'choice', 'instructions': 'Inspect marker.',
                             'criteria': {'inspect': 'Inspect it.', 'stop': 'Stop.'}}},
            primary_question='q', baseline_action='stop',
            gate=HostGate(('inspect', 'stop')),
            estimated_cost_upper_bound=.001)
        assert decision.source == 'baseline'
        for future in list(router.futures):
            future.result(timeout=2)
        assert not calls and host.coordinator.snapshot()['suspended']


@pytest.mark.parametrize('changed', ['source', 'model', 'policy', 'configuration', 'rubric'])
def test_adapter_or_runtime_drift_is_rejected(tmp_path, monkeypatch, changed):
    args = connected(tmp_path, monkeypatch)
    with HostRuntimeLifecycle(**args) as host:
        spec = args['adapters']['a'].SPEC
        if changed == 'source':
            spec['source'] = {'source_sha256': digest('changed')}
        elif changed == 'model':
            spec['runtime']['configuration']['model'] = 'jev-2.0.0'
        elif changed == 'policy':
            spec['runtime']['policy_version'] = 'changed'
        elif changed == 'configuration':
            spec['runtime']['configuration']['timeout_ms'] += 1
        else:
            spec['questions'] = {'q': {'type': 'choice', 'instructions': 'Changed rubric',
                                     'criteria': {'x': 'One', 'y': 'Two'}}}
        with pytest.raises(LifecycleError, match='runtime_source_or_configuration_drift'):
            host.router('a', {'task_id': 'task'})


def test_egress_authority_revocation_latches_runtime_off(tmp_path, monkeypatch):
    trusted = {'yes': True}
    args = connected(tmp_path, monkeypatch,
                     verifier=lambda kind, sha: trusted['yes'])
    with HostRuntimeLifecycle(**args) as host:
        trusted['yes'] = False
        with pytest.raises(LifecycleError, match='runtime_source_or_configuration_drift'):
            host.router('a', {'task_id': 'task'})
        assert host.mode_status()['effective_mode'] == 'off'
        assert host.mode_status()['rejection_reason'] == 'runtime_source_configuration_or_egress_drift'


def test_environment_drift_latches_off_before_provider_io(tmp_path, monkeypatch):
    current = {'digest': digest('test-environment')}
    args = connected(tmp_path, monkeypatch)
    args['current_environment_digest'] = lambda: current['digest']
    with HostRuntimeLifecycle(**args) as host:
        current['digest'] = digest('changed-environment')
        with pytest.raises(LifecycleError, match='runtime_source_or_configuration_drift'):
            host.router('a', {'task_id': 'task'})
        assert host.mode_status()['effective_mode'] == 'off'


def test_restart_keeps_spend_and_closed_tasks(tmp_path):
    path = tmp_path / 'ledger'
    first = RuntimeLedger(path, identity='same', **LIMITS)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reservations = list(pool.map(lambda _: first.reserve('task', .25), range(2)))
    for reservation in reservations:
        first.settle(reservation)
    first.close_task('task')
    first.release()
    second = RuntimeLedger(path, identity='same', **LIMITS)
    assert second.snapshot()['calls'] == 2
    assert second.snapshot()['closed_tasks'] == 1
    with pytest.raises(BudgetDenied):
        second.reserve('task', .1)
    with pytest.raises(BudgetDenied):
        second.reserve('other', .1)
    second.release()


def test_durable_ledger_requires_absolute_nonaliased_path(tmp_path):
    with pytest.raises(InputError, match='runtime_ledger_requires_absolute_path'):
        RuntimeLedger('relative-ledger', identity='scope', **LIMITS)
    target = tmp_path / 'actual'
    target.mkdir()
    alias = tmp_path / 'alias'
    try:
        alias.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('Local symlink creation unavailable')
    with pytest.raises(InputError, match='invalid_runtime_ledger_path'):
        RuntimeLedger(alias / 'ledger', identity='scope', **LIMITS)


def test_corrupt_ledger_reports_fixed_diagnostic_without_deleting_history(tmp_path):
    marker = tmp_path / 'corrupt'
    marker.write_bytes(b'0')
    database = tmp_path / 'corrupt.sqlite'
    database.write_bytes(b'not a SQLite database')
    with pytest.raises(InputError, match='runtime_ledger_unavailable') as caught:
        RuntimeLedger(marker, identity='scope', **LIMITS)
    assert str(tmp_path) not in str(caught.value)
    assert marker.exists() and database.read_bytes() == b'not a SQLite database'


def test_first_database_creation_failure_cleans_only_fresh_marker(tmp_path, monkeypatch):
    marker = tmp_path / 'failed-first-start'
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **k: (_ for _ in ()).throw(OSError('private path')))
    with pytest.raises(InputError, match='runtime_ledger_unavailable') as caught:
        RuntimeLedger(marker, identity='scope', **LIMITS)
    assert str(tmp_path) not in str(caught.value)
    assert not marker.exists() and not (tmp_path / 'failed-first-start.sqlite').exists()


def test_reservation_write_failure_suspends_before_provider_io(tmp_path, monkeypatch):
    ledger = RuntimeLedger(tmp_path / 'write-failure', identity='scope', **LIMITS)
    from jev_integration_evaluator.integrations import runtime_ledger
    monkeypatch.setattr(runtime_ledger, 'json', SimpleNamespace(
        dumps=lambda *a, **k: (_ for _ in ()).throw(OSError('private path'))))
    with pytest.raises(InputError, match='runtime_ledger_write_failed'):
        ledger.reserve('task', .1)
    assert ledger.snapshot()['suspended'] is True
    ledger.release()


@pytest.mark.parametrize('phase', ['reserve', 'settle'])
def test_begin_failure_latches_suspension(tmp_path, monkeypatch, phase):
    ledger = RuntimeLedger(tmp_path / f'begin-{phase}', identity=phase, **LIMITS)
    reservation = ledger.reserve('task', .1) if phase == 'settle' else None
    original = ledger._db
    class FailingConnection:
        def __getattr__(self, name):
            return getattr(original, name)
        def execute(self, sql, *args):
            if sql == 'BEGIN IMMEDIATE':
                raise sqlite3.OperationalError('private database path')
            return original.execute(sql, *args)
    ledger._db = FailingConnection()
    with pytest.raises(InputError, match='runtime_ledger_write_failed') as caught:
        if phase == 'settle':
            ledger.settle(reservation, actual_cost=.05)
        else:
            ledger.reserve('task', .1)
    assert 'private' not in str(caught.value)
    assert ledger.snapshot()['suspended'] is True
    ledger._db = original
    ledger.release()


def test_effect_completion_failure_latches_suspension(tmp_path):
    ledger = RuntimeLedger(tmp_path / 'effect-update', identity='effect-update', **LIMITS)
    key = ledger.claim_effect('task', digest('request'), 'placement', 'registry:inspect')
    original = ledger._db
    class FailingConnection:
        def __getattr__(self, name):
            return getattr(original, name)
        def execute(self, sql, *args):
            if sql.startswith('UPDATE effects'):
                raise sqlite3.OperationalError('private database path')
            return original.execute(sql, *args)
    ledger._db = FailingConnection()
    with pytest.raises(InputError, match='runtime_effect_completion_unavailable') as caught:
        ledger.complete_effect(key)
    assert 'private' not in str(caught.value)
    assert ledger.snapshot()['suspended'] is True
    ledger._db = original
    ledger.release()


def test_unresolved_provider_or_effect_blocks_restart(tmp_path):
    for suffix, effect in (('provider', False), ('effect', True)):
        path = tmp_path / suffix
        first = RuntimeLedger(path, identity=suffix, **LIMITS)
        if effect:
            first.claim_effect('task', digest('request'), 'placement', 'action:inspect')
        else:
            first.reserve('task', .1)
        first.release()  # Simulate a process lost after durable intent.
        with pytest.raises(InputError, match='runtime_ledger_unresolved_history'):
            RuntimeLedger(path, identity=suffix, **LIMITS)


def active_fixture_args(tmp_path, monkeypatch, mode, *, timeout_ms=20):
    # This is deliberately fabricated evidence with a mock authority verifier.
    # It proves local wiring and recomputation, never deployment eligibility.
    cfg = load_config()
    cfg['validation'].update(bootstrap_samples=120, bayesian_samples=200)
    inventory, old_study, baseline, treatment, bundle, _ = all_gate_study(cfg, evidence='observed')
    specification = copy.deepcopy(old_study['specification'])
    specification['jev']['mode'] = mode
    study = freeze_study(specification, cfg, inventory=inventory)
    for row in baseline + treatment:
        row['study_digest'] = study['contract_digest']
    for row in treatment:
        row['mode'] = mode
        row['calibration_validated'] = True
    adapters = {}
    receipts = {}
    for gate in specification['deployment_gates']:
        name = gate['candidate_id']
        config = load_config()['runtime']
        config['timeout_ms'] = timeout_ms
        spec = {'candidate_id': name, 'source': gate['source'],
                'questions': gate['questions'], 'primary_question': gate['primary_question'],
                'evidence_question': None,
                'label_actions': {'inspect': 'inspect', 'stop': 'stop'},
                'runtime': {'configuration': config, 'policy_version': gate['policy_version'],
                            'canary_scope': 'workflow', 'task_field': 'task_id'}}
        def factory(client, *, budget_coordinator, audit_log, runtime_config=None,
                    activation=None, _spec=spec):
            return SafeRouter(client, runtime_config or _spec['runtime']['configuration'],
                policy_version=_spec['runtime']['policy_version'], activation=activation,
                canary_scope='workflow', budget_coordinator=budget_coordinator,
                audit_log=audit_log, require_expiring_activation=True,
                require_runtime_binding=True)
        adapters[name] = SimpleNamespace(SPEC=spec, create_router=factory)
        temporary = factory(SimpleNamespace(is_remote=True, evaluate=lambda *a: None),
                            budget_coordinator=BudgetCoordinator(**LIMITS),
                            audit_log=AUDIT, runtime_config={**config, 'mode': mode})
        now = datetime.now(timezone.utc)
        receipt = {'approved': True, 'calibration_validated': True,
                   'model': config['model'], 'policy_version': gate['policy_version'],
                   'questions_hash': digest(spec['questions']),
                   'thresholds_hash': digest(asdict(Thresholds())),
                   'holdout_evidence_ref': gate['holdout_report_digest'],
                   'activation_id': 'FABRICATED-TEST-ONLY', 'evidence_type': 'observed',
                   'issued_at': (now-timedelta(minutes=1)).isoformat(),
                   'expires_at': (now+timedelta(minutes=2)).isoformat(),
                   'ordered_questions_hash': request_fingerprint(None, spec['questions'], config['model']),
                   'runtime_contract_hash': temporary.runtime_contract_hash(
                       spec['questions'], spec['primary_question'], None,
                       label_actions=spec['label_actions']),
                   'study_digest': study['contract_digest'], 'deployment_id': 'FABRICATED-TEST-ONLY'}
        receipts[name] = {'receipt': receipt,
                          'runtime_contract_hash': receipt['runtime_contract_hash']}
        temporary.close()
    args = connected(tmp_path, monkeypatch, mode=mode)
    args['adapters'] = adapters
    source_files = {}
    for item in adapters.values():
        relative = item.SPEC['source']['file']
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative not in source_files:
            path.write_text('synthetic edited host source', encoding='utf-8')
            source_files[relative] = {'path': str(path.absolute()),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    for name in adapters:
        relative = f'generated_{name}.py'
        path = tmp_path / relative
        adapters[name] = imported_adapter(path, adapters[name].SPEC)
        source_files[relative] = {'path': str(path.absolute()),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    args['connected_config']['source_plan'] = {'files': list(source_files.values())}
    args['connected_config']['source_bindings'] = {
        name: {'reviewed_file_sha256': item.SPEC['source']['file_sha256'],
               'applied_file_sha256': source_files[item.SPEC['source']['file']]['sha256'],
               'adapter_path': f'generated_{name}.py',
               'adapter_sha256': source_files[f'generated_{name}.py']['sha256']}
        for name, item in adapters.items()}
    grant = args['authority']['egress_grant']
    grant['source_digest'] = digest({'root': str(tmp_path.absolute()),
                                     'plan': args['connected_config']['source_plan'],
                                     'bindings': args['connected_config']['source_bindings']})
    grant['adapters_digest'] = digest({k: digest(v.SPEC) for k, v in adapters.items()})
    deployment = {'study_digest': study['contract_digest'],
                  'gate_manifest_digest': digest(specification['deployment_gates']),
                  'baseline_digest': digest(baseline),
                  'treatment_digest': digest(treatment),
                  'gate_bundle_digest': digest(bundle),
                  'inventory_digest': digest(inventory),
                  'mode': mode, 'deployment_id': 'FABRICATED-TEST-ONLY',
                  'issued_at': (now-timedelta(minutes=1)).isoformat(),
                  'expires_at': (now+timedelta(minutes=2)).isoformat()}
    args['authority']['activation'] = {**receipts,
        'evidence': {'study': study, 'baseline': baseline, 'treatment': treatment,
                     'gate_bundle': bundle, 'inventory': inventory,
                     'expected_study_digest': study['contract_digest'],
                     'deployment_grant': deployment}}
    schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas' /
                         'host-runtime-connected-v1.schema.json').read_text(encoding='utf-8'))
    jsonschema.validate(args['connected_config'], schema)
    jsonschema.validate(args['authority'], schema)
    return args, adapters


@pytest.mark.parametrize('mode', ['canary', 'active'])
@pytest.mark.parametrize('revoked_kind', ['deployment_grant', 'activation_receipt'])
def test_receipt_gated_mode_with_raw_fixture_evidence(tmp_path, monkeypatch, mode, revoked_kind):
    args, adapters = active_fixture_args(tmp_path, monkeypatch, mode)
    tampered = copy.copy(args)
    tampered['authority'] = copy.deepcopy(args['authority'])
    tampered['authority']['activation']['evidence']['treatment'][0]['cost'] += .001
    with pytest.raises(LifecycleError, match='connected_deployment_grant_invalid'):
        HostRuntimeLifecycle(**tampered)
    trusted = {'deployment_grant': True, 'activation_receipt': True}
    args['verify_authority'] = lambda kind, sha: trusted.get(kind, True)
    with HostRuntimeLifecycle(**args) as host:
        assert host.mode_status()['effective_mode'] == mode
        assert all(host.router(name, {'task_id': 'task'})._active_authorized(
            adapter.SPEC['questions'], adapter.SPEC['primary_question'], None,
            adapter.SPEC['label_actions']) for name, adapter in adapters.items())
        trusted[revoked_kind] = False
        with pytest.raises(LifecycleError, match='runtime_source_or_configuration_drift'):
            host.router(next(iter(adapters)), {'task_id': 'task'})
        assert host.mode_status()['effective_mode'] == 'off'
        host.revoke_activation()
        assert host.mode_status()['effective_mode'] == 'off'
    with pytest.raises(LifecycleError, match='invalid_shared_budget'):
        HostRuntimeLifecycle(**args)


def _route(host, adapter, task_id='task'):
    spec = adapter.SPEC
    router = host.router(spec['candidate_id'], {'task_id': task_id})
    return router.route(task_id=task_id, state={'marker': 1},
                        questions=spec['questions'], primary_question=spec['primary_question'],
                        evidence_question=None, baseline_action='stop',
                        gate=HostGate(('inspect', 'stop')),
                        label_actions=spec['label_actions'],
                        estimated_cost_upper_bound=.001)


def _response(model):
    return {'model': model, 'answers': {'action': {'type': 'choice',
            'choice': 'inspect', 'confidence': .95,
            'probabilities': {'inspect': .99, 'stop': .01}}},
            'usage': {'input_tokens': 1, 'output_tokens': 1}}


@pytest.mark.parametrize('fault', ['none', 'timeout', 'malformed', 'late', 'audit'])
def test_connected_provider_route_and_failure_fallback(tmp_path, monkeypatch, fault):
    args, adapters = active_fixture_args(tmp_path, monkeypatch, 'active')
    with HostRuntimeLifecycle(**args) as host:
        name, adapter = next(iter(adapters.items()))
        router = host.router(name, {'task_id': 'task'})
        def evaluate(state, questions, model, timeout_ms):
            if fault == 'timeout':
                raise TimeoutError('mock transport timeout')
            if fault == 'late':
                time.sleep(.04)
            result = _response(model)
            if fault == 'malformed':
                result['answers']['action']['probabilities']['inspect'] = .4
            return result
        host._client.evaluate = evaluate
        if fault == 'audit':
            router.log = SimpleNamespace(append=lambda event: (_ for _ in ()).throw(OSError('mock audit failure')))
        decision = _route(host, adapter)
        assert decision.source == ('jev_assessment' if fault == 'none' else 'baseline')
        assert host.coordinator.snapshot()['calls'] == 1
        assert host.coordinator.snapshot()['in_flight'] == 0
        assert host.coordinator.snapshot()['reserved_cost'] == pytest.approx(.001)


def test_connected_inflight_task_cancellation_discards_result(tmp_path, monkeypatch):
    args, adapters = active_fixture_args(tmp_path, monkeypatch, 'active')
    with HostRuntimeLifecycle(**args) as host:
        _, adapter = next(iter(adapters.items()))
        started, finish = threading.Event(), threading.Event()
        def evaluate(state, questions, model, timeout_ms):
            started.set()
            finish.wait(2)
            return _response(model)
        host._client.evaluate = evaluate
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_route, host, adapter)
            assert started.wait(2)
            host.complete_task('task')
            finish.set()
            decision = future.result(timeout=2)
        assert decision.source == 'baseline'
        assert host.coordinator.snapshot()['closed_tasks'] == 1
        assert host.coordinator.snapshot()['in_flight'] == 0


def test_connected_two_routers_threads_share_total_budget(tmp_path, monkeypatch):
    args, adapters = active_fixture_args(tmp_path, monkeypatch, 'active', timeout_ms=1000)
    with HostRuntimeLifecycle(**args) as host:
        entered = threading.Barrier(2)
        def evaluate(state, questions, model, timeout_ms):
            entered.wait(timeout=5)
            return _response(model)
        host._client.evaluate = evaluate
        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions = list(pool.map(lambda pair: _route(host, pair[1], pair[0]),
                                      [('task-a', list(adapters.values())[0]),
                                       ('task-b', list(adapters.values())[1])]))
        assert all(d.source == 'jev_assessment' for d in decisions), decisions
        assert host.coordinator.snapshot()['calls'] == 2
        assert host.coordinator.snapshot()['in_flight'] == 0
        third = _route(host, list(adapters.values())[0], 'task-c')
        assert third.source == 'baseline'
        assert third.reason == 'shared_total_call_budget'


def test_connected_effect_journal_blocks_duplicate_executor(tmp_path):
    ledger = RuntimeLedger(tmp_path / 'effects', identity='effect-test', **LIMITS)
    calls = []
    def context():
        c = Context.__new__(Context)
        c.router = SimpleNamespace(budget_coordinator=ledger, lock=threading.RLock(),
            suspended=False, closed=False, _active_authorized=lambda *a: True)
        c.spec = {'candidate_id': 'placement', 'questions': {},
                  'primary_question': 'q', 'evidence_question': None,
                  'label_actions': {}}
        c.task_id = 'task'
        c.request_hash = digest({'task_id': 'task', 'input': 'same'})
        c.host_operation_started = False
        c.options = {'inspect': execute, 'alias': execute}
        c.original = execute
        c.baseline = 'inspect'
        c.b = {'blocked': lambda request, reason: None}
        return c
    def execute(request=None):
        calls.append('effect')
        return 'done'
    first_context = context()
    assert first_context.host_operation(execute, effect_operation='action:inspect') == 'done'
    with pytest.raises(PolicyBlock, match='runtime_effect_replay_or_journal_unavailable'):
        first_context.host_operation(execute, effect_operation='baseline')
    first_context.policy = {'fallback': 'baseline'}
    first_context.baseline = 'inspect'
    first_context.original = execute
    first_context.request = {'task_id': 'task'}
    first_context.guard = nullcontext
    first_context.audit_intent = lambda action: None
    first_context.late = lambda action, receipt: execute
    with pytest.raises(PolicyBlock, match='runtime_effect_replay_or_journal_unavailable'):
        first_context.fallback('synthetic-revocation')
    with pytest.raises(PolicyBlock, match='runtime_effect_replay_or_journal_unavailable'):
        context().host_operation(execute, effect_operation='action:inspect')
    with pytest.raises(PolicyBlock, match='runtime_effect_replay_or_journal_unavailable'):
        context().host_operation(execute, effect_operation='baseline')
    with pytest.raises(PolicyBlock, match='runtime_effect_replay_or_journal_unavailable'):
        context().host_operation(execute, effect_operation='action:alias')
    assert calls == ['effect']
    ledger.release()


def test_effect_identity_separates_placements_and_actions(tmp_path):
    ledger = RuntimeLedger(tmp_path / 'placements', identity='same-workflow', **LIMITS)
    request_hash = digest('same-request')
    first = ledger.claim_effect('task', request_hash, 'placement-a', 'action:inspect')
    ledger.complete_effect(first)
    second = ledger.claim_effect('task', request_hash, 'placement-b', 'action:inspect')
    ledger.complete_effect(second)
    third = ledger.claim_effect('task', request_hash, 'placement-a', 'action:stop')
    ledger.complete_effect(third)
    with pytest.raises(InputError, match='runtime_effect_already_claimed'):
        ledger.claim_effect('task', request_hash, 'placement-a', 'action:inspect')
    with pytest.raises(InputError, match='runtime_effect_already_claimed'):
        ledger.claim_effect('task', request_hash, 'placement-a', 'action:inspect')
    ledger.release()


def test_distinct_registered_closures_with_same_qualname_have_distinct_effects(tmp_path):
    ledger = RuntimeLedger(tmp_path / 'closures', identity='closures', **LIMITS)
    calls = []
    def factory(action):
        def executor():
            calls.append(action)
        return executor
    first, second = factory('first'), factory('second')
    assert first.__qualname__ == second.__qualname__
    c = Context.__new__(Context)
    c.router = SimpleNamespace(budget_coordinator=ledger, lock=threading.RLock(),
        suspended=False, closed=False, _active_authorized=lambda *a: True)
    c.spec = {'candidate_id': 'placement', 'questions': {}, 'primary_question': 'q',
              'evidence_question': None, 'label_actions': {}}
    c.task_id, c.request_hash = 'task', digest('request')
    c.host_operation_started = False
    c.options = {'first': first, 'second': second}
    c.original, c.baseline, c.b = first, 'first', {'blocked': lambda *a: None}
    c.host_operation(first, effect_operation='action:first')
    c.host_operation(second, effect_operation='action:second')
    assert calls == ['first', 'second']
    ledger.release()


def test_reviewed_binding_and_plan_step_executors_have_effect_ids(tmp_path):
    ledger = RuntimeLedger(tmp_path / 'recipe-roles', identity='recipe-roles', **LIMITS)
    calls = []
    def factory(role):
        def executor():
            calls.append(role)
        return executor
    generate, finish, step_a, step_b = (factory(name) for name in
                                        ('generate', 'finish', 'step-a', 'step-b'))
    c = Context.__new__(Context)
    c.router = SimpleNamespace(budget_coordinator=ledger, lock=threading.RLock(),
        suspended=False, closed=False, _active_authorized=lambda *a: True)
    c.spec = {'candidate_id': 'placement', 'questions': {}, 'primary_question': 'q',
              'evidence_question': None, 'label_actions': {}}
    c.task_id, c.request_hash = 'task', digest('request')
    c.host_operation_started = False
    c.options = {'plan': ['a', 'b']}
    c.original, c.baseline = factory('baseline'), 'plan'
    c.b = {'generate': generate, 'finish': finish, 'blocked': factory('blocked')}
    c._reviewed_step_executors = {'a': step_a, 'b': step_b}
    for role, fn in [('generate', generate), ('a', step_a), ('b', step_b),
                     ('finish', finish)]:
        c.host_operation(fn, effect_operation=role)
    assert calls == ['generate', 'step-a', 'step-b', 'finish']
    with pytest.raises(PolicyBlock, match='runtime_effect_replay_or_journal_unavailable'):
        c.host_operation(step_a, effect_operation='alias')
    ledger.release()


def test_final_effect_gate_rejects_suspend_after_late_check(tmp_path):
    ledger = RuntimeLedger(tmp_path / 'final-gate', identity='final-gate', **LIMITS)
    c = Context.__new__(Context)
    c.router = SimpleNamespace(budget_coordinator=ledger, lock=threading.RLock(),
        suspended=False, closed=False, _active_authorized=lambda *a: True)
    c.spec = {'candidate_id': 'placement', 'questions': {},
              'primary_question': 'q', 'evidence_question': None, 'label_actions': {}}
    c.task_id, c.request_hash = 'task', digest('request')
    c.host_operation_started = False
    calls = []
    ledger.suspend()
    with pytest.raises(UseFallback, match='runtime_revoked_before_effect'):
        c.host_operation(lambda: calls.append('effect'), effect_operation='action:inspect')
    assert not calls
    assert c.host_operation(lambda: calls.append('baseline'),
                            effect_operation='baseline') is None
    assert calls == ['baseline']
    ledger.release()


def test_host_approved_fallback_survives_activation_revocation(tmp_path):
    ledger = RuntimeLedger(tmp_path / 'fallback', identity='fallback-test', **LIMITS)
    c = Context.__new__(Context)
    c.router = SimpleNamespace(budget_coordinator=ledger, lock=threading.RLock(),
        suspended=True, closed=False, _active_authorized=lambda *a: False,
        host_source_check=lambda: None)
    c.spec = {'candidate_id': 'placement', 'questions': {},
              'primary_question': 'q', 'evidence_question': None, 'label_actions': {}}
    c.task_id, c.request_hash = 'task', digest('request')
    c.host_operation_started = False
    c.policy = {'fallback': 'baseline'}
    c.baseline = 'stop'
    c.request = {'task_id': 'task'}
    c.guard = nullcontext
    c.audit_intent = lambda action: None
    c.late = lambda action, receipt: None
    calls = []
    def baseline(request):
        calls.append(request)
        return 'baseline-result'
    c.original = baseline
    ledger.suspend()
    assert c.fallback('synthetic-revocation') == 'baseline-result'
    assert calls == [{'task_id': 'task'}]
    ledger.release()


def test_two_placement_effects_drift_and_suspend_do_not_deadlock(tmp_path):
    ledger = RuntimeLedger(tmp_path / 'concurrent-effects', identity='concurrent', **LIMITS)
    entered, release = threading.Event(), threading.Event()
    drift = {'yes': False}
    calls = []
    def context(placement):
        c = Context.__new__(Context)
        def check():
            if drift['yes']:
                ledger.suspend()
                raise InputError('synthetic source drift')
        c.router = SimpleNamespace(budget_coordinator=ledger, lock=threading.RLock(),
            suspended=False, closed=False, _active_authorized=lambda *a: True,
            host_source_check=check)
        c.spec = {'candidate_id': placement, 'questions': {},
                  'primary_question': 'q', 'evidence_question': None, 'label_actions': {}}
        c.task_id, c.request_hash = 'task', digest('request')
        c.host_operation_started = False
        return c
    def first_effect():
        entered.set()
        assert release.wait(2)
        calls.append('first')
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(context('a').host_operation, first_effect,
                            effect_operation='action:inspect')
        assert entered.wait(2)
        drift['yes'] = True
        second = pool.submit(context('b').host_operation,
                             lambda: calls.append('second'),
                             effect_operation='action:inspect')
        suspension = pool.submit(ledger.suspend)
        release.set()
        first.result(timeout=2)
        with pytest.raises(PolicyBlock, match='runtime_authority_unavailable_before_effect'):
            second.result(timeout=2)
        suspension.result(timeout=2)
    assert calls == ['first']
    ledger.release()


@pytest.mark.parametrize('target_mode', ['canary', 'active'])
def test_clean_restart_transition_retains_spend_and_needs_new_mode_grant(tmp_path, monkeypatch, target_mode):
    target, _ = active_fixture_args(tmp_path, monkeypatch, target_mode)
    shadow = copy.copy(target)
    shadow['startup_mode'] = 'shadow'
    shadow['authority'] = {'egress_grant': {**target['authority']['egress_grant'],
                                           'mode': 'shadow'}, 'activation': None}
    with HostRuntimeLifecycle(**shadow) as first:
        reservation = first.coordinator.reserve('task', .1)
        first.coordinator.settle(reservation)
        assert first.mode_status()['effective_mode'] == 'shadow'
    stale_grant = copy.copy(target)
    stale_grant['authority'] = {'egress_grant': shadow['authority']['egress_grant'],
                                'activation': target['authority']['activation']}
    with pytest.raises(LifecycleError, match='connected_egress_binding_mismatch'):
        HostRuntimeLifecycle(**stale_grant)
    with HostRuntimeLifecycle(**target) as promoted:
        assert promoted.mode_status()['effective_mode'] == target_mode
        assert promoted.coordinator.snapshot()['calls'] == 1
        assert promoted.coordinator.snapshot()['reserved_cost'] == pytest.approx(.1)
        promoted.suspend()
    with pytest.raises(LifecycleError, match='invalid_shared_budget'):
        HostRuntimeLifecycle(**target)
