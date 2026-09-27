"""Command outcomes must remain internally consistent even in resealed receipts."""
import sys

import pytest

from jev_integration_evaluator.contracts import seal
from jev_integration_evaluator.integrations.lifecycle import (
    _load, _receipt, apply_implementation, plan_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.io import InputError, digest, file_hash, read_json, write_json
from scripts.implementation_fixtures import fixture


@pytest.fixture
def baseline_with_command(tmp_path):
    root, bundle = tmp_path / 'target', tmp_path / 'bundle'
    inventory, spec = fixture(root, 'C')
    spec['verification']['baseline_command'] = [sys.executable, '-c', 'pass']
    plan = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    result = verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert result['status'] == 'baseline_passed'
    receipt = read_json(bundle / 'baseline-receipt.json')
    assert receipt['command_checks'] == [{
        'definition_sha256': digest(spec['verification']['baseline_command']),
        'status': 'passed', 'returncode': 0,
    }]
    return root, bundle, spec, plan, receipt


@pytest.mark.parametrize('status,returncode', [
    ('passed', 17), ('passed', None), ('timeout', 0), ('not_run', 0),
])
def test_inconsistent_command_receipt_rejected_before_apply(baseline_with_command, status, returncode):
    root, bundle, spec, plan, receipt = baseline_with_command
    receipt['command_checks'][0].update(status=status, returncode=returncode)
    receipt['status'] = 'passed' if status == 'passed' else 'failed'
    path = bundle / 'baseline-receipt.json'
    write_json(path, seal(receipt))
    retained_sha256 = file_hash(path)
    loaded_plan = _load(root, bundle)[2]
    original = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    with pytest.raises(InputError, match='Invalid implementation-receipt contract'):
        _receipt(root, bundle, loaded_plan, spec, 'baseline', retained_sha256)
    with pytest.raises(InputError, match='Invalid implementation-receipt contract'):
        apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=retained_sha256)
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == original


@pytest.mark.parametrize('status,returncode', [
    ('passed', 0), ('failed', 0), ('failed', 17), ('failed', -9),
    ('timeout', None), ('not_run', None),
])
def test_valid_command_outcome_combinations_remain_readable(baseline_with_command, status, returncode):
    root, bundle, spec, _, receipt = baseline_with_command
    receipt['command_checks'][0].update(status=status, returncode=returncode)
    receipt['status'] = 'passed' if status == 'passed' else 'failed'
    path = bundle / 'baseline-receipt.json'
    write_json(path, seal(receipt))
    loaded = _receipt(root, bundle, _load(root, bundle)[2], spec, 'baseline', file_hash(path))
    assert loaded['command_checks'][0]['status'] == status
    assert loaded['command_checks'][0]['returncode'] == returncode
