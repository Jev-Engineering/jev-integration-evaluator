"""Synthetic state and process checks for the owned Linux console delivery profile."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import platform
import subprocess
import sys

import pytest

from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator import template_delivery as delivery


pytestmark = pytest.mark.skipif(
    not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
         and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)),
    reason='Delivery process profile is Linux x86-64 CPython 3.13 only')


def _scope(result, plan, *, launch=False, stop=False, disable=False,
           revoked=False, expires=None):
    value = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
             'reference': 'independent-synthetic-operator', 'run_id': result['run_id'],
             'plan_sha256': plan['plan_sha256'],
             'trusted_session_head': result['session_head_sha256'],
             'expires_at': (expires or datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
             'revoked': revoked,
             'grants': {'launch': launch, 'stop': stop, 'disable': disable,
                        'rollback': False, 'upgrade': False}}
    value['scope_sha256'] = digest(value)
    return value


def _fake_installed(tmp_path, monkeypatch, *, pause=5, receipts=None):
    root = tmp_path / 'installed'
    script = root / 'venv/bin/fixture-console'
    script.parent.mkdir(parents=True)
    marker = tmp_path / 'effect.bin'
    ready = tmp_path / 'ready.bin'
    content = f'''#!{sys.executable}
import os,time
from pathlib import Path
Path(os.environ["DELIVERY_EFFECT_PATH"]).write_bytes(b"actual-owned-effect")
Path(os.environ["DELIVERY_READY_PATH"]).write_bytes(b"ready")
time.sleep({pause})
'''
    script.write_text(content, encoding='utf-8')
    script.chmod(0o700)
    receipt = {'environment': str(root), 'generation_id': 'jev-env-' + root.parent.name,
               'installed': {'console_script': str(script),
                             'console_script_sha256': file_hash(script),
                             'entrypoint_origin': str(script)}}
    receipts = receipts if receipts is not None else {}
    receipts[str(root)] = receipt
    monkeypatch.setattr(delivery, '_receipt',
                        lambda install_plan, _anchor: receipts[install_plan['fake_generation']])
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [
                       {'role': 'ready', 'path': str(ready), 'before_sha256': None,
                        'expected_sha256': digest_bytes(b'ready')}]
                   + [
                       {'role': role, 'path': str(marker), 'before_sha256': None,
                        'expected_sha256': digest_bytes(b'actual-owned-effect')}
                       for role in ('entrypoint_reached', 'integration_reachable', 'outcome_verified')
                   ]}
    plan = delivery.plan_delivery({'schema_version': '1.0', 'fake_generation': str(root)},
                                  trusted_install_receipt_sha256='a' * 64,
                                  observation=observation,
                                  launch_environment={'DELIVERY_EFFECT_PATH': str(marker),
                                                      'DELIVERY_READY_PATH': str(ready)})
    return plan, marker


def digest_bytes(raw: bytes) -> str:
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def test_launch_observe_disable_and_exact_current_health(tmp_path, monkeypatch):
    plan, effect = _fake_installed(tmp_path, monkeypatch, pause=30)
    session = tmp_path / 'session'
    created = delivery.create_session(session, plan)
    unanchored = delivery.session_status(session)
    assert unanchored['evidence_trust'] == 'recorded_untrusted'
    assert created['recorded_observations']['installed'] is True
    assert created['recorded_observations']['launched'] is False
    refused = _scope(created, plan, launch=True, revoked=True)
    with pytest.raises(delivery.DeliveryError, match='exact_delivery_scope'):
        delivery.launch_session(session, scope=refused,
                                approved_scope_sha256=refused['scope_sha256'])
    expired = _scope(created, plan, launch=True,
                     expires=datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(delivery.DeliveryError, match='delivery_scope_expired'):
        delivery.launch_session(session, scope=expired,
                                approved_scope_sha256=expired['scope_sha256'])
    assert not effect.exists()
    authorized = _scope(created, plan, launch=True)
    launched = delivery.launch_session(session, scope=authorized,
                                       approved_scope_sha256=authorized['scope_sha256'])
    assert launched['recorded_observations']['launched'] is True
    assert launched['recorded_observations']['mode_authorized'] is True
    with pytest.raises(delivery.DeliveryError, match='already_running'):
        again = _scope(launched, plan, launch=True)
        delivery.launch_session(session, scope=again,
                                approved_scope_sha256=again['scope_sha256'])
    import time
    observed = launched
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        observed = delivery.observe_session(session,
                                            trusted_session_head=observed['session_head_sha256'])
        if observed['recorded_observations']['outcome_verified']:
            break
        time.sleep(0.01)
    assert observed['recorded_observations']['entrypoint_reached'] is True
    assert observed['recorded_observations']['integration_reachable'] is True
    assert observed['recorded_observations']['outcome_verified'] is True
    assert observed['recorded_observations']['provider_reachable'] is False
    assert observed['current_process_alive'] is True
    stop_scope = _scope(observed, plan, disable=True)
    stopped = delivery.stop_session(session, scope=stop_scope,
                                    approved_scope_sha256=stop_scope['scope_sha256'], disable=True)
    assert stopped['stage'] == 'disabled'
    assert stopped['current_process_alive'] is False
    assert delivery.session_status(session, trusted_session_head=stopped['session_head_sha256'])['evidence_trust'] == 'externally_anchored_history'


def test_unreleased_launch_is_retryable_and_unknown_effect_blocks(tmp_path, monkeypatch):
    plan, effect = _fake_installed(tmp_path, monkeypatch, pause=0)
    session = tmp_path / 'session'
    created = delivery.create_session(session, plan)
    target, rows, state, _ = delivery._open(session)
    state['attempts']['launch'] = 1
    state['stage'], state['pending'] = 'launch_pending', 'launch'
    head = delivery._append(target, rows, 'launch_pending', state)
    recovered = delivery.resume_session(session, trusted_session_head=head)
    assert recovered['stage'] == 'installed'
    assert recovered['recorded_observations']['launched'] is False
    assert recovered['next_action'] == 'supply_fresh_exact_launch_scope'
    assert not effect.exists()
    target, rows, state, _ = delivery._open(session)
    state['process'] = {'pid': os.getpid(), 'boot_id': delivery._boot_id(),
                        'start_ticks': delivery._process_info(os.getpid())[0]}
    state['stage'], state['pending'] = 'launched', 'launch'
    head = delivery._append(target, rows, 'launched', state)
    blocked = delivery.resume_session(session, trusted_session_head=head)
    assert blocked['stage'] == 'blocked_recovery'
    assert blocked['pending'] == 'launch'
    assert not effect.exists()


def test_waiting_preexec_helper_cannot_be_adopted_as_console(tmp_path, monkeypatch):
    plan, effect = _fake_installed(tmp_path, monkeypatch, pause=0)
    session = tmp_path / 'session'
    delivery.create_session(session, plan)
    read_fd, write_fd = os.pipe()
    child = subprocess.Popen([sys.executable, '-I', '-c', delivery._HELPER,
                              str(read_fd), plan['console_script'], plan['environment']],
                             pass_fds=(read_fd,), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(read_fd)
    try:
        target, rows, state, _ = delivery._open(session)
        state['attempts']['launch'] = 1
        state['process'] = {'pid': child.pid, 'boot_id': delivery._boot_id(),
                            'start_ticks': delivery._process_info(child.pid)[0]}
        state['stage'], state['pending'] = 'launched', 'launch'
        head = delivery._append(target, rows, 'launched', state)
        assert delivery._execed_console(state['process'], plan['console_script']) is False
        blocked = delivery.resume_session(session, trusted_session_head=head)
        assert blocked['stage'] == 'blocked_recovery'
        assert blocked['recorded_observations']['launched'] is False
        assert not effect.exists()
    finally:
        os.close(write_fd)
        child.wait(timeout=5)


def test_interrupted_stop_reconciles_exact_owned_process(tmp_path, monkeypatch):
    plan, _ = _fake_installed(tmp_path, monkeypatch, pause=10)
    session = tmp_path / 'session'
    created = delivery.create_session(session, plan)
    launch_scope = _scope(created, plan, launch=True)
    launched = delivery.launch_session(session, scope=launch_scope,
                                       approved_scope_sha256=launch_scope['scope_sha256'])
    target, rows, state, _ = delivery._open(session)
    state['stage'], state['pending'] = 'stop_pending', 'stop'
    state['attempts']['stop'] = 1
    head = delivery._append(target, rows, 'stop_pending', state)
    pending = delivery.resume_session(session, trusted_session_head=head)
    assert pending['pending'] == 'stop'
    assert pending['current_process_alive'] is True
    scope = _scope(pending, plan, stop=True)
    stopped = delivery.stop_session(session, scope=scope,
                                    approved_scope_sha256=scope['scope_sha256'],
                                    grace_seconds=0)
    assert stopped['stage'] == 'stopped'
    assert stopped['current_process_alive'] is False


def test_interrupted_disable_keeps_durable_disposition(tmp_path, monkeypatch):
    plan, _ = _fake_installed(tmp_path, monkeypatch, pause=10)
    session = tmp_path / 'session'
    created = delivery.create_session(session, plan)
    launch_scope = _scope(created, plan, launch=True)
    launched = delivery.launch_session(session, scope=launch_scope,
                                       approved_scope_sha256=launch_scope['scope_sha256'])
    target, rows, state, _ = delivery._open(session)
    state['stage'], state['pending'] = 'stop_pending', 'stop_disable'
    state['attempts']['stop'] = 1
    head = delivery._append(target, rows, 'stop_pending', state)
    pending = delivery.resume_session(session, trusted_session_head=head)
    assert pending['pending'] == 'stop_disable'
    wrong_scope = _scope(pending, plan, stop=True)
    with pytest.raises(delivery.DeliveryError, match='delivery_stop_pending_disposition_changed'):
        delivery.stop_session(session, scope=wrong_scope,
                              approved_scope_sha256=wrong_scope['scope_sha256'])
    delivery._signal_owned(state['process'], __import__('signal').SIGTERM)
    import time
    for _ in range(200):
        if not delivery._process_alive(state['process']):
            break
        time.sleep(0.01)
    disabled = delivery.resume_session(session, trusted_session_head=head)
    assert disabled['stage'] == 'disabled'
    assert disabled['pending'] is None
    assert delivery._open(session)[2]['disabled'] is True
    with pytest.raises(delivery.DeliveryError, match='exact_delivery_scope'):
        delivery.launch_session(session, scope=launch_scope,
                                approved_scope_sha256=launch_scope['scope_sha256'])


def test_drift_and_torn_journal_fail_closed(tmp_path, monkeypatch):
    plan, _ = _fake_installed(tmp_path, monkeypatch)
    session = tmp_path / 'session'
    created = delivery.create_session(session, plan)
    plan_file = session / 'plans' / (plan['plan_sha256'] + '.json')
    old = plan_file.read_bytes()
    plan_file.write_bytes(old.replace(b'jev-env-', b'changed-'))
    with pytest.raises(delivery.DeliveryError, match='delivery_session_plan_changed'):
        delivery.session_status(session, trusted_session_head=created['session_head_sha256'])
    plan_file.write_bytes(old)
    monkeypatch.setattr(delivery, '_receipt', lambda *_args: (_ for _ in ()).throw(delivery.DeliveryError('installed_drift')))
    assert delivery.session_status(session, trusted_session_head=created['session_head_sha256'])['current_installation'] == 'drift_or_unavailable'
    with (session / 'events.jsonl').open('ab') as stream:
        stream.write(b'{"torn":')
    with pytest.raises(delivery.DeliveryError, match='torn_or_modified'):
        delivery.session_status(session)


def test_readiness_and_integration_cannot_share_one_success_marker(tmp_path, monkeypatch):
    plan, marker = _fake_installed(tmp_path, monkeypatch)
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [
                       {'role': role, 'path': str(marker), 'before_sha256': None,
                        'expected_sha256': digest_bytes(b'actual-owned-effect')}
                       for role in ('ready', 'integration_reachable')]}
    with pytest.raises(delivery.DeliveryError,
                       match='readiness_and_integration_require_independent_checks'):
        delivery.plan_delivery(plan['install_plan'],
            trusted_install_receipt_sha256=plan['trusted_install_receipt_sha256'],
            observation=observation)


def test_required_observation_roles_and_reserved_mode_env(tmp_path, monkeypatch):
    plan, _ = _fake_installed(tmp_path, monkeypatch)
    for absent in ('ready', 'entrypoint_reached', 'integration_reachable'):
        observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                       'checks': [row for row in plan['observation']['checks']
                                  if row['role'] != absent]}
        with pytest.raises(delivery.DeliveryError,
                           match='readiness_and_integration_require_independent_checks'):
            delivery.plan_delivery(plan['install_plan'],
                trusted_install_receipt_sha256=plan['trusted_install_receipt_sha256'],
                observation=observation)
    for name in ('JEV_RUNTIME_MODE', 'JEV_TEST_SHADOW'):
        with pytest.raises(delivery.DeliveryError,
                           match='delivery_launch_environment_invalid_or_sensitive'):
            delivery.plan_delivery(plan['install_plan'],
                trusted_install_receipt_sha256=plan['trusted_install_receipt_sha256'],
                observation=plan['observation'], launch_environment={name: 'active'})


def test_partial_create_only_recovers_known_prelaunch_bytes(tmp_path, monkeypatch):
    plan, _ = _fake_installed(tmp_path, monkeypatch)
    session = tmp_path / 'session'
    session.mkdir(mode=0o700)
    pending = session / 'delivery-plan.json.pending'
    raw = delivery.canonical(plan) + b'\n'
    pending.write_bytes(raw[:23])
    pending.chmod(0o600)
    delivery.inspect_unlaunched_session(session, plan)
    recovered = delivery.recover_unlaunched_session(session, plan,
                                                    run_id='c1be85f4-884d-4b29-8336-b0d18d64c678')
    assert recovered['stage'] == 'installed'
    assert delivery.session_status(session)['run_id'] == recovered['run_id']
    other = tmp_path / 'other'
    other.mkdir(mode=0o700)
    (other / 'unknown').write_bytes(b'x')
    with pytest.raises(delivery.DeliveryError, match='delivery_partial_create_unknown_entries'):
        delivery.inspect_unlaunched_session(other, plan)


def test_immutable_upgrade_archive_recovers_only_own_write_prefix(tmp_path, monkeypatch):
    plan, _ = _fake_installed(tmp_path, monkeypatch)
    directory = tmp_path / 'archive-session'
    directory.mkdir(mode=0o700)
    plans = directory / 'plans'
    plans.mkdir(mode=0o700)
    final = plans / (plan['plan_sha256'] + '.json')
    pending = final.with_name(final.name + '.pending')
    raw = delivery.canonical(plan) + b'\n'
    pending.write_bytes(raw[:31])
    pending.chmod(0o600)
    delivery._write_plan_immutable(directory, plan)
    assert final.read_bytes() == raw
    assert not pending.exists()
    second = tmp_path / 'bad-archive'
    second.mkdir(mode=0o700)
    (second / 'plans').mkdir(mode=0o700)
    bad = second / 'plans' / (plan['plan_sha256'] + '.json.pending')
    bad.write_bytes(b'unknown')
    bad.chmod(0o600)
    with pytest.raises(delivery.DeliveryError, match='delivery_pending_plan_unknown_bytes'):
        delivery._write_plan_immutable(second, plan)
    linked = tmp_path / 'linked-archive'
    linked.mkdir(mode=0o700)
    (linked / 'plans').mkdir(mode=0o700)
    linked_final = linked / 'plans' / (plan['plan_sha256'] + '.json')
    linked_pending = linked_final.with_name(linked_final.name + '.pending')
    linked_pending.write_bytes(raw)
    linked_pending.chmod(0o600)
    os.link(linked_pending, linked_final)
    delivery._write_plan_immutable(linked, plan)
    assert linked_final.read_bytes() == raw
    assert linked_final.stat().st_nlink == 1
    assert not linked_pending.exists()


def test_session_lock_refuses_competing_controller(tmp_path, monkeypatch):
    plan, _ = _fake_installed(tmp_path, monkeypatch)
    session = tmp_path / 'session'
    delivery.create_session(session, plan)
    with delivery._locked(session):
        with pytest.raises(delivery.DeliveryError,
                           match='delivery_session_owned_by_another_controller'):
            delivery.session_status(session)


def test_upgrade_retains_old_generation_and_requires_new_launch_scope(tmp_path, monkeypatch):
    receipts = {}
    old, old_effect = _fake_installed(tmp_path / 'old', monkeypatch, pause=0.05,
                                      receipts=receipts)
    new, new_effect = _fake_installed(tmp_path / 'new', monkeypatch, pause=0.05,
                                      receipts=receipts)
    session = tmp_path / 'session'
    created = delivery.create_session(session, old)
    launch_scope = _scope(created, old, launch=True)
    launched = delivery.launch_session(session, scope=launch_scope,
                                       approved_scope_sha256=launch_scope['scope_sha256'])
    stop_scope = _scope(launched, old, stop=True)
    stopped = delivery.stop_session(session, scope=stop_scope,
                                    approved_scope_sha256=stop_scope['scope_sha256'],
                                    grace_seconds=2)
    assert stopped['stage'] == 'stopped'
    upgrade_scope = _scope(stopped, old)
    upgrade_scope['grants']['upgrade'] = True
    upgrade_scope['upgrade_plan_sha256'] = new['plan_sha256']
    upgrade_scope['scope_sha256'] = digest({k: v for k, v in upgrade_scope.items()
                                             if k != 'scope_sha256'})
    stale_receipt = delivery._receipt
    monkeypatch.setattr(delivery, '_receipt',
                        lambda install_plan, anchor: (_ for _ in ()).throw(
                            delivery.DeliveryError('stale_install_receipt'))
                        if install_plan == new['install_plan'] else stale_receipt(install_plan, anchor))
    with pytest.raises(delivery.DeliveryError, match='stale_install_receipt'):
        delivery.upgrade_session(session, new, scope=upgrade_scope,
                                 approved_scope_sha256=upgrade_scope['scope_sha256'])
    monkeypatch.setattr(delivery, '_receipt', stale_receipt)
    assert delivery.session_status(session,
        trusted_session_head=stopped['session_head_sha256'])['generation_id'] == old['generation_id']
    upgraded = delivery.upgrade_session(session, new, scope=upgrade_scope,
                                        approved_scope_sha256=upgrade_scope['scope_sha256'])
    assert upgraded['stage'] == 'upgrade_staged'
    assert upgraded['generation_id'] == new['generation_id']
    assert upgraded['generation_history'][-1]['plan_sha256'] == old['plan_sha256']
    assert upgraded['recorded_observations']['launched'] is False
    assert Path(old['environment']).is_dir()
    with pytest.raises(delivery.DeliveryError, match='exact_delivery_scope'):
        delivery.launch_session(session, scope=launch_scope,
                                approved_scope_sha256=launch_scope['scope_sha256'])
    new_scope = _scope(upgraded, new, launch=True)
    launched_new = delivery.launch_session(session, scope=new_scope,
        approved_scope_sha256=new_scope['scope_sha256'])
    stop_new_scope = _scope(launched_new, new, stop=True)
    stopped_new = delivery.stop_session(session, scope=stop_new_scope,
        approved_scope_sha256=stop_new_scope['scope_sha256'], grace_seconds=2)
    assert stopped_new['stage'] == 'stopped'
    rollback_scope = _scope(stopped_new, new)
    rollback_scope['grants']['rollback'] = True
    rollback_scope['rollback_digest'] = stopped_new['previous_generation_rollback_digest']
    rollback_scope['scope_sha256'] = digest({k: v for k, v in rollback_scope.items()
                                              if k != 'scope_sha256'})
    restored = delivery.rollback_session(session, scope=rollback_scope,
        approved_scope_sha256=rollback_scope['scope_sha256'])
    assert restored['stage'] == 'rolled_back'
    assert restored['generation_id'] == old['generation_id']
    assert Path(new['environment']).is_dir()


def test_partial_upgrade_and_rollback_pending_recover_without_relaunch(tmp_path, monkeypatch):
    receipts = {}
    old, old_effect = _fake_installed(tmp_path / 'old', monkeypatch, pause=0.05,
                                      receipts=receipts)
    new, new_effect = _fake_installed(tmp_path / 'new', monkeypatch, pause=0.05,
                                      receipts=receipts)
    session = tmp_path / 'session'
    created = delivery.create_session(session, old)
    launched_scope = _scope(created, old, launch=True)
    launched = delivery.launch_session(session, scope=launched_scope,
        approved_scope_sha256=launched_scope['scope_sha256'])
    stop_scope = _scope(launched, old, stop=True)
    stopped = delivery.stop_session(session, scope=stop_scope,
        approved_scope_sha256=stop_scope['scope_sha256'], grace_seconds=2)
    assert old_effect.read_bytes() == b'actual-owned-effect'
    upgrade_scope = _scope(stopped, old)
    upgrade_scope['grants']['upgrade'] = True
    upgrade_scope['upgrade_plan_sha256'] = new['plan_sha256']
    upgrade_scope['scope_sha256'] = digest({k: v for k, v in upgrade_scope.items()
                                             if k != 'scope_sha256'})
    original_append = delivery._append

    def interrupt_upgrade(path, rows, event, state):
        if event == 'upgrade_staged':
            raise RuntimeError('injected_after_plan_archive')
        return original_append(path, rows, event, state)

    monkeypatch.setattr(delivery, '_append', interrupt_upgrade)
    with pytest.raises(RuntimeError, match='injected_after_plan_archive'):
        delivery.upgrade_session(session, new, scope=upgrade_scope,
            approved_scope_sha256=upgrade_scope['scope_sha256'])
    unchanged = delivery.session_status(session,
        trusted_session_head=stopped['session_head_sha256'])
    assert unchanged['generation_id'] == old['generation_id']
    assert unchanged['recorded_observations']['launched'] is True
    assert not new_effect.exists()
    monkeypatch.setattr(delivery, '_append', original_append)
    upgraded = delivery.upgrade_session(session, new, scope=upgrade_scope,
        approved_scope_sha256=upgrade_scope['scope_sha256'])
    assert upgraded['stage'] == 'upgrade_staged'
    assert upgraded['recorded_observations']['launched'] is False
    assert not new_effect.exists()
    # A cutover never carries old launch authority into the new generation.
    with pytest.raises(delivery.DeliveryError, match='exact_delivery_scope'):
        delivery.launch_session(session, scope=launched_scope,
            approved_scope_sha256=launched_scope['scope_sha256'])
    launch_new_scope = _scope(upgraded, new, launch=True)
    launched_new = delivery.launch_session(session, scope=launch_new_scope,
        approved_scope_sha256=launch_new_scope['scope_sha256'])
    stop_new_scope = _scope(launched_new, new, stop=True)
    stopped_new = delivery.stop_session(session, scope=stop_new_scope,
        approved_scope_sha256=stop_new_scope['scope_sha256'], grace_seconds=2)
    assert new_effect.read_bytes() == b'actual-owned-effect'
    rollback_scope = _scope(stopped_new, new)
    rollback_scope['grants']['rollback'] = True
    rollback_scope['rollback_digest'] = stopped_new['previous_generation_rollback_digest']
    rollback_scope['scope_sha256'] = digest({k: v for k, v in rollback_scope.items()
                                              if k != 'scope_sha256'})

    def interrupt_rollback(path, rows, event, state):
        if event == 'rolled_back':
            raise RuntimeError('injected_after_rollback_pending')
        return original_append(path, rows, event, state)

    monkeypatch.setattr(delivery, '_append', interrupt_rollback)
    with pytest.raises(RuntimeError, match='injected_after_rollback_pending'):
        delivery.rollback_session(session, scope=rollback_scope,
            approved_scope_sha256=rollback_scope['scope_sha256'])
    pending = delivery.session_status(session)
    assert pending['stage'] == 'rollback_pending'
    assert pending['generation_id'] == new['generation_id']
    monkeypatch.setattr(delivery, '_append', original_append)
    recovered = delivery.resume_session(session,
        trusted_session_head=pending['session_head_sha256'])
    assert recovered['stage'] == 'rolled_back'
    assert recovered['generation_id'] == old['generation_id']
    assert recovered['recorded_observations']['launched'] is False
    assert Path(new['environment']).is_dir()
