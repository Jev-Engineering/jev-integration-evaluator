"""NTFS owner-only artifacts and cross-process locks for native delivery."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Iterator

from . import capabilities as cap
from .io import InputError
from .windows_template_preflight import _profile


def generation_root_present(path: str | Path) -> bool:
    """Distinguish an absent generation from a dangling NTFS reparse point."""
    _profile()
    target = Path(path)
    try:
        cap._windows_check_directory_path(target.parent, purpose='output')
    except (cap.CapabilityError, OSError):
        raise InputError('windows_owned_generation_parent_unavailable') from None
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return False
    except OSError:
        raise InputError('windows_owned_generation_unavailable') from None
    if cap._windows_reparse_reason(info) or not stat.S_ISDIR(info.st_mode):
        raise InputError('windows_owned_generation_reparse_or_non_directory')
    return True


def _security_descriptor():
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD))
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor = ctypes.c_void_p()
    size = wintypes.DWORD()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            'D:P(A;OICI;FA;;;OW)', 1, ctypes.byref(descriptor), ctypes.byref(size)):
        raise InputError('windows_owner_private_acl_unavailable')
    return ctypes, wintypes, advapi, kernel, descriptor


def acl_sha256(path: str | Path) -> str:
    """Hash the current owner and protected DACL bytes for later exact recheck."""
    _profile()
    import ctypes
    from ctypes import wintypes

    display, _ = cap._windows_absolute_path(path)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    advapi.GetFileSecurityW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD))
    advapi.GetFileSecurityW.restype = wintypes.BOOL
    required = wintypes.DWORD()
    flags = 0x00000001 | 0x00000004  # owner and DACL, including descriptor control bits
    advapi.GetFileSecurityW(display, flags, None, 0, ctypes.byref(required))
    if required.value == 0 or required.value > 65_536:
        raise InputError('windows_owned_acl_unavailable')
    buffer = ctypes.create_string_buffer(required.value)
    if not advapi.GetFileSecurityW(display, flags, buffer, len(buffer), ctypes.byref(required)):
        raise InputError('windows_owned_acl_unavailable')
    return hashlib.sha256(buffer.raw[:required.value]).hexdigest()


def create_private_directory(path: str | Path) -> dict:
    """Exclusively create a protected owner-only directory under a pinned NTFS parent."""
    _profile()
    import ctypes

    target = Path(path)
    display, io_path = cap._windows_absolute_path(target)
    if target.exists():
        raise InputError('windows_owned_directory_already_exists')
    _, _, _, pinned = cap._windows_pin_directory_path(target.parent, purpose='output')
    try:
        ctypes, wintypes, _, kernel, descriptor = _security_descriptor()

        class SecurityAttributes(ctypes.Structure):
            _fields_ = [('nLength', wintypes.DWORD),
                        ('lpSecurityDescriptor', ctypes.c_void_p),
                        ('bInheritHandle', wintypes.BOOL)]

        security = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        kernel.CreateDirectoryW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(SecurityAttributes))
        kernel.CreateDirectoryW.restype = wintypes.BOOL
        try:
            if not kernel.CreateDirectoryW(io_path, ctypes.byref(security)):
                error = ctypes.get_last_error()
                if error in (80, 183):
                    raise InputError('windows_owned_directory_already_exists')
                raise InputError('windows_owned_directory_create_failed')
        finally:
            kernel.LocalFree(descriptor)
        _, _, final = cap._windows_check_directory_path(display, purpose='output')
        if not cap._windows_same_path(final, io_path):
            raise InputError('windows_owned_directory_identity_changed')
        fd, info, final, identity = cap._windows_open_directory(io_path)
        try:
            if not cap._windows_same_path(final, io_path):
                raise InputError('windows_owned_directory_identity_changed')
            lock = Path(display) / 'delivery.lock'
            _, lock_io = cap._windows_absolute_path(lock)
            lock_fd = cap._windows_create_private_file(lock_io)
            try:
                os.write(lock_fd, b'0')
                os.fsync(lock_fd)
            finally:
                os.close(lock_fd)
            return {'path': display, 'volume_id': identity[0], 'file_id': identity[1],
                    'acl_sha256': acl_sha256(display),
                    'lock_acl_sha256': acl_sha256(lock)}
        finally:
            os.close(fd)
    except cap.CapabilityError as exc:
        raise InputError('windows_owned_' + exc.code) from None
    finally:
        for fd in reversed(pinned):
            os.close(fd)


def check_private_directory(receipt: dict) -> None:
    """Reject replacement or ACL drift of an existing exclusively owned directory."""
    _profile()
    if (type(receipt) is not dict or set(receipt) !=
            {'path', 'volume_id', 'file_id', 'acl_sha256', 'lock_acl_sha256'}):
        raise InputError('windows_owned_directory_receipt_invalid')
    try:
        _, io_path, final = cap._windows_check_directory_path(receipt['path'], purpose='output')
        fd, _, current, identity = cap._windows_open_directory(io_path)
        try:
            if (not cap._windows_same_path(final, current)
                    or identity != (receipt['volume_id'], receipt['file_id'])
                    or acl_sha256(receipt['path']) != receipt['acl_sha256']):
                raise InputError('windows_owned_directory_changed')
        finally:
            os.close(fd)
    except (cap.CapabilityError, OSError):
        raise InputError('windows_owned_directory_changed') from None


@contextmanager
def locked_private_directory(receipt: dict) -> Iterator[Path]:
    """Lock one owner directory across processes without following a lock link."""
    _profile()
    import msvcrt

    check_private_directory(receipt)
    root = Path(receipt['path'])
    lock = root / 'delivery.lock'
    if lock.exists() and (lock.is_symlink() or lock.stat().st_nlink != 1):
        raise InputError('windows_owned_lock_invalid')
    if not lock.exists():
        raise InputError('windows_owned_lock_unavailable')
    try:
        stream = lock.open('r+b')
    except OSError:
        raise InputError('windows_owned_lock_busy') from None
    with stream:
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise InputError('windows_owned_lock_busy') from None
        try:
            stream.seek(0)
            if stream.read(2) != b'0':
                raise InputError('windows_owned_lock_invalid')
            stream.seek(0)
            if acl_sha256(lock) != receipt['lock_acl_sha256']:
                raise InputError('windows_owned_lock_acl_changed')
            check_private_directory(receipt)
            yield root
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _record_limit(name: str) -> int:
    # Python 3.10 venvs include pip and setuptools by default. Their complete
    # file and ACL inventory can exceed 1 MB without exceeding schema bounds.
    return 4_000_000 if name == 'install-receipt.json' else 1_000_000


def write_private_json_exclusive(receipt: dict, name: str, value: dict) -> str:
    """Write one bounded canonical JSON event under the held owner directory lock."""
    _profile()
    if (type(name) is not str or not cap._windows_safe_component(name)
            or '/' in name or '\\' in name or type(value) is not dict):
        raise InputError('windows_owned_record_invalid')
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')) + '\n').encode('utf-8')
    if len(raw) > _record_limit(name):
        raise InputError('windows_owned_record_size_limit')
    return write_private_bytes_exclusive(receipt, name, raw)


def write_private_bytes_exclusive(receipt: dict, name: str, raw: bytes) -> str:
    """Create one owner-only bounded file, fsync it, and recheck exact bytes."""
    _profile()
    if (type(name) is not str or not cap._windows_safe_component(name)
            or '/' in name or '\\' in name or type(raw) is not bytes
            or len(raw) > _record_limit(name)):
        raise InputError('windows_owned_record_invalid')
    with locked_private_directory(receipt) as root:
        target = root / name
        _, io_path = cap._windows_absolute_path(target)
        try:
            fd = cap._windows_create_private_file(io_path)
        except OSError:
            raise InputError('windows_owned_record_exists_or_unavailable') from None
        try:
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise InputError('windows_owned_record_write_failed')
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        if (cap._windows_secure_input(target, _record_limit(name)) != raw
                or acl_sha256(target) != receipt['lock_acl_sha256']):
            raise InputError('windows_owned_record_write_unverified')
        return hashlib.sha256(raw).hexdigest()


def read_private_json(receipt: dict, name: str) -> dict:
    """Read one identity and ACL checked owner record without executing code."""
    _profile()
    if type(name) is not str or not cap._windows_safe_component(name) or '/' in name or '\\' in name:
        raise InputError('windows_owned_record_invalid')
    check_private_directory(receipt)
    path = Path(receipt['path']) / name
    try:
        if acl_sha256(path) != receipt['lock_acl_sha256']:
            raise InputError('windows_owned_record_acl_changed')
        raw = cap._windows_secure_input(path, _record_limit(name))
        value = json.loads(raw)
        if type(value) is not dict:
            raise ValueError('record')
        check_private_directory(receipt)
        return value
    except cap.CapabilityError:
        raise InputError('windows_owned_record_unavailable') from None
    except InputError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise InputError('windows_owned_record_unavailable') from None
