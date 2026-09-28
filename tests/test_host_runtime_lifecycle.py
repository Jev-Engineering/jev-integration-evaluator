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
from jev_integration_evaluator.integrations import runtime_lifecycle
from jev_integration_evaluator.runtime import SafeRouter
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.integrations.contracts import validate_spec
from jev_integration_evaluator.integrations.lifecycle import (
    plan_implementation, apply_implementation, rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.integrations.verification import _observable
from jev_integration_evaluator.integrations.recipes import host_lifecycle_marker
from jev_integration_evaluator.integrations.recipes import transform
from jev_integration_evaluator.integrations.probe import SyntheticClient, SyntheticAudit
from scripts.implementation_fixtures import fixture


LIMITS = dict(max_calls_per_task=2, max_cost_per_task=2,
              max_total_calls=2, max_total_cost=2, max_in_flight=1, max_tasks=2)
AUDIT = SimpleNamespace(append=lambda event: None)


def reviewed_host_lock(root, inventory, spec):
    files = {
        'requirements.lock': ('dependency_lock', 'jev-integration-evaluator==1.3.0.dev1\n',
                              'jev-integration-evaluator==1.3.0.dev11\n'),
        'runtime.json': ('configuration', '{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
                         '{"jev_runtime":{"mode":"off","credential_ref":"env:TYPESAFE_API_KEY"}}\n'),
    }
    for name, (_, old, _) in files.items():
        (root / name).write_text(old, encoding='utf-8')
        inventory['configuration_evidence'].append({
            'file': name, 'sha256': hashlib.sha256(old.encode()).hexdigest()})
    inventory['analysis_identity']['configuration_digest'] = digest(inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    spec['inventory_sha256'] = digest(inventory)
    spec['inventory_fingerprint'] = inventory['scan_fingerprint']
    spec['runtime_files'] = [{'file': name, 'kind': kind,
                              'old_sha256': hashlib.sha256(old.encode()).hexdigest(),
                              'new_content': new} for name, (kind, old, new) in files.items()]
    spec['output']['permitted_edits'].extend(files)
    return {'files': [{'path': str((root / name).resolve()),
                       'sha256': hashlib.sha256(new.encode()).hexdigest()}
                      for name, (_, _, new) in files.items()]}


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
    with HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
                              audit_log=AUDIT, dependency_plan=fresh_plan) as disabled:
        assert disabled.router('a', {'task_id': 'off'}) is disabled.router('a', {'task_id': 'off'})
        with pytest.raises(LifecycleError, match='provider_unavailable_without_egress'):
            disabled._client.evaluate({}, {}, 'synthetic', 1)
        with pytest.raises(LifecycleError, match='provider_probe_unavailable'):
            disabled.connectivity_probe_plan()
    with pytest.raises(LifecycleError, match='explicit_egress_authority_required'):
        HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
                             audit_log=AUDIT, dependency_plan=fresh_plan,
                             startup_mode='shadow')
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
                          'credential_ref': 'env:TYPESAFE_API_KEY',
                          'cost_upper_bound': 0.1})
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


