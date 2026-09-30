"""Public-only P-256 signature verification through native Windows CNG.

The child receives an externally pinned public key and signature only.  This
module cannot issue grants and never opens an issuer private key.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import re
import stat

from . import capabilities as cap
from .windows_template_owned import acl_sha256


_SPKI_PREFIX = bytes.fromhex(
    '3059'  # SEQUENCE, 89 bytes
    '3013'  # algorithm identifier
    '06072a8648ce3d0201'  # id-ecPublicKey
    '06082a8648ce3d030107'  # prime256v1
    '03420004'  # BIT STRING with uncompressed point
)


def cng_identity() -> dict:
    """Bind the fixed OS verifier DLL without trusting the child working directory."""
    root = Path(os.environ['SystemRoot'])
    path = root / 'System32' / 'bcrypt.dll'
    cap._windows_check_directory_path(path.parent, purpose='input')
    before = os.lstat(path)
    if (cap._windows_reparse_reason(before) or not stat.S_ISREG(before.st_mode)
            or not 1 <= before.st_size <= 2_000_000):
        raise ValueError('cng_origin_invalid')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if cap._windows_file_identity(opened) != cap._windows_file_identity(before):
            raise ValueError('cng_origin_changed')
        raw = stream.read(2_000_001)
        if len(raw) > 2_000_000 or cap._windows_file_identity(os.fstat(
                stream.fileno())) != cap._windows_file_identity(before):
            raise ValueError('cng_origin_changed')
    if cap._windows_file_identity(os.lstat(path)) != cap._windows_file_identity(before):
        raise ValueError('cng_origin_changed')
    volume, file_id = cap._windows_file_identity(before)
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
            'volume_id': volume, 'file_id': file_id,
            'nlink': before.st_nlink, 'acl_sha256': acl_sha256(path)}


def _public_point(pem: bytes) -> bytes:
    if len(pem) > 4096:
        raise ValueError('public_key_size')
    match = re.fullmatch(
        rb'-----BEGIN PUBLIC KEY-----\r?\n([A-Za-z0-9+/=\r\n]+)'
        rb'-----END PUBLIC KEY-----\r?\n?', pem)
    if match is None:
        raise ValueError('public_key_format')
    der = base64.b64decode(re.sub(rb'\s+', b'', match[1]), validate=True)
    if len(der) != len(_SPKI_PREFIX) + 64 or not der.startswith(_SPKI_PREFIX):
        raise ValueError('public_key_curve')
    return der[len(_SPKI_PREFIX):]


def _der_integer(raw: bytes, index: int) -> tuple[bytes, int]:
    if index + 2 > len(raw) or raw[index] != 2:
        raise ValueError('signature_format')
    size = raw[index + 1]
    end = index + 2 + size
    value = raw[index + 2:end]
    if (size < 1 or size > 33 or end > len(raw) or
            (value[0] == 0 and (len(value) == 1 or value[1] < 0x80)) or
            (value[0] != 0 and value[0] & 0x80)):
        raise ValueError('signature_format')
    if value[0] == 0:
        value = value[1:]
    if len(value) > 32:
        raise ValueError('signature_format')
    return value.rjust(32, b'\0'), end


def _signature_rs(der: bytes) -> bytes:
    if (len(der) > 72 or len(der) < 8 or der[0] != 0x30 or
            der[1] != len(der) - 2):
        raise ValueError('signature_format')
    r, end = _der_integer(der, 2)
    s, end = _der_integer(der, end)
    if end != len(der):
        raise ValueError('signature_format')
    return r + s


def verify_p256_sha256(public_pem: bytes, message: bytes, signature_der: bytes) -> bool:
    """Verify one canonical public P-256 ECDSA grant; fail closed on CNG errors."""
    if (type(message) is not bytes or len(message) > 256 or
            type(signature_der) is not bytes):
        return False
    try:
        point = _public_point(public_pem)
        signature = _signature_rs(signature_der)
    except (ValueError, base64.binascii.Error):
        return False
    try:
        bcrypt = ctypes.WinDLL(cng_identity()['path'], use_last_error=True)
        bcrypt.BCryptOpenAlgorithmProvider.argtypes = (
            ctypes.POINTER(ctypes.c_void_p), wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.ULONG)
        bcrypt.BCryptOpenAlgorithmProvider.restype = wintypes.LONG
        bcrypt.BCryptImportKeyPair.argtypes = (
            ctypes.c_void_p, ctypes.c_void_p, wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wintypes.ULONG,
            wintypes.ULONG)
        bcrypt.BCryptImportKeyPair.restype = wintypes.LONG
        bcrypt.BCryptVerifySignature.argtypes = (
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG,
            ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG)
        bcrypt.BCryptVerifySignature.restype = wintypes.LONG
        bcrypt.BCryptDestroyKey.argtypes = (ctypes.c_void_p,)
        bcrypt.BCryptDestroyKey.restype = wintypes.LONG
        bcrypt.BCryptCloseAlgorithmProvider.argtypes = (ctypes.c_void_p, wintypes.ULONG)
        bcrypt.BCryptCloseAlgorithmProvider.restype = wintypes.LONG
        provider = ctypes.c_void_p()
        key = ctypes.c_void_p()
        if bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(provider), 'ECDSA_P256', None, 0):
            return False
        try:
            # BCRYPT_ECCPUBLIC_BLOB: BCRYPT_ECCKEY_BLOB {ECS1, cbKey=32}, X, Y.
            blob = (0x31534345).to_bytes(4, 'little') + (32).to_bytes(4, 'little') + point
            blob_buffer = ctypes.create_string_buffer(blob)
            if bcrypt.BCryptImportKeyPair(provider, None, 'ECCPUBLICBLOB',
                                         ctypes.byref(key), blob_buffer, len(blob), 0):
                return False
            try:
                hashed = ctypes.create_string_buffer(hashlib.sha256(message).digest())
                signed = ctypes.create_string_buffer(signature)
                return bcrypt.BCryptVerifySignature(
                    key, None, hashed, 32, signed, len(signature), 0) == 0
            finally:
                bcrypt.BCryptDestroyKey(key)
        finally:
            bcrypt.BCryptCloseAlgorithmProvider(provider, 0)
    except (OSError, AttributeError, ValueError):
        return False
