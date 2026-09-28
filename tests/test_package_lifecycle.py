"""Package layouts use the same exact-byte bundle and synthetic host lifecycle."""
from pathlib import Path

import pytest

from scripts.implementation_fixtures import fixture
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import InputError, digest, read_json
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation, rollback_implementation,
)
from jev_integration_evaluator.integrations.errors import UnsupportedShape
from jev_integration_evaluator.integrations.verification import verify_implementation


@pytest.mark.parametrize('layout', ['flat', 'package', 'src', 'namespace'])
def test_package_host_lifecycle(tmp_path, layout):
    root, bundle = tmp_path / 'host', tmp_path / 'bundle'
    inventory, spec = fixture(root, 'C', layout=layout, tag='package_' + layout)
    plan = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    manifest = read_json(bundle / 'implementation-manifest.json')
    if layout != 'flat':
        assert manifest['package_binding'] == spec['package_binding']
        assert spec['source']['file'] in manifest['contributing_sources']
    baseline = verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(root, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'


def test_contributing_initializer_drift_invalidates_plan(tmp_path):
    root, bundle = tmp_path / 'host', tmp_path / 'bundle'
    inventory, spec = fixture(root, 'C', layout='src')
    plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    (root / 'src/fixture_pkg/__init__.py').write_text('"""Changed package."""\n', encoding='utf-8')
    with pytest.raises(InputError, match='Contributing package module changed'):
        verify_implementation(root, bundle, 'baseline', approve_execution=True)


def test_unsupported_package_contract_does_not_write(tmp_path):
    root, bundle = tmp_path / 'host', tmp_path / 'bundle'
    inventory, spec = fixture(root, 'C', layout='src')
    spec['package_binding']['module'] = 'wrong.host'
    before = {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(UnsupportedShape, match='module differs'):
        plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert not bundle.exists()
    assert {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


def test_imported_registry_is_source_bound_and_runs(tmp_path):
    root, bundle = tmp_path / 'host', tmp_path / 'bundle'
    inventory, spec = fixture(root, 'K', layout='package')
    host = root / spec['source']['file']
    source = host.read_text(encoding='utf-8')
    registry = spec['bindings']['registry']
    baseline_action = spec['bindings']['baseline_action']
    block = f'def {registry}(request):\n    return dict(OPTIONS)\n\n\n'
    baseline_block = f"def {baseline_action}(request):\n    return 'base'\n\n\n"
    assert block in source
    assert baseline_block in source
    source = source.replace(block, '').replace(baseline_block, '').replace('from __future__ import annotations',
                                                f'from __future__ import annotations\nfrom .callbacks import {registry}, {baseline_action}')
    host.write_text(source, encoding='utf-8', newline='')
    callbacks = host.parent / 'callbacks.py'
    callbacks.write_text("OPTIONS = {'base': 'inspect', 'accept': 'accept', 'changes': 'request_changes'}\n\n" + block + baseline_block,
                         encoding='utf-8', newline='')
    cfg = load_config(); cfg['repository']['typescript_ast'] = False
    inventory = scan_repo(root, cfg)
    candidate = next(c for c in inventory['candidates'] if c['source']['symbol'] == spec['source']['symbol'])
    apply_reviews(inventory, {candidate['candidate_id']:{'source_sha256':candidate['source']['source_sha256'],
        'approved':True,'reviewer':'offline-synthetic-fixture-author','reason':'Source matched synthetic binding review'}}, cfg)
    selected = candidate['source']
    spec['candidate_id'] = candidate['candidate_id']
    spec['experiment_id'] = candidate['recommended_experiment']['id']
    spec['inventory_sha256'] = digest(inventory)
    spec['inventory_fingerprint'] = inventory['scan_fingerprint']
    spec['source'].update(file_sha256=selected['file_sha256'], source_sha256=selected['source_sha256'])
    spec['binding_review']['source_sha256'] = selected['source_sha256']
    plan = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    manifest = read_json(bundle / 'implementation-manifest.json')
    assert 'fixture_pkg/callbacks.py' in manifest['contributing_sources']
    baseline = verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(root, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
