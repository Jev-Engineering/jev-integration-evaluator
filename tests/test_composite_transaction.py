"""Synthetic composite planning and transaction ownership, without private hosts."""
import copy
import json
import os
from pathlib import Path
import subprocess
import stat
import sys

import pytest

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.integrations.composite import (_compose_file, plan_composite,
    status_composite, verify_composite, apply_composite, rollback_composite)
from jev_integration_evaluator.integrations.lifecycle import _repository_lock
from jev_integration_evaluator.io import InputError, digest, file_hash, read_json, write_json
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from scripts.implementation_fixtures import fixture
import jev_integration_evaluator.integrations.composite as composite


def _two_hosts(tmp_path):
    root = tmp_path/'host'
    _,first = fixture(root,'C',tag='one')
    _,second = fixture(root,'C',tag='two')
    (root/'combined_check.py').write_bytes(b'''import hashlib, json
from pathlib import Path
import host_one, host_two, _generated_one, _generated_two
from jev_integration_evaluator.budget import BudgetDenied
from jev_integration_evaluator.integrations.runtime_lifecycle import HostRuntimeLifecycle

modules = [(_generated_one, host_one.public_entry_one),
           (_generated_two, host_two.public_entry_two)]
adapters = {adapter.SPEC['candidate_id']:adapter for adapter,_ in modules}
reviewed = {'files':[{'path':str(Path(__file__).resolve()),
                      'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}]}
runtime = HostRuntimeLifecycle(adapters,budget_limits={
    'max_calls_per_task':2,'max_cost_per_task':0.01,
    'max_total_calls':2,'max_total_cost':0.01},audit_log=[],
    dependency_plan=reviewed,startup_mode='off')
task = {'task_id':'fixture-task','objective':'synthetic evidence','command':'/prune'}
results = {}
tokens = []
scopes = []
for adapter,entry in modules:
    cid = adapter.SPEC['candidate_id']
    router = runtime.router(cid,task)
    assert router.budget_coordinator is runtime.coordinator
    reservation = runtime.coordinator.reserve(task['task_id'],0.0)
    results[cid] = entry(task)
    runtime.coordinator.settle(reservation)
    tokens.append(str(id(router.budget_coordinator)))
    scopes.append(router.canary_scope)
try:
    runtime.coordinator.reserve(task['task_id'],0.0)
except BudgetDenied:
    pass
else:
    raise AssertionError('shared budget reset between candidates')
snapshot = runtime.coordinator.snapshot()
ids = sorted(adapters)
print(json.dumps({'schema_version':'composite-host-observation-v1',
    'candidate_ids':ids,'task_id':task['task_id'],
    'coordinator_tokens':tokens,'canary_scopes':scopes,
    'assessment_calls':snapshot['calls'],'total_cost':snapshot['reserved_cost'],
    'audit_candidate_ids':ids,'results':results},sort_keys=True))
runtime.close()
''')
    config = load_config(); config['repository']['typescript_ast'] = False
    inventory = scan_repo(root,config)
    chosen = {}
    for spec in (first,second):
        candidate = next(c for c in inventory['candidates']
                         if c['source']['symbol'] == spec['source']['symbol'])
        chosen[candidate['candidate_id']] = candidate
    apply_reviews(inventory,{cid:{'source_sha256':c['source']['source_sha256'],
        'approved':True,'reviewer':'synthetic-composite-review',
        'reason':'Explicit source-matched synthetic composite fixture review'}
        for cid,c in chosen.items()},config)
    specs = {}
    for spec in (first,second):
        candidate = next(c for c in inventory['candidates']
                         if c['source']['symbol'] == spec['source']['symbol'])
        spec = copy.deepcopy(spec); source = candidate['source']
        spec.update(candidate_id=candidate['candidate_id'],
                    experiment_id=candidate['recommended_experiment']['id'],
                    inventory_sha256=digest(inventory),
                    inventory_fingerprint=inventory['scan_fingerprint'])
        spec['source'].update(file_sha256=source['file_sha256'],
                              source_sha256=source['source_sha256'])
        spec['binding_review']['source_sha256'] = source['source_sha256']
        spec['runtime']['canary_scope'] = 'synthetic-composite-workflow'
        spec['runtime']['configuration']['max_calls_per_task'] = 2
        specs[spec['candidate_id']] = spec
    ids = sorted(specs)
    trusted_root = str(Path(__file__).resolve().parents[1])
    bootstrap = ('import os,runpy,sys;sys.path.insert(0,'+repr(trusted_root)+');'
                 'sys.path.insert(0,os.getcwd());runpy.run_path("combined_check.py",run_name="__main__")')
    selection = {'schema_version':'composite-selection-v1','candidate_ids':ids,
                 'dependencies':[],'conflicts':[],
                 'shared_runtime':{'task_field':'task_id','policy_version':'fixture-v1',
                     'canary_scope':'synthetic-composite-workflow',
                     'max_calls_per_task':2,'max_cost_per_task':0.01},
                 'combined_verification':{'command':[sys.executable,'-I','-c',bootstrap],
                     'shared_task_id':'fixture-task','expected_results':{cid:'first' for cid in ids}}}
    return root,inventory,selection,specs


