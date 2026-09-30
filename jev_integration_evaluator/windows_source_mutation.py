"""Guarded NTFS replacement for reviewed source; no target execution.

Directory handles pin the lexical ancestors. An existing source lease denies
concurrent data writers and deletion. A copied stage retains named streams;
handle-owned, no-replace renames preserve peer files. An external intent
records exact identities for interrupted recovery without source bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import uuid

from . import capabilities as cap
from .io import InputError


def _security_snapshot(fd: int) -> tuple[str, bytes]:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = cap._windows_api()[2]
    advapi.GetSecurityInfo.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    advapi.GetSecurityInfo.restype = wintypes.DWORD
    advapi.GetLengthSid.argtypes = (ctypes.c_void_p,)
    advapi.GetLengthSid.restype = wintypes.DWORD
    advapi.GetSecurityDescriptorLength.argtypes = (ctypes.c_void_p,)
    advapi.GetSecurityDescriptorLength.restype = wintypes.DWORD
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel.LocalFree.restype = ctypes.c_void_p
    owner, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    if advapi.GetSecurityInfo(msvcrt.get_osfhandle(fd), 1, 1 | 4,
                              ctypes.byref(owner), None, None, None,
                              ctypes.byref(descriptor)):
        raise InputError('windows_source_security_unavailable')
    try:
        size = advapi.GetSecurityDescriptorLength(descriptor)
        sid_size = advapi.GetLengthSid(owner)
        if not 0 < size <= 65_536 or not 0 < sid_size <= 256:
            raise InputError('windows_source_security_unavailable')
        return (hashlib.sha256(ctypes.string_at(owner, sid_size)).hexdigest(),
                ctypes.string_at(descriptor, size))
    finally:
        kernel.LocalFree(descriptor)


def _security(fd: int) -> tuple[str, str]:
    owner, descriptor = _security_snapshot(fd)
    return owner, _dacl_hash(descriptor)


def _dacl_hash(descriptor: bytes) -> str:
    """Hash the DACL and its policy bits, excluding unrelated descriptor layout."""
    if len(descriptor) < 20 or descriptor[0] != 1:
        raise InputError('windows_source_security_unavailable')
    control = struct.unpack_from('<H', descriptor, 2)[0]
    if not control & 0x8000 or not control & 0x0004:
        raise InputError('windows_source_security_unavailable')
    offset = struct.unpack_from('<I', descriptor, 16)[0]
    if not offset or offset + 8 > len(descriptor):
        raise InputError('windows_source_security_unavailable')
    size = struct.unpack_from('<H', descriptor, offset + 2)[0]
    if size < 8 or offset + size > len(descriptor):
        raise InputError('windows_source_security_unavailable')
    # PRESENT, DEFAULTED, AUTO_INHERIT_REQ, AUTO_INHERITED, PROTECTED.
    material = struct.pack('<H', control & 0x150C) + descriptor[offset:offset + size]
    return hashlib.sha256(material).hexdigest()


def _restore_dacl(fd: int, descriptor: bytes) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    advapi.GetSecurityDescriptorControl.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD))
    advapi.GetSecurityDescriptorControl.restype = wintypes.BOOL
    advapi.SetKernelObjectSecurity.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p)
    advapi.SetKernelObjectSecurity.restype = wintypes.BOOL
    buffer = ctypes.create_string_buffer(descriptor)
    control, revision = wintypes.WORD(), wintypes.DWORD()
    if not advapi.GetSecurityDescriptorControl(buffer, ctypes.byref(control), ctypes.byref(revision)):
        raise InputError('windows_source_acl_restore_unavailable')
    flags = 4 | (0x80000000 if control.value & 0x1000 else 0x20000000)
    if not advapi.SetKernelObjectSecurity(msvcrt.get_osfhandle(fd), flags, buffer):
        raise InputError('windows_source_acl_restore_failed_recovery_required')


def _check_parent(parent: Path, pinned: list[int]) -> None:
    _, io_path, _ = cap._windows_check_directory_path(parent, purpose='source_mutation')
    fd, info, _, _ = cap._windows_open_directory(io_path)
    try:
        if cap._windows_file_identity(info) != cap._windows_file_identity(os.fstat(pinned[-1])):
            raise InputError('windows_source_parent_identity_changed')
    finally:
        os.close(fd)


def _ensure_parent(repository_root: Path, parent: Path) -> None:
    """Create ordinary missing descendants under pinned, checked ancestors."""
    root = Path(repository_root)
    try:
        components = parent.relative_to(root).parts
    except ValueError:
        raise InputError('windows_source_parent_outside_repository') from None
    _, _, _, pinned = cap._windows_pin_directory_path(root, purpose='source_mutation')
    cursor = root
    try:
        for part in components:
            if not cap._windows_safe_component(part):
                raise InputError('windows_source_path_component_refused')
            cursor = cursor / part
            _, io_path = cap._windows_absolute_path(cursor)
            try:
                os.mkdir(io_path)
            except FileExistsError:
                pass
            fd, _, final_path, _ = cap._windows_open_directory(io_path,
                                                                 share_delete=False)
            if not cap._windows_same_path(final_path, io_path):
                os.close(fd)
                raise InputError('windows_source_parent_identity_changed')
            pinned.append(fd)
    finally:
        for fd in reversed(pinned):
            os.close(fd)


def _lease(io_path: str, *, pin_name: bool = False):
    import ctypes
    import msvcrt

    _, wintypes, kernel = cap._windows_api()
    # Deny data writers while allowing the replace operation's DELETE access.
    access = 0x80000000 | 0x00020000 | 0x00040000 | (0x00010000 if pin_name else 0)
    handle = kernel.CreateFileW(io_path, access,
                                1 if pin_name else 1 | 4, None, 3, 0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise InputError('windows_source_locked_or_access_denied')
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or cap._windows_reparse_reason(info)
                or not cap._windows_same_path(
                    cap._windows_final_path(msvcrt.get_osfhandle(fd)), io_path)):
            raise InputError('windows_source_link_or_identity_refused')
        if info.st_file_attributes & 1:
            raise InputError('windows_source_readonly_refused')
        return fd, info
    except BaseException:
        os.close(fd)
        raise


def _identity_at(io_path: str) -> tuple[int, int]:
    fd, info = _lease(io_path)
    try:
        return cap._windows_file_identity(info)
    finally:
        os.close(fd)


def _rename_owned(fd: int, destination: Path) -> None:
    """Rename the retained NTFS identity without replacing any destination."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class _Rename(ctypes.Structure):
        _fields_ = (('ReplaceIfExists', wintypes.BOOLEAN),
                    ('RootDirectory', wintypes.HANDLE),
                    ('FileNameLength', wintypes.DWORD),
                    ('FileName', wintypes.WCHAR * 1))

    _, io_path = cap._windows_absolute_path(destination)
    name = io_path.encode('utf-16-le')
    buffer = ctypes.create_string_buffer(_Rename.FileName.offset + len(name) + 2)
    info = _Rename.from_buffer(buffer)
    info.ReplaceIfExists = 0
    info.RootDirectory = None
    info.FileNameLength = len(name)
    ctypes.memmove(ctypes.addressof(buffer) + _Rename.FileName.offset, name, len(name))
    _, _, kernel = cap._windows_api()
    kernel.SetFileInformationByHandle.argtypes = (
        wintypes.HANDLE, wintypes.INT, ctypes.c_void_p, wintypes.DWORD)
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    if not kernel.SetFileInformationByHandle(msvcrt.get_osfhandle(fd), 3,
                                              buffer, len(buffer)):
        raise InputError('windows_source_owned_rename_refused')


