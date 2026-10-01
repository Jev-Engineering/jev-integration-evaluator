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


@pytest.mark.parametrize('phase,peer', [('rename', False), ('rename', True),
                                        ('rename', 'dangling'), ('commit', False)])
def test_native_create_death_uses_prepared_identity_without_replay(tmp_path, phase, peer):
    from jev_integration_evaluator import windows_source_mutation as mutation

    if peer == 'dangling':
        probe = tmp_path / 'symlink-probe'
        try:
            probe.symlink_to(tmp_path / 'absent')
        except OSError as exc:
            pytest.skip(f'native symlink privilege unavailable: {type(exc).__name__}')
        probe.unlink()
    source = tmp_path / 'created.py'
    plan = make_patch_plan(tmp_path, [{'file': source.name,
                                       'new_content': 'reviewed\n'}], ['native-source'])
    planfile = tmp_path / 'reviewed-plan.json'
    planfile.write_text(json.dumps(plan), encoding='utf-8')
    child = '''import json,os,sys
from jev_integration_evaluator import windows_source_mutation as m
from jev_integration_evaluator.implementation import apply_patch_plan
phase=sys.argv[3]
if phase=='rename':
    real=m._rename_owned
    def crash(fd,destination):
        real(fd,destination)
        os._exit(73)
    m._rename_owned=crash
else:
    real=m._commit_intent
    def crash(*args):
        real(*args)
        os._exit(74)
    m._commit_intent=crash
plan=json.loads(open(sys.argv[2],encoding='utf-8').read())
apply_patch_plan(sys.argv[1],plan,plan['plan_digest'])
'''
    result = subprocess.run([sys.executable, '-c', child, str(tmp_path),
                             str(planfile), phase], capture_output=True,
                            text=True, timeout=20)
    assert result.returncode == (73 if phase == 'rename' else 74)
    assert source.read_bytes() == b'reviewed\n'
    intent = mutation._intent_path(source, None, plan['changes'][0]['new_sha256'],
                                   tmp_path)
    assert intent.is_file()
    if peer:
        source.unlink()  # disposable test-owned created file
        if peer == 'dangling':
            source.symlink_to(tmp_path / 'missing-peer')
        else:
            source.write_bytes(b'peer atomic save\n')
        with pytest.raises(InputError):
            apply_patch_plan(tmp_path, plan, plan['plan_digest'])
        if peer == 'dangling':
            assert source.is_symlink()
        else:
            assert source.read_bytes() == b'peer atomic save\n'
        assert intent.is_file()
        source.unlink()  # disposable test-owned peer
    with pytest.raises(InputError, match='reconciled; review a new plan'):
        apply_patch_plan(tmp_path, plan, plan['plan_digest'])
    if phase == 'rename':
        assert not source.exists()
    else:
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
    real_write = os.write
    def partial_target_write(fd, data):
        actual = cap._windows_final_path(msvcrt.get_osfhandle(fd))
        if '.jev-source-' in actual.casefold() and len(data) == len(b'value = 1\n'):
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


def _deny(path, rights: str) -> str:
    """Add one disposable explicit deny ACE for this account; no elevation needed."""
    principal = subprocess.run(['whoami'], capture_output=True, text=True, timeout=10)
    assert principal.returncode == 0
    identity = principal.stdout.strip()
    denied = subprocess.run(['icacls', str(path), '/deny', identity + ':' + rights],
                            capture_output=True, text=True, timeout=10)
    assert denied.returncode == 0, 'Disposable deny ACE could not be set'
    return identity


def _allow(path, identity: str) -> None:
    restored = subprocess.run(['icacls', str(path), '/remove:d', identity],
                              capture_output=True, text=True, timeout=10)
    assert restored.returncode == 0, 'Disposable test ACL could not be restored'


