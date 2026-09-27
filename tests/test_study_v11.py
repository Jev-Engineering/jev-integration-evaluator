import copy
import pytest
from jev_integration_evaluator.study import freeze_study, validate_study, evaluate_study
from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.contracts import seal


@pytest.fixture
def study(runs, cfg):
    baseline, jev = copy.deepcopy(runs)
    keys = ('treatment', 'code_revision', 'model_id', 'policy_version', 'prompt_hash', 'mode')
    schedule = [{'task_id': b['task_id'], 'replicate': b['replicate'], 'task_hash': b['task_hash'],
                 'cluster_id': b['task_id'], 'seed': b['seed'], 'split': 'test'} for b in baseline]
    schedule += [{'task_id': 'dev-only', 'replicate': 0, 'task_hash': digest('dev-only'), 'cluster_id': 'dev-only', 'split': 'development'}]
    spec = {'experiment_id': 'EXAMPLE', 'dataset_id': baseline[0]['dataset_id'], 'evidence_type': 'synthetic',
            'primary_metric': 'success', 'schedule': schedule,
            'baseline': {k: baseline[0][k] for k in keys}, 'jev': {k: jev[0][k] for k in keys},
            'required_metrics': ['cost', 'latency_ms', 'unsafe_actions', 'false_blocks']}
    plan = freeze_study(spec, cfg)
    for rows in (baseline, jev):
        for r in rows:
            r.update(experiment_id='EXAMPLE', study_digest=plan['contract_digest'], split='test',
                     cluster_id=r['task_id'], run_status='completed')
    return plan, baseline, jev


def test_full_scheduled_denominator_passes(study):
    plan, baseline, jev = study
    report = validate_study(plan, baseline, jev, expected_digest=plan['contract_digest'])
    assert report['scheduled_test_pairs'] == 80
    assert report['missing_from_both_arms'] == 0
    assert report['externally_pinned_digest']


def test_tasks_dropped_from_both_arms_are_detected(study):
    plan, baseline, jev = study
    with pytest.raises(InputError, match='frozen test schedule'):
        validate_study(plan, baseline[:-1], jev[:-1])


@pytest.mark.parametrize('field,value', [('model_id', 'wrong'), ('policy_version', 'wrong'),
    ('prompt_hash', 'wrong'), ('code_revision', 'wrong'), ('treatment', 'wrong'),
    ('mode', 'active'), ('experiment_id', 'wrong'), ('study_digest', 'wrong'),
    ('split', 'calibration'), ('evaluation_scope', 'decision_accuracy'), ('cluster_id', 'wrong')])
def test_frozen_provenance_mismatch_rejected(study, field, value):
    plan, baseline, jev = study
    for row in jev:
        row[field] = value
    with pytest.raises(InputError):
        validate_study(plan, baseline, jev)


@pytest.mark.parametrize('field', ['task_id', 'task_hash', 'cluster_id'])
def test_split_leakage_blocked_before_collection(study, cfg, field):
    plan, baseline, jev = study
    spec = copy.deepcopy(plan['specification'])
    spec['schedule'][-1][field] = spec['schedule'][0][field]
    with pytest.raises(InputError):
        freeze_study(spec, cfg)


def test_missing_metrics_and_false_timeout_success_rejected(study):
    plan, baseline, jev = study
    del jev[0]['cost']
    with pytest.raises(InputError):
        validate_study(plan, baseline, jev)
    jev[0]['cost'] = .01
    jev[0]['run_status'] = 'timeout'
    jev[0]['success'] = True
    with pytest.raises(InputError):
        validate_study(plan, baseline, jev)
    jev[0]['success'] = False
    assert validate_study(plan, baseline, jev)['jev_status_counts']['timeout'] == 1


def test_digest_modification_and_external_pin_rejected(study):
    plan, baseline, jev = study
    with pytest.raises(InputError):
        validate_study(plan, baseline, jev, expected_digest='0' * 64)
    plan['analysis_config']['validation']['minimum_useful_effect'] = .99
    with pytest.raises(InputError):
        validate_study(plan, baseline, jev)


def test_synthetic_study_never_adopts(study):
    plan, baseline, jev = study
    result = evaluate_study(plan, baseline, jev)
    assert result['recommendation'] == 'needs_more_evidence'
    assert not result['deployment_authorized']
    assert result['study_validation']['observed_pairs'] == 80


def test_frozen_analysis_not_replaced_by_later_config(study, cfg):
    plan, baseline, jev = study
    seed = plan['analysis_config']['validation']['seed']
    cfg['validation']['seed'] = seed + 1
    result = evaluate_study(plan, baseline, jev)
    assert result['provenance']['seed'] == seed


def test_non_task_scope_never_keeps(runs, cfg):
    from jev_integration_evaluator.statistics import compare_runs
    baseline, treatment = runs
    for r in baseline + treatment:
        r['evaluation_scope'] = 'decision_accuracy'
        r['evidence_type'] = 'observed'
        r['calibration_validated'] = True
    result = compare_runs(baseline, treatment, cfg)
    assert result['recommendation'] == 'needs_more_evidence'


def test_study_binds_specific_holdout_report_and_rubric(study, cfg):
    from test_holdout_v11 import inputs
    from jev_integration_evaluator.holdout import freeze_threshold, validate_holdout
    plan, baseline, jev = study
    cal, test, threshold_spec = inputs(evidence='observed')  # Synthetic unit-test data exercising observed-only code.
    for r in cal + test:
        r['model_id'] = plan['specification']['jev']['model_id']
        r['policy_version'] = plan['specification']['jev']['policy_version']
    report = validate_holdout(freeze_threshold(cal, threshold_spec), test)
    spec = copy.deepcopy(plan['specification'])
    spec['holdout_report_digest'] = report['contract_digest']
    spec['holdout_binding'] = {k: report['binding'][k] for k in ('model_id', 'policy_version', 'rubric_hash')}
    spec['holdout_binding']['policy_digest'] = report['policy_digest']
    plan = freeze_study(spec, cfg)
    for row in baseline + jev: row['study_digest'] = plan['contract_digest']
    result = evaluate_study(plan, baseline, jev, holdout_report=report)
    assert result['holdout_evidence_verified'] is True
    assert result['recommendation'] == 'needs_more_evidence'  # Task outcomes remain explicitly synthetic.
    spec['holdout_binding']['rubric_hash'] = digest('different-rubric')
    plan = freeze_study(spec, cfg)
    for row in baseline + jev: row['study_digest'] = plan['contract_digest']
    assert evaluate_study(plan, baseline, jev, holdout_report=report)['holdout_evidence_verified'] is False


def test_holdout_digest_alone_cannot_bind_study(study, cfg):
    plan, baseline, jev = study
    spec = copy.deepcopy(plan['specification']); spec['holdout_report_digest'] = '0' * 64
    with pytest.raises(InputError): freeze_study(spec, cfg)
