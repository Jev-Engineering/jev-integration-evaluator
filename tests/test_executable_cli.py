"""Installed-style CLI subprocess contracts, not just parser/help tests."""
import json
from pathlib import Path
import subprocess
import sys
import pytest
from scripts.implementation_fixtures import fixture
from jev_integration_evaluator.io import write_json,read_json

ROOT=Path(__file__).resolve().parents[1]

def cli(*args):
    return subprocess.run([sys.executable,'-m','jev_integration_evaluator',*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=60)


def test_all_command_entry_points_and_catalog():
    catalog=cli('implementation-recipes','--json')
    assert catalog.returncode==0
    assert {r['id'] for r in json.loads(catalog.stdout)['recipes']}=={'python.'+p for p in 'ABCDEFGHIJKLM'}
    for name in ('implementation-recipes','implement-plan','implement-apply','implement-verify','implement-status','implement-rollback'):
        result=subprocess.run([sys.executable,str(ROOT/'scripts'/(name.replace('-','_')+'.py')),'--help'],capture_output=True,text=True,timeout=20)
        assert result.returncode==0 and name in result.stdout


def test_cli_end_to_end_actual_host_demo(tmp_path):
    result=subprocess.run([sys.executable,str(ROOT/'scripts/run_implementation_demo.py'),'--out',str(tmp_path/'demo'),'--patterns','C'],cwd=ROOT,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stderr
    summary=read_json(tmp_path/'demo/summary.json')
    assert summary['status']=='passed' and summary['targets_applied_unverified']==0
    assert summary['recipes'][0]['modified_cases']==3 and summary['recipes'][0]['target_bytes_restored']


def test_cli_missing_execution_scope_returns_blocked_without_running(tmp_path):
    root,bundle=tmp_path/'host',tmp_path/'bundle';inv,spec=fixture(root)
    ip,sp=tmp_path/'inventory.json',tmp_path/'spec.json';write_json(ip,inv);write_json(sp,spec)
    result=cli('implement-plan','--repo',root,'--inventory',ip,'--candidate',spec['candidate_id'],'--spec',sp,'--out',bundle)
    assert result.returncode==0 and json.loads(result.stdout)['status']=='planned'
    denied=cli('implement-verify','--phase','baseline','--repo',root,'--bundle',bundle)
    assert denied.returncode==2 and json.loads(denied.stderr)['status']=='blocked'
    assert not (bundle/'baseline-receipt.json').exists()


def test_cli_semantic_schema_validation_and_failed_case_exit(tmp_path):
    root,bundle=tmp_path/'host',tmp_path/'bundle';inv,spec=fixture(root)
    ip,sp=tmp_path/'inventory.json',tmp_path/'spec.json';write_json(ip,inv)
    spec['label_actions'].pop('uncertain');write_json(sp,spec)
    assert cli('validate','--kind','implementation-spec','--input',sp).returncode==2
    spec['label_actions']['uncertain']=None
    spec['verification']['cases'][0]['baseline']['result']='intentionally_wrong_expected_result';write_json(sp,spec)
    assert cli('implement-plan','--repo',root,'--inventory',ip,'--candidate',spec['candidate_id'],'--spec',sp,'--out',bundle).returncode==0
    failed=cli('implement-verify','--phase','baseline','--repo',root,'--bundle',bundle,'--approve-execution')
    assert failed.returncode==3 and json.loads(failed.stdout)['status']=='verification_failed'