def test_same_file_static_imports_compose_and_extra_statement_is_refused(tmp_path):
    root = tmp_path/'host'; root.mkdir()
    (root/'host.py').write_bytes(b'def first():\n    return old()\n\ndef second():\n    return old()\n')
    first = 'from adapter_a import invoke as _jev_invoke_aaa\ndef first():\n    return _jev_invoke_aaa(old)\n\ndef second():\n    return old()\n'
    second = 'from adapter_b import invoke as _jev_invoke_bbb\ndef first():\n    return old()\n\ndef second():\n    return _jev_invoke_bbb(old)\n'
    combined = _compose_file(root,'host.py',[('a',first.encode()),('b',second.encode())])
    assert combined.count('from adapter_a import') == 1
    assert combined.count('from adapter_b import') == 1
    assert '_jev_invoke_aaa(old)' in combined and '_jev_invoke_bbb(old)' in combined
    bad = second.replace('from adapter_b import invoke as _jev_invoke_bbb\n',
                         'from adapter_b import invoke as _jev_invoke_bbb\nopen("marker", "w")\n')
    with pytest.raises(InputError, match='Unsupported same-file candidate change in host.py: b'):
        _compose_file(root,'host.py',[('a',first.encode()),('b',bad.encode())])
    overlapping = first.replace('_jev_invoke_aaa','_jev_invoke_bbb').replace('adapter_a','adapter_b')
    with pytest.raises(InputError,match='Overlapping candidate edits in host.py: a,b'):
        _compose_file(root,'host.py',[('a',first.encode()),('b',overlapping.encode())])


