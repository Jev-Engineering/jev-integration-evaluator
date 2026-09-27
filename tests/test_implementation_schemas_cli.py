import copy,json,os,subprocess,sys
from pathlib import Path
import pytest,jsonschema
from jev_integration_evaluator.io import InputError,read_json,write_json,read_jsonl,digest
from jev_integration_evaluator.implementation import make_patch_plan,apply_patch_plan,scaffold_integration,run_authorized_tests,prepare_worktree
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.traces import correlate_traces


def test_patch_requires_exact_approval_and_applies(tmp_path):
    path=tmp_path/'host.py';path.write_text('x = 1\n');path.chmod(0o755)
    plan=make_patch_plan(tmp_path,[{'file':'host.py','new_content':'x = 2\n'}],['JEV-TEST'])
    with pytest.raises(InputError):apply_patch_plan(tmp_path,plan,'wrong')
    assert path.read_text()=='x = 1\n'
    result=apply_patch_plan(tmp_path,plan,plan['plan_digest'])
    assert result['status']=='applied' and path.read_text()=='x = 2\n'
    assert path.stat().st_mode&0o777==0o755
    assert result['tests_executed'] is False

def test_stale_patch_preflight_leaves_all_unchanged(tmp_path):
    for name in ('a.py','b.py'):(tmp_path/name).write_text('old')
    plan=make_patch_plan(tmp_path,[{'file':n,'new_content':'new'} for n in ('a.py','b.py')],['JEV-X'])
    (tmp_path/'b.py').write_text('concurrent work')
    with pytest.raises(InputError):apply_patch_plan(tmp_path,plan,plan['plan_digest'])
    assert (tmp_path/'a.py').read_text()=='old'

@pytest.mark.parametrize('path',['../escape.py','.git/config','.env','secret.key','credentials/a.py'])
def test_patch_protected_paths(tmp_path,path):
    with pytest.raises(InputError):make_patch_plan(tmp_path,[{'file':path,'new_content':'x'}],['JEV-X'])

def test_patch_symlink_escape(tmp_path):
    (tmp_path/'link').symlink_to(tmp_path.parent,target_is_directory=True)
    with pytest.raises(InputError):make_patch_plan(tmp_path,[{'file':'link/file.py','new_content':'x'}],['JEV-X'])

def test_execution_and_worktree_are_separate_approvals(tmp_path):
    with pytest.raises(InputError):run_authorized_tests(tmp_path,[sys.executable,'-c','print(1)'])
    with pytest.raises(InputError):prepare_worktree(tmp_path,tmp_path.parent/'new-worktree','jev/test')
    o=run_authorized_tests(tmp_path,[sys.executable,'-c','print(1)'],approve_execution=True)
    assert o['status']=='passed' and o['sandboxed'] is False

def test_generated_adapter_runs_off_by_default(root,cfg,tmp_path):
    scan=scan_repo(root/'examples/coding-agent',cfg)
    manifest=scaffold_integration(scan,scan['candidates'][0]['candidate_id'],tmp_path/'adapter')
    assert manifest['wiring_status']=='adapter_generated_not_yet_connected_to_host_callsite'
    env={**os.environ,'PYTHONPATH':str(root)+os.pathsep+str(tmp_path/'adapter')}
    p=subprocess.run([sys.executable,'-m','pytest','-q','test_adapter.py'],cwd=tmp_path/'adapter',env=env,capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stdout+p.stderr

def test_trace_requires_exact_source_hash(root,cfg):
    scan=scan_repo(root/'examples/coding-agent',cfg);c=scan['candidates'][0];source=c['source']
    event={'source_location':source,'task_id':'one','success':False,'latency_ms':20,'model_calls':2,'tokens':200,'retries':1}
    s=correlate_traces(scan,[event],cfg)
    assert s['trace_correlation']['matched_source_keys']==1
    bad=copy.deepcopy(event);bad['source_location']['source_sha256']='0'*64
    o=correlate_traces(scan,[bad],cfg)
    assert o['trace_correlation']['ignored']['source hash/file/symbol not in this scan']==1

def test_invalid_trace_counters(root,cfg):
    scan=scan_repo(root/'examples/coding-agent',cfg)
    with pytest.raises(InputError):correlate_traces(scan,[{'source_location':scan['candidates'][0]['source'],'tokens':-1}],cfg)

@pytest.mark.parametrize('kind',['opportunity','inventory','experiment','decision','run','trace','config','review','activation','patch-plan'])
def test_all_schemas_valid_and_packaged_identically(root,kind):
    a=read_json(root/'schemas'/f'{kind}.schema.json');b=read_json(root/'jev_integration_evaluator/data'/f'{kind}.schema.json')
    jsonschema.Draft202012Validator.check_schema(a);assert a==b

def test_real_generated_inventory_validates(root,cfg):
    scan=scan_repo(root/'examples/coding-agent',cfg)
    jsonschema.validate(scan,read_json(root/'schemas/inventory.schema.json'))
    for c in scan['candidates']:jsonschema.validate(c,read_json(root/'schemas/opportunity.schema.json'))

def test_research_fixtures_validate(root):
    for r in read_jsonl(root/'examples/research/baseline.jsonl'):jsonschema.validate(r,read_json(root/'schemas/run.schema.json'))
    for r in read_jsonl(root/'examples/research/decisions.jsonl'):jsonschema.validate(r,read_json(root/'schemas/decision.schema.json'))

def test_cli_scan_and_validate_end_to_end(root,tmp_path):
    out=tmp_path/'reports';env={**os.environ,'PYTHONPATH':str(root)}
    cmd=[sys.executable,'-m','jev_integration_evaluator','scan','--repo',str(root/'examples/generic-service'),'--out',str(out)]
    p=subprocess.run(cmd,env=env,cwd=root,capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stderr
    for name in ('JEV_OPPORTUNITIES.md','JEV_ARCHITECTURE.md','JEV_INTEGRATION_PLAN.md','JEV_EXPERIMENT_PLAN.md','JEV_RISK_ANALYSIS.md','JEV_RESULTS.md','jev-opportunities.json','jev-opportunities.csv','jev-config.yaml'):assert (out/name).exists()
    assert read_json(out/'jev-placement-sets.json')['status']=='no_justified_integration_set'
    p=subprocess.run([sys.executable,'-m','jev_integration_evaluator','validate','--kind','inventory','--input',str(out/'jev-opportunities.json')],env=env,cwd=root,capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stderr