def test_native_write_path_acl_denial_refuses_apply_without_effect(tmp_path):
    from jev_integration_evaluator import windows_source_mutation as mutation

    def fixture(name: str):
        root = tmp_path / name
        root.mkdir()
        source = root / 'owned.py'
        source.write_bytes(b'old\n')
        update = make_patch_plan(root, [{'file': source.name,
                                         'new_content': 'new\n'}], ['native-source'])
        create = make_patch_plan(root, [{'file': 'created.py',
                                         'new_content': 'created\n'}], ['native-source'])
        intents = (mutation._intent_path(source, update['changes'][0]['old_sha256'],
                                         update['changes'][0]['new_sha256'], root),
                   mutation._intent_path(root / 'created.py', None,
                                         create['changes'][0]['new_sha256'], root))
        identity = cap._windows_file_identity(source.stat())

        def unchanged() -> None:
            assert source.read_bytes() == b'old\n'
            assert cap._windows_file_identity(source.stat()) == identity
            assert [entry.name for entry in root.iterdir()] == ['owned.py']
            assert not any(os.path.lexists(intent) for intent in intents)

        return root, source, update, create, intents, unchanged

    # Control: without a deny ACE the same reviewed update and creation apply,
    # so each refusal below is attributable to the denied write path alone.
    root, source, update, create, intents, _ = fixture('control')
    assert apply_patch_plan(root, update, update['plan_digest'])['status'] == 'applied'
    assert apply_patch_plan(root, create, create['plan_digest'])['status'] == 'applied'
    assert source.read_bytes() == b'new\n'
    assert (root / 'created.py').read_bytes() == b'created\n'
    assert sorted(entry.name for entry in root.iterdir()) == ['created.py', 'owned.py']
    assert not any(os.path.lexists(intent) for intent in intents)

    # 1. The directory refuses new files: neither the staged replacement nor
    #    an exclusively created reviewed file can be written.
    root, source, update, create, intents, unchanged = fixture('create-denied')
    account = _deny(root, '(WD)')
    try:
        with pytest.raises(InputError, match='^windows_source_staging_copy_failed$'):
            apply_patch_plan(root, update, update['plan_digest'])
        with pytest.raises(InputError, match='^windows_source_'):
            apply_patch_plan(root, create, create['plan_digest'])
        unchanged()
    finally:
        _allow(root, account)
    unchanged()

    # 2. DELETE on the file and DELETE_CHILD on its parent are both denied, so
    #    the pinned replace lease on the reviewed target is unavailable.
    root, source, update, _, _, unchanged = fixture('replace-denied')
    account = _deny(source, '(DE)')
    try:
        _deny(root, '(DC)')
        try:
            with pytest.raises(InputError, match='^windows_source_locked_or_access_denied$'):
                apply_patch_plan(root, update, update['plan_digest'])
            unchanged()
        finally:
            _allow(root, account)
    finally:
        _allow(source, account)
    unchanged()


def _source_security(path):
    """Owner, complete self-relative descriptor and policy hash of one file."""
    from jev_integration_evaluator import windows_source_mutation as mutation

    _, io_path = cap._windows_absolute_path(path)
    fd, _ = mutation._lease(io_path)
    try:
        owner, descriptor = mutation._security_snapshot(fd)
    finally:
        os.close(fd)
    return owner, descriptor, mutation._dacl_hash(descriptor)