def test_provider_probe_needs_separate_exact_egress_and_never_activates(tmp_path, monkeypatch):
    _, plan = inputs(tmp_path)
    sent = []

    class FakeRemote:
        is_remote = True

        def __init__(self, **kwargs):
            assert kwargs['allow_network'] is True

        def evaluate(self, state, questions, model, timeout_ms):
            sent.append((state, questions, model, timeout_ms))
            return {'model': model, 'answers': {'probe': {'type': 'choice',
                    'choice': 'marker', 'confidence': 1.0,
                    'probabilities': {'marker': 1.0, 'other': 0.0}}},
                    'usage': {'input_tokens': 1, 'output_tokens': 1}}

    monkeypatch.setattr(runtime_lifecycle, 'TypeSafeHTTPClient', FakeRemote)
    grant = {'endpoint': 'https://api.typesafe.ai/v1/systemone',
             'credential_ref': 'env:TYPESAFE_API_KEY', 'cost_upper_bound': 0.1}
    with HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
            audit_log=AUDIT, dependency_plan=plan, egress_grant=grant) as host:
        approved = digest(host.connectivity_probe_plan())
        with pytest.raises(LifecycleError, match='exact_provider_probe_authority_required'):
            host.probe_provider_connectivity(approved_request_sha256='0' * 64,
                                             egress_grant=grant)
        assert not sent
        # Rejected authority leaves the one permitted probe unused.
        report = host.probe_provider_connectivity(approved_request_sha256=approved,
                                                  egress_grant=grant)
        assert report['status'] == 'synthetic_provider_reachable'
        assert report['activation_authorized'] is False
        assert sent[0][0] == {'jev_probe': 'synthetic_connectivity_only'}
        assert host.coordinator.snapshot()['calls'] == 1
        assert host.router('a', {'task_id': 'unrelated'}).config['mode'] == 'off'
        with pytest.raises(LifecycleError, match='exact_provider_probe_authority_required'):
            host.probe_provider_connectivity(approved_request_sha256=approved,
                                             egress_grant=grant)


@pytest.mark.parametrize('fault', [TimeoutError, RuntimeError])
def test_provider_probe_failure_is_redacted_and_charged(tmp_path, monkeypatch, fault):
    _, plan = inputs(tmp_path)

    class FailingRemote:
        is_remote = True

        def __init__(self, **kwargs):
            pass

        def evaluate(self, state, questions, model, timeout_ms):
            raise fault('sensitive provider diagnostic')

    monkeypatch.setattr(runtime_lifecycle, 'TypeSafeHTTPClient', FailingRemote)
    grant = {'endpoint': 'https://api.typesafe.ai/v1/systemone',
             'credential_ref': 'env:TYPESAFE_API_KEY', 'cost_upper_bound': 0.1}
    with HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
            audit_log=AUDIT, dependency_plan=plan, egress_grant=grant) as host:
        approved = digest(host.connectivity_probe_plan())
        report = host.probe_provider_connectivity(approved_request_sha256=approved,
                                                  egress_grant=grant)
        assert report['status'] == 'provider_probe_failed'
        assert 'sensitive' not in str(report)
        assert host.coordinator.snapshot()['calls'] == 1
        assert host.coordinator.snapshot()['closed_tasks'] == 1


def test_probe_audit_failure_blocks_egress_before_request(tmp_path, monkeypatch):
    _, plan = inputs(tmp_path)
    sent = []

    class Remote:
        is_remote = True

        def __init__(self, **kwargs):
            pass

        def evaluate(self, *args):
            sent.append(args)
            raise AssertionError('must not reach provider')

    class BrokenAudit:
        def append(self, event):
            raise OSError('private audit path')

    monkeypatch.setattr(runtime_lifecycle, 'TypeSafeHTTPClient', Remote)
    grant = {'endpoint': 'https://api.typesafe.ai/v1/systemone',
             'credential_ref': 'env:TYPESAFE_API_KEY', 'cost_upper_bound': 0.1}
    with HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
            audit_log=BrokenAudit(), dependency_plan=plan, egress_grant=grant) as host:
        with pytest.raises(LifecycleError, match='provider_probe_audit_unavailable'):
            host.probe_provider_connectivity(
                approved_request_sha256=digest(host.connectivity_probe_plan()),
                egress_grant=grant)
        assert not sent and host.coordinator.snapshot()['calls'] == 0


