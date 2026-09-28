"""Additive one-source adaptation lifecycle; never executes target code itself.

The native runner must execute the independently scheduled host before/after
the edit. An external owner authenticates plan and phase receipt digests.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import difflib

from ..implementation import make_patch_plan, apply_patch_plan
from ..contracts import validate_contract
from ..io import InputError, canonical, digest, file_hash, read_json, safe_child, write_json
from ..runners.isolated_python import RunnerError, inspect_receipt
from ..runners.observations import inspect_baseline_postconditions, inspect_lifecycle_postconditions
from .adaptation_shapes import (prepare_reviewed_shape, prepare_shape,
                                validate_adapter_callback, validate_static_adapter_import)
from .lifecycle import (_bundle_dir, _inspect_file, _journal, _lock, _record,
                        _root_identity, _sync_dir, engine_identity)


def _proof_file(spec, relative, expected, mode=None):
    rows = [row for row in spec['files'] if row['path'] == relative]
    if len(rows) != 1 or rows[0]['sha256'] != expected or (mode is not None and rows[0]['mode'] != mode):
        raise InputError('Native proof omits exact adaptation source')


def _check_native(spec, root, row, adapter_file, adapter_sha, adapter_mode):
    actual = _root_identity(root)
    if any(spec['source_identity'].get(k) != actual[k] for k in ('device', 'inode')):
        raise InputError('Native proof belongs to another source root')
    _proof_file(spec, row['file'], row['sha256'], row['mode'])
    _proof_file(spec, adapter_file, adapter_sha, adapter_mode)


def _load(root, bundle, *, current_engine=False):
    root, bundle = Path(root).resolve(strict=True), _bundle_dir(bundle)
    if bundle == root or bundle.is_relative_to(root):
        raise InputError('Adaptation bundle must remain outside target')
    if os.name == 'posix' and (stat.S_IMODE(bundle.stat().st_mode) != 0o700
                                or bundle.stat().st_uid != os.geteuid()):
        raise InputError('Unsafe adaptation bundle ownership or mode')
    for name in ('adaptation-plan.json', 'patch-plan.json', 'adaptation-request.json',
                 'reviewed-inventory.json', 'preimage.utf8'):
        path = safe_child(bundle, name)
        if (not path.is_file() or (os.name == 'posix' and
                (stat.S_IMODE(path.stat().st_mode) != 0o600 or path.stat().st_uid != os.geteuid()))):
            raise InputError('Unsafe adaptation artifact ownership or mode')
    plan = read_json(safe_child(bundle, 'adaptation-plan.json'))
    patch = read_json(safe_child(bundle, 'patch-plan.json'))
    request = read_json(safe_child(bundle, 'adaptation-request.json'))
    inventory = read_json(safe_child(bundle, 'reviewed-inventory.json'))
    validate_contract(plan, 'adaptation-plan-v1')
    validate_contract(request, 'adaptation-request-v1')
    validate_contract(patch, 'patch-plan')
    if (plan.get('kind') != 'adaptation-plan-v1' or plan.get('schema_version') != '1.0'
            or set(plan) != {'kind', 'schema_version', 'root_identity', 'engine_identity',
                             'request_sha256', 'inventory_sha256', 'patch_sha256', 'owned_file',
                             'adapter_file', 'adapter_sha256', 'adapter_mode', 'contract_digest'}
            or digest({k:v for k,v in plan.items() if k != 'contract_digest'}) != plan['contract_digest']
            or plan['root_identity'] != _root_identity(root)
            or (current_engine and plan['engine_identity'] != engine_identity())
            or plan['request_sha256'] != digest(request)
            or plan['inventory_sha256'] != digest(inventory)
            or plan['patch_sha256'] != digest(patch)
            or patch.get('plan_digest') != digest({k:v for k,v in patch.items() if k != 'plan_digest'})
            or len(patch['changes']) != 1
            or patch['changes'][0]['file'] != plan['owned_file']['file']
            or patch['changes'][0]['old_sha256'] != plan['owned_file']['old_sha256']
            or patch['changes'][0]['new_sha256'] != plan['owned_file']['new_sha256']):
        raise InputError('Adaptation bundle identity mismatch')
    preimage = safe_child(bundle, 'preimage.utf8')
    if (not preimage.is_file() or preimage.stat().st_size > 2_000_000
            or (os.name == 'posix' and stat.S_IMODE(preimage.stat().st_mode) != 0o600)
            or hashlib.sha256(preimage.read_bytes()).hexdigest() != plan['owned_file']['old_sha256']):
        raise InputError('Adaptation preimage mismatch')
    source, binding = request['source'], request['binding_review']
    matches = [candidate for candidate in inventory.get('candidates', [])
               if candidate.get('candidate_id') == request['candidate_id']]
    if (len(matches) != 1 or matches[0].get('tier') == 0
            or matches[0].get('pattern') == 'NONE'
            or matches[0].get('hard_real_time') is True
            or matches[0].get('deterministic_alternative') in ('mandatory', 'preferred')
            or any(matches[0].get('source', {}).get(k) != source[k] for k in
                   ('file','symbol','source_sha256','file_sha256'))
            or matches[0].get('semantic_review', {}).get('approved') is not True
            or not matches[0]['semantic_review'].get('reviewer')
            or not matches[0]['semantic_review'].get('reason')
            or matches[0]['semantic_review'].get('source_sha256') != source['source_sha256']
            or inventory.get('scan_fingerprint') != request['inventory_fingerprint']
            or digest(inventory.get('analysis_identity')) != request['inventory_fingerprint']
            or len([entry for entry in inventory.get('files', []) if entry.get('file') == source['file']
                    and entry.get('sha256') == source['file_sha256']]) != 1
            or len([entry for entry in inventory.get('files', []) if entry.get('file') == binding['adapter_file']
                    and entry.get('sha256') == binding['adapter_sha256']]) != 1
            or plan['owned_file']['file'] != source['file']
            or plan['owned_file']['old_sha256'] != source['file_sha256']
            or plan['adapter_file'] != binding['adapter_file']
            or plan['adapter_sha256'] != binding['adapter_sha256']
            or binding['source_sha256'] != source['source_sha256']
            or patch.get('candidate_ids') != [request['candidate_id']]
            or patch.get('repository_identity') != digest(str(root))):
        raise InputError('Adaptation plan differs from reviewed source or binding')
    regenerated = prepare_shape(preimage.read_bytes(), shape=request['strategy']['shape'],
                                symbol=source['symbol'], source_sha256=source['file_sha256'],
                                anchor_sha256=source['anchor_sha256'], adapter_name=request['adapter_name'])
    validate_static_adapter_import(preimage.read_bytes(), request['adapter_name'])
    original = preimage.read_bytes().decode('utf-8')
    proposed = regenerated['new_content']
    expected_diff = ''.join(difflib.unified_diff(
        original.splitlines(keepends=True), proposed.splitlines(keepends=True),
        fromfile='a/'+source['file'], tofile='b/'+source['file']))
    if (patch['changes'][0].get('new_content') != proposed
            or patch['changes'][0].get('diff') != expected_diff
            or plan['owned_file']['new_sha256'] != regenerated['new_sha256']):
        raise InputError('Adaptation patch differs from deterministic reviewed shape')
    adapter = safe_child(root, plan['adapter_file'])
    if (not adapter.is_file() or file_hash(adapter) != plan['adapter_sha256']
            or stat.S_IMODE(adapter.stat().st_mode) != plan['adapter_mode']):
        raise InputError('Reviewed adapter changed')
    validate_adapter_callback(adapter.read_bytes(), request['strategy']['shape'])
    for entry in inventory.get('files', []) + inventory.get('configuration_evidence', []):
        if entry['file'] == plan['owned_file']['file']:
            continue
        path = safe_child(root, entry['file'])
        if not path.is_file() or file_hash(path) != entry['sha256']:
            raise InputError('Reviewed repository snapshot changed')
    _journal(bundle, plan)
    return root, bundle, plan, patch, request, inventory


def _oracle_identity(root, plan, oracle):
    # The native oracle schema has no candidate_id field; the selected source
    # and review identity are therefore represented by the exact request hash.
    expected_context = digest({'inventory_sha256': plan['inventory_sha256'],
                               'request_sha256': plan['request_sha256']})
    if (oracle.get('repository_identity') != digest(str(root))
            or oracle.get('context_sha256') != expected_context
            or oracle.get('bundle_digest') != plan['contract_digest']):
        raise InputError('Native oracle differs from adaptation plan identity')


def plan_adaptation(root, inventory, request, bundle):
    """Create a private exact-byte proposal; no target import, write or run."""
    root, bundle = Path(root).resolve(strict=True), _bundle_dir(bundle)
    if bundle == root or bundle.is_relative_to(root) or bundle.exists():
        raise InputError('Adaptation plan needs a new external bundle directory')
    proposal = prepare_reviewed_shape(root, inventory, request)
    patch = make_patch_plan(root, [{'file': proposal['source_file'],
                                    'new_content': proposal['new_content']}], [request['candidate_id']])
    source = safe_child(root, proposal['source_file'])
    if patch['changes'][0]['new_sha256'] != proposal['new_sha256']:
        raise InputError('Adaptation patch differs from prepared proposal')
    owned = {'file': proposal['source_file'], 'old_sha256': file_hash(source),
             'new_sha256': proposal['new_sha256'], 'old_mode': stat.S_IMODE(source.stat().st_mode),
             'new_mode': stat.S_IMODE(source.stat().st_mode)}
    body = {'kind': 'adaptation-plan-v1', 'schema_version': '1.0',
            'root_identity': _root_identity(root), 'engine_identity': engine_identity(),
            'request_sha256': digest(request), 'inventory_sha256': digest(inventory),
            'patch_sha256': digest(patch), 'owned_file': owned,
            'adapter_file': request['binding_review']['adapter_file'],
            'adapter_sha256': request['binding_review']['adapter_sha256'],
            'adapter_mode': stat.S_IMODE(safe_child(root, request['binding_review']['adapter_file']).stat().st_mode)}
    plan = {**body, 'contract_digest': digest(body)}
    validate_contract(plan, 'adaptation-plan-v1')
    preimage = source.read_bytes()
    bundle.mkdir(parents=True, mode=0o700)
    os.chmod(bundle, 0o700)
    for name, value in [('adaptation-request.json', request), ('reviewed-inventory.json', inventory),
                        ('patch-plan.json', patch), ('adaptation-plan.json', plan)]:
        write_json(safe_child(bundle, name), value)
        os.chmod(safe_child(bundle, name), 0o600)
    p = safe_child(bundle, 'preimage.utf8')
    with p.open('xb') as handle:
        handle.write(preimage); handle.flush(); os.fsync(handle.fileno())
    os.chmod(p, 0o600)
    _sync_dir(bundle)
    return {'status': 'planned', 'contract_digest': plan['contract_digest'],
            'rollback_digest': rollback_digest(plan['contract_digest']),
            'patch_digest': patch['plan_digest'], 'source_sha256': owned['old_sha256'],
            'new_sha256': owned['new_sha256']}


def apply_adaptation(root, bundle, approved_plan_sha256, *, baseline_spec, baseline_receipt,
                     baseline_outputs, oracle, trusted_oracle_sha256,
                     trusted_baseline_receipt_sha256):
    root, bundle, plan, patch, request, _ = _load(root, bundle, current_engine=True)
    if approved_plan_sha256 != plan['contract_digest']:
        raise InputError('Externally approved exact adaptation plan digest required')
    with _lock(bundle, root):
        row = plan['owned_file']
        if _inspect_file(root, row) != 'baseline':
            raise InputError('Adaptation source changed before apply')
        if _journal(bundle, plan):
            raise InputError('Adaptation apply already started; inspect recovery state')
        _oracle_identity(root, plan, oracle)
        _check_native(baseline_spec, root, {'file': row['file'], 'sha256': row['old_sha256'],
                      'mode': row['old_mode']}, plan['adapter_file'], plan['adapter_sha256'],
                      plan['adapter_mode'])
        try:
            inspect_receipt(baseline_spec, baseline_receipt,
                            trusted_receipt_sha256=trusted_baseline_receipt_sha256)
            report = inspect_baseline_postconditions(
                oracle, trusted_oracle_sha256=trusted_oracle_sha256,
                spec=baseline_spec, receipt=baseline_receipt, outputs=baseline_outputs,
                trusted_receipt_sha256=trusted_baseline_receipt_sha256)
        except (RunnerError, KeyError, TypeError, ValueError) as error:
            raise InputError('Native baseline proof invalid') from error
        if not report['postconditions_satisfied'] or baseline_receipt['exited_zero'] != baseline_receipt['scheduled']:
            raise InputError('Independent native baseline postconditions failed')
        _record(bundle, plan, 'apply_started', row['file'])
        def progress(event, change):
            if event == 'write_completed':
                _sync_dir(safe_child(root, change['file']).parent)
            _record(bundle, plan, 'apply_' + event, change['file'])
        try:
            apply_patch_plan(root, patch, patch['plan_digest'], progress=progress)
        except Exception:
            _record(bundle, plan, 'apply_failed_recovery_required', row['file'])
            raise
        if _inspect_file(root, row) != 'applied':
            raise InputError('Adaptation bytes or mode changed during apply')
        _record(bundle, plan, 'applied_unverified', row['file'])
        return {'status': 'applied_unverified', 'contract_digest': plan['contract_digest']}


def verify_adaptation(root, bundle, *, baseline_spec, baseline_receipt, baseline_outputs,
                      modified_spec, modified_receipt, modified_outputs, oracle,
                      trusted_oracle_sha256, trusted_baseline_receipt_sha256,
                      trusted_modified_receipt_sha256):
    root, bundle, plan, _, _, _ = _load(root, bundle, current_engine=True)
    with _lock(bundle, root):
        events = [row['event'] for row in _journal(bundle, plan)]
        row = plan['owned_file']
        if not events or events[-1] != 'applied_unverified' or _inspect_file(root, row) != 'applied':
            raise InputError('Adaptation is not in a complete applied state')
        _oracle_identity(root, plan, oracle)
        _check_native(baseline_spec, root, {'file': row['file'], 'sha256': row['old_sha256'],
                      'mode': row['old_mode']}, plan['adapter_file'], plan['adapter_sha256'],
                      plan['adapter_mode'])
        _check_native(modified_spec, root, {'file': row['file'], 'sha256': row['new_sha256'],
                      'mode': row['new_mode']}, plan['adapter_file'], plan['adapter_sha256'],
                      plan['adapter_mode'])
        try:
            report = inspect_lifecycle_postconditions(
                oracle, trusted_oracle_sha256=trusted_oracle_sha256,
                baseline_spec=baseline_spec, baseline_receipt=baseline_receipt,
                baseline_outputs=baseline_outputs,
                trusted_baseline_receipt_sha256=trusted_baseline_receipt_sha256,
                modified_spec=modified_spec, modified_receipt=modified_receipt,
                modified_outputs=modified_outputs,
                trusted_modified_receipt_sha256=trusted_modified_receipt_sha256)
        except (RunnerError, KeyError, TypeError, ValueError) as error:
            raise InputError('Native modified proof invalid') from error
        if _inspect_file(root, row) != 'applied':
            raise InputError('Adaptation source changed during verification')
        if not report['postconditions_satisfied'] or modified_receipt['exited_zero'] != modified_receipt['scheduled']:
            _record(bundle, plan, 'verification_failed', row['file'])
            return {'status': 'verification_failed', 'report': report}
        _record(bundle, plan, 'verified_fresh', row['file'])
        return {'status': 'verified_fresh', 'report': report,
                'trusted_modified_receipt_sha256': trusted_modified_receipt_sha256}


def adaptation_status(root, bundle):
    root, bundle, plan, _, _, _ = _load(root, bundle)
    events = [row['event'] for row in _journal(bundle, plan)]
    state = _inspect_file(root, plan['owned_file'])
    if state == 'drift': return {'status': 'blocked_recovery', 'reason': 'owned_source_drift'}
    if not events: return {'status': 'planned' if state == 'baseline' else 'blocked_recovery'}
    if events[-1] == 'rolled_back' and state == 'baseline': return {'status': 'rolled_back'}
    if events[-1] in ('applied_unverified', 'verified_fresh', 'verification_failed') and state == 'applied':
        # No local journal row authenticates a native receipt or private output.
        return {'status': 'applied_unverified', 'recorded_event': events[-1]}
    return {'status': 'blocked_recovery', 'reason': 'interrupted_or_inconsistent_adaptation'}


def rollback_digest(contract_digest):
    return digest({'operation': 'restore_owned_adaptation_preimage',
                   'contract_digest': contract_digest})


def rollback_adaptation(root, bundle, approved_rollback_sha256):
    root, bundle, plan, _, request, _ = _load(root, bundle)
    if approved_rollback_sha256 != rollback_digest(plan['contract_digest']):
        raise InputError('Exact adaptation rollback approval required')
    with _lock(bundle, root):
        row = plan['owned_file']
        state = _inspect_file(root, row)
        if state == 'drift':
            raise InputError('Rollback refuses changed owned source')
        if state == 'baseline':
            _record(bundle, plan, 'rolled_back', row['file'])
            return {'status': 'rolled_back', 'idempotent': True}
        preimage = safe_child(bundle, 'preimage.utf8').read_bytes().decode('utf-8')
        reverse = make_patch_plan(root, [{'file': row['file'], 'new_content': preimage}], [request['candidate_id']])
        _record(bundle, plan, 'rollback_started', row['file'])
        def progress(event, change):
            if event == 'write_completed':
                _sync_dir(safe_child(root, change['file']).parent)
            _record(bundle, plan, 'rollback_' + event, change['file'])
        apply_patch_plan(root, reverse, reverse['plan_digest'], progress=progress)
        if _inspect_file(root, row) != 'baseline':
            raise InputError('Rollback did not restore owned source')
        _record(bundle, plan, 'rolled_back', row['file'])
        return {'status': 'rolled_back', 'idempotent': False}
