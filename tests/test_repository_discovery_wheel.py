"""Installed staged discovery reaches the legacy inventory and plan contracts.

All hosts and reviews are synthetic; planning never executes or applies a target.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from jev_integration_evaluator.io import digest


pytestmark=pytest.mark.skipif(os.name!='posix',reason='Published secure discovery requires POSIX')


@pytest.fixture(scope='module')
def installed(tmp_path_factory):
    root=Path(__file__).resolve().parents[1]
    work=tmp_path_factory.mktemp('installed-discovery-bridge')
    dist=work/'dist';dist.mkdir()
    build=subprocess.run([sys.executable,'-c',
        'import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))',str(dist)],
        cwd=root,capture_output=True,text=True,timeout=60)
    assert build.returncode==0,build.stderr
    destination=work/'installed'
    result=subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps',
                           '--target',str(destination),str(next(dist.glob('*.whl')))],
                          capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    return destination


def run(installed,work,*args):
    bootstrap='''import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from jev_integration_evaluator import cli, capabilities, nomination_inventory, repository_discovery
for module in (cli,capabilities,nomination_inventory,repository_discovery):
    assert Path(module.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
raise SystemExit(cli.main(sys.argv[2:]))
'''
    result=subprocess.run([sys.executable,'-I','-c',bootstrap,str(installed),*args],
                          cwd=work,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr or result.stdout
    return json.loads(result.stdout)


def write(path,value):
    path.write_text(json.dumps(value),encoding='utf-8')
    return str(path)


def stages(installed,work,host,symbol):
    report_path=work/'report.json';prepared_path=work/'prepared.json';reviewed_path=work/'reviewed.json'
    run(installed,work,'repository-discovery',str(host),'--out',str(report_path))
    report=json.loads(report_path.read_text())
    seam=next(s for s in report['seams'] if s['source']['qualified_symbol']==symbol)
    source=seam['source']
    nomination={'schema_version':'1.0','discovery_version':report['discovery_version'],
                'report_sha256':report['report_sha256'],'seam_id':seam['seam_id'],'source':source,
                'pattern':'C','proposer':'synthetic-installed-wheel-review',
                'rationale':'Finite dispatch hypothesis, not authority or measured benefit.',
                'evidence':[{k:source[k] for k in ('file','file_sha256','start_line','end_line')}]}
    nominations_path=write(work/'nominations.json',[nomination])
    run(installed,work,'repository-discovery',str(host),'--stage','prepare',
        '--capabilities',str(report_path),'--nominations',nominations_path,'--out',str(prepared_path))
    prepared=json.loads(prepared_path.read_text())
    candidate=next(c for c in prepared['inventory']['candidates'] if c['source']['symbol']==symbol and c['pattern']=='C')
    assert not candidate['semantic_review']['approved']
    review={'schema_version':'1.0','prepared_sha256':prepared['prepared_sha256'],
            'reviews':{candidate['candidate_id']:{'source_sha256':candidate['source']['source_sha256'],
                       'reviewer':'synthetic-installed-wheel-review','reason':'Fixture dispatch reviewed; no execution authority.',
                       'approved':True}}}
    review_path=write(work/'review.json',review)
    run(installed,work,'repository-discovery',str(host),'--stage','review','--capabilities',str(report_path),
        '--prepared',str(prepared_path),'--review',review_path,'--out',str(reviewed_path))
    reviewed=json.loads(reviewed_path.read_text())
    for path,kind in ((prepared_path,'repository-nominated-inventory-v1'),
                      (review_path,'repository-semantic-review-v1'),(reviewed_path,'repository-reviewed-inventory-v1')):
        assert run(installed,work,'validate','--kind',kind,'--input',str(path))['source_revalidated'] is False
    for candidate in reviewed['inventory']['candidates']:
        path=write(work/'candidate.json',candidate)
        assert run(installed,work,'validate','--kind','opportunity','--input',path)['status']=='valid'
    assert reviewed['binding_review']=='not_performed'
    assert all(reviewed[k] is False for k in ('implementation_verified','mutation_authorized',
                                             'provider_execution_authorized','runtime_activation_authorized'))
    for path in (report_path,prepared_path,reviewed_path):
        assert path.stat().st_mode&0o777==0o600
    return reviewed


def test_installed_wheel_builds_reviewed_legacy_inventory_without_target_execution(installed,tmp_path):
    host=tmp_path/'host';host.mkdir()
    source='raise RuntimeError("TARGET MUST NEVER EXECUTE")\n\ndef q5(x):\n return x.dispatch()\n\ndef z93(x):\n return q5(x)\n'
    (host/'opaque.py').write_text(source)
    before={p.name:(p.read_bytes(),p.stat().st_mode) for p in host.iterdir()}
    reviewed=stages(installed,tmp_path,host,'z93')
    candidate=next(c for c in reviewed['inventory']['candidates'] if c['source']['symbol']=='z93')
    assert candidate['semantic_review']['approved']
    assert all(v is None for v in candidate['estimates'].values())
    assert candidate['policy']['default_mode']=='off'
    assert before=={p.name:(p.read_bytes(),p.stat().st_mode) for p in host.iterdir()}


def test_installed_reviewed_inventory_feeds_existing_recipe_plan_without_application(installed,tmp_path):
    from scripts.implementation_fixtures import fixture
    host=tmp_path/'host'
    _,spec=fixture(host,'C',tag='bridge_wheel')
    before={p.name:(p.read_bytes(),p.stat().st_mode) for p in host.iterdir()}
    reviewed=stages(installed,tmp_path,host,spec['source']['symbol'])
    inventory=reviewed['inventory']
    candidate=next(c for c in inventory['candidates'] if c['source']['symbol']==spec['source']['symbol'] and c['pattern']=='C')
    spec=copy.deepcopy(spec)
    spec.update(candidate_id=candidate['candidate_id'],experiment_id=candidate['recommended_experiment']['id'],
                inventory_sha256=digest(inventory),inventory_fingerprint=inventory['scan_fingerprint'])
    inventory_path=write(tmp_path/'inventory.json',inventory)
    spec_path=write(tmp_path/'binding.json',spec)
    summary=run(installed,tmp_path,'implement-plan','--repo',str(host),'--inventory',inventory_path,
                '--candidate',candidate['candidate_id'],'--spec',spec_path,'--out',str(tmp_path/'bundle'))
    assert summary['status']=='planned' and not summary['target_modified'] and not summary['target_executed']
    assert (tmp_path/'bundle'/'implementation.diff').is_file()
    assert before=={p.name:(p.read_bytes(),p.stat().st_mode) for p in host.iterdir()}
