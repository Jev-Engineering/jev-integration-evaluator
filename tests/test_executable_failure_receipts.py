"""Missing/corrupt scheduled execution remains failure evidence, never a passing claim."""
import copy
from pathlib import Path
import sys

import pytest

from jev_integration_evaluator.integrations import verification as verifier
from jev_integration_evaluator.integrations.lifecycle import (
    _load, apply_implementation, implementation_status, plan_implementation,
    rollback_implementation,
)
from jev_integration_evaluator.io import InputError, read_json
from scripts.implementation_fixtures import fixture


@pytest.fixture
def prepared(tmp_path):
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C')
    plan = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    return root, bundle, spec, plan


def test_null_probe_output_cannot_pass_a_baseline(prepared, monkeypatch):
    root, bundle, spec, _ = prepared
    def null_output(root, command, **kwargs):
        Path(command[-1]).write_text('null', encoding='utf-8')
        return {'status': 'passed', 'returncode': 0}
    monkeypatch.setattr(verifier, 'run_authorized_tests', null_output)
    result = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert result['status'] == 'verification_failed'
    receipt = read_json(bundle/'baseline-receipt.json')
    assert receipt['scheduled_cases'] == receipt['completed_cases'] == len(spec['verification']['cases'])
    assert all(r['status'] == 'failed' and r['observation'] is None for r in receipt['results'])


@pytest.mark.parametrize('corruption', ['empty', 'list', 'missing_calls', 'negative_counter',
                                      'bool_counter', 'unknown_field', 'bad_trace', 'bad_outcome',
                                      'nonfinite', 'unknown_role', 'wrong_arity'])
def test_bad_observations_produce_complete_failed_receipts(prepared, monkeypatch, corruption):
    root, bundle, spec, _ = prepared
    loaded = _load(root, bundle)[2]
    observation, status = verifier._probe(root, bundle, loaded, spec, spec['verification']['cases'][0], 'baseline')
    assert status == 'passed'
    broken = copy.deepcopy(observation)
    if corruption == 'empty': broken = {}
    elif corruption == 'list': broken = []
    elif corruption == 'missing_calls': broken.pop('calls')
    elif corruption == 'negative_counter': broken['adapter_calls'] = -1
    elif corruption == 'bool_counter': broken['model_calls'] = True
    elif corruption == 'unknown_field': broken['unreviewed'] = 'PRIVATE_SENTINEL'
    elif corruption == 'bad_trace': broken['trace'] = [{'role':'gate','event':'call','args':[]}]
    elif corruption == 'bad_outcome': broken['outcome']['exception'] = 9
    elif corruption == 'nonfinite': broken['globals']['invalid'] = float('nan')
    elif corruption == 'unknown_role': broken['trace'] = [{'role':'risk','event':'return','result':{}}]
    elif corruption == 'wrong_arity': broken['trace'] = [{'role':'gate','event':'call','args':[{}]}]
    monkeypatch.setattr(verifier, '_probe', lambda *a, **kw: (copy.deepcopy(broken), 'passed'))
    result = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert result['status'] == 'verification_failed'
    receipt = read_json(bundle/'baseline-receipt.json')
    assert receipt['scheduled_cases'] == receipt['completed_cases'] == len(spec['verification']['cases'])
    assert all(r['status'] == 'failed' and r['observation'] is None for r in receipt['results'])
    assert 'PRIVATE_SENTINEL' not in (bundle/'baseline-receipt.json').read_text()


@pytest.mark.parametrize('phase', ['baseline', 'modified'])
def test_missing_scheduled_command_is_not_run_and_blocks_pass(tmp_path, phase):
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C')
    spec['verification'][phase+'_command'] = [str(tmp_path/'not-an-installed-runner')]
    plan = plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    baseline_hash = applied = None
    if phase == 'modified':
        baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'baseline_passed'
        baseline_hash = baseline['receipt_sha256']
        applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline_hash)
    try:
        result = verifier.verify_implementation(root, bundle, phase, approve_execution=True, baseline_sha256=baseline_hash)
        assert result['status'] == 'verification_failed'
        receipt = read_json(bundle/('baseline-receipt.json' if phase == 'baseline' else 'verification-receipt.json'))
        expected = len(spec['verification']['cases']) * (1 if phase == 'baseline' else 3)
        assert receipt['scheduled_cases'] == receipt['completed_cases'] == expected
        assert all(row['status'] == 'passed' for row in receipt['results'])
        assert receipt['command_checks'][0]['status'] == 'not_run'
        assert receipt['command_checks'][0]['returncode'] is None
        if phase == 'baseline':
            with pytest.raises(InputError, match='Baseline verification did not pass'):
                apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=result['receipt_sha256'])
        else:
            assert implementation_status(root, bundle, trusted_receipt_sha256=result['receipt_sha256'])['status'] == 'verification_failed'
    finally:
        if applied:
            assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'


