"""Native source-mutation metadata and concurrent-work preservation."""
from __future__ import annotations

import os
import json
import struct
import subprocess
import sys

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.implementation import apply_patch_plan, make_patch_plan
from jev_integration_evaluator.windows_template_owned import acl_sha256
from jev_integration_evaluator.io import InputError


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native local NTFS source mutation')


def test_native_patch_update_preserves_protected_owner_dacl(tmp_path):
    source = tmp_path / 'owned.py'
    _, io_path = cap._windows_absolute_path(source)
    descriptor = cap._windows_create_private_file(io_path)
    try:
        os.write(descriptor, b'value = "baseline"\n')
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _, wintypes, kernel = cap._windows_api()
    kernel.SetFileAttributesW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD)
    kernel.SetFileAttributesW.restype = wintypes.BOOL
    assert kernel.SetFileAttributesW(io_path, source.stat().st_file_attributes | 0x2)
    before_attributes = source.stat().st_file_attributes
    stream = tmp_path / 'owned.py:metadata'
    stream.write_bytes(b'fixture-stream')
    before_acl = acl_sha256(source)
    plan = make_patch_plan(tmp_path, [{'file': 'owned.py', 'new_content': 'value = "reviewed"\n'}], ['native-source'])
    result = apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    assert result['status'] == 'applied'
    assert source.read_bytes() == b'value = "reviewed"\n'
    assert acl_sha256(source) == before_acl
    assert source.stat().st_file_attributes == before_attributes
    assert stream.read_bytes() == b'fixture-stream'


