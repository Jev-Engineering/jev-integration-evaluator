"""Durable single-process supervisor for an exact installed Node connected owner."""
from __future__ import annotations

from datetime import datetime, timezone
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from .contracts import parse_utc, validate_contract
from .io import InputError, canonical, digest, read_json
from .template_delivery import _boot_id, _process_alive, _process_info, _signal_owned
from .template_node_connected import connected_status
from .template_node_session import (_HELPER, _directory, _file, _lock,
                                    _private, _create_file, _linux)


_EVENTS = frozenset({'created', 'launch_pending', 'launched', 'running',
                     'observed', 'stop_pending', 'stopped', 'disabled',
                     'blocked_recovery'})
_OWNED = frozenset({'owner.json', 'request.json', 'descriptor.json',
                    'events.jsonl', 'session.lock'})


def _append(directory: Path, rows: list, event: str, state: dict) -> str:
    if event not in _EVENTS or len(rows) >= 128:
        raise InputError('connected_session_journal_bound')
    validate_contract(state, 'node-connected-session-v1')
    row = {'sequence': len(rows), 'previous_sha256': rows[-1]['record_sha256'] if rows else None,
           'event': event, 'state': copy.deepcopy(state), 'at': datetime.now(timezone.utc).isoformat()}
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


def _open(directory: str | Path):
    target = _directory(directory, exists=True)
    _private(target)
    if os.path.ismount(target) or {p.name for p in target.iterdir()} != _OWNED:
        raise InputError('connected_session_owned_content_changed')
    for name in _OWNED:
        _file(target / name)
    owner = read_json(target / 'owner.json')
    info = target.stat()
    if (owner.get('kind') != 'node-connected-session-owner-v1' or
            owner.get('uid') != os.geteuid() or
            (owner.get('dev'), owner.get('ino')) != (info.st_dev, info.st_ino)):
        raise InputError('connected_session_owner_changed')
    rows = []
    for raw in (target / 'events.jsonl').read_bytes().splitlines():
        if len(raw) > 16_384 or len(rows) >= 128:
            raise InputError('connected_session_journal_bound')
        try:
            row = json.loads(raw)
        except (ValueError, UnicodeError):
            raise InputError('connected_session_journal_torn') from None
        if (row.get('sequence') != len(rows) or row.get('event') not in _EVENTS or
                row.get('previous_sha256') != (rows[-1]['record_sha256'] if rows else None) or
                row.get('record_sha256') != digest({k: v for k, v in row.items()
                                                    if k != 'record_sha256'})):
            raise InputError('connected_session_journal_torn')
        validate_contract(row['state'], 'node-connected-session-v1')
        rows.append(row)
    if not rows:
        raise InputError('connected_session_creation_incomplete')
    state = copy.deepcopy(rows[-1]['state'])
    request = read_json(target / 'request.json')
    descriptor = read_json(target / 'descriptor.json')
    if (owner['run_id'] != state['run_id'] or
            digest(request) != state['request_sha256'] or
            descriptor.get('descriptor_sha256') != state['descriptor_sha256'] or
            digest({k: v for k, v in descriptor.items()
                    if k != 'descriptor_sha256'}) != state['descriptor_sha256']):
        raise InputError('connected_session_plan_changed')
    return target, rows, state, request, descriptor


def _scope(scope: dict, approved: str, state: dict, head: str, action: str):
    validate_contract(scope, 'template-delivery-scope-v1')
    if (scope['scope_sha256'] != approved or
            approved != digest({k: v for k, v in scope.items() if k != 'scope_sha256'}) or
            scope['run_id'] != state['run_id'] or
            scope['plan_sha256'] != state['descriptor_sha256'] or
            scope['trusted_session_head'] != head or scope['revoked'] or
            scope['grants'][action] is not True or
            parse_utc(scope['expires_at']) <= datetime.now(timezone.utc)):
        raise InputError('exact_connected_session_scope_required')


