"""The installed artifact must execute the real session/engine, not the checkout."""
import json
from pathlib import Path
import subprocess
import sys
from scripts.implementation_fixtures import fixture


def test_installed_wheel_repository_command_full_lifecycle(tmp_path):
    source=Path(__file__).resolve().parents[1]
    dist=tmp_path/'dist';dist.mkdir()
    build=subprocess.run([sys.executable,'-c','import setuptools.build_meta,sys;setuptools.build_meta.build_wheel(sys.argv[1])',str(dist)],cwd=source,capture_output=True,text=True,timeout=60)
    assert build.returncode==0,build.stderr
    installed=tmp_path/'installed'
    install=subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps','--target',str(installed),str(next(dist.glob('*.whl')))],capture_output=True,text=True,timeout=60)
    assert install.returncode==0,install.stderr
    host=tmp_path/'host';inventory,spec=fixture(host,'C',tag='installed_session_host')
    (tmp_path/'prepared.json').write_text(json.dumps(dict(schema_version='1.0',adapter='recorded-reviewed-input-v1',inventory=inventory,spec=spec)))
    check='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from jev_integration_evaluator import repository_run as run
from jev_integration_evaluator.integrations import lifecycle as engine
assert Path(run.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
work=Path(sys.argv[2]);root=work/'host';session=work/'session'
original={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
context=run.request_context(objective='Synthetic installed session qualification',saved_answers={'benefit':None})
inspection=run.inspect_repository(root,context=context)
scope=dict(schema_version='1.0',kind='repository-run-scope-v1',reference='synthetic-operator',repository_identity=inspection['report']['repository_identity'],context_sha256=inspection['context_sha256'],bundle_digest=None,trusted_session_head=None,trusted_baseline_receipt=None,trusted_modified_receipt=None,rollback_digest=None,execution_environment='trusted_host',grants={**run.ZERO_GRANTS,'prepare':True})
plan=run.run_repository(root,session,context=context,prepared=json.loads((work/'prepared.json').read_text()),scope=scope,stop_after='plan')
assert plan['status']=='planned'
scope.update(bundle_digest=plan['bundle_digest'],trusted_session_head=plan['session_head_sha256'],grants={**run.ZERO_GRANTS,'baseline':True,'apply':True,'modified':True})
result=run.run_repository(root,session,scope=scope)
assert result['status']=='verified' and len(result['retained_schedules'])==2
assert result['retained_schedules'][0]['scheduled_cases']==1
assert result['retained_schedules'][1]['scheduled_cases']==3
assert run.run_repository(root,session)['status']=='recorded_untrusted'
state=json.loads((session/'journal.jsonl').read_text().splitlines()[-1])['state']
bundle=Path(state['bundle']['path']);bundle_plan=json.loads((bundle/'implementation-plan.json').read_text())
scope.update(trusted_session_head=result['session_head_sha256'],rollback_digest=engine.rollback_digest(bundle_plan),grants={**run.ZERO_GRANTS,'rollback':True})
restored=run.run_repository(root,session,scope=scope,recover=True)
assert restored['status']=='rolled_back'
assert original=={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
print(json.dumps({'status':'passed','classification':'synthetic','baseline_cases':1,'modified_cases':3,'target_restored':True,'imported_from_installed_artifact':True,'activation_authorized':False}))
'''
    result=subprocess.run([sys.executable,'-I','-c',check,str(installed),str(tmp_path)],cwd=tmp_path,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['target_restored'] is True