def test_native_inherited_dacl_apply_and_owned_rollback(tmp_path):
    from jev_integration_evaluator import windows_source_mutation as mutation

    source = tmp_path / 'ordinary.py'
    source.write_bytes(b'old\n')
    _, io_path = cap._windows_absolute_path(source)
    fd, _ = mutation._lease(io_path)
    try:
        before_security = mutation._security(fd)
    finally:
        os.close(fd)
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'new\n'}], ['native-source'])
    def fail_after_write(phase, _change):
        if phase == 'write_completed':
            raise RuntimeError('injected_following_failure')
    with pytest.raises(RuntimeError, match='injected_following_failure'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'], progress=fail_after_write)
    assert source.read_bytes() == b'old\n'
    fd, _ = mutation._lease(io_path)
    try:
        assert mutation._security(fd) == before_security
    finally:
        os.close(fd)
    assert apply_patch_plan(tmp_path, plan, plan['plan_digest'])['status'] == 'applied'
    assert source.read_bytes() == b'new\n'
    fd, _ = mutation._lease(io_path)
    try:
        assert mutation._security(fd) == before_security
    finally:
        os.close(fd)


def test_native_dacl_hash_accepts_layout_only_and_rejects_policy_or_ace(tmp_path):
    from jev_integration_evaluator import windows_source_mutation as mutation

    source = tmp_path / 'ordinary.py'
    source.write_bytes(b'old\n')
    _, io_path = cap._windows_absolute_path(source)
    fd, _ = mutation._lease(io_path)
    try:
        descriptor = mutation._security_snapshot(fd)[1]
    finally:
        os.close(fd)
    baseline = mutation._dacl_hash(descriptor)
    layout = bytearray(descriptor)
    # Group offset is unrelated to the separately authenticated owner and DACL.
    struct.pack_into('<I', layout, 8, 0)
    assert mutation._dacl_hash(layout) == baseline
    policy = bytearray(descriptor)
    struct.pack_into('<H', policy, 2, struct.unpack_from('<H', policy, 2)[0] ^ 0x100)
    assert mutation._dacl_hash(policy) != baseline
    ace = bytearray(descriptor)
    offset = struct.unpack_from('<I', ace, 16)[0]
    ace[offset + 8] ^= 1
    assert mutation._dacl_hash(ace) != baseline
    invalid = bytearray(descriptor)
    invalid[0] = 2
    with pytest.raises(InputError, match='windows_source_security_unavailable'):
        mutation._dacl_hash(invalid)


def test_native_post_replace_failure_restores_owned_original(tmp_path, monkeypatch):
    from jev_integration_evaluator import windows_source_mutation as mutation

    source = tmp_path / 'owned.py'
    _, io_path = cap._windows_absolute_path(source)
    descriptor = cap._windows_create_private_file(io_path)
    try:
        os.write(descriptor, b'value = "baseline"\n')
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    before_acl = acl_sha256(source)
    before_identity = cap._windows_file_identity(source.stat())
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'value = "reviewed"\n'}], ['native-source'])
    real_check = mutation._check_parent
    calls = 0
    def fail_after_replace(*args):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise InputError('injected_post_replace_failure')
        return real_check(*args)
    monkeypatch.setattr(mutation, '_check_parent', fail_after_replace)
    with pytest.raises(InputError, match='injected_post_replace_failure'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    assert source.read_bytes() == b'value = "baseline"\n'
    assert cap._windows_file_identity(source.stat()) == before_identity
    assert acl_sha256(source) == before_acl
    assert not list(tmp_path.glob('.jev-source-*'))


def test_native_atomic_save_peer_at_vacated_name_is_preserved(tmp_path, monkeypatch):
    from jev_integration_evaluator import windows_source_mutation as mutation

    source = tmp_path / 'owned.py'
    source.write_bytes(b'old\n')
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'reviewed\n'}], ['native-source'])
    original_rename = mutation._rename_owned
    calls = 0
    def peer_after_owned_backup(fd, destination):
        nonlocal calls
        original_rename(fd, destination)
        calls += 1
        if calls == 1:
            # This is a real name-race at the former source path, not a
            # changed in-place writer blocked by the retained source handle.
            source.write_bytes(b'peer atomic save\n')
    monkeypatch.setattr(mutation, '_rename_owned', peer_after_owned_backup)
    with pytest.raises(InputError, match='windows_source_recovery_required'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    assert source.read_bytes() == b'peer atomic save\n'
    backups = list(tmp_path.glob('.jev-source-*.backup'))
    assert len(backups) == 1 and backups[0].read_bytes() == b'old\n'


@pytest.mark.parametrize('peer', [False, True])
def test_native_abrupt_death_reconciles_owned_backup_without_replay(tmp_path, peer):
    from jev_integration_evaluator import windows_source_mutation as mutation

    source = tmp_path / 'owned.py'
    source.write_bytes(b'old\n')
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'reviewed\n'}], ['native-source'])
    planfile = tmp_path / 'reviewed-plan.json'
    planfile.write_text(json.dumps(plan), encoding='utf-8')
    child = '''import json,os,sys
from jev_integration_evaluator import windows_source_mutation as m
from jev_integration_evaluator.implementation import apply_patch_plan
real=m._rename_owned
def crash(fd,destination):
    real(fd,destination)
    os._exit(71)
m._rename_owned=crash
plan=json.loads(open(sys.argv[2],encoding='utf-8').read())
apply_patch_plan(sys.argv[1],plan,plan['plan_digest'])
'''
    result = subprocess.run([sys.executable, '-c', child, str(tmp_path), str(planfile)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 71
    assert not source.exists()
    intent = mutation._intent_path(source, plan['changes'][0]['old_sha256'],
                                   plan['changes'][0]['new_sha256'], tmp_path)
    assert intent.is_file()
    if peer:
        source.write_bytes(b'peer atomic save\n')
        with pytest.raises(InputError, match='windows_source_peer_target_preserved'):
            apply_patch_plan(tmp_path, plan, plan['plan_digest'])
        assert source.read_bytes() == b'peer atomic save\n'
        assert intent.is_file()
        source.unlink()  # only this disposable test-owned peer
    with pytest.raises(InputError, match='reconciled; review a new plan'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    assert source.read_bytes() == b'old\n'
    assert not intent.exists()
    assert not list(tmp_path.glob('.jev-source-*'))


def test_native_committed_intent_death_cleans_backup_without_replay(tmp_path):
    from jev_integration_evaluator import windows_source_mutation as mutation

    source = tmp_path / 'owned.py'
    source.write_bytes(b'old\n')
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'reviewed\n'}], ['native-source'])
    planfile = tmp_path / 'reviewed-plan.json'
    planfile.write_text(json.dumps(plan), encoding='utf-8')
    child = '''import json,os,sys
from jev_integration_evaluator import windows_source_mutation as m
from jev_integration_evaluator.implementation import apply_patch_plan
real=m._commit_intent
def crash(*args):
    real(*args)
    os._exit(72)
m._commit_intent=crash
plan=json.loads(open(sys.argv[2],encoding='utf-8').read())
apply_patch_plan(sys.argv[1],plan,plan['plan_digest'])
'''
    result = subprocess.run([sys.executable, '-c', child, str(tmp_path), str(planfile)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 72
    assert source.read_bytes() == b'reviewed\n'
    intent = mutation._intent_path(source, plan['changes'][0]['old_sha256'],
                                   plan['changes'][0]['new_sha256'], tmp_path)
    assert intent.is_file() and list(tmp_path.glob('.jev-source-*.backup'))
    with pytest.raises(InputError, match='reconciled; review a new plan'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    assert source.read_bytes() == b'reviewed\n'
    assert not intent.exists() and not list(tmp_path.glob('.jev-source-*'))


def test_native_create_verification_failure_removes_owned_file(tmp_path, monkeypatch):
    from jev_integration_evaluator import windows_source_mutation as mutation

    real_check = mutation._check_parent
    calls = 0
    def fail_after_create(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise InputError('injected_post_create_failure')
        return real_check(*args)
    monkeypatch.setattr(mutation, '_check_parent', fail_after_create)
    plan = make_patch_plan(tmp_path, [{'file': 'created.py',
                                       'new_content': 'value = 1\n'}], ['native-source'])
    with pytest.raises(InputError, match='injected_post_create_failure'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    assert not (tmp_path / 'created.py').exists()


def test_native_partial_create_is_deleted_by_exclusive_handle(tmp_path, monkeypatch):
    import msvcrt
    from jev_integration_evaluator import windows_source_mutation as mutation

    source = tmp_path / 'created.py'
    _, source_io = cap._windows_absolute_path(source)
    real_write = os.write
    def partial_target_write(fd, data):
        actual = cap._windows_final_path(msvcrt.get_osfhandle(fd))
        if cap._windows_same_path(actual, source_io):
            real_write(fd, data[:3])
            return 3
        return real_write(fd, data)
    monkeypatch.setattr(mutation.os, 'write', partial_target_write)
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'value = 1\n'}], ['native-source'])
    with pytest.raises(InputError, match='windows_source_partial_write'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    assert not source.exists()


def test_native_rollback_preserves_concurrent_same_content_replacement(tmp_path):
    source = tmp_path / 'created.py'
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'value = 1\n'}], ['native-source'])
    replacement_identity = None
    def replace_then_fail(phase, _change):
        nonlocal replacement_identity
        if phase != 'write_completed':
            return
        competitor = tmp_path / 'competitor.py'
        competitor.write_bytes(b'value = 1\n')
        replacement_identity = cap._windows_file_identity(competitor.stat())
        os.replace(competitor, source)
        raise RuntimeError('injected_after_concurrent_replace')
    with pytest.raises(InputError, match='windows_source_owned_delete_identity_changed'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'], progress=replace_then_fail)
    assert source.read_bytes() == b'value = 1\n'
    assert cap._windows_file_identity(source.stat()) == replacement_identity


def test_native_owned_creation_rolls_back_after_later_failure(tmp_path):
    source = tmp_path / 'created.py'
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'value = 1\n'}], ['native-source'])
    def fail_after_write(phase, _change):
        if phase == 'write_completed':
            raise RuntimeError('injected_later_failure')
    with pytest.raises(RuntimeError, match='injected_later_failure'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'], progress=fail_after_write)
    assert not source.exists()


def test_native_new_nested_parent_creation_keeps_legacy_plan(tmp_path):
    source = tmp_path / 'new' / 'nested' / 'created.py'
    plan = make_patch_plan(tmp_path, [{'file': 'new/nested/created.py',
                                       'new_content': 'value = 1\n'}], ['native-source'])
    assert apply_patch_plan(tmp_path, plan, plan['plan_digest'])['status'] == 'applied'
    assert source.read_bytes() == b'value = 1\n'


def test_native_multifile_failure_restores_owned_first_write(tmp_path):
    source = tmp_path / 'owned.py'
    _, io_path = cap._windows_absolute_path(source)
    descriptor = cap._windows_create_private_file(io_path)
    try:
        os.write(descriptor, b'old\n')
    finally:
        os.close(descriptor)
    identity = cap._windows_file_identity(source.stat())
    acl = acl_sha256(source)
    plan = make_patch_plan(tmp_path, [
        {'file': source.name, 'new_content': 'new\n'},
        {'file': 'second.py', 'new_content': 'new\n'},
    ], ['native-source'])
    def fail_after_first(phase, _change):
        if phase == 'write_completed':
            raise RuntimeError('injected_second_file_failure')
    with pytest.raises(RuntimeError, match='injected_second_file_failure'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'], progress=fail_after_first)
    assert source.read_bytes() == b'old\n'
    assert acl_sha256(source) == acl
    # Rollback is a new reviewed replacement, so byte and ACL identity matter;
    # the original file identity is retained only for an interrupted write.
    assert cap._windows_file_identity(source.stat()) != identity
    assert not (tmp_path / 'second.py').exists()


def test_native_readonly_and_hardlink_refused_without_effect(tmp_path):
    source = tmp_path / 'owned.py'
    source.write_bytes(b'old\n')
    source.chmod(0o444)
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'new\n'}], ['native-source'])
    with pytest.raises(InputError):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    assert source.read_bytes() == b'old\n'
    source.chmod(0o666)
    alias = tmp_path / 'alias.py'
    os.link(source, alias)
    with pytest.raises(InputError, match='windows_source_link_or_identity_refused'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    assert source.read_bytes() == alias.read_bytes() == b'old\n'


def test_native_case_alias_duplicate_plan_refused(tmp_path):
    with pytest.raises(InputError, match='Duplicate patch path'):
        make_patch_plan(tmp_path, [
            {'file': 'A.py', 'new_content': 'a\n'},
            {'file': 'a.py', 'new_content': 'b\n'},
        ], ['native-source'])
    assert not list(tmp_path.iterdir())


def test_native_reparse_target_refused_without_effect(tmp_path):
    target = tmp_path / 'target.py'
    target.write_bytes(b'old\n')
    link = tmp_path / 'link.py'
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f'native symlink privilege unavailable: {type(exc).__name__}')
    with pytest.raises(InputError):
        make_patch_plan(tmp_path, [{'file': link.name,
                                    'new_content': 'new\n'}], ['native-source'])
    assert target.read_bytes() == b'old\n'


