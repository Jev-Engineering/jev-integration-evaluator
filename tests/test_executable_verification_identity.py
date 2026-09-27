"""Verification evidence is bound to the reviewed copies and final target identity."""
import os
from pathlib import Path
import stat
import sys

import pytest

from jev_integration_evaluator.integrations import verification as verifier
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation, rollback_implementation,
)
from jev_integration_evaluator.io import InputError, read_json
from scripts.implementation_fixtures import fixture


@pytest.mark.parametrize('drift', ['bytes', 'mode', 'missing'])
def test_modified_command_cannot_change_adapter_and_still_verify(tmp_path, drift):
    if drift == 'mode' and os.name != 'posix':
        pytest.skip('Exact POSIX mode transition exercised separately from Windows permissions')
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C')
    filename = spec['output']['module']+'.py'
    operation = {
        'bytes': "p.write_bytes(p.read_bytes()+b'\\n# post-check change\\n')",
        'mode': 'p.chmod(0o700)',
        'missing': 'p.unlink()',
    }[drift]
    spec['verification']['modified_command'] = [sys.executable, '-c',
        'from pathlib import Path;p=Path('+repr(filename)+');'+operation]
    plan = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
    adapter = root/filename
    original, mode = adapter.read_bytes(), stat.S_IMODE(adapter.stat().st_mode)
    try:
        modified = verifier.verify_implementation(root, bundle, 'modified', approve_execution=True,
                                                  baseline_sha256=baseline['receipt_sha256'])
        assert modified['status'] == 'verification_failed'
        receipt = read_json(bundle/'verification-receipt.json')
        assert receipt['status'] == 'failed' and receipt['file_identity_valid'] is False
        # Observed checks remain in the denominator, even though the target drifted afterward.
        assert receipt['scheduled_cases'] == len(spec['verification']['cases'])*3
        assert receipt['completed_cases'] == receipt['scheduled_cases']
        assert all(row['status'] == 'passed' for row in receipt['results'])
        if drift != 'missing':
            with pytest.raises(InputError):
                rollback_implementation(root, bundle, applied['rollback_digest'])
        # An absent generated file already equals its baseline; recovery may
        # legitimately restore the remaining host preimage without recreating it.
    finally:
        # Only this test reconciles its own deliberate drift, never the recovery engine.
        adapter.write_bytes(original)
        adapter.chmod(mode)
        assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'


def test_baseline_command_cannot_create_reserved_adapter_and_pass(tmp_path):
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C')
    filename = spec['output']['module']+'.py'
    spec['verification']['baseline_command'] = [sys.executable, '-c',
        'from pathlib import Path;Path('+repr(filename)+').write_text("# unexpected output\\n")']
    plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    try:
        baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'verification_failed'
        receipt = read_json(bundle/'baseline-receipt.json')
        assert receipt['file_identity_valid'] is False
        assert receipt['scheduled_cases'] == len(spec['verification']['cases'])
    finally:
        (root/filename).unlink(missing_ok=True)


@pytest.mark.parametrize('phase', ['baseline', 'modified'])
def test_probe_copy_requires_reviewed_hash_not_current_self_consistency(tmp_path, monkeypatch, phase):
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C')
    plan = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    baseline_hash = None
    applied = None
    if phase == 'modified':
        baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
        baseline_hash = baseline['receipt_sha256']
        applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline_hash)
    source = root/(spec['source']['file'] if phase == 'baseline' else spec['output']['module']+'.py')
    original = source.read_bytes()
    real = verifier._probe
    def changed_after_phase_preflight(*args, **kwargs):
        source.write_bytes(original+b'\n# unreviewed snapshot introduced after phase preflight\n')
        try:
            return real(*args, **kwargs)
        finally:
            source.write_bytes(original)
    monkeypatch.setattr(verifier, '_probe', changed_after_phase_preflight)
    try:
        result = verifier.verify_implementation(root, bundle, phase, approve_execution=True,
                                                baseline_sha256=baseline_hash)
        assert result['status'] == 'verification_failed'
        receipt = read_json(bundle/('baseline-receipt.json' if phase == 'baseline' else 'verification-receipt.json'))
        assert receipt['file_identity_valid'] is True  # Restored target cannot validate unreviewed scratch bytes.
        assert all(row['status'] == 'failed' and row['observation'] is None for row in receipt['results'])
        expected = len(spec['verification']['cases'])*(1 if phase == 'baseline' else 3)
        assert receipt['scheduled_cases'] == expected and receipt['completed_cases'] == expected
    finally:
        assert source.read_bytes() == original
        if applied:
            assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'


def test_receipt_identity_field_is_backward_readable_not_false_success(tmp_path):
    from jev_integration_evaluator.contracts import seal, validate_contract
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C')
    plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    result = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert result['status'] == 'baseline_passed' and result['file_identity_valid'] is True
    receipt = read_json(bundle/'baseline-receipt.json')
    validate_contract(receipt, 'implementation-receipt')
    historical_shape = dict(receipt)
    historical_shape.pop('file_identity_valid')
    validate_contract(seal(historical_shape), 'implementation-receipt')
    contradictory = seal({**receipt, 'file_identity_valid': False, 'status': 'passed'})
    with pytest.raises(InputError):
        validate_contract(contradictory, 'implementation-receipt')
