import copy
import math
import pytest
from jev_integration_evaluator.holdout import freeze_threshold, validate_holdout, binomial_error_upper
from jev_integration_evaluator.io import InputError, digest


def row(i, split='calibration', evidence='synthetic', subgroup='ordinary'):
    uid = split + '-' + str(i)
    return {'observation_id': uid, 'task_hash': digest(uid), 'cluster_id': uid,
            'subgroup': subgroup, 'kind': 'choice', 'split': split,
            'model_id': 'jev-1.13.0', 'policy_version': 'v1', 'rubric_hash': digest('rubric'),
            'evidence_type': evidence, 'probabilities': {'inspect': .99, 'stop': .01},
            'choice': 'inspect', 'confidence': .95, 'label': 'inspect'}


def inputs(evidence='synthetic', n=120):
    calibration = [row(i, evidence=evidence) for i in range(40)]
    test = [row(i, 'test', evidence=evidence) for i in range(n)]
    spec = {'probability_floor': .9, 'confidence_floor': .75, 'action_probability_floors': {},
            'abstention_labels': [], 'maximum_error': .05, 'alpha': .05, 'minimum_accepted': 30,
            'required_subgroups': [],
            'holdout_schedule': [{k: r[k] for k in ('observation_id', 'task_hash', 'cluster_id', 'subgroup')} for r in test]}
    return calibration, test, spec


def test_exact_zero_error_upper_bound():
    assert binomial_error_upper(0, 0) is None
    assert binomial_error_upper(10, 10) == 1
    assert binomial_error_upper(0, 100) == pytest.approx(1 - .05 ** .01)
    assert binomial_error_upper(0, 1) == pytest.approx(.95)
    assert binomial_error_upper(1, 2) == pytest.approx(math.sqrt(.95))


@pytest.mark.parametrize('k,n,a', [(-1, 10, .05), (11, 10, .05), (True, 10, .05), (0, -1, .05), (0, 10, 0), (0, 10, float('nan'))])
def test_invalid_binomial_inputs(k, n, a):
    with pytest.raises(InputError):
        binomial_error_upper(k, n, a)


def test_exact_bound_monotonicity():
    assert binomial_error_upper(1, 100) > binomial_error_upper(0, 100)
    assert binomial_error_upper(0, 100) < binomial_error_upper(0, 30)
    assert binomial_error_upper(1, 100, .01) > binomial_error_upper(1, 100, .05)


def test_synthetic_heldout_success_cannot_activate():
    calibration, test, spec = inputs()
    plan = freeze_threshold(calibration, spec)
    result = validate_holdout(plan, test, expected_digest=plan['contract_digest'])
    assert result['numerical_checks_pass']
    assert result['status'] == 'synthetic_only'
    assert not result['eligible_for_activation']
    assert not result['deployment_authorized']


def test_observed_contract_path_requires_all_checks():
    # Artificial unit-test observations marked observed only to exercise the branch.
    calibration, test, spec = inputs('observed')
    plan = freeze_threshold(calibration, spec)
    result = validate_holdout(plan, test)
    assert result['eligible_for_activation']
    assert not result['deployment_authorized']


@pytest.mark.parametrize('field', ['observation_id', 'task_hash', 'cluster_id'])
def test_selection_holdout_overlap_blocked(field):
    calibration, test, spec = inputs()
    spec['holdout_schedule'][0][field] = calibration[0][field]
    with pytest.raises(InputError):
        freeze_threshold(calibration, spec)


def test_missing_holdout_outcomes_never_disappear():
    calibration, test, spec = inputs()
    plan = freeze_threshold(calibration, spec)
    with pytest.raises(InputError):
        validate_holdout(plan, test[:-1])


@pytest.mark.parametrize('field', ['model_id', 'policy_version', 'rubric_hash', 'subgroup', 'task_hash', 'cluster_id'])
def test_holdout_identity_change_rejected(field):
    calibration, test, spec = inputs()
    plan = freeze_threshold(calibration, spec)
    test[0][field] = 'changed'
    with pytest.raises(InputError):
        validate_holdout(plan, test)


def test_repeated_clusters_are_not_independent_trials():
    calibration, test, spec = inputs()
    spec['holdout_schedule'][1]['cluster_id'] = spec['holdout_schedule'][0]['cluster_id']
    with pytest.raises(InputError, match='independent'):
        freeze_threshold(calibration, spec)


def test_subgroup_familywise_correction_and_missing_evidence():
    calibration, test, spec = inputs(n=120)
    for r in test[:10]:
        r['subgroup'] = 'rare'
    spec['holdout_schedule'] = [{k: r[k] for k in ('observation_id', 'task_hash', 'cluster_id', 'subgroup')} for r in test]
    spec['required_subgroups'] = ['rare']
    plan = freeze_threshold(calibration, spec)
    result = validate_holdout(plan, test)
    assert len(result['checks']) == 2
    assert all(c['alpha'] == .025 for c in result['checks'])
    assert not result['numerical_checks_pass']
    assert result['checks'][1]['accepted'] == 10


def test_action_threshold_and_confidence_gate_affect_acceptance():
    calibration, test, spec = inputs()
    spec['action_probability_floors'] = {'inspect': .999}
    result = validate_holdout(freeze_threshold(calibration, spec), test)
    assert result['checks'][0]['accepted'] == 0
    assert result['checks'][0]['error_upper_bound'] is None
    spec['action_probability_floors'] = {}
    spec['confidence_floor'] = .999
    assert validate_holdout(freeze_threshold(calibration, spec), test)['checks'][0]['accepted'] == 0


def test_bad_predictions_fail_risk_limit():
    calibration, test, spec = inputs()
    for r in test[:30]:
        r['label'] = 'stop'
    result = validate_holdout(freeze_threshold(calibration, spec), test)
    assert result['checks'][0]['errors'] == 30
    assert not result['numerical_checks_pass']


def test_policy_digest_protects_frozen_threshold():
    calibration, test, spec = inputs()
    plan = freeze_threshold(calibration, spec)
    plan['maximum_error'] = .99
    with pytest.raises(InputError):
        validate_holdout(plan, test)


def test_report_self_check_and_json_roundtrip():
    from jev_integration_evaluator.holdout import verify_holdout_report
    import json
    calibration, holdout, spec = inputs()
    report = validate_holdout(freeze_threshold(calibration, spec), holdout)
    verify_holdout_report(json.loads(json.dumps(report)))


@pytest.mark.parametrize('mutation', ['eligible', 'bound', 'coverage', 'errors', 'schedule'])
def test_report_cannot_self_consistently_claim_unsupported_validation(mutation):
    from jev_integration_evaluator.holdout import verify_holdout_report
    from jev_integration_evaluator.contracts import seal
    calibration, holdout, spec = inputs()
    report = validate_holdout(freeze_threshold(calibration, spec), holdout)
    if mutation == 'eligible': report['eligible_for_activation'] = True
    if mutation == 'bound': report['checks'][0]['error_upper_bound'] = 0
    if mutation == 'coverage': report['checks'][0]['coverage'] = 0
    if mutation == 'errors': report['checks'][0]['errors'] = 500
    if mutation == 'schedule': report['scheduled_observations'] = 1
    with pytest.raises(InputError): verify_holdout_report(seal(report))
