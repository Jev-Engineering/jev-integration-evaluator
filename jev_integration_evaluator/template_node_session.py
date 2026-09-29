"""Durable, off-mode supervisor for an exact installed Node descriptor.

This is a separate Linux process adapter. It never grants provider authority,
replays an uncertain invocation, or changes the JS implementation receipt.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import copy
import json
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import sys
import time
import uuid

from .contracts import parse_utc, validate_contract
from .io import InputError, canonical, digest, read_json
from .template_node_delivery import validate_node_delivery, _observed
from .template_node_installation import installation_status
from .template_delivery import _boot_id, _process_info, _process_alive, _signal_owned


class NodeSessionError(InputError):
    """An exact Node session or process ownership check failed."""


_EVENTS = frozenset({'created', 'launch_pending', 'launched', 'running',
                     'observed', 'stop_pending', 'stopped', 'disabled',
                     'upgrade_pending', 'upgrade_staged', 'rollback_pending',
                     'rolled_back', 'blocked_recovery'})
_HELPER = '''import os,sys
fd=int(sys.argv[1]); node=sys.argv[2]; entry=sys.argv[3]; cwd=sys.argv[4]
try: token=os.read(fd,1)
finally: os.close(fd)
if token != b'G': os._exit(125)
os.chdir(cwd)
os.execv(node,[node,entry])
'''


def _linux() -> None:
    if sys.platform != 'linux' or platform.machine().lower() != 'x86_64':
        raise NodeSessionError('node_session_requires_linux_x86_64')


def _directory(value: str | Path, *, exists: bool) -> Path:
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or any(
            item.is_symlink() for item in (path, *path.parents)):
        raise NodeSessionError('node_session_path_invalid')
    if exists and not path.is_dir():
        raise NodeSessionError('node_session_missing')
    if not exists and path.exists():
        raise NodeSessionError('node_session_collision')
    return path


def _private(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise NodeSessionError('node_session_private_directory_missing') from None
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise NodeSessionError('node_session_private_directory_required')


def _file(path: Path, limit: int = 4_000_000) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise NodeSessionError('node_session_file_missing') from None
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1
            or info.st_size > limit):
        raise NodeSessionError('node_session_file_invalid')


def _create_file(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _lock(directory: Path):
    import fcntl
    _private(directory.parent)
    _private(directory)
    path = directory / 'session.lock'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise NodeSessionError('node_session_lock_invalid')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise NodeSessionError('node_session_owned_by_another_controller') from None
        yield
    finally:
        os.close(fd)


def _write_plan(directory: Path, descriptor: dict) -> None:
    plans = directory / 'plans'
    _private(plans)
    path = plans / (descriptor['descriptor_sha256'] + '.json')
    raw = canonical(descriptor) + b'\n'
    if path.exists():
        _file(path)
        if path.read_bytes() != raw:
            raise NodeSessionError('node_session_plan_collision')
    else:
        _create_file(path, raw)


def _anchored_plan(directory: Path, expected_sha256: str) -> dict:
    path = directory / 'plans' / (expected_sha256 + '.json')
    _file(path)
    descriptor = read_json(path)
    validate_contract(descriptor, 'node-delivery-descriptor-v1')
    if (descriptor['descriptor_sha256'] != expected_sha256
            or digest({k: v for k, v in descriptor.items()
                       if k != 'descriptor_sha256'}) != expected_sha256):
        raise NodeSessionError('node_session_descriptor_changed')
    return descriptor


def _append(directory: Path, rows: list[dict], event: str, state: dict) -> str:
    if event not in _EVENTS or len(rows) >= 256:
        raise NodeSessionError('node_session_journal_bound')
    validate_contract(state, 'node-delivery-session-v1')
    row = {'sequence': len(rows), 'previous_sha256': rows[-1]['record_sha256'] if rows else None,
           'event': event, 'state': copy.deepcopy(state),
           'at': datetime.now(timezone.utc).isoformat()}
    row['record_sha256'] = digest(row)
    path = directory / 'events.jsonl'
    _file(path)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical(row) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    rows.append(row)
    return row['record_sha256']


def _open(directory: str | Path) -> tuple[Path, list[dict], dict, dict]:
    target = _directory(directory, exists=True)
    _private(target)
    if os.path.ismount(target):
        raise NodeSessionError('node_session_mount_root_unsupported')
    if any(row.name not in {'owner.json', 'plans', 'events.jsonl', 'session.lock'}
           or row.is_symlink() for row in target.iterdir()):
        raise NodeSessionError('node_session_unknown_owned_content')
    _private(target / 'plans')
    _file(target / 'owner.json')
    owner = read_json(target / 'owner.json')
    info = target.stat()
    if (owner.get('kind') != 'node-delivery-owner-v1' or owner.get('uid') != os.geteuid()
            or owner.get('dev') != info.st_dev or owner.get('ino') != info.st_ino):
        raise NodeSessionError('node_session_owner_changed')
    _file(target / 'events.jsonl')
    rows = []
    for line in (target / 'events.jsonl').read_bytes().splitlines():
        if len(line) > 16_384 or len(rows) >= 256:
            raise NodeSessionError('node_session_journal_bound')
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError):
            raise NodeSessionError('node_session_journal_torn') from None
        if (row.get('sequence') != len(rows) or row.get('event') not in _EVENTS
                or row.get('previous_sha256') != (rows[-1]['record_sha256'] if rows else None)
                or row.get('record_sha256') != digest({k: v for k, v in row.items()
                                                       if k != 'record_sha256'})):
            raise NodeSessionError('node_session_journal_torn')
        validate_contract(row['state'], 'node-delivery-session-v1')
        rows.append(row)
    if not rows:
        raise NodeSessionError('node_session_creation_incomplete')
    state = copy.deepcopy(rows[-1]['state'])
    if owner.get('run_id') != state['run_id']:
        raise NodeSessionError('node_session_owner_changed')
    descriptor = _anchored_plan(target, state['descriptor_sha256'])
    if descriptor['generation_id'] != state['generation_id']:
        raise NodeSessionError('node_session_descriptor_changed')
    return target, rows, state, descriptor


def _check_install(descriptor: dict) -> None:
    validate_contract(descriptor, 'node-delivery-descriptor-v1')
    if descriptor['descriptor_sha256'] != digest({k: v for k, v in descriptor.items()
                                                  if k != 'descriptor_sha256'}):
        raise NodeSessionError('node_session_descriptor_changed')
    status = installation_status(descriptor['install_plan'],
        trusted_receipt_sha256=descriptor['trusted_install_receipt_sha256'])
    if status['status'] != 'installed_recorded' or status['generation_id'] != descriptor['generation_id']:
        raise NodeSessionError('node_session_installed_generation_drift')


def _authority(scope: dict, approved: str, head: str, state: dict, action: str,
               *, extra: str | None = None) -> None:
    validate_contract(scope, 'template-delivery-scope-v1')
    if (scope['scope_sha256'] != approved
            or scope['scope_sha256'] != digest({k: v for k, v in scope.items() if k != 'scope_sha256'})
            or scope['run_id'] != state['run_id']
            or scope['plan_sha256'] != state['descriptor_sha256']
            or scope['trusted_session_head'] != head or scope['revoked']
            or scope['grants'][action] is not True):
        raise NodeSessionError('exact_node_session_scope_required')
    if parse_utc(scope['expires_at']) <= datetime.now(timezone.utc):
        raise NodeSessionError('node_session_scope_expired')
    if extra is not None and scope.get('upgrade_plan_sha256' if action == 'upgrade'
                                     else 'rollback_digest') != extra:
        raise NodeSessionError('exact_node_session_generation_scope_required')


def _result(state: dict, head: str, descriptor: dict | None = None) -> dict:
    alive = _process_alive(state['process'])
    result = {'schema_version': '1.0', 'kind': 'node-delivery-status-v1',
              'run_id': state['run_id'], 'descriptor_sha256': state['descriptor_sha256'],
              'generation_id': state['generation_id'], 'stage': state['stage'],
              'pending': state['pending'], 'disabled': state['disabled'],
              'process_alive': alive, 'observations': copy.deepcopy(state['observations']),
              'attempts': copy.deepcopy(state['attempts']), 'failures': list(state['failures']),
              'session_head_sha256': head, 'previous_generation_rollback_digest': None}
    if state['history']:
        result['previous_generation_rollback_digest'] = digest({
            'operation': 'restore_previous_node_generation', 'run_id': state['run_id'],
            'current_descriptor_sha256': state['descriptor_sha256'],
            'previous_descriptor_sha256': state['history'][-1]})
    if descriptor is not None:
        result['current_installation'] = 'current_verified' if _installation_current(descriptor) else 'drift_or_unavailable'
    validate_contract(result, 'node-delivery-status-v1')
    return result


def _installation_current(descriptor: dict) -> bool:
    try:
        _check_install(descriptor)
        return True
    except (InputError, OSError, ValueError):
        return False


def create_node_session(directory: str | Path, descriptor: dict,
                        *, run_id: str | None = None) -> dict:
    _linux()
    validate_node_delivery(descriptor)
    target = _directory(directory, exists=False)
    _private(target.parent)
    run_id = str(uuid.uuid4()) if run_id is None else run_id
    uuid.UUID(run_id)
    target.mkdir(mode=0o700)
    info = target.stat()
    owner = {'kind': 'node-delivery-owner-v1', 'run_id': run_id,
             'uid': os.geteuid(), 'dev': info.st_dev, 'ino': info.st_ino}
    _create_file(target / 'owner.json', canonical(owner) + b'\n')
    (target / 'plans').mkdir(mode=0o700)
    _create_file(target / 'events.jsonl', b'')
    _create_file(target / 'session.lock', b'')
    _write_plan(target, descriptor)
    state = {'schema_version': '1.0', 'kind': 'node-delivery-session-v1',
             'run_id': run_id, 'descriptor_sha256': descriptor['descriptor_sha256'],
             'generation_id': descriptor['generation_id'], 'stage': 'created',
             'pending': None, 'disabled': False, 'process': None,
             'observations': {name: False for name in
                              ('launched', 'ready', 'entrypoint_reached',
                               'integration_reachable', 'outcome_verified')},
             'attempts': {'launch': 0, 'stop': 0}, 'history': [],
             'pending_upgrade_sha256': None, 'failures': []}
    head = _append(target, [], 'created', state)
    return _result(state, head, descriptor)


def _execed_node(identity: dict, descriptor: dict) -> bool:
    if not _process_alive(identity):
        return False
    try:
        args = Path(f"/proc/{identity['pid']}/cmdline").read_bytes().split(b'\x00')
    except OSError:
        return False
    try:
        same_executable = os.path.samefile(f"/proc/{identity['pid']}/exe",
                                            descriptor['command'][0])
    except OSError:
        return False
    return (len(args) > 1 and args[1] == os.fsencode(descriptor['command'][1])
            and same_executable)


def launch_node_session(directory: str | Path, *, scope: dict,
                        approved_scope_sha256: str) -> dict:
    """Durably record the child before releasing its private exec pipe."""
    _linux()
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, descriptor = _open(target)
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state, 'launch')
        if (state['disabled'] or state['pending'] or state['stage'] not in
                ('created', 'stopped', 'upgrade_staged', 'rolled_back')
                or state['attempts']['launch'] >= 3 or _process_alive(state['process'])):
            raise NodeSessionError('node_session_launch_blocked')
        validate_node_delivery(descriptor)
        state['attempts']['launch'] += 1
        state['stage'], state['pending'] = 'launch_pending', 'launch'
        _append(target, rows, 'launch_pending', state)
        read_fd, write_fd = os.pipe()
        try:
            env = {'PATH': '/usr/bin:/bin', 'JEV_RUNTIME_MODE': 'off',
                   **descriptor['launch_environment']}
            child = subprocess.Popen([sys.executable, '-I', '-c', _HELPER,
                                      str(read_fd), *descriptor['command'],
                                      descriptor['working_directory']],
                                     pass_fds=(read_fd,), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True, close_fds=True, env=env,
                                     cwd=descriptor['working_directory'])
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
                raise NodeSessionError('node_session_child_identity_unavailable')
            state['process'] = {'pid': child.pid, 'boot_id': _boot_id(), 'start_ticks': start}
            state['stage'] = 'running'
            state['observations']['launched'] = True
            _append(target, rows, 'launched', state)
            os.write(write_fd, b'G')
        finally:
            if read_fd != -1:
                os.close(read_fd)
            os.close(write_fd)
        state['pending'] = None
        head = _append(target, rows, 'running', state)
        return _result(state, head)


def observe_node_session(directory: str | Path, *, trusted_session_head: str) -> dict:
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, descriptor = _open(target)
        if trusted_session_head != rows[-1]['record_sha256']:
            raise NodeSessionError('externally_retained_node_session_head_required')
        if state['stage'] not in ('running', 'stopped', 'stop_pending'):
            raise NodeSessionError('node_session_not_launched')
        found = copy.deepcopy(state['observations'])
        for row in descriptor['observation']['checks']:
            if _observed(Path(row['path'])) == row['expected_sha256']:
                if row['role'] != 'ready' or _execed_node(state['process'], descriptor):
                    found[row['role']] = True
        if found != state['observations']:
            state['observations'] = found
            head = _append(target, rows, 'observed', state)
        else:
            head = rows[-1]['record_sha256']
        return _result(state, head)


def stop_node_session(directory: str | Path, *, scope: dict, approved_scope_sha256: str,
                      disable: bool = False, grace_seconds: float = 1.0) -> dict:
    _linux()
    if type(disable) is not bool or not 0 <= grace_seconds <= 30:
        raise NodeSessionError('node_session_stop_policy_invalid')
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, descriptor = _open(target)
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state,
                   'disable' if disable else 'stop')
        if state['process'] is None or state['pending'] not in (None, 'stop', 'disable'):
            raise NodeSessionError('node_session_stop_requires_known_process')
        if state['stage'] in ('stopped', 'disabled'):
            if (state['stage'] == 'disabled') != disable:
                raise NodeSessionError('node_session_stop_disposition_changed')
            if _process_alive(state['process']):
                raise NodeSessionError('node_session_stopped_process_alive')
            return _result(state, rows[-1]['record_sha256'], descriptor)
        if state['stage'] not in ('running', 'stop_pending'):
            raise NodeSessionError('node_session_stop_requires_running_process')
        if state['pending'] is not None and (state['pending'] == 'disable') != disable:
            raise NodeSessionError('node_session_stop_disposition_changed')
        if state['pending'] is None:
            state['attempts']['stop'] += 1
            state['stage'], state['pending'] = 'stop_pending', 'disable' if disable else 'stop'
            _append(target, rows, 'stop_pending', state)
        until = time.monotonic() + grace_seconds
        while _process_alive(state['process']) and time.monotonic() < until:
            time.sleep(0.02)
        if _process_alive(state['process']):
            _signal_owned(state['process'], signal.SIGTERM)
            until = time.monotonic() + 1.0
            while _process_alive(state['process']) and time.monotonic() < until:
                time.sleep(0.02)
        if _process_alive(state['process']):
            return _result(state, rows[-1]['record_sha256'], descriptor)
        state['stage'], state['pending'] = ('disabled' if disable else 'stopped'), None
        state['disabled'] = disable
        head = _append(target, rows, state['stage'], state)
        return _result(state, head, descriptor)


def resume_node_session(directory: str | Path, *, trusted_session_head: str) -> dict:
    """Reconcile only known state; an uncertain start never reruns Node."""
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, descriptor = _open(target)
        if trusted_session_head != rows[-1]['record_sha256']:
            raise NodeSessionError('externally_retained_node_session_head_required')
        if state['pending'] == 'launch':
            if state['process'] is None:
                state['stage'], state['pending'] = 'created', None
                state['failures'].append('launch_unreleased')
                head = _append(target, rows, 'observed', state)
                return _result(state, head, descriptor)
            if _execed_node(state['process'], descriptor):
                state['stage'], state['pending'] = 'running', None
                head = _append(target, rows, 'running', state)
                return _result(state, head, descriptor)
            state['stage'] = 'blocked_recovery'
            state['failures'].append('launch_outcome_unknown')
            head = _append(target, rows, 'blocked_recovery', state)
            return _result(state, head, descriptor)
        if state['pending'] in ('stop', 'disable'):
            if _process_alive(state['process']):
                return _result(state, rows[-1]['record_sha256'], descriptor)
            disabling = state['pending'] == 'disable'
            state['stage'], state['pending'] = ('disabled' if disabling else 'stopped'), None
            state['disabled'] = disabling
            head = _append(target, rows, state['stage'], state)
            return _result(state, head, descriptor)
        if state['pending'] == 'rollback':
            return _finish_rollback(target, rows, state, descriptor)
        if state['pending'] == 'upgrade':
            return _finish_upgrade(target, rows, state, descriptor)
        return _result(state, rows[-1]['record_sha256'], descriptor)


def _finish_upgrade(target: Path, rows: list[dict], state: dict,
                    leaving: dict) -> dict:
    if state['pending_upgrade_sha256'] is None:
        raise NodeSessionError('node_session_upgrade_intent_missing')
    _check_install(leaving)
    new = _anchored_plan(target, state['pending_upgrade_sha256'])
    validate_node_delivery(new)
    state['history'].append(state['descriptor_sha256'])
    state['descriptor_sha256'] = new['descriptor_sha256']
    state['generation_id'] = new['generation_id']
    state['pending_upgrade_sha256'] = None
    state['process'] = None
    state['attempts'] = {'launch': 0, 'stop': 0}
    state['observations'] = {name: False for name in state['observations']}
    state['stage'], state['pending'] = 'upgrade_staged', None
    head = _append(target, rows, 'upgrade_staged', state)
    return _result(state, head, new)


def upgrade_node_session(directory: str | Path, new_descriptor: dict, *, scope: dict,
                         approved_scope_sha256: str) -> dict:
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, old = _open(target)
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state,
                   'upgrade', extra=new_descriptor['descriptor_sha256'])
        if state['pending'] or state['stage'] != 'stopped' or _process_alive(state['process']):
            raise NodeSessionError('node_session_upgrade_requires_stopped_process')
        _check_install(old)
        validate_node_delivery(new_descriptor)
        if new_descriptor['generation_id'] == state['generation_id']:
            raise NodeSessionError('node_session_upgrade_generation_reused')
        _write_plan(target, new_descriptor)
        state['stage'], state['pending'] = 'upgrade_pending', 'upgrade'
        state['pending_upgrade_sha256'] = new_descriptor['descriptor_sha256']
        _append(target, rows, 'upgrade_pending', state)
        return _finish_upgrade(target, rows, state, old)


def _finish_rollback(target: Path, rows: list[dict], state: dict,
                     leaving: dict) -> dict:
    if not state['history']:
        raise NodeSessionError('node_session_previous_generation_missing')
    _check_install(leaving)
    previous = state['history'][-1]
    old = _anchored_plan(target, previous)
    _check_install(old)
    state['history'].pop()
    state['descriptor_sha256'] = old['descriptor_sha256']
    state['generation_id'] = old['generation_id']
    state['process'] = None
    state['disabled'] = False
    state['attempts'] = {'launch': 0, 'stop': 0}
    state['observations'] = {name: False for name in state['observations']}
    state['stage'], state['pending'] = 'rolled_back', None
    head = _append(target, rows, 'rolled_back', state)
    return _result(state, head, old)


def rollback_node_session(directory: str | Path, *, scope: dict,
                          approved_scope_sha256: str) -> dict:
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, current = _open(target)
        expected = _result(state, rows[-1]['record_sha256'])['previous_generation_rollback_digest']
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state,
                   'rollback', extra=expected)
        if (expected is None or state['pending'] or state['stage'] not in ('stopped', 'disabled')
                or _process_alive(state['process'])):
            raise NodeSessionError('node_session_rollback_requires_stopped_generation')
        _check_install(current)
        previous = _anchored_plan(target, state['history'][-1])
        _check_install(previous)
        state['stage'], state['pending'] = 'rollback_pending', 'rollback'
        _append(target, rows, 'rollback_pending', state)
        return _finish_rollback(target, rows, state, current)


def node_session_status(directory: str | Path, *, trusted_session_head: str | None = None) -> dict:
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, descriptor = _open(target)
        if trusted_session_head is not None and trusted_session_head != rows[-1]['record_sha256']:
            raise NodeSessionError('externally_retained_node_session_head_required')
        return _result(state, rows[-1]['record_sha256'], descriptor)
