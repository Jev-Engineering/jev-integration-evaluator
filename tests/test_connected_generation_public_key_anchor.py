"""Real signatures must use the exact externally anchored public PEM bytes."""
from pathlib import Path
import sys

import pytest

from jev_integration_evaluator import template_connected_generation as generation
from jev_integration_evaluator.io import digest, file_hash, InputError
from tests.test_connected_installed_binding import _issuer, _issue


@pytest.mark.skipif(sys.platform != 'linux', reason='fixed OpenSSL verifier requires Linux')
def test_generation_authority_refuses_foreign_p256_snapshot_after_path_hash(tmp_path, monkeypatch):
    trusted_dir, foreign_dir = tmp_path / 'trusted', tmp_path / 'foreign'
    trusted_dir.mkdir(mode=0o700)
    foreign_dir.mkdir(mode=0o700)
    trusted_private, trusted_public = _issuer(trusted_dir)
    foreign_private, foreign_public = _issuer(foreign_dir)
    grant = {'old_binding_sha256': 'a' * 64}
    public_name = 'REGISTERED_ALPHA_AUTH_PUBKEY_FILE'
    plan = {'installed_binding': {'binding_sha256': grant['old_binding_sha256']},
            'off_provenance': {'launch_environment': {public_name: str(trusted_public)}},
            'reference_sha256': {public_name: file_hash(trusted_public)}}
    signature = tmp_path / 'signature.txt'
    signature.write_text(_issue(trusted_private, 'generation_transfer', digest(grant)))
    signature.chmod(0o600)
    assert callable(generation._authority(plan, grant, signature))
    signature.write_text(_issue(foreign_private, 'generation_transfer', digest(grant)))
    original_pem = trusted_public.read_bytes()
    foreign_pem = foreign_public.read_bytes()
    real_open = Path.open
    swaps = []

    def swap_before_snapshot(path, *args, **kwargs):
        if (path == trusted_public and not swaps
                and sys._getframe(1).f_code.co_name == '_verify'):
            # Replace actual path bytes after the controller's outer hash,
            # before its verifier opens, snapshots and validates the public key.
            swaps.append(True)
            with real_open(trusted_public, 'wb') as stream:
                stream.write(foreign_pem)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', swap_before_snapshot)
    try:
        with pytest.raises(InputError, match='transfer_unverified'):
            generation._authority(plan, grant, signature)
        assert swaps == [True]
    finally:
        trusted_public.write_bytes(original_pem)
