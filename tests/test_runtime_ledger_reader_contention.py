"""A transient read-only ledger inspection must not suspend the owning runtime."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading

import pytest

from jev_integration_evaluator.integrations import runtime_ledger
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
from jev_integration_evaluator.io import InputError, digest

LIMITS = dict(max_calls_per_task=2, max_cost_per_task=1,
              max_total_calls=3, max_total_cost=2, max_in_flight=2, max_tasks=4)
IDENTITY = digest('reviewed runtime')


def _reader(path: Path) -> sqlite3.Connection:
    """Open an independent read-only inspection that holds a shared read lock."""
    reader = sqlite3.connect(Path(str(path) + '.sqlite').resolve().as_uri() + '?mode=ro',
                             uri=True, timeout=0, isolation_level=None,
                             check_same_thread=False)
    reader.execute('BEGIN')
    assert reader.execute('SELECT payload FROM state WHERE id=1').fetchone() is not None
    return reader


def test_owner_commit_waits_out_a_transient_read_only_inspection(tmp_path):
    path = tmp_path / 'ledger'
    ledger = RuntimeLedger(path, identity=IDENTITY, **LIMITS)
    reader = _reader(path)
    released = threading.Timer(0.3, lambda: (reader.execute('ROLLBACK'), reader.close()))
    released.start()
    try:
        reservation = ledger.reserve('task-one', 0.5)
    finally:
        released.join()
    assert reservation is not None
    # The charge is durable and the owner was not latched off by the inspection.
    with sqlite3.connect(Path(str(path) + '.sqlite')) as check:
        assert json.loads(check.execute(
            'SELECT payload FROM state WHERE id=1').fetchone()[0])['calls'] == 1
    ledger.reserve('task-two', 0.5)
    ledger.release()


def test_owner_still_fails_closed_when_a_reader_outlasts_the_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_ledger, 'OWNER_BUSY_SECONDS', 0.2)
    path = tmp_path / 'ledger'
    ledger = RuntimeLedger(path, identity=IDENTITY, **LIMITS)
    reader = _reader(path)
    try:
        with pytest.raises(InputError, match='^runtime_ledger_write_failed$'):
            ledger.reserve('task-one', 0.5)
    finally:
        reader.execute('ROLLBACK')
        reader.close()
    # A failed durable write latches the owner off; it never resumes on its own.
    with pytest.raises(InputError):
        ledger.reserve('task-one', 0.5)
    with sqlite3.connect(Path(str(path) + '.sqlite')) as check:
        assert json.loads(check.execute(
            'SELECT payload FROM state WHERE id=1').fetchone()[0])['calls'] == 0
    ledger.release()
