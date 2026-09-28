"""Independent owned JS/TS bundle against real edited entrypoints; synthetic only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from jev_integration_evaluator.integrations import js_lifecycle as js
from jev_integration_evaluator.integrations.js_lifecycle import (
    apply_js, plan_js, recover_js, rollback_js, status_js, verify_js,
)
from jev_integration_evaluator.io import InputError, atomic_text, digest, file_hash

TOOLING = Path(__file__).resolve().parents[1]
PINNED = TOOLING / 'node_modules/typescript/lib/typescript.js'
pytestmark = pytest.mark.skipif(os.name != 'posix' or shutil.which('node') is None or not PINNED.is_file(),
                                reason='Native POSIX and trusted Node/TypeScript 5.8.3 tooling required')


def fixture(tmp_path, format_name):
    root = tmp_path / 'host'; root.mkdir()
    suffix = {'esm': '.mjs', 'commonjs': '.cjs', 'typescript': '.ts'}[format_name]
    typed = format_name == 'typescript'
    selected = ('export async function seam(request: {task_id:string, invocation_id:string, item:string, permit:boolean}): Promise<string> '
                if typed else 'export async function seam(request) '
                if format_name == 'esm' else 'async function seam(request) ')
    original = ('async function original(request: {item:string}): Promise<string> '
                if typed else 'async function original(request) ')
    source = ('export const events = [];\n' if format_name != 'commonjs' else 'const events = [];\n')
    source += selected + '{ return await original(request); }\n'
    source += original + "{ events.push(['read', request.item]); globalThis.__jev_probe_effect?.('read', request.item); return 'read:' + request.item; }\n"
    source += '''function hostRegistry(request) { return {read: original}; }
function hostGate(request, action) { return {allowed_actions: ['read'], baseline_permitted: true}; }
function hostValidate(request, action) { return request.permit === true; }
function hostBlocked(request, reason) { return 'blocked'; }
function hostEvidence(request) { return {item: request.item}; }
function hostBaseline(request) { return 'read'; }
'''
    if format_name == 'commonjs':
        source += 'module.exports = seam;\nmodule.exports.events = events;\n'
    path = root / ('host' + suffix); path.write_text(source, encoding='utf-8')
    cases = [dict(id='read', request=dict(task_id='task', invocation_id='one', item='x', permit=True),
                  result='read:x', events=[['read', 'x']], effects=[['read', 'x']])]
    spec = dict(schema_version='1.0', recipe_id='javascript.C', candidate_id='synthetic-reviewed-C',
                source=dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            symbol='seam', original='original'),
                bindings=dict(registry='hostRegistry', gate='hostGate', validate='hostValidate',
                              blocked='hostBlocked', evidence='hostEvidence', baseline_action='hostBaseline'),
                runtime=dict(registered_action_ids=['read'],
                             questions=dict(choice=dict(type='choice', criteria=dict(read='Read', uncertain='Unclear'))),
                             primary_question='choice', label_actions=dict(read='read', uncertain=None),
                             runtime=dict(mode='off', canary_scope='synthetic', cost_upper_bound=1,
                                          timeout_ms=40, model='model-v1')),
                verification_sha256=digest(cases), verification_cases_count=len(cases))
    return root, path, spec, cases


@pytest.mark.parametrize('format_name', ['esm', 'commonjs', 'typescript'])
def test_owned_plan_baseline_apply_modified_and_rollback(tmp_path, format_name):
    root, source, spec, cases = fixture(tmp_path, format_name)
    original = source.read_bytes()
    bundle = tmp_path / 'bundle'
    plan = plan_js(root, spec, bundle, tooling_dir=TOOLING)
    assert plan['status'] == 'planned' and source.read_bytes() == original
    assert status_js(root, bundle, tooling_dir=TOOLING)['status'] == 'planned'
    with pytest.raises(InputError, match='explicit authorization'):
        verify_js(root, bundle, 'baseline', cases, tooling_dir=TOOLING)
    baseline = verify_js(root, bundle, 'baseline', cases, tooling_dir=TOOLING,
                         approve_execution=True)
    assert baseline['status'] == 'passed'
    with pytest.raises(InputError, match='receipt differs'):
        apply_js(root, bundle, plan['bundle_sha256'], baseline_sha256='0' * 64, tooling_dir=TOOLING)
    applied = apply_js(root, bundle, plan['bundle_sha256'],
                       baseline_sha256=baseline['receipt_sha256'], tooling_dir=TOOLING)
    assert applied['status'] == 'applied_unverified' and source.read_bytes() != original
    assert (root / 'jev_runtime.cjs').is_file() and (root / 'jev_adapter.cjs').is_file()
    if format_name == 'typescript':
        assert (root / 'host.mjs').is_file()
    modified = verify_js(root, bundle, 'modified', cases, tooling_dir=TOOLING,
                         baseline_sha256=baseline['receipt_sha256'], approve_execution=True)
    assert modified['status'] == 'passed'
    assert status_js(root, bundle, tooling_dir=TOOLING)['receipt_trust'] == 'integrity_consistent_but_unverified'
    verified = status_js(root, bundle, tooling_dir=TOOLING,
                         trusted_modified_sha256=modified['receipt_sha256'])
    assert verified['status'] == 'verified'
    rolled = rollback_js(root, bundle, verified['rollback_digest'], tooling_dir=TOOLING)
    assert rolled['status'] == 'rolled_back' and source.read_bytes() == original
    assert not (root / 'jev_runtime.cjs').exists() and not (root / 'jev_adapter.cjs').exists()
    assert status_js(root, bundle, tooling_dir=TOOLING)['status'] == 'rolled_back'


def test_source_drift_and_output_collision_fail_before_mutation(tmp_path):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    source.write_bytes(source.read_bytes() + b'\n// owner edit\n')
    with pytest.raises(InputError, match='source changed'):
        plan_js(root, spec, tmp_path / 'bundle', tooling_dir=TOOLING)
    assert not (tmp_path / 'bundle').exists()
    source.write_bytes(source.read_bytes().replace(b'\n// owner edit\n', b''))
    (root / 'jev_adapter.cjs').write_text('owner file\n')
    with pytest.raises(InputError, match='collides'):
        plan_js(root, spec, tmp_path / 'bundle', tooling_dir=TOOLING)
    assert (root / 'jev_adapter.cjs').read_text() == 'owner file\n'


def test_bundle_tooling_and_receipt_tamper_fail_closed(tmp_path):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    bundle = tmp_path / 'bundle'; plan_js(root, spec, bundle, tooling_dir=TOOLING)
    (bundle / 'patch.json').write_bytes((bundle / 'patch.json').read_bytes() + b' ')
    with pytest.raises(InputError):
        status_js(root, bundle, tooling_dir=TOOLING)


def test_baseline_receipt_byte_tamper_blocks_apply(tmp_path):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    bundle = tmp_path / 'bundle'; plan = plan_js(root, spec, bundle, tooling_dir=TOOLING)
    baseline = verify_js(root, bundle, 'baseline', cases, tooling_dir=TOOLING,
                         approve_execution=True)
    receipt = bundle / 'baseline-receipt.json'
    receipt.write_bytes(receipt.read_bytes() + b' ')
    with pytest.raises(InputError, match='external digest'):
        apply_js(root, bundle, plan['bundle_sha256'],
                 baseline_sha256=baseline['receipt_sha256'], tooling_dir=TOOLING)
    assert source.read_bytes() == (bundle / 'source-preimage.utf8').read_bytes()


def test_unsupported_recipe_rejected_before_target_mutation(tmp_path):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    original = source.read_bytes()
    spec['recipe_id'] = 'javascript.E'
    with pytest.raises(InputError, match='javascript-implementation-spec-v1'):
        plan_js(root, spec, tmp_path / 'bundle', tooling_dir=TOOLING)
    assert source.read_bytes() == original


def test_unregistered_label_action_rejected_before_mutation(tmp_path):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    spec['runtime']['label_actions']['read'] = 'delete'
    with pytest.raises(InputError, match='finite JavaScript runtime'):
        plan_js(root, spec, tmp_path / 'bundle', tooling_dir=TOOLING)
    assert not (tmp_path / 'bundle').exists()


def test_interrupted_baseline_needs_external_receipt_anchor(tmp_path, monkeypatch):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    bundle = tmp_path / 'bundle'; plan = plan_js(root, spec, bundle, tooling_dir=TOOLING)
    append = js._append

    def interrupted(directory, record, event):
        if event == 'baseline_passed':
            raise KeyboardInterrupt()
        return append(directory, record, event)

    monkeypatch.setattr(js, '_append', interrupted)
    with pytest.raises(KeyboardInterrupt):
        verify_js(root, bundle, 'baseline', cases, tooling_dir=TOOLING, approve_execution=True)
    monkeypatch.setattr(js, '_append', append)
    assert status_js(root, bundle, tooling_dir=TOOLING)['status'] == 'blocked_recovery'
    with pytest.raises(InputError, match='external digest'):
        recover_js(root, bundle, 'baseline', tooling_dir=TOOLING,
                   trusted_receipt_sha256='0' * 64)
    anchor = file_hash(bundle / 'baseline-receipt.json')
    recovered = recover_js(root, bundle, 'baseline', tooling_dir=TOOLING,
                           trusted_receipt_sha256=anchor)
    assert recovered['status'] == 'planned'
    assert apply_js(root, bundle, plan['bundle_sha256'], baseline_sha256=anchor,
                    tooling_dir=TOOLING)['status'] == 'applied_unverified'


def test_partial_apply_rollback_preserves_unrelated_source(tmp_path, monkeypatch):
    root, source, spec, cases = fixture(tmp_path, 'commonjs')
    original = source.read_bytes(); other = root / 'owner.txt'; other.write_text('owner\n')
    bundle = tmp_path / 'bundle'; plan_js(root, spec, bundle, tooling_dir=TOOLING)
    baseline = verify_js(root, bundle, 'baseline', cases, tooling_dir=TOOLING,
                         approve_execution=True)

    def partial(target, patch, approval):
        first = patch['changes'][0]
        atomic_text(target / first['file'], first['new_content'])
        raise KeyboardInterrupt()

    monkeypatch.setattr(js, 'apply_patch_plan', partial)
    with pytest.raises(KeyboardInterrupt):
        apply_js(root, bundle, json.loads((bundle / 'plan.json').read_text())['contract_digest'],
                 baseline_sha256=baseline['receipt_sha256'], tooling_dir=TOOLING)
    assert status_js(root, bundle, tooling_dir=TOOLING)['status'] == 'blocked_recovery'
    approval = status_js(root, bundle, tooling_dir=TOOLING)['rollback_digest']
    assert rollback_js(root, bundle, approval, tooling_dir=TOOLING)['status'] == 'rolled_back'
    assert source.read_bytes() == original and other.read_text() == 'owner\n'


def test_public_cli_plan_and_status_do_not_execute_target(tmp_path):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    original = source.read_bytes()
    spec_path = tmp_path / 'reviewed-spec.json'
    spec_path.write_text(json.dumps(spec), encoding='utf-8')
    bundle = tmp_path / 'bundle'
    command = [sys.executable, '-m', 'jev_integration_evaluator', 'js-plan',
               '--repo', str(root), '--spec', str(spec_path), '--bundle', str(bundle),
               '--tooling', str(TOOLING)]
    planned = subprocess.run(command, cwd=TOOLING, capture_output=True, text=True, timeout=30, check=True)
    assert json.loads(planned.stdout)['status'] == 'planned'
    checked = subprocess.run([sys.executable, '-m', 'jev_integration_evaluator', 'js-status',
                              '--repo', str(root), '--bundle', str(bundle), '--tooling', str(TOOLING)],
                             cwd=TOOLING, capture_output=True, text=True, timeout=30, check=True)
    assert json.loads(checked.stdout)['status'] == 'planned'
    assert source.read_bytes() == original


def test_public_support_matrix_distinguishes_discovery_and_runtime(tmp_path):
    done = subprocess.run([sys.executable, '-m', 'jev_integration_evaluator', 'js-support'],
                          cwd=TOOLING, capture_output=True, text=True, timeout=10, check=True)
    matrix = json.loads(done.stdout)
    assert matrix['supported_recipe'] == 'C'
    assert set(matrix['unsupported_recipes']) == set('ABCDEFGHIJKLM') - {'C'}
    assert matrix['discovery_js_ts'] == 'unparsed_by_this_contract'
    assert matrix['target_verified'] is False
    assert matrix['activation_authorized'] is False


def test_competing_bundle_owner_cannot_advance_journal(tmp_path):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    bundle = tmp_path / 'bundle'; plan_js(root, spec, bundle, tooling_dir=TOOLING)
    with js._lock(bundle):
        with pytest.raises(InputError, match='owns the lock'):
            status_js(root, bundle, tooling_dir=TOOLING)
        with pytest.raises(InputError, match='owns the lock'):
            verify_js(root, bundle, 'baseline', cases, tooling_dir=TOOLING,
                      approve_execution=True)
    assert status_js(root, bundle, tooling_dir=TOOLING)['status'] == 'planned'


def test_distinct_bundle_cannot_apply_while_another_owns_target(tmp_path):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    first, second = tmp_path / 'first', tmp_path / 'second'
    plan_js(root, spec, first, tooling_dir=TOOLING)
    second_plan = plan_js(root, spec, second, tooling_dir=TOOLING)
    baseline = verify_js(root, second, 'baseline', cases, tooling_dir=TOOLING,
                         approve_execution=True)
    original = source.read_bytes()
    with js._lock(first), js._target_lock(root):
        with pytest.raises(InputError, match='owns this target'):
            apply_js(root, second, second_plan['bundle_sha256'],
                     baseline_sha256=baseline['receipt_sha256'], tooling_dir=TOOLING)
    assert source.read_bytes() == original
    assert apply_js(root, second, second_plan['bundle_sha256'],
                    baseline_sha256=baseline['receipt_sha256'],
                    tooling_dir=TOOLING)['status'] == 'applied_unverified'


def test_probe_owned_effect_oracle_catches_duplicate_effect(tmp_path):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    text = source.read_text()
    needle = "globalThis.__jev_probe_effect?.('read', request.item);"
    assert text.count(needle) == 1
    source.write_text(text.replace(needle, needle + needle))
    spec['source']['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    bundle = tmp_path / 'bundle'; plan_js(root, spec, bundle, tooling_dir=TOOLING)
    receipt = verify_js(root, bundle, 'baseline', cases, tooling_dir=TOOLING,
                        approve_execution=True)
    assert receipt['status'] == 'failed'
    assert status_js(root, bundle, tooling_dir=TOOLING)['status'] == 'verification_failed'


def test_modified_failure_is_not_reported_as_applied_success(tmp_path, monkeypatch):
    root, source, spec, cases = fixture(tmp_path, 'esm')
    bundle = tmp_path / 'bundle'; plan = plan_js(root, spec, bundle, tooling_dir=TOOLING)
    baseline = verify_js(root, bundle, 'baseline', cases, tooling_dir=TOOLING,
                         approve_execution=True)
    apply_js(root, bundle, plan['bundle_sha256'], baseline_sha256=baseline['receipt_sha256'],
             tooling_dir=TOOLING)
    probe = js._probe_run
    def wrong_effect(*args, **kwargs):
        result = probe(*args, **kwargs)
        result['results'][0]['effects'].append(['read', 'duplicate'])
        return result
    monkeypatch.setattr(js, '_probe_run', wrong_effect)
    modified = verify_js(root, bundle, 'modified', cases, tooling_dir=TOOLING,
                         baseline_sha256=baseline['receipt_sha256'], approve_execution=True)
    assert modified['status'] == 'failed'
    assert status_js(root, bundle, tooling_dir=TOOLING)['status'] == 'verification_failed'
