"""Exact, reversible creation/revision of a generated adaptation adapter.

Bootstrap creation precedes the legacy one-source adaptation baseline. A final
revision follows its verification and a fresh source review. Neither stage
executes target code or authenticates its own review receipt.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from typing import Any

from ..implementation import apply_patch_plan, make_patch_plan
from ..contracts import validate_contract
from ..io import InputError, digest, file_hash, read_json, safe_child, write_json
from .adaptation_runtime import inspect_runtime_package, render_adapter
from .adaptation_shapes import prepare_shape, validate_static_adapter_import
from .lifecycle import (_bundle_dir, _inspect_file, _journal, _lock, _record,
                        _root_identity, _sync_dir, engine_identity)


def _prepare(root: Path, request: dict, spec: dict) -> tuple[dict, dict, dict]:
    validate_contract(request, 'generated-adaptation-adapter-request-v1')
    if (type(request) is not dict or set(request) != {'kind', 'stage', 'candidate_id',
            'shape', 'source_file', 'symbol', 'source_before_sha256', 'source_after_sha256',
            'anchor_sha256', 'adapter_name', 'script', 'reviewed_inventory_sha256',
            'external_caller_review_sha256', 'request_position', 'positional_count'}
            | {'adaptation_verification_sha256'}
            or request['kind'] != 'generated-adaptation-adapter-v1'
            or request['stage'] not in ('bootstrap', 'final')
            or type(request['adapter_name']) is not str or not request['adapter_name'].isidentifier()):
        raise InputError('Invalid generated adapter request')
    source = safe_child(root, request['source_file'])
    if not source.is_file() or source.is_symlink():
        raise InputError('Selected adaptation source unavailable')
    raw = source.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if request['stage'] == 'bootstrap':
        if actual != request['source_before_sha256']:
            raise InputError('Bootstrap source differs from reviewed bytes')
        selected = prepare_shape(raw, shape=request['shape'], symbol=request['symbol'],
                                 source_sha256=actual, anchor_sha256=request['anchor_sha256'],
                                 adapter_name=request['adapter_name'])
        if selected['new_sha256'] != request['source_after_sha256']:
            raise InputError('Projected adapted bytes differ from request')
        adapted = selected['new_content']
    else:
        if actual != request['source_after_sha256']:
            raise InputError('Final adapter requires the verified adapted source bytes')
        adapted = raw.decode('utf-8')
    validate_static_adapter_import(raw, request['adapter_name'])
    scope = inspect_runtime_package(root, source_file=request['source_file'],
        adapted_source=adapted, symbol=request['symbol'], shape=request['shape'],
        script=request['script'], adapter_name=request['adapter_name'])
    if (spec.get('candidate_id') != request['candidate_id']
            or spec.get('source', {}).get('file') != request['source_file']
            or spec['source'].get('symbol') != request['symbol']
            or spec['source'].get('file_sha256') != request['source_after_sha256']):
        raise InputError('Runtime adapter spec differs from projected adapted source')
    if request['stage'] == 'final' and not spec['source'].get('source_sha256'):
        raise InputError('Fresh adapted source review identity required')
    adapter_rel = (Path(request['source_file']).parent / (request['adapter_name'] + '.py')).as_posix()
    adapter = safe_child(root, adapter_rel)
    if request['stage'] == 'final' and not adapter.is_file():
        raise InputError('Final adapter revision requires the generated bootstrap')
    depth = 2 if Path(request['source_file']).parts[0] == 'src' else 1
    content = render_adapter(spec=spec, shape=request['shape'],
                             source_files=scope['source_files'],
                             pyproject_sha256=scope['pyproject_sha256'],
                             script=scope['script'], script_target=scope['script_target'],
                             distribution=scope['distribution'],
                             caller_scope_sha256=digest(scope), source_root_depth=depth,
                             request_position=request['request_position'],
                             positional_count=request['positional_count'])
    patch = make_patch_plan(root, [{'file': adapter_rel, 'new_content': content}],
                            [request['candidate_id']])
    return scope, patch, {'file': adapter_rel, 'old_sha256': patch['changes'][0]['old_sha256'],
                          'new_sha256': patch['changes'][0]['new_sha256'],
                          'old_mode': stat.S_IMODE(adapter.stat().st_mode) if adapter.exists() else None,
                          'new_mode': stat.S_IMODE(adapter.stat().st_mode) if adapter.exists()
                          else (0o666 if os.name == 'nt' else 0o644)}


def plan_generated_adapter(root: Path, request: dict, spec: dict, inventory: dict,
                           caller_review: dict, bundle: Path,
                           *, verify_adaptation: Any = None) -> dict:
    """Write one private plan; caller retains independent review and approval."""
    validate_contract(request, 'generated-adaptation-adapter-request-v1')
    if type(spec) is not dict or type(inventory) is not dict:
        raise InputError('Reviewed runtime spec and inventory are required')
    root = Path(root).resolve(strict=True)
    bundle = _bundle_dir(bundle)
    if bundle.exists() or bundle == root or bundle.is_relative_to(root):
        raise InputError('Generated adapter plan needs a new external bundle')
    if digest(inventory) != request.get('reviewed_inventory_sha256'):
        raise InputError('Reviewed inventory differs from generated adapter request')
    if request['stage'] == 'final':
        if (type(request['adaptation_verification_sha256']) is not str
                or not callable(verify_adaptation)
                or verify_adaptation('verified_adaptation',
                    request['adaptation_verification_sha256']) is not True):
            raise InputError('Externally anchored verified adaptation required before final runtime')
    elif request['adaptation_verification_sha256'] is not None:
        raise InputError('Bootstrap cannot inherit a later adaptation receipt')
    candidates = [row for row in inventory.get('candidates', [])
                  if row.get('candidate_id') == request.get('candidate_id')]
    if (len(candidates) != 1 or candidates[0].get('semantic_review', {}).get('approved') is not True
            or not candidates[0]['semantic_review'].get('reviewer')
            or not candidates[0]['semantic_review'].get('reason')):
        raise InputError('Approved source-matched adaptation candidate required')
    expected = request['source_before_sha256'] if request['stage'] == 'bootstrap' else request['source_after_sha256']
    if (candidates[0].get('source', {}).get('file') != request['source_file']
            or candidates[0]['source'].get('symbol') != request['symbol']
            or candidates[0]['source'].get('file_sha256') != expected
            or candidates[0]['semantic_review'].get('source_sha256') != candidates[0]['source'].get('source_sha256')):
        raise InputError('Current adaptation source review differs from request')
    if (request['stage'] == 'final' and
            candidates[0]['source'].get('source_sha256') != spec['source'].get('source_sha256')):
        raise InputError('Final adapter spec requires fresh adapted source review')
    for row in inventory.get('files', []) + inventory.get('configuration_evidence', []):
        path = safe_child(root, row['file'])
        if not path.is_file() or file_hash(path) != row['sha256']:
            raise InputError('Reviewed adaptation package snapshot changed')
    scope, patch, owned = _prepare(root, request, spec)
    validate_contract(caller_review, 'adaptation-runtime-caller-review-v1')
    if (type(caller_review) is not dict or set(caller_review) != {
            'reviewer', 'reason', 'closed_scope', 'external_callers', 'caller_scope_sha256'}
            or type(caller_review['reviewer']) is not str or not caller_review['reviewer']
            or type(caller_review['reason']) is not str or not caller_review['reason']
            or caller_review['closed_scope'] is not True
            or caller_review['external_callers'] is not False
            or caller_review['caller_scope_sha256'] != digest(scope)
            or request['external_caller_review_sha256'] != digest(caller_review)):
        raise InputError('Independent complete-caller review must bind exact package audit')
    if request['stage'] == 'bootstrap' and owned['old_sha256'] is not None:
        raise InputError('Bootstrap adapter path already exists')
    body = {'kind': 'generated-adaptation-adapter-plan-v1', 'schema_version': '1.0',
            'root_identity': _root_identity(root), 'engine_identity': engine_identity(),
            'request_sha256': digest(request), 'spec_sha256': digest(spec),
            'inventory_sha256': digest(inventory), 'caller_scope_sha256': digest(scope),
            'patch_sha256': digest(patch), 'owned_file': owned,
            'source_file': request['source_file'], 'source_before_sha256': request['source_before_sha256'],
            'source_after_sha256': request['source_after_sha256'],
            'adaptation_verification_sha256': request['adaptation_verification_sha256'],
            'stage': request['stage']}
    plan = dict(body, contract_digest=digest(body))
    validate_contract(plan, 'generated-adaptation-adapter-plan-v1')
    bundle.mkdir(parents=True, mode=0o700)
    os.chmod(bundle, 0o700)
    for name, value in [('adapter-request.json', request), ('runtime-spec.json', spec),
                        ('reviewed-inventory.json', inventory), ('caller-scope.json', scope),
                        ('caller-review.json', caller_review),
                        ('patch-plan.json', patch), ('adapter-plan.json', plan)]:
        write_json(bundle / name, value)
        os.chmod(bundle / name, 0o600)
    if request['stage'] == 'bootstrap':
        original = safe_child(root, request['source_file']).read_bytes()
        with (bundle / 'source-preimage.utf8').open('xb') as handle:
            handle.write(original); handle.flush(); os.fsync(handle.fileno())
        os.chmod(bundle / 'source-preimage.utf8', 0o600)
    if owned['old_sha256'] is not None:
        preimage = safe_child(root, owned['file']).read_bytes()
        with (bundle / 'adapter-preimage.utf8').open('xb') as handle:
            handle.write(preimage); handle.flush(); os.fsync(handle.fileno())
        os.chmod(bundle / 'adapter-preimage.utf8', 0o600)
    _sync_dir(bundle)
    return {'status': 'planned', 'contract_digest': plan['contract_digest'],
            'rollback_digest': generated_adapter_rollback_digest(plan['contract_digest']),
            'adapter_sha256': owned['new_sha256'], 'caller_scope_sha256': digest(scope)}


def _load(root: Path, bundle: Path):
    root, bundle = Path(root).resolve(strict=True), _bundle_dir(bundle)
    if bundle.is_relative_to(root):
        raise InputError('Generated adapter bundle must remain outside target')
    plan = read_json(bundle / 'adapter-plan.json')
    request = read_json(bundle / 'adapter-request.json')
    spec = read_json(bundle / 'runtime-spec.json')
    inventory = read_json(bundle / 'reviewed-inventory.json')
    scope = read_json(bundle / 'caller-scope.json')
    caller_review = read_json(bundle / 'caller-review.json')
    patch = read_json(bundle / 'patch-plan.json')
    validate_contract(request, 'generated-adaptation-adapter-request-v1')
    validate_contract(plan, 'generated-adaptation-adapter-plan-v1')
    validate_contract(caller_review, 'adaptation-runtime-caller-review-v1')
    if (plan.get('root_identity') != _root_identity(root)
            or plan.get('contract_digest') != digest({k: v for k, v in plan.items() if k != 'contract_digest'})
            or plan.get('request_sha256') != digest(request)
            or plan.get('spec_sha256') != digest(spec)
            or plan.get('inventory_sha256') != digest(inventory)
            or plan.get('caller_scope_sha256') != digest(scope)
            or request.get('external_caller_review_sha256') != digest(caller_review)
            or caller_review.get('caller_scope_sha256') != digest(scope)
            or caller_review.get('closed_scope') is not True
            or caller_review.get('external_callers') is not False
            or plan.get('patch_sha256') != digest(patch)
            or plan.get('adaptation_verification_sha256') != request.get('adaptation_verification_sha256')
            or request.get('reviewed_inventory_sha256') != digest(inventory)):
        raise InputError('Generated adapter bundle identity mismatch')
    # Re-render from the original requested bytes. After bootstrap adaptation,
    # the selected source may be either original or projected bytes.
    source = safe_child(root, request['source_file'])
    current = file_hash(source)
    if request['stage'] == 'bootstrap' and current == request['source_after_sha256']:
        saved = bundle / 'source-preimage.utf8'
        if not saved.is_file():
            raise InputError('Bootstrap preimage missing after source adaptation')
        original = saved.read_bytes()
        if hashlib.sha256(original).hexdigest() != request['source_before_sha256']:
            raise InputError('Bootstrap source preimage changed')
        projected = prepare_shape(original, shape=request['shape'], symbol=request['symbol'],
                                  source_sha256=request['source_before_sha256'],
                                  anchor_sha256=request['anchor_sha256'],
                                  adapter_name=request['adapter_name'])
        if projected['new_sha256'] != current or projected['new_content'].encode('utf-8') != source.read_bytes():
            raise InputError('Adapted source differs from deterministic edit')
        # Exact adapter/content checks below remain valid during recovery.
        regenerated = None
    elif current == (request['source_before_sha256'] if request['stage'] == 'bootstrap'
                     else request['source_after_sha256']):
        regenerated = _prepare(root, request, spec)
    else:
        raise InputError('Generated adapter source drift')
    if regenerated is not None:
        fresh_scope, fresh_patch, fresh_owned = regenerated
        if (fresh_scope != scope or fresh_patch['changes'][0]['new_content'] != patch['changes'][0]['new_content']
                or fresh_owned['file'] != plan['owned_file']['file']
                or fresh_owned['new_sha256'] != plan['owned_file']['new_sha256']):
            raise InputError('Generated adapter differs from deterministic request')
    if patch['plan_digest'] != digest({k: v for k, v in patch.items() if k != 'plan_digest'}):
        raise InputError('Generated adapter patch changed')
    _journal(bundle, plan)
    return root, bundle, plan, patch, request


def apply_generated_adapter(root: Path, bundle: Path, approved_digest: str,
                            *, verify_review: Any) -> dict:
    root, bundle, plan, patch, request = _load(root, bundle)
    if approved_digest != plan['contract_digest'] or plan['engine_identity'] != engine_identity():
        raise InputError('Exact current generated adapter approval required')
    if (not callable(verify_review) or verify_review('adaptation_caller_review',
            request['external_caller_review_sha256']) is not True):
        raise InputError('Externally authenticated complete-caller review required')
    with _lock(bundle, root):
        root, bundle, plan, patch, request = _load(root, bundle)
        if (request['stage'] == 'bootstrap' and
                file_hash(safe_child(root, request['source_file'])) != request['source_before_sha256']):
            raise InputError('Bootstrap must be applied before source adaptation')
        if _journal(bundle, plan) or _inspect_file(root, plan['owned_file']) != 'baseline':
            raise InputError('Generated adapter apply already started or target drifted')
        _record(bundle, plan, 'apply_started', plan['owned_file']['file'])
        try:
            apply_patch_plan(root, patch, patch['plan_digest'])
            os.chmod(safe_child(root, plan['owned_file']['file']), plan['owned_file']['new_mode'])
            _sync_dir(safe_child(root, plan['owned_file']['file']).parent)
        except Exception:
            _record(bundle, plan, 'apply_failed_recovery_required', plan['owned_file']['file'])
            raise
        if _inspect_file(root, plan['owned_file']) != 'applied':
            raise InputError('Generated adapter bytes or mode changed during apply')
        _record(bundle, plan, 'applied_unverified', plan['owned_file']['file'])
        return {'status': 'applied_unverified', 'contract_digest': plan['contract_digest']}


def generated_adapter_rollback_digest(contract_digest: str) -> str:
    return digest({'operation': 'restore_generated_adaptation_adapter',
                   'contract_digest': contract_digest})


def generated_adapter_status(root: Path, bundle: Path) -> dict:
    root, bundle, plan, _, _ = _load(root, bundle)
    state = _inspect_file(root, plan['owned_file'])
    events = [row['event'] for row in _journal(bundle, plan)]
    if state == 'drift':
        status = 'blocked_recovery'
    elif not events:
        status = 'planned' if state == 'baseline' else 'blocked_recovery'
    elif events[-1] == 'rolled_back' and state == 'baseline':
        status = 'rolled_back'
    elif events[-1] == 'applied_unverified' and state == 'applied':
        status = 'applied_unverified'
    else:
        status = 'blocked_recovery'
    return {'status': status, 'contract_digest': plan['contract_digest'],
            'file_identity': state, 'target_executed': False,
            'runtime_activation_authorized': False}


def rollback_generated_adapter(root: Path, bundle: Path, approved_digest: str) -> dict:
    root, bundle, plan, _, request = _load(root, bundle)
    if approved_digest != generated_adapter_rollback_digest(plan['contract_digest']):
        raise InputError('Exact generated adapter rollback approval required')
    with _lock(bundle, root):
        if (request['stage'] == 'bootstrap' and
                file_hash(safe_child(root, request['source_file'])) != request['source_before_sha256']):
            raise InputError('Rollback adapted source before removing bootstrap adapter')
        state = _inspect_file(root, plan['owned_file'])
        if state == 'drift':
            raise InputError('Generated adapter rollback refuses owned byte or mode drift')
        if state == 'baseline':
            return {'status': 'rolled_back', 'idempotent': True}
        path = safe_child(root, plan['owned_file']['file'])
        _record(bundle, plan, 'rollback_started', plan['owned_file']['file'])
        if plan['owned_file']['old_sha256'] is None:
            path.unlink()
        else:
            preimage = (bundle / 'adapter-preimage.utf8').read_bytes()
            if hashlib.sha256(preimage).hexdigest() != plan['owned_file']['old_sha256']:
                raise InputError('Generated adapter preimage changed')
            reverse = make_patch_plan(root, [{'file': plan['owned_file']['file'],
                                              'new_content': preimage.decode('utf-8')}],
                                      [request['candidate_id']])
            apply_patch_plan(root, reverse, reverse['plan_digest'])
            os.chmod(path, plan['owned_file']['old_mode'])
        _sync_dir(path.parent)
        if _inspect_file(root, plan['owned_file']) != 'baseline':
            raise InputError('Generated adapter rollback did not restore owned state')
        _record(bundle, plan, 'rolled_back', plan['owned_file']['file'])
        return {'status': 'rolled_back', 'idempotent': False}
