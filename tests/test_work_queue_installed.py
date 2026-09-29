"""Opt-in normal installed command qualification for the second Python host."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import pytest

from tests.independent_hosts.work_queue import installed_journey


SCRIPT = (Path(__file__).parent / 'independent_hosts' / 'work_queue'
          / 'installed_journey.py')


def test_queue_origin_audit_refuses_swapped_interpreter(tmp_path, monkeypatch):
    if sys.platform != 'linux':
        pytest.skip('Linux installed interpreter symlink profile required')
    environment = tmp_path / 'environment'
    bin_dir = environment / 'venv/bin'
    bin_dir.mkdir(parents=True)
    python = bin_dir / 'python'
    python.symlink_to(Path(sys.executable).resolve())
    python.unlink()
    python.symlink_to('/usr/bin/false')
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: calls.append(args))
    with pytest.raises(RuntimeError, match='interpreter_origin_drift'):
        installed_journey._installed_origins(
            {'environment': str(environment), 'installed': {'python': str(python)}},
            {'profile': {'executable_path': str(Path(sys.executable).resolve())}})
    assert calls == []


def test_installed_work_queue_journey(tmp_path):
    if sys.platform != 'linux' or platform.machine().lower() != 'x86_64':
        pytest.skip('declared Linux x86-64 installed profile required')
    interpreter = os.environ.get('JEV_WORK_QUEUE_INSTALLED_PYTHON')
    wheelhouse = os.environ.get('JEV_WORK_QUEUE_WHEELHOUSE')
    if not interpreter or not wheelhouse:
        pytest.skip('explicit installed interpreter and reviewed wheelhouse required')
    workspace, anchors = tmp_path / 'workspace', tmp_path / 'anchors'
    process = subprocess.run(
        [interpreter, '-I', str(SCRIPT), '--workspace', str(workspace),
         '--wheelhouse', wheelhouse, '--anchors', str(anchors)],
        cwd=tmp_path, env={'PATH': '/usr/bin:/bin', 'PYTHONNOUSERSITE': '1'},
        capture_output=True, text=True, timeout=600)
    assert process.returncode == 0, process.stderr[-3000:]
    report = json.loads(process.stdout)
    assert report['kind'] == 'work-queue-offline-report-v1'
    assert report['classification'] == 'second_independent_installed_host'
    assert report['observed_operation'] == 'enqueue'
    assert report['effect_count'] == 1
    assert report['start_recovered_same_run'] and report['duplicate_refused']
    assert report['provider_qualification'] == 'not_run'
    assert report['measured_benefit'] is False
    assert report['final_stage'] == 'rolled_back'
    assert set(report['installed_origins']) == {'host', 'evaluator'}
    assert all(Path(value).is_relative_to(workspace / 'environments')
               for value in report['installed_origins'].values())
    effects = [json.loads(line) for line in
               (workspace / 'external-effects/effects.jsonl').read_text().splitlines()]
    assert effects == [{'job_id': 'queue-installed-1', 'operation': 'enqueue',
                        'item': 'batch-b'}]
    assert {'delivery_start_pending.json', 'delivery_start_recovered.json',
            'delivery_rolled_back.json'} <= {path.name for path in anchors.iterdir()}
