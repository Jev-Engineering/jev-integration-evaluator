"""Offline host-owned runtime startup contracts; no provider or target imports."""
from __future__ import annotations

import hashlib
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import sys
from types import SimpleNamespace

import pytest

from jev_integration_evaluator.budget import BudgetDenied
from jev_integration_evaluator.client import FixtureClient
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.integrations.runtime_lifecycle import (
    HostRuntimeLifecycle, LifecycleError, check_dependency_plan,
)
from jev_integration_evaluator.runtime import SafeRouter
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.integrations.contracts import validate_spec
from jev_integration_evaluator.integrations.lifecycle import (
    plan_implementation, apply_implementation, rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.integrations.recipes import transform
from jev_integration_evaluator.integrations.probe import SyntheticClient, SyntheticAudit
from scripts.implementation_fixtures import fixture


LIMITS = dict(max_calls_per_task=2, max_cost_per_task=2,
              max_total_calls=2, max_total_cost=2, max_in_flight=1, max_tasks=2)
AUDIT = SimpleNamespace(append=lambda event: None)


def adapter(name, scope='workflow'):
    config = load_config()['runtime']
    spec = {'candidate_id': name, 'runtime': {'configuration': config,
            'policy_version': 'reviewed-v1', 'canary_scope': scope,
            'task_field': 'task_id'}}

    def factory(client, *, budget_coordinator, audit_log, runtime_config=None):
        return SafeRouter(client, runtime_config or config, policy_version='reviewed-v1',
            canary_scope=scope, budget_coordinator=budget_coordinator,
            audit_log=audit_log, require_expiring_activation=True,
            require_runtime_binding=True)

    return SimpleNamespace(SPEC=spec, create_router=factory)


def inputs(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock = tmp_path / 'requirements.lock'
    lock.write_text('synthetic-package==1.0\n', encoding='utf-8')
    plan = {'files': [{'path': str(lock.resolve()),
                       'sha256': hashlib.sha256(lock.read_bytes()).hexdigest()}]}
    return lock, plan


def lifecycle(tmp_path, **kwargs):
    _, plan = inputs(tmp_path)
    return HostRuntimeLifecycle({'a': adapter('a'), 'b': adapter('b')},
        budget_limits=LIMITS, audit_log=AUDIT,
        dependency_plan=plan, client=FixtureClient({}), **kwargs)


def test_stable_startup_shared_budget_and_task_completion(tmp_path):
    with lifecycle(tmp_path) as host:
        a = host.router('a', {'task_id': 'stable'})
        b = host.router('b', {'task_id': 'stable'})
        assert host.router('a', {'task_id': 'stable'}) is a
        callback = host.runtime_binding('a')
        assert callback({'task_id': 'stable'}) is a
        assert callback({'task_id': 'stable'}) is a
        assert a is not b and a.budget_coordinator is b.budget_coordinator is host.coordinator
        reservation = host.coordinator.reserve('stable', 1)
        host.coordinator.settle(reservation)
        reservation = host.coordinator.reserve('stable', 1)
        host.coordinator.settle(reservation)
        with pytest.raises(BudgetDenied, match='shared_total_call_budget'):
            host.coordinator.reserve('another', 1)
        host.complete_task('stable')
        with pytest.raises(LifecycleError, match='task_closed_or_budget_suspended'):
            host.router('b', {'task_id': 'stable'})
        assert host.coordinator.snapshot()['closed_tasks'] == 1
    assert a.closed and b.closed and host.coordinator.snapshot()['suspended']
    with pytest.raises(LifecycleError, match='runtime_closed_or_forked'):
        host.router('a', {'task_id': 'stable'})


def test_dependency_drift_and_unsafe_startup_fail_closed(tmp_path):
    lock, plan = inputs(tmp_path)
    lock.write_text('changed\n', encoding='utf-8')
    with pytest.raises(LifecycleError, match='dependency_plan_drift'):
        check_dependency_plan(plan)
    _, fresh_plan = inputs(tmp_path / 'fresh')
    with pytest.raises(LifecycleError, match='explicit_egress_authority_required'):
        HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
                             audit_log=AUDIT, dependency_plan=fresh_plan)
    with pytest.raises(LifecycleError, match='distributed_coordinator_unsupported'):
        lifecycle(tmp_path / 'distributed', process_model='multiprocess')


def test_scope_and_identity_binding(tmp_path):
    _, plan = inputs(tmp_path)
    with pytest.raises(LifecycleError, match='runtime_configuration_binding_mismatch'):
        HostRuntimeLifecycle({'a': adapter('a'), 'b': adapter('b', 'other')},
            budget_limits=LIMITS, audit_log=AUDIT, dependency_plan=plan,
            client=FixtureClient({}))
    with lifecycle(tmp_path / 'identity') as host:
        with pytest.raises(LifecycleError, match='stable_task_identity_required'):
            host.router('a', {})
        with pytest.raises(LifecycleError, match='unregistered_placement'):
            host.router('unknown', {'task_id': 'x'})


def test_adapter_contract_is_frozen_at_startup(tmp_path):
    _, plan = inputs(tmp_path)
    selected = adapter('a')
    with HostRuntimeLifecycle({'a': selected}, budget_limits=LIMITS,
                              audit_log=AUDIT, dependency_plan=plan,
                              client=FixtureClient({})) as host:
        selected.SPEC['runtime']['task_field'] = 'replacement'
        with pytest.raises(LifecycleError, match='adapter_contract_changed'):
            host.router('a', {'task_id': 'original'})
        with pytest.raises(LifecycleError, match='adapter_contract_changed'):
            host.router('a', {'replacement': 'new'})


def test_remote_client_cannot_bypass_egress_scope(tmp_path):
    _, plan = inputs(tmp_path)
    with pytest.raises(LifecycleError, match='remote_client_requires_exact_egress_grant'):
        HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
            audit_log=AUDIT, dependency_plan=plan,
            client=SimpleNamespace(is_remote=True))


