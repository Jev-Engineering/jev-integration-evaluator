"""Opt-in installed Alpha versioned source/effect journey."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import pytest

from tests.independent_hosts.registered_alpha import installed_upgrade
from jev_integration_evaluator.contracts import validate_contract


SCRIPT = (Path(__file__).parent / 'independent_hosts' / 'registered_alpha'
          / 'installed_upgrade.py')


@pytest.mark.parametrize('relative', ('src/registered_alpha/host.py',
                                      'src/registered_alpha/runtime.json'))
def test_pinned_upgrade_source_refuses_drift_before_scan(tmp_path, monkeypatch, relative):
    source_root = tmp_path / 'source'
    shutil.copytree(installed_upgrade.ROOT, source_root,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    source = source_root / relative
    source.write_bytes(source.read_bytes() + b'\n# unauthorized drift\n')
    calls = []
    monkeypatch.setattr(installed_upgrade, 'ROOT', source_root)
    monkeypatch.setattr(installed_upgrade, 'source_matched_request',
                        lambda *args: calls.append(args))
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    with pytest.raises(ValueError, match='pinned_source_drift'):
        installed_upgrade._prepare(workspace, tmp_path / 'wheelhouse',
                                   tmp_path / 'anchors', '1.0.0')
    assert calls == []


def test_installed_alpha_versioned_upgrade_and_retained_rollback(tmp_path):
    if sys.platform != 'linux' or platform.machine().lower() != 'x86_64':
        pytest.skip('declared installed Linux x86-64 profile required')
    interpreter = os.environ.get('JEV_REGISTERED_ALPHA_INSTALLED_PYTHON')
    wheelhouse = os.environ.get('JEV_REGISTERED_ALPHA_WHEELHOUSE')
    if not interpreter or not wheelhouse:
        pytest.skip('explicit installed interpreter and reviewed wheelhouse required')
    workspace, anchors = tmp_path / 'workspace', tmp_path / 'anchors'
    process = subprocess.run(
        [interpreter, '-I', str(SCRIPT), '--workspace', str(workspace),
         '--wheelhouse', wheelhouse, '--anchors', str(anchors)],
        cwd=tmp_path, env={'PATH': '/usr/bin:/bin', 'PYTHONNOUSERSITE': '1'},
        capture_output=True, text=True, timeout=900)
    assert process.returncode == 0, process.stderr[-5000:]
    report = json.loads(process.stdout)
    validate_contract(report, 'registered-alpha-upgrade-report-v1')
    raw = (workspace / 'external-effects' / 'effects.jsonl').read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    assert rows == [
        {'task_id': 'alpha-upgrade-1-0-0', 'action': 'inspect', 'item': 'fixture-one'},
        {'task_id': 'alpha-upgrade-1-0-1', 'action': 'inspect-v2', 'item': 'fixture-one'},
        {'task_id': 'alpha-upgrade-rollback', 'action': 'inspect', 'item': 'fixture-one'},
    ]
    assert hashlib.sha256(raw).hexdigest() == report['raw_effect_sha256']
    assert report['final_stage'] == 'rolled_back'
    assert report['rollback_validation_run_id'] != report['run_id']
    assert len(report['offline_fault_checks']) == 4
    assert report['provider_qualification'] == 'not_run'
    assert report['measured_benefit'] is False
    assert report['reviewed_host_file_sha256'][0] != report['reviewed_host_file_sha256'][1]
    assert all(Path(path).is_dir() for path in report['retained_environments'])
    assert all(Path(path).is_relative_to(workspace / 'environments')
               for path in report['retained_environments'])
    assert all(Path(origin).is_relative_to(workspace / 'environments')
               for origins in report['installed_origins'] for origin in origins.values())
    assert {'1.0.0-modified.json', '1.0.1-modified.json',
            '1.0.0-install.json', '1.0.1-install.json', 'upgrade-staged.json',
            'retained-generation-rolled-back.json', 'upgrade-report.json'} <= {
                path.name for path in anchors.iterdir()}
