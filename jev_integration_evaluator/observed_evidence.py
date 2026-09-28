"""Source-bound study linkage and explicitly approved offline paired collection.

This module never imports a target, opens a provider connection, or activates a
router. Synthetic fixture outcomes are useful for checking orchestration only.
"""
from __future__ import annotations

import copy
import math
import platform
import sys
from pathlib import Path

from .contracts import seal, validate_contract, verify
from .io import InputError, digest, file_hash
from .study import evaluate_study
from .statistics import METRICS
from .integrations.lifecycle import _load, implementation_status


def _environment() -> dict:
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'executable_sha256': file_hash(Path(sys.executable).resolve())}


def _source_revision(plan: dict, phase: str) -> str:
    field = 'old_sha256' if phase == 'baseline' else 'new_sha256'
    mode = 'old_mode' if phase == 'baseline' else 'new_mode'
    return digest([(row['file'], row[field], row[mode]) for row in plan['owned_files']])


def _rubric(spec: dict) -> str:
    return digest({'questions': spec['questions'], 'primary_question': spec['primary_question'],
                   'evidence_question': spec['evidence_question'],
                   'label_actions': spec['label_actions']})


def expected_study_arm(root, bundle) -> dict:
    """Exact JEV arm fields a frozen study must use for this owned bundle."""
    _, _, plan, spec, _, _ = _load(root, bundle)
    return {'code_revision': _source_revision(plan, 'jev'),
            'model_id': spec['runtime']['configuration']['model'],
            'policy_version': spec['runtime']['policy_version'],
            'prompt_hash': _rubric(spec)}


def freeze_link(root, bundle, study: dict, placement_set: dict, *,
                expected_study_digest: str, expected_placement_digest: str,
                trusted_implementation_receipt_sha256: str,
                monitor_plan: dict | None = None, expected_monitor_digest: str | None = None) -> dict:
    """Freeze exact applied bytes, reviewed placement and study arm identities."""
    validate_contract(study, 'study')
    verify(study, expected=expected_study_digest)
    validate_contract(placement_set, 'observed-placement-set')
    verify(placement_set, expected=expected_placement_digest)
    root, bundle, plan, spec, _, _ = _load(root, bundle, current_engine=True)
    current = implementation_status(root, bundle,
        trusted_receipt_sha256=trusted_implementation_receipt_sha256)
    if current['status'] != 'verified' or current['receipt_trust'] != 'externally_anchored_execution':
        raise InputError('Externally anchored applied implementation verification required')
    if (placement_set['selected_candidate_ids'] != [spec['candidate_id']]
            or placement_set['reviewed_inventory_sha256'] != spec['inventory_sha256']):
        raise InputError('Placement set differs from reviewed implementation')
    study_spec = study['specification']
    if (study_spec['experiment_id'] != spec['experiment_id']
            or study_spec['jev']['code_revision'] != _source_revision(plan, 'jev')
            or study_spec['baseline']['code_revision'] != _source_revision(plan, 'baseline')
            or any(study_spec['jev'][k] != v for k, v in expected_study_arm(root, bundle).items())
            or study_spec['evidence_type'] not in ('synthetic', 'observed')):
        raise InputError('Frozen study arm differs from exact implementation or rubric')
    if (monitor_plan is None) != (expected_monitor_digest is None):
        raise InputError('Monitor plan and independently retained digest must be supplied together')
    if monitor_plan is not None:
        validate_contract(monitor_plan, 'monitor')
        verify(monitor_plan, expected=expected_monitor_digest)
        monitor = monitor_plan['specification']
        if (monitor['study_digest'] != study['contract_digest']
                or monitor['evidence_type'] != study_spec['evidence_type']
                or monitor['runtime_contracts'].get(spec['candidate_id']) != digest(spec['runtime'])):
            raise InputError('Frozen monitor differs from study or reviewed runtime contract')
    owned = [{'file': row['file'], 'sha256': row['new_sha256'], 'mode': row['new_mode']}
             for row in plan['owned_files']]
    result = seal({'schema_version': '1.0', 'kind': 'implementation_study_link',
        'study_digest': study['contract_digest'], 'placement_set_digest': placement_set['contract_digest'],
        'bundle_digest': plan['contract_digest'], 'spec_digest': plan['spec_digest'],
        'verified_receipt_sha256': trusted_implementation_receipt_sha256,
        'candidate_id': spec['candidate_id'], 'owned_files': owned,
        'runtime_configuration_digest': digest(spec['runtime']), 'rubric_digest': _rubric(spec),
        'model_id': study_spec['jev']['model_id'], 'policy_version': study_spec['jev']['policy_version'],
        'jev_source_revision': study_spec['jev']['code_revision'],
        'baseline_source_revision': study_spec['baseline']['code_revision'],
        'gate_manifest_digest': digest(study_spec['deployment_gates']) if study_spec.get('deployment_gates') else None,
        'monitor_digest': expected_monitor_digest,
        'environment': _environment(), 'wiring_status': 'verified_synthetic',
        'provider_connectivity': 'not_tested', 'observed_outcomes': 'not_collected',
        'benefit_supported': False, 'activation_eligible': False})
    validate_contract(result, 'observed-link')
    return result