def test_native_read_denied_source_refuses_apply_with_private_reason(tmp_path):
    from jev_integration_evaluator import windows_source_mutation as mutation

    root = tmp_path / 'host'
    root.mkdir()
    first, denied = root / 'first.py', root / 'owned.py'
    first.write_bytes(b'first old\n')
    denied.write_bytes(b'old\n')
    plan = make_patch_plan(root, [
        {'file': 'first.py', 'new_content': 'first new\n'},
        {'file': 'owned.py', 'new_content': 'new\n'},
    ], ['native-source'])
    intents = [mutation._intent_path(root / change['file'], change['old_sha256'],
                                     change['new_sha256'], root)
               for change in plan['changes']]
    identities = {path: cap._windows_file_identity(path.stat()) for path in (first, denied)}
    events = []
    # Deny file data reads only; WRITE_DAC stays available for the cleanup.
    account = _deny(denied, '(RD)')
    try:
        with pytest.raises(PermissionError):
            denied.read_bytes()
        with pytest.raises(InputError) as refused:
            apply_patch_plan(root, plan, plan['plan_digest'],
                             progress=lambda phase, _change: events.append(phase))
        assert str(refused.value) == 'windows_source_read_access_denied'
        assert refused.value.args == ('windows_source_read_access_denied',)
        assert refused.value.__cause__ is None and refused.value.__suppress_context__
        assert not isinstance(refused.value, OSError)
        for private in (str(tmp_path), tmp_path.name, 'owned.py', 'host'):
            assert private not in str(refused.value)
        # No effect: no write started, no stage, backup or external intent.
        assert events == []
        assert first.read_bytes() == b'first old\n'
        assert sorted(entry.name for entry in root.iterdir()) == ['first.py', 'owned.py']
        assert {path: cap._windows_file_identity(path.stat())
                for path in (first, denied)} == identities
        assert not any(os.path.lexists(intent) for intent in intents)
    finally:
        _allow(denied, account)
    assert denied.read_bytes() == b'old\n' and first.read_bytes() == b'first old\n'
    assert {path: cap._windows_file_identity(path.stat())
            for path in (first, denied)} == identities
    # The same approved plan applies once the read is allowed again.
    assert apply_patch_plan(root, plan, plan['plan_digest'])['status'] == 'applied'
    assert denied.read_bytes() == b'new\n' and first.read_bytes() == b'first new\n'


def _case_sensitive(directory, state: str) -> None:
    changed = subprocess.run(
        ['fsutil', 'file', 'setCaseSensitiveInfo', str(directory), state],
        capture_output=True, text=True, timeout=15)
    assert changed.returncode == 0, 'Per-directory NTFS case sensitivity is unavailable'


def test_native_real_case_alias_refuses_apply_without_effect(tmp_path):
    """A selected target with an on-disk sibling differing only by case."""
    from jev_integration_evaluator import windows_source_mutation as mutation

    root = tmp_path / 'host'
    package = root / 'pkg'
    package.mkdir(parents=True)
    _case_sensitive(package, 'enable')
    lower, upper = package / 'module.py', package / 'MODULE.py'
    try:
        # Planning refuses an alias too, so each plan is made while its target
        # has no differently cased sibling; the alias appears afterwards.
        upper.write_bytes(b'value = 2\n')
        other = make_patch_plan(root, [{'file': 'pkg/MODULE.py',
                                        'new_content': 'value = 5\n'}], ['native-source'])
        assert other['changes'][0]['operation'] == 'update'
        upper.unlink()
        create = make_patch_plan(root, [{'file': 'pkg/MODULE.py',
                                         'new_content': 'value = 4\n'}], ['native-source'])
        assert create['changes'][0]['operation'] == 'create'
        lower.write_bytes(b'value = 1\n')
        update = make_patch_plan(root, [{'file': 'pkg/module.py',
                                         'new_content': 'value = 3\n'}], ['native-source'])
        # Creating the other spelling beside the existing entry would make the alias.
        with pytest.raises(InputError, match='^windows_source_case_alias_refused$'):
            apply_patch_plan(root, create, create['plan_digest'])
        assert os.listdir(package) == ['module.py'] and lower.read_bytes() == b'value = 1\n'

        upper.write_bytes(b'value = 2\n')
        assert sorted(os.listdir(package)) == ['MODULE.py', 'module.py']
        identities = {path: cap._windows_file_identity(path.stat()) for path in (lower, upper)}
        intents = [mutation._intent_path(root / plan['changes'][0]['file'],
                                         plan['changes'][0]['old_sha256'],
                                         plan['changes'][0]['new_sha256'], root)
                   for plan in (update, other, create)]
        events = []
        for plan in (update, other):
            with pytest.raises(InputError, match='^windows_source_case_alias_refused$'):
                apply_patch_plan(root, plan, plan['plan_digest'],
                                 progress=lambda phase, _change: events.append(phase))
        assert events == []
        assert lower.read_bytes() == b'value = 1\n' and upper.read_bytes() == b'value = 2\n'
        assert sorted(os.listdir(package)) == ['MODULE.py', 'module.py']
        assert {path: cap._windows_file_identity(path.stat())
                for path in (lower, upper)} == identities
        assert not any(os.path.lexists(intent) for intent in intents)
        upper.unlink()
        # With the alias gone the same approved update applies in that directory.
        assert apply_patch_plan(root, update, update['plan_digest'])['status'] == 'applied'
        assert lower.read_bytes() == b'value = 3\n' and os.listdir(package) == ['module.py']
    finally:
        for path in (upper, lower):
            if os.path.lexists(path):
                path.unlink()
        _case_sensitive(package, 'disable')


