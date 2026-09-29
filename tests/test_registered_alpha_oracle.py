"""Independent host effects are observed from its normal caller, before integration."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

from jev_integration_evaluator.io import InputError, file_hash, read_json
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.template_catalog import prepare_template_binding, materialize_template
from jev_integration_evaluator.integrations.lifecycle import (
    plan_implementation, apply_implementation, implementation_status,
    rollback_implementation)
from jev_integration_evaluator.integrations import lifecycle
from jev_integration_evaluator.integrations.verification import verify_implementation
from tests.independent_hosts.registered_alpha.qualification import source_matched_request


ROOT = Path(__file__).resolve().parent / 'independent_hosts' / 'registered_alpha'
SOURCE = ROOT / 'src'
ORACLE = ROOT / 'oracle-v1.json'
REVIEW = ROOT / 'review-v1.json'
EVALUATOR_SOURCE = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='POSIX file lock and owner-private paths')


def _environment(private: Path, **choices: str) -> dict[str, str]:
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(private, 0o700)
    values = os.environ.copy()
    values.update({'REGISTERED_ALPHA_EFFECTS': str(private / 'effects.jsonl'),
                   'REGISTERED_ALPHA_AUDIT': str(private / 'audit.jsonl'), **choices})
    return values


def _command() -> list[str]:
    return [sys.executable, '-I', '-c',
            'import sys;sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[2]);'
            'from registered_alpha.console import main;raise SystemExit(main())',
            str(SOURCE), str(EVALUATOR_SOURCE)]


def _effects(private: Path) -> list[dict]:
    path = private / 'effects.jsonl'
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def test_frozen_source_review_and_oracle_are_current():
    review = read_json(REVIEW)
    assert review['status'] == 'source_reviewed_for_offline_qualification'
    assert review['qualification']['activation_authorized'] is False
    assert review['qualification']['provider_contacted'] is False
    assert set(review['semantic_review']['legal_actions']) == {'inspect', 'summarize'}
    for relative, expected in review['files'].items():
        assert file_hash(ROOT / relative) == expected
    inventory = scan_repo(ROOT, load_config())
    candidate = next(c for c in inventory['candidates']
                     if c['source']['symbol'] == review['candidate']['symbol'])
    assert candidate['candidate_id'] == review['candidate']['id']
    assert candidate['pattern'] == review['candidate']['pattern'] == 'C'
    assert candidate['source']['source_sha256'] == review['candidate']['source_sha256']
    assert candidate['source']['file_sha256'] == review['candidate']['file_sha256']


def test_alpha_source_bound_template_bind_render_and_plan(tmp_path):
    request, binding = source_matched_request()
    original = {name: file_hash(ROOT / name) for name in (
        'pyproject.toml', 'src/registered_alpha/host.py',
        'src/registered_alpha/console.py', 'src/registered_alpha/requirements.lock',
        'src/registered_alpha/runtime.json')}
    bound = prepare_template_binding(ROOT, request, binding)
    assert bound['binding_report']['status'] == 'planned_not_applied'
    spec = bound['request']['implementation_spec']
    assert spec['entrypoint_binding']['script'] == 'registered-alpha'
    assert spec['source']['source_sha256'] == read_json(REVIEW)['candidate']['source_sha256']
    rendered = materialize_template(ROOT, bound['request'], tmp_path / 'render')
    assert rendered['target_executed'] is False
    assert rendered['target_modified'] is False
    planned = plan_implementation(ROOT, read_json(tmp_path / 'render/reviewed-inventory.json'),
                                  spec['candidate_id'],
                                  read_json(tmp_path / 'render/implementation-spec.json'),
                                  tmp_path / 'plan')
    assert planned['status'] == 'planned'
    assert planned['target_modified'] is False
    assert {name: file_hash(ROOT / name) for name in original} == original


def test_alpha_reviewed_source_verification_on_disposable_copy(tmp_path, monkeypatch):
    host = tmp_path / 'host'
    shutil.copytree(ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    request, binding = source_matched_request(host)
    bound = prepare_template_binding(host, request, binding)['request']
    materialize_template(host, bound, tmp_path / 'render')
    spec = bound['implementation_spec']
    bundle = tmp_path / 'implementation'
    plan = plan_implementation(host, bound['reviewed_inventory'], spec['candidate_id'],
                               spec, bundle)
    probe = tmp_path / 'probe-effects'
    probe.mkdir(mode=0o700)
    monkeypatch.setenv('REGISTERED_ALPHA_PROBE_EFFECTS_DIR', str(probe))
    baseline = verify_implementation(host, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed', baseline
    apply_implementation(host, bundle, plan['bundle_digest'],
                         baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(host, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified', modified
    assert file_hash(ROOT / 'src/registered_alpha/host.py') == read_json(REVIEW)['files'][
        'src/registered_alpha/host.py']


def test_alpha_interrupted_apply_retains_recovery_and_owned_rollback(tmp_path, monkeypatch):
    host = tmp_path / 'host'
    shutil.copytree(ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    request, binding = source_matched_request(host)
    bound = prepare_template_binding(host, request, binding)['request']
    materialize_template(host, bound, tmp_path / 'render')
    spec = bound['implementation_spec']
    bundle = tmp_path / 'implementation'
    plan = plan_implementation(host, bound['reviewed_inventory'], spec['candidate_id'],
                               spec, bundle)
    baseline_source = {name: file_hash(host / name) for name in (
        'pyproject.toml', 'src/registered_alpha/host.py',
        'src/registered_alpha/console.py')}
    probe = tmp_path / 'probe-effects'
    probe.mkdir(mode=0o700)
    monkeypatch.setenv('REGISTERED_ALPHA_PROBE_EFFECTS_DIR', str(probe))
    baseline = verify_implementation(host, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    original_record = lifecycle._record

    def interrupt_after_intent(directory, current_plan, event, *extra):
        original_record(directory, current_plan, event, *extra)
        if event == 'apply_started':
            raise KeyboardInterrupt('alpha_apply_interrupted_after_durable_intent')

    monkeypatch.setattr(lifecycle, '_record', interrupt_after_intent)
    with pytest.raises(KeyboardInterrupt, match='alpha_apply_interrupted'):
        apply_implementation(host, bundle, plan['bundle_digest'],
                             baseline_sha256=baseline['receipt_sha256'])
    monkeypatch.setattr(lifecycle, '_record', original_record)
    pending = implementation_status(host, bundle)
    assert pending['status'] == 'blocked_recovery'
    with pytest.raises(InputError, match='recovery/rollback'):
        apply_implementation(host, bundle, plan['bundle_digest'],
                             baseline_sha256=baseline['receipt_sha256'])
    rolled = rollback_implementation(host, bundle, pending['rollback_digest'])
    assert rolled['status'] == 'rolled_back'
    assert {name: file_hash(host / name) for name in baseline_source} == baseline_source


@pytest.mark.parametrize('case', read_json(ORACLE)['cases'], ids=lambda case: case['id'])
def test_frozen_independent_baseline_and_effects(tmp_path, case):
    private = tmp_path / 'evidence'
    values = _environment(private, REGISTERED_ALPHA_TASK_ID=case['task_id'],
                          REGISTERED_ALPHA_INTENT=case['intent'], REGISTERED_ALPHA_ITEM=case['item'],
                          REGISTERED_ALPHA_PERMIT=case['permit'], REGISTERED_ALPHA_APPROVED=case['approved'])
    observed = []
    for expected in case['expected_exits']:
        process = subprocess.run(_command(), cwd=tmp_path, env=values,
                                 capture_output=True, text=True, timeout=10)
        observed.append(process.returncode)
        assert process.returncode == expected
    assert observed == case['expected_exits']
    assert _effects(private) == case['expected_effects']
    if case['expected_effects']:
        assert file_hash(private / 'effects.jsonl')
    assert not (private / 'audit.jsonl').exists(), 'off baseline must not create model audit'


def test_interrupted_live_action_has_no_effect(tmp_path):
    private = tmp_path / 'evidence'
    values = _environment(private, REGISTERED_ALPHA_TASK_ID='alpha-cancel-1',
                          REGISTERED_ALPHA_HOLD='1', REGISTERED_ALPHA_READY=str(private / 'ready'),
                          REGISTERED_ALPHA_RELEASE=str(private / 'release'))
    process = subprocess.Popen(_command(), cwd=tmp_path, env=values,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 8
        while not (private / 'ready').exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert process.poll() is None and (private / 'ready').is_file()
        assert _effects(private) == []
        process.terminate()
        assert process.wait(timeout=5) != 0
        assert _effects(private) == []
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=5)


@pytest.mark.parametrize('name,value', [('REGISTERED_ALPHA_INTENT', 'delete'),
                                        ('REGISTERED_ALPHA_ITEM', 'other'),
                                        ('REGISTERED_ALPHA_TASK_ID', '../escape'),
                                        ('REGISTERED_ALPHA_PERMIT', 'yes'),
                                        ('REGISTERED_ALPHA_APPROVED', 'yes')])
def test_invalid_caller_input_has_no_effect(tmp_path, name, value):
    private = tmp_path / 'evidence'
    values = _environment(private, **{name: value})
    process = subprocess.run(_command(), cwd=tmp_path, env=values,
                             capture_output=True, text=True, timeout=10)
    assert process.returncode != 0
    assert _effects(private) == []