def test_native_junction_parent_refused_without_effect(tmp_path):
    target = tmp_path / 'outside'
    target.mkdir()
    source = target / 'owned.py'
    source.write_bytes(b'old\n')
    junction = tmp_path / 'junction'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(target)],
                            capture_output=True, text=True)
    assert result.returncode == 0
    try:
        plan = make_patch_plan(tmp_path, [{'file': 'junction/owned.py',
                                           'new_content': 'new\n'}], ['native-source'])
        with pytest.raises(InputError):
            apply_patch_plan(tmp_path, plan, plan['plan_digest'])
        assert source.read_bytes() == b'old\n'
    finally:
        junction.rmdir()


def test_native_locked_handle_refuses_without_effect(tmp_path):
    import ctypes
    from ctypes import wintypes

    source = tmp_path / 'locked.py'
    source.write_bytes(b'old\n')
    _, io_path = cap._windows_absolute_path(source)
    kernel = cap._windows_api()[2]
    handle = kernel.CreateFileW(io_path, 0x80000000, 1, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value
    try:
        plan = make_patch_plan(tmp_path, [{'file': source.name,
                                           'new_content': 'new\n'}], ['native-source'])
        with pytest.raises(InputError):
            apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    finally:
        kernel.CloseHandle(handle)
    assert source.read_bytes() == b'old\n'


def test_native_long_path_apply_and_rollback(tmp_path):
    parent = tmp_path
    for index in range(5):
        parent = parent / (f'segment{index}_' + 'x' * 40)
        parent.mkdir()
    source = parent / 'long.py'
    source.write_bytes(b'old\n')
    relative = source.relative_to(tmp_path).as_posix()
    assert len(str(source)) > 260
    plan = make_patch_plan(tmp_path, [{'file': relative,
                                       'new_content': 'new\n'}], ['native-source'])
    def fail_after_write(phase, _change):
        if phase == 'write_completed':
            raise RuntimeError('injected_long_path_rollback')
    with pytest.raises(RuntimeError, match='injected_long_path_rollback'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'], progress=fail_after_write)
    assert source.read_bytes() == b'old\n'
    assert apply_patch_plan(tmp_path, plan, plan['plan_digest'])['status'] == 'applied'
    assert source.read_bytes() == b'new\n'


@pytest.mark.parametrize('kind', ['create', 'update'])
def test_native_real_implementation_rollback_uses_applied_identity(tmp_path, kind):
    from jev_integration_evaluator.integrations.lifecycle import (
        apply_implementation, plan_implementation, rollback_implementation)
    from jev_integration_evaluator.integrations.verification import verify_implementation
    from jev_integration_evaluator.io import read_json
    from scripts.implementation_fixtures import fixture

    root, bundle = tmp_path / 'host', tmp_path / 'private-bundle'
    inventory, spec = fixture(root, 'C')
    planned = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_implementation(root, bundle, planned['bundle_digest'],
                                   baseline_sha256=baseline['receipt_sha256'])
    assert applied['status'] == 'applied_unverified'
    plan = read_json(bundle / 'implementation-plan.json')
    row = next(row for row in plan['owned_files']
               if (row['preimage'] is None) == (kind == 'create'))
    target = root / row['file']
    original_bytes = target.read_bytes()
    original_identity = cap._windows_file_identity(target.stat())
    saved = tmp_path / 'saved-owned-file'
    os.rename(target, saved)
    competitor = tmp_path / 'same-content-peer'
    competitor.write_bytes(original_bytes)
    competitor.chmod(row['new_mode'])
    peer_identity = cap._windows_file_identity(competitor.stat())
    os.rename(competitor, target)
    with pytest.raises(InputError, match='changed applied identity'):
        rollback_implementation(root, bundle, applied['rollback_digest'])
    assert target.read_bytes() == original_bytes
    assert cap._windows_file_identity(target.stat()) == peer_identity
    target.unlink()  # disposable test-owned competing file
    os.rename(saved, target)
    assert cap._windows_file_identity(target.stat()) == original_identity
    assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
