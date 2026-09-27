"""Adversarial dev8 regressions, not independent corpus or runtime qualification.

The published factory constructs source-matched facts through the real discovery,
nomination and semantic-review bridge. New assertions deliberately mix judgments
at different scopes; no inventory, source hash, or runtime observation is forged.
"""
from __future__ import annotations

import os

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import placement_selection as selection
from jev_integration_evaluator.io import canonical
from test_repository_placement_selection import factory, context, request, scope_review

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Secure source discovery currently qualifies POSIX")


def _file(scope, name):
    return next(row for row in scope['files'] if row['file'] == name)


def _seam(scope, name):
    return next(row for row in scope['seams'] if row['source']['qualified_symbol'] == name)


def _inconsistent(case, kind):
    review = scope_review(case)
    if kind == 'negative_file_positive_candidate':
        # A positive judgment in another file must not hide this file's conflict.
        _file(review, 'other.py')['disposition'] = 'useful'
        for row in review['seams']:
            row['disposition'] = 'useful'
    elif kind == 'negative_seam_positive_candidate':
        for row in review['files']:
            row['disposition'] = 'useful'
    elif kind == 'negative_file_positive_seam':
        _file(review, 'other.py')['disposition'] = 'useful'
        _seam(review, 'q')['disposition'] = 'useful'
    elif kind == 'negative_file_unnominated_positive_seam':
        _file(review, 'other.py')['disposition'] = 'useful'
        _seam(review, 'b')['disposition'] = 'useful'
    elif kind == 'partial_negative_file_positive_candidate':
        review['seams'] = []
        review['files'] = [row for row in review['files'] if row['file'] == 'opaque.py']
    else:
        raise AssertionError('Unknown synthetic review variant')
    return review


KINDS = [
    'negative_file_positive_candidate',
    'negative_seam_positive_candidate',
    'negative_file_positive_seam',
    'negative_file_unnominated_positive_seam',
    'partial_negative_file_positive_candidate',
]


@pytest.mark.parametrize('kind', KINDS)
def test_mixed_scope_contradictions_are_unresolved(factory, kind):
    positive = kind not in ('negative_file_positive_seam', 'negative_file_unnominated_positive_seam')
    case = factory(approved=positive, extra={'other.py': 'VALUE = 11\n'})
    review = _inconsistent(case, kind)
    before = canonical(review)
    result = context(case, review)
    assert result['outcome'] == 'insufficient_evidence'
    assert result['next_action'] == 'reconcile_conflicting_semantic_reviews'
    assert result['scope_review']['provided']
    assert result['scope_review']['review_sha256']
    assert canonical(review) == before
    assert result['authorization'] == selection.DENIED
    assert not result['benefit_supported'] and not result['authority_authenticated']


@pytest.mark.parametrize('kind', KINDS[:2])
def test_mixed_conflict_cannot_select_or_revalidate_a_candidate(factory, kind):
    case = factory(extra={'other.py': 'VALUE = 11\n'})
    review = _inconsistent(case, kind)
    ctx = context(case, review)
    ids = [c['candidate_id'] for c in case['prepared']['inventory']['candidates']]
    req = request(ctx, ids=ids)
    result = selection.select_experimental_placements(**case, selection_review=req, scope_review=review)
    assert result['status'] == 'blocked'
    assert result['requested_count'] == len(ids)
    assert result['selected_count'] == 0
    assert result['placements'] == [] and result['selected_candidate_ids'] == []
    assert {row['reason'] for row in result['failures']} == {'insufficient_evidence'}
    repeated = selection.revalidate_experimental_selection(
        **case, selection_review=req, selection=result, scope_review=review,
        expected_selection_sha256=result['selection_sha256'])
    assert repeated == result and repeated['status'] == 'blocked'


def test_conflict_prevents_unsupported_positive_candidate_becoming_a_nomination(factory):
    case = factory(path='pkg/opaque.py', extra={'other.py': 'VALUE = 11\n'})
    review = scope_review(case)
    _file(review, 'other.py')['disposition'] = 'useful'
    result = context(case, review)
    assert result['outcome'] == 'insufficient_evidence'
    assert result['next_action'] == 'reconcile_conflicting_semantic_reviews'


def test_distinct_files_can_have_distinct_nonconflicting_judgments(factory):
    case = factory(approved=False, extra={'other.py': 'VALUE = 11\n'})
    review = scope_review(case)
    _file(review, 'other.py')['disposition'] = 'useful'
    result = context(case, review)
    assert result['outcome'] == 'nomination_required'
    assert not result['scope_review']['no_useful_judgment']


def test_positive_file_does_not_require_all_enumerated_seams_to_be_positive(factory):
    # Whole-file usefulness can concern a placement outside enumerated seams.
    case = factory(approved=False)
    review = scope_review(case)
    _file(review, 'opaque.py')['disposition'] = 'useful'
    result = context(case, review)
    assert result['outcome'] == 'nomination_required'


def test_positive_review_does_not_override_negative_candidate_for_a_different_recipe(factory):
    # A rejected C candidate does not prove all A-M recipes are useless.
    case = factory(approved=False)
    review = scope_review(case, 'useful')
    result = context(case, review)
    assert result['outcome'] == 'nomination_required'


@pytest.mark.parametrize('kind', ['list', 'dict', 'pending_siblings'])
def test_json_worklist_is_bounded_before_expansion(kind):
    # The invalid leaf must never be visited once the worklist itself is too big.
    # This checks rejection before allocating/traversing a second unbounded list.
    if kind == 'list':
        value = [None] * 200_000 + [object()]
    elif kind == 'dict':
        value = {str(i): None for i in range(200_000)}
        value['unvisited'] = object()
    else:
        value = [[None] * 199_999 + [object()], None]
    with pytest.raises(cap.CapabilityError, match='^selection_structure_budget$'):
        selection._bounded(value)


@pytest.mark.parametrize('value', [None, True, 1, 1.5, 'hello', [], {}, {'x': [1, 2, {'y': 'ok'}]}])
def test_ordinary_plain_json_contract_values_remain_admitted(value):
    selection._bounded(value)
