"""Synthetic edited hosts: executor exceptions are not routing instructions."""
from contextlib import contextmanager

import pytest

from integration_helpers import bound_host
from jev_integration_evaluator.integrations import host as bound_runtime
from jev_integration_evaluator.integrations.host import PolicyBlock, UseFallback
from jev_integration_evaluator.integrations.probe import _fixture_receipt


def test_e_synthetic_shadow_keeps_original_result_without_assessment(tmp_path):
    with bound_host(tmp_path, 'E') as (module, adapter, router, spec, client, call):
        router.config['mode'] = 'shadow'
        router.activation = _fixture_receipt(router, spec)
        result = call()
        assert result == {'reported': 'ok'}
        assert module.STATE['effects'] == ['first']
        assert client.calls == 0
        assert module.STATE['blocked'] == 0


@contextmanager
def _connected_e_shadow(tmp_path, monkeypatch):
    """Drive the connected E observation path without a durable lifecycle.

    Owner recognition is qualified by the installed connected test. Here it is
    forced so the post-effect observation boundary can be exercised in process.
    """
    with bound_host(tmp_path, 'E') as (module, adapter, router, spec, client, call):
        router.config['mode'] = 'shadow'
        router.activation = _fixture_receipt(router, spec)
        monkeypatch.setattr(bound_runtime, '_connected_e_owner', lambda router, candidate: True)
        yield module, router, spec, client, call


def test_connected_e_shadow_assesses_only_after_one_completed_effect(tmp_path, monkeypatch):
    with _connected_e_shadow(tmp_path, monkeypatch) as (module, router, spec, client, call):
        assert call() == {'reported': 'ok'}
        assert module.STATE['effects'] == ['first']
        assert module.STATE['blocked'] == 0
        assert client.calls == 1


@pytest.mark.parametrize('failing_observation', [1, 2])
def test_connected_e_observation_failure_keeps_original_result(tmp_path, monkeypatch,
                                                               failing_observation):
    with _connected_e_shadow(tmp_path, monkeypatch) as (module, router, spec, client, call):
        name = spec['bindings']['observe']
        real, seen = module.__dict__[name], []

        def observe(request):
            seen.append(True)
            if len(seen) == failing_observation:
                raise RuntimeError('synthetic observation failure')
            return real(request)

        module.__dict__[name] = observe
        assert call() == {'reported': 'ok'}
        assert module.STATE['effects'] == ['first']
        assert client.calls == 0


def test_connected_e_assessment_failure_keeps_original_result(tmp_path, monkeypatch):
    with _connected_e_shadow(tmp_path, monkeypatch) as (module, router, spec, client, call):
        def refuse(**kwargs):
            raise RuntimeError('synthetic assessment failure')

        monkeypatch.setattr(router, 'route', refuse)
        assert call() == {'reported': 'ok'}
        assert module.STATE['effects'] == ['first']
        assert module.STATE['blocked'] == 0


@pytest.mark.parametrize('interrupted_observation', [1, 2])
def test_connected_e_observation_interrupt_propagates(tmp_path, monkeypatch,
                                                      interrupted_observation):
    with _connected_e_shadow(tmp_path, monkeypatch) as (module, router, spec, client, call):
        name = spec['bindings']['observe']
        real, seen = module.__dict__[name], []

        def observe(request):
            seen.append(True)
            if len(seen) == interrupted_observation:
                raise KeyboardInterrupt
            return real(request)

        module.__dict__[name] = observe
        with pytest.raises(KeyboardInterrupt):
            call()
        # An interrupt before the executor prevents the effect; one after the
        # completed effect leaves exactly that one effect and no retry.
        assert module.STATE['effects'] == ([] if interrupted_observation == 1 else ['first'])
        assert client.calls == 0


