"""Private, exclusive native output archives for authenticated session recovery.

Raw target output can contain sensitive data. Callers must keep archive paths
inside their private 0700 session directory and retain the returned digest
externally with repository/bundle/phase/attempt identity. No archive is a grant.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from .isolated_python import RunnerError, _root_fd, canonical, inspect_receipt

MAX_ARCHIVE_BYTES = 96 * 1024 * 1024


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _outside_root(destination: Path, target_root: str | Path) -> None:
    if not destination.is_absolute():
        raise RunnerError('absolute_private_archive_required')
    if destination.resolve().is_relative_to(Path(target_root).resolve()):
        raise RunnerError('private_archive_must_be_external')


def _private_parent(path: Path) -> int:
    fd = _root_fd(path.parent)
    info = os.fstat(fd)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        os.close(fd)
        raise RunnerError('private_archive_directory_required')
    return fd


def _check_outputs(spec: dict[str, Any], receipt: dict[str, Any],
                   outputs: dict[str, tuple[bytes, bytes]]) -> list[dict[str, Any]]:
    if type(outputs) is not dict or set(outputs) - {row['case_id'] for row in receipt['cases']}:
        raise RunnerError('unexpected_private_output')
    rows = []
    for row in receipt['cases']:
        pair = outputs.get(row['case_id'])
        if pair is None:
            if row['outcome'] == 'exited_zero':
                raise RunnerError('missing_completed_private_output')
            rows.append({'case_id': row['case_id'], 'stdout_b64': None, 'stderr_b64': None})
            continue
        if (type(pair) is not tuple or len(pair) != 2
                or any(type(part) is not bytes for part in pair)):
            raise RunnerError('invalid_private_output')
        stdout, stderr = pair
        if (len(stdout), _hash(stdout), len(stderr), _hash(stderr)) != (
                row['stdout_bytes'], row['stdout_sha256'], row['stderr_bytes'], row['stderr_sha256']):
            raise RunnerError('private_output_receipt_mismatch')
        rows.append({'case_id': row['case_id'],
                     'stdout_b64': base64.b64encode(stdout).decode('ascii'),
                     'stderr_b64': base64.b64encode(stderr).decode('ascii')})
    return rows


def write_private_output_archive(
    path: str | Path, target_root: str | Path, spec: dict[str, Any],
    receipt: dict[str, Any], outputs: dict[str, tuple[bytes, bytes]], *,
    phase: str, attempt: int, trusted_receipt_sha256: str,
) -> str:
    """Write once, fsync, and return an externally retainable archive digest."""
    if phase not in ('baseline', 'modified') or type(attempt) is not int or not 1 <= attempt <= 3:
        raise RunnerError('invalid_native_phase_attempt')
    inspect_receipt(spec, receipt, trusted_receipt_sha256=trusted_receipt_sha256)
    destination = Path(path)
    _outside_root(destination, target_root)
    payload = {'schema_version': '1.0', 'kind': 'native-private-output-v1',
               'phase': phase, 'attempt': attempt,
               'receipt_sha256': trusted_receipt_sha256,
               'cases': _check_outputs(spec, receipt, outputs)}
    encoded = canonical(payload) + b'\n'
    if len(encoded) > MAX_ARCHIVE_BYTES:
        raise RunnerError('private_archive_byte_limit')
    parent = _private_parent(destination)
    fd = -1
    try:
        fd = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        pending = memoryview(encoded)
        while pending:
            count = os.write(fd, pending)
            if count <= 0:
                raise RunnerError('private_archive_write_failed')
            pending = pending[count:]
        os.fsync(fd)
        os.fsync(parent)
    except FileExistsError:
        raise RunnerError('private_archive_exists_no_replay') from None
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(parent)
    return _hash(encoded)


def read_private_output_archive(
    path: str | Path, target_root: str | Path, spec: dict[str, Any],
    receipt: dict[str, Any], *, phase: str, attempt: int,
    trusted_receipt_sha256: str, trusted_archive_sha256: str,
) -> dict[str, tuple[bytes, bytes]]:
    """Read only independently anchored, matching phase/attempt bytes."""
    destination = Path(path)
    _outside_root(destination, target_root)
    inspect_receipt(spec, receipt, trusted_receipt_sha256=trusted_receipt_sha256)
    if type(trusted_archive_sha256) is not str or len(trusted_archive_sha256) != 64:
        raise RunnerError('external_private_archive_anchor_required')
    parent = _private_parent(destination)
    fd = -1
    try:
        fd = os.open(destination.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
                or not 0 < info.st_size <= MAX_ARCHIVE_BYTES):
            raise RunnerError('unsafe_private_archive')
        data = bytearray()
        while len(data) <= MAX_ARCHIVE_BYTES:
            chunk = os.read(fd, min(65536, MAX_ARCHIVE_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        if (len(data) != info.st_size or info.st_mtime_ns != after.st_mtime_ns
                or info.st_ctime_ns != after.st_ctime_ns):
            raise RunnerError('private_archive_changed_during_read')
    except FileNotFoundError:
        raise RunnerError('private_archive_missing_no_replay') from None
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(parent)
    raw = bytes(data)
    if _hash(raw) != trusted_archive_sha256:
        raise RunnerError('external_private_archive_anchor_mismatch')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        record = json.loads(raw, object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (ValueError, UnicodeError):
        raise RunnerError('invalid_private_archive') from None
    if (type(record) is not dict or set(record) != {'schema_version', 'kind', 'phase', 'attempt',
                                                    'receipt_sha256', 'cases'}
            or record['schema_version'] != '1.0' or record['kind'] != 'native-private-output-v1'
            or record['phase'] != phase or record['attempt'] != attempt
            or record['receipt_sha256'] != trusted_receipt_sha256
            or type(record['cases']) is not list or len(record['cases']) != len(receipt['cases'])):
        raise RunnerError('private_archive_phase_attempt_mismatch')
    outputs = {}
    for item, case in zip(record['cases'], receipt['cases']):
        if type(item) is not dict or set(item) != {'case_id', 'stdout_b64', 'stderr_b64'} or item['case_id'] != case['case_id']:
            raise RunnerError('private_archive_schedule_mismatch')
        if item['stdout_b64'] is None and item['stderr_b64'] is None:
            continue
        if type(item['stdout_b64']) is not str or type(item['stderr_b64']) is not str:
            raise RunnerError('invalid_private_archive')
        try:
            outputs[item['case_id']] = (
                base64.b64decode(item['stdout_b64'], validate=True),
                base64.b64decode(item['stderr_b64'], validate=True))
        except (ValueError, base64.binascii.Error):
            raise RunnerError('invalid_private_archive') from None
    _check_outputs(spec, receipt, outputs)
    return outputs
