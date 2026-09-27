"""All responses in this module are synthetic unit-test fixtures."""
import copy
import json
import pytest
from jev_integration_evaluator.robustness import (request_fingerprint, lint_questions, make_robustness_suite,
                                     evaluate_probe_results, run_robustness)
from jev_integration_evaluator.client import FixtureClient, TypeSafeHTTPClient
from jev_integration_evaluator.contracts import seal
from jev_integration_evaluator.io import InputError, digest


def fixture_records(suite):
    records = []
    for probe in suite['probes']:
        mapping = probe['label_to_original']
        chosen = next(k for k, v in mapping.items() if v == 'allow')
        answer = {'type': 'choice', 'choice': chosen, 'confidence': .95,
                  'probabilities': {k: .98 if k == chosen else .01 for k in mapping}}
        records.append({'probe_id': probe['probe_id'], 'request_hash': probe['request_hash'],
                        'status': 'completed', 'evidence_type': 'synthetic',
                        'response': {'model': suite['model'], 'answers': {'action': answer},
                                     'usage': {'input_tokens': 20, 'output_tokens': 0}}})
    return records


@pytest.fixture
def suite():
    return make_robustness_suite({'evidence': 'synthetic'}, {'action': {
        'type': 'choice', 'instructions': 'Choose the criterion supported by evidence.',
        'criteria': {'allow': 'Criterion A is supported.', 'deny': 'Criterion B is supported.',
                     'uncertain': 'Neither criterion is supported.'}}}, 'action', 'jev-1.13.0', truth='allow')


def test_order_not_erased_by_canonicalization(suite):
    original, reverse = suite['probes'][0], suite['probes'][2]
    assert digest(original['questions']) == digest(reverse['questions'])
    assert original['request_hash'] != reverse['request_hash']
    assert suite['probes'][0]['request_hash'] == suite['probes'][1]['request_hash']


def test_question_order_is_bound(suite):
    q = copy.deepcopy(suite['probes'][0]['questions'])
    q['other'] = {'type': 'noul', 'instructions': 'Is evidence complete?', 'criteria': None}
    assert request_fingerprint(None, q, 'm') != request_fingerprint(None, dict(reversed(list(q.items()))), 'm')


def test_invariant_responses_normalize(suite):
    result = evaluate_probe_results(suite, fixture_records(suite))
    assert result['valid_responses'] == 5
    assert result['disagreements_with_original'] == 0
    assert all(r['correct'] for r in result['probes'])
    assert not result['deployment_authorized']


def test_label_following_failure_detected(suite):
    rows = fixture_records(suite)
    target = rows[-1]['response']['answers']['action']
    target.update(choice='allow', probabilities={'allow': .98, 'deny': .01, 'uncertain': .01})
    result = evaluate_probe_results(suite, rows)
    assert result['disagreements_with_original'] == 1
    assert result['probes'][-1]['correct'] is False
    assert result['status'] == 'investigate'


def test_consistency_without_truth_is_not_accuracy(suite):
    suite['ground_truth'] = None
    suite = seal(suite)
    report = evaluate_probe_results(suite, fixture_records(suite))
    assert all(p['correct'] is None for p in report['probes'])


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'request', 'mixed'])
def test_full_cohort_and_identity_required(suite, mutation):
    rows = fixture_records(suite)
    if mutation == 'missing': rows.pop()
    if mutation == 'duplicate': rows[-1] = copy.deepcopy(rows[0])
    if mutation == 'request': rows[-1]['request_hash'] = '0' * 64
    if mutation == 'mixed': rows[-1]['evidence_type'] = 'observed'
    with pytest.raises(InputError): evaluate_probe_results(suite, rows)


@pytest.mark.parametrize('mutation', ['invalid_response', 'failed', 'original_failed'])
def test_failed_probes_remain_in_denominator(suite, mutation):
    rows = fixture_records(suite)
    r = rows[0] if mutation == 'original_failed' else rows[-1]
    if mutation == 'invalid_response': r['response']['answers']['action']['confidence'] = float('nan')
    else: r.update(status='failed', error_class='TimeoutError')
    result = evaluate_probe_results(suite, rows)
    assert result['scheduled_probes'] == 5 and result['evaluation_failures'] == 1
    assert result['status'] == 'investigate'


