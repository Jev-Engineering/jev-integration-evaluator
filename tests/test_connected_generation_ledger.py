"""Cryptographically authenticated synthetic transfers; no provider traffic."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import sqlite3
import os

import pytest

from jev_integration_evaluator.budget import BudgetDenied
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
from jev_integration_evaluator.io import InputError, digest


LIMITS = dict(max_calls_per_task=2, max_cost_per_task=1,
              max_total_calls=3, max_total_cost=2, max_in_flight=2, max_tasks=4)
OLD, NEW = digest('old reviewed runtime'), digest('new reviewed runtime')


def authenticated(grant):
    # The private issuer authenticates one frozen grant digest, outside the ledger.
    key = secrets.token_bytes(32)
    signature = hmac.digest(key, digest(grant).encode(), hashlib.sha256)
    def verifier(kind, sha):
        return kind == 'generation_transfer' and hmac.compare_digest(
            signature, hmac.digest(key, sha.encode(), hashlib.sha256))
    return verifier


def grant_for(ledger, *, new_identity=NEW, old_placements=None, mapping=None):
    now = datetime.now(timezone.utc)
    return dict(schema_version='1.0', kind='connected-generation-transfer-v1',
                action='upgrade', old_identity=ledger.identity, new_identity=new_identity,
                old_plan_sha256=digest('old approved plan'),
                new_plan_sha256=digest('new approved plan'),
                old_binding_sha256=digest('old binding'), new_binding_sha256=digest('new binding'),
                session_head_sha256=digest('stopped session head'),
                history_sha256=digest(ledger.generation_snapshot()), limits=ledger.limits,
                old_placements=old_placements or ['old-placement'],
                new_to_old_placements=mapping or {'new-placement': 'old-placement'},
                issued_at=(now-timedelta(minutes=1)).isoformat(),
                expires_at=(now+timedelta(minutes=1)).isoformat())


def test_upgrade_and_reverse_transfer_preserve_spend_tasks_and_effect_lineage(tmp_path):
    path = tmp_path / 'ledger'
    ledger = RuntimeLedger(path, identity=OLD, **LIMITS)
    reservation = ledger.reserve('completed-task', .25)
    ledger.settle(reservation)
    effect = ledger.claim_effect('completed-task', digest('request'), 'old-placement', 'registry:run')
    ledger.complete_effect(effect)
    ledger.close_task('completed-task')
    grant = grant_for(ledger)
    before = ledger.generation_snapshot()
    ledger.release()
    receipt = RuntimeLedger.transfer_generation(path, grant=grant, verify_authority=authenticated(grant))
    assert receipt['before_sha256'] == digest(before)
    with pytest.raises(InputError, match='identity_or_limits_changed'):
        RuntimeLedger(path, identity=OLD, **LIMITS)
    upgraded = RuntimeLedger(path, identity=NEW, **LIMITS)
    assert upgraded.snapshot()['calls'] == 1
    assert upgraded.snapshot()['reserved_cost'] == .25
    assert upgraded.snapshot()['closed_tasks'] == 1
    assert upgraded.generation_snapshot()['effects'] == before['effects']
    with pytest.raises(BudgetDenied, match='shared_task_closed'):
        upgraded.reserve('completed-task', .25)
    with pytest.raises(InputError, match='already_claimed'):
        upgraded.claim_effect('completed-task', digest('request'), 'new-placement', 'registry:run')
    reservation = upgraded.reserve('new-task', .25)
    upgraded.settle(reservation)
    upgraded.close_task('new-task')
    rollback = grant_for(upgraded, new_identity=OLD, old_placements=['new-placement'],
                         mapping={'old-placement': 'new-placement'})
    rollback['action'] = 'rollback'
    upgraded.release()
    receipt = RuntimeLedger.transfer_generation(path, grant=rollback, verify_authority=authenticated(rollback))
    assert receipt['sequence'] == 2
    restored = RuntimeLedger(path, identity=OLD, **LIMITS)
    assert restored.snapshot()['calls'] == 2
    assert restored.snapshot()['closed_tasks'] == 2
    with pytest.raises(InputError, match='already_claimed'):
        restored.claim_effect('completed-task', digest('request'), 'old-placement', 'registry:run')
    restored.release()


@pytest.mark.parametrize('fault', ['signature', 'expired', 'history', 'limits', 'mapping', 'unfinished', 'owned'])
def test_transfer_refuses_unsafe_state_without_changing_history(tmp_path, fault):
    path = tmp_path / 'ledger'
    ledger = RuntimeLedger(path, identity=OLD, **LIMITS)
    reservation = ledger.reserve('task', .25)
    ledger.settle(reservation)
    if fault != 'unfinished':
        ledger.close_task('task')
    grant = grant_for(ledger)
    before = ledger.generation_snapshot()
    verifier = authenticated(grant)
    if fault == 'signature':
        grant['new_identity'] = digest('unauthorized target')
    elif fault == 'expired':
        grant['expires_at'] = grant['issued_at']
    elif fault == 'history':
        grant['history_sha256'] = digest('stale history')
    elif fault == 'limits':
        grant['limits']['max_total_calls'] += 1
    elif fault == 'mapping':
        grant['new_to_old_placements'] = {'new-placement': 'unreviewed'}
    if fault != 'signature':
        verifier = authenticated(grant)
    if fault != 'owned':
        ledger.release()
    with pytest.raises(InputError):
        RuntimeLedger.transfer_generation(path, grant=grant, verify_authority=verifier)
    if fault != 'owned':
        ledger = RuntimeLedger(path, identity=OLD, **LIMITS)
    assert ledger.generation_snapshot() == before
    ledger.release()


def test_legacy_payload_remains_unchanged_without_transfer(tmp_path):
    ledger = RuntimeLedger(tmp_path / 'legacy', identity=OLD, **LIMITS)
    assert 'generation' not in ledger.generation_snapshot()['state']
    ledger.close_task('task')
    assert 'generation' not in ledger.generation_snapshot()['state']
    ledger.release()


@pytest.mark.parametrize('fault', ['provider_pending', 'effect_pending', 'revoked'])
def test_transfer_never_reconciles_uncertain_or_revoked_history(tmp_path, fault):
    path = tmp_path / 'ledger'
    ledger = RuntimeLedger(path, identity=OLD, **LIMITS)
    if fault == 'provider_pending':
        ledger.reserve('task', .25)
    elif fault == 'effect_pending':
        ledger.claim_effect('task', digest('request'), 'old-placement', 'registry:run')
    else:
        ledger.suspend()
    grant = grant_for(ledger)
    ledger.release()
    database = path.with_name(path.name + '.sqlite')
    with sqlite3.connect(database) as connection:
        before = connection.execute('SELECT payload FROM state').fetchall()
        effects = connection.execute('SELECT * FROM effects').fetchall()
    with pytest.raises(InputError, match='unresolved_history|revoked'):
        RuntimeLedger.transfer_generation(path, grant=grant, verify_authority=authenticated(grant))
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT payload FROM state').fetchall() == before
        assert connection.execute('SELECT * FROM effects').fetchall() == effects


@pytest.mark.parametrize('committed', [False, True])
def test_interrupted_transfer_keeps_one_complete_generation(tmp_path, committed):
    path = tmp_path / 'ledger'
    ledger = RuntimeLedger(path, identity=OLD, **LIMITS)
    ledger.close_task('task')
    grant = grant_for(ledger)
    ledger.release()
    class InterruptedLedger(RuntimeLedger):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            database = self._db
            class Connection:
                def __getattr__(self, name):
                    return getattr(database, name)
                def execute(self, sql, *args):
                    if sql == 'COMMIT':
                        if committed:
                            database.execute(sql)
                        raise sqlite3.OperationalError('synthetic lost commit acknowledgement')
                    return database.execute(sql, *args)
            self._db = Connection()
    with pytest.raises(InputError, match='transfer_unavailable'):
        InterruptedLedger.transfer_generation(path, grant=grant, verify_authority=authenticated(grant))
    surviving = RuntimeLedger(path, identity=NEW if committed else OLD, **LIMITS)
    state = surviving.generation_snapshot()['state']
    assert state['tasks'][digest('task')]['closed'] is True
    assert ('generation' in state) is committed
    surviving.release()
    status = RuntimeLedger.generation_transfer_status(path, grant=grant,
                                                     verify_authority=authenticated(grant))
    assert status['status'] == ('committed' if committed else 'not_transferred')
    assert (status['receipt'] is not None) is committed
    if committed:
        assert status['receipt']['before_sha256'] == grant['history_sha256']


@pytest.mark.parametrize('fault', ['authority_revoked', 'external_effect_drift'])
def test_final_boundary_rechecks_authority_and_exact_effect_history(tmp_path, fault):
    path = tmp_path / 'ledger'
    ledger = RuntimeLedger(path, identity=OLD, **LIMITS)
    ledger.close_task('task')
    grant = grant_for(ledger)
    before = ledger.generation_snapshot()
    ledger.release()
    original = authenticated(grant)
    calls = 0
    def verifier(kind, sha):
        nonlocal calls
        calls += 1
        valid = original(kind, sha)
        if calls == 2:
            if fault == 'authority_revoked':
                return False
            # Simulate a writer violating the marker lease. Transfer must still
            # notice changed effects inside its own transaction before mutation.
            with sqlite3.connect(str(path) + '.sqlite') as connection:
                connection.execute('INSERT INTO effects VALUES(?,?)',
                                   (digest('external effect'), 'completed'))
        return valid
    with pytest.raises(InputError, match='unverified|history_changed'):
        RuntimeLedger.transfer_generation(path, grant=grant, verify_authority=verifier)
    restored = RuntimeLedger(path, identity=OLD, **LIMITS)
    assert restored.generation_snapshot()['state'] == before['state']
    restored.release()


@pytest.mark.parametrize('drift', ['marker_hardlink', 'database_hardlink',
                                   'marker_permissions', 'database_permissions'])
def test_historical_status_refuses_ledger_file_identity_or_permission_drift(tmp_path, drift):
    path = tmp_path / 'ledger'
    ledger = RuntimeLedger(path, identity=OLD, **LIMITS)
    ledger.close_task('task')
    grant = grant_for(ledger)
    ledger.release()
    RuntimeLedger.transfer_generation(path, grant=grant, verify_authority=authenticated(grant))
    target = path if drift.startswith('marker') else path.with_name(path.name + '.sqlite')
    original_mode = target.stat().st_mode & 0o777
    peer = tmp_path / 'other-link'
    try:
        if drift.endswith('hardlink'):
            os.link(target, peer)
        else:
            target.chmod(0o666)
        with pytest.raises(InputError, match='ledger_permissions_changed'):
            RuntimeLedger.generation_transfer_status(path, grant=grant,
                                                       verify_authority=authenticated(grant))
    finally:
        peer.unlink(missing_ok=True)
        target.chmod(original_mode)
    recovered = RuntimeLedger.generation_transfer_status(path, grant=grant,
        verify_authority=authenticated(grant))
    assert recovered['status'] == 'committed'
    assert recovered['current_generation_grant_sha256'] == digest(grant)
    assert recovered['current_history_sha256'] == recovered['receipt']['after_sha256']