def test_two_reviewed_same_file_seams_have_distinct_imports_and_wrappers(tmp_path):
    root = tmp_path/'host'
    _,first = fixture(root,'C',tag='one')
    source_path = root/first['source']['file']
    with source_path.open('ab') as handle:
        handle.write(b'\ndef select_boundary_alt(payload):\n    return legacy_dispatch_one(payload)\n'
                     b'\ndef public_entry_alt(payload):\n    return select_boundary_alt(payload)\n')
    config = load_config(); config['repository']['typescript_ast'] = False
    inventory = scan_repo(root,config)
    candidates = {}
    for symbol in ('select_boundary_one','select_boundary_alt'):
        matches = [c for c in inventory['candidates'] if c['source']['symbol']==symbol]
        assert len(matches)==1
        candidates[symbol] = matches[0]
    apply_reviews(inventory,{c['candidate_id']:{'source_sha256':c['source']['source_sha256'],
        'approved':True,'reviewer':'synthetic-same-file-review',
        'reason':'Independently reviewed finite synthetic source seam'}
        for c in candidates.values()},config)
    specs = {}
    for symbol,candidate in candidates.items():
        spec = copy.deepcopy(first)
        spec.update(candidate_id=candidate['candidate_id'],
                    experiment_id=candidate['recommended_experiment']['id'],
                    inventory_sha256=digest(inventory),
                    inventory_fingerprint=inventory['scan_fingerprint'])
        spec['source'].update(symbol=symbol,file_sha256=candidate['source']['file_sha256'],
                              source_sha256=candidate['source']['source_sha256'])
        spec['binding_review']['source_sha256']=candidate['source']['source_sha256']
        spec['runtime']['canary_scope']='synthetic-composite-workflow'
        spec['runtime']['configuration']['max_calls_per_task']=2
        if symbol.endswith('alt'):
            spec['verification']['entry_point']='public_entry_alt'
            spec['output']['module']='_generated_alt'
            spec['output']['permitted_edits']=[first['source']['file'],'_generated_alt.py']
        specs[spec['candidate_id']]=spec
    ids = sorted(specs)
    selection={'schema_version':'composite-selection-v1','candidate_ids':ids,
        'dependencies':[],'conflicts':[],
        'shared_runtime':{'task_field':'task_id','policy_version':'fixture-v1',
            'canary_scope':'synthetic-composite-workflow','max_calls_per_task':2,
            'max_cost_per_task':0.01},
        'combined_verification':{'command':[sys.executable,'-V'],
            'shared_task_id':'fixture-task','expected_results':{cid:'first' for cid in ids}}}
    bundle=tmp_path/'same-file-bundle'
    planned=plan_composite(root,inventory,selection,specs,bundle)
    assert planned['owned_files']==3
    patch=read_json(bundle/'patch-plan.json')
    host=next(row['new_content'] for row in patch['changes'] if row['file']==first['source']['file'])
    assert host.count('from _generated_one import invoke as')==1
    assert host.count('from _generated_alt import invoke as')==1
    assert host.count('_jev_invoke_')==4


def test_different_file_selected_set_and_source_drift(tmp_path):
    root,inventory,selection,specs = _two_hosts(tmp_path)
    original = {p.name:file_hash(p) for p in root.glob('*.py')}
    bundle = tmp_path/'bundle'
    planned = plan_composite(root,inventory,selection,specs,bundle)
    assert planned['status']=='planned' and planned['owned_files']==4
    assert status_composite(root,bundle)['status']=='planned'
    assert {p.name:file_hash(p) for p in root.glob('*.py')} == original
    changed = copy.deepcopy(selection); changed['candidate_ids'].reverse()
    with pytest.raises(InputError): plan_composite(root,inventory,changed,specs,tmp_path/'different')
    source = root/specs[selection['candidate_ids'][0]]['source']['file']
    source.write_text(source.read_text()+'\n# drift\n')
    with pytest.raises(InputError,match='drift'):
        plan_composite(root,inventory,selection,specs,tmp_path/'stale')


def test_selected_graph_and_shared_runtime_change_approval_identity(tmp_path):
    root,inventory,selection,specs = _two_hosts(tmp_path)
    first=plan_composite(root,inventory,selection,specs,tmp_path/'first')
    changed=copy.deepcopy(selection)
    changed['dependencies']=[[selection['candidate_ids'][0],selection['candidate_ids'][1]]]
    second=plan_composite(root,inventory,changed,specs,tmp_path/'second')
    assert first['selected_set_digest']!=second['selected_set_digest']
    with pytest.raises(InputError,match='Exact composite approval'):
        apply_composite(root,tmp_path/'second',first['bundle_digest'],baseline_sha256='0'*64)
    conflict=copy.deepcopy(selection); conflict['conflicts']=[selection['candidate_ids']]
    with pytest.raises(InputError,match='explicit conflict'):
        plan_composite(root,inventory,conflict,specs,tmp_path/'conflict')
    budget=copy.deepcopy(selection); budget['shared_runtime']['max_calls_per_task']=3
    with pytest.raises(InputError,match='call and cost budget'):
        plan_composite(root,inventory,budget,specs,tmp_path/'budget')
    assert not (tmp_path/'budget').exists()


