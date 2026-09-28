"""Exact-content bundles, durable recovery, and externally anchored execution receipts.

An intact local hash chain is integrity evidence, not authentication. In particular,
status never executes a target and never promotes a self-asserted success document.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from contextlib import contextmanager

from .. import __version__
from ..contracts import seal, verify, utc_now, validate_contract
from ..implementation import make_patch_plan, apply_patch_plan, FORBIDDEN
from ..io import InputError, atomic_text, canonical, digest, file_hash, read_json, read_jsonl, safe_child, write_json
from .contracts import validate_spec, validate_inventory
from .recipes import RECIPES, transform

IMMUTABLE = ('implementation-spec.json', 'reviewed-inventory.json', 'patch-plan.json',
             'implementation.diff', 'implementation-manifest.json', 'verification-cases.json')


def engine_identity():
    root = Path(__file__).resolve().parents[1]
    paths = sorted(root.rglob('*.py')) + sorted((root / 'data').glob('*.json'))
    return digest([(p.relative_to(root).as_posix(), file_hash(p)) for p in paths])


def _root_identity(root):
    p = Path(root).resolve(strict=True)
    if not p.is_dir(): raise InputError('Target root must be a directory')
    st = p.stat()
    return {'path_sha256': digest(str(p)), 'device': st.st_dev, 'inode': st.st_ino}


def _bundle_dir(path):
    p = Path(path).absolute()
    if any(q.is_symlink() for q in (p, *p.parents)):
        raise InputError('Bundle path may not traverse symlinks')
    return p.resolve()


def _sync_dir(p):
    if os.name != 'posix': return
    fd = os.open(p, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)


def _write_bytes(path, data):
    # Preimages are UTF-8 validated host bytes; use the shared atomic writer,
    # whose explicit newline mode retains supplied CRLF bytes exactly.
    atomic_text(path, data.decode('utf-8'))
    os.chmod(path, 0o600)
    _sync_dir(path.parent)


@contextmanager
def _lock(bundle):
    p = safe_child(bundle, 'operation.lock')
    with p.open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1): handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise InputError('Another implementation operation owns the bundle lock') from None
        try: yield
        finally:
            handle.seek(0)
            if os.name == 'nt': msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(handle, fcntl.LOCK_UN)


def _journal(bundle, plan):
    p = safe_child(bundle, 'journal.jsonl')
    if not p.exists(): return []
    if p.stat().st_size > 1_000_000: raise InputError('Recovery journal size limit exceeded')
    rows = list(read_jsonl(p))
    previous = None
    for index, row in enumerate(rows):
        verify(row)
        if row.get('sequence') != index or row.get('previous') != previous or row.get('bundle_digest') != plan['contract_digest']:
            raise InputError('Recovery journal chain mismatch')
        if set(row) != {'sequence', 'previous', 'bundle_digest', 'event', 'path_hash', 'time', 'contract_digest'}:
            raise InputError('Invalid recovery journal record')
        previous = row['contract_digest']
    return rows


def _record(bundle, plan, event, relative=None):
    rows = _journal(bundle, plan)
    if len(rows) >= 512: raise InputError('Recovery journal event limit; retain and review this bundle')
    row = seal({'sequence': len(rows), 'previous': rows[-1]['contract_digest'] if rows else None,
                'bundle_digest': plan['contract_digest'], 'event': event, 'path_hash': digest(relative) if relative else None,
                'time': utc_now()})
    with safe_child(bundle, 'journal.jsonl').open('ab') as handle:
        handle.write(canonical(row) + b'\n'); handle.flush(); os.fsync(handle.fileno())
    _sync_dir(bundle)


def _inspect_file(root, row):
    p = safe_child(root, row['file'])
    actual = file_hash(p) if p.is_file() else None
    mode = stat.S_IMODE(p.stat().st_mode) if p.exists() else None
    if p.exists() and not p.is_file(): return 'drift'
    if actual == row['old_sha256'] and mode == row['old_mode']: return 'baseline'
    if actual == row['new_sha256'] and mode == row['new_mode']: return 'applied'
    return 'drift'


def _load(root, bundle, *, current_engine=False):
    root, bundle = Path(root).resolve(strict=True), _bundle_dir(bundle)
    if bundle.is_relative_to(root): raise InputError('Implementation bundle must remain outside the target')
    plan = read_json(safe_child(bundle, 'implementation-plan.json'))
    validate_contract(plan, 'implementation-plan')
    verify(plan)
    if plan['root_identity'] != _root_identity(root): raise InputError('Wrong target root or worktree identity')
    if current_engine and plan['engine_identity'] != engine_identity():
        raise InputError('Implementation engine changed; regenerate and review a fresh plan')
    for rel, expected in plan['artifacts'].items():
        p = safe_child(bundle, rel)
        if not p.is_file() or file_hash(p) != expected: raise InputError('Implementation artifact integrity mismatch')
    expected_artifacts = set(IMMUTABLE) | {row['preimage'] for row in plan['owned_files'] if row['preimage'] is not None}
    if set(plan['artifacts']) != expected_artifacts: raise InputError('Unexpected or missing bundle artifact')
    spec = validate_spec(read_json(safe_child(bundle, 'implementation-spec.json')))
    inventory = read_json(safe_child(bundle, 'reviewed-inventory.json'))
    manifest = read_json(safe_child(bundle, 'implementation-manifest.json'))
    validate_contract(manifest, 'implementation-manifest')
    cases = read_json(safe_child(bundle, 'verification-cases.json'))
    validate_contract(cases, 'implementation-tests')
    if cases != spec['verification']: raise InputError('Scheduled test definitions differ from the reviewed specification')
    patch = read_json(safe_child(bundle, 'patch-plan.json'))
    validate_contract(patch, 'patch-plan')
    verify(patch, 'plan_digest')
    if (patch['plan_digest'] != plan['patch_digest'] or patch['repository_identity'] != digest(str(root))
            or digest(spec) != plan['spec_digest'] or digest(inventory) != spec['inventory_sha256']
            or plan['candidate_id'] != spec['candidate_id'] or plan['experiment_id'] != spec['experiment_id']
            or plan['recipe'] != spec['recipe'] or plan['binding_digest'] != digest(spec['bindings'])):
        raise InputError('Cross-artifact identity mismatch')
    if (manifest['candidate_id'] != spec['candidate_id'] or manifest['experiment_id'] != spec['experiment_id']
            or manifest['binding_digest'] != digest(spec['bindings']) or manifest['binding_review'] != spec['binding_review']
            or manifest['original_discovery_source']['file_sha256'] != spec['source']['file_sha256']
            or manifest['original_discovery_source']['source_sha256'] != spec['source']['source_sha256']):
        raise InputError('Implementation manifest differs from the reviewed discovery/binding')
    if spec.get('package_binding') != manifest.get('package_binding'):
        raise InputError('Package binding contract differs from the reviewed specification')
    if spec.get('package_binding') and spec['source']['file'] not in manifest.get('contributing_sources', {}):
        raise InputError('Package manifest omits the selected source dependency')
    if spec.get('package_binding') and set(manifest.get('qualified_bindings', {})) != set(spec['bindings']):
        raise InputError('Package manifest omits qualified role bindings')
    owned_sources = {row['file']: row for row in plan['owned_files']}
    for rel, expected in manifest.get('contributing_sources', {}).items():
        p = safe_child(root, rel)
        allowed = {expected}
        if rel in owned_sources: allowed.add(owned_sources[rel]['new_sha256'])
        if not p.is_file() or file_hash(p) not in allowed:
            raise InputError('Contributing package module changed since planning')
    owned = {row['file']: row for row in plan['owned_files']}
    if len(owned) != len(plan['owned_files']) or set(owned) != set(spec['output']['permitted_edits']):
        raise InputError('Overlapping or out-of-scope ownership')
    if {row['file'] for row in patch['changes']} != set(owned) or len(patch['changes']) != len(owned):
        raise InputError('Patch ownership differs from the binding')
    for change in patch['changes']:
        row = owned[change['file']]
        if (FORBIDDEN.search(row['file']) or row['old_sha256'] != change['old_sha256']
                or row['new_sha256'] != change['new_sha256']
                or hashlib.sha256(change['new_content'].encode('utf-8')).hexdigest() != row['new_sha256']):
            raise InputError('Owned file hash mismatch or protected path')
        if row['preimage'] is not None and file_hash(safe_child(bundle, row['preimage'])) != row['old_sha256']:
            raise InputError('Preimage differs from original source evidence')
    _journal(bundle, plan)
    return root, bundle, plan, spec, inventory, patch


def plan_implementation(root, inventory, candidate_id, spec, output):
    root, out = Path(root).resolve(strict=True), _bundle_dir(output)
    if out == root or out.is_relative_to(root): raise InputError('Plan output must be outside the target')
    spec = validate_spec(spec)
    if candidate_id != spec['candidate_id']: raise InputError('CLI candidate differs from binding candidate')
    if out.exists() and any(out.iterdir()):
        _, _, plan, oldspec, _, _ = _load(root, out, current_engine=True)
        if digest(spec) != digest(oldspec) or digest(inventory) != spec['inventory_sha256']:
            raise InputError('Refusing to overwrite a different implementation bundle')
        validate_inventory(root, inventory, spec)
        return {'status': 'planned', 'bundle_digest': plan['contract_digest'], 'reused': True}
    validate_inventory(root, inventory, spec)
    derived = transform(root, spec)
    patch = make_patch_plan(root, derived['changes'], [candidate_id])
    # Complete all independent validation before creating any bundle artifacts.
    discovery = {}
    for entry in inventory['files'] + inventory.get('configuration_evidence', []):
        p = safe_child(root, entry['file'])
        discovery[entry['file']] = {'sha256': entry['sha256'], 'mode': stat.S_IMODE(p.stat().st_mode)}
    for rel, expected in derived.get('contributing_sources', {}).items():
        p = safe_child(root, rel)
        if rel in discovery and discovery[rel]['sha256'] != expected:
            raise InputError('Contributing source differs from reviewed discovery')
        discovery[rel] = {'sha256': expected, 'mode': stat.S_IMODE(p.stat().st_mode)}
    if any(stat.S_IMODE(safe_child(root,c['file']).stat().st_mode) & 0o7000 for c in patch['changes'] if safe_child(root,c['file']).exists()):
        raise InputError('Privileged source file modes are unsupported; no target was changed')
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    owned = []
    for change in patch['changes']:
        p = safe_child(root, change['file'])
        preimage, mode = None, None
        if p.exists():
            mode = stat.S_IMODE(p.stat().st_mode)
            preimage = 'preimages/' + digest(change['file']) + '.utf8'
            _write_bytes(safe_child(out, preimage), p.read_bytes())
        owned.append({'file': change['file'], 'old_sha256': change['old_sha256'], 'new_sha256': change['new_sha256'],
                      'old_mode': mode, 'new_mode': mode if mode is not None else (0o666 if os.name == 'nt' else 0o600), 'preimage': preimage})
    write_json(out / 'implementation-spec.json', spec)
    write_json(out / 'verification-cases.json', spec['verification'])
    write_json(out / 'reviewed-inventory.json', inventory)
    write_json(out / 'patch-plan.json', patch)
    atomic_text(out / 'implementation.diff', '\n'.join(c['diff'] for c in patch['changes']))
    manifest = {k: v for k, v in derived.items() if k != 'changes'}
    manifest.update({'candidate_id': candidate_id, 'experiment_id': spec['experiment_id'],
                     'original_discovery_source': inventory['candidates'][next(i for i,c in enumerate(inventory['candidates']) if c['candidate_id']==candidate_id)]['source'],
                     'binding_review': spec['binding_review'], 'wiring_status': 'planned_not_applied', 'activation_authorized': False})
    validate_contract(manifest, 'implementation-manifest')
    write_json(out / 'implementation-manifest.json', manifest)
    artifact_names = list(IMMUTABLE) + [r['preimage'] for r in owned if r['preimage']]
    plan = seal({'schema_version': '1.0', 'root_identity': _root_identity(root), 'engine_version': __version__,
                 'engine_identity': engine_identity(), 'recipe': spec['recipe'], 'candidate_id': candidate_id,
                 'experiment_id': spec['experiment_id'], 'spec_digest': digest(spec), 'binding_digest': digest(spec['bindings']),
                 'patch_digest': patch['plan_digest'], 'owned_files': owned, 'discovery_files': discovery,
                 'artifacts': {n: file_hash(safe_child(out, n)) for n in artifact_names}})
    validate_contract(plan, 'implementation-plan')
    write_json(out / 'implementation-plan.json', plan)
    _sync_dir(out)
    _record(out, plan, 'planned')
    return {'status': 'planned', 'bundle_digest': plan['contract_digest'], 'patch_digest': patch['plan_digest'],
            'recipe': spec['recipe'], 'target_modified': False, 'target_executed': False}


def _receipt(root, bundle, plan, spec, phase, trusted_sha256=None):
    p = safe_child(bundle, 'baseline-receipt.json' if phase == 'baseline' else 'verification-receipt.json')
    if not p.is_file(): raise InputError('Missing ' + phase + ' execution receipt')
    if trusted_sha256 is not None and file_hash(p) != trusted_sha256:
        raise InputError('Execution receipt differs from the externally trusted digest')
    receipt = read_json(p)
    validate_contract(receipt, 'implementation-receipt')
    verify(receipt)
    from .observations import validate_observation
    expected_schedule = [(case['id'], mode) for case in spec['verification']['cases']
                         for mode in (('baseline',) if phase == 'baseline' else ('off', 'shadow', 'active'))]
    if ([(row['case_id'], row['mode']) for row in receipt['results']] != expected_schedule
            or receipt['scheduled_cases'] != len(expected_schedule)
            or receipt['completed_cases'] != sum(row['status'] in ('passed', 'failed') for row in receipt['results'])):
        raise InputError('Execution receipt does not cover the reviewed schedule')
    command = spec['verification'][phase+'_command']
    if [row['definition_sha256'] for row in receipt['command_checks']] != ([digest(command)] if command else []):
        raise InputError('Execution receipt omits or changes a reviewed command')
    for row in receipt['results']:
        if row['observation'] is not None:
            validate_observation(row['observation'], spec)
        elif row['status'] == 'passed':
            raise InputError('Passing execution case has no validated observation')
    if receipt['status'] == 'passed' and (any(row['status'] != 'passed' for row in receipt['results'])
            or any(row['status'] != 'passed' for row in receipt['command_checks'])):
        raise InputError('Passing receipt contains unsuccessful scheduled execution')
    if receipt.get('file_identity_valid') is False and receipt['status']=='passed':
        raise InputError('Passing execution receipt contradicts its final file identity check')
    if (receipt['bundle_digest'] != plan['contract_digest'] or receipt['phase'] != phase
            or receipt['spec_digest'] != plan['spec_digest'] or receipt['engine_identity'] != plan['engine_identity']
            or receipt['command_definition_digest'] != digest(spec['verification'])
            or receipt['file_hashes'] != {r['file']: r['old_sha256' if phase == 'baseline' else 'new_sha256'] for r in plan['owned_files']}):
        raise InputError('Execution receipt context mismatch')
    return receipt


def _check_discovery(root, plan, applied=False):
    owned = {r['file']: r for r in plan['owned_files']}
    for rel, original in plan['discovery_files'].items():
        expected = original['sha256']
        if applied and rel in owned: expected = owned[rel]['new_sha256']
        p = safe_child(root, rel)
        if not p.is_file() or file_hash(p) != expected or stat.S_IMODE(p.stat().st_mode) != original['mode']:
            raise InputError('Reviewed source or file mode drift')


def implementation_status(root, bundle, *, trusted_receipt_sha256=None):
    root, bundle, plan, spec, _, _ = _load(root, bundle)
    identities = {r['file']: _inspect_file(root, r) for r in plan['owned_files']}
    states = set(identities.values())
    events = [row['event'] for row in _journal(bundle, plan)]
    baseline_events = ('baseline_verification_started', 'baseline_verification_passed', 'baseline_verification_failed')
    # Baseline checks cannot reopen a rolled-back bundle or clear unfinished
    # mutation recovery. Their own incomplete start still blocks below.
    disposition_events = [event for event in events if event not in baseline_events]
    terminal_events = ('planned', 'applied_unverified', 'verification_failed', 'verified', 'rolled_back')
    if states == {'baseline'}:
        state = 'rolled_back' if disposition_events and disposition_events[-1] == 'rolled_back' else 'planned'
    elif states == {'applied'}:
        state = 'applied_unverified'
    else:
        state = 'blocked_recovery'
    if disposition_events and disposition_events[-1] not in terminal_events:
        state = 'blocked_recovery'
    if events and events[-1] not in terminal_events + baseline_events[1:]:
        state = 'blocked_recovery'
    receipt_state = 'absent'
    p = safe_child(bundle, 'verification-receipt.json')
    if p.exists():
        result = _receipt(root, bundle, plan, spec, 'modified', trusted_receipt_sha256)
        receipt_state = 'integrity_consistent_but_unverified'
        if state == 'applied_unverified' and result['status'] != 'passed': state = 'verification_failed'
        if trusted_receipt_sha256 is not None and state == 'applied_unverified' and result['status'] == 'passed':
            _check_discovery(root, plan, applied=True)
            if plan['engine_identity'] != engine_identity(): raise InputError('Receipt refers to another implementation engine')
            # The caller must have authenticated this digest outside the bundle.
            state, receipt_state = 'verified', 'externally_anchored_execution'
    return {'status': state, 'bundle_digest': plan['contract_digest'], 'file_identity': identities,
            'receipt_trust': receipt_state, 'target_executed': False, 'runtime_activation_authorized': False,
            'benefit_demonstrated': False, 'rollback_digest': rollback_digest(plan)}


def apply_implementation(root, bundle, approval, *, baseline_sha256):
    root, bundle, plan, spec, inventory, patch = _load(root, bundle, current_engine=True)
    if approval != plan['contract_digest']: raise InputError('Exact reviewed bundle digest approval is required')
    if not baseline_sha256: raise InputError('An externally retained baseline receipt digest is required')
    with _lock(bundle):
        receipt = _receipt(root, bundle, plan, spec, 'baseline', baseline_sha256)
        if receipt['status'] != 'passed': raise InputError('Baseline verification did not pass')
        status = implementation_status(root, bundle)
        if status['status'] in ('applied_unverified', 'verification_failed', 'verified'):
            _check_discovery(root, plan, applied=True)
            return {**status, 'idempotent': True}
        if status['status'] != 'planned': raise InputError('Bundle needs explicit recovery/rollback, not another application')
        validate_inventory(root, inventory, spec)
        _check_discovery(root, plan)
        if any(_inspect_file(root, r) != 'baseline' for r in plan['owned_files']): raise InputError('Owned path drift before apply')
        _record(bundle, plan, 'apply_started')
        def progress(event, change):
            if event == 'write_completed': _sync_dir(safe_child(root, change['file']).parent)
            _record(bundle, plan, 'apply_' + event, change['file'])
        try:
            apply_patch_plan(root, patch, patch['plan_digest'], progress=progress)
        except Exception:
            _record(bundle, plan, 'apply_failed_recovery_required')
            raise
        if any(_inspect_file(root, r) != 'applied' for r in plan['owned_files']):
            _record(bundle, plan, 'apply_identity_failed')
            raise InputError('Applied bytes/modes did not match the reviewed bundle')
        _record(bundle, plan, 'applied_unverified')
        return implementation_status(root, bundle)


def rollback_digest(plan):
    return digest({'operation': 'restore_owned_preimages', 'bundle_digest': plan['contract_digest'], 'owned_files': plan['owned_files']})


def rollback_implementation(root, bundle, approval):
    root, bundle, plan, _, _, _ = _load(root, bundle)
    if approval != rollback_digest(plan): raise InputError('Exact rollback digest approval is required')
    with _lock(bundle):
        identities = {r['file']: _inspect_file(root, r) for r in plan['owned_files']}
        if 'drift' in identities.values(): raise InputError('Rollback refuses changed owned bytes or modes; concurrent work is preserved')
        if set(identities.values()) == {'baseline'}:
            _record(bundle, plan, 'rolled_back')
            return {'status': 'rolled_back', 'idempotent': True}
        _record(bundle, plan, 'rollback_started')
        restores = [{'file': r['file'], 'new_content': safe_child(bundle, r['preimage']).read_bytes().decode('utf-8')}
                    for r in plan['owned_files'] if identities[r['file']] == 'applied' and r['preimage']]
        if restores:
            patch = make_patch_plan(root, restores, [plan['candidate_id']])
            def progress(event, row):
                if event == 'write_completed': _sync_dir(safe_child(root, row['file']).parent)
                _record(bundle, plan, 'rollback_' + event, row['file'])
            apply_patch_plan(root, patch, patch['plan_digest'], progress=progress)
        for row in plan['owned_files']:
            if row['preimage'] is None and identities[row['file']] == 'applied':
                p = safe_child(root, row['file'])
                if _inspect_file(root, row) != 'applied': raise InputError('Concurrent edit during rollback')
                _record(bundle, plan, 'rollback_delete_started', row['file'])
                p.unlink(); _sync_dir(p.parent)
                _record(bundle, plan, 'rollback_delete_completed', row['file'])
        if any(_inspect_file(root, r) != 'baseline' for r in plan['owned_files']):
            raise InputError('Rollback interrupted or concurrent edit detected; preserve the bundle for recovery')
        _record(bundle, plan, 'rolled_back')
        return {'status': 'rolled_back', 'owned_changes_restored': len(plan['owned_files']), 'unrelated_paths_modified': False}