def _result(state: dict, head: str):
    return {'schema_version': '1.0', 'kind': 'node-connected-session-status-v1',
            'run_id': state['run_id'], 'stage': state['stage'],
            'pending': state['pending'], 'disabled': state['disabled'],
            'descriptor_sha256': state['descriptor_sha256'],
            'session_head_sha256': head, 'process_alive': _process_alive(state['process']),
            'attempts': dict(state['attempts']), 'failures': list(state['failures'])}


def _execed_node(identity: dict | None, request: dict) -> bool:
    if not _process_alive(identity):
        return False
    receipt = read_json(Path(request['install_plan']['environment_parent']) /
                        ('jev-node-env-' + request['install_plan']['plan_sha256'][:24]) /
                        'install-receipt.json')
    try:
        args = Path(f"/proc/{identity['pid']}/cmdline").read_bytes().split(b'\x00')
        return (len(args) > 1 and args[1] == os.fsencode(receipt['command'][1]) and
                os.path.samefile(f"/proc/{identity['pid']}/exe", receipt['command'][0]))
    except OSError:
        return False


def create_connected_session(directory: str | Path, request: dict, descriptor: dict,
                             *, trusted_descriptor_sha256: str):
    _linux()
    connected_status(request, descriptor,
                     trusted_descriptor_sha256=trusted_descriptor_sha256)
    target = _directory(directory, exists=False)
    _private(target.parent)
    run_id = str(uuid.uuid4())
    target.mkdir(mode=0o700)
    info = target.stat()
    owner = {'kind': 'node-connected-session-owner-v1', 'run_id': run_id,
             'uid': os.geteuid(), 'dev': info.st_dev, 'ino': info.st_ino}
    _create_file(target / 'owner.json', canonical(owner) + b'\n')
    _create_file(target / 'request.json', canonical(request) + b'\n')
    _create_file(target / 'descriptor.json', canonical(descriptor) + b'\n')
    _create_file(target / 'events.jsonl', b'')
    _create_file(target / 'session.lock', b'')
    state = {'schema_version': '1.0', 'kind': 'node-connected-session-v1',
             'run_id': run_id, 'request_sha256': digest(request),
             'descriptor_sha256': trusted_descriptor_sha256, 'stage': 'created',
             'pending': None, 'disabled': False, 'process': None,
             'attempts': {'launch': 0, 'stop': 0}, 'failures': []}
    return _result(state, _append(target, [], 'created', state))


def launch_connected_session(directory: str | Path, scope: dict, *, approved_scope_sha256: str):
    _linux()
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, request, descriptor = _open(target)
        _scope(scope, approved_scope_sha256, state, rows[-1]['record_sha256'], 'launch')
        if (state['disabled'] or state['pending'] or state['stage'] not in ('created', 'stopped') or
                state['attempts']['launch'] >= 3 or _process_alive(state['process'])):
            raise InputError('connected_session_launch_blocked')
        connected_status(request, descriptor,
                         trusted_descriptor_sha256=state['descriptor_sha256'])
        if (os.environ.get('JEV_RUNTIME_MODE') != descriptor['mode'] or
                not os.environ.get('TYPESAFE_API_KEY')):
            raise InputError('connected_launch_environment_missing')
        receipt = read_json(Path(request['install_plan']['environment_parent']) /
                            ('jev-node-env-' + request['install_plan']['plan_sha256'][:24]) /
                            'install-receipt.json')
        state['attempts']['launch'] += 1
        state['stage'], state['pending'] = 'launch_pending', 'launch'
        _append(target, rows, 'launch_pending', state)
        read_fd, write_fd = os.pipe()
        try:
            keys = ('PATH', 'JEV_RUNTIME_MODE', 'TYPESAFE_API_KEY',
                    'NODE_EFFECT_PATH', 'NODE_READY_PATH', 'NODE_INTEGRATION_PATH',
                    'JEV_TRUSTED_EGRESS_GRANT_SHA256', 'JEV_TRUSTED_GRANT_FILE',
                    'JEV_FAKE_TRANSPORT_DELAY_MS', 'JEV_FAKE_TRANSPORT_MARKER',
                    'JEV_INVOCATION_ID')
            environment = {key: os.environ[key] for key in keys if key in os.environ}
            environment['JEV_CONNECTED_DESCRIPTOR'] = str(target / 'descriptor.json')
            child = subprocess.Popen([sys.executable, '-I', '-c', _HELPER,
                str(read_fd), *receipt['command'], receipt['working_directory']],
                pass_fds=(read_fd,), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, close_fds=True, env=environment,
                cwd=receipt['working_directory'])
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
                raise InputError('connected_session_child_identity_unavailable')
            state['process'] = {'pid': child.pid, 'boot_id': _boot_id(), 'start_ticks': start}
            state['stage'] = 'running'
            _append(target, rows, 'launched', state)
            os.write(write_fd, b'G')
        finally:
            if read_fd != -1:
                os.close(read_fd)
            os.close(write_fd)
        state['pending'] = None
        return _result(state, _append(target, rows, 'running', state))


