"""Bounded native Windows generation cutover with retained owned installs."""
from __future__ import annotations

from pathlib import Path
import uuid

from packaging.version import InvalidVersion, Version

from . import capabilities as cap
from .contracts import validate_contract
from .io import InputError, digest, loads
from .windows_template_install import (
    owned_windows_install_receipt, plan_windows_template_install,
)
from .windows_template_owned import (
    check_private_directory, create_private_directory, read_private_json,
    write_private_json_exclusive,
)
from .windows_template_session import (
    _checked_session, _environment, create_windows_template_session,
    windows_session_status,
)


_RECORDS = {
    'run': 'windows-template-run-v1',
    'intent': 'windows-template-run-intent-v1',
    'generation': 'windows-template-run-generation-v1',
    'selection': 'windows-template-run-selection-v1',
}
_ACTIONS = ('initial', 'upgrade', 'rollback')


def _event(owned: dict, name: str, kind: str) -> dict | None:
    path = Path(owned['path']) / name
    if not path.exists():
        return None
    row = read_private_json(owned, name)
    validate_contract(row, _RECORDS[kind])
    if row['record_sha256'] != digest({k: v for k, v in row.items()
                                       if k != 'record_sha256'}):
        raise InputError('windows_run_record_changed')
    return row


def _write(owned: dict, name: str, kind: str, body: dict) -> dict:
    row = {'schema_version': '1.0', 'kind': _RECORDS[kind], **body}
    row['record_sha256'] = digest(row)
    validate_contract(row, _RECORDS[kind])
    write_private_json_exclusive(owned, name, row)
    return row


def _open(directory: str | Path) -> tuple[Path, dict, dict]:
    root = Path(directory)
    try:
        candidate = loads(cap._windows_secure_input(root / 'run.json', 1_000_000))
        owned = candidate['owned_directory']
        check_private_directory(owned)
    except (OSError, KeyError, TypeError, ValueError, cap.CapabilityError):
        raise InputError('windows_run_owner_unavailable') from None
    if owned['path'] != str(root):
        raise InputError('windows_run_owner_changed')
    run = _event(owned, 'run.json', 'run')
    if run != candidate:
        raise InputError('windows_run_owner_changed')
    return root, owned, run


def _metadata(plan: dict, receipt: dict, trusted_receipt_sha256: str) -> dict:
    if plan != plan_windows_template_install(
            plan['package_plan'], plan['package_receipt'], trusted_package_receipt_sha256=
            plan['trusted_package_receipt_sha256']):
        raise InputError('windows_run_install_plan_drift')
    canonical = owned_windows_install_receipt(plan, trusted_receipt_sha256)
    if receipt != canonical:
        raise InputError('windows_run_install_receipt_substituted')
    package = plan['package_plan']['inputs']
    return {'install_plan_sha256': plan['plan_sha256'],
            'install_receipt_sha256': trusted_receipt_sha256,
            'environment': canonical['environment'],
            'project_name': package['project_name'],
            'project_version': package['project_version'],
            'source_sha256': package['source_sha256']}


def _disjoint_run_root(root: Path, plan: dict) -> None:
    request = plan['package_plan']['request']
    for name in ('host_root', 'implementation_bundle', 'template_directory',
                 'wheelhouse', 'output_parent', 'environment_parent'):
        other = Path(request[name])
        if cap._path_is_within(root, other) or cap._path_is_within(other, root):
            raise InputError('windows_run_overlaps_delivery_inputs_or_outputs')


def _selection(owned: dict, sequence: int, run_id: str) -> dict | None:
    row = _event(owned, f'selection-{sequence:03d}.json', 'selection')
    if row is None:
        return None
    if (row['sequence'] != sequence or row['run_id'] != run_id
            or row['action'] != _ACTIONS[sequence]):
        raise InputError('windows_run_selection_sequence_changed')
    generation = _event(owned, f'generation-{sequence:03d}.json', 'generation')
    if generation is None or row['generation_sha256'] != generation['record_sha256']:
        raise InputError('windows_run_generation_selection_changed')
    if (generation['run_id'] != run_id or generation['sequence'] != sequence
            or generation['action'] != row['action']
            or generation['session']['run_id'] != run_id):
        raise InputError('windows_run_generation_identity_changed')
    if sequence == 0:
        if row['previous_selection_sha256'] is not None:
            raise InputError('windows_run_selection_chain_changed')
    else:
        previous = _selection(owned, sequence - 1, run_id)
        if previous is None or row['previous_selection_sha256'] != previous['record_sha256']:
            raise InputError('windows_run_selection_chain_changed')
    return row