def test_composite_cli_plan_and_status_preserve_legacy_dispatch(tmp_path):
    root,inventory,selection,specs=_two_hosts(tmp_path)
    paths={name:tmp_path/(name+'.json') for name in ('inventory','selection','specs')}
    for name,value in (('inventory',inventory),('selection',selection),('specs',specs)):
        write_json(paths[name],value)
    bundle=tmp_path/'cli-bundle'
    project=Path(__file__).resolve().parents[1]
    planned=subprocess.run([sys.executable,'-m','jev_integration_evaluator',
        'implement-composite-plan','--repo',str(root),'--inventory',str(paths['inventory']),
        '--selection',str(paths['selection']),'--specs',str(paths['specs']),
        '--out',str(bundle)],cwd=project,text=True,capture_output=True,timeout=30)
    assert planned.returncode==0,planned.stderr
    assert json.loads(planned.stdout)['status']=='planned'
    status=subprocess.run([sys.executable,'-m','jev_integration_evaluator',
        'implement-composite-status','--repo',str(root),'--bundle',str(bundle)],
        cwd=project,text=True,capture_output=True,timeout=30)
    assert status.returncode==0,status.stderr
    assert json.loads(status.stdout)['status']=='planned'
    denied=subprocess.run([sys.executable,'-m','jev_integration_evaluator',
        'implement-composite-verify','--phase','baseline','--repo',str(root),
        '--bundle',str(bundle)],cwd=project,text=True,capture_output=True,timeout=30)
    assert denied.returncode==2
    assert not (bundle/'baseline-receipt.json').exists()


