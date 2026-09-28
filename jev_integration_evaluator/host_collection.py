"""Bounded paired host adapter orchestration; no adapter or egress is installed here.

The caller owns the adapter, input lookup, external approval and durable host
receipts. This module only invokes an explicitly supplied adapter for exact
scheduled pairs. It never calls a provider itself or promotes observations.
"""
from __future__ import annotations

import math
from typing import Protocol

from .contracts import seal, validate_contract, verify
from .io import InputError, digest
from .observed_evidence import _outcome_row, check_link


class PairedHostAdapter(Protocol):
    """Host-owned atomic pair adapter; implementation lives outside this package.

    `run_pair` must durably account for both attempts, including partial failure,
    before returning. An exception leaves the pair unresolved and forbids retry
    under this request. The host must enforce the per-call cost and egress scope.
    """

    adapter_id: str
    contract_digest: str
    host_scope_digest: str

    def run_pair(self, *, task_id: str, replicate: int, task_hash: str,
                 input_sha256: str, link_digest: str, max_pair_cost: float,
                 egress_grant_sha256: str | None) -> dict: ...


def collect_host_pairs(link: dict, study: dict, request: dict,
                       input_manifest: list[dict], labels: list[dict], adapter: PairedHostAdapter, *,
                       approved_request_sha256: str, expected_link_digest: str,
                       root, bundle, placement_set: dict,
                       trusted_implementation_receipt_sha256: str,
                       trusted_egress_grant_sha256: str | None = None,
                       monitor_plan: dict | None = None) -> dict:
    """Invoke one supplied host-owned adapter at most once per scheduled pair.

    Only a synthetic adapter is exercised by repository tests. An observed
    request requires an independently retained exact egress grant and remains
    unverified-origin evidence until its host receipts are authenticated.
    """
    validate_contract(link, 'observed-link')
    verify(link, expected=expected_link_digest)
    check_link(root, bundle, study, placement_set, link,
        expected_link_digest=expected_link_digest,
        trusted_implementation_receipt_sha256=trusted_implementation_receipt_sha256,
        monitor_plan=monitor_plan)
    validate_contract(study, 'study')
    verify(study, expected=link['study_digest'])
    validate_contract(request, 'observed-host-collection-request')
    if (type(input_manifest) is not list or type(labels) is not list
            or len(input_manifest) > 100000 or len(labels) > 100000
            or request['link_digest'] != link['contract_digest']
            or request['study_digest'] != study['contract_digest']
            or request['input_manifest_sha256'] != digest(input_manifest)
            or request['labels_sha256'] != digest(labels)
            or digest(request) != approved_request_sha256):
        raise InputError('Exact externally approved host collection request required')
    for field in ('adapter_id', 'contract_digest', 'host_scope_digest'):
        if getattr(adapter, field, None) != request[field]:
            raise InputError('Host adapter differs from approved identity or scope')
    evidence = study['specification']['evidence_type']
    if evidence != request['evidence_type']:
        raise InputError('Host request evidence type differs from frozen study')
    grant = request['egress_grant_sha256']
    if (evidence == 'observed' and grant is not None and
            trusted_egress_grant_sha256 is not None and grant != trusted_egress_grant_sha256):
        raise InputError('Observed egress grant differs from approved scope')
    if evidence == 'synthetic' and (grant is not None or trusted_egress_grant_sha256 is not None):
        raise InputError('Synthetic host collection cannot receive egress authority')
    scheduled_rows = [r for r in study['specification']['schedule'] if r['split'] == 'test']
    schedule = {(r['task_id'], r['replicate']): r for r in scheduled_rows}
    if not schedule or len(schedule) != len(scheduled_rows):
        raise InputError('Frozen host test schedule is empty or duplicates a pair')
    bounds = ('max_pairs', 'max_pair_calls', 'max_pair_cost', 'max_total_cost', 'stop_after_failures')
    unknown_bounds = any(request[k] is None for k in bounds)
    if any(request[k] is not None and type(request[k]) is not int
           for k in ('max_pairs', 'max_pair_calls', 'stop_after_failures')):
        raise InputError('Host call bounds must be exact positive integers')
    if any(request[k] is not None and (type(request[k]) not in (int, float)
           or not math.isfinite(request[k])) for k in ('max_pair_cost', 'max_total_cost')):
        raise InputError('Host cost bounds must be finite')
    insufficient = not unknown_bounds and (
        request['max_pairs'] < len(schedule) or request['max_pair_calls'] < len(schedule)
        or request['max_total_cost'] < len(schedule) * request['max_pair_cost'])
    inputs = {}
    for row in input_manifest:
        if (type(row) is not dict or set(row) != {'task_id', 'replicate', 'task_hash', 'input_sha256'}
                or type(row['input_sha256']) is not str or len(row['input_sha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['input_sha256'])):
            raise InputError('Invalid host input manifest identity')
        key = (row['task_id'], row['replicate'])
        if key in inputs or key not in schedule or row['task_hash'] != schedule[key]['task_hash']:
            raise InputError('Host input differs from frozen schedule')
        inputs[key] = row
    label_index = {}
    for row in labels:
        if (type(row) is not dict or set(row) !=
                {'task_id', 'replicate', 'task_hash', 'expected_label', 'reviewer', 'source_sha256'}
                or type(row['expected_label']) is not str or not row['expected_label']
                or type(row['reviewer']) is not str or not row['reviewer']
                or type(row['source_sha256']) is not str or len(row['source_sha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['source_sha256'])):
            raise InputError('Independent host outcome label required')
        key = (row['task_id'], row['replicate'])
        if key in label_index or key not in schedule or row['task_hash'] != schedule[key]['task_hash']:
            raise InputError('Host label differs from frozen schedule')
        label_index[key] = row
    def empty_report(status):
        report = seal({'schema_version': '1.0', 'kind': 'host_paired_collection',
            'link_digest': link['contract_digest'], 'study_digest': study['contract_digest'],
            'request_sha256': approved_request_sha256,
            'input_manifest_sha256': digest(input_manifest), 'labels_sha256': digest(labels),
            'adapter_id': request['adapter_id'], 'adapter_contract_digest': request['contract_digest'],
            'host_scope_digest': request['host_scope_digest'], 'egress_grant_sha256': grant,
            'status': status, 'evidence_type': evidence, 'scheduled_pairs': len(schedule),
            'collected_pairs': 0,
            'missing_pairs': [{'task_id': k[0], 'replicate': k[1]} for k in sorted(schedule)],
            'baseline': [], 'jev': [], 'host_pair_calls': 0, 'recorded_cost': 0,
            'receipt_hashes': [], 'independent_label_count': len(label_index),
            'provider_connectivity': 'not_established', 'benefit_supported': False,
            'activation_eligible': False})
        validate_contract(report, 'observed-host-collection')
        return report
    if evidence == 'observed' and (grant is None or trusted_egress_grant_sha256 is None):
        return empty_report('incomplete_egress_scope')
    if unknown_bounds:
        return empty_report('incomplete_unknown_budget')
    if insufficient:
        return empty_report('incomplete_bound_insufficient')
    baseline, jev, missing, receipts = [], [], [], []
    calls, failures, spent, unresolved = 0, 0, 0.0, False
    for key in sorted(schedule):
        if (unresolved or key not in inputs or key not in label_index
                or failures >= request['stop_after_failures']
                or calls >= request['max_pair_calls']
                or spent + request['max_pair_cost'] > request['max_total_cost']):
            missing.append({'task_id': key[0], 'replicate': key[1]})
            continue
        calls += 1  # Reserve before any host effect; never retry after exception.
        try:
            result = adapter.run_pair(task_id=key[0], replicate=key[1],
                task_hash=schedule[key]['task_hash'], input_sha256=inputs[key]['input_sha256'],
                link_digest=link['contract_digest'], max_pair_cost=request['max_pair_cost'],
                egress_grant_sha256=grant)
            # A host effect can change the very source or environment being studied.
            # Recheck before accepting the pair or invoking another one.
            check_link(root, bundle, study, placement_set, link,
                expected_link_digest=expected_link_digest,
                trusted_implementation_receipt_sha256=trusted_implementation_receipt_sha256,
                monitor_plan=monitor_plan)
            if (type(result) is not dict or set(result) != {'baseline', 'jev', 'receipt_sha256'}
                    or type(result['receipt_sha256']) is not str or len(result['receipt_sha256']) != 64
                    or any(c not in '0123456789abcdef' for c in result['receipt_sha256'])):
                raise InputError('Host pair lacks exact outcome and durable receipt identity')
            b = _outcome_row(study, schedule[key], 'baseline', result['baseline'], label_index[key],
                             evidence_type=evidence)
            j = _outcome_row(study, schedule[key], 'jev', result['jev'], label_index[key],
                             evidence_type=evidence)
            pair_cost = b['cost'] + j['cost']
            if not math.isfinite(pair_cost) or pair_cost > request['max_pair_cost']:
                raise InputError('Host pair exceeded reserved cost bound')
        except Exception:
            unresolved = True
            missing.append({'task_id': key[0], 'replicate': key[1]})
            continue
        spent += pair_cost
        failures += int(b['run_status'] != 'completed' or j['run_status'] != 'completed')
        baseline.append(b)
        jev.append(j)
        receipts.append({'task_id': key[0], 'replicate': key[1],
                         'receipt_sha256': result['receipt_sha256']})
    status = ('incomplete_unresolved_host_attempt' if unresolved else
              'incomplete_scheduled_outcomes' if missing else
              'synthetic_complete' if evidence == 'synthetic' else
              'observed_collected_unverified_origin')
    report = seal({'schema_version': '1.0', 'kind': 'host_paired_collection',
        'link_digest': link['contract_digest'], 'study_digest': study['contract_digest'],
        'request_sha256': approved_request_sha256,
        'input_manifest_sha256': digest(input_manifest), 'labels_sha256': digest(labels),
        'adapter_id': request['adapter_id'], 'adapter_contract_digest': request['contract_digest'],
        'host_scope_digest': request['host_scope_digest'], 'egress_grant_sha256': grant,
        'status': status, 'evidence_type': evidence, 'scheduled_pairs': len(schedule),
        'collected_pairs': len(baseline), 'missing_pairs': missing,
        'baseline': baseline, 'jev': jev, 'host_pair_calls': calls,
        'recorded_cost': None if unresolved else spent,
        'receipt_hashes': receipts, 'independent_label_count': len(label_index),
        'provider_connectivity': 'not_established', 'benefit_supported': False,
        'activation_eligible': False})
    validate_contract(report, 'observed-host-collection')
    check_link(root, bundle, study, placement_set, link,
        expected_link_digest=expected_link_digest,
        trusted_implementation_receipt_sha256=trusted_implementation_receipt_sha256,
        monitor_plan=monitor_plan)
    return report