def _current(owned: dict, run_id: str) -> tuple[int | None, dict | None]:
    current = None
    index = None
    for sequence in range(3):
        row = _selection(owned, sequence, run_id)
        if row is None:
            if any((Path(owned['path']) / f'selection-{later:03d}.json').exists()
                   for later in range(sequence + 1, 3)):
                raise InputError('windows_run_selection_order_changed')
            break
        current, index = row, sequence
    return index, current


def _intent(owned: dict, sequence: int, run_id: str) -> dict | None:
    row = _event(owned, f'intent-{sequence:03d}.json', 'intent')
    if row is not None and (row['sequence'] != sequence or row['run_id'] != run_id
                            or row['action'] != _ACTIONS[sequence]):
        raise InputError('windows_run_intent_sequence_changed')
    return row


def windows_template_run_status(directory: str | Path, *,
                                trusted_selection_sha256: str | None = None) -> dict:
    """Read-only current selection and incomplete stage, without target import."""
    root, owned, run = _open(directory)
    index, selected = _current(owned, run['run_id'])
    pending_index = 0 if index is None else index + 1
    pending = _intent(owned, pending_index, run['run_id']) if pending_index < 3 else None
    if pending is not None and pending['previous_selection_sha256'] != (
            selected['record_sha256'] if selected else None):
        raise InputError('windows_run_pending_chain_changed')
    if selected is None:
        return {'status': 'pending_initial' if pending else 'blocked_recovery',
                'run_id': run['run_id'], 'pending_intent_sha256':
                pending['record_sha256'] if pending else None,
                'selection_trust': 'absent'}
    generation = _event(owned, f'generation-{index:03d}.json', 'generation')
    session = generation['session']
    if session['run_id'] != run['run_id']:
        raise InputError('windows_run_session_identity_changed')
    _checked_session(session, check_executables=False)
    child = windows_session_status(session)
    anchored = trusted_selection_sha256 == selected['record_sha256']
    return {'status': ('pending_' + pending['action'] if pending else 'selected'),
            'run_id': run['run_id'], 'sequence': index,
            'selected_version': generation['project_version'],
            'selected_environment': generation['environment'],
            'selected_session_sha256': session['session_sha256'],
            'selected_session': session if anchored else None,
            'selected_session_status': child['status'],
            'selection_sha256': selected['record_sha256'],
            'selection_trust': ('externally_anchored' if anchored else 'recorded_untrusted'),
            'pending_intent_sha256': pending['record_sha256'] if pending else None}


def _existing_or_new_session(root: Path, run: dict, intent: dict,
                             plan: dict, receipt: dict, launch_environment: dict) -> dict:
    child_path = Path(intent['session_path'])
    if child_path != root / f'session-{intent["sequence"]:03d}':
        raise InputError('windows_run_session_path_changed')
    if child_path.exists():
        try:
            candidate = loads(cap._windows_secure_input(child_path / 'session.json', 1_000_000))
            session = candidate
            _checked_session(session)
        except (OSError, KeyError, TypeError, ValueError, cap.CapabilityError):
            raise InputError('windows_run_partial_session_requires_review') from None
        canonical = owned_windows_install_receipt(plan, intent['install_receipt_sha256'])
        installed = canonical['installed']
        if (session['owned_directory']['path'] != str(child_path)
                or session['run_id'] != run['run_id']
                or session['install_plan_sha256'] != intent['install_plan_sha256']
                or session['install_receipt_sha256'] != intent['install_receipt_sha256']
                or session['install_environment'] != canonical['environment']
                or session['python'] != installed['python']
                or session['python_sha256'] != installed['python_sha256']
                or session['console_script'] != installed['console_script']
                or session['console_script_sha256'] != installed['console_script_sha256']
                or session['launch_environment'] != launch_environment
                or windows_session_status(session)['status'] != 'created'):
            raise InputError('windows_run_existing_session_changed')
        return session
    return create_windows_template_session(
        child_path, plan, receipt,
        trusted_install_receipt_sha256=intent['install_receipt_sha256'],
        launch_environment=launch_environment, run_id=run['run_id'])


