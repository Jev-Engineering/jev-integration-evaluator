"""Durable Node supervisor state machine; native installed tests cover Node bytes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import platform
import sys
import time

import pytest

from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator import template_node_session as session


pytestmark = pytest.mark.skipif(
    sys.platform != 'linux' or platform.machine().lower() != 'x86_64',
    reason='Native Linux x86-64 process ownership required')


def _descriptor(root: Path, tag: str) -> dict:
    root.mkdir(mode=0o700)
    script = root / 'host.py'
    script.write_text('''import os,time
from pathlib import Path
assert os.environ['JEV_RUNTIME_MODE'] == 'off'
for name, value in [('NODE_EFFECT_PATH',b'effect\\n'),
                    ('NODE_READY_PATH',b'ready\\n'),
                    ('NODE_INTEGRATION_PATH',b'integration\\n')]:
    Path(os.environ[name]).write_bytes(value)
time.sleep(2)
''', encoding='utf-8')
    paths = {key: root / name for key, name in (
        ('NODE_EFFECT_PATH', 'effect.bin'), ('NODE_READY_PATH', 'ready.bin'),
        ('NODE_INTEGRATION_PATH', 'integration.bin'))}
    expected = {'NODE_EFFECT_PATH': b'effect\n', 'NODE_READY_PATH': b'ready\n',
                'NODE_INTEGRATION_PATH': b'integration\n'}
    roles = {'NODE_EFFECT_PATH': 'entrypoint_reached', 'NODE_READY_PATH': 'ready',
             'NODE_INTEGRATION_PATH': 'integration_reachable'}
    value = {'schema_version': '1.0', 'kind': 'node-delivery-descriptor-v1',
             'install_plan': {}, 'trusted_install_receipt_sha256': 'a' * 64,
             'generation_id': digest(tag), 'generation_path': str(root),
             'command': [sys.executable, str(script)], 'working_directory': str(root),
             'executable_sha256': file_hash(Path(sys.executable)), 'entrypoint_sha256': file_hash(script),
             'artifact_sha256': digest(tag + 'artifact'), 'source_sha256': digest(tag + 'source'),
             'configuration_sha256': digest(tag + 'config'),
             'secret_references_sha256': digest({}),
             'observation': {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                             'checks': [{'role': roles[key], 'path': str(path),
                                         'before_sha256': None,
                                         'expected_sha256': digest_bytes(expected[key])}
                                        for key, path in paths.items()]},
             'launch_environment': {key: str(path) for key, path in paths.items()},
             'mode': 'off', 'runtime_activation_authorized': False,
             'launch_status': 'not_started'}
    value['descriptor_sha256'] = digest(value)
    return value


def digest_bytes(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()


def _scope(result: dict, action: str, *, extra: str | None = None) -> dict:
    value = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
             'reference': 'node-fixture-external-operator', 'run_id': result['run_id'],
             'plan_sha256': result['descriptor_sha256'],
             'trusted_session_head': result['session_head_sha256'],
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
             'revoked': False,
             'grants': {name: name == action for name in
                        ('launch', 'stop', 'disable', 'upgrade', 'rollback')}}
    if action == 'upgrade':
        value['upgrade_plan_sha256'] = extra
    if action == 'rollback':
        value['rollback_digest'] = extra
    value['scope_sha256'] = digest(value)
    return value


def test_owned_off_mode_process_observe_disable_and_scope_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(session, 'validate_node_delivery', lambda _: {'status': 'verified_unlaunched'})
    monkeypatch.setattr(session, '_check_install', lambda _: None)
    descriptor = _descriptor(tmp_path / 'host', 'one')
    created = session.create_node_session(tmp_path / 'session', descriptor)
    launch = _scope(created, 'launch')
    refused = {**launch, 'revoked': True}
    refused['scope_sha256'] = digest({k: v for k, v in refused.items() if k != 'scope_sha256'})
    with pytest.raises(session.NodeSessionError, match='scope'):
        session.launch_node_session(tmp_path / 'session', scope=refused,
                                    approved_scope_sha256=refused['scope_sha256'])
    expired = {**launch, 'expires_at': (datetime.now(timezone.utc)
                                  - timedelta(seconds=1)).isoformat()}
    expired['scope_sha256'] = digest({k: v for k, v in expired.items()
                                      if k != 'scope_sha256'})
    with pytest.raises(session.NodeSessionError, match='expired'):
        session.launch_node_session(tmp_path / 'session', scope=expired,
                                    approved_scope_sha256=expired['scope_sha256'])
    started = session.launch_node_session(tmp_path / 'session', scope=launch,
                                          approved_scope_sha256=launch['scope_sha256'])
    observed = started
    for _ in range(150):
        observed = session.observe_node_session(tmp_path / 'session',
            trusted_session_head=observed['session_head_sha256'])
        if observed['observations']['integration_reachable']:
            break
        time.sleep(.01)
    assert observed['process_alive']
    assert all(value for name, value in observed['observations'].items()
               if name != 'outcome_verified')
    assert (tmp_path / 'host/effect.bin').read_bytes() == b'effect\n'
    with pytest.raises(session.NodeSessionError, match='scope'):
        session.stop_node_session(tmp_path / 'session', scope=_scope(started, 'disable'),
                                  approved_scope_sha256=_scope(started, 'disable')['scope_sha256'],
                                  disable=True)
    disable = _scope(observed, 'disable')
    stopped = session.stop_node_session(tmp_path / 'session', scope=disable,
        approved_scope_sha256=disable['scope_sha256'], disable=True, grace_seconds=0)
    assert stopped['stage'] == 'disabled' and not stopped['process_alive']
    stop_after_disable = _scope(stopped, 'stop')
    with pytest.raises(session.NodeSessionError, match='disposition_changed'):
        session.stop_node_session(tmp_path / 'session', scope=stop_after_disable,
            approved_scope_sha256=stop_after_disable['scope_sha256'])
    blocked = _scope(stopped, 'launch')
    with pytest.raises(session.NodeSessionError, match='launch_blocked'):
        session.launch_node_session(tmp_path / 'session', scope=blocked,
                                    approved_scope_sha256=blocked['scope_sha256'])


def test_interrupted_start_preserves_run_and_never_replays_unknown_effect(tmp_path, monkeypatch):
    monkeypatch.setattr(session, 'validate_node_delivery', lambda _: {'status': 'verified_unlaunched'})
    monkeypatch.setattr(session, '_check_install', lambda _: None)
    descriptor = _descriptor(tmp_path / 'host', 'one')
    created = session.create_node_session(tmp_path / 'session', descriptor)
    original = session._append
    def interrupt(directory, rows, event, state):
        if event == 'launched':
            raise RuntimeError('before_release')
        return original(directory, rows, event, state)
    monkeypatch.setattr(session, '_append', interrupt)
    scope = _scope(created, 'launch')
    with pytest.raises(RuntimeError, match='before_release'):
        session.launch_node_session(tmp_path / 'session', scope=scope,
                                    approved_scope_sha256=scope['scope_sha256'])
    monkeypatch.setattr(session, '_append', original)
    pending = session.node_session_status(tmp_path / 'session')
    assert pending['stage'] == 'launch_pending' and pending['run_id'] == created['run_id']
    recovered = session.resume_node_session(tmp_path / 'session',
        trusted_session_head=pending['session_head_sha256'])
    assert recovered['stage'] == 'created' and recovered['attempts']['launch'] == 1
    assert not (tmp_path / 'host/effect.bin').exists()
    new_scope = _scope(recovered, 'launch')
    original_write = os.write
    def interrupt_release(fd, raw):
        if raw == b'G':
            raise RuntimeError('release_unknown')
        return original_write(fd, raw)
    monkeypatch.setattr(session.os, 'write', interrupt_release)
    with pytest.raises(RuntimeError, match='release_unknown'):
        session.launch_node_session(tmp_path / 'session', scope=new_scope,
                                    approved_scope_sha256=new_scope['scope_sha256'])
    monkeypatch.setattr(session.os, 'write', original_write)
    pending = session.node_session_status(tmp_path / 'session')
    recovered = session.resume_node_session(tmp_path / 'session',
        trusted_session_head=pending['session_head_sha256'])
    assert recovered['stage'] == 'blocked_recovery' and recovered['run_id'] == created['run_id']
    retry = _scope(recovered, 'launch')
    with pytest.raises(session.NodeSessionError, match='launch_blocked'):
        session.launch_node_session(tmp_path / 'session', scope=retry,
                                    approved_scope_sha256=retry['scope_sha256'])


def test_stopped_generation_upgrade_and_pending_rollback_reconcile(tmp_path, monkeypatch):
    monkeypatch.setattr(session, 'validate_node_delivery', lambda _: {'status': 'verified_unlaunched'})
    monkeypatch.setattr(session, '_check_install', lambda _: None)
    old = _descriptor(tmp_path / 'old', 'one')
    new = _descriptor(tmp_path / 'new', 'two')
    created = session.create_node_session(tmp_path / 'session', old)
    launched_scope = _scope(created, 'launch')
    launched = session.launch_node_session(tmp_path / 'session', scope=launched_scope,
        approved_scope_sha256=launched_scope['scope_sha256'])
    stop_scope = _scope(launched, 'stop')
    stopped = session.stop_node_session(tmp_path / 'session', scope=stop_scope,
        approved_scope_sha256=stop_scope['scope_sha256'], grace_seconds=0)
    upgrade_scope = _scope(stopped, 'upgrade', extra=new['descriptor_sha256'])
    original = session._append
    def interrupt_upgrade(directory, rows, event, state):
        if event == 'upgrade_staged':
            raise RuntimeError('upgrade_interrupted')
        return original(directory, rows, event, state)
    monkeypatch.setattr(session, '_append', interrupt_upgrade)
    with pytest.raises(RuntimeError, match='upgrade_interrupted'):
        session.upgrade_node_session(tmp_path / 'session', new, scope=upgrade_scope,
            approved_scope_sha256=upgrade_scope['scope_sha256'])
    monkeypatch.setattr(session, '_append', original)
    pending = session.node_session_status(tmp_path / 'session')
    assert pending['pending'] == 'upgrade' and pending['run_id'] == created['run_id']
    upgraded = session.resume_node_session(tmp_path / 'session',
        trusted_session_head=pending['session_head_sha256'])
    assert upgraded['stage'] == 'upgrade_staged' and upgraded['generation_id'] == new['generation_id']
    launch_new = _scope(upgraded, 'launch')
    new_running = session.launch_node_session(tmp_path / 'session', scope=launch_new,
        approved_scope_sha256=launch_new['scope_sha256'])
    stop_new = _scope(new_running, 'stop')
    new_stopped = session.stop_node_session(tmp_path / 'session', scope=stop_new,
        approved_scope_sha256=stop_new['scope_sha256'], grace_seconds=0)
    rollback = _scope(new_stopped, 'rollback',
        extra=new_stopped['previous_generation_rollback_digest'])
    def interrupt_rollback(directory, rows, event, state):
        if event == 'rolled_back':
            raise RuntimeError('rollback_interrupted')
        return original(directory, rows, event, state)
    monkeypatch.setattr(session, '_append', interrupt_rollback)
    with pytest.raises(RuntimeError, match='rollback_interrupted'):
        session.rollback_node_session(tmp_path / 'session', scope=rollback,
            approved_scope_sha256=rollback['scope_sha256'])
    monkeypatch.setattr(session, '_append', original)
    pending = session.node_session_status(tmp_path / 'session')
    assert pending['pending'] == 'rollback'
    restored = session.resume_node_session(tmp_path / 'session',
        trusted_session_head=pending['session_head_sha256'])
    assert restored['run_id'] == created['run_id']
    assert restored['generation_id'] == old['generation_id']
    assert restored['stage'] == 'rolled_back' and not restored['observations']['launched']
