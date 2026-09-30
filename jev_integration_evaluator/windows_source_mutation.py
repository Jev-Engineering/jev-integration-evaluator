"""Guarded NTFS replacement for reviewed source; no target execution.

Directory handles pin the lexical ancestors. An existing source lease denies
concurrent data writers. ReplaceFileW retains named streams; the DACL is
restored and checked from the reviewed source handle.
An unexpected replacement identity retains the backup for explicit recovery.
"""
from __future__ import annotations

import hashlib
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


def _lease(io_path: str):
    import ctypes
    import msvcrt

    _, wintypes, kernel = cap._windows_api()
    # Deny data writers while allowing the replace operation's DELETE access.
    handle = kernel.CreateFileW(io_path, 0x80000000 | 0x00020000 | 0x00040000,
                                1 | 4, None, 3, 0x00200000, None)
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
            value = ctypes.c_uint32(1)
            kernel.SetFileInformationByHandle.argtypes = (
                wintypes.HANDLE, wintypes.INT, ctypes.c_void_p, wintypes.DWORD)
            kernel.SetFileInformationByHandle.restype = wintypes.BOOL
            if not kernel.SetFileInformationByHandle(msvcrt.get_osfhandle(fd), 4,
                                                      ctypes.byref(value), ctypes.sizeof(value)):
                raise InputError('windows_source_owned_delete_failed')
        finally:
            os.close(fd)
    finally:
        for fd in reversed(pinned):
            os.close(fd)


def write_reviewed_text(path: Path, text: str, expected_sha256: str | None,
                        *, expected_identity: tuple[int, int] | None = None) -> tuple[int, int]:
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
    pinned = []
    source_fd = stage_fd = None
    stage_path = Path(display).with_name('.jev-source-' + uuid.uuid4().hex)
    backup_path = stage_path.with_suffix('.backup')
    stage_identity = None
    created_identity = None
    replacement_effect = False
    old_identity = None
    try:
        _, _, _, pinned = cap._windows_pin_directory_path(
            Path(display).parent, purpose='source_mutation')
        _check_parent(Path(display).parent, pinned)
        if expected_sha256 is None:
            # CREATE_NEW refuses any concurrently introduced file or reparse point.
            stage_fd = cap._windows_create_private_file(io_path)
            created_identity = cap._windows_file_identity(os.fstat(stage_fd))
            created_security = _security(stage_fd)
            if os.write(stage_fd, raw) != len(raw):
                raise InputError('windows_source_partial_write_recovery_required')
            os.fsync(stage_fd)
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
        source_fd, before = _lease(io_path)
        old_identity = cap._windows_file_identity(before)
        if expected_identity is not None and old_identity != expected_identity:
            raise InputError('windows_source_expected_identity_changed')
        content = os.read(source_fd, 2_000_001)
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise InputError('windows_source_concurrent_change')
        owner, descriptor = _security_snapshot(source_fd)
        security = _dacl_hash(descriptor)
        _, stage_io = cap._windows_absolute_path(stage_path)
        stage_fd = cap._windows_create_private_file(stage_io)
        stage_identity = cap._windows_file_identity(os.fstat(stage_fd))
        if _security(stage_fd)[0] != owner:
            raise InputError('windows_source_owner_not_supported')
        if os.write(stage_fd, raw) != len(raw):
            raise InputError('windows_source_staging_write_failed')
        os.fsync(stage_fd)
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
        # Refuse a renamed/replaced source before invoking the native replacement.
        _check_parent(Path(display).parent, pinned)
        current_fd, current = _lease(io_path)
        try:
            if (cap._windows_file_identity(current) != cap._windows_file_identity(before)
                    or _security(current_fd) != (owner, security)):
                raise InputError('windows_source_identity_or_acl_changed')
        finally:
            os.close(current_fd)
        _, _, kernel = cap._windows_api()
        kernel.ReplaceFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p,
                                        ctypes.c_wchar_p, ctypes.c_uint32,
                                        ctypes.c_void_p, ctypes.c_void_p)
        kernel.ReplaceFileW.restype = ctypes.c_int
        _, backup_io = cap._windows_absolute_path(backup_path)
        if not kernel.ReplaceFileW(io_path, stage_io, backup_io, 0, None, None):
            raise InputError('windows_source_replace_failed_recovery_required')
        replacement_effect = True
        result_fd, result = _lease(io_path)
        try:
            backup = os.stat(backup_path, follow_symlinks=False)
            if (cap._windows_file_identity(result) != stage_identity
                    or cap._windows_file_identity(backup) != cap._windows_file_identity(before)
                    or result.st_file_attributes != before.st_file_attributes
                    or hashlib.sha256(os.read(result_fd, 2_000_001)).digest()
                    != hashlib.sha256(raw).digest()):
                raise InputError('windows_source_replace_postcondition_recovery_required')
            # Windows can normalize OWNER_RIGHTS ACEs during replacement. Restore
            # the exact retained DACL on the verified replacement handle, then
            # independently compare the complete owner/DACL descriptor bytes.
            _restore_dacl(result_fd, descriptor)
            os.chmod(path, before.st_mode & 0o777)
            if (_security(result_fd) != (owner, security)
                    or os.fstat(result_fd).st_mode & 0o777 != before.st_mode & 0o777):
                raise InputError('windows_source_acl_postcondition_recovery_required')
            _check_parent(Path(display).parent, pinned)
        finally:
            os.close(result_fd)
        backup_path.unlink()
        return stage_identity
    except Exception as error:
        if replacement_effect:
            # Only restore when both names still designate the identities we own.
            # An unknown state keeps the original backup for explicit recovery.
            try:
                if source_fd is not None:
                    os.close(source_fd)
                    source_fd = None
                if (_identity_at(io_path) != stage_identity
                        or cap._windows_file_identity(backup_path.lstat()) != old_identity):
                    raise InputError('windows_source_recovery_identity_changed')
                _, backup_io = cap._windows_absolute_path(backup_path)
                _, stage_io = cap._windows_absolute_path(stage_path)
                if not kernel.ReplaceFileW(io_path, backup_io, stage_io, 0, None, None):
                    raise InputError('windows_source_recovery_replace_failed')
                if _identity_at(io_path) != old_identity:
                    raise InputError('windows_source_recovery_postcondition_failed')
                restored_fd, restored = _lease(io_path)
                try:
                    _restore_dacl(restored_fd, descriptor)
                    os.chmod(path, before.st_mode & 0o777)
                    if (restored.st_file_attributes != before.st_file_attributes
                            or os.fstat(restored_fd).st_mode & 0o777 != before.st_mode & 0o777
                            or hashlib.sha256(os.read(restored_fd, 2_000_001)).hexdigest()
                            != expected_sha256 or _security(restored_fd) != (owner, security)):
                        raise InputError('windows_source_recovery_postcondition_failed')
                finally:
                    os.close(restored_fd)
            except Exception as recovery_error:
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
        # Remove only our retained staging identity. Unknown backup states stay.
        if stage_identity is not None and stage_path.exists():
            info = stage_path.lstat()
            if (not cap._windows_reparse_reason(info) and info.st_nlink == 1
                    and cap._windows_file_identity(info) == stage_identity):
                stage_path.unlink()
        for fd in reversed(pinned):
            os.close(fd)