def test_missing_remote_credentials_are_redacted(tmp_path, monkeypatch):
    _, plan = inputs(tmp_path)
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    with pytest.raises(LifecycleError, match='provider_startup_unavailable') as error:
        HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
            audit_log=AUDIT, dependency_plan=plan,
            egress_grant={'endpoint': 'https://api.typesafe.ai/v1/systemone',
                          'credential_ref': 'env:TYPESAFE_API_KEY'})
    assert 'TYPESAFE_API_KEY' not in str(error.value)


def test_placements_share_limits_across_threads(tmp_path):
    with lifecycle(tmp_path) as host:
        callbacks = [host.runtime_binding('a'), host.runtime_binding('b')]

        def reserve(index):
            router = callbacks[index % 2]({'task_id': 'same-task'})
            try:
                reservation = router.budget_coordinator.reserve('same-task', 1)
            except BudgetDenied as error:
                return error.reason
            router.budget_coordinator.settle(reservation)
            return 'charged'

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(reserve, range(8)))
        assert outcomes.count('charged') == 2
        assert host.coordinator.snapshot()['calls'] == 2
        assert host.coordinator.snapshot()['reserved_cost'] == 2


def test_synthetic_shadow_is_explicit_and_active_is_rejected(tmp_path):
    with lifecycle(tmp_path, startup_mode='shadow') as host:
        assert host.router('a', {'task_id': 'x'}).config['mode'] == 'shadow'
        assert host.router('b', {'task_id': 'x'}).config['mode'] == 'shadow'
    with pytest.raises(LifecycleError, match='activation_requires_separate_reviewed_runtime'):
        lifecycle(tmp_path / 'active', startup_mode='active')


