"""Synthetic reproductions of mixed whole-source/candidate review contradictions.

These fixed assertions do not call target code, a provider, or a mutation API.
The implementation under test is the existing PR #22 placement_selection module,
not a parallel selection engine.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import nomination_inventory as bridge
from jev_integration_evaluator import placement_selection as selection
from jev_integration_evaluator.config import DEFAULT

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Inherited secure discovery requires POSIX')
ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'def b(x):\n    return x["operation"](x)\n\ndef q(x):\n    return b(x)\n'


def case(root, *, approved=True, other_file=False):
    root.mkdir()
    (root/'opaque.py').write_text(SOURCE)
    if other_file:(root/'other.py').write_text('def elsewhere(x):\n    return x.work()\n')
    cfg=copy.deepcopy(DEFAULT);cfg['repository']['typescript_ast']=False
    report=bridge.discover_repository_capabilities(root,cfg)
    seam=next(s for s in report['seams'] if s['source']['qualified_symbol']=='q')
    a=seam['source']
    nomination={'schema_version':'1.0','discovery_version':cap.VERSION,
        'report_sha256':report['report_sha256'],'seam_id':seam['seam_id'],'source':copy.deepcopy(a),
        'pattern':'C','proposer':'synthetic-conflict-fixture-author',
        'rationale':'Finite existing choice for a fixed conflict regression; no execution authority.',
        'evidence':[{'file':a['file'],'file_sha256':a['file_sha256'],
                     'start_line':a['start_line'],'end_line':a['end_line']}]}
    prepared=bridge.prepare_nominated_inventory(root,report,[nomination],cfg)
    review={'schema_version':'1.0','prepared_sha256':prepared['prepared_sha256'],
        'reviews':{c['candidate_id']:{'source_sha256':c['source']['source_sha256'],
            'approved':approved,'reviewer':'synthetic-candidate-reviewer',
            'reason':'Fixed source-bound candidate judgment, never an authority grant.'}
            for c in prepared['inventory']['candidates']}}
    scope={'schema_version':'1.0','contract':selection.SCOPE_REVIEW,
        'report_sha256':report['report_sha256'],'prepared_sha256':prepared['prepared_sha256'],
        'reviewer':'synthetic-scope-reviewer','reason':'Explicit full source judgment for the regression.',
        'pattern_scope':selection.PATTERN_SCOPE,'snapshot_scope':report['snapshot_scope'],
        'files':[{'file':f['file'],'file_sha256':f['sha256'],'line_count':f['line_count'],
            'coverage':'entire_file','disposition':'useful','reason':'Entire file includes a potentially useful seam.'}
            for f in report['files']],
        'seams':[{'seam_id':s['seam_id'],'source':copy.deepcopy(s['source']),
            'disposition':'useful','reason':'Exact seam source considered useful in this control.'}
            for s in report['seams']]}
    cid=next(c['candidate_id'] for c in prepared['inventory']['candidates'] if c['source']['symbol']=='q')
    return {'repo':root,'report':report,'prepared':prepared,'semantic_review':review,'cfg':cfg},scope,cid,seam['seam_id']


def request(context,cid):
    return {'schema_version':'1.0','contract':selection.SELECTION_REVIEW,
        'context_sha256':context['context_sha256'],'candidate_ids':[cid],
        'reviewer':'synthetic-experimental-reviewer','reason':'Test an exact source-bound proposed choice.',
        'approved':True,'mode':'experimental',
        'resource_bounds':{'max_calls_total':None,'max_cost_total_usd':None,'deadline_seconds':None}}


@pytest.mark.parametrize('other_file',[False,True])
def test_negative_selected_seam_is_not_hidden_by_useful_other_scope(tmp_path,other_file):
    args,scope,cid,sid=case(tmp_path/'host',other_file=other_file)
    next(row for row in scope['seams'] if row['seam_id']==sid)['disposition']='no_useful_placement'
    before={p.relative_to(args['repo']).as_posix():(p.read_bytes(),p.stat().st_mode)
            for p in args['repo'].rglob('*') if p.is_file()}
    ctx=selection.prepare_placement_context(**args,scope_review=scope)
    assert not ctx['scope_review']['no_useful_judgment']
    assert ctx['outcome']=='insufficient_evidence'
    assert ctx['next_action']=='reconcile_conflicting_semantic_reviews'
    selected=selection.select_experimental_placements(**args,scope_review=scope,selection_review=request(ctx,cid))
    assert selected['status']=='blocked'
    assert selected['requested_count']==1 and selected['selected_count']==0
    assert selected['selected_candidate_ids']==[]
    assert {'candidate_id':cid,'reason':'insufficient_evidence'} in selected['failures']
    assert selected['authorization']==selection.DENIED
    after={p.relative_to(args['repo']).as_posix():(p.read_bytes(),p.stat().st_mode)
           for p in args['repo'].rglob('*') if p.is_file()}
    assert before==after


def test_negative_entire_file_cannot_be_overridden_by_positive_candidate(tmp_path):
    args,scope,cid,sid=case(tmp_path/'host',other_file=True)
    next(row for row in scope['files'] if row['file']=='opaque.py')['disposition']='no_useful_placement'
    ctx=selection.prepare_placement_context(**args,scope_review=scope)
    assert ctx['scope_review']['useful']>0
    assert ctx['outcome']=='insufficient_evidence'
    selected=selection.select_experimental_placements(**args,scope_review=scope,selection_review=request(ctx,cid))
    assert selected['status']=='blocked' and selected['selected_count']==0


def test_caller_mutation_after_scope_validation_cannot_clear_conflict(tmp_path, monkeypatch):
    args, scope, cid, sid = case(tmp_path/'host')
    next(row for row in scope['seams'] if row['seam_id'] == sid)['disposition'] = 'no_useful_placement'
    original = selection._scope_assessment

    def mutate_caller_after_validation(report, prepared, review):
        result = original(report, prepared, review)
        next(row for row in scope['seams'] if row['seam_id'] == sid)['disposition'] = 'useful'
        return result

    monkeypatch.setattr(selection, '_scope_assessment', mutate_caller_after_validation)
    context = selection.prepare_placement_context(**args, scope_review=scope)
    assert context['outcome'] == 'insufficient_evidence'
    assert context['next_action'] == 'reconcile_conflicting_semantic_reviews'


def test_negative_unselected_callback_does_not_reject_consistent_selected_seam(tmp_path):
    args,scope,cid,sid=case(tmp_path/'host')
    for row in scope['seams']:
        if row['seam_id']!=sid:row['disposition']='no_useful_placement'
    ctx=selection.prepare_placement_context(**args,scope_review=scope)
    assert ctx['outcome']=='experimental_review_required'
    selected=selection.select_experimental_placements(**args,scope_review=scope,selection_review=request(ctx,cid))
    assert selected['selected_candidate_ids']==[cid]
    assert all(value is None for value in selected['placements'][0]['estimates'].values())
    assert not any(selected['authorization'].values())


def test_complete_negative_judgment_without_positive_candidate_is_retained(tmp_path):
    args,scope,cid,sid=case(tmp_path/'host',approved=False)
    for row in scope['files']+scope['seams']:row['disposition']='no_useful_placement'
    ctx=selection.prepare_placement_context(**args,scope_review=scope)
    assert ctx['outcome']=='no_useful_placement'
    assert ctx['scope_review']['complete']


def test_unresolved_selected_scope_stays_blocked(tmp_path):
    args,scope,cid,sid=case(tmp_path/'host')
    next(row for row in scope['seams'] if row['seam_id']==sid)['disposition']='unresolved'
    ctx=selection.prepare_placement_context(**args,scope_review=scope)
    assert ctx['outcome']=='insufficient_evidence'
    result=selection.select_experimental_placements(**args,scope_review=scope,selection_review=request(ctx,cid))
    assert result['status']=='blocked' and result['selected_count']==0


def test_absent_scope_review_keeps_existing_experimental_contract(tmp_path):
    args,scope,cid,sid=case(tmp_path/'host')
    ctx=selection.prepare_placement_context(**args)
    record=selection.select_experimental_placements(**args,selection_review=request(ctx,cid))
    assert record['selected_candidate_ids']==[cid]
    assert record['runtime_mode']=='off'
    assert record['missing_resource_bounds']==list(selection.BOUND_KEYS)


def test_cli_returns_blocked_with_complete_requested_denominator(tmp_path):
    args,scope,cid,sid=case(tmp_path/'host')
    next(row for row in scope['seams'] if row['seam_id']==sid)['disposition']='no_useful_placement'
    ctx=selection.prepare_placement_context(**args,scope_review=scope)
    data={'report':args['report'],'prepared':args['prepared'],
          'semantic-review':args['semantic_review'],'config-json':args['cfg'],
          'scope-review':scope,'selection-review':request(ctx,cid)}
    command=[sys.executable,'-m','jev_integration_evaluator.placement_selection','select',
             '--repo',str(args['repo']),'--out',str(tmp_path/'result.json')]
    for key,value in data.items():
        path=tmp_path/(key+'.json');path.write_text(json.dumps(value));command+=['--'+key,str(path)]
    proc=subprocess.run(command,cwd=tmp_path,env=dict(os.environ,PYTHONPATH=str(ROOT)),
                        capture_output=True,text=True,timeout=20)
    assert proc.returncode==2
    assert json.loads(proc.stdout)['outcome']=='blocked'
    record=json.loads((tmp_path/'result.json').read_text())
    assert record['requested_count']==1 and record['selected_count']==0
    assert str(args['repo']) not in proc.stdout+proc.stderr