def test_probe_budget_denial_cannot_retry_egress(tmp_path, monkeypatch):
    _, plan = inputs(tmp_path)
    sent = []

    class Remote:
        is_remote = True

        def __init__(self, **kwargs):
            pass

        def evaluate(self, *args):
            sent.append(args)
            raise AssertionError('must not reach provider')

    monkeypatch.setattr(runtime_lifecycle, 'TypeSafeHTTPClient', Remote)
    grant = {'endpoint': 'https://api.typesafe.ai/v1/systemone',
             'credential_ref': 'env:TYPESAFE_API_KEY', 'cost_upper_bound': 0.1}
    with HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
            audit_log=AUDIT, dependency_plan=plan, egress_grant=grant) as host:
        for _ in range(2):
            reservation = host.coordinator.reserve('existing', 1)
            host.coordinator.settle(reservation)
        approved = digest(host.connectivity_probe_plan())
        with pytest.raises(LifecycleError, match='provider_probe_budget_denied'):
            host.probe_provider_connectivity(approved_request_sha256=approved,
                                             egress_grant=grant)
        with pytest.raises(LifecycleError, match='exact_provider_probe_authority_required'):
            host.probe_provider_connectivity(approved_request_sha256=approved,
                                             egress_grant=grant)
        assert not sent and host.coordinator.snapshot()['calls'] == 2


def test_post_egress_audit_failure_does_not_replay(tmp_path, monkeypatch):
    _, plan = inputs(tmp_path)
    sent = []

    class Remote:
        is_remote = True

        def __init__(self, **kwargs):
            pass

        def evaluate(self, state, questions, model, timeout_ms):
            sent.append(state)
            return {'model': model, 'answers': {'probe': {'type': 'choice',
                    'choice': 'marker', 'confidence': 1.0,
                    'probabilities': {'marker': 1.0, 'other': 0.0}}},
                    'usage': {'input_tokens': 1, 'output_tokens': 1}}

    class ResultAudit:
        def append(self, event):
            if event['type'] == 'synthetic_provider_probe_result':
                raise OSError('private audit path')

    monkeypatch.setattr(runtime_lifecycle, 'TypeSafeHTTPClient', Remote)
    grant = {'endpoint': 'https://api.typesafe.ai/v1/systemone',
             'credential_ref': 'env:TYPESAFE_API_KEY', 'cost_upper_bound': 0.1}
    with HostRuntimeLifecycle({'a': adapter('a')}, budget_limits=LIMITS,
            audit_log=ResultAudit(), dependency_plan=plan, egress_grant=grant) as host:
        approved = digest(host.connectivity_probe_plan())
        with pytest.raises(LifecycleError, match='provider_probe_audit_unavailable'):
            host.probe_provider_connectivity(approved_request_sha256=approved,
                                             egress_grant=grant)
        with pytest.raises(LifecycleError, match='exact_provider_probe_authority_required'):
            host.probe_provider_connectivity(approved_request_sha256=approved,
                                             egress_grant=grant)
        assert len(sent) == 1 and host.coordinator.snapshot()['calls'] == 1


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
    plan = reviewed_host_lock(root, inventory, spec)
    spec['host_lifecycle'] = {'kind': 'module-startup-v1', 'startup': 'start_jev_runtime',
                              'shutdown': 'stop_jev_runtime', 'complete_task': 'finish_jev_task'}
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
        client = SyntheticClient(spec['verification']['cases'][0]['assessment_label'])
        rogue = tmp_path / 'unreviewed.lock'
        rogue.write_text('offline-test==1.0\n', encoding='utf-8')
        wrong = copy.deepcopy(plan)
        wrong['files'][0] = {'path': str(rogue.resolve()),
                             'sha256': hashlib.sha256(rogue.read_bytes()).hexdigest()}
        with pytest.raises(LifecycleError, match='reviewed_dependency_plan_mismatch'):
            module.start_jev_runtime(budget_limits=LIMITS, audit_log=SyntheticAudit(),
                                     dependency_plan=wrong, client=client)
        with pytest.raises(LifecycleError, match='reviewed_dependency_plan_mismatch'):
            module.start_jev_runtime(budget_limits=LIMITS, audit_log=SyntheticAudit(),
                                     dependency_plan={'files': [{'path': [], 'sha256': 'x'}]},
                                     client=client)
        host = module.start_jev_runtime(budget_limits=LIMITS, audit_log=SyntheticAudit(),
                                        dependency_plan=plan, client=(client if mode == 'shadow' else None),
                                        startup_mode=mode,
                                        enable_experiment=(mode == 'shadow'))
        try:
            request = copy.deepcopy(spec['verification']['cases'][0]['request'])
            entry = module.__dict__[spec['verification']['entry_point']]
            first = entry(copy.deepcopy(request))
            second = entry(copy.deepcopy(request))
            assert first == second
            router = host.router(spec['candidate_id'], request)
            assert router is host.router(spec['candidate_id'], request)
            assert router.config['mode'] == mode
            module.finish_jev_task(request[spec['runtime']['task_field']])
            assert host.coordinator.snapshot()['closed_tasks'] == 1
            with pytest.raises(RuntimeError, match='host_runtime_already_started'):
                module.start_jev_runtime(budget_limits=LIMITS, audit_log=SyntheticAudit(),
                                         dependency_plan=plan, client=client)
        finally:
            module.stop_jev_runtime()
        assert router.closed
        if mode == 'off':
            assert client.calls == 0
        else:
            assert client.calls >= 1
    finally:
        sys.path.remove(str(root))
        sys.modules.pop(source_name, None)
        sys.modules.pop(adapter_name, None)