def check_link(root, bundle, study: dict, placement_set: dict, link: dict, *,
               expected_link_digest: str, trusted_implementation_receipt_sha256: str,
               monitor_plan: dict | None = None) -> None:
    """Reconstruct all current identity fields; drift needs a new frozen link."""
    validate_contract(link, 'observed-link')
    verify(link, expected=expected_link_digest)
    fresh = freeze_link(root, bundle, study, placement_set,
        expected_study_digest=link['study_digest'],
        expected_placement_digest=link['placement_set_digest'],
        trusted_implementation_receipt_sha256=trusted_implementation_receipt_sha256,
        monitor_plan=monitor_plan, expected_monitor_digest=link['monitor_digest'])
    if fresh != link:
        raise InputError('Implementation, study, placement or environment drift requires requalification')


def _budget(request: dict, scheduled: int) -> str:
    validate_contract(request, 'observed-collection-request')
    if (type(request) is not dict or set(request) !=
            {'schema_version', 'link_digest', 'fixture_sha256', 'labels_sha256',
             'max_pairs', 'max_total_calls', 'max_total_cost', 'stop_after_failures', 'egress'}
            or request['schema_version'] != '1.0' or request['egress'] is not False):
        raise InputError('Invalid offline collection request')
    values = [request[k] for k in ('max_pairs', 'max_total_calls', 'stop_after_failures')]
    if any(v is not None and (type(v) is not int or v < 1) for v in values):
        raise InputError('Invalid offline collection bound')
    cost = request['max_total_cost']
    if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
        raise InputError('Invalid offline collection cost bound')
    if any(v is None for v in values) or cost is None:
        return 'unknown'
    if request['max_pairs'] < scheduled or request['max_total_calls'] < scheduled * 2:
        return 'insufficient'
    return 'ready'


def _outcome_row(study: dict, schedule: dict, arm: str, outcome: dict, label: dict) -> dict:
    if (type(outcome) is not dict or set(outcome) != {'run_status', 'output_label', 'metrics'}
            or outcome['run_status'] not in ('completed', 'failed', 'timeout', 'cancelled')
            or type(outcome['metrics']) is not dict
            or (outcome['output_label'] is not None and type(outcome['output_label']) is not str)):
        raise InputError('Invalid bounded offline host outcome')
    required = set(study['specification']['required_metrics']) | {'cost', 'latency_ms'}
    if not required <= set(outcome['metrics']) or not set(outcome['metrics']) <= set(METRICS):
        raise InputError('Offline outcome lacks a required measured metric')
    for value in outcome['metrics'].values():
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise InputError('Invalid measured offline metric')
    spec = study['specification']
    return {**copy.deepcopy(spec[arm]), 'task_id': schedule['task_id'],
            'replicate': schedule['replicate'], 'task_hash': schedule['task_hash'],
            'cluster_id': schedule['cluster_id'], 'seed': schedule.get('seed'),
            'dataset_id': spec['dataset_id'], 'experiment_id': spec['experiment_id'],
            'study_digest': study['contract_digest'], 'split': 'test',
            'evaluation_scope': 'task_success', 'evidence_type': 'synthetic',
            'run_status': outcome['run_status'],
            'success': outcome['run_status'] == 'completed' and outcome['output_label'] == label['expected_label'],
            **outcome['metrics'],
            **({'gate_manifest_digest': digest(spec['deployment_gates'])}
               if spec.get('deployment_gates') else {})}


