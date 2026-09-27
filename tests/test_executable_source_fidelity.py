"""Transformation must preserve unrelated decorators and the actual source encoding."""
import ast
import copy

import pytest

from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation, rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.io import InputError, read_json, digest
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.integrations.recipes import anchor_hash
from scripts.implementation_fixtures import fixture
from test_executable_safety import refreshed, snapshots


@pytest.mark.parametrize('kind', ['function', 'class'])
@pytest.mark.parametrize('decorator', [
    '@(lambda value: value)\n',
    '@(\n    # Keep the decorator opening outside its expression span.\n    lambda value: value\n)\n',
], ids=['single_line', 'multiline'])
def test_unrelated_leading_decorator_survives_real_host_lifecycle(tmp_path, kind, decorator):
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C', tag='decorated_neighbor_'+kind)
    path = root/spec['source']['file']
    text = path.read_text()
    prefix, remaining = text.split('from threading import RLock', 1)
    decorated = (decorator +
                 ('def unrelated_helper():\n    return 7\n' if kind == 'function' else
                  'class UnrelatedMarker:\n    pass\n'))
    path.write_text(prefix + decorated + 'from threading import RLock' + remaining)
    inventory, spec = refreshed(root, spec)
    original = snapshots(root)
    plan = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert snapshots(root) == original
    patch = read_json(bundle/'patch-plan.json')
    changed = next(c['new_content'] for c in patch['changes'] if c['file'] == spec['source']['file'])
    assert decorated in changed
    ast.parse(changed)
    baseline = verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
    try:
        modified = verify_implementation(root, bundle, 'modified', approve_execution=True,
                                          baseline_sha256=baseline['receipt_sha256'])
        assert modified['status'] == 'verified'
    finally:
        assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
        assert snapshots(root) == original


@pytest.mark.parametrize('encoding', ['latin-1', 'ascii', 'unknown-encoding'])
def test_non_utf8_source_cookie_is_rejected_before_bundle(tmp_path, encoding):
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C')
    path = root/spec['source']['file']
    path.write_bytes(path.read_bytes().replace(b'coding: utf-8', b'coding: '+encoding.encode()))
    # Match the scanner's UTF-8 text interpretation, not Python's byte-cookie decoding.
    cfg = load_config(); cfg['repository']['typescript_ast'] = False
    inventory = scan_repo(root, cfg)
    candidate = next(c for c in inventory['candidates'] if c['source']['symbol'] == spec['source']['symbol'])
    source = candidate['source']
    apply_reviews(inventory, {candidate['candidate_id']: {'source_sha256': source['source_sha256'],
        'approved': True, 'reviewer': 'synthetic-test', 'reason': 'Deliberately invalid encoding fixture'}}, cfg)
    spec = copy.deepcopy(spec)
    spec.update(candidate_id=candidate['candidate_id'], experiment_id=candidate['recommended_experiment']['id'],
                inventory_sha256=digest(inventory), inventory_fingerprint=inventory['scan_fingerprint'])
    spec['source'].update(file_sha256=source['file_sha256'], source_sha256=source['source_sha256'])
    spec['binding_review']['source_sha256'] = source['source_sha256']
    function = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body
                    if isinstance(n, ast.FunctionDef) and n.name == source['symbol'])
    spec['source']['anchor_sha256'] = anchor_hash(function.body[-1])
    original = snapshots(root)
    with pytest.raises(InputError, match='encoding|UTF-8'):
        plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert snapshots(root) == original and not bundle.exists()


@pytest.mark.parametrize('cookie', ['utf8', 'UTF-8', 'utf_8'])
def test_equivalent_utf8_cookie_is_still_supported(tmp_path, cookie):
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C')
    path = root/spec['source']['file']
    path.write_bytes(path.read_bytes().replace(b'coding: utf-8', b'coding: '+cookie.encode()))
    inventory, spec = refreshed(root, spec)
    original = snapshots(root)
    assert plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)['status'] == 'planned'
    assert snapshots(root) == original
