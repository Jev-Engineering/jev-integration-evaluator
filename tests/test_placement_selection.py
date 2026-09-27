"""Deterministic selector qualification; all hosts/reviews/numbers synthetic."""
import copy
from pathlib import Path

import pytest

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.contracts import seal, validate_contract
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.optimizer import REQUIRED, optimize
from jev_integration_evaluator.selection import (
    SelectionError, prepare_experimental_plan, request_sha256,
    select_placement, verify_selection, selection_engine_sha256,
)
from scripts.implementation_fixtures import fixture


@pytest.fixture
def context(tmp_path):
    host = tmp_path / 'host'
    inventory, spec = fixture(host, 'C', tag='selection_fixture')
    c = next(c for c in inventory['candidates'] if c['candidate_id'] == spec['candidate_id'])
    assert all(c['estimates'][k] is None for k in REQUIRED)
    request = {
        'schema_version': '1.0', 'selection_engine_sha256': selection_engine_sha256(), 'mode': 'experimental',
        'inventory_sha256': digest(inventory), 'candidate_id': c['candidate_id'],
        'decision_review': {'reviewer': 'synthetic-selector-test',
                            'reason': 'Synthetic local preparation qualification; no live authority.',
                            'evidence_refs': ['fixture:selection-case-C']},
        'preparation_scope_ref': 'synthetic-disposable-local-fixture',
        'implementation_spec_sha256': digest(spec), 'constraints': None,
        'live_limits': {'max_total_cost': None, 'max_total_calls': None,
                        'max_concurrent_calls': None},
    }
    return host, inventory, c, spec, request


def bind(inventory, request, spec=None):
    request['inventory_sha256'] = digest(inventory)
    if spec is not None:
        spec['inventory_sha256'] = digest(inventory)
        request['implementation_spec_sha256'] = digest(spec)
    return request_sha256(request)


def select(context):
    _, inventory, _, _, request = context
    return select_placement(inventory, request, approved_request_sha256=bind(inventory, request))


def optimization_request(inventory):
    return {'schema_version': '1.0', 'selection_engine_sha256': selection_engine_sha256(), 'mode': 'optimize',
            'inventory_sha256': digest(inventory), 'candidate_id': None,
            'decision_review': None, 'preparation_scope_ref': None,
            'implementation_spec_sha256': None,
            'constraints': load_config()['constraints'],
            'live_limits': {'max_total_cost': None, 'max_total_calls': None,
                            'max_concurrent_calls': None}}


def measured_shape(c, **updates):
    c['estimates'].update({k: 0.0 for k in REQUIRED})
    c['estimates'].update(quality_gain=.3, reliability_gain=.1, throughput=100,
                          provenance='Synthetic declared assumptions, not observed measurements')
    c['estimates'].update(updates)


def test_experiment_retains_unknown_values_and_no_authority(context):
    _, inventory, c, _, request = context
    before = copy.deepcopy((inventory, request))
    result = select(context)
    assert result['status'] == 'experimental_selected'
    assert result['selected_candidate_ids'] == [c['candidate_id']]
    assert result['selected_estimates'][c['candidate_id']] == c['estimates']
    assert all(v is None for v in result['selected_estimates'][c['candidate_id']].values())
    assert result['optimizer_result'] is None
    assert result['implementation_status'] == 'not_checked'
    assert len(result['missing_live_bounds']) == 3
    for name in ('execution_authorized', 'target_mutation_authorized',
                 'live_spend_authorized', 'runtime_activation_authorized', 'benefit_demonstrated'):
        assert result[name] is False
    assert result['adoption_recommendation'] is None
    assert (inventory, request) == before
    validate_contract(result, 'placement-selection')


def test_unknown_estimates_do_not_mean_no_useful_placement(context):
    _, inventory, _, _, _ = context
    result = select_placement(inventory, optimization_request(inventory))
    assert result['status'] == 'insufficient_estimates'
    assert result['optimizer_result']['status'] == 'no_justified_integration_set'
    assert result['selected_candidate_ids'] == []