def _complete_stage(root: Path, owned: dict, run: dict, intent: dict,
                    plan: dict, receipt: dict) -> dict:
    sequence = intent['sequence']
    if _selection(owned, sequence, run['run_id']) is not None:
        raise InputError('windows_run_stage_already_selected')
    metadata = _metadata(plan, receipt, intent['install_receipt_sha256'])
    _disjoint_run_root(root, plan)
    if any(metadata[key] != intent[key] for key in metadata):
        raise InputError('windows_run_intent_plan_drift')
    session = _existing_or_new_session(root, run, intent, plan, receipt,
                                       intent['launch_environment'])
    body = {'run_id': run['run_id'], 'sequence': sequence,
            'action': intent['action'], 'session': session, **metadata}
    generation = _event(owned, f'generation-{sequence:03d}.json', 'generation')
    if generation is None:
        generation = _write(owned, f'generation-{sequence:03d}.json', 'generation', body)
    elif {k: v for k, v in generation.items() if k not in
          ('schema_version', 'kind', 'record_sha256')} != body:
        raise InputError('windows_run_generation_changed')
    selected = _write(owned, f'selection-{sequence:03d}.json', 'selection',
                      {'run_id': run['run_id'], 'sequence': sequence,
                       'action': intent['action'],
                       'generation_sha256': generation['record_sha256'],
                       'previous_selection_sha256': intent['previous_selection_sha256']})
    return windows_template_run_status(root, trusted_selection_sha256=
                                       selected['record_sha256'])


def _start_stage(root: Path, owned: dict, run: dict, sequence: int, action: str,
                 previous: str | None, plan: dict, receipt: dict,
                 trusted_receipt_sha256: str, launch_environment: dict) -> dict:
    metadata = _metadata(plan, receipt, trusted_receipt_sha256)
    _disjoint_run_root(root, plan)
    _environment(root, Path(receipt['installed']['python']), launch_environment)
    if _intent(owned, sequence, run['run_id']) is not None:
        raise InputError('windows_run_stage_already_attempted')
    intent = _write(owned, f'intent-{sequence:03d}.json', 'intent',
                    {'run_id': run['run_id'], 'sequence': sequence,
                     'action': action, 'previous_selection_sha256': previous,
                     'session_path': str(root / f'session-{sequence:03d}'),
                     'launch_environment': launch_environment, **metadata})
    return _complete_stage(root, owned, run, intent, plan, receipt)


def create_windows_template_run(directory: str | Path, install_plan: dict,
                                install_receipt: dict, *,
                                trusted_install_receipt_sha256: str,
                                launch_environment: dict | None = None) -> dict:
    """Create one run and its first retained installed generation."""
    launch_environment = {} if launch_environment is None else launch_environment
    metadata = _metadata(install_plan, install_receipt, trusted_install_receipt_sha256)
    root = Path(directory)
    _environment(root, Path(install_receipt['installed']['python']), launch_environment)
    _disjoint_run_root(root, install_plan)
    owned = create_private_directory(root)
    run = _write(owned, 'run.json', 'run',
                 {'run_id': str(uuid.uuid4()), 'owned_directory': owned,
                  'mode': 'off', 'maximum_generations': 3})
    return _start_stage(root, owned, run, 0, 'initial', None, install_plan,
                        install_receipt, trusted_install_receipt_sha256,
                        launch_environment)