@pytest.mark.parametrize('mode', ['off', 'shadow'])
def test_actual_generated_host_uses_startup_router_without_probe_replacement(tmp_path, mode):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'C', tag='lifecycle_' + mode)
    derived = transform(root, spec)
    for change in derived['changes']:
        (root / change['file']).write_text(change['new_content'], encoding='utf-8', newline='')
    source_name = spec['source']['file'][:-3]
    adapter_name = spec['output']['module']
    sys.path.insert(0, str(root))
    try:
        loader = importlib.util.spec_from_file_location(source_name, root / spec['source']['file'])
        module = importlib.util.module_from_spec(loader)
        sys.modules[source_name] = module
        loader.loader.exec_module(module)
        adapter_module = sys.modules[adapter_name]
        _, plan = inputs(tmp_path / 'dependencies')
        client = SyntheticClient(spec['verification']['cases'][0]['assessment_label'])
        with HostRuntimeLifecycle({spec['candidate_id']: adapter_module},
                budget_limits=LIMITS, audit_log=SyntheticAudit(),
                dependency_plan=plan, client=client, startup_mode=mode) as host:
            # The application performs this assignment at startup. The verifier
            # neither substitutes a router callback per call nor grants active mode.
            module.__dict__[spec['bindings']['runtime']] = host.runtime_binding(spec['candidate_id'])
            adapter_module.ENABLED = True
            request = copy.deepcopy(spec['verification']['cases'][0]['request'])
            entry = module.__dict__[spec['verification']['entry_point']]
            first = entry(copy.deepcopy(request))
            second = entry(copy.deepcopy(request))
            assert first == second
            router = host.router(spec['candidate_id'], request)
            assert router is host.router(spec['candidate_id'], request)
            assert router.config['mode'] == mode
            host.complete_task(request[spec['runtime']['task_field']])
            assert host.coordinator.snapshot()['closed_tasks'] == 1
        assert router.closed
        if mode == 'off':
            assert client.calls == 0
        else:
            assert client.calls >= 1
    finally:
        sys.path.remove(str(root))
        sys.modules.pop(source_name, None)
        sys.modules.pop(adapter_name, None)


def test_reviewed_lock_and_config_edits_are_owned_and_rollback(tmp_path):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'C', tag='runtime_files')
    originals = {
        'requirements.lock': 'jev-integration-evaluator==1.3.0.dev1\n',
        'runtime.json': '{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
    }
    changed = {
        'requirements.lock': 'jev-integration-evaluator==1.3.0.dev11\n',
        'runtime.json': '{"jev_runtime":{"mode":"off","credential_ref":"env:TYPESAFE_API_KEY"}}\n',
    }
    kinds = {'requirements.lock': 'dependency_lock', 'runtime.json': 'configuration'}
    for name, content in originals.items():
        (root / name).write_text(content, encoding='utf-8', newline='')
        inventory['configuration_evidence'].append({
            'file': name, 'sha256': hashlib.sha256(content.encode()).hexdigest()})
    inventory['analysis_identity']['configuration_digest'] = digest(inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    spec['inventory_sha256'] = digest(inventory)
    spec['inventory_fingerprint'] = inventory['scan_fingerprint']
    spec['runtime_files'] = [{'file': name, 'kind': kinds[name],
                              'old_sha256': hashlib.sha256(originals[name].encode()).hexdigest(),
                              'new_content': changed[name]} for name in originals]
    spec['output']['permitted_edits'].extend(originals)
    unowned = copy.deepcopy(spec)
    unowned['output']['permitted_edits'].remove('runtime.json')
    with pytest.raises(InputError, match='Permitted edits'):
        validate_spec(unowned)
    protected = copy.deepcopy(spec)
    protected['runtime_files'][0]['file'] = '.env'
    protected['output']['permitted_edits'][2] = '.env'
    with pytest.raises(InputError, match='Invalid or unchanged reviewed runtime file'):
        validate_spec(protected)
    active_config = copy.deepcopy(spec)
    active_config['runtime_files'][1]['new_content'] = '{"jev_runtime":{"mode":"active","credential_ref":null}}'
    with pytest.raises(InputError, match='Runtime configuration must remain off'):
        validate_spec(active_config)
    conflicting_lock = copy.deepcopy(spec)
    conflicting_lock['runtime_files'][0]['new_content'] += 'jev_integration_evaluator==2.0\n'
    with pytest.raises(InputError, match='Conflicting or missing evaluator dependency lock'):
        validate_spec(conflicting_lock)
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert planned['status'] == 'planned'
    plan = __import__('json').loads((bundle / 'implementation-plan.json').read_text())
    assert set(originals) <= {row['file'] for row in plan['owned_files']}
    assert all((root / name).read_text() == content for name, content in originals.items())
    baseline = verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_implementation(root, bundle, planned['bundle_digest'],
                                   baseline_sha256=baseline['receipt_sha256'])
    assert all((root / name).read_text() == content for name, content in changed.items())
    assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
    assert all((root / name).read_text() == content for name, content in originals.items())
