"""Source-bound, scope-complete semantic conclusions; never implementation authority.

A negative opinion on one nominated candidate is not an absence result. This
contract requires a complete A--M review of every discovered file and seam,
including file-level behavior not represented by a discovered function. Even a
complete conclusion is about the stated bounded snapshot and objective, not an
absence proof for unparsed/excluded source, dependencies, or every possible goal.

Reviewer names and digests are not authentication. The caller must authenticate
the review and retain its digest through a trusted channel outside the records.
No provider, target import, shell command, mutation, or activation runs here.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from . import capabilities as cap
from .nomination_inventory import MAX_RECORD_BYTES, _settings

REVIEW_CONTRACT = 'repository-coverage-review-v1'
CONCLUSION_CONTRACT = 'repository-conclusion-v1'
PATTERNS = tuple('ABCDEFGHIJKLM')
DEFAULT_OBJECTIVE = (
    'Identify source-supported A-M placement hypotheses; do not infer measured '
    'benefit, implementation support, missing host capabilities, or authority.'
)


def _bounded_copy(value: Any) -> Any:
    raw = cap._json(value)
    if len(raw) > MAX_RECORD_BYTES:
        raise cap.CapabilityError('repository_conclusion_byte_bound')
    return json.loads(raw)


def conclusion_engine_identity() -> str:
    """Bind the code/configuration and all schemas used by this contract."""
    package = Path(__file__).parent
    names = ('repository_conclusion', 'nomination_inventory', 'capabilities',
             'repository_discovery', 'config', 'contracts', 'io', '__init__')
    schemas = (REVIEW_CONTRACT, CONCLUSION_CONTRACT, 'repository-capabilities',
               'candidate-nomination', 'admitted-nomination')
    return cap._digest({
        'modules': {name: hashlib.sha256((package / (name + '.py')).read_bytes()).hexdigest()
                    for name in names},
        'schemas': {name: hashlib.sha256((package / 'data' / (name + '.schema.json')).read_bytes()).hexdigest()
                    for name in schemas},
    })


def _by_unique(rows: list[dict], key: str, reason: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        if row[key] in result:
            raise cap.CapabilityError(reason)
        result[row[key]] = row
    return result


def _file_anchor(record: dict) -> dict:
    return {
        'file': record['file'], 'file_sha256': record['sha256'],
        'mode': record['mode'],
        'start_line': 1 if record['line_count'] else 0,
        'end_line': record['line_count'],
    }


def _review_rows(review: dict, fresh: dict, settings_sha256: str,
                 objective_sha256: str, engine: str) -> tuple[dict, dict]:
    cap._schema(REVIEW_CONTRACT, review)
    expected = {
        'report_sha256': fresh['report_sha256'],
        'settings_sha256': settings_sha256,
        'objective_sha256': objective_sha256,
        'conclusion_engine_sha256': engine,
    }
    if any(review[key] != value for key, value in expected.items()):
        raise cap.CapabilityError('stale_repository_coverage_review')
    files = _by_unique(review['files'], 'file', 'duplicate_file_review')
    seams = _by_unique(review['seams'], 'seam_id', 'duplicate_seam_review')
    source_files = {row['file']: row for row in fresh['files']}
    source_seams = {row['seam_id']: row for row in fresh['seams']}
    for path, row in files.items():
        if path not in source_files or not cap._safe_rel(path):
            raise cap.CapabilityError('unknown_or_excluded_file_review')
        anchor = _file_anchor(source_files[path])
        if any(row[key] != value for key, value in anchor.items()):
            raise cap.CapabilityError('file_review_anchor_mismatch')
    for seam_id, row in seams.items():
        if seam_id not in source_seams:
            raise cap.CapabilityError('unknown_or_excluded_seam_review')
        seam = source_seams[seam_id]
        if row['source'] != seam['source']:
            raise cap.CapabilityError('seam_review_anchor_mismatch')
        parent = files.get(seam['source']['file'])
        for pattern, opinion in row['patterns'].items():
            if opinion['disposition'] != 'potentially_useful':
                continue
            if seam['eligibility'] == 'ineligible':
                raise cap.CapabilityError('mandatory_eligibility_exclusion')
            if parent and parent['patterns'][pattern]['disposition'] == 'not_useful':
                raise cap.CapabilityError('inconsistent_file_and_seam_review')
    return files, seams


def _finding(kind: str, target: str, pattern: str, support: str) -> dict:
    return {'target_kind': kind, 'target': target, 'pattern': pattern,
            'implementation_support': support}


def conclude_repository(repo: str | Path, report: dict, cfg: dict, *,
                        objective: str | None = None,
                        review: dict | None = None,
                        expected_review_sha256: str | None = None,
                        policy: cap.DiscoveryPolicy | None = None) -> dict:
    """Re-read the repository and compute a bounded, non-authoritative conclusion.

    Missing rows and unresolved opinions are retained in the denominator. A
    valid but incomplete review is useful resumable input, not an absence proof.
    Unknown fields, duplicate rows, false source anchors, contradictory opinions,
    and attempts to override mandatory eligibility are rejected, not repaired.

    ``expected_review_sha256`` is supplied independently by the authenticated
    caller. Reading that value out of the same untrusted review is insufficient.
    This function checks a digest match; it cannot authenticate that caller.
    """
    report = _bounded_copy(report)
    settings, effective_policy = _settings(cfg, policy)
    if objective is None:
        objective = DEFAULT_OBJECTIVE
    if type(objective) is not str or not objective.strip() or len(objective) > 4096:
        raise cap.CapabilityError('invalid_repository_objective')
    if expected_review_sha256 is not None and (
            type(expected_review_sha256) is not str
            or not cap.HEX.fullmatch(expected_review_sha256)):
        raise cap.CapabilityError('invalid_coverage_review_anchor')
    if review is None and expected_review_sha256 is not None:
        raise cap.CapabilityError('coverage_review_required_for_anchor')
    engine = conclusion_engine_identity()
    settings_sha256 = cap._digest(settings)
    objective_sha256 = cap._digest(objective)
    fresh = cap.discover_repository(repo, effective_policy)
    if cap._json(fresh) != cap._json(report):
        raise cap.CapabilityError('stale_or_tampered_capability_report')

    file_reviews, seam_reviews = {}, {}
    review_sha256 = None
    reviewer = None
    anchor_matched = False
    if review is not None:
        review = _bounded_copy(review)
        file_reviews, seam_reviews = _review_rows(
            review, fresh, settings_sha256, objective_sha256, engine)
        review_sha256 = cap._digest(review)
        reviewer = review['reviewer']
        if expected_review_sha256 is not None:
            if review_sha256 != expected_review_sha256:
                raise cap.CapabilityError('coverage_review_digest_mismatch')
            anchor_matched = True

    missing_files = [f['file'] for f in fresh['files'] if f['file'] not in file_reviews]
    missing_seams = [s['seam_id'] for s in fresh['seams'] if s['seam_id'] not in seam_reviews]
    unresolved = 13 * (len(missing_files) + len(missing_seams))
    findings = []
    unresolved_targets = []
    for row in file_reviews.values():
        for pattern, opinion in row['patterns'].items():
            if opinion['disposition'] == 'unresolved':
                unresolved += 1
                unresolved_targets.append({'target_kind': 'file', 'target': row['file'],
                                           'pattern': pattern})
            elif opinion['disposition'] == 'potentially_useful':
                # A file-level opinion can identify an unrecognized placement;
                # it does not establish a supported source transformation.
                findings.append(_finding('file', row['file'], pattern, 'not_established'))
    source_seams = {row['seam_id']: row for row in fresh['seams']}
    for seam_id, row in seam_reviews.items():
        seam = source_seams[seam_id]
        for pattern, opinion in row['patterns'].items():
            if opinion['disposition'] == 'unresolved':
                unresolved += 1
                unresolved_targets.append({'target_kind': 'seam', 'target': seam_id,
                                           'pattern': pattern})
            elif opinion['disposition'] == 'potentially_useful':
                support = ('preflight_only' if seam['shape'] == 'module-tail-call-v1-preflight'
                           and 'ambiguous_symbol' not in seam['reasons']
                           else 'unsupported_or_unresolved')
                findings.append(_finding('seam', seam_id, pattern, support))
    complete_review = bool(review is not None and not missing_files and not missing_seams
                           and not unresolved and anchor_matched)
    complete_analysis = fresh['coverage']['complete_within_policy']
    if not complete_analysis:
        outcome = 'incomplete_analysis'
        actions = ['resolve_coverage_limitations_and_rescan']
    elif not fresh['files']:
        # A vacuous empty review is not a semantic result about a repository.
        outcome = 'no_candidates_discovered'
        actions = ['confirm_source_scope_and_supported_file_types']
    elif review is None:
        outcome = ('no_candidates_discovered' if not fresh['seams']
                   else 'unsupported_or_unresolved' if fresh['discovery_outcome'] == 'unsupported_or_unresolved'
                   else 'review_required')
        actions = ['obtain_source_bound_file_and_seam_reviews']
    elif not complete_review:
        outcome = 'insufficient_evidence'
        actions = []
        if missing_files or missing_seams or unresolved:
            actions.append('complete_unresolved_review_schedule')
        if not anchor_matched:
            actions.append('supply_independently_retained_review_digest')
    elif findings:
        outcome = ('useful_placements_identified' if any(
            f['implementation_support'] == 'preflight_only' for f in findings)
                   else 'unsupported_or_unresolved')
        actions = ['obtain_separate_semantic_candidate_and_binding_decisions']
    else:
        outcome = 'no_useful_placement'
        actions = ['retain_scoped_review_without_claiming_global_absence_or_benefit']

    result = {
        'schema_version': '1.0', 'contract': CONCLUSION_CONTRACT,
        'report_sha256': fresh['report_sha256'],
        'conclusion_engine_sha256': engine,
        'settings_sha256': settings_sha256, 'objective_sha256': objective_sha256,
        'review_sha256': review_sha256, 'reviewer_claim': reviewer,
        'review_anchor_matched': anchor_matched, 'review_principal_authenticated': False,
        'scope': {
            'snapshot_scope': fresh['snapshot_scope'],
            'snapshot_sha256': fresh['snapshot_sha256'],
            'policy_sha256': cap._digest(fresh['policy']),
            'excluded_entries': fresh['coverage']['excluded_entries'],
            'global_absence_proven': False,
        },
        'outcome': outcome, 'discovery_outcome': fresh['discovery_outcome'],
        'coverage': {
            'analysis_complete_within_policy': complete_analysis,
            'expected_file_reviews': len(fresh['files']),
            'received_file_reviews': len(file_reviews),
            'expected_seam_reviews': len(fresh['seams']),
            'received_seam_reviews': len(seam_reviews),
            'unresolved_pattern_reviews': unresolved,
            'complete_anchored_review': complete_review,
        },
        'pending': {'files': missing_files, 'seams': missing_seams,
                    'opinions': unresolved_targets},
        'findings': findings, 'next_actions': actions,
        'binding_review': 'not_performed', 'implementation_verified': False,
        'benefit': None,
        'authorization': {'execution': False, 'mutation': False,
                          'egress': False, 'activation': False},
    }
    # Recheck after the complete review has been evaluated, including negative
    # opinions. No historical successful scan may substitute for current bytes.
    final = cap.discover_repository(repo, effective_policy)
    if cap._json(final) != cap._json(fresh):
        raise cap.CapabilityError('source_changed_during_repository_conclusion')
    if conclusion_engine_identity() != engine:
        raise cap.CapabilityError('conclusion_engine_changed_during_review')
    result['conclusion_sha256'] = cap._digest(result)
    result = _bounded_copy(result)
    cap._schema(CONCLUSION_CONTRACT, result)
    return result


def coverage_review_schedule(report: dict, cfg: dict, *, objective: str | None = None,
                             policy: cap.DiscoveryPolicy | None = None) -> dict:
    """Describe required source anchors, without inventing any review answers.

    The schedule is preparation data, not a valid completed review. An independent
    reviewer must read the complete listed source and fill each A--M opinion.
    ``conclude_repository`` always revalidates the snapshot before using answers.
    """
    report = _bounded_copy(report)
    cap._schema('repository-capabilities', report)
    settings, _ = _settings(cfg, policy)
    if objective is None:
        objective = DEFAULT_OBJECTIVE
    if type(objective) is not str or not objective.strip() or len(objective) > 4096:
        raise cap.CapabilityError('invalid_repository_objective')
    return {
        'schema_version': '1.0', 'report_sha256': report['report_sha256'],
        'conclusion_engine_sha256': conclusion_engine_identity(),
        'settings_sha256': cap._digest(settings), 'objective_sha256': cap._digest(objective),
        'required_patterns': list(PATTERNS),
        'files': [_file_anchor(row) for row in report['files']],
        'seams': [{'seam_id': row['seam_id'], 'source': copy.deepcopy(row['source'])}
                  for row in report['seams']],
        'semantic_review': 'not_performed', 'source_revalidated': False,
    }