def observe_connected_session(directory: str | Path, *, trusted_session_head: str):
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, request, descriptor = _open(target)
        if rows[-1]['record_sha256'] != trusted_session_head:
            raise InputError('externally_retained_connected_session_head_required')
        connected_status(request, descriptor,
                         trusted_descriptor_sha256=state['descriptor_sha256'])
        return _result(state, rows[-1]['record_sha256'])


def reconcile_connected_session(directory: str | Path, *, trusted_session_head: str):
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, request, descriptor = _open(target)
        if rows[-1]['record_sha256'] != trusted_session_head:
            raise InputError('externally_retained_connected_session_head_required')
        if state['pending'] == 'launch':
            if state['process'] is None:
                state['stage'], state['pending'] = 'created', None
                state['failures'].append('launch_unreleased')
                return _result(state, _append(target, rows, 'observed', state))
            if _execed_node(state['process'], request):
                state['stage'], state['pending'] = 'running', None
                return _result(state, _append(target, rows, 'running', state))
            state['stage'] = 'blocked_recovery'
            state['failures'].append('launch_outcome_unknown')
            return _result(state, _append(target, rows, 'blocked_recovery', state))
        if state['pending'] in ('stop', 'disable') and not _process_alive(state['process']):
            state['disabled'] = state['pending'] == 'disable'
            state['stage'], state['pending'] = ('disabled' if state['disabled'] else 'stopped'), None
            return _result(state, _append(target, rows, state['stage'], state))
        return _result(state, rows[-1]['record_sha256'])


def stop_connected_session(directory: str | Path, scope: dict, *,
                           approved_scope_sha256: str, disable: bool = False):
    _linux()
    target = _directory(directory, exists=True)
    with _lock(target):
        _, rows, state, _, _ = _open(target)
        _scope(scope, approved_scope_sha256, state, rows[-1]['record_sha256'],
               'disable' if disable else 'stop')
        if state['stage'] != 'running' or state['pending'] is not None or state['process'] is None:
            raise InputError('connected_session_stop_requires_running')
        state['attempts']['stop'] += 1
        state['stage'], state['pending'] = 'stop_pending', 'disable' if disable else 'stop'
        _append(target, rows, 'stop_pending', state)
        if _process_alive(state['process']):
            _signal_owned(state['process'], signal.SIGTERM)
        until = time.monotonic() + 2
        while _process_alive(state['process']) and time.monotonic() < until:
            time.sleep(.02)
        if _process_alive(state['process']):
            return _result(state, rows[-1]['record_sha256'])
        state['disabled'] = disable
        state['stage'], state['pending'] = ('disabled' if disable else 'stopped'), None
        return _result(state, _append(target, rows, state['stage'], state))
