"""Opt-in installed Alpha fault journey, executed outside both source trees."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import pytest


SCRIPT = (Path(__file__).parent / 'independent_hosts' / 'registered_alpha'
          / 'installed_journey.py')
CHECKS = {'install_interrupted_recovered', 'revoked_scope', 'source_drift', 'config_drift',
          'unreleased_start_recovered', 'duplicate_effect_twice',
          'post_disable_refusal', 'rollback_edit_refusal'}


def test_installed_registered_alpha_fault_journey(tmp_path):
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
        capture_output=True, text=True, timeout=600)
    assert process.returncode == 0, process.stderr[-3000:]
    result = json.loads(process.stdout)
    assert result['classification'] == 'offline_installed_host'
    assert result['final_stage'] == 'rolled_back'
    assert result['provider_qualification'] == 'not_run'
    assert result['measured_benefit'] is False
    assert set(result['offline_fault_checks']) == CHECKS
    assert set(result['installed_origins']) == {'host', 'evaluator'}
    assert all(Path(origin).is_relative_to(workspace / 'environments')
               for origin in result['installed_origins'].values())
    assert (workspace / 'external-effects' / 'effects.jsonl').read_text().count('\n') == 1
    assert {'install_incomplete_generation.json',
            'delivery_start_pending.json', 'delivery_start_recovered.json',
            'delivery_rolled_back.json'} <= {path.name for path in anchors.iterdir()}
