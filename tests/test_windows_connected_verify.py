"""Public-only Windows CNG verifier agrees with a separate synthetic issuer."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from datetime import datetime, timedelta, timezone
import hashlib
import base64

import pytest

from jev_integration_evaluator.windows_connected_verify import verify_p256_sha256
from jev_integration_evaluator.windows_template_connected_delivery import (
    WindowsConnectedDeliveryError, _scope,
)
from jev_integration_evaluator.io import digest


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native Windows CNG only')
_ISSUER = Path(r'C:\Program Files\Git\usr\bin\openssl.exe')


def test_native_cng_checks_exact_p256_message_without_issuer_key(tmp_path):
    issuer = _ISSUER
    assert issuer.is_file(), 'Declared synthetic issuer tooling absent'
    private = tmp_path / 'issuer-private.pem'
    public = tmp_path / 'issuer-public.pem'
    commands = ([str(issuer), 'genpkey', '-algorithm', 'EC', '-pkeyopt',
                 'ec_paramgen_curve:P-256', '-out', str(private)],
                [str(issuer), 'pkey', '-in', str(private), '-pubout', '-out', str(public)])
    for command in commands:
        issued = subprocess.run(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=10, check=False)
        assert issued.returncode == 0
    message = b'installed_binding:' + b'a' * 64
    signed = subprocess.run([str(issuer), 'dgst', '-sha256', '-sign', str(private)],
                            input=message, capture_output=True, timeout=10, check=False)
    assert signed.returncode == 0
    key = public.read_bytes()
    assert verify_p256_sha256(key, message, signed.stdout)
    assert not verify_p256_sha256(key, message + b'b', signed.stdout)
    assert not verify_p256_sha256(key, message, signed.stdout[:-1])
    assert not verify_p256_sha256(b'changed-key', message, signed.stdout)


def test_native_scope_requires_exact_signature_and_live_expiry(tmp_path):
    assert _ISSUER.is_file(), 'Declared synthetic issuer tooling absent'
    private = tmp_path / 'private.pem'
    public = tmp_path / 'public.pem'
    for command in ([str(_ISSUER), 'genpkey', '-algorithm', 'EC',
                     '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', str(private)],
                    [str(_ISSUER), 'pkey', '-in', str(private), '-pubout', '-out', str(public)]):
        assert subprocess.run(command, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=10).returncode == 0
    key = public.read_bytes()
    body = {'schema_version': '1.0', 'kind': 'windows-connected-delivery-scope-v1',
            'run_id': '5ca21dd9-d9f5-49ec-b1e4-0beab34bfd7e',
            'plan_sha256': 'a' * 64, 'session_sha256': 'b' * 64,
            'public_key_sha256': hashlib.sha256(key).hexdigest(),
            'action': 'launch',
            'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
    scope = dict(body, scope_sha256=digest(body))
    signed = subprocess.run([str(_ISSUER), 'dgst', '-sha256', '-sign', str(private)],
                            input=('scope:' + scope['scope_sha256']).encode('ascii'),
                            capture_output=True, timeout=10, check=False)
    assert signed.returncode == 0
    scope['issuer_signature'] = base64.b64encode(signed.stdout).decode('ascii')
    kwargs = {'run_id': body['run_id'], 'plan_sha256': body['plan_sha256'],
              'session_sha256': body['session_sha256'], 'action': 'launch'}
    _scope(scope, scope['scope_sha256'], key, **kwargs)
    with pytest.raises(WindowsConnectedDeliveryError, match='exact_scope_required'):
        _scope(scope, scope['scope_sha256'], key, **dict(kwargs, action='stop'))
    expired = dict(body, expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    expired['scope_sha256'] = digest(expired)
    expired['issuer_signature'] = scope['issuer_signature']
    with pytest.raises(WindowsConnectedDeliveryError, match='exact_scope_required'):
        _scope(expired, expired['scope_sha256'], key, **kwargs)
