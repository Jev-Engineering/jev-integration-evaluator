"""Existing console owner for two finite, independently visible operations."""
from __future__ import annotations

import atexit
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from concurrent.futures import TimeoutError as FutureTimeout

from .alpha import public_entry
from .work_queue import handle_job


EVENTS: list[dict] = []
OBSERVATION: dict = {}


class Audit:
    def append(self, record: dict) -> None:
        EVENTS.append(record)


def limits_alpha() -> dict:
    return {'max_calls_per_task': 2, 'max_cost_per_task': 2,
            'max_total_calls': 2, 'max_total_cost': 2,
            'max_in_flight': 1, 'max_tasks': 1}


def limits_queue() -> dict:
    return limits_alpha()


def audit_alpha() -> Audit:
    return Audit()


def audit_queue() -> Audit:
    return Audit()


def dependencies_alpha() -> dict:
    base = Path(__file__).resolve().parent
    return {'files': [{'path': str(base / name),
                       'sha256': hashlib.sha256((base / name).read_bytes()).hexdigest()}
                      for name in ('requirements.lock', 'runtime.json')]}


def dependencies_queue() -> dict:
    return dependencies_alpha()


def options_alpha() -> dict:
    if os.environ.get('DUAL_SHADOW') != '1':
        return {}
    from jev_integration_evaluator.integrations.probe import SyntheticClient
    return {'startup_mode': 'shadow', 'client': SyntheticClient('alternative'),
            'enable_experiment': True}


def options_queue() -> dict:
    return options_alpha()


def observe_composite_runtime(runtime, request, candidate_ids) -> None:
    routers = [runtime.router(candidate, request) for candidate in candidate_ids]
    def settle_shadow() -> None:
        # The host owns task completion. Let each scheduled comparison finish
        # while that stable task remains open, so its budget denial is observed
        # before generated teardown closes the shared coordinator.
        deadline = time.monotonic() + 10
        for router in routers:
            with router.lock:
                pending = tuple(router.futures)
            for future in pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FutureTimeout('dual_shadow_comparison_timeout')
                future.result(timeout=remaining)

    settle_shadow()
    repeated: list[str] = []
    if os.environ.get('DUAL_REPEAT') == '1':
        # These call the transformed seams while both adapters still share
        # the live coordinator. No direct budget reservation is fabricated.
        for entry in (public_entry, handle_job):
            try:
                entry(request)
                repeated.append('unexpected_success')
            except RuntimeError as error:
                repeated.append(str(error))
        settle_shadow()
    snapshot = runtime.coordinator.snapshot()
    OBSERVATION.update({'tokens': [str(id(router.budget_coordinator)) for router in routers],
                        'scopes': [router.canary_scope for router in routers],
                        'calls': snapshot['calls'], 'cost': snapshot['reserved_cost'],
                        'repeat_results': repeated})
    if os.environ.get('DUAL_HOLD') == '1':
        from . import alpha
        ready = alpha._owned_path('DUAL_READY_PATH')
        release = alpha._owned_path('DUAL_RELEASE_PATH')
        fd = os.open(ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, b'dual-ready\n')
            os.fsync(fd)
        finally:
            os.close(fd)
        deadline = time.monotonic() + 12
        while not release.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('dual_release_missing')
            time.sleep(.01)


def make_alpha() -> dict:
    return {'task_id': os.environ.get('DUAL_TASK_ID', 'dual-task-one'),
            'item': 'fixture-one', 'intent': 'summarize',
            'permit': True, 'approved': True,
            'allowed': True, 'complete_allowed': True}


def make_queue() -> dict:
    return make_alpha()


def main_alpha() -> int:
    request = make_alpha()
    return public_entry(request)


def main_queue() -> int:
    request = make_queue()
    return handle_job(request)


def _write_audit() -> None:
    from . import alpha, work_queue
    import jev_integration_evaluator as evaluator
    assessments = [row for row in EVENTS if row.get('type') == 'assessment']
    output = {'assessed': [row['candidate_id'] for row in assessments],
              'task_hashes': [row['task_id_hash'] for row in assessments],
              'modes': [row['mode'] for row in assessments],
              'tokens': OBSERVATION.get('tokens', []),
              'calls': OBSERVATION.get('calls'), 'cost': OBSERVATION.get('cost'),
              'audit_types': [row.get('type') for row in EVENTS],
              'audit_reasons': [row.get('reason') for row in EVENTS],
              'repeat_results': OBSERVATION.get('repeat_results', []),
              'python_prefix': sys.prefix,
              'python_executable': sys.executable,
              'module_origins': {'alpha': str(Path(alpha.__file__).resolve()),
                                 'queue': str(Path(work_queue.__file__).resolve()),
                                 'console': str(Path(__file__).resolve()),
                                 'evaluator': str(Path(evaluator.__file__).resolve())}}
    Path(os.environ['DUAL_AUDIT_PATH']).write_text(json.dumps(output, sort_keys=True))


if os.environ.get('DUAL_AUDIT_PATH'):
    atexit.register(_write_audit)
