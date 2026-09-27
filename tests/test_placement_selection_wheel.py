"""Installed selector checkpoint qualification, not full release/host qualification."""
import json
from pathlib import Path
import subprocess
import sys

from jev_integration_evaluator.io import digest, write_json
from jev_integration_evaluator.selection import selection_engine_sha256
from scripts.implementation_fixtures import fixture


def test_installed_selector_prepares_and_existing_lifecycle_verifies(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dist = tmp_path/'dist'; dist.mkdir()
    build = subprocess.run([sys.executable, '-c',
        'import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))', str(dist)],
        cwd=root, capture_output=True, text=True, timeout=90)
    assert build.returncode == 0, 'offline_checkpoint_wheel_build_failed'
    wheel = next(dist.glob('*.whl')); installed = tmp_path/'installed'
    install = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
                              '--target', str(installed), str(wheel)], capture_output=True, timeout=90)
    assert install.returncode == 0, 'offline_checkpoint_wheel_install_failed'
    host = tmp_path/'host'; inventory, spec = fixture(host, 'C', tag='installed_selection')
    request = {'schema_version': '1.0', 'selection_engine_sha256': selection_engine_sha256(),
        'mode': 'experimental', 'inventory_sha256': digest(inventory), 'candidate_id': spec['candidate_id'],
        'decision_review': {'reviewer': 'synthetic-wheel-test',
            'reason': 'Installed selector preparation, no observed application benefit.', 'evidence_refs': ['fixture:wheel']},
        'preparation_scope_ref': 'wheel-test-disposable-fixture', 'implementation_spec_sha256': digest(spec),
        'constraints': None, 'live_limits': {'max_total_cost': None, 'max_total_calls': None, 'max_concurrent_calls': None}}
    write_json(tmp_path/'input.json', {'inventory': inventory, 'spec': spec, 'request': request})
    # A fresh isolated interpreter imports the installed wheel, not the checkout.
    code = r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import jev_integration_evaluator.selection as selection
from jev_integration_evaluator.integrations.lifecycle import apply_implementation,implementation_status,rollback_implementation
from jev_integration_evaluator.integrations.verification import verify_implementation
assert Path(selection.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
work=Path(sys.argv[2]); data=json.loads((work/'input.json').read_text()); host=work/'host'; bundle=work/'bundle'
before={p.relative_to(host):p.read_bytes() for p in host.rglob('*') if p.is_file()}
approval=selection.request_sha256(data['request'])
prepared=selection.prepare_experimental_plan(host,data['inventory'],data['request'],data['spec'],bundle,approved_request_sha256=approval)
assert prepared['implementation']['status']=='planned'
assert before=={p.relative_to(host):p.read_bytes() for p in host.rglob('*') if p.is_file()}
selection.verify_selection(data['inventory'],data['request'],prepared['selection'],approved_request_sha256=approval)
baseline=verify_implementation(host,bundle,'baseline',approve_execution=True)
assert baseline['status']=='baseline_passed'
applied=apply_implementation(host,bundle,prepared['implementation']['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
modified=verify_implementation(host,bundle,'modified',approve_execution=True,baseline_sha256=baseline['receipt_sha256'])
assert modified['status']=='verified'
assert implementation_status(host,bundle,trusted_receipt_sha256=modified['receipt_sha256'])['status']=='verified'
assert rollback_implementation(host,bundle,applied['rollback_digest'])['status']=='rolled_back'
assert before=={p.relative_to(host):p.read_bytes() for p in host.rglob('*') if p.is_file()}
print(json.dumps({'classification':'synthetic_installed_evaluator_flat_generated_host','installed_selector':True,
 'baseline_scheduled':baseline['scheduled_cases'],'modified_scheduled':modified['scheduled_cases'],
 'target_restored':True,'live_spend_authorized':prepared['selection']['live_spend_authorized'],
 'benefit_demonstrated':prepared['selection']['benefit_demonstrated']}))
'''
    run = subprocess.run([sys.executable, '-I', '-c', code, str(installed), str(tmp_path)],
                          cwd=tmp_path, capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, 'installed_selector_or_synthetic_lifecycle_failed'
    result = json.loads(run.stdout)
    assert result['installed_selector'] and result['target_restored']
    assert result['baseline_scheduled'] == 1 and result['modified_scheduled'] == 3
    assert result['live_spend_authorized'] is result['benefit_demonstrated'] is False