@pytest.mark.skipif(sys.platform != 'linux', reason='native Linux installed-fixture qualification')
def test_combined_lifecycle_shared_budget_and_fresh_receipt_generation(tmp_path):
    root,inventory,selection,specs = _two_hosts(tmp_path)
    bundle = tmp_path/'bundle'
    planned = plan_composite(root,inventory,selection,specs,bundle)
    baseline = verify_composite(root,bundle,'baseline',approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_composite(root,bundle,planned['bundle_digest'],
                              baseline_sha256=baseline['receipt_sha256'])
    assert applied['status'] == 'applied_unverified'
    repeated = apply_composite(root,bundle,planned['bundle_digest'],
                               baseline_sha256=baseline['receipt_sha256'])
    assert repeated['idempotent'] is True
    modified = verify_composite(root,bundle,'modified',approve_execution=True,
                                baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert modified['scheduled_cases'] == sum(len(spec['verification']['cases'])*3
                                              for spec in specs.values())
    unanchored = status_composite(root,bundle)
    assert unanchored['status'] == 'applied_unverified'
    anchored = status_composite(root,bundle,trusted_receipt_sha256=modified['receipt_sha256'])
    assert anchored['status'] == 'verified'
    restored = rollback_composite(root,bundle,anchored['rollback_digest'])
    assert restored['status'] == 'rolled_back'
    with pytest.raises(InputError,match='earlier generation'):
        apply_composite(root,bundle,planned['bundle_digest'],
                        baseline_sha256=baseline['receipt_sha256'])
    fresh_baseline = verify_composite(root,bundle,'baseline',approve_execution=True)
    assert fresh_baseline['status'] == 'baseline_passed'
    reapplied = apply_composite(root,bundle,planned['bundle_digest'],
                                baseline_sha256=fresh_baseline['receipt_sha256'])
    assert reapplied['status'] == 'applied_unverified'
    stale = status_composite(root,bundle,trusted_receipt_sha256=modified['receipt_sha256'])
    assert stale['status'] == 'applied_unverified' and stale['receipt_trust'] == 'stale_generation'


def _prepared_apply(tmp_path):
    root,inventory,selection,specs = _two_hosts(tmp_path)
    bundle = tmp_path/'bundle'
    plan = plan_composite(root,inventory,selection,specs,bundle)
    baseline = verify_composite(root,bundle,'baseline',approve_execution=True)
    assert baseline['status']=='baseline_passed'
    return root,bundle,plan,baseline,read_json(bundle/'patch-plan.json')


@pytest.mark.skipif(sys.platform != 'linux', reason='native Linux crash simulation')
@pytest.mark.parametrize('path_index',range(4))
@pytest.mark.parametrize('event',('write_started','write_completed'))
@pytest.mark.parametrize('failure',(OSError,SystemExit))
def test_each_composite_apply_write_boundary_recovers_owned_bytes(tmp_path,monkeypatch,
                                                                    path_index,event,failure):
    root,bundle,plan,baseline,patch = _prepared_apply(tmp_path)
    target = patch['changes'][path_index]['file']
    unrelated = root/'unrelated.txt'; unrelated.write_bytes(b'concurrent unrelated work')
    original = composite.apply_patch_plan
    def interrupted(repo,reviewed,approval,*,progress):
        def after(event_name,change):
            progress(event_name,change)
            if event_name==event and change['file']==target:
                raise failure('synthetic write boundary')
        return original(repo,reviewed,approval,progress=after)
    monkeypatch.setattr(composite,'apply_patch_plan',interrupted)
    with pytest.raises(failure):
        apply_composite(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    assert status_composite(root,bundle)['status']=='blocked_recovery'
    monkeypatch.setattr(composite,'apply_patch_plan',original)
    recovery = rollback_composite(root,bundle,status_composite(root,bundle)['rollback_digest'])
    assert recovery['status']=='rolled_back'
    assert unrelated.read_bytes()==b'concurrent unrelated work'
    assert all(composite._inspect_file(root,row)=='baseline'
               for row in read_json(bundle/'composite-plan.json')['owned_files'])


@pytest.mark.skipif(sys.platform != 'linux', reason='native Linux crash simulation')
@pytest.mark.parametrize('event',('apply_started','applied_unverified'))
def test_composite_apply_terminal_journal_boundaries(tmp_path,monkeypatch,event):
    root,bundle,plan,baseline,_ = _prepared_apply(tmp_path)
    original=composite._record
    def interrupted(private,record,kind,relative=None):
        original(private,record,kind,relative)
        if kind==event: raise SystemExit('synthetic journal crash')
    monkeypatch.setattr(composite,'_record',interrupted)
    with pytest.raises(SystemExit):
        apply_composite(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    monkeypatch.setattr(composite,'_record',original)
    status=status_composite(root,bundle)
    assert status['status']==('blocked_recovery' if event=='apply_started' else 'applied_unverified')
    rollback_composite(root,bundle,status['rollback_digest'])
    assert status_composite(root,bundle)['status']=='rolled_back'


@pytest.mark.skipif(sys.platform != 'linux', reason='native Linux crash simulation')
@pytest.mark.parametrize('path_index',range(4))
@pytest.mark.parametrize('event',('rollback_write_started','rollback_write_completed'))
def test_each_composite_rollback_write_boundary_resumes(tmp_path,monkeypatch,path_index,event):
    root,bundle,plan,baseline,patch = _prepared_apply(tmp_path)
    apply_composite(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    target=patch['changes'][path_index]['file']
    unrelated=root/'unrelated.txt'; unrelated.write_bytes(b'independent concurrent edit')
    original=composite._record
    def interrupted(private,record,kind,relative=None):
        original(private,record,kind,relative)
        if kind==event and relative==target:
            raise SystemExit('synthetic rollback boundary')
    monkeypatch.setattr(composite,'_record',interrupted)
    approval=status_composite(root,bundle)['rollback_digest']
    with pytest.raises(SystemExit): rollback_composite(root,bundle,approval)
    monkeypatch.setattr(composite,'_record',original)
    assert status_composite(root,bundle)['status']=='blocked_recovery'
    assert rollback_composite(root,bundle,approval)['status']=='rolled_back'
    assert unrelated.read_bytes()==b'independent concurrent edit'


@pytest.mark.skipif(sys.platform != 'linux', reason='native Linux crash simulation')
@pytest.mark.parametrize('event',('rollback_started','rolled_back'))
def test_composite_rollback_terminal_journal_boundaries(tmp_path,monkeypatch,event):
    root,bundle,plan,baseline,_ = _prepared_apply(tmp_path)
    apply_composite(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    approval=status_composite(root,bundle)['rollback_digest']
    original=composite._record
    def interrupted(private,record,kind,relative=None):
        original(private,record,kind,relative)
        if kind==event: raise SystemExit('synthetic rollback journal crash')
    monkeypatch.setattr(composite,'_record',interrupted)
    with pytest.raises(SystemExit): rollback_composite(root,bundle,approval)
    monkeypatch.setattr(composite,'_record',original)
    assert status_composite(root,bundle)['status']==(
        'blocked_recovery' if event=='rollback_started' else 'rolled_back')
    assert rollback_composite(root,bundle,approval)['status']=='rolled_back'


@pytest.mark.parametrize('attack',('separate_coordinator','over_budget','missing_audit','wrong_result'))
def test_shared_host_observation_refuses_false_combined_proof(tmp_path,monkeypatch,attack):
    root,_,selection,_ = _two_hosts(tmp_path)
    ids = selection['candidate_ids']
    observed = {'schema_version':'composite-host-observation-v1',
                'candidate_ids':ids,'task_id':'fixture-task',
                'coordinator_tokens':['one','one'],
                'canary_scopes':['synthetic-composite-workflow']*2,
                'assessment_calls':2,'total_cost':0.0,'audit_candidate_ids':ids,
                'results':{cid:'first' for cid in ids}}
    if attack=='separate_coordinator': observed['coordinator_tokens'][1]='two'
    if attack=='over_budget': observed['assessment_calls']=3
    if attack=='missing_audit': observed['audit_candidate_ids']=ids[:1]
    if attack=='wrong_result': observed['results'][ids[0]]='unreviewed'
    monkeypatch.setattr(composite,'run_authorized_tests',lambda *args,**kwargs:
                        {'status':'passed','stdout':json.dumps(observed)})
    check=composite._combined_check(root,selection)
    assert check['status']=='passed' and check['shared_budget_valid'] is False


@pytest.mark.skipif(sys.platform != 'linux', reason='native Linux lock and mode behavior')
def test_worktree_lock_and_concurrent_owned_edit_refuse_rollback(tmp_path):
    root,bundle,plan,baseline,patch = _prepared_apply(tmp_path)
    with composite._lock(bundle,root):
        with pytest.raises(InputError,match='worktree'):
            with _repository_lock(root): pass
    apply_composite(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    target=root/patch['changes'][0]['file']
    target.write_bytes(target.read_bytes()+b'\n# concurrent edit\n')
    unrelated=root/'unrelated.txt'; unrelated.write_bytes(b'other owner')
    approval=status_composite(root,bundle)['rollback_digest']
    with pytest.raises(InputError,match='Concurrent owned-byte'):
        rollback_composite(root,bundle,approval)
    assert target.read_bytes().endswith(b'# concurrent edit\n')
    assert unrelated.read_bytes()==b'other owner'


@pytest.mark.skipif(sys.platform != 'linux', reason='POSIX atomic mode preservation')
def test_rollback_crash_after_mode_preserving_replace_recovers(tmp_path,monkeypatch):
    root,inventory,selection,specs = _two_hosts(tmp_path)
    for spec in specs.values():
        os.chmod(root/spec['source']['file'],0o644)
    # File modes are not part of discovery hashes, but the reviewed inventory
    # and plan are built after the explicit mode choice.
    bundle=tmp_path/'bundle'
    plan=plan_composite(root,inventory,selection,specs,bundle)
    owned=read_json(bundle/'composite-plan.json')['owned_files']
    original_row=next(row for row in owned if row['preimage'])
    target=root/original_row['file']
    assert original_row['old_mode']==0o644
    baseline=verify_composite(root,bundle,'baseline',approve_execution=True)
    apply_composite(root,bundle,plan['bundle_digest'],baseline_sha256=baseline['receipt_sha256'])
    original=composite.atomic_text
    triggered=False
    def after_replace(path,text):
        nonlocal triggered
        original(path,text)
        if Path(path)==target and not triggered:
            triggered=True
            raise SystemExit('crash after atomic replacement, before journal completion')
    monkeypatch.setattr(composite,'atomic_text',after_replace)
    approval=status_composite(root,bundle)['rollback_digest']
    with pytest.raises(SystemExit): rollback_composite(root,bundle,approval)
    monkeypatch.setattr(composite,'atomic_text',original)
    assert triggered
    assert file_hash(target)==original_row['old_sha256']
    assert stat.S_IMODE(target.stat().st_mode)==original_row['old_mode']
    assert status_composite(root,bundle)['status']=='blocked_recovery'
    assert rollback_composite(root,bundle,approval)['status']=='rolled_back'