def test_hash_computation_is_not_selection_approval(context):
    _, inventory, _, _, request = context
    digest_value = request_sha256(request)
    result = select_placement(inventory, request)
    assert result['request_sha256'] == digest_value
    assert result['status'] == 'selection_review_required'
    assert result['selected_candidate_ids'] == []


def test_wrong_selection_approval_rejected(context):
    _, inventory, _, _, request = context
    with pytest.raises(SelectionError, match='selection_approval_mismatch'):
        select_placement(inventory, request, approved_request_sha256='0'*64)


@pytest.mark.parametrize('change', [
    {'tier': 0}, {'pattern': 'NONE'}, {'deterministic_alternative': 'preferred'},
    {'deterministic_alternative': 'mandatory'}, {'hard_real_time': True},
])
@pytest.mark.parametrize('mode', ['experimental', 'optimize'])
def test_hard_rejections_cannot_be_overridden(context, change, mode):
    _, inventory, c, _, request = context
    c.update(change)
    c['semantic_review']['approved'] = True
    measured_shape(c)
    bind(inventory, request)
    if mode == 'optimize':
        request = optimization_request(inventory)
    result = select_placement(inventory, request, approved_request_sha256=request_sha256(request))
    assert c['candidate_id'] not in result['selected_candidate_ids']
    row = next(r for r in result['candidate_assessments'] if r['candidate_id'] == c['candidate_id'])
    assert row['review_status'] == 'deterministic_rejection'


@pytest.mark.parametrize('mode', ['experimental', 'optimize'])
def test_stale_source_review_never_selected(context, mode):
    _, inventory, c, _, request = context
    c['semantic_review']['source_sha256'] = 'a'*64
    measured_shape(c)
    if mode == 'optimize':request = optimization_request(inventory)
    bind(inventory, request)
    result = select_placement(inventory, request, approved_request_sha256=request_sha256(request))
    assert c['candidate_id'] not in result['selected_candidate_ids']
    assert next(r for r in result['candidate_assessments'] if r['candidate_id'] == c['candidate_id'])['review_status'] == 'stale_semantic_review'


@pytest.mark.parametrize('field,value', [('reviewer', None), ('reviewer', ' '), ('reason', None), ('reason', '\n')])
def test_missing_review_is_not_a_semantic_rejection(context, field, value):
    _, _, c, _, _ = context
    c['semantic_review'][field] = value
    assert select(context)['status'] == 'semantic_review_required'


def test_source_matched_negative_review_is_distinct(context):
    _, _, c, _, _ = context
    c['semantic_review']['approved'] = False
    assert select(context)['status'] == 'semantic_rejection'


def test_inventory_and_analysis_digest_must_match(context):
    _, inventory, _, _, request = context
    inventory['repository_name'] += '-drift'
    with pytest.raises(SelectionError, match='inventory_identity_mismatch'):
        select_placement(inventory, request)
    request['inventory_sha256'] = digest(inventory)
    inventory['scan_fingerprint'] = '0'*64
    request['inventory_sha256'] = digest(inventory)
    with pytest.raises(SelectionError, match='analysis_identity_mismatch'):
        select_placement(inventory, request)


def test_duplicate_candidate_ids_rejected(context):
    _, inventory, c, _, request = context
    inventory['candidates'].append(copy.deepcopy(c))
    bind(inventory, request)
    with pytest.raises(SelectionError, match='duplicate_candidate_id'):
        select_placement(inventory, request)


def test_unknown_selected_id_is_not_no_candidate(context):
    _, inventory, _, _, request = context
    request['candidate_id'] = 'JEV-UNKNOWN'
    with pytest.raises(SelectionError, match='unknown_selected_candidate'):
        select_placement(inventory, request)


def test_no_candidates_not_no_useful_placement(context):
    _, inventory, _, _, _ = context
    inventory['candidates'] = []
    inventory['interactions'] = []
    result = select_placement(inventory, optimization_request(inventory))
    assert result['status'] == 'no_candidates_discovered'


