"""Host-owned connected startup boundary for the independent D retrieval fixture.

The private files are provisioned by a separate owner. This module checks their
ownership and authenticates exact digest grants; a descriptor hash is not a
grant. It never logs or returns credential values.
"""
from __future__ import annotations

import hashlib
import base64
import json
import os
from pathlib import Path
import platform
import ssl
import stat
import subprocess
import sys
import tempfile

from jev_integration_evaluator.io import digest


OPENSSL = Path('/usr/bin/openssl')
OPENSSL_ENV = {'LANG': 'C', 'OPENSSL_CONF': os.devnull,
               'OPENSSL_MODULES': '/nonexistent', 'OPENSSL_ENGINES': '/nonexistent'}


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


def _public_key() -> Path:
    reference = os.environ.get('D_AUTH_PUBKEY_FILE')
    expected = os.environ.get('D_AUTH_PUBKEY_SHA256')
    if (not reference or not expected or len(expected) != 64
            or any(character not in '0123456789abcdef' for character in expected)):
        raise RuntimeError('connected_public_key_unanchored')
    key = _private_file(reference, maximum=4096)
    if hashlib.sha256(key.read_bytes()).hexdigest() != expected:
        raise RuntimeError('connected_public_key_changed')
    return key


def _openssl_identity() -> dict:
    info = OPENSSL.stat()
    if (OPENSSL.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) & 0o022):
        raise RuntimeError('connected_verifier_invalid')
    version = subprocess.run([str(OPENSSL), 'version'], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2,
        env=OPENSSL_ENV, check=False)
    if (version.returncode != 0 or len(version.stdout) > 256
            or not version.stdout.startswith(b'OpenSSL 3.')):
        raise RuntimeError('connected_verifier_invalid')
    return {'path': str(OPENSSL), 'sha256': hashlib.sha256(OPENSSL.read_bytes()).hexdigest(),
            'version': version.stdout.decode('ascii').strip()}


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
                   'signature_verifier': _openssl_identity(),
                   'public_key_sha256': hashlib.sha256(_public_key().read_bytes()).hexdigest(),
                   'cert_sha256': cert_sha,
                   'credential_present': bool(os.environ.get('TYPESAFE_API_KEY'))})


def options() -> dict:
    reference = os.environ.get('D_CONNECTED_REF')
    if reference is None:
        return {}
    reference_hash = os.environ.get('D_CONNECTED_REF_SHA256')
    if not reference_hash or len(reference_hash) != 64:
        raise RuntimeError('connected_reference_unanchored')
    reference_path = _private_file(reference, maximum=256_000)
    if hashlib.sha256(reference_path.read_bytes()).hexdigest() != reference_hash:
        raise RuntimeError('connected_reference_changed')
    manifest = json.loads(reference_path.read_text(encoding='utf-8'))
    if (type(manifest) is not dict or set(manifest) !=
            {'schema_version', 'mode', 'connected_config', 'authority',
             'ledger_path', 'signatures'}
            or manifest['schema_version'] != '1.0' or manifest['mode'] != 'shadow'
            or type(manifest['signatures']) is not dict):
        raise RuntimeError('connected_private_reference_invalid')
    key_file = _public_key()
    verifier_identity = _openssl_identity()
    ledger = Path(manifest['ledger_path'])
    if (not ledger.is_absolute() or any(part.is_symlink() for part in (ledger, *ledger.parents))
            or ledger.parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(ledger.parent.stat().st_mode) & 0o077):
        raise RuntimeError('connected_ledger_path_invalid')

    def verify_authority(kind: str, exact_digest: str) -> bool:
        if (type(kind) is not str or type(exact_digest) is not str
                or kind not in ('installed_binding', 'egress_grant', 'activation',
                                'gate_0', 'gate_1', 'deployment_grant')
                or len(exact_digest) != 64):
            return False
        # Reread the owner-private manifest so revocation takes effect during
        # an existing process, before every route and every provider attempt.
        current_bytes = _private_file(reference, maximum=256_000).read_bytes()
        if hashlib.sha256(current_bytes).hexdigest() != reference_hash:
            return False
        current = json.loads(current_bytes)
        if (type(current) is not dict or current.get('mode') != 'shadow'
                or current.get('connected_config') != manifest['connected_config']
                or current.get('authority') != manifest['authority']
                or current.get('ledger_path') != manifest['ledger_path']
                or type(current.get('signatures')) is not dict):
            return False
        signature = current['signatures'].get(kind)
        if type(signature) is not str or len(signature) > 8192:
            return False
        try:
            if (_public_key() != key_file or _openssl_identity() != verifier_identity):
                return False
            raw = base64.b64decode(signature, validate=True)
            with tempfile.TemporaryFile(mode='w+b') as signature_file:
                signature_file.write(raw)
                signature_file.flush()
                verification = subprocess.run(
                    [str(OPENSSL), 'dgst', '-sha256', '-verify', str(key_file),
                     '-signature', f'/proc/self/fd/{signature_file.fileno()}'],
                    input=(kind + ':' + exact_digest).encode('ascii'),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    pass_fds=(signature_file.fileno(),), timeout=2,
                    env=OPENSSL_ENV, check=False)
            return verification.returncode == 0
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
            return False

    return {'startup_mode': 'shadow', 'connected_config': manifest['connected_config'],
            'authority': manifest['authority'], 'verify_authority': verify_authority,
            'current_environment_digest': current_environment_digest,
            'ledger_path': ledger}
