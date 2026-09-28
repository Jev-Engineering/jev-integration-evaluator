"""Offline host-owned runtime startup contracts; no provider or target imports."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from jev_integration_evaluator.budget import BudgetDenied
from jev_integration_evaluator.client import FixtureClient
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.integrations.runtime_lifecycle import (
    HostRuntimeLifecycle, LifecycleError, check_dependency_plan,
)
from jev_integration_evaluator.runtime import SafeRouter


LIMITS = dict(max_calls_per_task=2, max_cost_per_task=2,
              max_total_calls=2, max_total_cost=2, max_in_flight=1, max_tasks=2)


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
        budget_limits=LIMITS, audit_log=SimpleNamespace(append=lambda event: None),
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
                             audit_log=object(), dependency_plan=fresh_plan)
    with pytest.raises(LifecycleError, match='distributed_coordinator_unsupported'):
        lifecycle(tmp_path / 'distributed', process_model='multiprocess')


def test_scope_and_identity_binding(tmp_path):
    _, plan = inputs(tmp_path)
    with pytest.raises(LifecycleError, match='runtime_configuration_binding_mismatch'):
        HostRuntimeLifecycle({'a': adapter('a'), 'b': adapter('b', 'other')},
            budget_limits=LIMITS, audit_log=object(), dependency_plan=plan,
            client=FixtureClient({}))
    with lifecycle(tmp_path / 'identity') as host:
        with pytest.raises(LifecycleError, match='stable_task_identity_required'):
            host.router('a', {})
        with pytest.raises(LifecycleError, match='unregistered_placement'):
            host.router('unknown', {'task_id': 'x'})


def test_task_field_is_frozen_at_startup(tmp_path):
    _, plan = inputs(tmp_path)
    selected = adapter('a')
    with HostRuntimeLifecycle({'a': selected}, budget_limits=LIMITS,
                              audit_log=object(), dependency_plan=plan,
                              client=FixtureClient({})) as host:
        selected.SPEC['runtime']['task_field'] = 'replacement'
        assert host.router('a', {'task_id': 'original'}) is host.router('a', {'task_id': 'original'})
        with pytest.raises(LifecycleError, match='stable_task_identity_required'):
            host.router('a', {'replacement': 'new'})


def test_remote_client_cannot_bypass_egress_scope(tmp_path):
    _, plan = inputs(tmp_path)
    with pytest.raises(LifecycleError, match='remote_client_requires_exact_egress_grant'):
        HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
            audit_log=object(), dependency_plan=plan,
            client=SimpleNamespace(is_remote=True))


def test_synthetic_shadow_is_explicit_and_active_is_rejected(tmp_path):
    with lifecycle(tmp_path, startup_mode='shadow') as host:
        assert host.router('a', {'task_id': 'x'}).config['mode'] == 'shadow'
        assert host.router('b', {'task_id': 'x'}).config['mode'] == 'shadow'
    with pytest.raises(LifecycleError, match='activation_requires_separate_reviewed_runtime'):
        lifecycle(tmp_path / 'active', startup_mode='active')
