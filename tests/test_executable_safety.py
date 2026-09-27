"""Source selection, local integrity/trust boundaries, crash recovery, and path protection."""
import ast
import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.contracts import seal
from jev_integration_evaluator.io import InputError,read_json,write_json,digest,file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.integrations.recipes import transform,anchor_hash
from jev_integration_evaluator.integrations.lifecycle import (plan_implementation,apply_implementation,
    rollback_implementation,implementation_status)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator import implementation
from scripts.implementation_fixtures import fixture


def snapshots(root):return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_review_anchor_is_stable_across_supported_python_ast_dumps():
    statement = ast.parse('def seam(payload):\n    return legacy_dispatch_example_a(payload)\n').body[0].body[0]
    assert anchor_hash(statement) == '26813ee4e09bf8c94bccb5a7092aa2b1139a8a1d10d03d17e1aef4c1a9689fcc'


def refreshed(root,spec):
    cfg=load_config();cfg['repository']['typescript_ast']=False
    inv=scan_repo(root,cfg);c=next(c for c in inv['candidates'] if c['source']['symbol']==spec['source']['symbol'])
    apply_reviews(inv,{c['candidate_id']:{'source_sha256':c['source']['source_sha256'],'approved':True,'reviewer':'synthetic-test',
                                       'reason':'Source-matched explicitly synthetic seam review'}},cfg)
    spec=copy.deepcopy(spec);src=c['source']
    spec.update(candidate_id=c['candidate_id'],experiment_id=c['recommended_experiment']['id'],inventory_sha256=digest(inv),inventory_fingerprint=inv['scan_fingerprint'])
    spec['source'].update(file_sha256=src['file_sha256'],source_sha256=src['source_sha256'])
    spec['binding_review']['source_sha256']=src['source_sha256']
    tree=ast.parse((root/src['file']).read_bytes());fn=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==src['symbol'])
    spec['source']['anchor_sha256']=anchor_hash(fn.body[-1])
    return inv,spec


@pytest.fixture
def planned(tmp_path):
    root,bundle=tmp_path/'host',tmp_path/'private'
    inv,spec=fixture(root,'C');plan=plan_implementation(root,inv,spec['candidate_id'],spec,bundle)
    return root,bundle,inv,spec,plan


@pytest.fixture
def qualified(planned):
    root,bundle,inv,spec,plan=planned
    baseline=verify_implementation(root,bundle,'baseline',approve_execution=True)
    assert baseline['status']=='baseline_passed'
    return (*planned,baseline)


def test_plan_repeat_is_identical_and_does_not_touch_target(planned):
    root,bundle,inv,spec,plan=planned;before=snapshots(root)
    repeated=plan_implementation(root,inv,spec['candidate_id'],spec,bundle)
    assert repeated['reused'] and repeated['bundle_digest']==plan['bundle_digest']
    assert snapshots(root)==before


@pytest.mark.parametrize('change',['source','binding','no_review','deterministic','anchor','candidate','mapping','missing_binding','output_escape','protected'])
def test_invalid_source_or_binding_causes_zero_target_mutation(tmp_path,change):
    root=tmp_path/'host';inv,spec=fixture(root,'C');out=tmp_path/'bundle'
    if change=='source':(root/spec['source']['file']).write_text('# changed\n'+(root/spec['source']['file']).read_text())
    elif change=='binding':spec['bindings']['runtime']='not_present'
    elif change in ('no_review','deterministic'):
        c=next(c for c in inv['candidates'] if c['candidate_id']==spec['candidate_id'])
        if change=='no_review':c.pop('semantic_review',None)
        else:c['tier']=0
        spec['inventory_sha256']=digest(inv)
    elif change=='anchor':spec['source']['anchor_sha256']='a'*64
    elif change=='candidate':spec['candidate_id']='wrong-candidate'
    elif change=='mapping':spec['label_actions']['alternative']='new_unregistered_capability'
    elif change=='missing_binding':spec['bindings'].pop('guard')
    elif change=='output_escape':spec['output']['module']='../escape'
    elif change=='protected':spec['output']['permitted_edits']=['.git/config','anything.py']
    before=snapshots(root)
    with pytest.raises(InputError):plan_implementation(root,inv,spec['candidate_id'],spec,out)
    assert snapshots(root)==before and not out.exists()


