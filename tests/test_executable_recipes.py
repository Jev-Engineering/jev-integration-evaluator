"""Actual host edits, subprocess executions, independent assertions, and recovery."""
from pathlib import Path
import copy
import pytest
from scripts.implementation_fixtures import fixture
from jev_integration_evaluator.io import file_hash, read_json
from jev_integration_evaluator.integrations.lifecycle import (plan_implementation,apply_implementation,
    implementation_status,rollback_implementation)
from jev_integration_evaluator.integrations.verification import verify_implementation


@pytest.mark.parametrize('pattern', list('ABCDEFGHIJKLM'))
def test_full_host_lifecycle_all_thirteen_recipes(tmp_path, pattern):
    root,bundle=tmp_path/'target',tmp_path/'private-bundle'
    inventory,spec=fixture(root,pattern,tag='varied_'+pattern.lower(),crlf=pattern=='D')
    original={p.name:p.read_bytes() for p in root.iterdir()}
    plan=plan_implementation(root,inventory,spec['candidate_id'],spec,bundle)
    assert {p.name:p.read_bytes() for p in root.iterdir()}==original
    baseline=verify_implementation(root,bundle,'baseline',approve_execution=True)
    assert baseline['status']=='baseline_passed', read_json(bundle/'baseline-receipt.json')
    applied=apply_implementation(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    assert applied['status']=='applied_unverified'
    assert apply_implementation(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])['idempotent']
    modified=verify_implementation(root,bundle,'modified',approve_execution=True,baseline_sha256=baseline['receipt_sha256'])
    assert modified['status']=='verified', read_json(bundle/'verification-receipt.json')
    assert implementation_status(root,bundle)['status']=='applied_unverified'
    assert implementation_status(root,bundle,trusted_receipt_sha256=modified['receipt_sha256'])['status']=='verified'
    rolled=rollback_implementation(root,bundle,applied['rollback_digest'])
    assert rolled['status']=='rolled_back'
    assert {p.name:p.read_bytes() for p in root.iterdir()}==original
    assert implementation_status(root,bundle)['status']=='rolled_back'
