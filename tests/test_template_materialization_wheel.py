"""Installed wheel catalog API and CLI from an isolated interpreter."""
import json
from pathlib import Path
import site
import subprocess
import sys

from jev_integration_evaluator.io import write_json
from tests.test_template_catalog import example


def test_installed_wheel_template_cli_and_api(tmp_path):
    checkout = Path(__file__).resolve().parents[1]
    dist = tmp_path / 'dist'; dist.mkdir()
    built = subprocess.run(
        [sys.executable, '-c', 'import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))', str(dist)],
        cwd=checkout, capture_output=True, text=True, timeout=90)
    assert built.returncode == 0, built.stderr
    wheel = next(dist.glob('*.whl'))
    installed = tmp_path / 'installed'
    installed_result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--target', str(installed), str(wheel)],
        cwd=tmp_path, capture_output=True, text=True, timeout=90)
    assert installed_result.returncode == 0, installed_result.stderr
    root, request = example('c')
    write_json(tmp_path / 'request.json', request)
    code = '''import io,json,sys
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
sys.path.insert(0,sys.argv[1])
sys.path.append(sys.argv[4])
import jev_integration_evaluator as package
assert Path(package.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
from jev_integration_evaluator.cli import main
from jev_integration_evaluator.io import read_json,write_json
from jev_integration_evaluator.template_catalog import list_templates,inspect_template,validate_template_request,materialize_template,template_error
work=Path(sys.argv[2]);host=Path(sys.argv[3]);request=read_json(work/'request.json')
def cli(*args):
    out=io.StringIO()
    with redirect_stdout(out): assert main(['template',*args])==0
    return json.loads(out.getvalue())
assert cli('list','--json')==list_templates()
assert cli('inspect','python.bounded-tail-call')==inspect_template('python.bounded-tail-call')
try: inspect_template('python.bounded-tail-call','0.9.0')
except Exception as error: expected=template_error(error)
else: raise AssertionError('legacy template version was accepted')
invalid=io.StringIO()
with redirect_stderr(invalid): assert main(['template','inspect','python.bounded-tail-call','--version','0.9.0'])==2
assert json.loads(invalid.getvalue())==expected
bad=dict(request);bad['unexpected']=True;write_json(work/'invalid-request.json',bad)
try: validate_template_request(host,bad)
except Exception as error: expected=template_error(error)
else: raise AssertionError('unknown request field was accepted')
invalid=io.StringIO()
with redirect_stderr(invalid): assert main(['template','validate','--repo',str(host),'--request',str(work/'invalid-request.json')])==2
assert json.loads(invalid.getvalue())==expected
assert cli('validate','--repo',str(host),'--request',str(work/'request.json'))==validate_template_request(host,request)
result=cli('materialize','--repo',str(host),'--request',str(work/'request.json'),'--out',str(work/'cli-render'))
assert result==read_json(work/'cli-render'/'template-lock.json')
assert result['lifecycle']['measured_benefit']=='unknown'
assert materialize_template(host,request,work/'api-render')==result
print(json.dumps({'status':'passed','installed_module':package.__file__,'lock_sha256':result['lock_sha256']}))
'''
    run = subprocess.run([sys.executable, '-I', '-c', code, str(installed), str(tmp_path), str(root), site.getusersitepackages()],
                         cwd=tmp_path, capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)['status'] == 'passed'