def _private_refusal(refused, reason: str, tmp_path, *private: str) -> None:
    assert str(refused.value) == reason and refused.value.args == (reason,)
    # No chained operating-system exception is reachable from the refusal.
    assert refused.value.__cause__ is None
    assert refused.value.__context__ is None or refused.value.__suppress_context__
    assert not isinstance(refused.value, OSError)
    for text in (str(tmp_path), tmp_path.name, *private):
        assert text not in str(refused.value)


def test_native_read_denied_source_refuses_plan_with_private_reason(tmp_path):
    """Planning reads the target; a denied read is a fixed path-free reason."""
    import hashlib

    root = tmp_path / 'host'
    root.mkdir()
    first, denied = root / 'first.py', root / 'owned.py'
    first.write_bytes(b'first old\n')
    denied.write_bytes(b'old\n')
    changes = [{'file': 'first.py', 'new_content': 'first new\n'},
               {'file': 'owned.py', 'new_content': 'new\n'}]
    identities = {path: cap._windows_file_identity(path.stat()) for path in (first, denied)}
    # Deny file data reads only; WRITE_DAC stays available for the cleanup.
    account = _deny(denied, '(RD)')
    try:
        with pytest.raises(PermissionError):
            denied.read_bytes()
        with pytest.raises(InputError) as refused:
            make_patch_plan(root, changes, ['native-source'])
        _private_refusal(refused, 'windows_source_read_access_denied', tmp_path,
                         'owned.py', 'host')
        assert sorted(entry.name for entry in root.iterdir()) == ['first.py', 'owned.py']
        assert first.read_bytes() == b'first old\n'
    finally:
        _allow(denied, account)
    assert denied.read_bytes() == b'old\n'
    assert {path: cap._windows_file_identity(path.stat())
            for path in (first, denied)} == identities
    # The same request plans once the read is allowed again.
    plan = make_patch_plan(root, changes, ['native-source'])
    assert [(change['file'], change['operation']) for change in plan['changes']] == [
        ('first.py', 'update'), ('owned.py', 'update')]
    assert plan['changes'][1]['old_sha256'] == hashlib.sha256(b'old\n').hexdigest()


