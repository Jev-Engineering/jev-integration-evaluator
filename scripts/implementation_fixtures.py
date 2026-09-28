"""Synthetic, independently specified hosts and outcomes for all thirteen recipes.

These are test fixtures, not application-benefit measurements or production
integrations. The scanner's heuristic label is retained; a separate source-matched
binding review explicitly chooses the implementation pattern at this seam.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.integrations.recipes import RECIPES, anchor_hash


def fixture(root: Path, pattern='C', *, tag=None, crlf=False, layout='flat', native_probe=False):
    root.mkdir(parents=True, exist_ok=True)
    tag = tag or ('scenario_' + pattern.lower())
    recipe = RECIPES['python.'+pattern]
    names = {role:'bound_'+role+'_'+tag for role in recipe.bindings}
    first, second = 'perform_primary_'+tag, 'perform_alternative_'+tag
    legacy, seam, entry = 'legacy_dispatch_'+tag, 'select_boundary_'+tag, 'public_entry_'+tag
    state = dict(effects=[],kept=[],blocked=0,step=0,retries=0,completed=False,idempotent=True,
                 approval=True,remaining=10,scope=True,ineffective=False,records=0,checks=True,
                 revision=0,compactions=0,owner_allowed=True,child_valid=True,hard_block=False,valid=True)
    records = [dict(id='hit',text='relevant claim',provenance='source:one'),
               dict(id='counter',text='contradictory evidence',provenance='source:two',contradictory=True),
               dict(id='maybe',text='uncertain evidence',provenance='source:three',uncertain=True),
               dict(id='noise',text='unrelated background',provenance='source:four')]
    if pattern=='H': records=[dict(id='pinned',text='never discard this constraint',pinned=True),
                              dict(id='work',text='current work'),dict(id='old',text='obsolete')]
    source = ['# -*- coding: utf-8 -*-', '"""Synthetic café host; no live model, service or database."""',
              'from __future__ import annotations', 'from threading import RLock',
              ('class HostGate:\n    def __init__(self, actions, **kwargs):\n        self.actions = actions'
               if native_probe else 'from jev_integration_evaluator.runtime import HostGate'), 'LOCK = RLock()',
              'STATE = '+repr(state), 'RECORDS = '+repr(records)]
    def define(name,args,body):
        source.append('\ndef '+name+'('+args+'):\n'+''.join('    '+line+'\n' for line in body.splitlines()))
    if pattern=='E':
        define(first,'request',"STATE['effects'].append('first')\nif not STATE['ineffective']: STATE['records'] += 1\nreturn {'reported': 'ok'}")
    elif pattern=='J':
        define(first,'request',"STATE['effects'].append('first')\nreturn {'task_id': request['task_id'], 'owner': 'base'}")
    else:define(first,'request',"STATE['effects'].append('first')\nreturn 'first'")
    if pattern=='J':define(second,'request',"STATE['effects'].append('second')\nreturn {'task_id': request['task_id'], 'owner': 'alt'}")
    elif pattern=='L':define(second,'request',"STATE['effects'].append('second')\nSTATE['revision'] += 1\nreturn 'merged'")
    else:define(second,'request',"STATE['effects'].append('second')\nreturn 'second'")
    options = "{'base': "+first+", 'alt': "+second+"}"
    baseline='base';labels={'primary':'base','alternative':'alt','uncertain':None};policy={'fallback':'baseline'}
    if pattern=='A':policy={'fallback':'block'}
    if pattern=='B':policy={'fallback':'block'}
    if pattern=='D':
        options=repr({'all':[x['id'] for x in records],'focused':['hit']});baseline='all'
        labels={'supports':'focused','contradicts':'all','uncertain':None}
        policy={'fallback':'baseline','max_items':16,'preserve_contradictions':True,'preserve_uncertain':True}
    if pattern=='E':
        options=repr({'base':'base','success':'accept','inspect':'inspect'})
        labels={'succeeded':'success','failed':'inspect','uncertain':None}
        policy={'fallback':'block','success_action':'success','failure_action':'inspect',
                'postconditions':[{'path':'after.records','operation':'increased_by','value':1}]}
    if pattern=='F':
        options=repr({'continue':'continue','stop':'stop','inspect':'inspect'});baseline='continue'
        labels={'progress':'continue','done':'stop','uncertain':None};policy={'fallback':'baseline','max_steps':3}
    if pattern=='G':
        options=repr({'full':['first','second'],'short':['first']});baseline='full'
        labels={'resolved':'short','unresolved':'full','uncertain':None};policy={'fallback':'baseline','max_steps':2}
    if pattern=='H':
        options=repr({'all':[x['id'] for x in records],'focused':['work']});baseline='all'
        labels={'keep_current':'focused','keep_all':'all','uncertain':None}
        policy={'fallback':'baseline','max_items':16,'choice_field':'command'}
    if pattern=='I':policy={'fallback':'block','max_retries':3}
    if pattern=='J':policy={'fallback':'block','max_concurrent':2}
    if pattern=='K':
        options=repr({'base':'inspect','accept':'accept','changes':'request_changes'})
        labels={'satisfied':'accept','not_satisfied':'changes','uncertain':None}
        policy={'fallback':'baseline','failed_checks_action':'changes'}
    if pattern=='L':
        options="{'base': "+first+", 'merge': "+second+", 'related': "+first+"}"
        labels={'same':'merge','related':'related','different':'base','uncertain':None}
        policy={'fallback':'block','mutating_actions':['merge'],'nonmutating_actions':['base','related']}
    if pattern=='M':
        options=repr({'base':'inspect','accept':'accept','revise':'revise'})
        labels={'supported':'accept','contradicted':'revise','uncertain':None}
        policy={'fallback':'baseline','failed_claims_action':'base'}
    source.append('OPTIONS = '+options)
    arguments={role:', '.join(['request','action','result'][:arity]) for role,arity in recipe.bindings.items()}
    bodies={
        'runtime':"raise RuntimeError('Synthetic fixture runtime is supplied by the authorized probe')",
        'evidence':"return {'goal': 'resolve an ambiguous request', 'evidence': request.get('evidence', ['supplied evidence'])}",
        'baseline_action':'return '+repr(baseline),
        'registry':'return dict(OPTIONS)',
        'gate':"return HostGate(tuple(OPTIONS) + ('first','second'), hard_block=STATE['hard_block'], approval_required=action in ('alt','merge'), approval_granted=STATE['approval'])",
        'validate':"return request.get('valid', True) is True and STATE['valid'] is True",
        'blocked':"STATE['blocked'] += 1\nreturn 'blocked'",
        'guard':'return LOCK',
        'risk':"return {'scope_authorized': STATE['scope'], 'budget_remaining': STATE['remaining'], 'estimated_cost': 1, 'irreversible': True, 'approval_granted': STATE['approval']}",
        'items':'return RECORDS',
        'generate':"STATE['kept'] = [item['id'] for item in action]\nSTATE['effects'].append('generate')\nreturn STATE['kept'][:]",
        'observe':"return {'records': STATE['records']}",
        'postcondition':"return True  # Deliberately ineffective verifier; independent state must still change.",
        'attempt':"return STATE['retries']" if pattern=='I' else "return STATE['step']",
        'step_registry':"return {'first': "+first+", 'second': "+second+"}",
        'retain':"STATE['kept'] = [item['id'] for item in action]\nSTATE['effects'].append('retain')\nreturn STATE['kept'][:]",
        'reserve_retry':"STATE['retries'] += 1\nreturn True",
        'effect_state':"return {'state': 'completed' if STATE['completed'] else 'not_started', 'idempotent': STATE['idempotent']}",
        'completed':"return 'already_completed'",
        'ownership':"return STATE['owner_allowed']",
        'verify_child':"return STATE['child_valid']",
        'checks':"return STATE['checks']",
        'revision':"return STATE['revision']",
        'verify_claims':"return STATE['checks']",
        'finish':"return {'outcome': action, 'disposition': result}" if pattern=='E' else "return {'child': action, 'disposition': result}" if pattern=='J' else 'return action',
    }
    if pattern=='M':bodies['evidence']="return {'claims': ['specific claim'], 'evidence': request.get('evidence', ['supplied source'])}"
    for role in recipe.bindings:define(names[role],arguments[role],bodies[role])
    body='return '+first+'(request)'
    if pattern=='D':body='return '+names['generate']+'(request, RECORDS)'
    if pattern=='H':body='return '+names['retain']+'(request, RECORDS)'
    if pattern=='E':body='return '+first+'(request)'
    if pattern=='F':body="return 'continue'"
    if pattern=='G':body='return '+names['finish']+'(request, ['+first+'(request), '+second+'(request)])'
    if pattern=='I':body="if STATE['completed']: return "+names['completed']+"(request)\n"+names['reserve_retry']+"(request, 'base')\nreturn "+first+'(request)'
    if pattern=='J':body="return "+names['finish']+"(request, "+first+"(request), 'accept')"
    if pattern=='K':body="return 'inspect' if STATE['checks'] else 'request_changes'"
    if pattern=='M':body="return 'inspect'"
    define(legacy,'request',body)
    define(seam,'payload','"""Reviewed finite decision boundary, not generative replacement source."""\n# Retain this unrelated café comment.\nreturn '+legacy+'(payload)')
    if pattern=='F':
        define(entry,'request',"while STATE['step'] < 3:\n    transition = "+seam+"(request)\n    if transition != 'continue': return transition\n    "+first+"(request)\n    STATE['step'] += 1\nreturn 'stop'")
    else:define(entry,'request','return '+seam+'(request)')
    text='\n'.join(source)+'\n'
    if crlf:text=text.replace('\n','\r\n')
    filename='host_'+tag+'.py'
    if layout not in ('flat', 'package', 'src', 'namespace'):
        raise ValueError('Unsupported synthetic fixture layout')
    if layout != 'flat':
        parent = 'src/fixture_pkg' if layout in ('src', 'namespace') else 'fixture_pkg'
        (root/parent).mkdir(parents=True, exist_ok=True)
        if layout != 'namespace': (root/parent/'__init__.py').write_text('"""Synthetic host package."""\n',encoding='utf-8')
        filename=parent+'/'+filename
    (root/filename).write_bytes(text.encode('utf-8'))
    if native_probe:
        if pattern != 'C' or layout != 'flat':
            raise ValueError('Native fixture probe supports only flat pattern C')
        (root/'entry.py').write_text(
            'import json, sys\nimport '+Path(filename).stem+' as host\nimport toy_package\n'
            'mode = sys.argv[1]\n'
            'result = host.'+entry+'({"task_id":"fixture-task","evidence":["supplied"]})\n'
            'assessments = 1 if mode == "shadow" and toy_package.marker() == "approved" else 0\n'
            'print(json.dumps({"reached": True, "result": result, "effects": host.STATE["effects"], '
            '"state": {"blocked": host.STATE["blocked"]}, "assessments": assessments, '
            '"dependency_origin": toy_package.__file__}, sort_keys=True), flush=True)\n',
            encoding='utf-8')
    cfg=load_config();cfg['repository']['typescript_ast']=False
    inventory=scan_repo(root,cfg)
    candidate=next(c for c in inventory['candidates'] if c['source']['symbol']==seam)
    reason='Synthetic source-matched review: the finite '+pattern+' decision consumes supplied ambiguous evidence; deterministic policy remains with the host.'
    apply_reviews(inventory,{candidate['candidate_id']:{'source_sha256':candidate['source']['source_sha256'],'approved':True,'reviewer':'offline-synthetic-fixture-author','reason':reason}},cfg)
    statement=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==seam).body[-1]
    effects=[] if pattern in ('K','M') else [names['generate']] if pattern=='D' else [names['retain']] if pattern=='H' else [first] if pattern in ('E','F') else [first,second]
    def expected(result, performed=(), *, kept=None, step=None, records_count=None, retries=None, blocked=0):
        counts={name:0 for name in effects}
        for name in performed:counts[name]=counts.get(name,0)+1
        vals={'STATE.effects':['generate' if n==names.get('generate') else 'retain' if n==names.get('retain') else 'first' if n==first else 'second' for n in performed], 'STATE.blocked':blocked}
        if kept is not None:vals['STATE.kept']=kept
        if step is not None:vals['STATE.step']=step
        if records_count is not None:vals['STATE.records']=records_count
        if retries is not None:vals['STATE.retries']=retries
        return {'result':result,'exception':None,'calls':counts,'globals':vals}
    base=expected('first',[first]);active=expected('second',[second]);label='alternative';negative=None
    if pattern=='A':active=expected('blocked',[],blocked=1);negative=('primary',{},expected('first',[first]))
    if pattern=='B':negative=('alternative',{'remaining':0},expected('blocked',[],blocked=1))
    if pattern=='D':
        allids=[x['id'] for x in records];keep=['hit','counter','maybe'];label='supports'
        base=expected(allids,[names['generate']],kept=allids);active=expected(keep,[names['generate']],kept=keep)
    if pattern=='E':
        label='succeeded';base=expected({'reported':'ok'},[first],records_count=1)
        active=expected({'outcome':{'reported':'ok'},'disposition':'success'},[first],records_count=1)
        negative=('succeeded',{'ineffective':True},expected({'outcome':{'reported':'ok'},'disposition':'inspect'},[first],records_count=0))
    if pattern=='F':
        label='done';base=expected('stop',[first]*3,step=3);active=expected('stop',[],step=0)
        negative=('progress',{},expected('stop',[first]*3,step=3))
    if pattern=='G':
        label='resolved';base=expected(['first','second'],[first,second]);active=expected(['first'],[first])
    if pattern=='H':
        label='keep_current';allids=[x['id'] for x in records];keep=['pinned','work']
        base=expected(allids,[names['retain']],kept=allids);active=expected(keep,[names['retain']],kept=keep)
    if pattern=='I':
        base=expected('first',[first],retries=1);active=expected('second',[second],retries=1)
        negative=('alternative',{'completed':True},expected('already_completed',[],retries=0))
    if pattern=='J':
        base=expected({'child':{'task_id':'fixture-task','owner':'base'},'disposition':'accept'},[first])
        active=expected({'child':{'task_id':'fixture-task','owner':'alt'},'disposition':'accept'},[second])
    if pattern=='K':
        label='satisfied';base=expected('inspect');active=expected('accept')
        negative=('satisfied',{'checks':False},expected('request_changes'))
    if pattern=='L':
        label='same';base=expected('first',[first]);base['calls']={first:1,second:0}
        active=expected('merged',[second]);negative=('uncertain',{},expected('blocked',[],blocked=1))
    if pattern=='M':
        label='supported';base=expected('inspect');active=expected('accept')
        negative=('supported',{'checks':False},expected('inspect'))
    cases=[]
    def add(case_id,label,initial,baseline,modified):
        request={'task_id':'fixture-task','objective':'Interpret ambiguous supplied evidence','command':'/prune'}
        cases.append({'id':case_id,'request':request,'initial_globals':{'STATE':initial},'baseline':baseline,'active':modified,'assessment_label':label})
    add('intended_change',label,copy.deepcopy(state),base,active)
    if negative:
        label,changes,modified=negative;initial={**copy.deepcopy(state),**changes};baseline=copy.deepcopy(base)
        if pattern=='E':baseline['globals']['STATE.records']=0
        if pattern=='I':baseline=expected('already_completed',[],retries=0)
        if pattern=='K':baseline=expected('request_changes')
        add('policy_or_fallback',label,initial,baseline,modified)
    source=candidate['source']
    spec={'schema_version':'1.0','candidate_id':candidate['candidate_id'],'experiment_id':candidate['recommended_experiment']['id'],
          'inventory_sha256':digest(inventory),'inventory_fingerprint':inventory['scan_fingerprint'],
          'source':{'file':filename,'symbol':seam,'file_sha256':source['file_sha256'],'source_sha256':source['source_sha256'],'anchor_sha256':anchor_hash(statement)},
          'recipe':{'id':'python.'+pattern,'version':'1.0','shape':'module-tail-call-v1'},'bindings':names,
          'binding_review':{'approved':True,'source_sha256':source['source_sha256'],'pattern':pattern,'reviewer':'offline-synthetic-fixture-author','reason':reason},
          'questions':{'decision':{'type':'choice','instructions':'Which declared finite consequence is justified by the supplied evidence?',
                                   'criteria':{k:'Explicit fixture semantic criterion for '+k for k in labels}},
                       'sufficient':{'type':'noul','instructions':'Is the supplied evidence adequate for this bounded classification?'}},
          'primary_question':'decision','evidence_question':'sufficient','label_actions':labels,'policy':policy,
          'runtime':{'configuration':cfg['runtime'],'policy_version':'fixture-v1','canary_scope':'synthetic-'+tag,'task_field':'task_id','max_evidence_bytes':96000,
                     'cost_upper_bound':0.0,'ownership':'stable_host','coordinator':'shared_process_local','task_completion':'host_owned','audit':'required','immutable_cache':False},
          'output':{'module':'_generated_'+tag,'permitted_edits':[filename,(Path(filename).parent/('_generated_'+tag+'.py')).as_posix() if layout!='flat' else '_generated_'+tag+'.py'],'feature_flag_default':False,'dependencies':['jev-integration-evaluator>=1.3.0.dev1']},
          'verification':{'classification':'synthetic','entry_point':entry,'effect_symbols':effects,'cases':cases,'timeout_s':20,'baseline_command':[],'modified_command':[]},
          'authorization_context':{'reference':'explicit offline demonstration request','scopes':['synthetic_workspace_only'],'not_authority':True}}
    if layout!='flat': spec['package_binding']={'version':'1.0','namespace':layout=='namespace',
                                                'module':'fixture_pkg.'+Path(filename).stem}
    return inventory,spec
