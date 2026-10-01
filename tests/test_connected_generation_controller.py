"""Local controller authority boundaries; no provider or target imports."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

from jev_integration_evaluator.template_connected_generation import _verify, _OPENSSL_ENV
from jev_integration_evaluator import template_connected_generation as generation
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
from jev_integration_evaluator.io import digest


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


LIMITS = dict(max_calls_per_task=2, max_cost_per_task=1,
              max_total_calls=3, max_total_cost=2, max_in_flight=2, max_tasks=4)


def _planned(monkeypatch, tmp_path):
    """Bypass installed-source checks so only the ledger precondition is exercised."""
    ledger = tmp_path / 'runtime-ledger'
    far = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace('+00:00', 'Z')
    monkeypatch.setattr(generation.delivery.offline, '_linux_profile', lambda: None)
    monkeypatch.setattr(generation, '_stopped',
                        lambda directory, trusted_head: ({}, {'plan_sha256': 'a' * 64}))
    monkeypatch.setattr(generation.delivery, '_check_plan', lambda plan: None)
    installed = iter(({'identity': digest('old reviewed runtime'), 'placement': 'seam',
                       'ledger': ledger, 'binding_sha256': 'b' * 64, 'public': 'c' * 64,
                       'egress_expires_at': far},
                      {'identity': digest('new reviewed runtime'), 'placement': 'seam',
                       'ledger': ledger, 'binding_sha256': 'd' * 64, 'public': 'c' * 64,
                       'egress_expires_at': far}))
    monkeypatch.setattr(generation, '_installed',
                        lambda plan, dependency_plan, limits: next(installed))
    now = datetime.now(timezone.utc)
    stamp = lambda delta: (now + delta).isoformat().replace('+00:00', 'Z')
    return ledger, dict(trusted_old_head='e' * 64, old_dependency_plan={},
                        new_dependency_plan={}, limits=LIMITS, action='upgrade',
                        issued_at=stamp(timedelta(minutes=-1)),
                        expires_at=stamp(timedelta(minutes=5)))


def test_transfer_plan_requires_existing_durable_ledger(tmp_path, monkeypatch):
    ledger, arguments = _planned(monkeypatch, tmp_path)
    with pytest.raises(generation.ConnectedGenerationError,
                       match='^connected_generation_existing_ledger_required$'):
        generation.plan_connected_generation_transfer(tmp_path / 'old', {'plan_sha256': 'f' * 64},
                                                      **arguments)
    # Planning must not manufacture an empty ledger in place of the missing history.
    assert not ledger.exists() and not Path(str(ledger) + '.sqlite').exists()


def test_transfer_plan_derives_from_existing_ledger_history(tmp_path, monkeypatch):
    ledger, arguments = _planned(monkeypatch, tmp_path)
    RuntimeLedger(ledger, identity=digest('old reviewed runtime'), **LIMITS).release()
    grant = generation.plan_connected_generation_transfer(tmp_path / 'old',
                                                          {'plan_sha256': 'f' * 64}, **arguments)
    assert grant['kind'] == 'connected-generation-transfer-v1'
    assert grant['old_identity'] == digest('old reviewed runtime')
    assert grant['new_identity'] == digest('new reviewed runtime')


def test_transfer_plan_refuses_mixed_profile_generations(tmp_path, monkeypatch):
    ledger, arguments = _planned(monkeypatch, tmp_path)
    RuntimeLedger(ledger, identity=digest('old reviewed runtime'), **LIMITS).release()
    with pytest.raises(generation.ConnectedGenerationError,
                       match='^connected_generation_scope_invalid$'):
        generation.plan_connected_generation_transfer(
            tmp_path / 'old', {'plan_sha256': 'f' * 64, 'host_profile': 'retrieval-d-v1'},
            **arguments)


NEW_PROFILES = ('graph-l-v1', 'claim-m-v1', 'completion-e-v1')


def test_transfer_profiles_are_finite_single_placement_shapes(tmp_path):
    assert generation._TRANSFER_PROFILES == (
        None, 'retrieval-d-v1', 'retention-h-v1', *NEW_PROFILES)
    for name in generation._TRANSFER_PROFILES:
        profile = generation.delivery._profile(name)
        # One reviewed source file and one loader: never a composite placement map.
        assert type(profile['source']) is str and 'loader' in profile['members']
    for refused in ('registered-dual-connected-v1', 'unregistered-host', 'GRAPH-L-V1', ''):
        assert refused not in generation._TRANSFER_PROFILES
        with pytest.raises(generation.ConnectedGenerationError,
                           match='^connected_generation_profile_not_supported$'):
            generation._authority({'host_profile': refused}, {}, tmp_path / 'absent-signature')


@pytest.mark.parametrize('old_profile,new_profile', [
    ('graph-l-v1', 'claim-m-v1'), ('claim-m-v1', 'completion-e-v1'),
    ('completion-e-v1', 'graph-l-v1'), ('graph-l-v1', 'retrieval-d-v1'),
    ('retention-h-v1', 'claim-m-v1'), ('completion-e-v1', None), (None, 'graph-l-v1')])
def test_transfer_plan_refuses_mixed_new_finite_profiles(tmp_path, monkeypatch,
                                                         old_profile, new_profile):
    ledger, arguments = _planned(monkeypatch, tmp_path)
    old_plan = {'plan_sha256': 'a' * 64}
    if old_profile is not None:
        old_plan['host_profile'] = old_profile
    monkeypatch.setattr(generation, '_stopped', lambda directory, trusted_head: ({}, old_plan))
    RuntimeLedger(ledger, identity=digest('old reviewed runtime'), **LIMITS).release()
    new_plan = {'plan_sha256': 'f' * 64}
    if new_profile is not None:
        new_plan['host_profile'] = new_profile
    with pytest.raises(generation.ConnectedGenerationError,
                       match='^connected_generation_scope_invalid$'):
        generation.plan_connected_generation_transfer(tmp_path / 'old', new_plan, **arguments)


@pytest.mark.parametrize('profile', NEW_PROFILES)
def test_transfer_plan_keeps_one_new_finite_profile_on_both_sides(tmp_path, monkeypatch,
                                                                  profile):
    ledger, arguments = _planned(monkeypatch, tmp_path)
    monkeypatch.setattr(generation, '_stopped', lambda directory, trusted_head: (
        {}, {'plan_sha256': 'a' * 64, 'host_profile': profile}))
    # The existing-ledger precondition applies to the new profiles unchanged.
    with pytest.raises(generation.ConnectedGenerationError,
                       match='^connected_generation_existing_ledger_required$'):
        generation.plan_connected_generation_transfer(
            tmp_path / 'old', {'plan_sha256': 'f' * 64, 'host_profile': profile}, **arguments)
    assert not ledger.exists() and not Path(str(ledger) + '.sqlite').exists()


def _status_inputs(monkeypatch, tmp_path, parent_change=None):
    """Isolate the parent-link comparison from installed-source and ledger reads."""
    grant = {'action': 'upgrade', 'old_plan_sha256': 'a' * 64, 'new_plan_sha256': 'b' * 64,
             'new_binding_sha256': 'c' * 64}
    old_state = {'run_id': 'run-1', 'failures': ['provider_timeout']}
    old_plan = {'plan_sha256': 'a' * 64, 'off_provenance': {'launch_environment': {
        'REGISTERED_ALPHA_CONNECTED_REF': str(tmp_path / 'reference.json')}}}
    new_plan = {'plan_sha256': 'b' * 64, 'installed_binding': {'binding_sha256': 'c' * 64}}
    parent = {'run_id': 'run-1', 'old_plan_sha256': 'a' * 64,
              'old_session_head_sha256': 'e' * 64, 'grant_sha256': digest(grant),
              'action': 'upgrade', 'original_expires_at': '2030-01-01T00:00:00Z',
              'failure_history': ['provider_timeout']}
    if parent_change:
        parent_change(parent)
    state = {'generation_parent': parent, 'stage': 'generation_pending'}
    monkeypatch.setattr(generation, 'validate_contract', lambda value, name: None)
    monkeypatch.setattr(generation, '_stopped', lambda directory, head: (old_state, old_plan))
    monkeypatch.setattr(generation, '_authority',
                        lambda plan, grant, signature: (lambda kind, exact: True))
    monkeypatch.setattr(generation.delivery, '_open',
                        lambda directory: (None, [{'record_sha256': 'd' * 64}], state, new_plan))
    monkeypatch.setattr(generation, 'read_json', lambda path: {
        'ledger_path': str(tmp_path / 'ledger'),
        'authority': {'egress_grant': {'expires_at': '2030-01-01T00:00:00Z'}}})
    monkeypatch.setattr(RuntimeLedger, 'generation_transfer_status',
                        staticmethod(lambda path, **kwargs: {'status': 'committed'}))
    return grant, dict(grant=grant, signature_file=tmp_path / 'grant.sig',
                       trusted_old_head='e' * 64)


def test_generation_status_accepts_the_exact_prepared_child(tmp_path, monkeypatch):
    grant, arguments = _status_inputs(monkeypatch, tmp_path)
    status = generation.connected_generation_status(tmp_path / 'old', tmp_path / 'new',
                                                    **arguments)
    assert status['grant_sha256'] == digest(grant)
    assert status['child_stage'] == 'generation_pending'


@pytest.mark.parametrize('change', [
    lambda parent: parent.update(original_expires_at='2031-01-01T00:00:00Z'),
    lambda parent: parent.update(failure_history=[]),
    lambda parent: parent.update(failure_history=['provider_timeout', 'launch_effect_unknown']),
    lambda parent: parent.pop('original_expires_at'),
    lambda parent: parent.update(unreviewed='extra'),
    lambda parent: parent.update(run_id='run-2'),
], ids=['later-cutoff', 'erased-failures', 'added-failure', 'missing-cutoff',
        'extra-field', 'other-run'])
def test_generation_status_refuses_any_changed_parent_link(tmp_path, monkeypatch, change):
    grant, arguments = _status_inputs(monkeypatch, tmp_path, change)
    with pytest.raises(generation.ConnectedGenerationError,
                       match='^connected_generation_child_changed$'):
        generation.connected_generation_status(tmp_path / 'old', tmp_path / 'new', **arguments)
