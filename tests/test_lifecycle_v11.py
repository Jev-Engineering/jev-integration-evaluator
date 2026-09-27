import copy
import subprocess
import pytest
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.lifecycle import compare_snapshots
from jev_integration_evaluator.io import InputError

SOURCE = 'def route(state):\n    return model.choose(state)\n'


def fixture_repo(tmp_path):
    (tmp_path / 'router.py').write_text(SOURCE)
    return tmp_path


def test_same_snapshot_is_reproducible(tmp_path, cfg):
    root = fixture_repo(tmp_path)
    a, b = scan_repo(root, cfg), scan_repo(root, cfg)
    assert a['scan_fingerprint'] == b['scan_fingerprint']
    d = compare_snapshots(a, b)
    assert d['counts']['unchanged'] > 0
    assert not any(c['requires_review'] for c in d['candidates'])
    assert d['automatically_carried_approvals'] == 0


def test_configuration_only_change_invalidates_identity(tmp_path, cfg):
    root = fixture_repo(tmp_path)
    (root / 'pyproject.toml').write_text('[project]\nname="before"\n')
    a = scan_repo(root, cfg)
    (root / 'pyproject.toml').write_text('[project]\nname="after"\n')
    b = scan_repo(root, cfg)
    assert a['analysis_identity']['source_digest'] == b['analysis_identity']['source_digest']
    assert a['scan_fingerprint'] != b['scan_fingerprint']
    d = compare_snapshots(a, b)
    assert d['configuration_changed']
    assert all(c['requires_review'] for c in d['candidates'])


def test_settings_only_change_requires_review(tmp_path, cfg):
    root = fixture_repo(tmp_path)
    a = scan_repo(root, cfg)
    cfg['scoring']['semantic_uncertainty'] += 1
    b = scan_repo(root, cfg)
    assert a['scan_fingerprint'] != b['scan_fingerprint']
    assert compare_snapshots(a, b)['settings_changed']


def test_edit_keeps_boundary_id_but_invalidates_source(tmp_path, cfg):
    root = fixture_repo(tmp_path)
    a = scan_repo(root, cfg)
    (root / 'router.py').write_text(SOURCE.replace('model.choose(state)', 'model.choose(state, tools=registry)'))
    b = scan_repo(root, cfg)
    common = set(c['candidate_id'] for c in a['candidates']) & set(c['candidate_id'] for c in b['candidates'])
    assert common
    changes = [r for r in compare_snapshots(a, b)['candidates'] if r['candidate_id'] in common]
    assert all(r['change'] == 'changed' and r['requires_review'] for r in changes)


def test_line_shift_is_distinguished_from_body_edit(tmp_path, cfg):
    root = fixture_repo(tmp_path)
    a = scan_repo(root, cfg)
    (root / 'router.py').write_text('# moved down\n' + SOURCE)
    b = scan_repo(root, cfg)
    rows = compare_snapshots(a, b)['candidates']
    assert any(r['change'] == 'line_shift_only' for r in rows)
    assert all(r['prior_evidence_reusable_automatically'] is False for r in rows)


def test_legacy_identity_never_claims_proven_absence(tmp_path, cfg):
    a = scan_repo(fixture_repo(tmp_path), cfg)
    b = copy.deepcopy(a)
    del a['analysis_identity']
    b['candidates'] = []
    d = compare_snapshots(a, b)
    assert d['legacy_identity']
    assert set(c['change'] for c in d['candidates']) == {'not_observed'}


def test_partial_coverage_absence_is_not_removal(tmp_path, cfg):
    a = scan_repo(fixture_repo(tmp_path), cfg)
    b = copy.deepcopy(a)
    b['coverage']['truncated'] = True
    b['candidates'] = []
    assert compare_snapshots(a, b)['counts']['not_observed']


def test_duplicate_candidate_and_identity_collision_rejected(tmp_path, cfg):
    a = scan_repo(fixture_repo(tmp_path), cfg)
    b = copy.deepcopy(a)
    b['candidates'].append(b['candidates'][0])
    with pytest.raises(InputError):
        compare_snapshots(a, b)
    b = copy.deepcopy(a)
    b['candidates'][0]['source']['symbol'] = 'another_boundary'
    with pytest.raises(InputError):
        compare_snapshots(a, b)


def test_repository_mismatch_needs_explicit_override(tmp_path, cfg):
    a = scan_repo(fixture_repo(tmp_path), cfg)
    b = copy.deepcopy(a)
    b['repository_name'] = 'different'
    with pytest.raises(InputError):
        compare_snapshots(a, b)
    assert compare_snapshots(a, b, allow_repository_mismatch=True)['repository_names_match'] is False


def test_scan_does_not_invoke_configured_fsmonitor(tmp_path, cfg):
    root = fixture_repo(tmp_path)
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    marker = root / 'executed-hook'
    hook = root / 'hook.sh'
    hook.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
    hook.chmod(0o755)
    subprocess.run(['git', '-C', str(root), 'config', 'core.fsmonitor', str(hook)], check=True)
    scan_repo(root, cfg)
    assert not marker.exists()