@pytest.mark.parametrize('phase', ['baseline', 'modified'])
def test_unlaunchable_command_arguments_rejected_before_bundle(tmp_path, phase):
    root, bundle = tmp_path/'target', tmp_path/'bundle'
    inventory, spec = fixture(root, 'C')
    original = {p.name:p.read_bytes() for p in root.iterdir()}
    spec['verification'][phase+'_command'] = [sys.executable, 'bad\x00argument']
    with pytest.raises(InputError, match='command'):
        plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert not bundle.exists()
    assert {p.name:p.read_bytes() for p in root.iterdir()} == original


def test_interrupted_reverification_does_not_reuse_old_success(prepared, monkeypatch):
    root, bundle, spec, plan = prepared
    baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
    success = verifier.verify_implementation(root, bundle, 'modified', approve_execution=True,
                                             baseline_sha256=baseline['receipt_sha256'])
    assert success['status'] == 'verified'
    def interrupted(*a, **kw):
        raise KeyboardInterrupt('deliberate test interruption')
    real_probe = verifier._probe
    monkeypatch.setattr(verifier, '_probe', interrupted)
    try:
        with pytest.raises(KeyboardInterrupt):
            verifier.verify_implementation(root, bundle, 'modified', approve_execution=True,
                                           baseline_sha256=baseline['receipt_sha256'])
        status = implementation_status(root, bundle, trusted_receipt_sha256=success['receipt_sha256'])
        assert status['status'] == 'blocked_recovery'
        assert read_json(bundle/'verification-receipt.json')['status'] == 'passed'  # Kept as historical evidence.
        monkeypatch.setattr(verifier, '_probe', real_probe)
        recovered = verifier.verify_implementation(root, bundle, 'modified', approve_execution=True,
                                                   baseline_sha256=baseline['receipt_sha256'])
        assert recovered['status'] == 'verified'
        assert implementation_status(root, bundle, trusted_receipt_sha256=recovered['receipt_sha256'])['status'] == 'verified'
    finally:
        assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'


@pytest.mark.parametrize('interruption', ['keyboard_interrupt', 'process_exit'])
def test_interrupted_baseline_reverification_blocks_old_receipt_and_recovers(prepared, monkeypatch, interruption):
    import subprocess
    root, bundle, spec, plan = prepared
    baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    before = {p.name:p.read_bytes() for p in root.iterdir()}
    receipt_before = (bundle/'baseline-receipt.json').read_bytes()
    real_probe = verifier._probe
    if interruption == 'keyboard_interrupt':
        def interrupted(*a, **kw):
            raise KeyboardInterrupt('deliberate baseline test interruption')
        monkeypatch.setattr(verifier, '_probe', interrupted)
        with pytest.raises(KeyboardInterrupt):
            verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
        monkeypatch.setattr(verifier, '_probe', real_probe)
    else:
        checkout = str(Path(__file__).resolve().parents[1])
        code = '''import os,sys
sys.path.insert(0,sys.argv[1])
from jev_integration_evaluator.integrations import verification
verification._probe=lambda *a,**kw: os._exit(23)
verification.verify_implementation(sys.argv[2],sys.argv[3],'baseline',approve_execution=True)
'''
        run = subprocess.run([sys.executable, '-I', '-c', code, checkout, str(root), str(bundle)],
                             cwd=root.parent, capture_output=True, text=True, timeout=30)
        assert run.returncode == 23, run.stderr
    assert (bundle/'baseline-receipt.json').read_bytes() == receipt_before
    assert implementation_status(root, bundle)['status'] == 'blocked_recovery'
    with pytest.raises(InputError, match='recovery'):
        apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
    assert {p.name:p.read_bytes() for p in root.iterdir()} == before
    with pytest.raises(InputError, match='execution'):
        verifier.verify_implementation(root, bundle, 'baseline')
    assert implementation_status(root, bundle)['status'] == 'blocked_recovery'
    recovered = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert recovered['status'] == 'baseline_passed'
    assert implementation_status(root, bundle)['status'] == 'planned'
    applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=recovered['receipt_sha256'])
    assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'


