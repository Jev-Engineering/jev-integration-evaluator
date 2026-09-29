"""Normal installed command for the independent work-queue host."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from .engine import handle_job


class Audit:
    def append(self, record) -> None:
        path = Path(os.environ['WORK_QUEUE_AUDIT'])
        if (not path.is_absolute() or path.is_symlink() or
                any(parent.is_symlink() for parent in path.parents) or
                path.parent.stat().st_uid != os.getuid() or
                stat.S_IMODE(path.parent.stat().st_mode) & 0o077):
            raise RuntimeError('queue_audit_path_invalid')
        raw = json.dumps(record, sort_keys=True, default=str).encode()
        summary = {'record_sha256': hashlib.sha256(raw).hexdigest()}
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
                raise RuntimeError('queue_audit_file_invalid')
            os.write(fd, (json.dumps(summary, sort_keys=True) + '\n').encode())
            os.fsync(fd)
        finally:
            os.close(fd)


def limits() -> dict:
    return {'max_calls_per_task': 2, 'max_cost_per_task': 2, 'max_total_calls': 2,
            'max_total_cost': 2, 'max_in_flight': 1, 'max_tasks': 1}


def audit() -> Audit:
    return Audit()


def dependencies() -> dict:
    base = Path(__file__).resolve().parent
    return {'files': [{'path': str(base / name),
                       'sha256': hashlib.sha256((base / name).read_bytes()).hexdigest()}
                      for name in ('requirements.lock', 'runtime.json')]}


def options() -> dict:
    return {}


def _flag(name: str, default: str) -> bool:
    value = os.environ.get(name, default)
    if value not in ('0', '1'):
        raise ValueError('invalid_' + name.lower())
    return value == '1'


def make_job() -> dict:
    intent = os.environ.get('WORK_QUEUE_INTENT', 'enqueue')
    item = os.environ.get('WORK_QUEUE_ITEM', 'batch-a')
    job_id = os.environ.get('WORK_QUEUE_JOB_ID', 'queue-baseline')
    if intent not in ('enqueue', 'complete') or item not in ('batch-a', 'batch-b'):
        raise ValueError('invalid_work_queue_choice')
    if not job_id or len(job_id) > 64 or not job_id.isascii() or not all(
            char.isalnum() or char in '_-' for char in job_id):
        raise ValueError('invalid_work_queue_job_id')
    return {'job_id': job_id, 'item': item, 'intent': intent,
            'allowed': _flag('WORK_QUEUE_ALLOWED', '1'),
            'complete_allowed': _flag('WORK_QUEUE_COMPLETE_ALLOWED', '0')}


def main() -> int:
    job = make_job()
    return handle_job(job)
