"""An installed native run retains exact old and new generations."""
from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path
import time

import pytest

from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.windows_template_plan import (
    build_windows_template_package, plan_windows_template_package,
)
from jev_integration_evaluator.windows_template_install import (
    install_windows_template_package, plan_windows_template_install,
)
from jev_integration_evaluator.windows_template_session import (
    launch_windows_template_session, observe_windows_template_session,
    stop_windows_template_session,
)
from jev_integration_evaluator import windows_template_run as run
from jev_integration_evaluator.windows_template_install import windows_install_status
from test_windows_template_delivery import (
    _deny_sharing, _request, _supervised_off_console_run,
)


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')


def _installed(root: Path, version: str, *, ready=False):
    root.mkdir()
    request, _, _, _, spec = _request(root, version=version, ready=ready)
    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package,
        trusted_package_receipt_sha256=package['receipt_sha256'])
    receipt = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    from jev_integration_evaluator.integrations.recipes import host_lifecycle_marker
    marker = host_lifecycle_marker(
        spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    return install_plan, receipt, marker


def _invoke(selected: dict, plan: dict, record: Path, ready: Path | None = None,
            release: Path | None = None):
    session = selected['selected_session']
    identity = launch_windows_template_session(
        session, plan, approved_session_sha256=session['session_sha256'])
    deadline = time.monotonic() + 30
    if ready is not None:
        while not ready.is_file() and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.is_file()
        evidence = observe_windows_template_session(
            session, approved_identity_sha256=identity['identity_sha256'],
            phase='ready', path=ready,
            expected_sha256=hashlib.sha256(b'entry-ready\n').hexdigest())
        assert evidence['status'] == 'matched'
        assert evidence['job_assigned_count'] >= 2
        assert any(member['pid'] == identity['pid'] for member in evidence['job_members'])
        assert any(member['pid'] != identity['pid'] for member in evidence['job_members'])
        ready_report = record.with_name(record.stem + '-ready-observation.json')
        ready_report.write_text(json.dumps(evidence, sort_keys=True) + '\n', encoding='utf-8')
        assert release is not None and not release.exists()
        release.write_bytes(b'release\n')
    while not record.is_file() and time.monotonic() < deadline:
        time.sleep(.05)
    assert record.is_file()
    stopped = stop_windows_template_session(
        session, approved_identity_sha256=identity['identity_sha256'])
    assert stopped['status'] == 'stopped'
    expected_effect = json.dumps({'effects': ['first'], 'started': True,
                                  'closed': True, 'model_calls': 0}).encode('utf-8')
    evidence = observe_windows_template_session(
        session, approved_identity_sha256=identity['identity_sha256'],
        phase='effect', path=record,
        expected_sha256=hashlib.sha256(expected_effect).hexdigest())
    assert evidence['status'] == 'matched'
    assert evidence['job_assigned_count'] is None and evidence['job_members'] == []
    effect_report = record.with_name(record.stem + '-effect-observation.json')
    effect_report.write_text(json.dumps(evidence, sort_keys=True) + '\n', encoding='utf-8')
    with pytest.raises(InputError, match='observation_phase_unavailable'):
        observe_windows_template_session(
            session, approved_identity_sha256=identity['identity_sha256'],
            phase='ready', path=record,
            expected_sha256=hashlib.sha256(expected_effect).hexdigest())
    return identity


def test_owned_upgrade_rollback_and_same_run_recovery(tmp_path, monkeypatch):
    old_plan, old_receipt, marker = _installed(tmp_path / 'old', '1.0.0', ready=True)
    old_record = tmp_path / 'old-effect.json'
    ready = tmp_path / 'old-ready.txt'
    release = tmp_path / 'old-release.txt'
    first = run.create_windows_template_run(
        tmp_path / 'run', old_plan, old_receipt,
        trusted_install_receipt_sha256=old_receipt['receipt_sha256'],
        launch_environment={'JEV_FIXTURE_RECORD': str(old_record),
                            'JEV_FIXTURE_READY': str(ready),
                            'JEV_FIXTURE_RELEASE': str(release),
                            'JEV_FIXTURE_MARKER': marker})
    assert first['status'] == 'selected' and first['selected_version'] == '1.0.0'
    assert first['selection_trust'] == 'externally_anchored'
    run_id = first['run_id']
    _invoke(first, old_plan, old_record, ready, release)

    new_plan, new_receipt, new_marker = _installed(tmp_path / 'new', '1.0.1', ready=True)
    assert new_marker == marker
    new_record = tmp_path / 'new-effect.json'
    new_ready = tmp_path / 'new-ready.txt'
    new_release = tmp_path / 'new-release.txt'
    original_complete = run._complete_stage
    def interrupt(*args, **kwargs):
        raise RuntimeError('simulated interruption after durable intent')
    monkeypatch.setattr(run, '_complete_stage', interrupt)
    with pytest.raises(RuntimeError, match='simulated interruption'):
        run.upgrade_windows_template_run(
            tmp_path / 'run', old_plan, new_plan, new_receipt,
            approved_selection_sha256=first['selection_sha256'],
            trusted_new_receipt_sha256=new_receipt['receipt_sha256'],
            launch_environment={'JEV_FIXTURE_RECORD': str(new_record),
                                'JEV_FIXTURE_READY': str(new_ready),
                                'JEV_FIXTURE_RELEASE': str(new_release),
                                'JEV_FIXTURE_MARKER': marker})
    pending = run.windows_template_run_status(
        tmp_path / 'run', trusted_selection_sha256=first['selection_sha256'])
    assert pending['status'] == 'pending_upgrade'
    assert pending['selected_session_sha256'] == first['selected_session_sha256']
    monkeypatch.setattr(run, '_complete_stage', original_complete)
    second = run.resume_windows_template_run(
        tmp_path / 'run', new_plan, new_receipt,
        approved_intent_sha256=pending['pending_intent_sha256'],
        trusted_install_receipt_sha256=new_receipt['receipt_sha256'])
    assert second['run_id'] == run_id and second['selected_version'] == '1.0.1'
    assert second['sequence'] == 1
    assert Path(first['selected_environment']).is_dir()
    _invoke(second, new_plan, new_record, new_ready, new_release)

    rollback_record = tmp_path / 'rollback-effect.json'
    rollback_ready = tmp_path / 'rollback-ready.txt'
    rollback_release = tmp_path / 'rollback-release.txt'
    original_write = run._write
    def interrupt_after_child(owned, name, kind, body):
        if name == 'generation-002.json':
            raise RuntimeError('simulated interruption after child session')
        return original_write(owned, name, kind, body)
    monkeypatch.setattr(run, '_write', interrupt_after_child)
    with pytest.raises(RuntimeError, match='after child session'):
        run.rollback_windows_template_run(
            tmp_path / 'run', old_plan, old_receipt,
            approved_selection_sha256=second['selection_sha256'],
            trusted_retained_receipt_sha256=old_receipt['receipt_sha256'],
            launch_environment={'JEV_FIXTURE_RECORD': str(rollback_record),
                                'JEV_FIXTURE_READY': str(rollback_ready),
                                'JEV_FIXTURE_RELEASE': str(rollback_release),
                                'JEV_FIXTURE_MARKER': marker})
    pending = run.windows_template_run_status(tmp_path / 'run')
    assert pending['status'] == 'pending_rollback'
    monkeypatch.setattr(run, '_write', original_write)
    third = run.resume_windows_template_run(
        tmp_path / 'run', old_plan, old_receipt,
        approved_intent_sha256=pending['pending_intent_sha256'],
        trusted_install_receipt_sha256=old_receipt['receipt_sha256'])
    assert third['run_id'] == run_id and third['sequence'] == 2
    assert third['selected_version'] == '1.0.0'
    assert third['selected_environment'] == first['selected_environment']
    assert third['selected_session_sha256'] != first['selected_session_sha256']
    assert Path(second['selected_environment']).is_dir()
    _invoke(third, old_plan, rollback_record, rollback_ready, rollback_release)
    assert run.windows_template_run_status(tmp_path / 'run')['selection_trust'] == 'recorded_untrusted'
    with pytest.raises(InputError, match='exact_upgrade_scope'):
        run.upgrade_windows_template_run(
            tmp_path / 'run', old_plan, new_plan, new_receipt,
            approved_selection_sha256=second['selection_sha256'],
            trusted_new_receipt_sha256=new_receipt['receipt_sha256'])


def test_native_locked_generation_file_blocks_upgrade_and_rollback_selection(tmp_path):
    """A handle that shares nothing inside the selected or retained install."""
    old_plan, old_receipt, marker = _installed(tmp_path / 'old', '1.0.0')
    root = tmp_path / 'run'

    def environment(label: str) -> dict:
        return {'JEV_FIXTURE_RECORD': str(tmp_path / (label + '-effect.json')),
                'JEV_FIXTURE_MARKER': marker}

    def recorded(plan: dict, receipt: dict) -> None:
        assert windows_install_status(
            plan, trusted_receipt_sha256=receipt['receipt_sha256']) == {
                'status': 'installed_recorded', 'receipt_trust': 'externally_anchored',
                'receipt_sha256': receipt['receipt_sha256']}

    def still_selected(selection: dict, version: str, sequence: int) -> None:
        status = run.windows_template_run_status(
            root, trusted_selection_sha256=selection['selection_sha256'])
        assert status == {**selection, 'selected_session_status': 'stopped'}
        assert (status['status'], status['sequence'], status['selected_version'],
                status['pending_intent_sha256'], status['selection_trust']) == (
                    'selected', sequence, version, None, 'externally_anchored')

    first = run.create_windows_template_run(
        root, old_plan, old_receipt,
        trusted_install_receipt_sha256=old_receipt['receipt_sha256'],
        launch_environment=environment('old'))
    assert first['status'] == 'selected' and first['selected_version'] == '1.0.0'
    _invoke(first, old_plan, tmp_path / 'old-effect.json')
    new_plan, new_receipt, new_marker = _installed(tmp_path / 'new', '1.0.1')
    assert new_marker == marker
    old_root = Path(old_receipt['environment'])
    new_root = Path(new_receipt['environment'])
    assert old_root == Path(first['selected_environment']) and old_root != new_root
    unrelated = tmp_path / 'unrelated.txt'
    unrelated.write_bytes(b'preserve unrelated bytes\n')

    def upgrade() -> dict:
        return run.upgrade_windows_template_run(
            root, old_plan, new_plan, new_receipt,
            approved_selection_sha256=first['selection_sha256'],
            trusted_new_receipt_sha256=new_receipt['receipt_sha256'],
            launch_environment=environment('new'))

    # Upgrade: a locked file in the currently selected generation, then in the
    # generation the upgrade would select. Neither records a stage.
    entries = sorted(entry.name for entry in root.iterdir())
    assert 'selection-000.json' in entries and not any('001' in name for name in entries)
    for locked in (old_root / 'venv' / 'Lib' / 'site-packages' / 'atlas_pkg' / 'console.py',
                   old_root / 'config.json',
                   new_root / 'venv' / 'Lib' / 'site-packages' / 'atlas_pkg' / 'console.py'):
        original = locked.read_bytes()
        with _deny_sharing(locked):
            with pytest.raises(PermissionError):
                locked.read_bytes()
            with pytest.raises(InputError, match='^windows_install_status_unavailable$'):
                upgrade()
            assert sorted(entry.name for entry in root.iterdir()) == entries
            still_selected(first, '1.0.0', 0)
        assert locked.read_bytes() == original
    assert sorted(entry.name for entry in root.iterdir()) == entries
    still_selected(first, '1.0.0', 0)
    recorded(old_plan, old_receipt)
    recorded(new_plan, new_receipt)
    # The generation that stayed selected still runs under the off-mode supervisor.
    _supervised_off_console_run(tmp_path / 'old-after-lock', old_plan, old_receipt, marker)
    assert unrelated.read_bytes() == b'preserve unrelated bytes\n'

    second = upgrade()
    assert (second['status'], second['sequence'], second['selected_version']) == (
        'selected', 1, '1.0.1')
    assert second['run_id'] == first['run_id']
    assert second['selected_environment'] == str(new_root) and old_root.is_dir()
    _invoke(second, new_plan, tmp_path / 'new-effect.json')

    def rollback() -> dict:
        return run.rollback_windows_template_run(
            root, old_plan, old_receipt,
            approved_selection_sha256=second['selection_sha256'],
            trusted_retained_receipt_sha256=old_receipt['receipt_sha256'],
            launch_environment=environment('rollback'))

    # Rollback: a locked file in the retained generation it would select.
    entries = sorted(entry.name for entry in root.iterdir())
    assert 'selection-001.json' in entries and not any('002' in name for name in entries)
    for locked, reason in (
            (old_root / 'venv' / 'Scripts' / 'python.exe',
             'windows_install_status_unavailable'),
            (old_root / 'install-receipt.json', 'windows_owned_record_unavailable')):
        original = locked.read_bytes()
        with _deny_sharing(locked):
            with pytest.raises(PermissionError):
                locked.read_bytes()
            with pytest.raises(InputError, match='^' + reason + '$'):
                rollback()
            assert sorted(entry.name for entry in root.iterdir()) == entries
            still_selected(second, '1.0.1', 1)
        assert locked.read_bytes() == original
    assert sorted(entry.name for entry in root.iterdir()) == entries
    still_selected(second, '1.0.1', 1)
    recorded(old_plan, old_receipt)
    recorded(new_plan, new_receipt)
    _supervised_off_console_run(tmp_path / 'new-after-lock', new_plan, new_receipt, marker)
    assert unrelated.read_bytes() == b'preserve unrelated bytes\n'

    third = rollback()
    assert (third['status'], third['sequence'], third['selected_version']) == (
        'selected', 2, '1.0.0')
    assert third['run_id'] == first['run_id']
    assert third['selected_environment'] == first['selected_environment']
    assert third['selected_session_sha256'] != first['selected_session_sha256']
    assert new_root.is_dir()
    _invoke(third, old_plan, tmp_path / 'rollback-effect.json')
    assert unrelated.read_bytes() == b'preserve unrelated bytes\n'