def test_generated_host_lifecycle_rejects_collision_and_keyword(tmp_path):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'C', tag='lifecycle_reject')
    reviewed_host_lock(root, inventory, spec)
    spec['host_lifecycle'] = {'kind': 'module-startup-v1', 'startup': spec['bindings']['runtime'],
                              'shutdown': 'stop_jev_runtime', 'complete_task': 'finish_jev_task'}
    missing_config = copy.deepcopy(spec)
    missing_config['runtime_files'] = missing_config['runtime_files'][:1]
    missing_config['output']['permitted_edits'].remove('runtime.json')
    with pytest.raises(InputError, match='reviewed lock and configuration'):
        validate_spec(missing_config)
    with pytest.raises(Exception, match='Unsupported host lifecycle'):
        transform(root, spec)
    spec['host_lifecycle']['startup'] = 'class'
    with pytest.raises(Exception, match='Unsupported host lifecycle'):
        transform(root, spec)
    spec['host_lifecycle']['startup'] = 'start_jev_runtime'
    marker = host_lifecycle_marker(spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    source = root / spec['source']['file']
    source.write_text(source.read_text(encoding='utf-8') + '\n' + marker + '_started = False\n',
                      encoding='utf-8')
    with pytest.raises(Exception, match='Unsupported host lifecycle'):
        transform(root, spec)


def test_neutral_generated_globals_only_are_excluded_from_parity(tmp_path):
    root = tmp_path / 'target'
    _, spec = fixture(root, 'C', tag='lifecycle_parity')
    spec['host_lifecycle'] = {'kind': 'module-startup-v1', 'startup': 'start_jev_runtime',
                              'shutdown': 'stop_jev_runtime', 'complete_task': 'finish_jev_task'}
    marker = host_lifecycle_marker(spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    base = {'outcome': {'result': 'first'}, 'globals': {'STATE': {'effects': []}}, 'calls': {}}
    modified = copy.deepcopy(base)
    modified['globals'].update({marker: None, marker + '_started': False})
    assert _observable(base, spec) == _observable(modified, spec)
    modified['globals'][marker + '_started'] = True
    assert _observable(base, spec) != _observable(modified, spec)


def test_reviewed_lock_and_config_edits_are_owned_and_rollback(tmp_path):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'C', tag='runtime_files')
    spec['host_lifecycle'] = {'kind': 'module-startup-v1', 'startup': 'start_jev_runtime',
                              'shutdown': 'stop_jev_runtime', 'complete_task': 'finish_jev_task'}
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
    manifest = __import__('json').loads((bundle / 'implementation-manifest.json').read_text())
    assert manifest['host_lifecycle'] == spec['host_lifecycle']
    assert all((root / name).read_text() == content for name, content in originals.items())
    baseline = verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_implementation(root, bundle, planned['bundle_digest'],
                                   baseline_sha256=baseline['receipt_sha256'])
    assert all((root / name).read_text() == content for name, content in changed.items())
    assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
    assert all((root / name).read_text() == content for name, content in originals.items())