@pytest.mark.parametrize('error_type', [PolicyBlock, UseFallback])
@pytest.mark.parametrize('mode', ['flag_off', 'runtime_off', 'shadow', 'active', 'fallback'])
def test_host_control_exceptions_propagate_once(tmp_path, error_type, mode):
    with bound_host(tmp_path) as (module, adapter, router, spec, client, call):
        error = error_type('host-owned control exception')
        def operation(request):
            module.STATE['effects'].append('completed')
            raise error
        for action in ('base', 'alt'):
            name = module.OPTIONS[action].__name__
            module.__dict__[name] = operation
            module.OPTIONS[action] = operation
        if mode == 'flag_off':
            adapter.ENABLED = False
        elif mode in ('runtime_off', 'shadow'):
            router.config['mode'] = 'off' if mode == 'runtime_off' else 'shadow'
            router.activation = _fixture_receipt(router, spec)
        elif mode == 'fallback':
            client.fault = 'provider'
        with pytest.raises(error_type) as caught:
            call()
        assert caught.value is error
        assert module.STATE['effects'] == ['completed']
        assert module.STATE['blocked'] == 0
        if mode in ('flag_off', 'runtime_off'):
            assert client.calls == 0


@pytest.mark.parametrize('error_type', [PolicyBlock, UseFallback])
@pytest.mark.parametrize('pattern', list('ABDEGHIJL'))
def test_recipe_effects_cannot_reinterpret_host_exceptions(tmp_path, pattern, error_type):
    with bound_host(tmp_path, pattern) as (module, adapter, router, spec, client, call):
        if pattern == 'A':
            client.label = 'primary'
        error = error_type('host effect was already attempted')
        def operation(*args):
            module.STATE['effects'].append('completed')
            raise error
        effects = spec['verification']['effect_symbols']
        for name in effects:
            old = module.__dict__[name]
            module.__dict__[name] = operation
            for key, value in module.OPTIONS.items():
                if value is old:
                    module.OPTIONS[key] = operation
        with pytest.raises(error_type) as caught:
            call()
        assert caught.value is error
        assert module.STATE['effects'] == ['completed']
        assert module.STATE['blocked'] == 0


@pytest.mark.parametrize('error_type', [PolicyBlock, UseFallback])
def test_later_plan_executor_exception_is_not_a_preflight_block(tmp_path, error_type):
    with bound_host(tmp_path, 'G') as (module, adapter, router, spec, client, call):
        client.label = 'unresolved'
        error = error_type('second executor failed after effect')
        second = spec['verification']['effect_symbols'][1]
        def operation(request):
            module.STATE['effects'].append('second-attempted')
            raise error
        module.__dict__[second] = operation
        with pytest.raises(error_type) as caught:
            call()
        assert caught.value is error
        assert module.STATE['effects'] == ['first', 'second-attempted']
        assert module.STATE['blocked'] == 0


@pytest.mark.parametrize('error_type', [PolicyBlock, UseFallback])
@pytest.mark.parametrize('pattern', ['E', 'G', 'J'])
def test_finishing_exception_preserves_already_completed_outcome(tmp_path, error_type, pattern):
    with bound_host(tmp_path, pattern) as (module, adapter, router, spec, client, call):
        error = error_type('host result handler failed')
        attempted = []
        def finish(*args):
            attempted.append(args)
            raise error
        module.__dict__[spec['bindings']['finish']] = finish
        with pytest.raises(error_type) as caught:
            call()
        assert caught.value is error and len(attempted) == 1
        assert len(module.STATE['effects']) == 1
        assert module.STATE['blocked'] == 0


@pytest.mark.parametrize('error_type', [PolicyBlock, UseFallback])
def test_guard_cleanup_failure_after_executor_does_not_replay(tmp_path, error_type):
    with bound_host(tmp_path) as (module, adapter, router, spec, client, call):
        error = error_type('host guard cleanup failed')
        @contextmanager
        def guard(request):
            with module.LOCK:
                yield
                raise error
        module.__dict__[spec['bindings']['guard']] = guard
        with pytest.raises(error_type) as caught:
            call()
        assert caught.value is error
        assert module.STATE['effects'] == ['second']
        assert module.STATE['blocked'] == 0