class OfflineFixtureHost:
    """Finite fixture adapter; returns only scheduled bounded outcomes."""

    def __init__(self, rows: dict):
        self._rows = rows
        self.calls = 0

    def run(self, key: tuple[str, int], arm: str) -> dict:
        if key not in self._rows or arm not in ('baseline', 'jev'):
            raise InputError('Unscheduled offline host adapter call')
        self.calls += 1
        return copy.deepcopy(self._rows[key][arm])


def collect_offline(link: dict, study: dict, request: dict, fixtures: list[dict], labels: list[dict], *,
                    approved_request_sha256: str, expected_link_digest: str,
                    root, bundle, placement_set: dict,
                    trusted_implementation_receipt_sha256: str,
                    monitor_plan: dict | None = None) -> dict:
    """Run finite fixture adapters only; independent labels decide task success."""
    validate_contract(link, 'observed-link')
    verify(link, expected=expected_link_digest)
    check_link(root, bundle, study, placement_set, link,
        expected_link_digest=expected_link_digest,
        trusted_implementation_receipt_sha256=trusted_implementation_receipt_sha256,
        monitor_plan=monitor_plan)
    validate_contract(study, 'study')
    verify(study, expected=link['study_digest'])
    if (type(request) is not dict or type(fixtures) is not list or type(labels) is not list or len(fixtures) > 100000
            or len(labels) > 100000 or request.get('link_digest') != link['contract_digest']
            or request.get('fixture_sha256') != digest(fixtures)
            or request.get('labels_sha256') != digest(labels)
            or digest(request) != approved_request_sha256):
        raise InputError('Exact externally approved offline collection request required')
    schedule = {(r['task_id'], r['replicate']): r for r in study['specification']['schedule'] if r['split'] == 'test'}
    budget_status = _budget(request, len(schedule))
    if study['specification']['evidence_type'] != 'synthetic':
        result = seal({'schema_version': '1.0', 'kind': 'offline_paired_collection',
            'link_digest': link['contract_digest'], 'study_digest': study['contract_digest'],
            'request_sha256': approved_request_sha256, 'fixture_sha256': digest(fixtures),
            'labels_sha256': digest(labels), 'status': 'incomplete_egress_scope',
            'evidence_type': 'synthetic', 'scheduled_pairs': len(schedule), 'collected_pairs': 0,
            'missing_pairs': [{'task_id': key[0], 'replicate': key[1]} for key in sorted(schedule)],
            'baseline': [], 'jev': [], 'host_adapter_calls': 0, 'recorded_cost': 0,
            'independent_label_count': 0, 'provider_connectivity': 'not_tested',
            'benefit_supported': False, 'activation_eligible': False})
        validate_contract(result, 'observed-collection')
        check_link(root, bundle, study, placement_set, link,
            expected_link_digest=expected_link_digest,
            trusted_implementation_receipt_sha256=trusted_implementation_receipt_sha256,
            monitor_plan=monitor_plan)
        return result
    fixture_index = {}
    for row in fixtures:
        if type(row) is not dict or set(row) != {'task_id', 'replicate', 'task_hash', 'baseline', 'jev'}:
            raise InputError('Invalid offline fixture row')
        key = (row['task_id'], row['replicate'])
        if key in fixture_index or key not in schedule or row['task_hash'] != schedule[key]['task_hash']:
            raise InputError('Offline fixture differs from frozen schedule')
        fixture_index[key] = row
    label_index = {}
    for row in labels:
        if (type(row) is not dict or set(row) !=
                {'task_id', 'replicate', 'task_hash', 'expected_label', 'reviewer', 'source_sha256'}
                or type(row['expected_label']) is not str or not row['expected_label']
                or type(row['reviewer']) is not str or not row['reviewer']
                or type(row['source_sha256']) is not str or len(row['source_sha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['source_sha256'])):
            raise InputError('Independent label record required')
        key = (row['task_id'], row['replicate'])
        if key in label_index or key not in schedule or row['task_hash'] != schedule[key]['task_hash']:
            raise InputError('Independent label differs from frozen schedule')
        label_index[key] = row
    baseline, jev, missing = [], [], []
    host = OfflineFixtureHost(fixture_index)
    failures = 0
    cost = 0.0
    for key in sorted(schedule):
        fixture, label = fixture_index.get(key), label_index.get(key)
        if (budget_status != 'ready' or fixture is None or label is None or
                failures >= request['stop_after_failures'] or host.calls + 2 > request['max_total_calls']):
            missing.append({'task_id': key[0], 'replicate': key[1]})
            continue
        try:
            declared_cost = fixture['baseline']['metrics']['cost'] + fixture['jev']['metrics']['cost']
            if (type(fixture['baseline']['metrics']['cost']) not in (int, float)
                    or type(fixture['jev']['metrics']['cost']) not in (int, float)
                    or not math.isfinite(declared_cost) or declared_cost < 0):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise InputError('Offline fixture lacks a finite measured cost') from None
        if cost + declared_cost > request['max_total_cost']:
            missing.append({'task_id': key[0], 'replicate': key[1]})
            continue
        b = _outcome_row(study, schedule[key], 'baseline', host.run(key, 'baseline'), label)
        j = _outcome_row(study, schedule[key], 'jev', host.run(key, 'jev'), label)
        pair_cost = b.get('cost', 0) + j.get('cost', 0)
        if pair_cost != declared_cost:
            raise InputError('Offline fixture cost changed during collection')
        cost += pair_cost
        failures += int(b['run_status'] != 'completed' or j['run_status'] != 'completed')
        baseline.append(b)
        jev.append(j)
    status = 'synthetic_complete' if not missing else (
        'incomplete_unknown_budget' if budget_status == 'unknown' else
        'incomplete_bound_insufficient' if budget_status == 'insufficient' else
        'incomplete_scheduled_outcomes')
    report = seal({'schema_version': '1.0', 'kind': 'offline_paired_collection',
        'link_digest': link['contract_digest'], 'study_digest': study['contract_digest'],
        'request_sha256': approved_request_sha256, 'fixture_sha256': digest(fixtures),
        'labels_sha256': digest(labels), 'status': status, 'evidence_type': 'synthetic',
        'scheduled_pairs': len(schedule), 'collected_pairs': len(baseline),
        'missing_pairs': missing, 'baseline': baseline, 'jev': jev,
        'host_adapter_calls': host.calls, 'recorded_cost': cost,
        'independent_label_count': len(label_index), 'provider_connectivity': 'not_tested',
        'benefit_supported': False, 'activation_eligible': False})
    validate_contract(report, 'observed-collection')
    check_link(root, bundle, study, placement_set, link,
        expected_link_digest=expected_link_digest,
        trusted_implementation_receipt_sha256=trusted_implementation_receipt_sha256,
        monitor_plan=monitor_plan)
    return report


def _check_collection(collection: dict, study: dict) -> None:
    validate_contract(collection, 'observed-collection')
    verify(collection)
    for row in collection['baseline'] + collection['jev']:
        validate_contract(row, 'run')
    schedule = {(r['task_id'], r['replicate']) for r in study['specification']['schedule']
                if r['split'] == 'test'}
    missing = [(r['task_id'], r['replicate']) for r in collection['missing_pairs']]
    baseline = [(r.get('task_id'), r.get('replicate')) for r in collection['baseline']]
    jev = [(r.get('task_id'), r.get('replicate')) for r in collection['jev']]
    if (collection['scheduled_pairs'] != len(schedule)
            or collection['collected_pairs'] != len(baseline) or baseline != jev
            or len(set(baseline)) != len(baseline) or len(set(missing)) != len(missing)
            or set(baseline) & set(missing) or set(baseline) | set(missing) != schedule
            or collection['host_adapter_calls'] != 2 * len(baseline)
            or (collection['status'] == 'synthetic_complete') != (not missing)):
        raise InputError('Offline collection denominator or pair identity mismatch')


def evaluate_linked(link: dict, study: dict, collection: dict, *,
                    expected_link_digest: str, expected_collection_digest: str,
                    root, bundle, placement_set: dict,
                    trusted_implementation_receipt_sha256: str,
                    gate_bundle: dict | None = None, holdout_report: dict | None = None,
                    holdout_plan: dict | None = None, holdout_rows: list[dict] | None = None,
                    monitor_plan: dict | None = None, monitor_rows: list[dict] | None = None,
                    monitor_as_of: str | None = None) -> dict:
    """Recompute existing study and raw gate checks; never promote synthetic benefit."""
    validate_contract(link, 'observed-link')
    verify(link, expected=expected_link_digest)
    check_link(root, bundle, study, placement_set, link,
        expected_link_digest=expected_link_digest,
        trusted_implementation_receipt_sha256=trusted_implementation_receipt_sha256,
        monitor_plan=monitor_plan)
    _check_collection(collection, study)
    verify(collection, expected=expected_collection_digest)
    validate_contract(study, 'study')
    verify(study, expected=link['study_digest'])
    if collection['link_digest'] != link['contract_digest'] or collection['study_digest'] != study['contract_digest']:
        raise InputError('Collection differs from frozen implementation study')
    if any(x is not None for x in (holdout_report, holdout_plan, holdout_rows)):
        if any(x is None for x in (holdout_report, holdout_plan, holdout_rows)):
            raise InputError('Legacy holdout evidence requires frozen plan, raw rows and report together')
        from .holdout import validate_holdout
        recomputed = validate_holdout(holdout_plan, holdout_rows,
                                     expected_digest=holdout_plan['contract_digest'])
        if recomputed != holdout_report:
            raise InputError('Legacy holdout summary differs from raw recomputation')
    if monitor_rows is not None and monitor_plan is None:
        raise InputError('Unfrozen monitor evidence is unsupported')
    monitor_status, monitor_recommendation, exposure_action = 'not_run', 'none', 'none'
    if monitor_rows is not None:
        from .monitoring import evaluate_monitor
        monitor_report = evaluate_monitor(monitor_plan, monitor_rows,
            expected_digest=link['monitor_digest'], as_of=monitor_as_of)
        monitor_status = monitor_report['status']
        monitor_recommendation = monitor_report['recommendation']
        if monitor_recommendation == 'suspend':
            exposure_action = 'suspend'
    if collection['status'] != 'synthetic_complete':
        if gate_bundle is not None or holdout_report is not None:
            raise InputError('Incomplete collection cannot evaluate gate evidence')
        result = seal({'schema_version': '1.0', 'link_digest': link['contract_digest'],
            'collection_digest': collection['contract_digest'], 'code_wiring': link['wiring_status'],
            'provider_connectivity': collection['provider_connectivity'],
            'task_outcomes': collection['status'], 'supported_benefit': False,
            'activation_eligible': False, 'study_evaluation': None,
            'monitor_status': monitor_status, 'monitor_recommendation': monitor_recommendation,
            'exposure_action': exposure_action})
        validate_contract(result, 'observed-evaluation')
        return result
    report = evaluate_study(study, collection['baseline'], collection['jev'],
        expected_digest=link['study_digest'], holdout_report=holdout_report,
        gate_bundle=gate_bundle)
    result = seal({'schema_version': '1.0', 'link_digest': link['contract_digest'],
        'collection_digest': collection['contract_digest'], 'code_wiring': link['wiring_status'],
        'provider_connectivity': collection['provider_connectivity'],
        'task_outcomes': 'synthetic_complete', 'supported_benefit': False,
        'activation_eligible': False, 'study_evaluation': report,
        'monitor_status': monitor_status, 'monitor_recommendation': monitor_recommendation,
        'exposure_action': exposure_action})
    validate_contract(result, 'observed-evaluation')
    return result
