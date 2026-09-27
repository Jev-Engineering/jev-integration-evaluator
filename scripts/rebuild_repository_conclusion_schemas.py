"""Rebuild only the versioned repository-conclusion contract schema pair."""
from __future__ import annotations
import json
from pathlib import Path


def schemas() -> dict[str, dict]:
    def text(maximum=1024, minimum=1):
        return {'type': 'string', 'minLength': minimum, 'maxLength': maximum}
    def count(maximum=10000):
        return {'type': 'integer', 'minimum': 0, 'maximum': maximum}
    def obj(properties, required=None):
        return {'type': 'object', 'properties': properties,
                'required': list(properties) if required is None else required,
                'additionalProperties': False}
    def array(items, maximum=10000):
        return {'type': 'array', 'items': items, 'maxItems': maximum}
    def const(value):
        return {'const': value}
    sha = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    nullable_sha = {'anyOf': [sha, {'type': 'null'}]}
    boolean = {'type': 'boolean'}
    source = obj({'file': text(), 'qualified_symbol': text(),
                  'start_line': {'type': 'integer', 'minimum': 1, 'maximum': 10000000},
                  'end_line': {'type': 'integer', 'minimum': 1, 'maximum': 10000000},
                  'file_sha256': sha, 'ast_sha256': sha})
    opinion = obj({
        'disposition': {'enum': ['not_useful', 'potentially_useful', 'unresolved']},
        'reason': {**text(2048), 'pattern': r'\S'},
    })
    patterns = obj({p: opinion for p in 'ABCDEFGHIJKLM'})
    file = obj({'file': text(), 'file_sha256': sha, 'mode': count(4095),
                'start_line': count(4194304), 'end_line': count(4194304),
                'patterns': patterns})
    seam = obj({'seam_id': sha, 'source': source, 'patterns': patterns})
    pending_opinion = obj({'target_kind': {'enum': ['file', 'seam']},
                           'target': text(), 'pattern': {'enum': list('ABCDEFGHIJKLM')}})
    finding = obj({**pending_opinion['properties'],
                   'implementation_support': {'enum': ['not_established', 'preflight_only',
                                                       'unsupported_or_unresolved']}})
    coverage = obj({'analysis_complete_within_policy': boolean,
                    'expected_file_reviews': count(), 'received_file_reviews': count(),
                    'expected_seam_reviews': count(), 'received_seam_reviews': count(),
                    'unresolved_pattern_reviews': count(260000),
                    'complete_anchored_review': boolean})
    base = {'schema_version': const('1.0')}
    review_name = 'repository-coverage-review-v1'
    conclusion_name = 'repository-conclusion-v1'
    review = obj({**base, 'contract': const(review_name),
                  'report_sha256': sha, 'conclusion_engine_sha256': sha,
                  'settings_sha256': sha, 'objective_sha256': sha,
                  'reviewer': {**text(256), 'pattern': r'\S'},
                  'files': array(file), 'seams': array(seam)})
    result = obj({**base, 'contract': const(conclusion_name),
                  'report_sha256': sha, 'conclusion_engine_sha256': sha,
                  'settings_sha256': sha, 'objective_sha256': sha,
                  'review_sha256': nullable_sha,
                  'reviewer_claim': {'anyOf': [text(256), {'type': 'null'}]},
                  'review_anchor_matched': boolean,
                  'review_principal_authenticated': const(False),
                  'scope': obj({
                      'snapshot_scope': const('bounded_source_and_configuration_not_full_repository'),
                      'snapshot_sha256': sha, 'policy_sha256': sha,
                      'excluded_entries': count(100000), 'global_absence_proven': const(False)}),
                  'outcome': {'enum': ['incomplete_analysis', 'no_candidates_discovered',
                                       'review_required', 'insufficient_evidence',
                                       'unsupported_or_unresolved', 'useful_placements_identified',
                                       'no_useful_placement']},
                  'discovery_outcome': {'enum': ['incomplete_analysis', 'no_candidates_discovered',
                                                'deterministic_rejection', 'unsupported_or_unresolved',
                                                'review_required']},
                  'coverage': coverage,
                  'pending': obj({'files': array(text()), 'seams': array(sha),
                                  'opinions': array(pending_opinion, 260000)}),
                  'findings': array(finding, 260000),
                  'next_actions': array({'enum': [
                      'resolve_coverage_limitations_and_rescan',
                      'confirm_source_scope_and_supported_file_types',
                      'obtain_source_bound_file_and_seam_reviews',
                      'complete_unresolved_review_schedule',
                      'supply_independently_retained_review_digest',
                      'obtain_separate_semantic_candidate_and_binding_decisions',
                      'retain_scoped_review_without_claiming_global_absence_or_benefit']}, 4),
                  'binding_review': const('not_performed'),
                  'implementation_verified': const(False), 'benefit': {'type': 'null'},
                  'authorization': obj({key: const(False) for key in
                                        ['execution', 'mutation', 'egress', 'activation']}),
                  'conclusion_sha256': sha})
    # Shape-only validators must also reject the most serious false completion
    # combinations. Fresh-source validation is still exclusively the API/CLI.
    result['allOf'] = [
        {'if': {'properties': {'outcome': const('no_useful_placement')}},
         'then': {'properties': {
             'review_anchor_matched': const(True),
             'review_sha256': sha,
             'reviewer_claim': {**text(256), 'pattern': r'\S'},
             'coverage': {'properties': {
                 'analysis_complete_within_policy': const(True),
                 'complete_anchored_review': const(True),
                 'expected_file_reviews': {'minimum': 1},
                 'unresolved_pattern_reviews': const(0)}},
             'pending': {'properties': {key: {'maxItems': 0}
                                        for key in ['files', 'seams', 'opinions']}},
             'findings': {'maxItems': 0}}}},
    ]
    return {name: {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                   '$id': 'urn:jev-integration-evaluator:' + name,
                   'title': name, **body}
            for name, body in [(review_name, review), (conclusion_name, result)]}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for name, value in schemas().items():
        raw = (json.dumps(value, indent=2) + '\n').encode('utf-8')
        for directory in (root / 'schemas', root / 'jev_integration_evaluator' / 'data'):
            (directory / (name + '.schema.json')).write_bytes(raw)


if __name__ == '__main__':
    main()