def test_baseline_verification_preserves_rolled_back_disposition(prepared):
    root, bundle, spec, plan = prepared
    baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
    assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
    repeated = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert repeated['status'] == 'baseline_passed'
    assert implementation_status(root, bundle)['status'] == 'rolled_back'
    with pytest.raises(InputError, match='recovery'):
        apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=repeated['receipt_sha256'])


def test_baseline_verification_does_not_clear_incomplete_mutation(prepared):
    from jev_integration_evaluator.integrations.lifecycle import _record
    root, bundle, spec, plan = prepared
    loaded = _load(root, bundle)[2]
    _record(bundle, loaded, 'apply_failed_recovery_required')
    baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    assert implementation_status(root, bundle)['status'] == 'blocked_recovery'
    with pytest.raises(InputError, match='recovery'):
        apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])


@pytest.mark.parametrize('phase', ['baseline', 'modified'])
def test_receipt_byte_budget_counts_pretty_json_and_retains_failed_schedule(prepared, monkeypatch, phase):
    from jev_integration_evaluator.io import canonical
    root, bundle, spec, plan = prepared
    real_probe = verifier._probe
    def observed_padding(*args, **kwargs):
        observation, status = real_probe(*args, **kwargs)
        # Small canonical data expands substantially at the receipt's nesting
        # depth, so this detects a bound that overlooks pretty JSON whitespace.
        observation['globals']['receipt_size_fixture'] = [0]*400
        return observation, status
    monkeypatch.setattr(verifier, '_probe', observed_padding)
    baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = None
    if phase == 'modified':
        applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
        normal = verifier.verify_implementation(root, bundle, phase, approve_execution=True,
                                                baseline_sha256=baseline['receipt_sha256'])
        assert normal['status'] == 'verified'
    path = bundle/('baseline-receipt.json' if phase == 'baseline' else 'verification-receipt.json')
    normal_receipt = read_json(path)
    compact_bytes = len(canonical(normal_receipt))
    byte_limit = (compact_bytes + path.stat().st_size)//2
    assert compact_bytes < byte_limit < path.stat().st_size
    monkeypatch.setattr(verifier, 'MAX_RECEIPT_BYTES', byte_limit, raising=False)
    try:
        limited = verifier.verify_implementation(root, bundle, phase, approve_execution=True,
                                                 baseline_sha256=baseline['receipt_sha256'] if applied else None)
        assert limited['status'] == 'verification_failed'
        receipt = read_json(path, max_bytes=byte_limit)
        expected = len(spec['verification']['cases'])*(3 if applied else 1)
        assert receipt['status'] == 'failed'
        assert receipt['scheduled_cases'] == receipt['completed_cases'] == expected
        assert len(receipt['results']) == expected
        discarded = [row for row in receipt['results'] if row['observation'] is None]
        assert discarded and all(row['status'] == 'failed' and row['assertions'] == []
                                 and row['diagnostic'] == 'receipt_size_limit' for row in discarded)
        assert receipt['contract_assertions'] == []
        if applied:
            assert implementation_status(root, bundle, trusted_receipt_sha256=limited['receipt_sha256'])['status'] == 'verification_failed'
        else:
            assert implementation_status(root, bundle)['status'] == 'planned'
            with pytest.raises(InputError, match='Baseline verification did not pass'):
                apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=limited['receipt_sha256'])
    finally:
        if applied:
            assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'


