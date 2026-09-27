"""Hand-authored synthetic fixtures; no provider, target import, or benefit claim."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.nomination_inventory import discover_repository_capabilities
from jev_integration_evaluator.repository_conclusion import (
    CONCLUSION_CONTRACT, REVIEW_CONTRACT, conclude_repository, coverage_review_schedule,
)


@pytest.fixture
def host(tmp_path):
    repo = tmp_path / 'host'
    repo.mkdir()
    # Opaque names deliberately carry no scanner keyword oracle. The baseline
    # uses a real dictionary lookup; it is not a literal/pure-operation wrapper.
    (repo / 'opaque.py').write_text(
        "def x7(q):\n    return q.get('route', 'ordinary')\n\n"
        "def z9(q):\n    return x7(q)\n", encoding='utf-8')
    return repo


def report(repo, policy=None):
    return discover_repository_capabilities(repo, copy.deepcopy(DEFAULT), policy=policy)


def negative_review(r, policy=None):
    schedule = coverage_review_schedule(r, copy.deepcopy(DEFAULT), policy=policy)
    opinion = {p: {'disposition': 'not_useful',
                    'reason': 'The synthetic source provides no justified need for this placement.'}
               for p in 'ABCDEFGHIJKLM'}
    return {
        'schema_version': '1.0', 'contract': REVIEW_CONTRACT,
        **{k: schedule[k] for k in ['report_sha256', 'conclusion_engine_sha256',
                                   'settings_sha256', 'objective_sha256']},
        'reviewer': 'synthetic-test-reviewer-not-an-authenticated-principal',
        'files': [{**row, 'patterns': copy.deepcopy(opinion)} for row in schedule['files']],
        'seams': [{**row, 'patterns': copy.deepcopy(opinion)} for row in schedule['seams']],
    }


def conclude(repo, r, review=None, *, anchor=True, policy=None, **kwargs):
    return conclude_repository(repo, r, copy.deepcopy(DEFAULT), review=review,
                               expected_review_sha256=cap._digest(review) if anchor and review is not None else None,
                               policy=policy, **kwargs)


def test_complete_negative_review_is_scoped_not_global_absence(host):
    r = report(host)
    assert r['discovery_outcome'] == 'review_required'
    rv = negative_review(r)
    original = copy.deepcopy(rv)
    result = conclude(host, r, rv)
    assert result['outcome'] == 'no_useful_placement'
    assert result['scope']['global_absence_proven'] is False
    assert result['scope']['snapshot_scope'] == 'bounded_source_and_configuration_not_full_repository'
    assert result['coverage']['expected_file_reviews'] == 1
    assert result['coverage']['expected_seam_reviews'] == 2
    assert result['coverage']['unresolved_pattern_reviews'] == 0
    assert result['review_principal_authenticated'] is False
    assert result['benefit'] is None
    assert result['binding_review'] == 'not_performed'
    assert not any(result['authorization'].values())
    assert not result['implementation_verified']
    assert rv == original


def test_no_review_is_not_absence(host):
    result = conclude(host, report(host))
    assert result['outcome'] == 'review_required'
    assert result['coverage']['unresolved_pattern_reviews'] == 39
    assert result['coverage']['complete_anchored_review'] is False


@pytest.mark.parametrize('rows', ['files', 'seams'])
def test_omitted_review_keeps_denominator(host, rows):
    r = report(host)
    rv = negative_review(r)
    rv[rows].pop()
    result = conclude(host, r, rv)
    assert result['outcome'] == 'insufficient_evidence'
    assert result['coverage']['unresolved_pattern_reviews'] == 13
    assert result['pending'][rows]


def test_unanchored_complete_review_is_not_trusted(host):
    r = report(host)
    result = conclude(host, r, negative_review(r), anchor=False)
    assert result['outcome'] == 'insufficient_evidence'
    assert result['review_anchor_matched'] is False
    assert 'supply_independently_retained_review_digest' in result['next_actions']


def test_unknown_answer_remains_unresolved(host):
    r = report(host)
    rv = negative_review(r)
    rv['files'][0]['patterns']['M']['disposition'] = 'unresolved'
    result = conclude(host, r, rv)
    assert result['outcome'] == 'insufficient_evidence'
    assert result['coverage']['unresolved_pattern_reviews'] == 1
    assert result['pending']['opinions'] == [{'target_kind': 'file', 'target': 'opaque.py', 'pattern': 'M'}]


@pytest.mark.parametrize('suffix,text', [
    ('bad.py', 'def not valid syntax'),
    ('code.ts', 'export const x = 3;'),
    ('code.rs', 'fn main() {}'),
    ('hint.pyi', 'def g() -> int: ...'),
])
def test_unparsed_source_cannot_become_absence(host, suffix, text):
    (host / suffix).write_text(text, encoding='utf-8')
    r = report(host)
    result = conclude(host, r, negative_review(r))
    assert result['outcome'] == 'incomplete_analysis'
    assert result['coverage']['analysis_complete_within_policy'] is False


def test_no_definitions_is_distinct_from_negative_review(host):
    (host / 'opaque.py').write_text('FIXED_SETTING = 17\n')
    r = report(host)
    assert conclude(host, r)['outcome'] == 'no_candidates_discovered'
    assert conclude(host, r, negative_review(r))['outcome'] == 'no_useful_placement'


def test_empty_repository_cannot_use_vacuous_review(host):
    (host / 'opaque.py').unlink()
    r = report(host)
    result = conclude(host, r, negative_review(r))
    assert result['outcome'] == 'no_candidates_discovered'


def test_positive_supported_seam_never_claims_wiring_or_benefit(host):
    r = report(host)
    rv = negative_review(r)
    seam = next(s for s in rv['seams'] if s['source']['qualified_symbol'] == 'z9')
    rv['files'][0]['patterns']['C']['disposition'] = 'potentially_useful'
    seam['patterns']['C']['disposition'] = 'potentially_useful'
    result = conclude(host, r, rv)
    assert result['outcome'] == 'useful_placements_identified'
    assert any(f['implementation_support'] == 'preflight_only' for f in result['findings'])
    assert result['benefit'] is None
    assert result['implementation_verified'] is False
    assert not any(result['authorization'].values())


def test_useful_unsupported_shape_is_not_no_useful(host):
    (host / 'opaque.py').write_text('async def z9(q):\n    return await q()\n')
    r = report(host)
    rv = negative_review(r)
    rv['files'][0]['patterns']['C']['disposition'] = 'potentially_useful'
    rv['seams'][0]['patterns']['C']['disposition'] = 'potentially_useful'
    result = conclude(host, r, rv)
    assert result['outcome'] == 'unsupported_or_unresolved'
    assert any(f['implementation_support'] == 'unsupported_or_unresolved' for f in result['findings'])


def test_file_level_unrecognized_placement_is_not_lost(host):
    (host / 'opaque.py').write_text('FIXED_SETTING = 17\n')
    r = report(host)
    rv = negative_review(r)
    rv['files'][0]['patterns']['M']['disposition'] = 'potentially_useful'
    result = conclude(host, r, rv)
    assert result['outcome'] == 'unsupported_or_unresolved'
    assert result['findings'] == [{'target_kind': 'file', 'target': 'opaque.py',
                                   'pattern': 'M', 'implementation_support': 'not_established'}]


@pytest.mark.parametrize('kind', ['files', 'seams'])
def test_duplicate_rows_are_rejected_not_counted_twice(host, kind):
    r = report(host)
    rv = negative_review(r)
    rv[kind].append(copy.deepcopy(rv[kind][0]))
    with pytest.raises(cap.CapabilityError, match='duplicate_.*_review'):
        conclude(host, r, rv)


@pytest.mark.parametrize('field', ['report_sha256', 'conclusion_engine_sha256',
                                  'settings_sha256', 'objective_sha256'])
def test_forged_review_identity_rejected(host, field):
    r = report(host)
    rv = negative_review(r)
    rv[field] = '0' * 64
    with pytest.raises(cap.CapabilityError, match='stale_repository_coverage_review'):
        conclude(host, r, rv)


def test_source_drift_invalidates_all_reviews(host):
    r = report(host)
    rv = negative_review(r)
    with (host / 'opaque.py').open('a') as f:
        f.write('\nCHANGED = True\n')
    with pytest.raises(cap.CapabilityError, match='stale_or_tampered_capability_report'):
        conclude(host, r, rv)


def test_file_mode_drift_invalidates_review(host):
    r = report(host)
    rv = negative_review(r)
    p = host / 'opaque.py'
    p.chmod(0o700)
    with pytest.raises(cap.CapabilityError, match='stale_or_tampered_capability_report'):
        conclude(host, r, rv)


@pytest.mark.parametrize('location', ['root', 'file', 'opinion'])
def test_review_cannot_carry_authority_or_commands(host, location):
    r = report(host)
    rv = negative_review(r)
    dest = rv if location == 'root' else rv['files'][0] if location == 'file' else rv['files'][0]['patterns']['A']
    dest['execution_authorized'] = True
    with pytest.raises(cap.CapabilityError, match='invalid_repository_coverage_review_v1'):
        conclude(host, r, rv)


def test_review_cannot_waive_deterministic_exclusion(host):
    (host / 'opaque.py').write_text('def z9(q):\n    return abs(q)\n')
    r = report(host)
    rv = negative_review(r)
    rv['files'][0]['patterns']['C']['disposition'] = 'potentially_useful'
    rv['seams'][0]['patterns']['C']['disposition'] = 'potentially_useful'
    with pytest.raises(cap.CapabilityError, match='mandatory_eligibility_exclusion'):
        conclude(host, r, rv)


def test_review_cannot_waive_external_hard_real_time_policy(host):
    policy = cap.DiscoveryPolicy(max_file_bytes=1000000, hard_real_time=('opaque.py::z9',))
    r = report(host, policy)
    rv = negative_review(r, policy)
    rv['files'][0]['patterns']['C']['disposition'] = 'potentially_useful'
    next(s for s in rv['seams'] if s['source']['qualified_symbol'] == 'z9')['patterns']['C']['disposition'] = 'potentially_useful'
    with pytest.raises(cap.CapabilityError, match='mandatory_eligibility_exclusion'):
        conclude(host, r, rv, policy=policy)


def test_conflicting_file_and_seam_claims_rejected(host):
    r = report(host)
    rv = negative_review(r)
    next(s for s in rv['seams'] if s['source']['qualified_symbol'] == 'z9')['patterns']['C']['disposition'] = 'potentially_useful'
    with pytest.raises(cap.CapabilityError, match='inconsistent_file_and_seam_review'):
        conclude(host, r, rv)


def test_target_is_not_imported_even_with_top_level_effect(host, tmp_path):
    marker = tmp_path / 'must-not-exist'
    p = host / 'opaque.py'
    p.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n' + p.read_text())
    r = report(host)
    conclude(host, r, negative_review(r))
    assert not marker.exists()


def test_source_scope_exclusions_remain_disclosed(host):
    (host / '.env').write_text('not-a-real-secret=synthetic\n')
    r = report(host)
    result = conclude(host, r, negative_review(r))
    assert result['outcome'] == 'no_useful_placement'
    assert result['scope']['excluded_entries'] == 1
    assert result['scope']['global_absence_proven'] is False


def test_review_schedule_does_not_invent_answers(host):
    schedule = coverage_review_schedule(report(host), DEFAULT)
    assert schedule['semantic_review'] == 'not_performed'
    assert schedule['source_revalidated'] is False
    assert 'reviewer' not in schedule
    assert all('patterns' not in row for row in schedule['files'] + schedule['seams'])


def test_new_schemas_are_identical_and_strict():
    import jsonschema
    root = Path(__file__).resolve().parents[1]
    for name in [CONCLUSION_CONTRACT, REVIEW_CONTRACT]:
        a = root / 'schemas' / (name + '.schema.json')
        b = root / 'jev_integration_evaluator/data' / (name + '.schema.json')
        assert a.read_bytes() == b.read_bytes()
        schema = json.loads(a.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema['additionalProperties'] is False


@pytest.mark.parametrize('field', ['report_sha256', 'settings_sha256', 'objective_sha256', 'conclusion_engine_sha256'])
def test_all_review_context_fields_bound(host, field):
    r = report(host); rv = negative_review(r)
    rv[field] = '0' * 64
    with pytest.raises(cap.CapabilityError, match='stale_repository_coverage_review'):
        conclude(host, r, rv)


@pytest.mark.parametrize('field,value', [('mode', 0), ('start_line', 0), ('end_line', 0),
                                         ('file_sha256', '0' * 64)])
def test_every_file_anchor_component_checked(host, field, value):
    r = report(host); rv = negative_review(r)
    rv['files'][0][field] = value
    with pytest.raises(cap.CapabilityError, match='file_review_anchor_mismatch'):
        conclude(host, r, rv)


@pytest.mark.parametrize('field,value', [('qualified_symbol', 'invented'), ('start_line', 99),
                                         ('end_line', 99), ('ast_sha256', '0' * 64)])
def test_every_seam_anchor_component_checked(host, field, value):
    r = report(host); rv = negative_review(r)
    rv['seams'][0]['source'][field] = value
    with pytest.raises(cap.CapabilityError, match='seam_review_anchor_mismatch'):
        conclude(host, r, rv)


@pytest.mark.parametrize('path', ['../outside.py', '/absolute.py', 'unknown.py', '.env'])
def test_unknown_or_out_of_scope_file_review_rejected(host, path):
    r = report(host); rv = negative_review(r)
    rv['files'][0]['file'] = path
    with pytest.raises(cap.CapabilityError, match='unknown_or_excluded_file_review'):
        conclude(host, r, rv)


def test_changed_objective_invalidates_old_review(host):
    r = report(host); rv = negative_review(r)
    with pytest.raises(cap.CapabilityError, match='stale_repository_coverage_review'):
        conclude(host, r, rv, objective='A different independent review objective')


def test_wrong_retained_review_digest_is_not_repaired(host):
    r = report(host); rv = negative_review(r)
    with pytest.raises(cap.CapabilityError, match='coverage_review_digest_mismatch'):
        conclude_repository(host, r, copy.deepcopy(DEFAULT), review=rv, expected_review_sha256='f'*64)


@pytest.mark.parametrize('mutate', [
    lambda rv: rv['files'][0]['patterns'].pop('M'),
    lambda rv: rv['files'][0]['patterns']['A'].update(reason='  \n\t'),
    lambda rv: rv.update(reviewer=' '),
    lambda rv: rv['files'][0]['patterns']['A'].update(disposition=True),
])
def test_strict_opinion_schedule_not_coerced_or_completed(host, mutate):
    r = report(host); rv = negative_review(r); mutate(rv)
    with pytest.raises(cap.CapabilityError):
        conclude(host, r, rv)


def test_changed_source_on_final_pass_rejects_negative_conclusion(host, monkeypatch):
    r = report(host); rv = negative_review(r)
    actual = cap.discover_repository
    calls = []
    def raced(repo, policy):
        calls.append(1)
        if len(calls) == 2:
            (host / 'added.py').write_text('answer = 42\n')
        return actual(repo, policy)
    monkeypatch.setattr(cap, 'discover_repository', raced)
    with pytest.raises(cap.CapabilityError, match='source_changed_during_repository_conclusion'):
        conclude(host, r, rv)


def test_changed_engine_on_final_pass_rejects_negative_conclusion(host, monkeypatch):
    import jev_integration_evaluator.repository_conclusion as module
    r = report(host); rv = negative_review(r)
    old = module.conclusion_engine_identity(); calls = []
    def raced():
        calls.append(1)
        return old if len(calls) == 1 else 'f' * 64
    monkeypatch.setattr(module, 'conclusion_engine_identity', raced)
    with pytest.raises(cap.CapabilityError, match='conclusion_engine_changed_during_review'):
        conclude(host, r, rv)


@pytest.mark.parametrize('bound,value', [('max_files', 1), ('max_file_bytes', 1),
                                         ('max_total_bytes', 1), ('max_symbols', 1)])
def test_resource_truncation_cannot_be_negative_absence(host, bound, value):
    from dataclasses import replace
    # Two real source files ensure max_files is exercised rather than assumed.
    (host / 'second.py').write_text('def b2(q):\n    return q.get("other")\n')
    from jev_integration_evaluator.nomination_inventory import _settings
    policy = replace(_settings(copy.deepcopy(DEFAULT), None)[1], **{bound: value})
    r = report(host, policy)
    rv = negative_review(r, policy)
    result = conclude(host, r, rv, policy=policy)
    assert result['outcome'] == 'incomplete_analysis'
    assert not result['coverage']['analysis_complete_within_policy']


def test_self_consistent_tampered_report_still_rejected(host):
    r = report(host)
    r['files'][0]['sha256'] = '0' * 64
    r['report_sha256'] = cap._digest({k: v for k, v in r.items() if k != 'report_sha256'})
    with pytest.raises(cap.CapabilityError, match='stale_or_tampered_capability_report'):
        conclude(host, r)


def test_byte_budget_checks_before_untrusted_review_parsing(host, monkeypatch):
    import jev_integration_evaluator.repository_conclusion as module
    r = report(host); rv = negative_review(r)
    monkeypatch.setattr(module, 'MAX_RECORD_BYTES', 16)
    with pytest.raises(cap.CapabilityError, match='repository_conclusion_byte_bound'):
        conclude(host, r, rv)
