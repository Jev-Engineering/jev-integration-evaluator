"""Local controller authority boundaries; no provider or target imports."""
from __future__ import annotations

import base64
from pathlib import Path
import subprocess
import sys

import pytest

from jev_integration_evaluator.template_connected_generation import _verify, _OPENSSL_ENV


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
        assert _verify(public, 'generation_transfer', exact, signature) is (algorithm == 'EC')
        assert not _verify(public, 'generation_transfer', 'b' * 64, signature)
