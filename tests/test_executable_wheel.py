"""Offline wheel build and actual host lifecycle without importing the source checkout."""
import json
from pathlib import Path
import subprocess
import sys
from scripts.implementation_fixtures import fixture
from jev_integration_evaluator.io import write_json


def test_installed_wheel_drives_generated_host_and_loads_strict_data(tmp_path):
    root=Path(__file__).resolve().parents[1];dist=tmp_path/'dist';dist.mkdir()
    build=subprocess.run([sys.executable,'-c','import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))',str(dist)],cwd=root,capture_output=True,text=True,timeout=60)
    assert build.returncode==0,build.stderr
    wheel=next(dist.glob('*.whl'));installed=tmp_path/'installed'
    install=subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps','--target',str(installed),str(wheel)],capture_output=True,text=True,timeout=60)
    assert install.returncode==0,install.stderr
    target,bundle=tmp_path/'host',tmp_path/'bundle';inv,spec=fixture(target,'C',tag='wheel_source')
    write_json(tmp_path/'inventory.json',inv);write_json(tmp_path/'spec.json',spec)
    code='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import jev_integration_evaluator as package
assert Path(package.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
from jev_integration_evaluator.io import read_json
from jev_integration_evaluator.integrations.lifecycle import plan_implementation,apply_implementation,rollback_implementation,implementation_status
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.integrations.recipes import recipe_catalog
assert len(recipe_catalog()['recipes'])==13
work=Path(sys.argv[2]);repo=work/'host';bundle=work/'bundle';spec=read_json(work/'spec.json')
p=plan_implementation(repo,read_json(work/'inventory.json'),spec['candidate_id'],spec,bundle)
b=verify_implementation(repo,bundle,'baseline',approve_execution=True)
assert b['status']=='baseline_passed'
a=apply_implementation(repo,bundle,p['bundle_digest'],baseline_sha256=b['receipt_sha256'])
v=verify_implementation(repo,bundle,'modified',approve_execution=True,baseline_sha256=b['receipt_sha256'])
assert v['status']=='verified',v
assert implementation_status(repo,bundle,trusted_receipt_sha256=v['receipt_sha256'])['status']=='verified'
assert rollback_implementation(repo,bundle,a['rollback_digest'])['status']=='rolled_back'
print(json.dumps({'status':'passed','imported_from':package.__file__,'version':package.__version__,'cases':v['scheduled_cases']}))
'''
    run=subprocess.run([sys.executable,'-I','-c',code,str(installed),str(tmp_path)],cwd=tmp_path,capture_output=True,text=True,timeout=60)
    assert run.returncode==0,run.stderr
    result=json.loads(run.stdout)
    assert result['status']=='passed' and result['cases']==3
    assert str(root) not in result['imported_from']