@pytest.mark.parametrize('shape',['branch','async','decorator','two_statements','generator','aliased_registry','dynamic_registry','dict_shadow'])
def test_unsupported_shapes_are_explicit_not_text_fallback(tmp_path,shape):
    root=tmp_path/'host';inv,spec=fixture(root,'C');file=root/spec['source']['file'];text=file.read_text()
    seam=spec['source']['symbol'];legacy='legacy_dispatch_scenario_c';needle='return '+legacy+'(payload)'
    if shape=='branch':text=text.replace(needle,'if payload:\n        '+needle+'\n    return None')
    elif shape=='async':text=text.replace('def '+seam+'(','async def '+seam+'(')
    elif shape=='decorator':text=text.replace('def '+seam+'(','@staticmethod\ndef '+seam+'(')
    elif shape=='two_statements':text=text.replace(needle,'ignored = 1\n    '+needle)
    elif shape=='generator':text=text.replace(needle,'yield '+legacy+'(payload)')
    elif shape=='aliased_registry':text+='\n'+spec['bindings']['registry']+' = lambda request: OPTIONS\n'
    elif shape=='dynamic_registry':text=text.replace('return dict(OPTIONS)',"return {key:value for key,value in OPTIONS.items()}")
    else:text+='\ndict = lambda *a: {}\n'
    file.write_text(text)
    # Shape rejection is tested directly on the parsed transformer. Lifecycle additionally
    # requires re-reviewed source hashes and rejects drift before reaching this code.
    before=snapshots(root)
    with pytest.raises(InputError):transform(root,spec)
    assert snapshots(root)==before


def test_scan_and_plan_never_execute_top_level_target_code(tmp_path):
    root=tmp_path/'host';inv,spec=fixture(root,'C');file=root/spec['source']['file'];marker=tmp_path/'executed'
    file.write_text(file.read_text()+"\nopen("+repr(str(marker))+", 'w').write('execution')\n")
    inv,spec=refreshed(root,spec)
    plan_implementation(root,inv,spec['candidate_id'],spec,tmp_path/'bundle')
    assert not marker.exists()
    with pytest.raises(InputError,match='Missing scope'):verify_implementation(root,tmp_path/'bundle','baseline')
    assert not marker.exists()
    assert implementation_status(root,tmp_path/'bundle')['target_executed'] is False


@pytest.mark.parametrize('artifact',['implementation-spec.json','patch-plan.json','implementation-manifest.json','implementation-plan.json'])
def test_bundle_artifact_tampering_is_not_trusted(planned,artifact):
    root,bundle,inv,spec,plan=planned;before=snapshots(root)
    value=read_json(bundle/artifact);value['wiring_status']='verified';write_json(bundle/artifact,value)
    with pytest.raises((InputError,ValueError)):implementation_status(root,bundle)
    assert snapshots(root)==before


def test_wrong_root_is_rejected_even_with_identical_bytes(planned,tmp_path):
    root,bundle,inv,spec,plan=planned;other=tmp_path/'another';shutil.copytree(root,other)
    with pytest.raises(InputError,match='root'):implementation_status(other,bundle)


