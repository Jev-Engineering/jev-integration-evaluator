"""Native offline install interruption preserves owned evidence and blocks replay."""
from __future__ import annotations

import os
import pytest

from jev_integration_evaluator.io import InputError, file_hash
from jev_integration_evaluator import windows_template_install as install
from jev_integration_evaluator.windows_template_plan import (
    build_windows_template_package, plan_windows_template_package,
)
from test_windows_template_delivery import _request


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')


@pytest.mark.parametrize('phase', ['durable_intent', 'host_installed', 'before_receipt'])
def test_native_interrupted_install_retains_generation_and_refuses_replay(
        tmp_path, monkeypatch, phase):
    request, _, target, _, _ = _request(tmp_path)
    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    plan = install.plan_windows_template_install(
        package_plan, package,
        trusted_package_receipt_sha256=package['receipt_sha256'])
    root = install._generation(plan)
    unrelated = tmp_path / 'unrelated.txt'
    unrelated.write_bytes(b'preserve independent work\n')
    unrelated_hash = file_hash(unrelated)
    source_hashes = {name: file_hash(target / name)
                     for name in request['reviewed_source_files']}
    real_write = install.write_private_json_exclusive
    real_run = install._run
    commands = []
    interruptions = []

    def interrupted_write(owned, name, value):
        if phase == 'before_receipt' and name == 'install-receipt.json':
            interruptions.append(phase)
            raise OSError('fixture interruption before receipt commit')
        result = real_write(owned, name, value)
        if phase == 'durable_intent' and name == 'install-intent.json':
            interruptions.append(phase)
            raise OSError('fixture interruption after durable intent')
        return result

    def interrupted_run(command, **kwargs):
        result = real_run(command, **kwargs)
        commands.append(tuple(command))
        if phase == 'host_installed' and str(root / 'host.lock') in command:
            interruptions.append(phase)
            raise OSError('fixture interruption after host installation')
        return result

    monkeypatch.setattr(install, 'write_private_json_exclusive', interrupted_write)
    monkeypatch.setattr(install, '_run', interrupted_run)
    with pytest.raises(OSError, match='fixture interruption'):
        install.install_windows_template_package(
            plan, approved_plan_sha256=plan['plan_sha256'])
    assert interruptions == [phase]
    assert root.is_dir()
    assert not (root / 'install-receipt.json').exists()
    preserved = {name: file_hash(root / name)
                 for name in ('owner.json', 'install-intent.json')}
    assert (root / 'venv').exists() is (phase != 'durable_intent')
    assert (root / 'config.json').exists() is (phase == 'before_receipt')
    if phase != 'durable_intent':
        console = root / 'venv' / 'Scripts' / (package_plan['inputs']['console_script'] + '.exe')
        # Read installed bytes only; a partial install grants no launch authority.
        host = root / 'venv' / 'Lib' / 'site-packages' / 'atlas_pkg' / 'console.py'
        assert console.is_file() and host.is_file()
        assert file_hash(host) == file_hash(target / 'atlas_pkg' / 'console.py')
        assert any(str(root / 'host.lock') in command for command in commands)
    command_count = len(commands)
    assert install.windows_install_status(plan) == {
        'status': 'blocked_recovery', 'receipt_trust': 'absent'}
    with pytest.raises(InputError, match='windows_session_install_unverified'):
        install.owned_windows_install_receipt(plan, 'a' * 64)
    with pytest.raises(InputError, match='existing_generation_requires_status_review'):
        install.install_windows_template_package(
            plan, approved_plan_sha256=plan['plan_sha256'])
    assert len(commands) == command_count
    assert {name: file_hash(root / name) for name in preserved} == preserved
    assert {name: file_hash(target / name) for name in source_hashes} == source_hashes
    assert file_hash(unrelated) == unrelated_hash
    assert not (root / 'install-receipt.json').exists()
