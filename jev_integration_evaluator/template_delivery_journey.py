"""Read-only reconciliation bridge from a reviewed source transaction to a session.

The underlying source, package and installation owners perform their own
effectful operations.  This journal pins their exact receipts into one stable
delivery run, without granting an extra path that could replay an effect.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import uuid

from .contracts import validate_contract
from .io import InputError, canonical, digest, file_hash, read_json
from .template_delivery import (DeliveryError, _locked, _now, _owned_file,
                                _private, _safe_directory, create_session,
                                plan_delivery, session_status)
from .template_installation import (installation_status, package_status,
                                    plan_install, plan_package)
from .integrations.lifecycle import implementation_status


_STAGES = ('source_planned', 'baseline_anchored', 'source_verified',
           'package_planned', 'package_built', 'install_planned',
           'installed', 'promotion_pending', 'runtime_session')
_MAX_EVENTS = 32


def _source_status(state: dict) -> dict:
    if state['source_kind'] == 'composite':
        from .integrations.composite import status_composite
        return status_composite(state['source_root'], state['bundle'],
            trusted_receipt_sha256=state['modified_receipt_sha256'])
    return implementation_status(state['source_root'], state['bundle'],
        trusted_receipt_sha256=state['modified_receipt_sha256'])


def _package_plan(state: dict, plan: dict) -> dict:
    request = plan['request']
    if (request['host_root'] != state['source_root'] or
            request['implementation_bundle'] != state['bundle'] or
            request['trusted_modified_receipt_sha256'] != state['modified_receipt_sha256']):
        raise DeliveryError('journey_package_source_binding_changed')
    if state['source_kind'] == 'composite':
        from .template_installation import plan_composite_package
        return plan_composite_package(request, _allow_existing_output=True)
    return plan_package(request, _allow_existing_output=True)


def _install_plan(state: dict, package_plan: dict, package_receipt: dict) -> dict:
    if state['source_kind'] == 'composite':
        from .template_installation import plan_composite_install
        return plan_composite_install(package_plan, package_receipt)
    return plan_install(package_plan, package_receipt)


def _package_status(state: dict, plan: dict) -> dict:
    return package_status(plan)


def _install_status(state: dict, plan: dict) -> dict:
    if state['source_kind'] == 'composite':
        from .template_installation import composite_installation_status
        return composite_installation_status(plan)
    return installation_status(plan)


def _archive(directory: Path, value: dict, sha: str) -> None:
    parent = directory / 'plans'
    _private(parent)
    path = parent / (sha + '.json')
    if path.exists():
        _owned_file(path, maximum=2_000_000)
        if read_json(path) != value:
            raise DeliveryError('journey_plan_archive_collision')
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical(value) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _load_plan(directory: Path, sha: str) -> dict:
    path = directory / 'plans' / (sha + '.json')
    _owned_file(path, maximum=2_000_000)
    value = read_json(path)
    if value.get('plan_sha256') != sha:
        raise DeliveryError('journey_plan_archive_changed')
    return value


def _rows(directory: Path) -> list[dict]:
    _private(directory)
    _private(directory / 'plans')
    path = directory / 'journey.jsonl'
    _owned_file(path, maximum=1_000_000)
    rows: list[dict] = []
    with path.open('rb') as stream:
        for line in stream:
            if len(line) > 8192 or len(rows) >= _MAX_EVENTS:
                raise DeliveryError('journey_journal_bound_exceeded')
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise DeliveryError('journey_journal_torn_or_modified') from None
            if (type(row) is not dict or row.get('sequence') != len(rows)
                    or row.get('event') not in _STAGES
                    or row.get('previous_sha256') != (rows[-1]['record_sha256'] if rows else None)
                    or 'state' not in row
                    or row.get('record_sha256') != digest({k: v for k, v in row.items()
                                                           if k != 'record_sha256'})):
                raise DeliveryError('journey_journal_torn_or_modified')
            validate_contract(row['state'], 'template-delivery-journey-v1')
            rows.append(row)
    if not rows:
        raise DeliveryError('journey_journal_empty')
    return rows


def _append(directory: Path, rows: list[dict], event: str, state: dict) -> str:
    if event not in _STAGES or len(rows) >= _MAX_EVENTS:
        raise DeliveryError('journey_journal_bound_exceeded')
    validate_contract(state, 'template-delivery-journey-v1')
    row = {'sequence': len(rows),
           'previous_sha256': rows[-1]['record_sha256'] if rows else None,
           'event': event, 'at': _now(), 'state': copy.deepcopy(state)}
    row['record_sha256'] = digest(row)
    path = directory / 'journey.jsonl'
    _owned_file(path, maximum=1_000_000)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical(row) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    rows.append(row)
    return row['record_sha256']


def _open(directory: str | Path) -> tuple[Path, list[dict], dict]:
    target = _safe_directory(directory, exists=True)
    rows = _rows(target)
    return target, rows, copy.deepcopy(rows[-1]['state'])


def create_journey(directory: str | Path, *, source_root: str,
                   bundle: str, source_kind: str = 'single') -> dict:
    """Create a stable run before apply; no target or package effect occurs."""
    if source_kind not in ('single', 'composite'):
        raise DeliveryError('journey_source_kind_unsupported')
    for name in (source_root, bundle):
        path = Path(name)
        if not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents)):
            raise DeliveryError('journey_source_and_bundle_must_be_absolute_without_symlinks')
    target = _safe_directory(directory, exists=False)
    if not target.parent.is_dir():
        raise DeliveryError('journey_parent_missing')
    state = {'schema_version': '1.0', 'kind': 'template-delivery-journey-v1',
             'run_id': str(uuid.uuid4()), 'stage': 'source_planned',
             'source_kind': source_kind, 'source_root': source_root,
             'bundle': bundle, 'bundle_digest': '',
             'baseline_receipt_sha256': None, 'modified_receipt_sha256': None,
             'package_plan_sha256': None, 'package_receipt_sha256': None,
             'install_plan_sha256': None, 'install_receipt_sha256': None,
             'delivery_plan_sha256': None}
    observed = _source_status(state)
    if observed['status'] not in ('planned', 'applied_unverified'):
        raise DeliveryError('journey_requires_reviewed_source_transaction')
    state['bundle_digest'] = observed['bundle_digest']
    if any(target == root or target.is_relative_to(root) or root.is_relative_to(target)
           for root in (Path(source_root), Path(bundle))):
        raise DeliveryError('journey_overlaps_source_or_bundle')
    target.mkdir(mode=0o700)
    _private(target)
    (target / 'plans').mkdir(mode=0o700)
    fd = os.open(target / 'journey.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with _locked(target):
        head = _append(target, [], 'source_planned', state)
    return journey_status(target, trusted_journey_head=head)


def _current(directory: Path, state: dict) -> dict:
    try:
        source = _source_status(state)
    except (InputError, OSError, ValueError):
        source = {'status': 'drift_or_unavailable', 'receipt_trust': 'unavailable',
                  'bundle_digest': state['bundle_digest']}
    if source['bundle_digest'] != state['bundle_digest']:
        raise DeliveryError('journey_source_bundle_changed')
    result = {'source_status': source['status'], 'source_receipt_trust': source['receipt_trust']}
    if state['package_plan_sha256'] is not None:
        package_plan = _load_plan(directory, state['package_plan_sha256'])
        if source['status'] == 'verified':
            try:
                if _package_plan(state, package_plan) != package_plan:
                    raise DeliveryError('journey_package_plan_drift')
            except (InputError, OSError, ValueError):
                result['package_status'] = 'plan_or_source_drift'
        if 'package_status' not in result:
            result['package_status'] = _package_status(state, package_plan)['status']
    else:
        result['package_status'] = 'unplanned'
    if state['install_plan_sha256'] is not None:
        install_plan = _load_plan(directory, state['install_plan_sha256'])
        result['install_status'] = _install_status(state, install_plan)['status']
    else:
        result['install_status'] = 'unplanned'
    runtime = directory / 'runtime'
    if runtime.exists():
        child = session_status(runtime)
        if child['run_id'] != state['run_id']:
            raise DeliveryError('journey_runtime_run_identity_changed')
        result['runtime_status'] = child['stage']
    else:
        result['runtime_status'] = 'absent'
    return result


def _next(state: dict, current: dict) -> str:
    if current['source_status'] == 'blocked_recovery':
        return 'reconcile_exact_source_transaction'
    if current['source_status'] == 'drift_or_unavailable':
        return 'review_source_transaction'
    if state['baseline_receipt_sha256'] is None:
        return 'verify_and_anchor_source_baseline'
    if current['source_status'] == 'planned':
        return 'apply_exact_source_bundle'
    if current['source_status'] == 'applied_unverified':
        return 'verify_and_anchor_modified_source'
    if current['source_status'] != 'verified':
        return 'review_source_transaction'
    if state['modified_receipt_sha256'] is None:
        return 'anchor_modified_source_receipt'
    if state['package_plan_sha256'] is None:
        return 'prepare_exact_package_plan'
    if current['package_status'] == 'interrupted_recovery_required':
        return 'recover_exact_package_generation'
    if current['package_status'] == 'absent':
        return 'build_exact_package_plan'
    if current['package_status'] != 'built_recorded':
        return 'review_package_generation'
    if state['package_receipt_sha256'] is None:
        return 'anchor_package_receipt'
    if state['install_plan_sha256'] is None:
        return 'prepare_exact_install_plan'
    if current['install_status'] == 'interrupted_recovery_required':
        return 'recover_exact_install_generation'
    if current['install_status'] == 'absent':
        return 'install_exact_generation'
    if current['install_status'] != 'installed_recorded':
        return 'review_install_generation'
    if state['install_receipt_sha256'] is None:
        return 'anchor_install_receipt'
    if current['runtime_status'] == 'absent':
        return 'promote_verified_installation'
    return 'use_owned_runtime_session'


def journey_status(directory: str | Path, *, trusted_journey_head: str | None = None) -> dict:
    """Read-only current source/package/install state and exact next action."""
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state = _open(target)
        current = _current(target, state)
        head = rows[-1]['record_sha256']
        return {'schema_version': '1.0', 'kind': 'template-delivery-journey-result-v1',
                'run_id': state['run_id'], 'stage': state['stage'],
                'journey_head_sha256': head,
                'evidence_trust': ('externally_anchored_history' if head == trusted_journey_head
                                   else 'recorded_untrusted'),
                'next_action': _next(state, current),
                'source': current['source_status'], 'package': current['package_status'],
                'installation': current['install_status'], 'runtime': current['runtime_status'],
                'runtime_session': str(target / 'runtime') if current['runtime_status'] != 'absent' else None,
                'anchors': {key: state[key] for key in (
                    'bundle_digest', 'baseline_receipt_sha256', 'modified_receipt_sha256',
                    'package_plan_sha256', 'package_receipt_sha256',
                    'install_plan_sha256', 'install_receipt_sha256', 'delivery_plan_sha256')}}


def record_journey(directory: str | Path, *, trusted_journey_head: str,
                   stage: str, plan: dict | None = None,
                   receipt: dict | None = None,
                   trusted_receipt_sha256: str | None = None) -> dict:
    """Pin one externally retained receipt or exact plan, without effects."""
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state = _open(target)
        if rows[-1]['record_sha256'] != trusted_journey_head:
            raise DeliveryError('externally_retained_journey_head_required')
        current = _current(target, state)
        if stage == 'baseline_anchored':
            if (state['baseline_receipt_sha256'] is not None or plan is not None
                    or receipt is not None or current['source_status'] != 'planned'):
                raise DeliveryError('journey_baseline_stage_unavailable')
            baseline = Path(state['bundle']) / 'baseline-receipt.json'
            _owned_file(baseline, maximum=2_000_000)
            if (file_hash(baseline) != trusted_receipt_sha256
                    or read_json(baseline).get('status') != 'passed'):
                raise DeliveryError('journey_baseline_receipt_untrusted_or_failed')
            state['baseline_receipt_sha256'] = trusted_receipt_sha256
        elif stage == 'source_verified':
            if (state['baseline_receipt_sha256'] is None or plan is not None
                    or receipt is not None or current['source_status'] != 'applied_unverified'):
                raise DeliveryError('journey_modified_stage_unavailable')
            state['modified_receipt_sha256'] = trusted_receipt_sha256
            verified = _source_status(state)
            if (verified['status'] != 'verified'
                    or verified['receipt_trust'] != 'externally_anchored_execution'):
                raise DeliveryError('journey_modified_receipt_untrusted_or_failed')
        elif stage == 'package_planned':
            if (state['modified_receipt_sha256'] is None or current['source_status'] != 'verified'
                    or state['package_plan_sha256'] is not None or plan is None
                    or receipt is not None or trusted_receipt_sha256 is not None):
                raise DeliveryError('journey_package_plan_stage_unavailable')
            if _package_plan(state, plan) != plan:
                raise DeliveryError('journey_package_plan_changed')
            _archive(target, plan, plan['plan_sha256'])
            state['package_plan_sha256'] = plan['plan_sha256']
        elif stage == 'package_built':
            if (state['package_plan_sha256'] is None or state['package_receipt_sha256'] is not None
                    or current['package_status'] != 'built_recorded' or plan is not None
                    or receipt is None):
                raise DeliveryError('journey_package_receipt_stage_unavailable')
            package_plan = _load_plan(target, state['package_plan_sha256'])
            path = Path(package_plan['request']['package_directory']) / 'package-receipt.json'
            _owned_file(path, maximum=2_000_000)
            if (read_json(path) != receipt
                    or receipt.get('receipt_sha256') != trusted_receipt_sha256):
                raise DeliveryError('journey_package_receipt_untrusted')
            state['package_receipt_sha256'] = trusted_receipt_sha256
        elif stage == 'install_planned':
            if (state['package_receipt_sha256'] is None or state['install_plan_sha256'] is not None
                    or plan is None or receipt is not None or trusted_receipt_sha256 is not None):
                raise DeliveryError('journey_install_plan_stage_unavailable')
            package_plan = _load_plan(target, state['package_plan_sha256'])
            package_receipt = read_json(Path(package_plan['request']['package_directory']) /
                                        'package-receipt.json')
            if (_install_plan(state, package_plan, package_receipt) != plan
                    or plan['package_receipt']['receipt_sha256'] != state['package_receipt_sha256']):
                raise DeliveryError('journey_install_plan_changed')
            _archive(target, plan, plan['plan_sha256'])
            state['install_plan_sha256'] = plan['plan_sha256']
        elif stage == 'installed':
            if (state['install_plan_sha256'] is None or state['install_receipt_sha256'] is not None
                    or current['install_status'] != 'installed_recorded'
                    or plan is not None or receipt is not None):
                raise DeliveryError('journey_install_receipt_stage_unavailable')
            install_plan = _load_plan(target, state['install_plan_sha256'])
            path = (Path(install_plan['environment_parent']) /
                    ('jev-env-' + install_plan['plan_sha256'][:24]) / 'install-receipt.json')
            _owned_file(path, maximum=2_000_000)
            if read_json(path).get('receipt_sha256') != trusted_receipt_sha256:
                raise DeliveryError('journey_install_receipt_untrusted')
            state['install_receipt_sha256'] = trusted_receipt_sha256
        else:
            raise DeliveryError('journey_stage_unsupported')
        state['stage'] = stage
        head = _append(target, rows, stage, state)
    return journey_status(target, trusted_journey_head=head)


def promote_journey(directory: str | Path, *, trusted_journey_head: str,
                    observation: dict, launch_environment: dict[str, str] | None = None) -> dict:
    """Select an installed generation for the same run, without launching it."""
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state = _open(target)
        if rows[-1]['record_sha256'] != trusted_journey_head:
            raise DeliveryError('externally_retained_journey_head_required')
        current = _current(target, state)
        if (state['install_receipt_sha256'] is None
                or current['install_status'] != 'installed_recorded'):
            raise DeliveryError('journey_verified_installation_required')
        if state['delivery_plan_sha256'] is not None:
            delivery_plan = _load_plan(target, state['delivery_plan_sha256'])
            if (observation != delivery_plan['observation']
                    or (launch_environment or {}) != delivery_plan['launch_environment']):
                raise DeliveryError('journey_pending_promotion_plan_changed')
        else:
            install_plan = _load_plan(target, state['install_plan_sha256'])
            delivery_plan = plan_delivery(install_plan,
                trusted_install_receipt_sha256=state['install_receipt_sha256'],
                observation=observation, launch_environment=launch_environment)
            _archive(target, delivery_plan, delivery_plan['plan_sha256'])
            state['delivery_plan_sha256'] = delivery_plan['plan_sha256']
            state['stage'] = 'promotion_pending'
            _append(target, rows, 'promotion_pending', state)
        runtime = target / 'runtime'
        if runtime.exists():
            existing = session_status(runtime)
            if existing['run_id'] != state['run_id']:
                raise DeliveryError('journey_runtime_run_identity_changed')
            if read_json(runtime / 'delivery-plan.json') != delivery_plan:
                raise DeliveryError('journey_runtime_plan_changed')
        else:
            create_session(runtime, delivery_plan, run_id=state['run_id'])
        state['stage'] = 'runtime_session'
        head = _append(target, rows, 'runtime_session', state)
    return journey_status(target, trusted_journey_head=head)