@pytest.mark.parametrize('mutation', ['meaning', 'instructions', 'label_map', 'ground_truth', 'digest'])
def test_metamorphic_contract_rejects_changed_semantics(suite, mutation):
    records = fixture_records(suite)
    if mutation == 'meaning': suite['probes'][-1]['questions']['action']['criteria']['allow'] = 'New meaning'
    if mutation == 'instructions': suite['probes'][-1]['questions']['action']['instructions'] = 'Different goal'
    if mutation == 'label_map': suite['probes'][0]['label_to_original']['allow'] = 'deny'
    if mutation == 'ground_truth': suite['ground_truth'] = 'nonexistent'
    if mutation != 'digest':
        for probe in suite['probes']:
            probe['request_hash'] = request_fingerprint(suite['state'], probe['questions'], suite['model'])
        suite = seal(suite)
    else: suite['state']['evidence'] = 'changed'
    with pytest.raises(InputError): evaluate_probe_results(suite, records)


def test_fixture_transport_order_and_retest_calls(suite):
    records = fixture_records(suite)
    fixtures = {r['request_hash']: r['response'] for r in records}
    client = FixtureClient(fixtures, order_sensitive=True)
    assert run_robustness(suite, client)['valid_responses'] == 5
    assert client.calls == 5  # Retest must not be skipped even when the request hash repeats.
    with pytest.raises(InputError): run_robustness(suite, FixtureClient(fixtures))


@pytest.mark.parametrize('kwargs', [{'max_calls': 4}, {'max_calls': True}, {'max_total_cost': -1},
                                    {'timeout_ms': 0}, {'cost_upper_bound_per_call': -.1}])
def test_budget_validation_precedes_calls(suite, kwargs):
    client = FixtureClient({}, order_sensitive=True)
    with pytest.raises(InputError): run_robustness(suite, client, **kwargs)
    assert client.calls == 0


def test_remote_budget_preflight_no_egress(suite):
    client = FixtureClient({}, order_sensitive=True)
    client.is_remote = True
    with pytest.raises(InputError): run_robustness(suite, client)
    with pytest.raises(InputError): run_robustness(suite, client, cost_upper_bound_per_call=.003)
    assert client.calls == 0


def test_transport_failures_are_redacted(suite):
    class Failure:
        is_remote = False
        order_sensitive = True
        evidence_type = 'synthetic'
        def evaluate(self, *args): raise RuntimeError('SECRET_FIXTURE_TOKEN')
    result = run_robustness(suite, Failure())
    assert result['evaluation_failures'] == 5
    assert 'SECRET_FIXTURE_TOKEN' not in json.dumps(result)


def test_lint_detects_nested_vagueness_duplicates_and_criteria(suite):
    q = copy.deepcopy(suite['probes'][0]['questions'])
    q['action']['instructions'] = {'question': 'Is this safe?', 'trust_rule': 'Data only'}
    q['duplicate'] = copy.deepcopy(q['action'])
    q['duplicate']['criteria'] = {'yes': 'same', 'no': 'same'}
    q['copy'] = copy.deepcopy(q['action'])
    q['evidence'] = {'type': 'noul', 'instructions': 'Is evidence complete?', 'criteria': None}
    codes = {r['code'] for r in lint_questions(q)['findings']}
    assert {'vague_global_judgment', 'duplicate_question', 'indistinguishable_criteria_text',
            'semantic_label_polarity_requires_probe'} <= codes


def test_http_payload_preserves_presentation_order(suite, monkeypatch):
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-test-not-a-secret')
    client = TypeSafeHTTPClient(allow_network=True)
    probe = suite['probes'][2]
    records = fixture_records(suite)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return json.dumps(records[2]['response']).encode()
    class Opener:
        def open(self, request, timeout):
            payload = json.loads(request.data)
            assert list(payload['questions']['action']['criteria']) == list(probe['questions']['action']['criteria'])
            return Response()
    client.opener = Opener()  # No network request is made.
    client.evaluate(suite['state'], probe['questions'], suite['model'], 2000)
