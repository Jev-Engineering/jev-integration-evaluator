"""Offline wheel build and actual host lifecycle without importing the source checkout."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import pytest
from scripts.implementation_fixtures import fixture
from jev_integration_evaluator.io import write_json, digest


@pytest.mark.parametrize('layout', ['flat', 'package', 'src', 'namespace'])
def test_installed_wheel_drives_generated_host_and_loads_strict_data(tmp_path, layout):
    root=Path(__file__).resolve().parents[1];dist=tmp_path/'dist';dist.mkdir()
    build=subprocess.run([sys.executable,'-c','import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))',str(dist)],cwd=root,capture_output=True,text=True,timeout=60)
    assert build.returncode==0,build.stderr
    wheel=next(dist.glob('*.whl'));installed=tmp_path/'installed'
    install=subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps','--target',str(installed),str(wheel)],capture_output=True,text=True,timeout=60)
    assert install.returncode==0,install.stderr
    target,bundle=tmp_path/'host',tmp_path/'bundle';inv,spec=fixture(target,'C',tag='wheel_source',layout=layout)
    if layout == 'flat':
        runtime_files={
            'requirements.lock':('dependency_lock','jev-integration-evaluator==1.3.0.dev1\n',
                                 'jev-integration-evaluator==1.3.0.dev11\n'),
            'runtime.json':('configuration','{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
                            '{"jev_runtime":{"mode":"off","credential_ref":"env:TYPESAFE_API_KEY"}}\n'),
        }
        for name,(_,old,_) in runtime_files.items():
            (target/name).write_text(old,encoding='utf-8')
            inv['configuration_evidence'].append({'file':name,'sha256':hashlib.sha256(old.encode()).hexdigest()})
        inv['analysis_identity']['configuration_digest']=digest(inv['configuration_evidence'])
        inv['scan_fingerprint']=digest(inv['analysis_identity'])
        spec['inventory_sha256']=digest(inv)
        spec['inventory_fingerprint']=inv['scan_fingerprint']
        spec['runtime_files']=[{'file':name,'kind':kind,
            'old_sha256':hashlib.sha256(old.encode()).hexdigest(),'new_content':new}
            for name,(kind,old,new) in runtime_files.items()]
        spec['output']['permitted_edits'].extend(runtime_files)
        spec['host_lifecycle'] = {'kind': 'module-startup-v1', 'startup': 'start_jev_runtime',
                                  'shutdown': 'stop_jev_runtime', 'complete_task': 'finish_jev_task'}
    write_json(tmp_path/'inventory.json',inv);write_json(tmp_path/'spec.json',spec)
    code='''import json,sys
from pathlib import Path
import hashlib, importlib
sys.path.insert(0,sys.argv[1])
import jev_integration_evaluator as package
assert Path(package.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
from jev_integration_evaluator.io import read_json
from jev_integration_evaluator.integrations.lifecycle import plan_implementation,apply_implementation,rollback_implementation,implementation_status
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.integrations.recipes import recipe_catalog
from jev_integration_evaluator.integrations.runtime_lifecycle import HostRuntimeLifecycle
assert HostRuntimeLifecycle.__module__.startswith('jev_integration_evaluator.')
assert len(recipe_catalog()['recipes'])==13
work=Path(sys.argv[2]);repo=work/'host';bundle=work/'bundle';spec=read_json(work/'spec.json')
p=plan_implementation(repo,read_json(work/'inventory.json'),spec['candidate_id'],spec,bundle)
b=verify_implementation(repo,bundle,'baseline',approve_execution=True)
assert b['status']=='baseline_passed'
a=apply_implementation(repo,bundle,p['bundle_digest'],baseline_sha256=b['receipt_sha256'])
v=verify_implementation(repo,bundle,'modified',approve_execution=True,baseline_sha256=b['receipt_sha256'])
assert v['status']=='verified',v
assert implementation_status(repo,bundle,trusted_receipt_sha256=v['receipt_sha256'])['status']=='verified'
if 'host_lifecycle' in spec:
    from jev_integration_evaluator.integrations.probe import SyntheticClient, SyntheticAudit
    dependency_plan={'files':[{'path':str((repo/name).resolve()),
        'sha256':hashlib.sha256((repo/name).read_bytes()).hexdigest()}
        for name in ('requirements.lock','runtime.json')]}
    sys.path.insert(0,str(repo))
    host=importlib.import_module(Path(spec['source']['file']).stem)
    runtime=host.start_jev_runtime(budget_limits=dict(max_calls_per_task=2,max_cost_per_task=2,
        max_total_calls=2,max_total_cost=2,max_in_flight=1,max_tasks=2),
        audit_log=SyntheticAudit(),dependency_plan=dependency_plan,
        client=SyntheticClient(spec['verification']['cases'][0]['assessment_label']))
    request=spec['verification']['cases'][0]['request']
    entry=getattr(host,spec['verification']['entry_point'])
    assert entry(request)==entry(request)
    assert runtime.router(spec['candidate_id'],request) is runtime.router(spec['candidate_id'],request)
    host.finish_jev_task(request[spec['runtime']['task_field']])
    assert runtime.coordinator.snapshot()['closed_tasks']==1
    host.stop_jev_runtime()
    assert runtime._closed
assert rollback_implementation(repo,bundle,a['rollback_digest'])['status']=='rolled_back'
print(json.dumps({'status':'passed','imported_from':package.__file__,'version':package.__version__,'cases':v['scheduled_cases']}))
'''
    run=subprocess.run([sys.executable,'-I','-c',code,str(installed),str(tmp_path)],cwd=tmp_path,capture_output=True,text=True,timeout=60)
    assert run.returncode==0,run.stderr
    result=json.loads(run.stdout)
    assert result['status']=='passed' and result['cases']==3
    assert str(root) not in result['imported_from']
