"""Host-owned connected startup boundary for the independent Alpha 1.0.2 fixture.

The private files are provisioned by a separate owner. This module checks their
ownership and authenticates exact digest grants; a descriptor hash is not a
grant. It never logs or returns credential values.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import platform
import ssl
import stat
import sys

from jev_integration_evaluator.io import digest


def _private_file(value: str, *, maximum: int) -> Path:
    path = Path(value)
    if (not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents))
            or not path.is_file()):
        raise RuntimeError('connected_private_reference_invalid')
    info = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077
            or info.st_size > maximum):
        raise RuntimeError('connected_private_reference_invalid')
    parent = path.parent.stat()
    if (parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077):
        raise RuntimeError('connected_private_reference_invalid')
    return path


def current_environment_digest() -> str:
    """Recompute code-owned runtime facts on every lifecycle check."""
    cert = os.environ.get('SSL_CERT_FILE')
    cert_sha = None
    if cert is not None:
        cert_sha = hashlib.sha256(_private_file(cert, maximum=1_000_000).read_bytes()).hexdigest()
    return digest({'python': str(Path(sys.executable).resolve()),
                   'version': list(sys.version_info[:3]),
                   'implementation': platform.python_implementation(),
                   'openssl': ssl.OPENSSL_VERSION,
                   'cert_sha256': cert_sha,
                   'credential_present': bool(os.environ.get('TYPESAFE_API_KEY'))})


def options() -> dict:
    reference = os.environ.get('REGISTERED_ALPHA_CONNECTED_REF')
    if reference is None:
        return {}
    manifest = json.loads(_private_file(reference, maximum=256_000).read_text(encoding='utf-8'))
    if (type(manifest) is not dict or set(manifest) !=
            {'schema_version', 'mode', 'connected_config', 'authority',
             'ledger_path', 'signatures'}
            or manifest['schema_version'] != '1.0' or manifest['mode'] != 'shadow'
            or type(manifest['signatures']) is not dict):
        raise RuntimeError('connected_private_reference_invalid')
    key_reference = os.environ.get('REGISTERED_ALPHA_AUTH_KEY_FILE')
    if not key_reference:
        raise RuntimeError('connected_authority_key_invalid')
    key_file = _private_file(key_reference, maximum=4096)
    key = key_file.read_bytes()
    if len(key) < 32:
        raise RuntimeError('connected_authority_key_invalid')
    ledger = Path(manifest['ledger_path'])
    if (not ledger.is_absolute() or any(part.is_symlink() for part in (ledger, *ledger.parents))
            or ledger.parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(ledger.parent.stat().st_mode) & 0o077):
        raise RuntimeError('connected_ledger_path_invalid')

    def verify_authority(kind: str, exact_digest: str) -> bool:
        if type(kind) is not str or type(exact_digest) is not str:
            return False
        # Reread the owner-private manifest so revocation takes effect during
        # an existing process, before every route and every provider attempt.
        current = json.loads(_private_file(reference, maximum=256_000).read_text(encoding='utf-8'))
        if (type(current) is not dict or current.get('mode') != 'shadow'
                or current.get('connected_config') != manifest['connected_config']
                or current.get('authority') != manifest['authority']
                or current.get('ledger_path') != manifest['ledger_path']
                or os.environ.get('REGISTERED_ALPHA_AUTH_KEY_FILE') != key_reference
                or type(current.get('signatures')) is not dict):
            return False
        signature = current['signatures'].get(kind)
        if type(signature) is not str:
            return False
        message = (kind + ':' + exact_digest).encode('ascii', errors='strict')
        expected = hmac.new(_private_file(key_reference, maximum=4096).read_bytes(),
                            message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    return {'startup_mode': 'shadow', 'connected_config': manifest['connected_config'],
            'authority': manifest['authority'], 'verify_authority': verify_authority,
            'current_environment_digest': current_environment_digest,
            'ledger_path': ledger}
