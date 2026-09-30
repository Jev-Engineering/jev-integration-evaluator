"""Declared Linux fixture loaders reject independently issued non-P256 keys."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
LOADERS = (
    ('alpha', 'tests/independent_hosts/registered_alpha_connected/src/registered_alpha/connected_authority.py', 'REGISTERED_ALPHA'),
    ('retrieval', 'tests/independent_hosts/retrieval_connected/connected_authority.py', 'D'),
    ('dual', 'tests/independent_hosts/registered_dual_connected/src/registered_dual/connected_authority.py', 'REGISTERED_DUAL'),
)
pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Fixed Linux OpenSSL fixture loader')


@pytest.fixture(scope='module')
def issued_keys(tmp_path_factory):
    owner = tmp_path_factory.mktemp('independent-key-issuer')
    owner.chmod(0o700)
    env = {'LANG': 'C', 'OPENSSL_CONF': '/dev/null',
           'OPENSSL_MODULES': '/nonexistent', 'OPENSSL_ENGINES': '/nonexistent'}
    payload = b'egress_grant:' + b'0' * 64
    keys = {}
    for name, options in (
        ('p256', ['-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:prime256v1']),
        ('p384', ['-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:secp384r1']),
        ('rsa', ['-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048']),
    ):
        private = owner / (name + '-issuer.pem')
        public = owner / (name + '-public.pem')
        signature = owner / (name + '.sig')
        subprocess.run(['/usr/bin/openssl', 'genpkey', *options, '-out', str(private)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=env, timeout=10)
        subprocess.run(['/usr/bin/openssl', 'pkey', '-in', str(private), '-pubout', '-out', str(public)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=env, timeout=2)
        public.chmod(0o600)
        subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', str(private), '-out', str(signature)],
                       input=payload, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, env=env, timeout=2)
        # Both unsupported algorithms have valid separately issued signatures.
        # Rejection below is the declared key policy, not a broken signature.
        subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-verify', str(public),
                        '-signature', str(signature)], input=payload, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=2)
        keys[name] = public
        if name == 'p256':
            keys['private'] = private
    return keys


@pytest.mark.parametrize('name,relative,prefix', LOADERS, ids=[row[0] for row in LOADERS])
@pytest.mark.parametrize('key_kind', ('p256', 'p384', 'rsa', 'private'))
def test_reviewed_loader_requires_anchored_public_p256(monkeypatch, issued_keys,
                                                     name, relative, prefix, key_kind):
    # Qualification imports only these explicit reviewed synthetic fixtures.
    spec = importlib.util.spec_from_file_location('reviewed_loader_' + name, ROOT / relative)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    reference = issued_keys[key_kind]
    monkeypatch.setenv(prefix + '_AUTH_PUBKEY_FILE', str(reference))
    monkeypatch.setenv(prefix + '_AUTH_PUBKEY_SHA256', hashlib.sha256(reference.read_bytes()).hexdigest())
    if key_kind == 'p256':
        assert loader._public_key() == reference
    else:
        with pytest.raises(RuntimeError, match='^connected_public_key_invalid$'):
            loader._public_key()
