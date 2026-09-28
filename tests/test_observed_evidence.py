"""Synthetic-only issue #15 identity and offline collection qualifications."""
import copy

import pytest

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.contracts import seal
from jev_integration_evaluator.io import InputError, digest, read_json, write_json
from jev_integration_evaluator.cli import main as cli_main
from jev_integration_evaluator.study import freeze_study
from jev_integration_evaluator.integrations.lifecycle import plan_implementation, apply_implementation
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.observed_evidence import (
    expected_study_arm, freeze_link, check_link, collect_offline, evaluate_linked,
)
from jev_integration_evaluator.host_collection import collect_host_pairs
from scripts.implementation_fixtures import fixture
from scripts.v12_fixtures import monitor_fixture
from jev_integration_evaluator.monitoring import freeze_monitor


def prepared(tmp_path):
    root, bundle = tmp_path / 'host', tmp_path / 'bundle'
    inventory, spec = fixture(root, 'C', tag='observed_link')
    planned = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    apply_implementation(root, bundle, planned['bundle_digest'],
                         baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(root, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    plan = read_json(bundle / 'implementation-plan.json')
    return root, bundle, spec, plan, modified['receipt_sha256']


def study_and_rows(root, bundle, spec, plan, cfg):
    arm = expected_study_arm(root, bundle)
    schedule = [{'task_id': f'task-{i}', 'replicate': 0, 'task_hash': digest(f'task-{i}'),
                 'cluster_id': f'cluster-{i}', 'split': 'test', 'seed': i} for i in range(2)]
    baseline = {'treatment': 'baseline', 'code_revision': digest([
        (r['file'], r['old_sha256'], r['old_mode']) for r in plan['owned_files']]),
        'model_id': 'baseline-model', 'policy_version': 'baseline-policy',
        'prompt_hash': digest('baseline-rubric'), 'mode': 'baseline'}
    jev = {'treatment': 'jev', **arm, 'mode': 'active'}
    study = freeze_study({'experiment_id': spec['experiment_id'], 'dataset_id': 'synthetic-dataset',
        'evidence_type': 'synthetic', 'primary_metric': 'success', 'schedule': schedule,
        'baseline': baseline, 'jev': jev,
        'required_metrics': ['cost', 'latency_ms', 'unsafe_actions', 'false_blocks']}, cfg)
    placement = seal({'schema_version': '1.0', 'selected_candidate_ids': [spec['candidate_id']],
                      'reviewed_inventory_sha256': spec['inventory_sha256'],
                      'selection_sha256': digest('independently-reviewed-fixture-selection')})
    labels = [{'task_id': r['task_id'], 'replicate': 0, 'task_hash': r['task_hash'],
               'expected_label': 'correct', 'reviewer': 'independent-fixture-reviewer',
               'source_sha256': digest(r['task_id'])} for r in schedule]
    def outcome(label, status='completed'):
        return {'run_status': status, 'output_label': label,
                'metrics': {'cost': 0.01, 'latency_ms': 10, 'unsafe_actions': 0, 'false_blocks': 0}}
    fixtures = [{'task_id': r['task_id'], 'replicate': 0, 'task_hash': r['task_hash'],
                 'baseline': outcome('wrong'), 'jev': outcome('correct')}
                for r in schedule]
    return study, placement, fixtures, labels


def linked(tmp_path, cfg):
    root, bundle, spec, plan, receipt = prepared(tmp_path)
    study, placement, fixtures, labels = study_and_rows(root, bundle, spec, plan, cfg)
    link = freeze_link(root, bundle, study, placement,
        expected_study_digest=study['contract_digest'],
        expected_placement_digest=placement['contract_digest'],
        trusted_implementation_receipt_sha256=receipt)
    request = {'schema_version': '1.0', 'link_digest': link['contract_digest'],
               'fixture_sha256': digest(fixtures), 'labels_sha256': digest(labels),
               'max_pairs': 2, 'max_total_calls': 4, 'max_total_cost': 1.0,
               'stop_after_failures': 2, 'egress': False}
    return root, bundle, receipt, study, placement, link, fixtures, labels, request


def test_exact_link_and_complete_offline_pairs_are_synthetic(tmp_path, cfg):
    root, bundle, receipt, study, placement, link, fixtures, labels, request = linked(tmp_path, cfg)
    check_link(root, bundle, study, placement, link,
               expected_link_digest=link['contract_digest'],
               trusted_implementation_receipt_sha256=receipt)
    result = collect_offline(link, study, request, fixtures, labels,
        approved_request_sha256=digest(request), expected_link_digest=link['contract_digest'],
        root=root, bundle=bundle, placement_set=placement,
        trusted_implementation_receipt_sha256=receipt)
    assert result['status'] == 'synthetic_complete'
    assert result['scheduled_pairs'] == result['collected_pairs'] == 2
    assert result['host_adapter_calls'] == 4
    assert all(not row['success'] for row in result['baseline'])
    assert all(row['success'] for row in result['jev'])
    evaluation = evaluate_linked(link, study, result,
        expected_link_digest=link['contract_digest'],
        expected_collection_digest=result['contract_digest'],
        root=root, bundle=bundle, placement_set=placement,
        trusted_implementation_receipt_sha256=receipt)
    assert evaluation['study_evaluation']['study_validation']['observed_pairs'] == 2
    assert evaluation['study_evaluation']['recommendation'] == 'needs_more_evidence'
    assert evaluation['supported_benefit'] is False and evaluation['activation_eligible'] is False


def test_missing_outcome_unknown_budget_and_label_remain_incomplete(tmp_path, cfg):
    root, bundle, receipt, study, placement, link, fixtures, labels, request = linked(tmp_path, cfg)
    for changed_fixtures, changed_labels, budget in (
            (fixtures[:1], labels, request),
            (fixtures, labels[:1], request),
            (fixtures, labels, {**request, 'max_total_cost': None}),
            (fixtures, labels, {**request, 'max_total_calls': 2})):
        req = {**budget, 'fixture_sha256': digest(changed_fixtures),
               'labels_sha256': digest(changed_labels)}
        report = collect_offline(link, study, req, changed_fixtures, changed_labels,
            approved_request_sha256=digest(req), expected_link_digest=link['contract_digest'],
            root=root, bundle=bundle, placement_set=placement,
            trusted_implementation_receipt_sha256=receipt)
        assert report['scheduled_pairs'] == 2 and report['missing_pairs']
        assert report['status'].startswith('incomplete_')
        evaluated = evaluate_linked(link, study, report,
            expected_link_digest=link['contract_digest'],
            expected_collection_digest=report['contract_digest'],
            root=root, bundle=bundle, placement_set=placement,
            trusted_implementation_receipt_sha256=receipt)
        assert evaluated['study_evaluation'] is None and not evaluated['supported_benefit']


def test_observed_study_cannot_use_synthetic_offline_adapter(tmp_path, cfg):
    root, bundle, spec, plan, receipt = prepared(tmp_path)
    study, placement, fixtures, labels = study_and_rows(root, bundle, spec, plan, cfg)
    observed_spec = copy.deepcopy(study['specification'])
    observed_spec['evidence_type'] = 'observed'
    observed = freeze_study(observed_spec, cfg)
    link = freeze_link(root, bundle, observed, placement,
        expected_study_digest=observed['contract_digest'],
        expected_placement_digest=placement['contract_digest'],
        trusted_implementation_receipt_sha256=receipt)
    request = {'schema_version': '1.0', 'link_digest': link['contract_digest'],
               'fixture_sha256': digest(fixtures), 'labels_sha256': digest(labels),
               'max_pairs': 2, 'max_total_calls': 4, 'max_total_cost': 1.0,
               'stop_after_failures': 2, 'egress': False}
    report = collect_offline(link, observed, request, fixtures, labels,
        approved_request_sha256=digest(request), expected_link_digest=link['contract_digest'],
        root=root, bundle=bundle, placement_set=placement,
        trusted_implementation_receipt_sha256=receipt)
    assert report['status'] == 'incomplete_egress_scope'
    assert report['host_adapter_calls'] == 0 and report['collected_pairs'] == 0


def test_observed_cli_runs_exact_offline_link_collection_and_evaluation(tmp_path, cfg):
    root, bundle, receipt, study, placement, _, fixtures, labels, _ = linked(tmp_path, cfg)
    inputs = {'study': study, 'placement': placement, 'fixtures': fixtures, 'labels': labels}
    paths = {}
    for name, value in inputs.items():
        paths[name] = tmp_path / f'{name}.json'
        write_json(paths[name], value)
    link_path, request_path, collection_path, evaluation_path = (
        tmp_path / name for name in ('link.json', 'request.json', 'collection.json', 'evaluation.json'))
    base = ['--repo', str(root), '--bundle', str(bundle), '--study', str(paths['study']),
            '--placement-set', str(paths['placement']), '--receipt-sha256', receipt]
    assert cli_main(['observed-link', *base, '--study-digest', study['contract_digest'],
                     '--placement-digest', placement['contract_digest'], '--out', str(link_path)]) == 0
    link = read_json(link_path)
    request = {'schema_version': '1.0', 'link_digest': link['contract_digest'],
               'fixture_sha256': digest(fixtures), 'labels_sha256': digest(labels),
               'max_pairs': 2, 'max_total_calls': 4, 'max_total_cost': 1.0,
               'stop_after_failures': 2, 'egress': False}
    write_json(request_path, request)
    linked_args = [*base, '--link', str(link_path), '--link-digest', link['contract_digest']]
    assert cli_main(['observed-collect-offline', *linked_args,
                     '--request', str(request_path), '--fixtures', str(paths['fixtures']),
                     '--labels', str(paths['labels']), '--approve-request', digest(request),
                     '--out', str(collection_path)]) == 0
    collection = read_json(collection_path)
    assert collection['status'] == 'synthetic_complete'
    assert cli_main(['observed-evaluate', *linked_args, '--collection', str(collection_path),
                     '--collection-digest', collection['contract_digest'],
                     '--out', str(evaluation_path)]) == 0
    assert read_json(evaluation_path)['activation_eligible'] is False


def test_timeout_kept_and_unreviewed_identity_rejected(tmp_path, cfg):
    root, bundle, receipt, study, placement, link, fixtures, labels, request = linked(tmp_path, cfg)
    fixtures[0]['jev']['run_status'] = 'timeout'
    fixtures[0]['jev']['output_label'] = None
    req = {**request, 'fixture_sha256': digest(fixtures)}
    report = collect_offline(link, study, req, fixtures, labels,
        approved_request_sha256=digest(req), expected_link_digest=link['contract_digest'],
        root=root, bundle=bundle, placement_set=placement,
        trusted_implementation_receipt_sha256=receipt)
    assert report['scheduled_pairs'] == report['collected_pairs'] == 2
    assert report['jev'][0]['run_status'] == 'timeout' and report['jev'][0]['success'] is False
    with pytest.raises(InputError):
        collect_offline(link, study, req, fixtures, labels,
            approved_request_sha256='0' * 64, expected_link_digest=link['contract_digest'],
            root=root, bundle=bundle, placement_set=placement,
            trusted_implementation_receipt_sha256=receipt)
    altered = copy.deepcopy(study)
    altered['specification']['jev']['model_id'] = 'other'
    with pytest.raises(InputError):
        freeze_link(root, bundle, altered, placement,
            expected_study_digest=study['contract_digest'],
            expected_placement_digest=placement['contract_digest'],
            trusted_implementation_receipt_sha256=receipt)
    source = root / read_json(bundle / 'implementation-spec.json')['source']['file']
    source.write_text(source.read_text(encoding='utf-8') + '\n# drift\n', encoding='utf-8')
    with pytest.raises(InputError):
        check_link(root, bundle, study, placement, link,
            expected_link_digest=link['contract_digest'],
            trusted_implementation_receipt_sha256=receipt)


def test_collection_tamper_and_gate_substitution_rejected(tmp_path, cfg):
    root, bundle, receipt, study, placement, link, fixtures, labels, request = linked(tmp_path, cfg)
    report = collect_offline(link, study, request, fixtures, labels,
        approved_request_sha256=digest(request), expected_link_digest=link['contract_digest'],
        root=root, bundle=bundle, placement_set=placement,
        trusted_implementation_receipt_sha256=receipt)
    changed = copy.deepcopy(report)
    changed['jev'][0]['cost'] = 0
    with pytest.raises(InputError):
        evaluate_linked(link, study, changed, expected_link_digest=link['contract_digest'],
                        expected_collection_digest=report['contract_digest'],
                        root=root, bundle=bundle, placement_set=placement,
                        trusted_implementation_receipt_sha256=receipt)
    with pytest.raises(InputError, match='no frozen all-gate manifest'):
        evaluate_linked(link, study, report, expected_link_digest=link['contract_digest'],
                        expected_collection_digest=report['contract_digest'], gate_bundle={},
                        root=root, bundle=bundle, placement_set=placement,
                        trusted_implementation_receipt_sha256=receipt)
    with pytest.raises(InputError, match='requires frozen plan, raw rows and report'):
        evaluate_linked(link, study, report, expected_link_digest=link['contract_digest'],
                        expected_collection_digest=report['contract_digest'], holdout_report={},
                        root=root, bundle=bundle, placement_set=placement,
                        trusted_implementation_receipt_sha256=receipt)


def test_frozen_monitor_recomputes_complete_denominator_and_only_suspends(tmp_path, cfg):
    root, bundle, receipt, study, placement, _, fixtures, labels, _ = linked(tmp_path, cfg)
    fixture_plan, _, as_of = monitor_fixture()
    monitor_spec = copy.deepcopy(fixture_plan['specification'])
    monitor_spec['study_digest'] = study['contract_digest']
    monitor_spec['runtime_contracts'] = {
        read_json(bundle / 'implementation-spec.json')['candidate_id']:
        digest(read_json(bundle / 'implementation-spec.json')['runtime'])}
    monitor = freeze_monitor(monitor_spec)
    link = freeze_link(root, bundle, study, placement,
        expected_study_digest=study['contract_digest'],
        expected_placement_digest=placement['contract_digest'],
        trusted_implementation_receipt_sha256=receipt,
        monitor_plan=monitor, expected_monitor_digest=monitor['contract_digest'])
    request = {'schema_version': '1.0', 'link_digest': link['contract_digest'],
               'fixture_sha256': digest(fixtures), 'labels_sha256': digest(labels),
               'max_pairs': 2, 'max_total_calls': 4, 'max_total_cost': 1.0,
               'stop_after_failures': 2, 'egress': False}
    collection = collect_offline(link, study, request, fixtures, labels,
        approved_request_sha256=digest(request), expected_link_digest=link['contract_digest'],
        root=root, bundle=bundle, placement_set=placement,
        trusted_implementation_receipt_sha256=receipt, monitor_plan=monitor)
    from datetime import datetime, timedelta
    start = datetime.fromisoformat(monitor_spec['starts_at'])
    rows = [{**a, 'deployment_id': monitor_spec['deployment_id'],
             'study_digest': study['contract_digest'], 'window_id': monitor_spec['window_id'],
             'monitor_digest': monitor['contract_digest'], 'evidence_type': 'synthetic',
             'started_at': (start + timedelta(seconds=1)).isoformat(),
             'finished_at': (start + timedelta(seconds=2)).isoformat(),
             'run_status': 'completed', 'success': True, 'latency_ms': 10.0,
             'cost': .001, 'unsafe_actions': 0, 'fallbacks': 0, 'decisions': 1,
             'action_counts': {'inspect': 1}} for a in monitor['assignments']]
    def evaluate(outcomes):
        return evaluate_linked(link, study, collection,
            expected_link_digest=link['contract_digest'],
            expected_collection_digest=collection['contract_digest'],
            root=root, bundle=bundle, placement_set=placement,
            trusted_implementation_receipt_sha256=receipt,
            monitor_plan=monitor, monitor_rows=outcomes, monitor_as_of=as_of)
    healthy = evaluate(rows)
    assert healthy['monitor_status'] == 'within_declared_limits'
    assert len(healthy['monitor_report_digest']) == 64
    assert healthy['exposure_action'] == 'none' and not healthy['activation_eligible']
    as_of = (datetime.fromisoformat(as_of) + timedelta(minutes=2)).isoformat()
    missing = evaluate(rows[:-1])
    assert missing['monitor_status'] == 'incomplete_overdue_window'
    assert missing['monitor_report_digest'] != healthy['monitor_report_digest']
    assert missing['exposure_action'] == 'suspend'
    breached = copy.deepcopy(rows)
    breached[0]['unsafe_actions'] = 1
    assert evaluate(breached)['exposure_action'] == 'suspend'


def test_host_owned_pair_adapter_is_invoked_only_under_exact_bounded_scope(tmp_path, cfg):
    root, bundle, receipt, study, placement, link, fixtures, labels, _ = linked(tmp_path, cfg)
    inputs = [{'task_id': r['task_id'], 'replicate': r['replicate'],
               'task_hash': r['task_hash'], 'input_sha256': digest(r['task_id'])}
              for r in study['specification']['schedule'] if r['split'] == 'test']
    class SyntheticHost:
        adapter_id = 'owned-synthetic-pair-host'
        contract_digest = digest('reviewed-synthetic-adapter-code')
        host_scope_digest = digest('finite-host-fixture-scope')
        def __init__(self):
            self.calls = []
            self.fail = False
            self.mode = None
        def run_pair(self, **scope):
            self.calls.append(scope)
            if self.fail:
                raise RuntimeError('host attempt unresolved')
            fixture = next(row for row in fixtures if
                           (row['task_id'], row['replicate']) ==
                           (scope['task_id'], scope['replicate']))
            if self.mode == 'malformed':
                return {'baseline': fixture['baseline']}
            if self.mode == 'over_cost':
                fixture = copy.deepcopy(fixture)
                fixture['jev']['metrics']['cost'] = .2
            if self.mode == 'drift':
                source = root / read_json(bundle / 'implementation-spec.json')['source']['file']
                source.write_text(source.read_text(encoding='utf-8') + '\n# host drift\n',
                                  encoding='utf-8')
            return {'baseline': fixture['baseline'], 'jev': fixture['jev'],
                    'receipt_sha256': digest(scope)}
    host = SyntheticHost()
    request = {'schema_version': '1.0', 'link_digest': link['contract_digest'],
               'study_digest': study['contract_digest'],
               'input_manifest_sha256': digest(inputs), 'labels_sha256': digest(labels),
               'adapter_id': host.adapter_id, 'contract_digest': host.contract_digest,
               'host_scope_digest': host.host_scope_digest, 'egress_grant_sha256': None,
               'evidence_type': 'synthetic', 'max_pairs': 2, 'max_pair_calls': 2,
               'max_pair_cost': .1, 'max_total_cost': .2, 'stop_after_failures': 1}
    def collect(req=request, supplied_labels=labels, supplied_inputs=inputs, approved=None):
        return collect_host_pairs(link, study, req, supplied_inputs, supplied_labels, host,
            approved_request_sha256=approved or digest(req),
            expected_link_digest=link['contract_digest'], root=root, bundle=bundle,
            placement_set=placement, trusted_implementation_receipt_sha256=receipt)
    with pytest.raises(InputError):
        collect({**request, 'contract_digest': digest('wrong-adapter')})
    assert host.calls == []
    with pytest.raises(InputError):
        collect({**request, 'input_manifest_sha256': digest(inputs + inputs[:1])},
                supplied_inputs=inputs + inputs[:1])
    with pytest.raises(InputError):
        collect({**request, 'labels_sha256': digest(labels + labels[:1])},
                supplied_labels=labels + labels[:1])
    assert host.calls == []
    insufficient = collect({**request, 'max_total_cost': .1})
    assert insufficient['status'] == 'incomplete_bound_insufficient'
    unknown = collect({**request, 'max_total_cost': None})
    assert unknown['status'] == 'incomplete_unknown_budget'
    assert insufficient['host_pair_calls'] == unknown['host_pair_calls'] == 0
    assert host.calls == []
    report = collect()
    assert report['status'] == 'synthetic_complete'
    assert report['host_pair_calls'] == report['collected_pairs'] == 2
    assert len(report['receipt_hashes']) == 2
    assert all(call['egress_grant_sha256'] is None and
               call['link_digest'] == link['contract_digest'] for call in host.calls)
    assert report['benefit_supported'] is False and report['activation_eligible'] is False
    host.calls.clear()
    missing = collect(supplied_labels=labels[:1],
        req={**request, 'labels_sha256': digest(labels[:1])})
    assert missing['status'] == 'incomplete_scheduled_outcomes'
    assert missing['scheduled_pairs'] == 2 and len(missing['missing_pairs']) == 1
    host.calls.clear()
    host.fail = True
    interrupted = collect()
    assert interrupted['status'] == 'incomplete_unresolved_host_attempt'
    assert interrupted['host_pair_calls'] == 1 and interrupted['recorded_cost'] is None
    assert len(interrupted['missing_pairs']) == 2
    host.fail = False
    for mode in ('malformed', 'over_cost'):
        host.calls.clear()
        host.mode = mode
        invalid = collect()
        assert invalid['status'] == 'incomplete_unresolved_host_attempt'
        assert invalid['host_pair_calls'] == len(host.calls) == 1
        assert invalid['recorded_cost'] is None and len(invalid['missing_pairs']) == 2
    host.calls.clear()
    host.mode = 'drift'
    with pytest.raises(InputError):
        collect()
    assert len(host.calls) == 1


def test_host_observed_scope_requires_independent_exact_egress_grant(tmp_path, cfg):
    root, bundle, spec, plan, receipt = prepared(tmp_path)
    study, placement, _, labels = study_and_rows(root, bundle, spec, plan, cfg)
    observed_spec = copy.deepcopy(study['specification'])
    observed_spec['evidence_type'] = 'observed'
    observed = freeze_study(observed_spec, cfg)
    link = freeze_link(root, bundle, observed, placement,
        expected_study_digest=observed['contract_digest'],
        expected_placement_digest=placement['contract_digest'],
        trusted_implementation_receipt_sha256=receipt)
    inputs = [{'task_id': r['task_id'], 'replicate': r['replicate'],
               'task_hash': r['task_hash'], 'input_sha256': digest(r['task_id'])}
              for r in observed['specification']['schedule'] if r['split'] == 'test']
    class NoCallHost:
        adapter_id = 'never-call'
        contract_digest = digest('adapter')
        host_scope_digest = digest('scope')
        def run_pair(self, **scope):
            raise AssertionError('observed host must not be called without grant')
    host = NoCallHost()
    request = {'schema_version': '1.0', 'link_digest': link['contract_digest'],
               'study_digest': observed['contract_digest'],
               'input_manifest_sha256': digest(inputs), 'labels_sha256': digest(labels),
               'adapter_id': host.adapter_id, 'contract_digest': host.contract_digest,
               'host_scope_digest': host.host_scope_digest, 'egress_grant_sha256': digest('grant'),
               'evidence_type': 'observed', 'max_pairs': 2, 'max_pair_calls': 2,
               'max_pair_cost': .1, 'max_total_cost': .2, 'stop_after_failures': 1}
    incomplete = collect_host_pairs(link, observed, request, inputs, labels, host,
        approved_request_sha256=digest(request), expected_link_digest=link['contract_digest'],
        root=root, bundle=bundle, placement_set=placement,
        trusted_implementation_receipt_sha256=receipt)
    assert incomplete['status'] == 'incomplete_egress_scope'
    assert incomplete['host_pair_calls'] == 0 and incomplete['scheduled_pairs'] == 2
    with pytest.raises(InputError, match='differs from approved scope'):
        collect_host_pairs(link, observed, request, inputs, labels, host,
            approved_request_sha256=digest(request), expected_link_digest=link['contract_digest'],
            root=root, bundle=bundle, placement_set=placement,
            trusted_implementation_receipt_sha256=receipt,
            trusted_egress_grant_sha256=digest('wrong-grant'))
