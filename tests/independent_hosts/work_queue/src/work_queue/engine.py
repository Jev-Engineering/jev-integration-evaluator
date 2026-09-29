"""Existing work-queue operations with a finite host-owned effect ledger."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import stat
from threading import RLock
import time

from jev_integration_evaluator.runtime import HostGate


LOCK = RLock()
OPERATIONS = {'enqueue', 'complete'}
ITEMS = {'batch-a', 'batch-b'}


def _owned_file(name: str) -> Path:
    value = os.environ.get(name)
    if not value and name == 'WORK_QUEUE_EFFECTS':
        probe = os.environ.get('WORK_QUEUE_PROBE_EFFECTS_DIR')
        if probe:
            value = str(Path(probe) / ('effects-' + str(os.getpid()) + '.jsonl'))
    if not value:
        raise RuntimeError('missing_' + name.lower())
    path = Path(value)
    if (not path.is_absolute() or path.is_symlink() or
            any(parent.is_symlink() for parent in path.parents)):
        raise RuntimeError('unsafe_' + name.lower())
    owner = path.parent.stat()
    if owner.st_uid != os.getuid() or stat.S_IMODE(owner.st_mode) & 0o077:
        raise RuntimeError('nonprivate_' + name.lower())
    return path


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    if not path.is_file() or path.stat().st_size > 1_000_000:
        raise RuntimeError('queue_effect_file_invalid')
    records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    if any(type(row) is not dict or set(row) != {'job_id', 'operation', 'item'}
           for row in records):
        raise RuntimeError('queue_effect_file_invalid')
    return records


def _record(job: dict, operation: str) -> int:
    path = _owned_file('WORK_QUEUE_EFFECTS')
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError('queue_effect_file_invalid')
        fcntl.flock(fd, fcntl.LOCK_EX)
        if any(row['job_id'] == job['job_id'] for row in _rows(path)):
            raise RuntimeError('duplicate_queue_job')
        event = {'job_id': job['job_id'], 'operation': operation, 'item': job['item']}
        os.write(fd, (json.dumps(event, sort_keys=True, separators=(',', ':')) + '\n').encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    return 0


def _pause_if_requested() -> None:
    if os.environ.get('WORK_QUEUE_HOLD') != '1':
        return
    ready, release = (_owned_file(name) for name in ('WORK_QUEUE_READY', 'WORK_QUEUE_RELEASE'))
    fd = os.open(ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, b'queue-running\n')
        os.fsync(fd)
    finally:
        os.close(fd)
    deadline = time.monotonic() + 15
    while not release.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError('queue_release_missing')
        time.sleep(.01)


def enqueue_batch(job: dict) -> int:
    if not validate_job(job, 'enqueue'):
        return refuse_job(job, 'host_policy')
    _pause_if_requested()
    return _record(job, 'enqueue')


def complete_batch(job: dict) -> int:
    if not validate_job(job, 'complete') or job.get('complete_allowed') is not True:
        return refuse_job(job, 'host_policy')
    _pause_if_requested()
    return _record(job, 'complete')


def original_route(job: dict) -> int:
    return enqueue_batch(job)


def choose_operation(job: dict) -> int:
    return original_route(job)


def handle_job(job: dict) -> int:
    return choose_operation(job)


def runtime_for_job(job: dict):
    raise RuntimeError('work_queue_runtime_requires_host_startup')


def evidence_for_job(job: dict) -> dict:
    return {'item_kind': 'batch', 'intent': job['intent']}


def base_route(job: dict) -> str:
    return 'enqueue'


def handlers(job: dict) -> dict:
    return {'enqueue': enqueue_batch, 'complete': complete_batch}


def gate_for_job(job: dict, operation: str) -> HostGate:
    return HostGate(tuple(sorted(OPERATIONS)), hard_block=job.get('allowed') is not True,
                    approval_required=operation == 'complete',
                    approval_granted=job.get('complete_allowed') is True,
                    baseline_permitted=job.get('allowed') is True)


def validate_job(job: dict, operation: str) -> bool:
    return (job.get('allowed') is True and operation in OPERATIONS
            and job.get('item') in ITEMS and
            type(job.get('job_id')) is str and
            bool(re.fullmatch(r'[A-Za-z0-9_-]{1,64}', job['job_id'])))


def refuse_job(job: dict, reason: str) -> int:
    return 2


def guard_for_job(job: dict) -> RLock:
    return LOCK


def observe_job(job: dict) -> dict:
    return {'count': len(_rows(_owned_file('WORK_QUEUE_EFFECTS')))}


def postcondition(job: dict, result: int, observations: dict) -> bool:
    return result == 0 and observations['after']['count'] == observations['before']['count'] + 1