def upgrade_windows_template_run(directory: str | Path, old_plan: dict,
                                 new_plan: dict, new_receipt: dict, *,
                                 approved_selection_sha256: str,
                                 trusted_new_receipt_sha256: str,
                                 launch_environment: dict | None = None) -> dict:
    """Cut over to a strictly newer, disjoint installed version after stop."""
    root, owned, run = _open(directory)
    index, selected = _current(owned, run['run_id'])
    if index != 0 or selected['record_sha256'] != approved_selection_sha256:
        raise InputError('windows_run_exact_upgrade_scope_required')
    old = _event(owned, 'generation-000.json', 'generation')
    if old_plan['plan_sha256'] != old['install_plan_sha256']:
        raise InputError('windows_run_old_plan_changed')
    old_session = old['session']
    if windows_session_status(old_session)['status'] != 'stopped':
        raise InputError('windows_run_old_generation_must_stop')
    old_receipt = owned_windows_install_receipt(old_plan, old['install_receipt_sha256'])
    old_metadata = _metadata(old_plan, old_receipt, old['install_receipt_sha256'])
    if any(old_metadata[key] != old[key] for key in old_metadata):
        raise InputError('windows_run_old_generation_drift')
    metadata = _metadata(new_plan, new_receipt, trusted_new_receipt_sha256)
    if (metadata['project_name'] != old['project_name']
            or metadata['environment'] == old['environment']
            or cap._path_is_within(Path(metadata['environment']), Path(old['environment']))
            or cap._path_is_within(Path(old['environment']), Path(metadata['environment']))):
        raise InputError('windows_run_upgrade_generation_incompatible')
    try:
        if Version(metadata['project_version']) <= Version(old['project_version']):
            raise InputError('windows_run_upgrade_version_not_newer')
    except InvalidVersion:
        raise InputError('windows_run_upgrade_version_invalid') from None
    return _start_stage(root, owned, run, 1, 'upgrade', selected['record_sha256'],
                        new_plan, new_receipt, trusted_new_receipt_sha256,
                        {} if launch_environment is None else launch_environment)


def rollback_windows_template_run(directory: str | Path, retained_plan: dict,
                                  retained_receipt: dict, *,
                                  approved_selection_sha256: str,
                                  trusted_retained_receipt_sha256: str,
                                  launch_environment: dict | None = None) -> dict:
    """Select the retained old install through a fresh session after new stop."""
    root, owned, run = _open(directory)
    index, selected = _current(owned, run['run_id'])
    if index != 1 or selected['record_sha256'] != approved_selection_sha256:
        raise InputError('windows_run_exact_rollback_scope_required')
    current = _event(owned, 'generation-001.json', 'generation')
    original = _event(owned, 'generation-000.json', 'generation')
    if windows_session_status(current['session'])['status'] != 'stopped':
        raise InputError('windows_run_new_generation_must_stop')
    metadata = _metadata(retained_plan, retained_receipt,
                         trusted_retained_receipt_sha256)
    if any(metadata[key] != original[key] for key in metadata):
        raise InputError('windows_run_retained_generation_drift')
    return _start_stage(root, owned, run, 2, 'rollback', selected['record_sha256'],
                        retained_plan, retained_receipt,
                        trusted_retained_receipt_sha256,
                        {} if launch_environment is None else launch_environment)


def resume_windows_template_run(directory: str | Path, install_plan: dict,
                                install_receipt: dict, *,
                                approved_intent_sha256: str,
                                trusted_install_receipt_sha256: str) -> dict:
    """Finish only an already recorded stage in the same run, without launch."""
    root, owned, run = _open(directory)
    index, selected = _current(owned, run['run_id'])
    sequence = 0 if index is None else index + 1
    if sequence >= 3:
        raise InputError('windows_run_no_pending_stage')
    intent = _intent(owned, sequence, run['run_id'])
    if intent is None or intent['record_sha256'] != approved_intent_sha256:
        raise InputError('windows_run_exact_pending_intent_required')
    previous = None if selected is None else selected['record_sha256']
    if intent['previous_selection_sha256'] != previous:
        raise InputError('windows_run_pending_chain_changed')
    if intent['install_receipt_sha256'] != trusted_install_receipt_sha256:
        raise InputError('windows_run_pending_receipt_changed')
    if sequence > 0:
        prior = _event(owned, f'generation-{sequence - 1:03d}.json', 'generation')
        if windows_session_status(prior['session'])['status'] != 'stopped':
            raise InputError('windows_run_prior_generation_must_stop')
    return _complete_stage(root, owned, run, intent, install_plan, install_receipt)
