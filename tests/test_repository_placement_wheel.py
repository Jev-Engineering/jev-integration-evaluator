"""Installed repository-scope review uses packaged code and contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != "posix", reason="Secure discovery requires POSIX")
def test_installed_scope_review_distinguishes_negative_from_empty(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dist = tmp_path / "dist"
    dist.mkdir()
    build = subprocess.run(
        [sys.executable, "-c",
         "import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))",
         str(dist)], cwd=root, capture_output=True, text=True, timeout=90)
    assert build.returncode == 0, build.stderr
    installed = tmp_path / "installed"
    install = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-index", "--no-deps",
         "--target", str(installed), str(next(dist.glob("*.whl")))],
        capture_output=True, text=True, timeout=90)
    assert install.returncode == 0, install.stderr
    code = r'''
import copy,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from jev_integration_evaluator import capabilities as cap, nomination_inventory as bridge, placement_selection as scope
from jev_integration_evaluator.config import DEFAULT
assert Path(scope.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
host=Path(sys.argv[2])/'host';host.mkdir()
source='raise RuntimeError("TARGET MUST NOT IMPORT")\n\ndef b(x):\n return x["operation"](x)\n\ndef q(x):\n return b(x)\n'
(host/'opaque.py').write_text(source)
cfg=copy.deepcopy(DEFAULT);cfg['repository']['typescript_ast']=False
report=bridge.discover_repository_capabilities(host,cfg)
prepared=bridge.prepare_nominated_inventory(host,report,[],cfg)
semantic={'schema_version':'1.0','prepared_sha256':prepared['prepared_sha256'],'reviews':{}}
empty=scope.prepare_placement_context(host,report,prepared,semantic,cfg)
assert empty['outcome']=='no_candidates_discovered'
review={'schema_version':'1.0','contract':scope.SCOPE_REVIEW,'report_sha256':report['report_sha256'],
 'prepared_sha256':prepared['prepared_sha256'],'reviewer':'synthetic-wheel-reviewer',
 'reason':'Review all enumerated synthetic source for this fixture only.',
 'pattern_scope':scope.PATTERN_SCOPE,'snapshot_scope':report['snapshot_scope'],
 'files':[{'file':f['file'],'file_sha256':f['sha256'],'line_count':f['line_count'],
  'coverage':'entire_file','disposition':'no_useful_placement','reason':'Synthetic whole-file judgment.'} for f in report['files']],
 'seams':[{'seam_id':s['seam_id'],'source':s['source'],'disposition':'no_useful_placement',
  'reason':'Synthetic exact-seam judgment.'} for s in report['seams']]}
negative=scope.prepare_placement_context(host,report,prepared,semantic,cfg,scope_review=review)
assert negative['outcome']=='no_useful_placement'
assert negative['scope_review']['files_reviewed']==negative['scope_review']['files_total']
assert negative['scope_review']['seams_reviewed']==negative['scope_review']['seams_total']
assert (host/'opaque.py').read_text()==source
print(json.dumps({'installed':True,'empty':empty['outcome'],'negative':negative['outcome']}))
'''
    run = subprocess.run(
        [sys.executable, "-I", "-c", code, str(installed), str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {
        "installed": True, "empty": "no_candidates_discovered",
        "negative": "no_useful_placement"}