def test_native_exclusively_locked_source_refuses_plan_with_private_reason(tmp_path):
    """A handle that shares nothing makes the planning read a sharing violation."""
    from ctypes import wintypes

    root = tmp_path / 'host'
    root.mkdir()
    source = root / 'locked.py'
    source.write_bytes(b'old\n')
    changes = [{'file': 'locked.py', 'new_content': 'new\n'}]
    _, io_path = cap._windows_absolute_path(source)
    kernel = cap._windows_api()[2]
    handle = kernel.CreateFileW(io_path, 0x80000000, 0, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value
    try:
        with pytest.raises(PermissionError):
            source.read_bytes()
        with pytest.raises(InputError) as refused:
            make_patch_plan(root, changes, ['native-source'])
        _private_refusal(refused, 'windows_source_read_access_denied', tmp_path,
                         'locked.py', 'host')
        assert [entry.name for entry in root.iterdir()] == ['locked.py']
    finally:
        assert kernel.CloseHandle(handle)
    assert source.read_bytes() == b'old\n'
    plan = make_patch_plan(root, changes, ['native-source'])
    assert plan['changes'][0]['operation'] == 'update'
    assert apply_patch_plan(root, plan, plan['plan_digest'])['status'] == 'applied'
    assert source.read_bytes() == b'new\n'


def test_native_real_case_alias_refuses_plan_without_effect(tmp_path):
    """Planning refuses a target with an on-disk sibling differing only by case."""
    root = tmp_path / 'host'
    package = root / 'pkg'
    package.mkdir(parents=True)
    _case_sensitive(package, 'enable')
    lower, upper = package / 'module.py', package / 'MODULE.py'

    def planned(relative: str) -> dict:
        return make_patch_plan(root, [{'file': relative, 'new_content': 'value = 3\n'}],
                               ['native-source'])

    try:
        lower.write_bytes(b'value = 1\n')
        # A new spelling beside the existing entry would create the alias.
        with pytest.raises(InputError) as refused:
            planned('pkg/MODULE.py')
        _private_refusal(refused, 'windows_source_case_alias_refused', tmp_path,
                         'MODULE.py', 'pkg')
        assert os.listdir(package) == ['module.py']
        upper.write_bytes(b'value = 2\n')
        identities = {path: cap._windows_file_identity(path.stat()) for path in (lower, upper)}
        for relative in ('pkg/module.py', 'pkg/MODULE.py'):
            with pytest.raises(InputError, match='^windows_source_case_alias_refused$'):
                planned(relative)
        # A clean first change does not hide the aliased one.
        with pytest.raises(InputError, match='^windows_source_case_alias_refused$'):
            make_patch_plan(root, [{'file': 'clean.py', 'new_content': 'clean\n'},
                                   {'file': 'pkg/module.py', 'new_content': 'value = 3\n'}],
                            ['native-source'])
        assert sorted(os.listdir(package)) == ['MODULE.py', 'module.py']
        assert sorted(entry.name for entry in root.iterdir()) == ['pkg']
        assert lower.read_bytes() == b'value = 1\n' and upper.read_bytes() == b'value = 2\n'
        assert {path: cap._windows_file_identity(path.stat())
                for path in (lower, upper)} == identities
        upper.unlink()
        # With the alias gone the same request plans and applies.
        plan = planned('pkg/module.py')
        assert plan['changes'][0]['operation'] == 'update'
        assert apply_patch_plan(root, plan, plan['plan_digest'])['status'] == 'applied'
        assert lower.read_bytes() == b'value = 3\n' and os.listdir(package) == ['module.py']
    finally:
        for path in (upper, lower):
            if os.path.lexists(path):
                path.unlink()
        _case_sensitive(package, 'disable')


@pytest.mark.parametrize('touched', ('file', 'parent'))
def test_native_icacls_touched_inherited_dacl_is_reproduced_exactly(tmp_path, touched):
    """An ACE added and removed by icacls leaves SE_DACL_AUTO_INHERITED set."""
    root = tmp_path / 'host'
    root.mkdir()
    source = root / 'owned.py'
    source.write_bytes(b'old\n')
    target = source if touched == 'file' else root
    account = _deny(target, '(WD)')
    _allow(target, account)
    owner, descriptor, policy = _source_security(source)
    control = struct.unpack_from('<H', descriptor, 2)[0]
    offset = struct.unpack_from('<I', descriptor, 16)[0]
    dacl = descriptor[offset:offset + struct.unpack_from('<H', descriptor, offset + 2)[0]]
    # Not protected, automatically inherited: the control bit a plain
    # SetKernelObjectSecurity restore drops unless it is requested.
    assert control & 0x0400 and not control & 0x1000
    plan = make_patch_plan(root, [{'file': 'owned.py', 'new_content': 'new\n'}],
                           ['native-source'])

    def fail_after_write(phase, _change):
        if phase == 'write_completed':
            raise RuntimeError('injected_following_failure')

    def exact() -> None:
        now_owner, now, now_policy = _source_security(source)
        start = struct.unpack_from('<I', now, 16)[0]
        assert (now_owner, now_policy) == (owner, policy)
        assert struct.unpack_from('<H', now, 2)[0] & 0x150C == control & 0x150C
        assert now[start:start + struct.unpack_from('<H', now, start + 2)[0]] == dacl

    with pytest.raises(RuntimeError, match='injected_following_failure'):
        apply_patch_plan(root, plan, plan['plan_digest'], progress=fail_after_write)
    assert source.read_bytes() == b'old\n'
    exact()
    assert apply_patch_plan(root, plan, plan['plan_digest'])['status'] == 'applied'
    assert source.read_bytes() == b'new\n'
    assert [entry.name for entry in root.iterdir()] == ['owned.py']
    exact()