@pytest.mark.parametrize('error_type', [PolicyBlock, UseFallback])
@pytest.mark.parametrize('pattern', ['E', 'G'])
def test_later_guard_cleanup_failure_preserves_exception_and_stops_finishing(tmp_path, error_type, pattern):
    with bound_host(tmp_path, pattern) as (module, adapter, router, spec, client, call):
        client.label = 'succeeded' if pattern == 'E' else 'unresolved'
        error = error_type('host cleanup failed after a completed effect')
        entered, finished = [], []
        @contextmanager
        def guard(request):
            with module.LOCK:
                entered.append(len(entered) + 1)
                yield
                # E: postcondition guard; G: first step after the plan preflight.
                if len(entered) == 2:
                    raise error
        original_finish = module.__dict__[spec['bindings']['finish']]
        def finish(*args):
            finished.append(args)
            return original_finish(*args)
        module.__dict__[spec['bindings']['guard']] = guard
        module.__dict__[spec['bindings']['finish']] = finish
        with pytest.raises(error_type) as caught:
            call()
        assert caught.value is error
        assert entered == [1, 2]
        assert module.STATE['effects'] == ['first']
        assert finished == [] and module.STATE['blocked'] == 0


@pytest.mark.parametrize('error_type', [PolicyBlock, UseFallback])
def test_guard_sees_original_executor_exception(tmp_path, error_type):
    with bound_host(tmp_path) as (module, adapter, router, spec, client, call):
        error = error_type('same exception must reach host cleanup')
        observed = []
        @contextmanager
        def guard(request):
            try:
                yield
            except error_type as caught:
                observed.append(caught)
                raise
        def operation(request):
            module.STATE['effects'].append('completed')
            raise error
        module.__dict__[spec['bindings']['guard']] = guard
        module.OPTIONS['alt'] = operation
        with pytest.raises(error_type) as caught:
            call()
        assert caught.value is error and observed == [error]
        assert module.STATE['effects'] == ['completed']


@pytest.mark.parametrize('error_type', [PolicyBlock, UseFallback])
def test_completed_recovery_callback_exception_never_restarts_effect(tmp_path, error_type):
    with bound_host(tmp_path, 'I') as (module, adapter, router, spec, client, call):
        module.STATE['completed'] = True
        error = error_type('completed result retrieval failed')
        def completed(request):
            raise error
        module.__dict__[spec['bindings']['completed']] = completed
        with pytest.raises(error_type) as caught:
            call()
        assert caught.value is error
        assert module.STATE['effects'] == [] and module.STATE['blocked'] == 0
        assert client.calls == 0


@pytest.mark.parametrize('ownership', ['coordinator', 'router'])
def test_dropped_runtime_cannot_reset_workflow_budget_ownership(tmp_path, ownership):
    import copy
    import gc
    import weakref
    from jev_integration_evaluator.budget import BudgetCoordinator
    with bound_host(tmp_path) as (module, adapter, unused_router, spec, client, call):
        references = []
        def construct_per_decision(request):
            ledger = BudgetCoordinator(max_calls_per_task=1, max_cost_per_task=10,
                                       max_total_calls=1, max_total_cost=20, max_in_flight=1, max_tasks=64)
            if ownership == 'router':
                ledger = unused_router.budget_coordinator
            config = copy.deepcopy(spec['runtime']['configuration'])
            config['mode'] = 'active'
            router = adapter.create_router(client, budget_coordinator=ledger,
                                            audit_log=unused_router.log, runtime_config=config)
            router.activation = _fixture_receipt(router, spec)
            references.append(weakref.ref(router))
            return router
        module.__dict__[spec['bindings']['runtime']] = construct_per_decision
        assert call() == 'second'
        gc.collect()
        assert references[0]() is None
        assert call() == 'blocked'
        assert client.calls == 1 and module.STATE['effects'] == ['second']