@pytest.mark.parametrize('change', [
    {'truncated': True}, {'warnings': [{'reason': 'parser unavailable'}]},
    {'ignored': [{'reason': 'file-size budget'}]},
    {'parser_counts': {'lexical_review_only': 1}}, {},
])
def test_incomplete_scan_never_becomes_negative_evidence(context, change):
    _, inventory, _, _, _ = context
    inventory['candidates'] = []; inventory['interactions'] = []
    if change:inventory['coverage'].update(change)
    else:inventory['coverage'] = {}
    inventory['analysis_identity']['coverage_digest'] = digest(inventory['coverage'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    result = select_placement(inventory, optimization_request(inventory))
    assert result['status'] == 'incomplete_analysis'
    assert result['coverage_complete_within_inventory'] is False


def test_complete_negative_reviews_are_inventory_scoped_not_repository_absence(context):
    _, inventory, _, _, _ = context
    for c in inventory['candidates']:
        c['tier'] = 1; c['pattern'] = 'C'; c['deterministic_alternative'] = 'weak'
        c['semantic_review'] = {'approved': False, 'reviewer': 'synthetic-independent-rejection',
            'reason': 'Synthetic case: deterministic alternatives meet the stated objective.',
            'source_sha256': c['source']['source_sha256']}
    result = select_placement(inventory, optimization_request(inventory))
    assert result['status'] == 'no_useful_placement_within_reviewed_inventory'
    inventory['coverage']['warnings'] = [{'reason': 'truncated source'}]
    inventory['analysis_identity']['coverage_digest'] = digest(inventory['coverage'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    result = select_placement(inventory, optimization_request(inventory))
    assert result['status'] == 'incomplete_analysis'


def test_estimate_based_optimization_is_not_observed_benefit(context):
    _, inventory, c, _, _ = context
    measured_shape(c)
    result = select_placement(inventory, optimization_request(inventory))
    assert result['status'] == 'estimate_based_optimization'
    assert c['candidate_id'] in result['selected_candidate_ids']
    assert result['benefit_demonstrated'] is False
    assert result['adoption_recommendation'] is None


def test_missing_estimate_provenance_distinct(context):
    _, inventory, c, _, _ = context
    measured_shape(c, provenance=None)
    result = select_placement(inventory, optimization_request(inventory))
    assert result['status'] == 'missing_estimate_provenance'


def test_no_positive_set_not_semantic_absence(context):
    _, inventory, c, _, _ = context
    measured_shape(c, quality_gain=-2, reliability_gain=-2)
    result = select_placement(inventory, optimization_request(inventory))
    assert result['status'] == 'no_feasible_positive_set_under_declared_model'


@pytest.mark.parametrize('value', [True, -1, '0', float('nan'), float('inf')])
def test_invalid_live_bounds_rejected(context, value):
    _, inventory, _, _, request = context
    request['live_limits']['max_total_cost'] = value
    with pytest.raises(SelectionError):select_placement(inventory, request)


def test_known_live_limits_still_do_not_authorize_spending(context):
    _, _, _, _, request = context
    request['live_limits'] = {'max_total_cost': 1, 'max_total_calls': 5, 'max_concurrent_calls': 1}
    result = select(context)
    assert result['missing_live_bounds'] == []
    assert result['live_spend_authorized'] is False


def test_unknown_fields_cannot_smuggle_approval(context):
    _, inventory, _, _, request = context
    request['execution_authorized'] = True
    with pytest.raises(SelectionError, match='invalid_placement_selection_request'):
        select_placement(inventory, request)


def test_resealed_fake_receipt_rejected_by_recomputation(context):
    _, inventory, _, _, request = context
    result = select(context)
    result['status'] = 'no_candidates_discovered'
    result = seal(result)
    with pytest.raises(SelectionError, match='selection_recomputation_mismatch'):
        verify_selection(inventory, request, result, approved_request_sha256=request_sha256(request))


def test_selection_roundtrip_recomputes(context):
    _, inventory, _, _, request = context
    result = select(context)
    verify_selection(inventory, request, result, approved_request_sha256=request_sha256(request))


def test_actual_plan_unknown_estimates_no_target_mutation(context, tmp_path):
    host, inventory, c, spec, request = context
    before = {p.relative_to(host): p.read_bytes() for p in host.rglob('*') if p.is_file()}
    out = tmp_path / 'bundle'
    result = prepare_experimental_plan(host, inventory, request, spec, out,
                                      approved_request_sha256=request_sha256(request))
    assert result['selection']['status'] == 'experimental_selected'
    assert result['implementation']['status'] == 'planned'
    assert result['implementation']['target_modified'] is False
    assert result['implementation']['target_executed'] is False
    assert (out / 'implementation.diff').is_file()
    assert (out / 'implementation-plan.json').is_file()
    assert all(v is None for v in c['estimates'].values())
    assert before == {p.relative_to(host): p.read_bytes() for p in host.rglob('*') if p.is_file()}


def test_plan_refuses_source_drift_before_output(context, tmp_path):
    host, inventory, _, spec, request = context
    (host / spec['source']['file']).write_text('# drift\n')
    with pytest.raises(SelectionError, match='implementation_validation_failed'):
        prepare_experimental_plan(host, inventory, request, spec, tmp_path / 'bundle',
                                  approved_request_sha256=request_sha256(request))
    assert not (tmp_path / 'bundle').exists()


def test_changed_spec_requires_fresh_selection_review(context, tmp_path):
    host, inventory, _, spec, request = context
    spec['runtime']['task_field'] = 'different'
    with pytest.raises(SelectionError, match='specification_identity_mismatch'):
        prepare_experimental_plan(host, inventory, request, spec, tmp_path / 'bundle',
                                  approved_request_sha256=request_sha256(request))
    assert not (tmp_path / 'bundle').exists()


@pytest.mark.parametrize("shape,expected", [("two_statements", "unsupported_implementation"),
                                           ("async", "missing_prerequisite")])
def test_recipe_unsupported_not_absence_of_useful_placement(context, tmp_path, shape, expected):
    host, inventory, _, spec, request = context
    # This is an intentionally unsupported source shape. Preserve the refreshed
    # hashes/reviews so rejection must come from the actual recipe validator.
    file = host / spec['source']['file']
    raw = file.read_text()
    symbol = spec['source']['symbol']
    if shape == 'async':
        # The current strict recipe classifies the absent synchronous binding
        # as MissingBinding. Do not weaken or reclassify that validator.
        raw = raw.replace('def ' + symbol + '(', 'async def ' + symbol + '(')
    else:
        import ast
        node = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == symbol)
        lines = raw.splitlines(keepends=True)
        lines.insert(node.body[0].lineno - 1, '    pass\n')
        raw = ''.join(lines)
    file.write_text(raw)
    from jev_integration_evaluator.scanner import scan_repo
    from jev_integration_evaluator.scoring import apply_reviews
    fresh = scan_repo(host, load_config())
    match = next(c for c in fresh['candidates'] if c['source']['symbol'] == symbol and c['pattern'] == 'C')
    apply_reviews(fresh, {match['candidate_id']: {'source_sha256': match['source']['source_sha256'],
        'reviewer': 'synthetic', 'reason': 'Synthetic reviewed unsupported candidate; not rewrite qualification.', 'approved': True}}, load_config())
    spec['source'].update({k: match['source'][k] for k in ('source_sha256','file_sha256')})
    spec['binding_review']['source_sha256'] = match['source']['source_sha256']
    spec['inventory_fingerprint'] = fresh['scan_fingerprint']
    spec['candidate_id'] = match['candidate_id']
    spec['experiment_id'] = match['recommended_experiment']['id']
    request['candidate_id'] = match['candidate_id']
    approved = bind(fresh, request, spec)
    result = prepare_experimental_plan(host, fresh, request, spec, tmp_path/'bundle', approved_request_sha256=approved)
    assert result['implementation']['status'] == expected
    assert result['selection']['status'] == 'experimental_selected'
    assert not (tmp_path/'bundle').exists()


@pytest.mark.parametrize('change', [{'hard_real_time': True}, {'pattern': 'NONE'}, {'deterministic_alternative': 'mandatory'}])
def test_legacy_optimizer_rechecks_hard_gates_with_high_tier(context, change):
    _, inventory, c, _, _ = context
    c['tier'] = 3; c.update(change); measured_shape(c)
    result = optimize(inventory, load_config()['constraints'])
    assert c['candidate_id'] not in result['recommended_balanced_set']['candidate_ids']


def test_legacy_optimizer_rejects_explicit_source_stale_review(context):
    _, inventory, c, _, _ = context
    measured_shape(c); c['semantic_review']['source_sha256'] = '0'*64
    result = optimize(inventory, load_config()['constraints'])
    assert c['candidate_id'] not in result['recommended_balanced_set']['candidate_ids']
    assert any(x['candidate_id'] == c['candidate_id'] and x['reason'] == 'Stale semantic review' for x in result['excluded'])


@pytest.mark.parametrize('field', ['source_digest', 'configuration_digest', 'parser_digest', 'coverage_digest'])
def test_self_consistent_top_hash_does_not_hide_changed_analysis_records(context, field):
    _, inventory, _, _, request = context
    inventory['analysis_identity'][field] = 'f'*64
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    bind(inventory, request)
    with pytest.raises(SelectionError, match='analysis_record_mismatch'):
        select_placement(inventory, request)


def test_candidate_must_match_full_file_record(context):
    _, inventory, c, _, request = context
    c['source']['file_sha256'] = 'f'*64
    bind(inventory, request)
    with pytest.raises(SelectionError, match='candidate_source_record_mismatch'):
        select_placement(inventory, request)


def test_unknown_dependency_fields_are_not_silently_discarded(context):
    _, inventory, c, _, request = context
    other = next(x for x in inventory['candidates'] if x['candidate_id'] != c['candidate_id'])
    inventory['interactions'] = [{'a': c['candidate_id'], 'b': other['candidate_id'],
        'status': 'hypothesis', 'utility_delta': 0, 'conflict': False, 'requires': True}]
    bind(inventory, request)
    with pytest.raises(SelectionError, match='invalid_placement_interaction'):
        select_placement(inventory, request)


def test_duplicate_interaction_cannot_double_count_synergy(context):
    _, inventory, c, _, request = context
    other = next(x for x in inventory['candidates'] if x['candidate_id'] != c['candidate_id'])
    edge = {'a': c['candidate_id'], 'b': other['candidate_id'], 'status': 'measured',
            'utility_delta': .1, 'conflict': False, 'provenance': 'Synthetic branch test only'}
    inventory['interactions'] = [edge, {**edge, 'a': edge['b'], 'b': edge['a']}]
    bind(inventory, request)
    with pytest.raises(SelectionError, match='duplicate_candidate_interaction'):
        select_placement(inventory, request)


def test_measured_interaction_requires_declared_provenance(context):
    _, inventory, c, _, request = context
    other = next(x for x in inventory['candidates'] if x['candidate_id'] != c['candidate_id'])
    inventory['interactions'] = [{'a': c['candidate_id'], 'b': other['candidate_id'],
        'status': 'measured', 'utility_delta': 100, 'conflict': False}]
    bind(inventory, request)
    with pytest.raises(SelectionError, match='invalid_placement_interaction'):
        select_placement(inventory, request)


@pytest.mark.parametrize('field,value', [('utility_delta', True), ('conflict', 'false'),
                                        ('status', 'secret-unrecognized-status')])
def test_interaction_types_are_strict(context, field, value):
    _, inventory, c, _, request = context
    other = next(x for x in inventory['candidates'] if x['candidate_id'] != c['candidate_id'])
    edge = {'a': c['candidate_id'], 'b': other['candidate_id'],
            'status': 'hypothesis', 'utility_delta': 0, 'conflict': False}
    edge[field] = value; inventory['interactions'] = [edge]
    bind(inventory, request)
    with pytest.raises(SelectionError, match='invalid_placement_interaction'):
        select_placement(inventory, request)


def test_optimization_candidate_bound_is_explicit(context, monkeypatch):
    import jev_integration_evaluator.selection as module
    _, inventory, _, _, _ = context
    monkeypatch.setattr(module, 'MAX_OPTIMIZER_CANDIDATES', 0)
    with pytest.raises(SelectionError, match='optimization_candidate_limit'):
        select_placement(inventory, optimization_request(inventory))


@pytest.mark.parametrize('pattern', list('ABCDEFGHIJKLM'))
def test_each_existing_recipe_prepares_with_unknown_estimates(tmp_path, pattern):
    host = tmp_path/'host'; inventory, spec = fixture(host, pattern, tag='selection_'+pattern)
    request = {'schema_version': '1.0', 'selection_engine_sha256': selection_engine_sha256(), 'mode': 'experimental', 'inventory_sha256': digest(inventory),
        'candidate_id': spec['candidate_id'], 'decision_review': {'reviewer': 'synthetic-selector',
        'reason': 'Existing bounded recipe preparation with unknown benefit; synthetic only.',
        'evidence_refs': ['fixture:'+pattern]}, 'preparation_scope_ref': 'test-owned-disposable-fixture',
        'implementation_spec_sha256': digest(spec), 'constraints': None,
        'live_limits': {'max_total_cost': None, 'max_total_calls': None, 'max_concurrent_calls': None}}
    before = {p.relative_to(host): p.read_bytes() for p in host.rglob('*') if p.is_file()}
    result = prepare_experimental_plan(host, inventory, request, spec, tmp_path/'bundle',
                                      approved_request_sha256=request_sha256(request))
    assert result['implementation']['status'] == 'planned'
    assert result['selection']['benefit_demonstrated'] is False
    assert all(v is None for v in result['selection']['selected_estimates'][spec['candidate_id']].values())
    assert before == {p.relative_to(host): p.read_bytes() for p in host.rglob('*') if p.is_file()}


def test_result_math_overflow_is_redacted(context):
    _, inventory, _, _, _ = context
    # Finite individual inputs may overflow when added. Never emit an infinite
    # utility or call a non-serializable result a valid optimization record.
    for c in inventory['candidates'][:3]:
        c.update(tier=2, pattern='C', deterministic_alternative='weak')
        c['semantic_review'].update(approved=True, reviewer='synthetic-overflow', reason='Synthetic limits test',
                                    source_sha256=c['source']['source_sha256'])
        measured_shape(c, quality_gain=1.5e308, reliability_gain=1.5e308)
    with pytest.raises(SelectionError):
        select_placement(inventory, optimization_request(inventory))


def test_io_failure_from_existing_planner_does_not_leak_private_paths(context, tmp_path, monkeypatch):
    from jev_integration_evaluator.integrations import lifecycle
    host, inventory, _, spec, request = context
    def failed(*args, **kwargs):
        raise PermissionError('PRIVATE_PATH_AND_CREDENTIAL_SENTINEL')
    monkeypatch.setattr(lifecycle, 'plan_implementation', failed)
    with pytest.raises(SelectionError, match='implementation_io_unavailable') as caught:
        prepare_experimental_plan(host, inventory, request, spec, tmp_path/'bundle',
                                  approved_request_sha256=request_sha256(request))
    assert 'PRIVATE_' not in str(caught.value)
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize('name', ['placement-selection-request', 'placement-selection', 'placement-estimates',
                                 'placement-interaction', 'placement-selection-envelope', 'placement-selection-summary'])
def test_new_schemas_are_valid_and_mirrored(name):
    import json
    import jsonschema
    root = Path(__file__).resolve().parents[1]
    package = root/'jev_integration_evaluator/data'/(name+'.schema.json')
    assert package.read_bytes() == (root/'schemas'/(name+'.schema.json')).read_bytes()
    jsonschema.Draft202012Validator.check_schema(json.loads(package.read_bytes()))


def test_changed_selector_engine_invalidates_approval(context, monkeypatch):
    import jev_integration_evaluator.selection as module
    _, inventory, _, _, request = context
    approval = request_sha256(request)
    monkeypatch.setattr(module, 'selection_engine_sha256', lambda: 'f'*64)
    with pytest.raises(SelectionError, match='selection_engine_mismatch'):
        select_placement(inventory, request, approved_request_sha256=approval)


def test_engine_hash_is_retained_in_selection(context):
    _, _, _, _, request = context
    result = select(context)
    assert result['selection_engine_sha256'] == request['selection_engine_sha256']
