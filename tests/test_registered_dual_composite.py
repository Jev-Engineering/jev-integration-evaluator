"""Source-bound offline two-decision qualification on an authored host."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import json
import shutil
import subprocess
import sys

import pytest

from jev_integration_evaluator.integrations.composite import (
    plan_composite, verify_composite, apply_composite)
from jev_integration_evaluator.io import read_json
from tests.independent_hosts.registered_dual.qualification import (
    ROOT, source_matched_composite)
from tests.independent_hosts.registered_dual import installed_journey


pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux owned effect paths')


def test_frozen_dual_baselines_write_two_independent_raw_effects(tmp_path):
    effects = tmp_path / 'effects'
    effects.mkdir(mode=0o700)
    alpha, queue = effects / 'alpha.jsonl', effects / 'queue.jsonl'
    env = {**os.environ, 'REGISTERED_ALPHA_EFFECTS': str(alpha),
           'WORK_QUEUE_EFFECTS': str(queue), 'DUAL_TASK_ID': 'dual-task-one',
           'DUAL_SHADOW': '0', 'JEV_RUNTIME_MODE': 'off'}
    evaluator = Path(__file__).resolve().parents[1]
    for function in ('main_alpha', 'main_queue'):
        code = ('import sys;sys.path.insert(0,sys.argv[1]);'
                'sys.path.insert(0,sys.argv[2]);'
                'from registered_dual.console import ' + function + ';'
                'raise SystemExit(' + function + '())')
        run = subprocess.run([sys.executable, '-I', '-c', code,
                              str(ROOT / 'src'), str(evaluator)],
                             cwd=tmp_path, env=env, capture_output=True, timeout=15)
        assert run.returncode == 0, run.stderr
    oracle = read_json(ROOT / 'oracle-v1.json')
    assert [json.loads(line) for line in alpha.read_text().splitlines()] == [oracle['alpha_effect']]
    assert [json.loads(line) for line in queue.read_text().splitlines()] == [oracle['queue_effect']]


def test_two_reviewed_dual_seams_and_shared_modified_decisions(tmp_path, monkeypatch):
    host = tmp_path / 'host'
    shutil.copytree(ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    inventory, selection, specs = source_matched_composite(host)
    assert len(specs) == 2
    assert {spec['source']['symbol'] for spec in specs.values()} == {
        'select_registered_tool', 'choose_operation'}
    probe = tmp_path / 'probe'
    probe.mkdir(mode=0o700)
    monkeypatch.setenv('REGISTERED_ALPHA_PROBE_EFFECTS_DIR', str(probe))
    monkeypatch.setenv('WORK_QUEUE_PROBE_EFFECTS_DIR', str(probe))
    monkeypatch.setenv('DUAL_SHADOW', '1')
    monkeypatch.setenv('DUAL_REPEAT', '1')
    monkeypatch.setenv('DUAL_AUDIT_PATH', str(tmp_path / 'audit.json'))
    bundle = tmp_path / 'bundle'
    planned = plan_composite(host, inventory, selection, specs, bundle)
    baseline = verify_composite(host, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    apply_composite(host, bundle, planned['bundle_digest'],
                    baseline_sha256=baseline['receipt_sha256'])
    modified = verify_composite(host, bundle, 'modified', approve_execution=True,
                                baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert read_json(bundle / 'verification-receipt.json')['combined_check']['shared_budget_valid'] is True
    audit = read_json(tmp_path / 'audit.json')
    assert audit['calls'] == 2
    assert audit['audit_reasons'][-2:] == ['shared_total_call_budget'] * 2


@pytest.mark.parametrize('changed', ['source', 'oracle', 'review'])
def test_dual_installed_driver_refuses_copied_source_drift(tmp_path, monkeypatch, changed):
    if platform.machine().lower() != 'x86_64' or sys.version_info[:2] != (3, 13):
        pytest.skip('declared installed profile required')
    original_copytree = installed_journey.shutil.copytree

    def changed_copy(*args, **kwargs):
        copied = original_copytree(*args, **kwargs)
        if Path(args[0]) == installed_journey.ROOT:
            target = Path(copied) / {
                'source': 'src/registered_dual/alpha.py',
                'oracle': 'oracle-v1.json', 'review': 'review-v1.json'}[changed]
            target.write_text(target.read_text() + '\n# copied drift\n')
        return copied

    monkeypatch.setattr(installed_journey.shutil, 'copytree', changed_copy)
    calls = []
    monkeypatch.setattr(installed_journey._qualification, 'source_matched_composite',
                        lambda *args: calls.append(args))
    wheelhouse = tmp_path / 'wheelhouse'
    wheelhouse.mkdir(mode=0o700)
    workspace, anchors = tmp_path / 'workspace', tmp_path / 'anchors'
    with pytest.raises(RuntimeError, match='dual_frozen_(source|oracle|review)_changed'):
        installed_journey.run_offline(workspace, wheelhouse, anchors)
    assert calls == []
    assert not (workspace / 'bundle').exists()
    assert not (workspace / 'external-effects').exists()


def test_installed_dual_composite_journey(tmp_path):
    if platform.machine().lower() != 'x86_64' or sys.version_info[:2] != (3, 13):
        pytest.skip('declared installed profile required')
    interpreter = os.environ.get('JEV_DUAL_INSTALLED_PYTHON')
    wheelhouse = os.environ.get('JEV_DUAL_WHEELHOUSE')
    if not interpreter or not wheelhouse:
        pytest.skip('explicit installed interpreter and wheelhouse required')
    process = subprocess.run(
        [interpreter, '-I', str(ROOT / 'installed_journey.py'),
         '--workspace', str(tmp_path / 'workspace'), '--wheelhouse', wheelhouse,
         '--anchors', str(tmp_path / 'anchors')], cwd=tmp_path,
        env={'PATH': '/usr/bin:/bin', 'PYTHONNOUSERSITE': '1'},
        capture_output=True, text=True, timeout=600)
    assert process.returncode == 0, process.stderr[-3000:]
    report = json.loads(process.stdout)
    assert report['kind'] == 'registered-dual-offline-report-v1'
    assert report['classification'] == 'independent_installed_composite_fixture'
    assert len(report['candidate_ids']) == 2
    assert report['assessment_count'] == 2
    assert report['common_task_identity'] and report['shared_budget_exhausted']
    assert report['duplicate_refused'] and report['start_recovered_same_run']
    assert report['provider_qualification'] == 'not_run'
    assert report['measured_benefit'] is False and report['final_stage'] == 'rolled_back'
    oracle = read_json(ROOT / 'oracle-v1.json')
    evidence = tmp_path / 'workspace/external-effects'
    assert [json.loads(line) for line in (evidence / 'alpha.jsonl').read_text().splitlines()] == [oracle['alpha_effect']]
    assert [json.loads(line) for line in (evidence / 'queue.jsonl').read_text().splitlines()] == [oracle['queue_effect']]
    assert {'delivery_start_pending.json', 'delivery_start_recovered.json',
            'delivery_rolled_back.json'} <= {row.name for row in (tmp_path / 'anchors').iterdir()}
