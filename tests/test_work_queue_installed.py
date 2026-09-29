"""Opt-in normal installed command qualification for the second Python host."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import pytest

from tests.independent_hosts.work_queue import installed_journey


SCRIPT = (Path(__file__).parent / 'independent_hosts' / 'work_queue'
          / 'installed_journey.py')


@pytest.mark.parametrize('drift_stage', ['source', 'copied', 'review'])
def test_installed_queue_refuses_unreviewed_bytes_before_effects(tmp_path, monkeypatch,
                                                                   drift_stage):
    if (sys.platform != 'linux' or platform.machine().lower() != 'x86_64' or
            sys.version_info[:2] != (3, 13)):
        pytest.skip('declared Linux x86-64 CPython 3.13 profile required')
    authored = tmp_path / 'authored'
    shutil.copytree(installed_journey.ROOT, authored,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    monkeypatch.setattr(installed_journey, 'ROOT', authored)
    if drift_stage == 'source':
        (authored / 'src/work_queue/engine.py').write_text(
            (authored / 'src/work_queue/engine.py').read_text() + '\n# drift\n')
    elif drift_stage == 'review':
        review = authored / 'review-v1.json'
        review.write_text(review.read_text() + ' ')
    else:
        original_copytree = installed_journey.shutil.copytree

        def changed_copy(*args, **kwargs):
            copied = original_copytree(*args, **kwargs)
            if Path(args[0]) == authored:
                source = Path(copied) / 'src/work_queue/engine.py'
                source.write_text(source.read_text() + '\n# copied drift\n')
            return copied

        monkeypatch.setattr(installed_journey.shutil, 'copytree', changed_copy)
    calls = []
    monkeypatch.setattr(installed_journey._qualification, 'source_matched_request',
                        lambda *args: calls.append(args))
    wheelhouse = tmp_path / 'wheelhouse'
    wheelhouse.mkdir(mode=0o700)
    workspace, anchors = tmp_path / 'workspace', tmp_path / 'anchors'
    with pytest.raises(RuntimeError, match='work_queue_frozen_(source|review)_changed'):
        installed_journey.run_offline(workspace, wheelhouse, anchors)
    assert calls == []
    assert not (workspace / 'journey').exists()
    assert not (workspace / 'external-effects').exists()
    assert not (workspace / 'implementation').exists()


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
