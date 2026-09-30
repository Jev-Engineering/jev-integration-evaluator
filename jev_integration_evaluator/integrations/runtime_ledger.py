"""Durable, single-process budget and effect journal for connected runtimes.

The SQLite file contains only hashed task/effect identifiers and accounting.
An unresolved provider reservation or host effect blocks restart rather than
assuming it failed. The host owns the file and its backup/retention policy.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import threading

from ..budget import BudgetCoordinator
from ..io import InputError, digest


class RuntimeLedger(BudgetCoordinator):
    def __init__(self, path: str | Path, *, identity: str, **limits):
        path = Path(path)
        if not path.is_absolute():
            raise InputError('runtime_ledger_requires_absolute_path')
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise InputError('invalid_runtime_ledger_path')
        path = path.resolve(strict=False)
        database = Path(str(path) + '.sqlite')
        if (not path.is_absolute() or path.is_symlink() or database.is_symlink()
                or not path.parent.is_dir() or path.parent.is_symlink()
                or any(Path(str(database) + suffix).is_symlink() for suffix in ('-wal', '-shm'))):
            raise InputError('invalid_runtime_ledger_path')
        marker_existed = path.exists()
        if marker_existed and not database.exists():
            raise InputError('runtime_ledger_database_missing')
        self._path_identity = os.path.normcase(str(path))
        self._pid = os.getpid()
        try:
            self._file = path.open('a+b')
            self._lock_file()
            self._db = sqlite3.connect(database, timeout=0,
                                       check_same_thread=False, isolation_level=None)
            if os.name != 'nt':
                os.chmod(database, 0o600)
            self._db.execute('PRAGMA synchronous=FULL')
            self._db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            self._db.execute('CREATE TABLE IF NOT EXISTS effects (identity TEXT PRIMARY KEY, status TEXT NOT NULL)')
            super().__init__(**limits)
            self.identity = identity
            self._durably_revoked = False
            row = self._db.execute('SELECT payload FROM state WHERE id=1').fetchone()
            if row is None:
                self._save()
            else:
                state = json.loads(row[0])
                if (state['identity'] != identity or state['limits'] != self.limits
                        or state['ledger_path'] != self._path_identity):
                    raise InputError('runtime_ledger_identity_or_limits_changed')
                self._tasks = state['tasks']
                self._inflight = {k: tuple(v) for k, v in state['inflight'].items()}
                self._calls = state['calls']
                self._cost = state['cost']
                self._suspended = state['revoked']
                self._durably_revoked = state['revoked']
                self._overruns = state['overruns']
                if self._inflight or self._db.execute("SELECT 1 FROM effects WHERE status='pending' LIMIT 1").fetchone():
                    raise InputError('runtime_ledger_unresolved_history')
                if self._suspended:
                    raise InputError('runtime_ledger_revoked')
        except Exception as exc:
            self.release()
            if not marker_existed and not database.exists():
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            if isinstance(exc, InputError):
                raise
            raise InputError('runtime_ledger_unavailable') from None

    def _lock_file(self):
        self._file.seek(0)
        if os.name == 'nt':
            import msvcrt
            self._file.seek(0, 2)
            if self._file.tell() == 0:
                self._file.write(b'0')
            self._file.flush()
            self._file.seek(0)
            try:
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self._file.close()
                raise InputError('runtime_ledger_owned_by_another_process') from None
        else:
            import fcntl
            try:
                fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self._file.close()
                raise InputError('runtime_ledger_owned_by_another_process') from None

    def _save(self):
        state = dict(identity=self.identity, ledger_path=self._path_identity,
                     limits=self.limits, tasks=self._tasks,
                     inflight=self._inflight, calls=self._calls, cost=self._cost,
                     revoked=self._durably_revoked, overruns=self._overruns)
        try:
            self._db.execute('BEGIN IMMEDIATE')
            self._db.execute('INSERT OR REPLACE INTO state(id,payload) VALUES(1,?)',
                             (json.dumps(state, sort_keys=True, allow_nan=False),))
            self._db.execute('COMMIT')
        except BaseException:
            try:
                if self._db.in_transaction:
                    self._db.execute('ROLLBACK')
            except sqlite3.Error:
                pass
            self._suspended = True
            raise InputError('runtime_ledger_write_failed') from None

    def reserve(self, task_id, cost_upper_bound):
        self._check_owner()
        with self._lock:
            reservation = super().reserve(task_id, cost_upper_bound)
            self._save()  # Must commit before the caller can issue provider I/O.
            return reservation

    def settle(self, reservation, *, actual_cost=None):
        self._check_owner()
        with self._lock:
            super().settle(reservation, actual_cost=actual_cost)
            if self._overruns:
                self._durably_revoked = True
            self._save()  # A crash before commit retains unresolved reservation.

    def close_task(self, task_id):
        self._check_owner()
        with self._lock:
            super().close_task(task_id)
            self._save()

    def suspend(self, *, durable=True):
        self._check_owner()
        with self._lock:
            super().suspend()
            if durable:
                self._durably_revoked = True
                self._save()

    def claim_effect(self, task_id: str, request_hash: str,
                     placement: str, operation: str) -> str:
        self._check_owner()
        if not placement or not operation:
            raise InputError('runtime_effect_identity_required')
        key = digest([self.identity, digest(task_id), request_hash,
                      placement, operation])
        with self._lock:
            try:
                self._db.execute('INSERT INTO effects(identity,status) VALUES(?,?)', (key, 'pending'))
            except sqlite3.IntegrityError:
                raise InputError('runtime_effect_already_claimed') from None
            except sqlite3.Error:
                self.suspend()
                raise InputError('runtime_effect_journal_unavailable') from None
        return key

    @contextmanager
    def effect_boundary(self):
        """Serialize local suspension with the final gate and host executor."""
        self._check_owner()
        with self._lock:
            yield

    def complete_effect(self, key: str) -> None:
        self._check_owner()
        with self._lock:
            try:
                completed = self._db.execute("UPDATE effects SET status='completed' WHERE identity=? AND status='pending'", (key,)).rowcount == 1
            except sqlite3.Error:
                completed = False
            if not completed:
                self.suspend()
                raise InputError('runtime_effect_completion_unavailable')

    def _check_owner(self) -> None:
        if os.getpid() != self._pid:
            raise InputError('runtime_ledger_forked')

    def release(self):
        db = getattr(self, '_db', None)
        if db is not None:
            db.close()
        file = getattr(self, '_file', None)
        if file is not None and not file.closed:
            file.close()