@pytest.mark.parametrize('status', ['timeout', 'not_run', 'failed', 'unknown'])
def test_unsuccessful_probe_cannot_promote_even_valid_observation(prepared, monkeypatch, status):
    root, bundle, spec, _ = prepared
    loaded = _load(root, bundle)[2]
    observation, _ = verifier._probe(root, bundle, loaded, spec, spec['verification']['cases'][0], 'baseline')
    monkeypatch.setattr(verifier, '_probe', lambda *a, **kw: (observation, status))
    result = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    assert result['status'] == 'verification_failed'
    receipt = read_json(bundle/'baseline-receipt.json')
    expected = status if status in ('timeout', 'not_run', 'failed') else 'failed'
    assert all(row['status'] == expected and row['observation'] is None for row in receipt['results'])
    assert receipt['completed_cases'] == (receipt['scheduled_cases'] if expected == 'failed' else 0)


@pytest.mark.parametrize('corruption', ['omitted', 'duplicate', 'mode', 'scheduled', 'completed', 'null_observation', 'command'])
def test_self_consistent_receipt_still_needs_its_actual_schedule(prepared, corruption):
    from jev_integration_evaluator.contracts import seal
    from jev_integration_evaluator.io import file_hash, write_json
    root, bundle, spec, plan = prepared
    baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    path = bundle/'baseline-receipt.json'
    receipt = read_json(path)
    if corruption == 'omitted': receipt['results'] = []
    elif corruption == 'duplicate': receipt['results'] *= 2
    elif corruption == 'mode': receipt['results'][0]['mode'] = 'off'
    elif corruption == 'scheduled': receipt['scheduled_cases'] += 1
    elif corruption == 'completed': receipt['completed_cases'] = 0
    elif corruption == 'null_observation': receipt['results'][0]['observation'] = None
    elif corruption == 'command': receipt['command_checks'] = [{'definition_sha256':'0'*64,'status':'passed','returncode':0}]
    write_json(path, seal(receipt))
    with pytest.raises(InputError):
        apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=file_hash(path))
    assert implementation_status(root, bundle)['status'] == 'planned'


def test_actual_process_exit_during_reverification_leaves_recovery_marker(prepared):
    import subprocess
    root, bundle, spec, plan = prepared
    baseline = verifier.verify_implementation(root, bundle, 'baseline', approve_execution=True)
    applied = apply_implementation(root, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
    success = verifier.verify_implementation(root, bundle, 'modified', approve_execution=True,
                                             baseline_sha256=baseline['receipt_sha256'])
    assert success['status'] == 'verified'
    checkout = str(Path(__file__).resolve().parents[1])
    code = '''import os,sys
sys.path.insert(0,sys.argv[1])
from jev_integration_evaluator.integrations import verification
verification._probe=lambda *a,**kw: os._exit(23)
verification.verify_implementation(sys.argv[2],sys.argv[3],'modified',approve_execution=True,baseline_sha256=sys.argv[4])
'''
    try:
        run = subprocess.run([sys.executable, '-I', '-c', code, checkout, str(root), str(bundle), baseline['receipt_sha256']],
                             cwd=root.parent, capture_output=True, text=True, timeout=30)
        assert run.returncode == 23, run.stderr
        assert implementation_status(root, bundle, trusted_receipt_sha256=success['receipt_sha256'])['status'] == 'blocked_recovery'
    finally:
        assert rollback_implementation(root, bundle, applied['rollback_digest'])['status'] == 'rolled_back'


def test_observation_contract_has_cli_validation_and_mirrored_schema(prepared, tmp_path):
    import subprocess
    from jev_integration_evaluator.io import write_json
    root, bundle, spec, _ = prepared
    loaded = _load(root, bundle)[2]
    observation, _ = verifier._probe(root, bundle, loaded, spec, spec['verification']['cases'][0], 'baseline')
    checkout = Path(__file__).resolve().parents[1]
    assert (checkout/'schemas/implementation-observation.schema.json').read_bytes() == (
        checkout/'jev_integration_evaluator/data/implementation-observation.schema.json').read_bytes()
    path = tmp_path/'observation.json'
    write_json(path, observation)
    command = [sys.executable,'-m','jev_integration_evaluator','validate','--kind','implementation-observation','--input',str(path)]
    assert subprocess.run(command,cwd=checkout,capture_output=True,timeout=30).returncode == 0
    write_json(path, {'private_detail':'PRIVATE_SENTINEL'})
    rejected = subprocess.run(command,cwd=checkout,capture_output=True,text=True,timeout=30)
    assert rejected.returncode == 2
    assert 'PRIVATE_SENTINEL' not in rejected.stdout + rejected.stderr
