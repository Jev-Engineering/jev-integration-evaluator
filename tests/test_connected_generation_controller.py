"""Local controller authority boundaries; no provider or target imports."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

from jev_integration_evaluator.template_connected_generation import _verify, _OPENSSL_ENV
from jev_integration_evaluator import template_connected_generation as generation


@pytest.mark.skipif(sys.platform != 'linux', reason='fixed OpenSSL verifier is Linux only')
def test_transfer_signature_requires_public_p256_not_merely_valid_rsa(tmp_path):
    if not Path('/usr/bin/openssl').is_file():
        pytest.skip('fixed OpenSSL verifier unavailable')
    exact = 'a' * 64
    for algorithm in ('EC', 'RSA'):
        private = tmp_path / (algorithm + '-private.pem')
        public = tmp_path / (algorithm + '-public.pem')
        args = (['-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256']
                if algorithm == 'EC' else ['-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048'])
        subprocess.run(['/usr/bin/openssl', 'genpkey', *args, '-out', str(private)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10, env=_OPENSSL_ENV)
        subprocess.run(['/usr/bin/openssl', 'pkey', '-in', str(private), '-pubout',
                        '-out', str(public)], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10, env=_OPENSSL_ENV)
        private.chmod(0o600); public.chmod(0o600)
        signed = subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', str(private)],
            input=('generation_transfer:' + exact).encode('ascii'), capture_output=True,
            check=True, timeout=10, env=_OPENSSL_ENV)
        signature = base64.b64encode(signed.stdout).decode('ascii')
        expected_public_sha256 = hashlib.sha256(public.read_bytes()).hexdigest()
        assert _verify(public, 'generation_transfer', exact, signature,
                       expected_public_sha256=expected_public_sha256) is (algorithm == 'EC')
        assert not _verify(public, 'generation_transfer', 'b' * 64, signature,
                           expected_public_sha256=expected_public_sha256)


@pytest.mark.skipif(sys.platform != 'linux', reason='fixed OpenSSL verifier is Linux only')
def test_transfer_verification_consumes_the_inspected_public_key_bytes(tmp_path, monkeypatch):
    exact = 'a' * 64
    trusted = tmp_path / 'trusted.pem'
    trusted_private = tmp_path / 'trusted-private.pem'
    foreign_private = tmp_path / 'foreign-private.pem'
    foreign_public = tmp_path / 'foreign.pem'
    real_run = subprocess.run
    for private, args in ((trusted_private, ['-algorithm', 'EC', '-pkeyopt',
                                             'ec_paramgen_curve:prime256v1']),
                          (foreign_private, ['-algorithm', 'RSA', '-pkeyopt',
                                             'rsa_keygen_bits:2048'])):
        real_run(['/usr/bin/openssl', 'genpkey', *args, '-out', str(private)],
                 check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 timeout=10, env=_OPENSSL_ENV)
    for private, public in ((trusted_private, trusted), (foreign_private, foreign_public)):
        real_run(['/usr/bin/openssl', 'pkey', '-in', str(private), '-pubout',
                  '-out', str(public)], check=True, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, timeout=2, env=_OPENSSL_ENV)
    signed = real_run(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', str(foreign_private)],
        input=('generation_transfer:' + exact).encode('ascii'), capture_output=True,
        check=True, timeout=2, env=_OPENSSL_ENV)
    signature = base64.b64encode(signed.stdout).decode('ascii')
    # The foreign signature is independently valid under its own public key.
    foreign_signature = tmp_path / 'foreign.sig'
    foreign_signature.write_bytes(signed.stdout)
    verified = real_run(['/usr/bin/openssl', 'dgst', '-sha256', '-verify', str(foreign_public),
                         '-signature', str(foreign_signature)],
        input=('generation_transfer:' + exact).encode('ascii'), capture_output=True,
        timeout=2, env=_OPENSSL_ENV)
    assert verified.returncode == 0
    expected_public_sha256 = hashlib.sha256(trusted.read_bytes()).hexdigest()
    swapped = []
    def swap_before_verify(args, **kwargs):
        if len(args) > 1 and args[1] == 'dgst':
            trusted.write_bytes(foreign_public.read_bytes())
            swapped.append(True)
        return real_run(args, **kwargs)
    monkeypatch.setattr(generation.subprocess, 'run', swap_before_verify)
    assert not _verify(trusted, 'generation_transfer', exact, signature,
                       expected_public_sha256=expected_public_sha256)
    assert swapped == [True]
