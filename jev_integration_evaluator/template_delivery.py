"""Owned, recoverable delivery of a verified installed console host.

This module deliberately keeps delivery evidence apart from implementation and
installation receipts.  It never turns an installer receipt into a launch or a
provider qualification claim.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import copy
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import sys
import time
import uuid
from typing import Iterator

from .io import InputError, canonical, digest, file_hash, read_json, write_json
from .contracts import parse_utc, validate_contract
from .template_installation import installation_status, plan_install
from .integrations.lifecycle import implementation_status, rollback_implementation


class DeliveryError(InputError):
    """A delivery precondition or ownership invariant failed."""


_FIELDS = ('generated', 'applied', 'installed', 'launched', 'ready',
           'entrypoint_reached', 'integration_reachable', 'provider_reachable',
           'mode_authorized', 'outcome_verified')
_EVENTS = ('created', 'launch_pending', 'launched', 'observed',
           'stop_pending', 'stopped', 'disabled', 'rollback_pending',
           'rolled_back', 'upgrade_staged', 'blocked_recovery')
_MAX_EVENTS = 256
_NEXT_ACTIONS = frozenset({
    'supply_exact_launch_scope', 'supply_fresh_exact_launch_scope',
    'supply_fresh_off_mode_launch_scope', 'observe_independent_host_postconditions',
    'disable_or_review_outcome', 'disable_or_upgrade', 'review_stopped_session',
    'reconcile_pending', 'supply_externally_retained_session_head',
    'review_live_process_and_reconcile', 'review_outcomes_and_owned_rollback',
    'retain_owned_generation_for_review', 'review_unknown_launch_effects',
    'review_exact_owned_rollback_state'})
_HELPER = '''import os,sys
fd=int(sys.argv[1]); executable=sys.argv[2]; cwd=sys.argv[3]
try: signal=os.read(fd,1)
finally: os.close(fd)
if signal != b'G': os._exit(125)
os.chdir(cwd)
os.execv(executable,[executable])
'''


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _linux_profile() -> None:
    if (sys.platform != 'linux' or platform.machine().lower() != 'x86_64'
            or sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 13)):
        raise DeliveryError('delivery_profile_requires_linux_x86_64_cpython_3_13')


def _safe_directory(path: str | Path, *, exists: bool) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute() or any(part.is_symlink() for part in (candidate, *candidate.parents)):
        raise DeliveryError('delivery_directory_must_be_absolute_without_symlinks')
    candidate = candidate.resolve(strict=False)
    if exists and (not candidate.is_dir() or candidate.is_symlink()):
        raise DeliveryError('delivery_directory_unavailable')
    if not exists and candidate.exists():
        raise DeliveryError('delivery_directory_already_exists')
    return candidate


def _private(path: Path) -> None:
    try:
        info = path.stat()
    except OSError:
        raise DeliveryError('delivery_directory_unavailable') from None
    if (not stat.S_ISDIR(info.st_mode) or path.is_symlink()
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise DeliveryError('delivery_directory_not_owner_private')


def _owned_file(path: Path, *, maximum: int) -> None:
    """Check local journal inputs before treating their bytes as owned state."""
    if path.is_symlink():
        raise DeliveryError('delivery_state_file_invalid')
    try:
        info = path.stat()
    except OSError:
        raise DeliveryError('delivery_state_file_unavailable') from None
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077
            or info.st_size > maximum):
        raise DeliveryError('delivery_state_file_invalid')


def _boot_id() -> str:
    try:
        value = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
    except OSError:
        raise DeliveryError('linux_boot_identity_unavailable') from None
    if not value:
        raise DeliveryError('linux_boot_identity_unavailable')
    return value


def _process_info(pid: int) -> tuple[str, str] | None:
    """Linux process start ticks; PID alone may refer to a different process."""
    try:
        raw = Path(f'/proc/{pid}/stat').read_text(encoding='ascii')
        suffix = raw[raw.rfind(')') + 2:].split()
        return suffix[19], suffix[0]  # proc fields 22 and 3.
    except (OSError, IndexError, ValueError):
        return None


def _process_alive(identity: dict | None) -> bool:
    if not identity or identity['boot_id'] != _boot_id():
        return False
    info = _process_info(identity['pid'])
    return bool(info and info[0] == identity['start_ticks'] and info[1] not in ('Z', 'X', 'x'))


def _signal_owned(identity: dict, signum: int) -> None:
    """Use a Linux pidfd so PID reuse cannot redirect a stop request."""
    if identity['boot_id'] != _boot_id():
        raise DeliveryError('delivery_process_identity_unavailable')
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        fd = os.pidfd_open(identity['pid'], 0) if hasattr(os, 'pidfd_open') else int(
            libc.syscall(434, identity['pid'], 0))
    except ProcessLookupError:
        return
    if fd < 0:
        error = ctypes.get_errno()
        if error == 3:  # ESRCH
            return
        raise DeliveryError('delivery_pidfd_unavailable')
    try:
        info = _process_info(identity['pid'])
        if info is None or info[0] != identity['start_ticks']:
            raise DeliveryError('delivery_process_identity_changed')
        if info[1] in ('Z', 'X', 'x'):
            return
        if hasattr(signal, 'pidfd_send_signal'):
            signal.pidfd_send_signal(fd, signum)
        elif libc.syscall(424, fd, int(signum), None, 0) != 0:
            if ctypes.get_errno() != 3:
                raise DeliveryError('delivery_pidfd_signal_failed')
    except ProcessLookupError:
        return
    finally:
        os.close(fd)


def _execed_console(identity: dict, executable: str) -> bool:
    if not _process_alive(identity):
        return False
    try:
        args = Path(f"/proc/{identity['pid']}/cmdline").read_bytes().split(b'\x00')
    except OSError:
        return False
    # The waiting helper contains the console path later in its argv.  A
    # shebang console exec presents it as argv[1] of its interpreter.
    return len(args) > 1 and args[1] == os.fsencode(executable)


def _probe_hash(path: Path) -> str | None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise DeliveryError('delivery_observation_symlink')
    if not path.exists():
        return None
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1_000_000:
        raise DeliveryError('delivery_observation_file_invalid_or_oversize')
    return file_hash(path)


def _current_observation(plan: dict, role: str, alive: bool,
                         identity: dict | None) -> bool:
    if not alive:
        return False
    try:
        return any(row['role'] == role and _probe_hash(Path(row['path'])) == row['expected_sha256']
                   and _process_alive(identity) for row in plan['observation']['checks'])
    except (DeliveryError, OSError):
        return False


def _receipt(plan: dict, trusted_sha256: str) -> dict:
    """Re-read installer-owned bytes; the caller retains the digest elsewhere."""
    composite = plan.get('kind') == 'template-composite-install-plan-v1'
    validate_contract(plan, 'template-composite-install-plan-v1' if composite
                      else 'template-install-plan-v1')
    if composite:
        from .template_installation import (plan_composite_install,
                                            composite_installation_status)
        planner, status = plan_composite_install, composite_installation_status
    else:
        planner, status = plan_install, installation_status
    if planner(plan['package_plan'], plan['package_receipt']) != plan:
        raise DeliveryError('delivery_source_or_install_plan_drift')
    root = Path(plan['environment_parent']) / ('jev-env-' + plan['plan_sha256'][:24])
    if root.is_symlink() or not (root / 'install-receipt.json').is_file():
        raise DeliveryError('installed_receipt_unavailable')
    receipt = read_json(root / 'install-receipt.json')
    validate_contract(receipt, 'template-composite-install-receipt-v1' if composite
                      else 'template-install-receipt-v1')
    if receipt['receipt_sha256'] != trusted_sha256 or digest({
            key: value for key, value in receipt.items() if key != 'receipt_sha256'}) != trusted_sha256:
        raise DeliveryError('externally_retained_install_receipt_required')
    if status(plan)['status'] != 'installed_recorded':
        raise DeliveryError('installed_generation_drift_or_unverified')
    if receipt['plan_sha256'] != plan['plan_sha256'] or receipt['mode'] != 'off':
        raise DeliveryError('installer_receipt_binding_changed')
    return receipt


def plan_delivery(install_plan: dict, *, trusted_install_receipt_sha256: str,
                  observation: dict, launch_environment: dict[str, str] | None = None) -> dict:
    """Make a source and installation bound, effect-free launch plan.

    Observation is an independently authored schedule of exact regular-file
    postconditions.  It is never loaded from the generated bundle or host output.
    """
    _linux_profile()
    receipt = _receipt(install_plan, trusted_install_receipt_sha256)
    validate_contract(observation, 'template-delivery-observation-v1')
    ready_paths = {row['path'] for row in observation['checks'] if row['role'] == 'ready'}
    entrypoint_paths = {row['path'] for row in observation['checks']
                        if row['role'] == 'entrypoint_reached'}
    integration_paths = {row['path'] for row in observation['checks']
                         if row['role'] == 'integration_reachable'}
    if (not ready_paths or not entrypoint_paths or not integration_paths
            or ready_paths & integration_paths):
        raise DeliveryError('readiness_and_integration_require_independent_checks')
    launch_environment = copy.deepcopy(launch_environment or {})
    if (type(launch_environment) is not dict or len(launch_environment) > 16
            or any(type(key) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key)
                   or key.startswith(('PYTHON', 'PIP_', 'VIRTUAL_ENV', 'JEV_'))
                   or key in ('PATH', 'HOME')
                   or re.search(r'(?i)(secret|password|token|api[_-]?key|credential)', key)
                   or type(value) is not str or len(value) > 4096 or '\x00' in value
                   for key, value in launch_environment.items())):
        raise DeliveryError('delivery_launch_environment_invalid_or_sensitive')
    environment = Path(receipt['environment'])
    request = install_plan.get('package_plan', {}).get('request', {})
    protected_roots = [environment]
    for name in ('host_root', 'implementation_bundle', 'package_directory',
                 'environment_parent', 'wheelhouse'):
        if type(request.get(name)) is str:
            protected_roots.append(Path(request[name]))
    for row in observation['checks']:
        path = Path(row['path'])
        if (not path.is_absolute()
                or any(path == root or path.is_relative_to(root) for root in protected_roots)
                or any(part.is_symlink() for part in (path, *path.parents))):
            raise DeliveryError('delivery_observation_path_must_be_external_and_owned')
        if _probe_hash(path) != row['before_sha256']:
            raise DeliveryError('delivery_observation_baseline_drift')
        if row['before_sha256'] == row['expected_sha256']:
            raise DeliveryError('delivery_observation_has_no_expected_transition')
    executable = Path(receipt['installed']['console_script'])
    if (not executable.is_file() or executable.is_symlink()
            or file_hash(executable) != receipt['installed']['console_script_sha256']):
        raise DeliveryError('installed_console_script_drift')
    plan = {'schema_version': '1.0', 'kind': 'template-delivery-plan-v1',
            'install_plan': install_plan,
            'trusted_install_receipt_sha256': trusted_install_receipt_sha256,
            'generation_id': receipt['generation_id'],
            'environment': receipt['environment'],
            'console_script': str(executable),
            'console_script_sha256': file_hash(executable),
            'entrypoint_origin': receipt['installed']['entrypoint_origin'],
            'observation': copy.deepcopy(observation),
            'launch_environment': launch_environment,
            'requested_mode': 'off', 'runtime_activation_authorized': False}
    plan['plan_sha256'] = digest(plan)
    validate_contract(plan, 'template-delivery-plan-v1')
    return plan


def _check_plan(plan: dict) -> dict:
    validate_contract(plan, 'template-delivery-plan-v1')
    expected = digest({key: value for key, value in plan.items() if key != 'plan_sha256'})
    if plan['plan_sha256'] != expected:
        raise DeliveryError('delivery_plan_digest_changed')
    validate_contract(plan['observation'], 'template-delivery-observation-v1')
    receipt = _receipt(plan['install_plan'], plan['trusted_install_receipt_sha256'])
    if (receipt['generation_id'] != plan['generation_id'] or
            receipt['environment'] != plan['environment'] or
            receipt['installed']['console_script'] != plan['console_script'] or
            receipt['installed']['console_script_sha256'] != plan['console_script_sha256'] or
            receipt['installed']['entrypoint_origin'] != plan['entrypoint_origin']):
        raise DeliveryError('delivery_installation_binding_changed')
    if file_hash(Path(plan['console_script'])) != plan['console_script_sha256']:
        raise DeliveryError('delivery_executable_drift')
    return receipt


@contextmanager
def _locked(directory: Path) -> Iterator[None]:
    _linux_profile()
    _private(directory.parent)
    _private(directory)
    import fcntl
    lock = directory / 'session.lock'
    if lock.is_symlink():
        raise DeliveryError('delivery_lock_invalid')
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
            raise DeliveryError('delivery_lock_invalid')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeliveryError('delivery_session_owned_by_another_controller') from None
        yield
    finally:
        os.close(fd)


def _events(directory: Path) -> list[dict]:
    path = directory / 'events.jsonl'
    _owned_file(path, maximum=4_000_000)
    rows = []
    with path.open('rb') as stream:
        for line in stream:
            if len(line) > 16_384 or len(rows) >= _MAX_EVENTS:
                raise DeliveryError('delivery_journal_bound_exceeded')
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise DeliveryError('delivery_journal_torn_or_modified') from None
            if (type(row) is not dict or row.get('sequence') != len(rows)
                    or row.get('event') not in _EVENTS
                    or row.get('previous_sha256') != (rows[-1]['record_sha256'] if rows else None)
                    or row.get('record_sha256') != digest({k: v for k, v in row.items()
                                                           if k != 'record_sha256'})
                    or 'state' not in row):
                raise DeliveryError('delivery_journal_torn_or_modified')
            validate_contract(row['state'], 'template-delivery-session-v1')
            rows.append(row)
    if not rows:
        raise DeliveryError('delivery_journal_empty')
    return rows


def _open(directory: str | Path) -> tuple[Path, list[dict], dict, dict]:
    target = _safe_directory(directory, exists=True)
    _private(target)
    _private(target / 'plans')
    rows = _events(target)
    state = copy.deepcopy(rows[-1]['state'])
    plan_path = target / 'plans' / (state['plan_sha256'] + '.json')
    _owned_file(plan_path, maximum=4_000_000)
    plan = read_json(plan_path)
    if state['plan_sha256'] != plan['plan_sha256'] or state['generation_id'] != plan['generation_id']:
        raise DeliveryError('delivery_session_plan_changed')
    validate_contract(plan, 'template-delivery-plan-v1')
    if plan['plan_sha256'] != digest({key: value for key, value in plan.items()
                                     if key != 'plan_sha256'}):
        raise DeliveryError('delivery_session_plan_changed')
    return target, rows, state, plan


def _authority(scope: dict, approved_scope_sha256: str, head: str,
               state: dict, operation: str) -> None:
    validate_contract(scope, 'template-delivery-scope-v1')
    if (scope['scope_sha256'] != digest({k: v for k, v in scope.items() if k != 'scope_sha256'})
            or scope['scope_sha256'] != approved_scope_sha256
            or scope['run_id'] != state['run_id'] or scope['plan_sha256'] != state['plan_sha256']
            or scope['trusted_session_head'] != head or scope['revoked'] is True
            or scope['grants'][operation] is not True):
        raise DeliveryError('exact_delivery_scope_and_head_required')
    if parse_utc(scope['expires_at']) <= datetime.now(timezone.utc):
        raise DeliveryError('delivery_scope_expired')


def _source_transaction(plan: dict) -> tuple[str, str, str]:
    request = plan['install_plan']['package_plan']['request']
    return (request['host_root'], request['implementation_bundle'],
            request['trusted_modified_receipt_sha256'])


def _source_status(plan: dict) -> dict:
    source, bundle, anchor = _source_transaction(plan)
    if plan['install_plan']['kind'] == 'template-composite-install-plan-v1':
        from .integrations.composite import status_composite
        return status_composite(source, bundle, trusted_receipt_sha256=anchor)
    return implementation_status(source, bundle, trusted_receipt_sha256=anchor)


def _source_rollback(plan: dict, rollback_digest: str) -> dict:
    source, bundle, _ = _source_transaction(plan)
    if plan['install_plan']['kind'] == 'template-composite-install-plan-v1':
        from .integrations.composite import rollback_composite
        return rollback_composite(source, bundle, rollback_digest)
    return rollback_implementation(source, bundle, rollback_digest)


def launch_session(directory: str | Path, *, scope: dict,
                   approved_scope_sha256: str) -> dict:
    """Start exactly one installed console invocation behind a durable intent.

    The child waits on a private inherited pipe until its identity is durable.
    If the controller dies before releasing it, EOF prevents target execution.
    A crash after release may have executed the target and blocks replay.
    """
    _linux_profile()
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, plan = _open(target)
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state, 'launch')
        if state['disabled'] or state['pending'] or state['attempts']['launch'] >= 3:
            raise DeliveryError('delivery_launch_already_attempted_or_blocked')
        if _process_alive(state['process']):
            raise DeliveryError('delivery_process_already_running')
        _check_plan(plan)
        for row in plan['observation']['checks']:
            if _probe_hash(Path(row['path'])) != row['before_sha256']:
                raise DeliveryError('delivery_observation_baseline_drift')
        state['attempts']['launch'] += 1
        # This records the exact approved *off* mode.  It does not authorize
        # connected provider traffic or any later exposure expansion.
        state['observations']['mode_authorized'] = True
        state['stage'], state['pending'] = 'launch_pending', 'launch'
        _append(target, rows, 'launch_pending', state)
        read_fd, write_fd = os.pipe()
        child = None
        try:
            env = dict(plan['launch_environment'])
            env.update({'PATH': str(Path(plan['environment']) / 'venv/bin'),
                        'PYTHONNOUSERSITE': '1', 'JEV_RUNTIME_MODE': 'off'})
            child = subprocess.Popen([sys.executable, '-I', '-c', _HELPER,
                                      str(read_fd), plan['console_script'], plan['environment']],
                                     pass_fds=(read_fd,), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     close_fds=True, start_new_session=True, env=env,
                                     cwd=plan['environment'])
            os.close(read_fd)
            read_fd = -1
            start = None
            for _ in range(100):
                info = _process_info(child.pid)
                if info is not None:
                    start = info[0]
                    break
                time.sleep(0.001)
            if start is None:
                raise DeliveryError('delivery_child_identity_unavailable')
            state['process'] = {'pid': child.pid, 'boot_id': _boot_id(), 'start_ticks': start}
            state['stage'] = 'launched'
            state['observations']['launched'] = True
            _append(target, rows, 'launched', state)
            os.write(write_fd, b'G')
        except BaseException:
            # Closing the pipe before release stops the waiting child.  If the
            # release already happened, keep the durable pending intent: never
            # rerun a possibly effectful console command.
            raise
        finally:
            if read_fd != -1:
                os.close(read_fd)
            os.close(write_fd)
        state['stage'], state['pending'] = 'running', None
        head = _append(target, rows, 'observed', state)
        return _result(state, head, 'observe_independent_host_postconditions',
                       current_process_alive=_process_alive(state['process']), plan=plan)


def resume_session(directory: str | Path, *, trusted_session_head: str) -> dict:
    """Adopt only proven process state; never replay an uncertain invocation."""
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, plan = _open(target)
        if trusted_session_head != rows[-1]['record_sha256']:
            raise DeliveryError('externally_retained_session_head_required')
        if state['pending'] == 'launch':
            if state['process'] is None:
                # The helper's pipe could not have been released before its
                # process identity was journaled.  Closing the crashed owner
                # pipe prevents exec, so this attempt is safe to retry.
                state['stage'], state['pending'] = 'installed', None
                state['failures'].append('launch_unreleased')
                head = _append(target, rows, 'observed', state)
                return _result(state, head, 'supply_fresh_exact_launch_scope',
                               current_process_alive=False)
            if _execed_console(state['process'], plan['console_script']):
                state['stage'], state['pending'] = 'running', None
                head = _append(target, rows, 'observed', state)
                return _result(state, head, 'observe_independent_host_postconditions',
                               current_process_alive=True)
            state['stage'] = 'blocked_recovery'
            state['failures'].append('launch_outcome_unknown')
            head = _append(target, rows, 'blocked_recovery', state)
            return _result(state, head, 'review_unknown_launch_effects',
                           current_process_alive=_process_alive(state['process']))
        if state['pending'] in ('stop', 'stop_disable'):
            if _process_alive(state['process']):
                return _result(state, rows[-1]['record_sha256'],
                               'review_live_process_and_reconcile', current_process_alive=True)
            disabling = state['pending'] == 'stop_disable'
            state['stage'], state['pending'] = ('disabled' if disabling else 'stopped'), None
            state['disabled'] = disabling
            head = _append(target, rows, state['stage'], state)
            return _result(state, head, 'review_outcomes_and_owned_rollback',
                           current_process_alive=False)
        if state['pending'] == 'rollback':
            if state['generation_history']:
                previous = state['generation_history'][-1]
                old_file = target / 'plans' / (previous['plan_sha256'] + '.json')
                if old_file.is_symlink() or not old_file.is_file():
                    raise DeliveryError('previous_generation_plan_unavailable')
                old_plan = read_json(old_file)
                _check_plan(old_plan)
                state['generation_history'].pop()
                state['plan_sha256'] = old_plan['plan_sha256']
                state['generation_id'] = old_plan['generation_id']
                state['process'] = None
                state['disabled'] = False
                state['stage'], state['pending'] = 'rolled_back', None
                state['attempts'] = {'launch': 0, 'stop': 0}
                state['observations'] = {name: False for name in _FIELDS}
                state['observations'].update(generated=True, applied=True, installed=True)
                head = _append(target, rows, 'rolled_back', state)
                return _result(state, head, 'supply_fresh_off_mode_launch_scope',
                               current_process_alive=False)
            observed = _source_status(plan)
            if observed['status'] == 'rolled_back':
                state['stage'], state['pending'] = 'rolled_back', None
                head = _append(target, rows, 'rolled_back', state)
                return _result(state, head, 'retain_owned_generation_for_review',
                               current_process_alive=False)
            state['stage'] = 'blocked_recovery'
            head = _append(target, rows, 'blocked_recovery', state)
            return _result(state, head, 'review_exact_owned_rollback_state',
                           current_process_alive=False)
        return _result(state, rows[-1]['record_sha256'],
                       'observe_independent_host_postconditions' if _process_alive(state['process'])
                       else 'review_stopped_session',
                       current_process_alive=_process_alive(state['process']))


def observe_session(directory: str | Path, *, trusted_session_head: str) -> dict:
    """Check independently specified file bytes; never trust host success JSON."""
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, plan = _open(target)
        if trusted_session_head != rows[-1]['record_sha256']:
            raise DeliveryError('externally_retained_session_head_required')
        if state['stage'] not in ('running', 'launched', 'stop_pending', 'stopped'):
            raise DeliveryError('delivery_launch_not_recorded')
        findings = copy.deepcopy(state['observations'])
        alive = _process_alive(state['process'])
        for row in plan['observation']['checks']:
            if _probe_hash(Path(row['path'])) != row['expected_sha256']:
                continue
            if row['role'] == 'ready' and (not alive or not _process_alive(state['process'])):
                continue
            findings[row['role']] = True
        # Later loss of health does not erase a recorded observation, but the
        # current_process_alive field remains independently recomputed.
        if findings != state['observations']:
            state['observations'] = findings
            head = _append(target, rows, 'observed', state)
        else:
            head = rows[-1]['record_sha256']
        return _result(state, head, 'disable_or_review_outcome',
                       current_process_alive=alive, plan=plan)


def stop_session(directory: str | Path, *, scope: dict,
                 approved_scope_sha256: str, disable: bool = False,
                 grace_seconds: float = 5.0) -> dict:
    """Drain only the exact owned process; never signal a reused PID."""
    _linux_profile()
    if type(disable) is not bool or not (0 <= grace_seconds <= 30):
        raise DeliveryError('invalid_stop_policy')
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, plan = _open(target)
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state,
                   'disable' if disable else 'stop')
        if state['process'] is None or state['pending'] not in (None, 'stop', 'stop_disable'):
            raise DeliveryError('delivery_stop_requires_known_process')
        if state['pending'] is not None and (state['pending'] == 'stop_disable') != disable:
            raise DeliveryError('delivery_stop_pending_disposition_changed')
        if state['stage'] in ('stopped', 'disabled') and not _process_alive(state['process']):
            return _result(state, rows[-1]['record_sha256'], 'review_stopped_session',
                           current_process_alive=False)
        first_request = state['pending'] is None
        if first_request:
            state['attempts']['stop'] += 1
            state['stage'], state['pending'] = 'stop_pending', ('stop_disable' if disable else 'stop')
            _append(target, rows, 'stop_pending', state)
        if _process_alive(state['process']):
            deadline = time.monotonic() + grace_seconds
            while _process_alive(state['process']) and time.monotonic() < deadline:
                time.sleep(0.02)
        if _process_alive(state['process']):
            _signal_owned(state['process'], signal.SIGTERM)
            if first_request:
                state['failures'].append('bounded_drain_expired_process_signaled')
            _append(target, rows, 'observed', state)
            deadline = time.monotonic() + 1.0
            while _process_alive(state['process']) and time.monotonic() < deadline:
                time.sleep(0.02)
        if _process_alive(state['process']):
            return _result(state, rows[-1]['record_sha256'], 'review_live_process_and_reconcile',
                           current_process_alive=True)
        state['pending'] = None
        state['stage'] = 'disabled' if disable else 'stopped'
        state['disabled'] = disable
        head = _append(target, rows, 'disabled' if disable else 'stopped', state)
        return _result(state, head, 'review_outcomes_and_owned_rollback', current_process_alive=False)


def rollback_session(directory: str | Path, *, scope: dict,
                     approved_scope_sha256: str) -> dict:
    """Delegate exact owned source restoration after the console has stopped.

    The installed environment remains retained as historical evidence.  This
    operation never deletes a verified generation or edits unrelated source.
    """
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, plan = _open(target)
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state, 'rollback')
        if state['pending'] or state['stage'] not in ('stopped', 'disabled'):
            raise DeliveryError('delivery_rollback_requires_stopped_session')
        if _process_alive(state['process']):
            raise DeliveryError('delivery_rollback_process_still_alive')
        if state['generation_history']:
            previous = state['generation_history'][-1]
            expected = digest({'operation': 'restore_previous_owned_generation',
                               'current_plan_sha256': state['plan_sha256'],
                               'previous_plan_sha256': previous['plan_sha256'],
                               'run_id': state['run_id']})
            if scope.get('rollback_digest') != expected:
                raise DeliveryError('exact_previous_generation_rollback_required')
            old_file = target / 'plans' / (previous['plan_sha256'] + '.json')
            if old_file.is_symlink() or not old_file.is_file():
                raise DeliveryError('previous_generation_plan_unavailable')
            old_plan = read_json(old_file)
            _check_plan(old_plan)
            state['stage'], state['pending'] = 'rollback_pending', 'rollback'
            _append(target, rows, 'rollback_pending', state)
            state['generation_history'].pop()
            state['plan_sha256'] = old_plan['plan_sha256']
            state['generation_id'] = old_plan['generation_id']
            state['process'] = None
            state['disabled'] = False
            state['stage'], state['pending'] = 'rolled_back', None
            state['attempts'] = {'launch': 0, 'stop': 0}
            state['observations'] = {name: False for name in _FIELDS}
            state['observations'].update(generated=True, applied=True, installed=True)
            head = _append(target, rows, 'rolled_back', state)
            return _result(state, head, 'supply_fresh_off_mode_launch_scope',
                           current_process_alive=False)
        observed = _source_status(plan)
        if (observed['status'] != 'verified'
                or observed['receipt_trust'] != 'externally_anchored_execution'
                or scope.get('rollback_digest') != observed['rollback_digest']):
            raise DeliveryError('exact_verified_owned_rollback_required')
        state['stage'], state['pending'] = 'rollback_pending', 'rollback'
        _append(target, rows, 'rollback_pending', state)
        result = _source_rollback(plan, scope['rollback_digest'])
        if result['status'] != 'rolled_back':
            raise DeliveryError('owned_source_rollback_incomplete')
        state['stage'], state['pending'] = 'rolled_back', None
        head = _append(target, rows, 'rolled_back', state)
        return _result(state, head, 'retain_owned_generation_for_review',
                       current_process_alive=False)


def _append(directory: Path, rows: list[dict], event: str, state: dict) -> str:
    if event not in _EVENTS or len(rows) >= _MAX_EVENTS:
        raise DeliveryError('delivery_journal_bound_exceeded')
    validate_contract(state, 'template-delivery-session-v1')
    row = {'sequence': len(rows), 'previous_sha256': rows[-1]['record_sha256'] if rows else None,
           'event': event, 'at': _now(), 'state': copy.deepcopy(state)}
    row['record_sha256'] = digest(row)
    path = directory / 'events.jsonl'
    _owned_file(path, maximum=4_000_000)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(row) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        raise
    rows.append(row)
    return row['record_sha256']


def _publish_exact(path: Path, raw: bytes) -> None:
    """Publish only complete bytes; a matching write prefix can be retried."""
    pending = path.with_name(path.name + '.pending')
    _pending_prefix(pending, raw, remove=True)
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(pending, path, follow_symlinks=False)
    pending.unlink()
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _pending_prefix(path: Path, raw: bytes, *, remove: bool = False) -> None:
    if path.exists() or path.is_symlink():
        _owned_file(path, maximum=len(raw))
        if not raw.startswith(path.read_bytes()):
            raise DeliveryError('delivery_pending_plan_unknown_bytes')
        if remove:
            path.unlink()


def _write_plan_immutable(directory: Path, plan: dict) -> None:
    parent = directory / 'plans'
    _private(parent)
    path = parent / (plan['plan_sha256'] + '.json')
    _pending_prefix(path.with_name(path.name + '.pending'), canonical(plan) + b'\n',
                    remove=path.exists())
    if path.exists():
        _owned_file(path, maximum=4_000_000)
        if read_json(path) != plan:
            raise DeliveryError('delivery_plan_archive_collision')
        return
    _publish_exact(path, canonical(plan) + b'\n')


def create_session(directory: str | Path, plan: dict, *, run_id: str | None = None) -> dict:
    """Create a private session with no target execution or installation."""
    if run_id is not None:
        try:
            if str(uuid.UUID(run_id)) != run_id:
                raise ValueError
        except (ValueError, TypeError):
            raise DeliveryError('invalid_existing_delivery_run_id') from None
    _check_plan(plan)
    target = _safe_directory(directory, exists=False)
    if target == Path(plan['environment']) or target.is_relative_to(Path(plan['environment'])):
        raise DeliveryError('delivery_session_overlaps_installed_generation')
    if not target.parent.is_dir():
        raise DeliveryError('delivery_session_parent_missing')
    _private(target.parent)
    target.mkdir(mode=0o700)
    _private(target)
    fd = os.open(target / 'events.jsonl', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    (target / 'plans').mkdir(mode=0o700)
    _write_plan_immutable(target, plan)
    _publish_exact(target / 'delivery-plan.json', canonical(plan) + b'\n')
    state = _initial_state(plan, run_id or str(uuid.uuid4()))
    with _locked(target):
        head = _append(target, [], 'created', state)
    return _result(state, head, 'supply_exact_launch_scope')


def _initial_state(plan: dict, run_id: str) -> dict:
    return {'schema_version': '1.0', 'kind': 'template-delivery-session-v1',
             'run_id': run_id, 'plan_sha256': plan['plan_sha256'],
             'generation_id': plan['generation_id'], 'stage': 'installed',
             'pending': None, 'process': None, 'disabled': False,
             'observations': {name: name in ('generated', 'applied', 'installed') for name in _FIELDS},
             'attempts': {'launch': 0, 'stop': 0}, 'failures': [],
             'generation_history': []}


def inspect_unlaunched_session(directory: str | Path, plan: dict) -> None:
    """Read-only proof that an incomplete create contains only known bytes."""
    target = _safe_directory(directory, exists=True)
    _private(target)
    allowed = {'session.lock', 'events.jsonl', 'plans', 'delivery-plan.json',
               'delivery-plan.json.pending'}
    if {item.name for item in target.iterdir()} - allowed:
        raise DeliveryError('delivery_partial_create_unknown_entries')
    lock = target / 'session.lock'
    if lock.exists():
        _owned_file(lock, maximum=1024)
    events = target / 'events.jsonl'
    if events.exists():
        _owned_file(events, maximum=4_000_000)
        if events.stat().st_size:
            raise DeliveryError('delivery_partial_create_nonempty_journal')
    plans = target / 'plans'
    if plans.exists():
        _private(plans)
        if {item.name for item in plans.iterdir()} - {
                plan['plan_sha256'] + '.json', plan['plan_sha256'] + '.json.pending'}:
            raise DeliveryError('delivery_partial_create_unknown_plan')
        archived = plans / (plan['plan_sha256'] + '.json')
        _pending_prefix(archived.with_name(archived.name + '.pending'),
                        canonical(plan) + b'\n')
        if archived.exists():
            _owned_file(archived, maximum=4_000_000)
            if read_json(archived) != plan:
                raise DeliveryError('delivery_partial_create_plan_changed')
    visible = target / 'delivery-plan.json'
    _pending_prefix(visible.with_name(visible.name + '.pending'), canonical(plan) + b'\n')
    if visible.exists():
        _owned_file(visible, maximum=4_000_000)
        if read_json(visible) != plan:
            raise DeliveryError('delivery_partial_create_plan_changed')


def recover_unlaunched_session(directory: str | Path, plan: dict, *, run_id: str) -> dict:
    """Complete only the exact owner-private pre-journal create prefix."""
    _check_plan(plan)
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        inspect_unlaunched_session(target, plan)
        events = target / 'events.jsonl'
        plans = target / 'plans'
        if not plans.exists():
            plans.mkdir(mode=0o700)
        visible = target / 'delivery-plan.json'
        if not events.exists():
            fd = os.open(events, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        _write_plan_immutable(target, plan)
        if not visible.exists():
            _publish_exact(visible, canonical(plan) + b'\n')
        else:
            _pending_prefix(visible.with_name(visible.name + '.pending'),
                            canonical(plan) + b'\n', remove=True)
        state = _initial_state(plan, run_id)
        head = _append(target, [], 'created', state)
    return _result(state, head, 'supply_exact_launch_scope')


def _result(state: dict, head: str, next_action: str, *, current_process_alive: bool | None = None,
            plan: dict | None = None) -> dict:
    if next_action not in _NEXT_ACTIONS:
        raise DeliveryError('unregistered_delivery_next_action')
    previous = state['generation_history'][-1] if state['generation_history'] else None
    return {'schema_version': '1.0', 'kind': 'template-delivery-result-v1',
            'run_id': state['run_id'], 'session_head_sha256': head,
            'stage': state['stage'], 'pending': state['pending'],
            'generation_id': state['generation_id'],
            'generation_history': copy.deepcopy(state['generation_history']),
            'previous_generation_rollback_digest': (digest({
                'operation': 'restore_previous_owned_generation',
                'current_plan_sha256': state['plan_sha256'],
                'previous_plan_sha256': previous['plan_sha256'],
                'run_id': state['run_id']}) if previous else None),
            'recorded_observations': copy.deepcopy(state['observations']),
            'current_process_alive': current_process_alive,
            'current_ready': (_current_observation(plan, 'ready', current_process_alive,
                                                   state['process'])
                              if plan is not None and current_process_alive is not None else None),
            'current_integration_reachable': (
                _current_observation(plan, 'integration_reachable', current_process_alive,
                                     state['process'])
                if plan is not None and current_process_alive is not None else None),
            'next_action': next_action, 'provider_qualification': 'not_run',
            'observed_benefit': False}


def upgrade_session(directory: str | Path, new_plan: dict, *, scope: dict,
                    approved_scope_sha256: str) -> dict:
    """Stage and select a new verified, off-mode generation after old drain.

    The previous environment is retained.  The new console does not start until
    a fresh exact launch scope is supplied, so an interrupted cutover cannot
    silently expand exposure or replay a task.
    """
    _linux_profile()
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, old_plan = _open(target)
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state, 'upgrade')
        if state['pending'] or state['stage'] not in ('stopped', 'disabled'):
            raise DeliveryError('upgrade_requires_completed_old_generation_stop')
        if _process_alive(state['process']):
            raise DeliveryError('upgrade_old_process_still_alive')
        if len(state['generation_history']) >= 2:
            raise DeliveryError('upgrade_generation_history_limit')
        if scope.get('upgrade_plan_sha256') != new_plan.get('plan_sha256'):
            raise DeliveryError('exact_upgrade_plan_authority_required')
        _check_plan(new_plan)
        if (new_plan['schema_version'] != old_plan['schema_version'] or
                new_plan['kind'] != old_plan['kind']):
            raise DeliveryError('incompatible_delivery_schema_requires_migration')
        if (new_plan['generation_id'] == state['generation_id'] or
                new_plan['environment'] == old_plan['environment'] or
                Path(new_plan['environment']).is_relative_to(Path(old_plan['environment'])) or
                Path(old_plan['environment']).is_relative_to(Path(new_plan['environment']))):
            raise DeliveryError('upgrade_requires_new_disjoint_owned_generation')
        _write_plan_immutable(target, new_plan)
        state['generation_history'].append({'plan_sha256': state['plan_sha256'],
                                            'generation_id': state['generation_id']})
        state['plan_sha256'] = new_plan['plan_sha256']
        state['generation_id'] = new_plan['generation_id']
        state['process'] = None
        state['disabled'] = False
        state['stage'] = 'upgrade_staged'
        state['attempts'] = {'launch': 0, 'stop': 0}
        state['observations'] = {name: False for name in _FIELDS}
        state['observations'].update(generated=True, applied=True, installed=True)
        head = _append(target, rows, 'upgrade_staged', state)
        return _result(state, head, 'supply_fresh_off_mode_launch_scope',
                       current_process_alive=False)


def session_status(directory: str | Path, *, trusted_session_head: str | None = None) -> dict:
    """Read-only status. A local chain is not an external trust anchor."""
    target = _safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, plan = _open(target)
        head = rows[-1]['record_sha256']
        try:
            _check_plan(plan)
            installation = 'current_verified'
        except (DeliveryError, InputError, OSError, ValueError):
            installation = 'drift_or_unavailable'
        alive = _process_alive(state['process'])
        if trusted_session_head != head:
            return _result(state, head, 'supply_externally_retained_session_head',
                           current_process_alive=alive, plan=plan) | {'evidence_trust': 'recorded_untrusted',
                                                          'current_installation': installation}
        return _result(state, head, 'reconcile_pending' if state['pending'] else
                       ('disable_or_upgrade' if alive else 'review_stopped_session'),
                       current_process_alive=alive, plan=plan) | {'evidence_trust': 'externally_anchored_history',
                                                      'current_installation': installation}
