"""Public-only native Windows authority for the independent Alpha fixture."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import ssl
import sys

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.windows_connected_verify import (
    cng_identity, verify_p256_sha256,
)
from .host import _native_acl_sha256


def _private_file(value: str, *, maximum: int) -> tuple[Path, bytes]:
    path = Path(value)
    expected = os.environ.get('REGISTERED_ALPHA_REFERENCE_ACL_SHA256')
    if (not path.is_absolute() or not expected or len(expected) != 64
            or any(character not in '0123456789abcdef' for character in expected)):
        raise RuntimeError('connected_private_reference_invalid')
    try:
        cap._windows_check_directory_path(path.parent, purpose='input')
        if (_native_acl_sha256(path.parent) != expected
                or _native_acl_sha256(path) != _native_acl_sha256(path.parent / 'delivery.lock')):
            raise RuntimeError('connected_private_reference_invalid')
        raw = cap._windows_secure_input(path, maximum)
        if _native_acl_sha256(path.parent) != expected:
            raise RuntimeError('connected_private_reference_invalid')
        return path, raw
    except (OSError, cap.CapabilityError):
        raise RuntimeError('connected_private_reference_invalid') from None


def _public_key() -> tuple[Path, bytes]:
    reference = os.environ.get('REGISTERED_ALPHA_AUTH_PUBKEY_FILE')
    expected = os.environ.get('REGISTERED_ALPHA_AUTH_PUBKEY_SHA256')
    if (not reference or not expected or len(expected) != 64
            or any(character not in '0123456789abcdef' for character in expected)):
        raise RuntimeError('connected_public_key_unanchored')
    key, raw = _private_file(reference, maximum=4096)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError('connected_public_key_changed')
    return key, raw


def current_environment_digest() -> str:
    cert = os.environ.get('SSL_CERT_FILE')
    cert_sha = None
    if cert is not None:
        cert_sha = hashlib.sha256(_private_file(cert, maximum=1_000_000)[1]).hexdigest()
    _, public = _public_key()
    verifier_path = Path(sys.modules[verify_p256_sha256.__module__].__file__)
    verifier = hashlib.sha256(cap._windows_secure_input(verifier_path, 1_000_000)).hexdigest()
    return digest({'python': str(Path(sys.executable).resolve()),
                   'version': list(sys.version_info[:3]),
                   'implementation': platform.python_implementation(),
                   'openssl': ssl.OPENSSL_VERSION,
                   'signature_verifier_sha256': verifier,
                   'cng': cng_identity(),
                   'public_key_sha256': hashlib.sha256(public).hexdigest(),
                   'cert_sha256': cert_sha,
                   'credential_present': bool(os.environ.get('TYPESAFE_API_KEY'))})


def options() -> dict:
    reference = os.environ.get('REGISTERED_ALPHA_CONNECTED_REF')
    if reference is None:
        return {}
    reference_hash = os.environ.get('REGISTERED_ALPHA_CONNECTED_REF_SHA256')
    if not reference_hash or len(reference_hash) != 64:
        raise RuntimeError('connected_reference_unanchored')
    reference_path, reference_bytes = _private_file(reference, maximum=256_000)
    if hashlib.sha256(reference_bytes).hexdigest() != reference_hash:
        raise RuntimeError('connected_reference_changed')
    manifest = json.loads(reference_bytes)
    if (type(manifest) is not dict or set(manifest) !=
            {'schema_version', 'mode', 'connected_config', 'authority',
             'ledger_path', 'signatures'}
            or manifest['schema_version'] != '1.0' or manifest['mode'] != 'shadow'
            or type(manifest['signatures']) is not dict):
        raise RuntimeError('connected_private_reference_invalid')
    key_path, key_bytes = _public_key()
    ledger = Path(manifest['ledger_path'])
    expected_acl = os.environ.get('REGISTERED_ALPHA_OBSERVATION_ACL_SHA256')
    if (not ledger.is_absolute() or not expected_acl
            or _native_acl_sha256(ledger.parent) != expected_acl):
        raise RuntimeError('connected_ledger_path_invalid')

    def verify_authority(kind: str, exact_digest: str) -> bool:
        if (type(kind) is not str or type(exact_digest) is not str
                or kind not in ('installed_binding', 'egress_grant', 'activation',
                                'gate_0', 'gate_1', 'deployment_grant')
                or len(exact_digest) != 64):
            return False
        try:
            current = _private_file(str(reference_path), maximum=256_000)[1]
            if hashlib.sha256(current).hexdigest() != reference_hash:
                return False
            current_manifest = json.loads(current)
            if (type(current_manifest) is not dict
                    or current_manifest.get('mode') != 'shadow'
                    or current_manifest.get('connected_config') != manifest['connected_config']
                    or current_manifest.get('authority') != manifest['authority']
                    or current_manifest.get('ledger_path') != manifest['ledger_path']
                    or type(current_manifest.get('signatures')) is not dict):
                return False
            signature = current_manifest['signatures'].get(kind)
            if type(signature) is not str or len(signature) > 8192:
                return False
            if (_public_key() != (key_path, key_bytes)
                    or _native_acl_sha256(ledger.parent) != expected_acl):
                return False
            raw = base64.b64decode(signature, validate=True)
            return verify_p256_sha256(key_bytes,
                                      (kind + ':' + exact_digest).encode('ascii'), raw)
        except (OSError, ValueError, RuntimeError, cap.CapabilityError):
            return False

    return {'startup_mode': 'shadow', 'connected_config': manifest['connected_config'],
            'authority': manifest['authority'], 'verify_authority': verify_authority,
            'current_environment_digest': current_environment_digest,
            'ledger_path': ledger}
