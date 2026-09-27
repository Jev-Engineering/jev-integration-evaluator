import copy,os
from pathlib import Path
import pytest
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews,score_candidate
from jev_integration_evaluator.config import WEIGHTS
from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.questions import api_questions
from jev_integration_evaluator.patterns import roles_for_calls

@pytest.fixture
def inventory(root,cfg): return scan_repo(root/'examples',cfg)

@pytest.mark.parametrize('pattern',list('ABCDEFGHIJKLM'))
def test_all_major_patterns_are_detected(inventory,pattern):
    assert any(c['pattern']==pattern and c['evidence_status']=='structurally_supported' for c in inventory['candidates'])

def test_unknown_estimates_are_not_measurements(inventory):
    for c in inventory['candidates']:
        assert set(c['dimensions'])==set(WEIGHTS)
        assert all(v is None for v in c['estimates'].values())
        assert c['tier']<=1
        assert c['deployment_status']=='not_validated'
        assert c['source']['source_sha256']
        if c['pattern']!='NONE':
            api_questions(c['jev_questions'])
            assert 'Q1?' not in c['jev_questions'][1]['question']
        assert all(d['rationale'] and d['evidence_refs'] for d in c['score_breakdown'].values())

def test_deterministic_service_has_no_recommendation(root,cfg):
    scan=scan_repo(root/'examples/generic-service',cfg)
    assert len(scan['candidates'])>=3
    assert all(c['tier']==0 for c in scan['candidates'])

@pytest.mark.parametrize('name',['print','summarize','paint','format','maximum_model'])
def test_deterministic_calls_are_not_substring_matches(name):
    assert 'deterministic' not in roles_for_calls([{'name':name,'line':1}])

def test_opaque_name_actual_dataflow(tmp_path,cfg):
    (tmp_path/'opaque.py').write_text('def xyz(llm, executor, state):\n    x = llm.choose(state)\n    y = executor.execute_tool(x)\n    return y\n')
    scan=scan_repo(tmp_path,cfg)
    c=next(c for c in scan['candidates'] if c['pattern']=='A')
    assert c['source']['symbol']=='xyz'
    assert c['evidence'][0]['facts']['dataflow']

def test_name_only_review_never_promoted_by_score(tmp_path,cfg):
    (tmp_path/'x.py').write_text('def choose_path(state):\n    return state\n')
    c=scan_repo(tmp_path,cfg)['candidates'][0]
    assert c['evidence_status']=='review_required' and c['tier']==1

def test_durable_id_and_stale_review(tmp_path,cfg):
    path=tmp_path/'x.py';path.write_text('def route(llm,executor,s):\n    return executor.execute_tool(llm.choose(s))\n')
    first=scan_repo(tmp_path,cfg);a=first['candidates'][0]
    path.write_text('\n\n'+path.read_text());shifted=scan_repo(tmp_path,cfg)
    b=next(c for c in shifted['candidates'] if c['candidate_id']==a['candidate_id'])
    assert a['source']['start_line']!=b['source']['start_line']
    assert a['source']['source_sha256']==b['source']['source_sha256']
    path.write_text(path.read_text().replace('llm.choose(s)','llm.choose(s, 2)'))
    newer=scan_repo(tmp_path,cfg)
    with pytest.raises(InputError,match='Stale'):
        apply_reviews(newer,{a['candidate_id']:{'source_sha256':a['source']['source_sha256'],'reviewer':'tester','reason':'read exact code','approved':True}},cfg)

def test_scan_does_not_execute_code_and_ignores_symlinks(tmp_path,cfg):
    marker=tmp_path/'executed'
    (tmp_path/'evil.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\ndef select_path(x):\n    return x\n')
    (tmp_path/'linked.py').symlink_to(tmp_path/'evil.py')
    (tmp_path/'.env').write_text('API_KEY=not-real')
    scan=scan_repo(tmp_path,cfg)
    assert not marker.exists()
    assert not any(f['file']=='linked.py' for f in scan['files'])
    assert not any('not-real' in str(c) for c in scan['candidates'])

def test_truncation_reported(tmp_path,cfg):
    for i in range(3): (tmp_path/f'{i}.py').write_text('def f(x): return x + 1')
    cfg['repository']['max_files']=1
    scan=scan_repo(tmp_path,cfg)
    assert scan['coverage']['truncated']
    assert scan['coverage']['warnings']

def test_syntax_and_other_language_fallback(tmp_path,cfg):
    (tmp_path/'bad.py').write_text('def choose(: broken')
    (tmp_path/'x.go').write_text('func chooseAction(x string) string { return x }')
    s=scan_repo(tmp_path,cfg)
    assert s['coverage']['parser_counts']['lexical_review_only']==2
    assert s['coverage']['warnings']
    assert all(c['tier']<=1 for c in s['candidates'])

def test_native_typescript_ast(root,cfg):
    scan=scan_repo(root/'examples/polyglot',cfg)
    ts=[x for x in scan['files'] if x['file']=='router.ts']
    if ts[0]['parser']!='typescript_ast': pytest.skip('Trusted Node/TypeScript 5.x/6.x not installed')
    assert any(c['pattern']=='A' and c['source']['symbol']=='opaqueSeam' for c in scan['candidates'])

def test_no_target_node_plugins(tmp_path,cfg):
    (tmp_path/'node_modules'/'typescript').mkdir(parents=True)
    (tmp_path/'node_modules'/'typescript'/'index.js').write_text('throw Error("target plugin loaded")')
    (tmp_path/'x.ts').write_text('export function choosePath(llm: any) { return llm.choose({}); }')
    scan=scan_repo(tmp_path,cfg)
    assert all('node_modules' not in f['file'] for f in scan['files'])

def test_exact_antipattern_cannot_be_waived(root,cfg):
    scan=scan_repo(root/'examples/generic-service',cfg);c=scan['candidates'][0]
    update={'source_sha256':c['source']['source_sha256'],'reviewer':'r','reason':'x','approved':True,'deterministic_alternative':'none'}
    with pytest.raises(InputError): apply_reviews(scan,{c['candidate_id']:update},cfg)

def test_hard_real_time_rejected(inventory,cfg):
    c=copy.deepcopy(next(c for c in inventory['candidates'] if c['tier']==1));c['hard_real_time']=True
    score_candidate(c,cfg);assert c['tier']==0

def test_callgraph_local_edges(tmp_path,cfg):
    (tmp_path/'x.py').write_text('def outer(x):\n    return inner(x)\ndef inner(x):\n    return x+1\n')
    scan=scan_repo(tmp_path,cfg)
    assert any('inner' in str(e) and 'outer' in str(e) for e in scan['architecture']['edges'])
