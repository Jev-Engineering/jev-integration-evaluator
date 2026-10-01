"""Durable, single-process budget and effect journal for connected runtimes.

The SQLite file contains only hashed task/effect identifiers and accounting.
An unresolved provider reservation or host effect blocks restart rather than
assuming it failed. The host owns the file and its backup/retention policy.
"""
from __future__ import annotations

import json
import copy
from datetime import datetime, timezone
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import stat
import threading

from ..budget import BudgetCoordinator
from ..io import InputError, digest
from ..contracts import parse_utc, validate_contract


# Upper bound, in seconds, that the owning connection waits for a competing
# SQLite lock before a durable write fails closed.
OWNER_BUSY_SECONDS = 2.0


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
            # Single ownership is the marker-file lock above, not this
            # timeout. A bounded wait lets a durable commit outlast a
            # transient read-only inspection instead of latching the owner
            # off; a lock held past the bound still fails closed.
            self._db = sqlite3.connect(database, timeout=OWNER_BUSY_SECONDS,
                                       check_same_thread=False, isolation_level=None)
            if os.name != 'nt':
                os.chmod(database, 0o600)
            self._db.execute('PRAGMA synchronous=FULL')
            self._db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            self._db.execute('CREATE TABLE IF NOT EXISTS effects (identity TEXT PRIMARY KEY, status TEXT NOT NULL)')
            super().__init__(**limits)
            self.identity = identity
            self._generation = None
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
                self._generation = state.get('generation')
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

    def _state(self):
        state = dict(identity=self.identity, ledger_path=self._path_identity,
                     limits=self.limits, tasks=self._tasks,
                     inflight=self._inflight, calls=self._calls, cost=self._cost,
                     revoked=self._durably_revoked, overruns=self._overruns)
        if self._generation is not None:
            state['generation'] = self._generation
        return state

    def _save(self):
        state = self._state()
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
        owner_identity = self.identity
        if self._generation is not None:
            owner_identity = self._generation['effect_owner_identity']
            if placement not in self._generation['placements']:
                raise InputError('runtime_effect_unregistered_generation_placement')
            placement = self._generation['placements'][placement]
        key = digest([owner_identity, digest(task_id), request_hash, placement, operation])
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

    def generation_snapshot(self) -> dict:
        """Hash exact accounting and effect history while holding ownership.

        This read-only snapshot is evidence, never transfer or egress authority.
        It contains hashes and accounting, not raw tasks or provider requests.
        """
        self._check_owner()
        with self._lock:
            effects = [list(row) for row in self._db.execute(
                'SELECT identity,status FROM effects ORDER BY identity')]
            return copy.deepcopy(dict(state=self._state(), effects=effects))

    @classmethod
    def transfer_generation(cls, path, *, grant, verify_authority):
        """Transfer a stopped workflow without resetting spend or launching it.

        The host must authenticate the exact grant independently and derive its
        identities/placement mapping from reviewed old and new installed bindings.
        An existing owner, unfinished task or uncertain effect blocks transfer.
        SQLite commits the new identity and lineage together; an interruption
        leaves either complete old or complete new state, never a fresh ledger.
        """
        grant = copy.deepcopy(grant)
        validate_contract(grant, 'connected-generation-transfer-v1')
        grant_sha = digest(grant)
        try:
            authenticated = verify_authority('generation_transfer', grant_sha) is True
        except Exception:
            authenticated = False
        if not authenticated:
            raise InputError('runtime_generation_transfer_unverified')
        now = datetime.now(timezone.utc)
        if not parse_utc(grant['issued_at']) <= now < parse_utc(grant['expires_at']):
            raise InputError('runtime_generation_transfer_expired')
        path = Path(path)
        if not path.is_absolute() or not path.is_file() or not Path(str(path) + '.sqlite').is_file():
            raise InputError('runtime_generation_existing_ledger_required')
        ledger = cls(path, identity=grant['old_identity'], **grant['limits'])
        try:
            with ledger._lock:
                before = ledger.generation_snapshot()
                if digest(before) != grant['history_sha256']:
                    raise InputError('runtime_generation_history_changed')
                if (ledger._inflight or ledger._durably_revoked or ledger._overruns
                        or any(not task['closed'] for task in ledger._tasks.values())
                        or any(status != 'completed' for _, status in before['effects'])):
                    raise InputError('runtime_generation_not_quiescent')
                old = grant['old_placements']
                mapping = grant['new_to_old_placements']
                if (len(set(old)) != len(old) or len(mapping) != len(old)
                        or set(mapping.values()) != set(old)
                        or grant['old_identity'] == grant['new_identity']):
                    raise InputError('runtime_generation_placement_mapping_invalid')
                previous = ledger._generation
                if previous is not None and set(previous['placements']) != set(old):
                    raise InputError('runtime_generation_placement_mapping_invalid')
                generation = dict(
                    effect_owner_identity=(previous['effect_owner_identity'] if previous else ledger.identity),
                    placements={new: (previous['placements'][prior] if previous else prior)
                                for new, prior in mapping.items()},
                    sequence=(previous['sequence'] + 1 if previous else 1),
                    grant_sha256=grant_sha, previous_history_sha256=grant['history_sha256'])
                after_state = copy.deepcopy(before['state'])
                after_state['identity'] = grant['new_identity']
                after_state['generation'] = generation
                after = dict(state=after_state, effects=before['effects'])
                receipt = dict(kind='connected-generation-transfer-receipt-v1',
                               grant_sha256=grant_sha, before_sha256=digest(before),
                               after_sha256=digest(after), sequence=generation['sequence'])
                # Authenticate and check expiry again immediately before mutation.
                try:
                    authenticated = verify_authority('generation_transfer', grant_sha) is True
                except Exception:
                    authenticated = False
                if not authenticated:
                    raise InputError('runtime_generation_transfer_unverified')
                if not parse_utc(grant['issued_at']) <= datetime.now(timezone.utc) < parse_utc(grant['expires_at']):
                    raise InputError('runtime_generation_transfer_expired')
                try:
                    ledger._db.execute('BEGIN IMMEDIATE')
                    row = ledger._db.execute('SELECT payload FROM state WHERE id=1').fetchone()
                    current_effects = [list(row) for row in ledger._db.execute(
                        'SELECT identity,status FROM effects ORDER BY identity')]
                    if json.loads(row[0]) != before['state'] or current_effects != before['effects']:
                        raise InputError('runtime_generation_history_changed')
                    try:
                        authenticated = verify_authority('generation_transfer', grant_sha) is True
                    except Exception:
                        authenticated = False
                    if not authenticated:
                        raise InputError('runtime_generation_transfer_unverified')
                    if not parse_utc(grant['issued_at']) <= datetime.now(timezone.utc) < parse_utc(grant['expires_at']):
                        raise InputError('runtime_generation_transfer_expired')
                    ledger._db.execute('CREATE TABLE IF NOT EXISTS generation_transfers '
                                       '(grant_sha256 TEXT PRIMARY KEY, payload TEXT NOT NULL)')
                    ledger._db.execute('UPDATE state SET payload=? WHERE id=1',
                        (json.dumps(after_state, sort_keys=True, allow_nan=False),))
                    ledger._db.execute('INSERT INTO generation_transfers VALUES(?,?)',
                        (grant_sha, json.dumps(receipt, sort_keys=True, allow_nan=False)))
                    ledger._db.execute('COMMIT')
                except BaseException as exc:
                    if ledger._db.in_transaction:
                        ledger._db.execute('ROLLBACK')
                    if isinstance(exc, sqlite3.Error):
                        raise InputError('runtime_generation_transfer_unavailable') from None
                    raise
                ledger.identity = grant['new_identity']
                ledger._generation = generation
                if ledger.generation_snapshot() != after:
                    raise InputError('runtime_generation_transfer_postcondition_failed')
                return receipt
        finally:
            ledger.release()

    @classmethod
    def generation_transfer_status(cls, path, *, grant, verify_authority,
                                   on_current=None):
        """Read a committed transfer receipt without replay, startup or writes.

        Expired grants can authenticate historical receipt readback. An active
        ledger owner blocks this inspection; the caller must retain the exact
        grant digest independently. Revoked/pending runtime state stays intact.
        """
        grant = copy.deepcopy(grant)
        validate_contract(grant, 'connected-generation-transfer-v1')
        grant_sha = digest(grant)
        try:
            authenticated = verify_authority('generation_transfer', grant_sha) is True
        except Exception:
            authenticated = False
        if not authenticated:
            raise InputError('runtime_generation_transfer_unverified')
        path = Path(path)
        database = Path(str(path) + '.sqlite')
        if (not path.is_absolute() or not path.is_file() or not database.is_file()
                or any(part.is_symlink() for part in (path, database, *path.parents))
                or any(Path(str(database) + suffix).is_symlink() for suffix in ('-wal', '-shm'))):
            raise InputError('runtime_generation_existing_ledger_required')
        def private_file(target: Path, *, marker: bool = False) -> bool:
            info = target.stat()
            return (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and info.st_nlink == 1 and not (info.st_mode & 0o022)
                    and (marker or not (info.st_mode & 0o077)))
        if os.name != 'nt':
            parent_info = path.parent.stat()
            if (not stat.S_ISDIR(parent_info.st_mode)
                    or parent_info.st_uid != os.getuid()
                    or parent_info.st_mode & 0o077
                    or not private_file(path, marker=True)
                    or not private_file(database)
                    or any(sidecar.exists() and not private_file(sidecar) for sidecar in
                           (Path(str(database) + '-wal'), Path(str(database) + '-shm')))):
                raise InputError('runtime_generation_ledger_permissions_changed')
        holder = cls.__new__(cls)
        try:
            holder._file = path.open('r+b')
            if os.name != 'nt':
                opened = os.fstat(holder._file.fileno())
                named = path.stat()
                if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino) or not private_file(path, marker=True):
                    raise InputError('runtime_generation_ledger_permissions_changed')
            holder._lock_file()
            holder._db = sqlite3.connect(database.resolve().as_uri() + '?mode=ro',
                                        uri=True, timeout=0, isolation_level=None)
            holder._db.execute('BEGIN IMMEDIATE' if on_current is not None else 'BEGIN')
            table = holder._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                       "AND name='generation_transfers'").fetchone()
            row = (holder._db.execute('SELECT payload FROM generation_transfers WHERE grant_sha256=?',
                                      (grant_sha,)).fetchone() if table else None)
            state_row = holder._db.execute('SELECT payload FROM state WHERE id=1').fetchone()
            if state_row is None:
                raise InputError('runtime_generation_history_unavailable')
            state = json.loads(state_row[0])
            effects = [list(item) for item in holder._db.execute(
                'SELECT identity,status FROM effects ORDER BY identity')]
            current_history_sha = digest(dict(state=state, effects=effects))
            current_generation_sha = (state.get('generation') or {}).get('grant_sha256')
            if row is None:
                status = dict(kind='connected-generation-transfer-status-v1',
                            status=('not_transferred' if state['identity'] == grant['old_identity']
                                    and digest(dict(state=state, effects=effects)) == grant['history_sha256']
                                    else 'history_changed'), receipt=None,
                            grant_sha256=grant_sha, current_identity=state['identity'],
                            current_history_sha256=current_history_sha,
                            current_generation_grant_sha256=current_generation_sha)
                validate_contract(status, 'connected-generation-transfer-status-v1')
                return status
            receipt = json.loads(row[0])
            validate_contract(receipt, 'connected-generation-transfer-receipt-v1')
            if receipt['grant_sha256'] != grant_sha or receipt['before_sha256'] != grant['history_sha256']:
                raise InputError('runtime_generation_receipt_changed')
            status = dict(kind='connected-generation-transfer-status-v1', status='committed',
                          receipt=receipt, grant_sha256=grant_sha, current_identity=state['identity'],
                          current_history_sha256=current_history_sha,
                          current_generation_grant_sha256=current_generation_sha)
            validate_contract(status, 'connected-generation-transfer-status-v1')
            if on_current is not None:
                on_current(status)
            return status
        except InputError:
            raise
        except (OSError, sqlite3.Error, ValueError, KeyError):
            raise InputError('runtime_generation_history_unavailable') from None
        finally:
            holder.release()

    def release(self):
        db = getattr(self, '_db', None)
        if db is not None:
            db.close()
        file = getattr(self, '_file', None)
        if file is not None and not file.closed:
            file.close()
