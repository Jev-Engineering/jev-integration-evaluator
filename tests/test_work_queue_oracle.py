"""Independent queue source, frozen oracle and recipe C reuse."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from jev_integration_evaluator.io import file_hash, read_json
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.template_catalog import prepare_template_binding, materialize_template
from jev_integration_evaluator.integrations.lifecycle import plan_implementation, apply_implementation
from jev_integration_evaluator.integrations.verification import verify_implementation
from tests.independent_hosts.work_queue.qualification import source_matched_request


ROOT = Path(__file__).parent / 'independent_hosts' / 'work_queue'
SOURCE = ROOT / 'src'
ORACLE = ROOT / 'oracle-v1.json'
REVIEW = ROOT / 'review-v1.json'
EVALUATOR_SOURCE = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux file lock and owner-private paths')


def _command() -> list[str]:
    return [sys.executable, '-I', '-c',
            'import sys;sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[2]);'
            'from work_queue.cli import main;raise SystemExit(main())',
            str(SOURCE), str(EVALUATOR_SOURCE)]


def test_queue_source_review_matches_independently_frozen_files():
    review = read_json(REVIEW)
    assert review['qualification'] == {'platform': 'linux-x86_64-cpython3.13',
                                       'mode': 'off', 'provider_contacted': False,
                                       'activation_authorized': False,
                                       'measured_benefit': False}
    for relative, expected in review['files'].items():
        assert file_hash(ROOT / relative) == expected
    inventory = scan_repo(ROOT, load_config())
    candidate = next(row for row in inventory['candidates']
                     if row['source']['symbol'] == 'choose_operation')
    assert candidate['candidate_id'] == review['candidate']['id']
    assert candidate['pattern'] == review['candidate']['pattern'] == 'C'
    assert candidate['source']['source_sha256'] == review['candidate']['source_sha256']
    assert candidate['source']['file_sha256'] == review['candidate']['file_sha256']


@pytest.mark.parametrize('case', read_json(ORACLE)['cases'], ids=lambda row: row['id'])
def test_authored_queue_oracle_before_template(tmp_path, case):
    evidence = tmp_path / 'evidence'
    evidence.mkdir(mode=0o700)
    env = {**os.environ, 'WORK_QUEUE_EFFECTS': str(evidence / 'effects.jsonl'),
           'WORK_QUEUE_AUDIT': str(evidence / 'audit.jsonl'),
           'WORK_QUEUE_JOB_ID': case['job_id'], 'WORK_QUEUE_ITEM': case['item'],
           'WORK_QUEUE_INTENT': case['intent'], 'WORK_QUEUE_ALLOWED': case['allowed'],
           'WORK_QUEUE_COMPLETE_ALLOWED': case['complete_allowed']}
    exits = [subprocess.run(_command(), cwd=tmp_path, env=env,
                            capture_output=True, timeout=10).returncode
             for _ in case['expected_exits']]
    assert exits == case['expected_exits']
    path = evidence / 'effects.jsonl'
    observed = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    assert observed == case['expected_effects']
    assert not (evidence / 'audit.jsonl').exists()


def test_queue_bind_render_plan_verify_on_disposable_copy(tmp_path, monkeypatch):
    host = tmp_path / 'host'
    shutil.copytree(ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    request, binding = source_matched_request(host)
    bound = prepare_template_binding(host, request, binding)['request']
    spec = bound['implementation_spec']
    assert spec['entrypoint_binding']['script'] == 'work-queue'
    assert spec['source']['source_sha256'] == read_json(REVIEW)['candidate']['source_sha256']
    rendered = materialize_template(host, bound, tmp_path / 'render')
    assert rendered['target_executed'] is False and rendered['target_modified'] is False
    bundle = tmp_path / 'bundle'
    plan = plan_implementation(host, bound['reviewed_inventory'], spec['candidate_id'],
                               spec, bundle)
    assert plan['status'] == 'planned'
    probe = tmp_path / 'probe'
    probe.mkdir(mode=0o700)
    monkeypatch.setenv('WORK_QUEUE_PROBE_EFFECTS_DIR', str(probe))
    baseline = verify_implementation(host, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed', baseline
    apply_implementation(host, bundle, plan['bundle_digest'],
                         baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(host, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified', modified