def _delete_owned_handle(fd: int) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _, _, kernel = cap._windows_api()
    kernel.SetFileInformationByHandle.argtypes = (
        wintypes.HANDLE, wintypes.INT, ctypes.c_void_p, wintypes.DWORD)
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    value = ctypes.c_uint32(1)
    if not kernel.SetFileInformationByHandle(msvcrt.get_osfhandle(fd), 4,
                                              ctypes.byref(value), ctypes.sizeof(value)):
        raise InputError('windows_source_owned_delete_failed')


def _open_stage_writer(io_path: str, identity: tuple[int, int]) -> int:
    import msvcrt

    _, wintypes, kernel = cap._windows_api()
    handle = kernel.CreateFileW(io_path, 0x40000000 | 0x00010000,
                                0, None, 5, 0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise InputError('windows_source_staging_write_unavailable')
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    info = os.fstat(fd)
    if (cap._windows_file_identity(info) != identity or info.st_nlink != 1
            or cap._windows_reparse_reason(info)):
        os.close(fd)
        raise InputError('windows_source_staging_identity_changed')
    return fd


def _intent_path(path: Path, old_sha: str, new_sha: str,
                 repository_root: Path | None = None) -> Path:
    display, _ = cap._windows_absolute_path(path)
    key = hashlib.sha256((display.casefold() + '\0' + old_sha + '\0' + new_sha)
                         .encode('utf-8')).hexdigest()[:32]
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        raise InputError('windows_source_external_intent_unavailable')
    _, _, _ = cap._windows_check_directory_path(local, purpose='source_intent')
    intent = Path(local) / ('.jev-source-' + key + '.intent')
    if repository_root is not None and cap._path_is_within(intent, repository_root):
        raise InputError('windows_source_external_intent_unavailable')
    return intent


def _intent_bytes(record: dict) -> bytes:
    return (json.dumps(record, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True) + '\n').encode('ascii')


def _write_intent(path: Path, record: dict) -> tuple[tuple[int, int], str]:
    _, io_path = cap._windows_absolute_path(path)
    raw = _intent_bytes(record)
    _, _, _, pinned = cap._windows_pin_directory_path(path.parent,
                                                       purpose='source_intent')
    try:
        fd = cap._windows_create_private_file(io_path, delete_access=True)
        try:
            identity = cap._windows_file_identity(os.fstat(fd))
            if os.write(fd, raw) != len(raw):
                raise InputError('windows_source_intent_write_failed')
            os.fsync(fd)
            return identity, hashlib.sha256(raw).hexdigest()
        except Exception:
            _delete_owned_handle(fd)
            raise
        finally:
            os.close(fd)
    finally:
        for fd in reversed(pinned):
            os.close(fd)


def _commit_intent(path: Path, identity: tuple[int, int], raw_sha: str) -> str:
    _, io_path = cap._windows_absolute_path(path)
    fd = os.open(io_path, os.O_RDWR | os.O_BINARY)
    try:
        if cap._windows_file_identity(os.fstat(fd)) != identity:
            raise InputError('windows_source_intent_identity_changed')
        raw = os.read(fd, 4097)
        if hashlib.sha256(raw).hexdigest() != raw_sha:
            raise InputError('windows_source_intent_content_changed')
        marker = b'commit\n'
        if os.write(fd, marker) != len(marker):
            raise InputError('windows_source_intent_commit_failed')
        os.fsync(fd)
        return hashlib.sha256(raw + marker).hexdigest()
    finally:
        os.close(fd)


def reconcile_pending_reviewed_write(path: Path, old_sha: str, new_sha: str,
                                     repository_root: Path) -> bool:
    """Reconcile one exact approved interrupted write; never replay the edit."""
    intent = _intent_path(path, old_sha, new_sha, repository_root)
    if not intent.exists():
        return False
    _, intent_io = cap._windows_absolute_path(intent)
    intent_fd, intent_info = _lease(intent_io)
    try:
        raw = os.read(intent_fd, 4097)
        if len(raw) > 4096:
            raise InputError('windows_source_intent_invalid')
        lines = raw.splitlines(keepends=True)
        if len(lines) not in (1, 2) or any(not line.endswith(b'\n') for line in lines):
            raise InputError('windows_source_intent_invalid')
        committed = len(lines) == 2 and lines[1] == b'commit\n'
        if len(lines) == 2 and not committed:
            raise InputError('windows_source_intent_invalid')
        try:
            record = json.loads(lines[0])
        except (ValueError, UnicodeDecodeError):
            raise InputError('windows_source_intent_invalid') from None
        if (type(record) is not dict or set(record) !=
                {'kind', 'target', 'old_sha256', 'new_sha256', 'old_identity',
                 'stage_identity', 'stage', 'backup'} or
                record['kind'] != 'jev-reviewed-source-intent-v1' or
                record['target'] != path.name or record['old_sha256'] != old_sha or
                record['new_sha256'] != new_sha or
                any(type(record[key]) is not list or len(record[key]) != 2
                    for key in ('old_identity', 'stage_identity')) or
                any(type(v) is not int or v <= 0
                    for key in ('old_identity', 'stage_identity') for v in record[key]) or
                type(record['stage']) is not str or
                not record['stage'].startswith('.jev-source-') or
                not cap._windows_safe_component(record['stage']) or
                type(record['backup']) is not str or
                record['backup'] != record['stage'] + '.backup'):
            raise InputError('windows_source_intent_invalid')
        intent_identity = cap._windows_file_identity(intent_info)
        intent_sha = hashlib.sha256(raw).hexdigest()
    finally:
        os.close(intent_fd)
    parent = path.parent
    stage = parent / record['stage']
    backup = parent / record['backup']
    old_identity = tuple(record['old_identity'])
    stage_identity = tuple(record['stage_identity'])
    _, target_io = cap._windows_absolute_path(path)
    _, _, _, pinned = cap._windows_pin_directory_path(parent, purpose='source_mutation')
    try:
        if committed:
            if not path.exists():
                raise InputError('windows_source_committed_target_missing')
            fd, info = _lease(target_io)
            try:
                if (cap._windows_file_identity(info) != stage_identity or
                        hashlib.sha256(os.read(fd, 2_000_001)).hexdigest() != new_sha):
                    raise InputError('windows_source_committed_target_changed')
            finally:
                os.close(fd)
            if backup.exists():
                remove_owned_created(backup, old_identity, old_sha)
        elif backup.exists():
            _, backup_io = cap._windows_absolute_path(backup)
            old_fd, old_info = _lease(backup_io, pin_name=True)
            try:
                if (cap._windows_file_identity(old_info) != old_identity or
                        hashlib.sha256(os.read(old_fd, 2_000_001)).hexdigest() != old_sha):
                    raise InputError('windows_source_backup_changed')
                if path.exists():
                    current_fd, current_info = _lease(target_io, pin_name=True)
                    try:
                        if (cap._windows_file_identity(current_info) != stage_identity or
                                hashlib.sha256(os.read(current_fd, 2_000_001)).hexdigest()
                                != new_sha):
                            raise InputError('windows_source_peer_target_preserved')
                        _rename_owned(current_fd, stage)
                    finally:
                        os.close(current_fd)
                _rename_owned(old_fd, path)
            finally:
                os.close(old_fd)
        else:
            fd, info = _lease(target_io)
            try:
                if (cap._windows_file_identity(info) != old_identity or
                        hashlib.sha256(os.read(fd, 2_000_001)).hexdigest() != old_sha):
                    raise InputError('windows_source_unexpected_target_preserved')
            finally:
                os.close(fd)
        if stage.exists():
            remove_owned_created(stage, stage_identity, new_sha)
        remove_owned_created(intent, intent_identity, intent_sha)
        return True
    finally:
        for fd in reversed(pinned):
            os.close(fd)


def remove_owned_created(path: Path, identity: tuple[int, int], expected_sha256: str) -> None:
    """Delete an owned creation by handle, never by a checked-then-reopened name."""
    import ctypes
    import msvcrt

    display, io_path = cap._windows_absolute_path(path)
    _, _, _, pinned = cap._windows_pin_directory_path(Path(display).parent,
                                                        purpose='source_mutation')
    try:
        _, wintypes, kernel = cap._windows_api()
        handle = kernel.CreateFileW(io_path, 0x80000000 | 0x00010000,
                                    1, None, 3, 0x00200000, None)
        if handle == wintypes.HANDLE(-1).value:
            raise InputError('windows_source_owned_delete_unavailable')
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        try:
            info = os.fstat(fd)
            if (cap._windows_file_identity(info) != identity or info.st_nlink != 1
                    or cap._windows_reparse_reason(info)
                    or not cap._windows_same_path(cap._windows_final_path(msvcrt.get_osfhandle(fd)), io_path)
                    or hashlib.sha256(os.read(fd, 2_000_001)).hexdigest() != expected_sha256):
                raise InputError('windows_source_owned_delete_identity_changed')
            _check_parent(Path(display).parent, pinned)
            _delete_owned_handle(fd)
        finally:
            os.close(fd)
    finally:
        for fd in reversed(pinned):
            os.close(fd)


def write_reviewed_text(path: Path, text: str, expected_sha256: str | None,
                        *, expected_identity: tuple[int, int] | None = None,
                        repository_root: Path | None = None) -> tuple[int, int]:
    """Replace one exact reviewed file, or exclusively create an absent file."""
    import ctypes
    from .windows_template_preflight import _profile

    _profile()
    raw = text.encode('utf-8')
    if len(raw) > 2_000_000:
        raise InputError('windows_source_content_limit')
    display, io_path = cap._windows_absolute_path(path)
    if not cap._windows_safe_component(Path(display).name):
        raise InputError('windows_source_path_component_refused')
    if repository_root is not None:
        try:
            _ensure_parent(Path(repository_root), Path(display).parent)
        except (cap.CapabilityError, OSError):
            raise InputError('windows_source_parent_unavailable') from None
    pinned = []
    source_fd = stage_fd = None
    stage_path = Path(display).with_name('.jev-source-' + uuid.uuid4().hex)
    backup_path = stage_path.with_suffix('.backup')
    stage_identity = None
    created_identity = None
    source_moved = False
    stage_moved = False
    recovery_required = False
    stage_expected_sha = None
    old_identity = None
    intent_path = None
    intent_identity = None
    intent_sha = None
    intent_committed = False
    try:
        _, _, _, pinned = cap._windows_pin_directory_path(
            Path(display).parent, purpose='source_mutation')
        _check_parent(Path(display).parent, pinned)
        if expected_sha256 is None:
            # CREATE_NEW refuses any concurrently introduced file or reparse point.
            stage_fd = cap._windows_create_private_file(io_path, delete_access=True)
            created_identity = cap._windows_file_identity(os.fstat(stage_fd))
            created_security = _security(stage_fd)
            try:
                if os.write(stage_fd, raw) != len(raw):
                    raise InputError('windows_source_partial_write')
                os.fsync(stage_fd)
            except Exception:
                # The exclusive CREATE_NEW handle owns the identity even when
                # a partial write made its bytes unknowable to the caller.
                _delete_owned_handle(stage_fd)
                created_identity = None
                raise
            os.close(stage_fd)
            stage_fd = None
            _check_parent(Path(display).parent, pinned)
            result_fd, result = _lease(io_path)
            try:
                if (cap._windows_file_identity(result) != created_identity
                        or _security(result_fd) != created_security
                        or os.read(result_fd, 2_000_001) != raw):
                    raise InputError('windows_source_creation_postcondition_recovery_required')
            finally:
                os.close(result_fd)
            return created_identity
        source_fd, before = _lease(io_path, pin_name=True)
        old_identity = cap._windows_file_identity(before)
        if expected_identity is not None and old_identity != expected_identity:
            raise InputError('windows_source_expected_identity_changed')
        content = os.read(source_fd, 2_000_001)
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise InputError('windows_source_concurrent_change')
        owner, descriptor = _security_snapshot(source_fd)
        security = _dacl_hash(descriptor)
        _, stage_io = cap._windows_absolute_path(stage_path)
        _, wintypes, kernel = cap._windows_api()
        kernel.CopyFileW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.BOOL)
        kernel.CopyFileW.restype = wintypes.BOOL
        if not kernel.CopyFileW(io_path, stage_io, True):
            raise InputError('windows_source_staging_copy_failed')
        stage_identity = cap._windows_file_identity(stage_path.lstat())
        stage_expected_sha = expected_sha256
        stage_fd = _open_stage_writer(stage_io, stage_identity)
        try:
            if os.write(stage_fd, raw) != len(raw):
                raise InputError('windows_source_staging_write_failed')
            os.fsync(stage_fd)
            stage_expected_sha = hashlib.sha256(raw).hexdigest()
        except Exception:
            _delete_owned_handle(stage_fd)
            stage_identity = None
            raise
        os.close(stage_fd)
        stage_fd = None
        # Prove this descriptor is reproducible before touching the source.
        # Inherited DACLs can be normalized by Windows and must fail closed.
        stage_acl_fd, _ = _lease(stage_io)
        try:
            _restore_dacl(stage_acl_fd, descriptor)
            if _security(stage_acl_fd) != (owner, security):
                raise InputError('windows_source_acl_not_reproducible')
        finally:
            os.close(stage_acl_fd)
        # The source name remains pinned against peer rename/delete until it
        # is moved by this exact handle. The stage rename never replaces a peer.
        _check_parent(Path(display).parent, pinned)
        if (_security(source_fd) != (owner, security)
                or cap._windows_file_identity(os.fstat(source_fd)) != old_identity):
            raise InputError('windows_source_identity_or_acl_changed')
        intent_path = _intent_path(path, expected_sha256,
                                   hashlib.sha256(raw).hexdigest(), repository_root)
        intent_identity, intent_sha = _write_intent(intent_path, {
            'kind': 'jev-reviewed-source-intent-v1', 'target': path.name,
            'old_sha256': expected_sha256, 'new_sha256': hashlib.sha256(raw).hexdigest(),
            'old_identity': list(old_identity), 'stage_identity': list(stage_identity),
            'stage': stage_path.name, 'backup': backup_path.name,
        })
        try:
            _rename_owned(source_fd, backup_path)
            source_moved = True
        except InputError:
            import msvcrt
            current_name = cap._windows_final_path(msvcrt.get_osfhandle(source_fd))
            if cap._windows_same_path(current_name, backup_path):
                source_moved = True
            elif not cap._windows_same_path(current_name, path):
                recovery_required = True
            raise
        stage_rename_fd, staged = _lease(stage_io, pin_name=True)
        try:
            if cap._windows_file_identity(staged) != stage_identity:
                raise InputError('windows_source_staging_identity_changed')
            try:
                _rename_owned(stage_rename_fd, path)
                stage_moved = True
            except InputError:
                import msvcrt
                current_name = cap._windows_final_path(msvcrt.get_osfhandle(stage_rename_fd))
                if cap._windows_same_path(current_name, path):
                    stage_moved = True
                elif not cap._windows_same_path(current_name, stage_path):
                    recovery_required = True
                raise
        finally:
            os.close(stage_rename_fd)
        result_fd, result = _lease(io_path)
        try:
            backup = os.stat(backup_path, follow_symlinks=False)
            if (cap._windows_file_identity(result) != stage_identity
                    or cap._windows_file_identity(backup) != cap._windows_file_identity(before)
                    or result.st_file_attributes != before.st_file_attributes
                    or hashlib.sha256(os.read(result_fd, 2_000_001)).digest()
                    != hashlib.sha256(raw).digest()):
                raise InputError('windows_source_replace_postcondition_recovery_required')
            # Native metadata operations can normalize ACL representation.
            # Restore and independently compare exact owner/DACL material.
            _restore_dacl(result_fd, descriptor)
            os.chmod(path, before.st_mode & 0o777)
            if (_security(result_fd) != (owner, security)
                    or os.fstat(result_fd).st_mode & 0o777 != before.st_mode & 0o777):
                raise InputError('windows_source_acl_postcondition_recovery_required')
            _check_parent(Path(display).parent, pinned)
        finally:
            os.close(result_fd)
        intent_sha = _commit_intent(intent_path, intent_identity, intent_sha)
        intent_committed = True
        os.close(source_fd)
        source_fd = None
        remove_owned_created(backup_path, old_identity, expected_sha256)
        remove_owned_created(intent_path, intent_identity, intent_sha)
        intent_identity = None
        return stage_identity
    except Exception as error:
        if intent_committed:
            recovery_required = True
            raise InputError('windows_source_committed_cleanup_required') from error
        if source_moved:
            # No name-based replace: a peer's new target is never overwritten.
            try:
                if stage_moved:
                    current_fd, current = _lease(io_path, pin_name=True)
                    try:
                        if (cap._windows_file_identity(current) != stage_identity
                                or hashlib.sha256(os.read(current_fd, 2_000_001)).digest()
                                != hashlib.sha256(raw).digest()):
                            raise InputError('windows_source_recovery_identity_changed')
                        _rename_owned(current_fd, stage_path)
                    finally:
                        os.close(current_fd)
                if source_fd is None:
                    _, backup_io = cap._windows_absolute_path(backup_path)
                    source_fd, backup = _lease(backup_io, pin_name=True)
                    if cap._windows_file_identity(backup) != old_identity:
                        raise InputError('windows_source_recovery_identity_changed')
                os.lseek(source_fd, 0, os.SEEK_SET)
                if (hashlib.sha256(os.read(source_fd, 2_000_001)).hexdigest()
                        != expected_sha256 or _security(source_fd) != (owner, security)):
                    raise InputError('windows_source_recovery_identity_changed')
                _rename_owned(source_fd, path)
                source_moved = False
                restored_fd, restored = _lease(io_path)
                try:
                    if (cap._windows_file_identity(restored) != old_identity
                            or restored.st_file_attributes != before.st_file_attributes
                            or os.fstat(restored_fd).st_mode & 0o777 != before.st_mode & 0o777
                            or hashlib.sha256(os.read(restored_fd, 2_000_001)).hexdigest()
                            != expected_sha256 or _security(restored_fd) != (owner, security)):
                        raise InputError('windows_source_recovery_postcondition_failed')
                finally:
                    os.close(restored_fd)
            except Exception as recovery_error:
                recovery_required = True
                raise InputError('windows_source_recovery_required') from recovery_error
        elif created_identity is not None and stage_fd is None:
            # A successful CREATE_NEW followed by a failed verification is
            # recoverable only while its exact owned bytes remain unchanged.
            try:
                remove_owned_created(path, created_identity,
                                     hashlib.sha256(raw).hexdigest())
            except Exception as recovery_error:
                raise InputError('windows_source_creation_recovery_required') from recovery_error
        if isinstance(error, (cap.CapabilityError, OSError)):
            raise InputError('windows_source_mutation_unavailable') from None
        raise
    finally:
        for fd in (stage_fd, source_fd):
            if fd is not None:
                os.close(fd)
        # Cleanup pins the actual identity; an unknown recovery state stays.
        if (not recovery_required and stage_identity is not None
                and stage_expected_sha is not None and stage_path.exists()):
            remove_owned_created(stage_path, stage_identity, stage_expected_sha)
        if (not recovery_required and intent_identity is not None
                and intent_sha is not None and intent_path is not None):
            remove_owned_created(intent_path, intent_identity, intent_sha)
        for fd in reversed(pinned):
            os.close(fd)
