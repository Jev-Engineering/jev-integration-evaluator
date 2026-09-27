"""Historical parser-bound examples and fresh local discovery, never host execution."""
import ast
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from jev_integration_evaluator import capabilities as c

ROOT=Path(__file__).resolve().parents[1]
EXAMPLES=ROOT/'examples/capabilities'
LOCAL_PARSER=f'{sys.implementation.name}-{sys.version_info.major}.{sys.version_info.minor}-ast'


def example(name):
    return json.loads((EXAMPLES/(name+'.example.json')).read_text(encoding='utf-8'))


def assert_source_anchor(root, source, parser_identity):
    raw=(root/source['file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==source['file_sha256']
    node=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)
              and n.name==source['qualified_symbol'])
    assert [node.lineno,node.end_lineno]==[source['start_line'],source['end_line']]
    # AST serialization is intentionally bound to the recorded interpreter.
    # A different parser still checks source bytes, lines and artifact links;
    # fresh discovery below independently checks that parser's own AST anchors.
    if parser_identity==LOCAL_PARSER:
        assert hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()==source['ast_sha256']


@pytest.mark.parametrize('name,kind',[
    ('report','repository-capabilities'),('nomination','candidate-nomination'),
    ('admitted','admitted-nomination'),
])
def test_example_contracts_and_source_hashes(name,kind):
    report=example('report')
    value=example(name)
    c._schema(kind,value)
    if name=='report':
        data=dict(value);recorded=data.pop('report_sha256')
        assert recorded==c._digest(data)
        sources=[s['source'] for s in value['seams']]
    else:sources=[value['source']]
    for source in sources:
        assert source in [seam['source'] for seam in report['seams']]
        assert_source_anchor(EXAMPLES/'opaque_host',source,report['parser_identity'])


def test_example_admission_provenance_does_not_claim_qualification():
    r=example('report');n=example('nomination');a=example('admitted')
    assert n['report_sha256']==a['report_sha256']==r['report_sha256']
    assert a['nomination_sha256']==c._digest(n)
    assert a['benefit'] is None and not a['execution_qualified']
    assert a['semantic_review']=='not_performed' and not any(a['authorization'].values())


@pytest.mark.skipif(os.name!='posix',reason='Secure discovery requires POSIX descriptor-relative filesystem operations')
def test_examples_regenerate_local_parser_anchors_and_admission(tmp_path):
    host=tmp_path/'host';host.mkdir()
    for source in (EXAMPLES/'opaque_host').glob('*.py'):
        (host/source.name).write_bytes(source.read_bytes())
    report=c.discover_repository(host)
    assert report['parser_identity']==LOCAL_PARSER
    assert report['coverage']['complete_within_policy']
    for seam in report['seams']:
        assert_source_anchor(host,seam['source'],LOCAL_PARSER)
        assert seam['seam_id']==c._digest([c.VERSION,seam['source']])
    nomination=deepcopy(example('nomination'))
    source=nomination['source']
    seam=next(s for s in report['seams'] if s['source']['file']==source['file']
              and s['source']['qualified_symbol']==source['qualified_symbol'])
    nomination.update(report_sha256=report['report_sha256'],seam_id=seam['seam_id'],source=deepcopy(seam['source']))
    nomination['evidence']=[{key:seam['source'][key] for key in ('file','file_sha256','start_line','end_line')}]
    admitted=c.admit_nomination(host,nomination,expected_report_sha256=report['report_sha256'])
    for kind,value in [('repository-capabilities',report),('candidate-nomination',nomination),('admitted-nomination',admitted)]:
        c._schema(kind,value)
    assert admitted['source']==seam['source']
    assert admitted['nomination_sha256']==c._digest(nomination)
    assert admitted['report_sha256']==report['report_sha256']
    assert admitted['semantic_review']=='not_performed' and not admitted['execution_qualified']
    assert admitted['benefit'] is None and not any(admitted['authorization'].values())
    assert c.admit_nomination(host,nomination,expected_report_sha256=report['report_sha256'])==admitted


@pytest.mark.skipif(os.name!='posix',reason='Secure discovery requires POSIX descriptor-relative filesystem operations')
def test_thin_script_runs_from_outside_checkout_without_host_execution(tmp_path):
    host=tmp_path/'host';host.mkdir()
    source='raise RuntimeError("TARGET MUST NOT RUN")\n\ndef n4(p):\n return p.dispatch()\n\ndef v8(p):\n return n4(p)\n'
    (host/'opaque.py').write_text(source)
    out=tmp_path/'report.json'
    result=subprocess.run([sys.executable,str(ROOT/'scripts/discover_capabilities.py'),
         'discover','--repo',str(host),'--out',str(out)],cwd=tmp_path,
         capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['status']=='written'
    assert json.loads(out.read_text())['discovery_outcome']=='review_required'
    assert (host/'opaque.py').read_text()==source
    assert os.stat(out).st_mode&0o777==0o600