@pytest.mark.parametrize('drift',['bytes','mode'])
def test_drift_immediately_before_apply_refuses_all_writes(qualified,drift):
    root,bundle,inv,spec,plan,baseline=qualified;source=root/spec['source']['file']
    if drift=='bytes':source.write_bytes(source.read_bytes()+b'\n# concurrent edit\n')
    else:source.chmod(0o700 if os.name=='posix' else 0o444)
    before=snapshots(root)
    with pytest.raises(InputError):apply_implementation(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    assert snapshots(root)==before


def test_rollback_preserves_unrelated_edits_and_refuses_modified_owned_file(qualified):
    root,bundle,inv,spec,plan,baseline=qualified
    applied=apply_implementation(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    unrelated=root/'independent.txt';unrelated.write_text('preserve concurrent work')
    source=root/spec['source']['file'];applied_bytes=source.read_bytes();source.write_bytes(applied_bytes+b'\n# concurrent work\n')
    before=snapshots(root)
    with pytest.raises(InputError,match='concurrent work'):rollback_implementation(root,bundle,applied['rollback_digest'])
    assert snapshots(root)==before
    # The test author reconciles its own synthetic edit explicitly, not the recovery tool.
    source.write_bytes(applied_bytes)
    assert rollback_implementation(root,bundle,applied['rollback_digest'])['status']=='rolled_back'
    assert unrelated.read_text()=='preserve concurrent work'


def test_write_exception_and_process_termination_have_distinct_recovery(qualified,monkeypatch):
    root,bundle,inv,spec,plan,baseline=qualified;original=snapshots(root)
    real=implementation.atomic_text;counter=0
    def failing(path,text):
        nonlocal counter
        counter+=1
        if counter==2:raise OSError('synthetic write failure')
        return real(path,text)
    monkeypatch.setattr(implementation,'atomic_text',failing)
    with pytest.raises(OSError):apply_implementation(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    assert snapshots(root)==original  # ordinary exception did get its immediate rollback attempt
    status=implementation_status(root,bundle);assert status['status']=='blocked_recovery'
    monkeypatch.setattr(implementation,'atomic_text',real)
    assert rollback_implementation(root,bundle,status['rollback_digest'])['status']=='rolled_back'


def test_actual_process_exit_leaves_journal_and_reconciles_preimages(qualified):
    root,bundle,inv,spec,plan,baseline=qualified;original=snapshots(root)
    package=Path(__file__).resolve().parents[1]
    code='''import os,sys
sys.path.insert(0,sys.argv[1])
from jev_integration_evaluator import implementation
from jev_integration_evaluator.integrations.lifecycle import apply_implementation
real=implementation.atomic_text
def crash(path,text):
    real(path,text)
    os._exit(71)
implementation.atomic_text=crash
apply_implementation(sys.argv[2],sys.argv[3],sys.argv[4],baseline_sha256=sys.argv[5])
'''
    result=subprocess.run([sys.executable,'-I','-c',code,str(package),str(root),str(bundle),plan['bundle_digest'],baseline['receipt_sha256']],capture_output=True,timeout=20)
    assert result.returncode==71 and snapshots(root)!=original
    status=implementation_status(root,bundle);assert status['status']=='blocked_recovery'
    assert rollback_implementation(root,bundle,status['rollback_digest'])['status']=='rolled_back'
    assert snapshots(root)==original


def test_receipt_changes_cannot_preserve_external_trust(qualified):
    root,bundle,inv,spec,plan,baseline=qualified
    applied=apply_implementation(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    modified=verify_implementation(root,bundle,'modified',approve_execution=True,baseline_sha256=baseline['receipt_sha256'])
    assert modified['status']=='verified'
    receipt=read_json(bundle/'verification-receipt.json');receipt['contract_assertions']=['forged_manifest_assertion']
    # An attacker can recompute LOCAL hashes, but cannot change the independently held anchor.
    write_json(bundle/'verification-receipt.json',seal({k:v for k,v in receipt.items() if k!='contract_digest'}))
    assert implementation_status(root,bundle)['status']=='applied_unverified'
    with pytest.raises(InputError):implementation_status(root,bundle,trusted_receipt_sha256=modified['receipt_sha256'])
    rollback_implementation(root,bundle,applied['rollback_digest'])


def test_execution_flag_and_command_output_are_bounded(tmp_path):
    with pytest.raises(InputError):implementation.run_authorized_tests(tmp_path,[sys.executable,'-c','raise SystemExit(0)'])
    output=implementation.run_authorized_tests(tmp_path,[sys.executable,'-c',"import sys;sys.stdout.write('x'*2000000)"],approve_execution=True)
    assert output['status']=='failed' and output['output_limit_exceeded'] and len(output['stdout'])<=20000
    timeout=implementation.run_authorized_tests(tmp_path,[sys.executable,'-c','import time;time.sleep(10)'],approve_execution=True,timeout_s=.05)
    assert timeout['status']=='timeout' and timeout['sandboxed'] is False


def test_overlapping_recipe_plans_conflict_without_duplicate_wiring(qualified,tmp_path):
    root,bundle,inv,spec,plan,baseline=qualified
    other=copy.deepcopy(spec);other['recipe']['id']='python.A';other['binding_review']['pattern']='A'
    other['policy']['fallback']='block';other['output']['module']='_second_adapter'
    other['output']['permitted_edits']=[spec['source']['file'],'_second_adapter.py']
    second=tmp_path/'second-bundle';p2=plan_implementation(root,inv,other['candidate_id'],other,second)
    b2=verify_implementation(root,second,'baseline',approve_execution=True)
    applied=apply_implementation(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    before=snapshots(root)
    with pytest.raises(InputError):apply_implementation(root,second,p2['bundle_digest'],baseline_sha256=b2['receipt_sha256'])
    assert snapshots(root)==before and not (root/'_second_adapter.py').exists()
    rollback_implementation(root,bundle,applied['rollback_digest'])


def test_actual_rollback_process_exit_is_recoverable(qualified):
    root,bundle,inv,spec,plan,baseline=qualified;original=snapshots(root)
    applied=apply_implementation(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    package=Path(__file__).resolve().parents[1]
    code='''import os,sys
sys.path.insert(0,sys.argv[1])
from jev_integration_evaluator import implementation
from jev_integration_evaluator.integrations.lifecycle import rollback_implementation
real=implementation.atomic_text
def crash(path,text):
    real(path,text)
    os._exit(72)
implementation.atomic_text=crash
rollback_implementation(sys.argv[2],sys.argv[3],sys.argv[4])
'''
    crashed=subprocess.run([sys.executable,'-I','-c',code,str(package),str(root),str(bundle),applied['rollback_digest']],capture_output=True,timeout=20)
    assert crashed.returncode==72
    status=implementation_status(root,bundle);assert status['status']=='blocked_recovery'
    assert rollback_implementation(root,bundle,status['rollback_digest'])['status']=='rolled_back'
    assert snapshots(root)==original


@pytest.mark.skipif(not hasattr(os,'symlink'),reason='Platform does not expose symlink creation')
def test_bundle_or_source_symlinks_are_never_followed(tmp_path):
    root=tmp_path/'host';inv,spec=fixture(root,'C');bundle=tmp_path/'bundle';outside=tmp_path/'outside';outside.mkdir()
    try:bundle.symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('Symlink creation not authorized by this platform')
    with pytest.raises(InputError,match='symlink'):plan_implementation(root,inv,spec['candidate_id'],spec,bundle)
    assert not list(outside.iterdir())
    bundle.unlink();source=root/spec['source']['file'];raw=source.read_bytes();source.unlink();victim=outside/'host.py';victim.write_bytes(raw);source.symlink_to(victim)
    with pytest.raises(InputError):plan_implementation(root,inv,spec['candidate_id'],spec,bundle)
    assert victim.read_bytes()==raw


def test_cannot_hide_executor_by_observing_irrelevant_function(tmp_path):
    root=tmp_path/'host';inv,spec=fixture(root,'C');spec['verification']['effect_symbols']=[spec['bindings']['evidence']]
    with pytest.raises(InputError,match='exactly cover'):plan_implementation(root,inv,spec['candidate_id'],spec,tmp_path/'bundle')
