"""Runtime policy failures exercised through actual edited host entry points."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import threading
import pytest
from integration_helpers import bound_host
from jev_integration_evaluator.budget import BudgetCoordinator
from jev_integration_evaluator.integrations.probe import _fixture_receipt
from jev_integration_evaluator.integrations.host import PartialPlanError


@pytest.mark.parametrize('fault',['unknown','distribution','low_confidence','low_evidence','missing_evidence','provider','timeout'])
def test_bad_assessments_keep_baseline_and_execute_once(tmp_path,fault):
    with bound_host(tmp_path,config={'timeout_ms':30}) as (m,a,r,s,c,call):
        c.fault=fault
        assert call()=='first'
        assert m.STATE['effects']==['first'] and c.calls==1
        assert r.budget_coordinator.snapshot()['calls']==1


@pytest.mark.parametrize('fault',['missing','expired','revoked','bad_mapping','wrong_scope','closed_task','missing_state'])
def test_missing_or_invalid_receipt_never_executes_treatment(tmp_path,fault):
    with bound_host(tmp_path) as (m,a,r,s,c,call):
        if fault=='missing':r.activation={}
        elif fault=='expired':r.activation['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        elif fault=='revoked':r.suspended=True
        elif fault=='bad_mapping':a.SPEC['label_actions']['alternative']='base'
        elif fault=='wrong_scope':r.canary_scope+='-unapproved'
        elif fault=='closed_task':r.budget_coordinator.close_task(s['verification']['cases'][0]['request']['task_id'])
        elif fault=='missing_state':m.__dict__[s['bindings']['evidence']]=lambda request:{}
        result=call()
        assert result in ('first','blocked')
        assert m.STATE['effects'] in (['first'],[])
        assert c.calls==0


@pytest.mark.parametrize('late',['approval','validation','membership','executor','revoked','task_closed','hard_block'])
def test_late_changes_block_before_executor(tmp_path,late):
    with bound_host(tmp_path) as (m,a,r,s,c,call):
        def mutate():
            if late=='approval':m.STATE['approval']=False
            elif late=='validation':m.STATE['valid']=False
            elif late=='membership':m.OPTIONS.pop('alt')
            elif late=='executor':m.OPTIONS['alt']=m.OPTIONS['base']
            elif late=='revoked':r.suspended=True
            elif late=='task_closed':r.budget_coordinator.close_task(s['verification']['cases'][0]['request']['task_id'])
            else:m.STATE['hard_block']=True
        c.effect=mutate
        # Revoking the assessor does not revoke an independently permitted host baseline.
        # Host permission/state failures block; runtime-only revocation falls back exactly once.
        expected = 'first' if late in ('revoked','task_closed') else 'blocked'
        assert call()==expected
        assert m.STATE['effects']==(['first'] if expected=='first' else []) and c.calls==1


def test_late_audit_failure_blocks_without_side_effect(tmp_path):
    with bound_host(tmp_path) as (m,a,r,s,c,call):
        old=r.log.append
        def fail_intent(event):
            if event.get('type')=='host_execution_intent':raise OSError('synthetic full disk')
            old(event)
        r.log.append=fail_intent
        assert call()=='blocked' and m.STATE['effects']==[]


@pytest.mark.parametrize('mode',['off','shadow','active'])
def test_host_exceptions_are_not_replayed_or_replaced(tmp_path,mode):
    with bound_host(tmp_path) as (m,a,r,s,c,call):
        first_name=m.OPTIONS['base'].__name__;second_name=m.OPTIONS['alt'].__name__
        def boom(request):m.STATE['effects'].append('effect');raise LookupError('original host exception')
        m.__dict__[first_name]=boom;m.__dict__[second_name]=boom;m.OPTIONS.update(base=boom,alt=boom)
        r.config['mode']=mode;r.activation=_fixture_receipt(r,s)
        a.ENABLED=mode!='off'
        with pytest.raises(LookupError,match='original host exception'):call()
        assert m.STATE['effects']==['effect']
        if mode=='off':assert c.calls==0


@pytest.mark.parametrize('pattern,field',[('B','approval'),('B','scope'),('B','remaining'),('L','approval'),('L','revision'),('J','owner_allowed')])
def test_pattern_specific_late_host_policy(tmp_path,pattern,field):
    with bound_host(tmp_path,pattern) as (m,a,r,s,c,call):
        c.effect=lambda:m.STATE.update({field:1 if field=='revision' else 0 if field=='remaining' else False})
        assert call()=='blocked' and m.STATE['effects']==[]


def test_prune_is_not_compaction_and_pins_are_preserved(tmp_path):
    with bound_host(tmp_path,'H') as (m,a,r,s,c,call):
        request=copy.deepcopy(s['verification']['cases'][0]['request']);request['command']='/compact'
        assert call(request)=='blocked' and not m.STATE['effects'] and c.calls==0
        assert call()==['pinned','work'] and m.STATE['compactions']==0


def test_late_retrieval_changes_do_not_generate(tmp_path):
    with bound_host(tmp_path,'D') as (m,a,r,s,c,call):
        c.effect=lambda:m.RECORDS[0].update(text='changed concurrently')
        assert call()=='blocked' and not m.STATE['effects']


def test_true_verifier_cannot_cover_ineffective_side_effect(tmp_path):
    with bound_host(tmp_path,'E') as (m,a,r,s,c,call):
        m.STATE['ineffective']=True
        assert call()=={'outcome':{'reported':'ok'},'disposition':'inspect'}
        assert m.STATE['effects']==['first'] and m.STATE['records']==0


def test_retry_completed_side_effect_never_repeats(tmp_path):
    with bound_host(tmp_path,'I') as (m,a,r,s,c,call):
        m.STATE['completed']=True
        assert call()=='already_completed' and not m.STATE['effects'] and c.calls==0


@pytest.mark.parametrize('bad',['unknown_nonidempotent','retry_limit','bad_reservation','completed_during_assessment'])
def test_recovery_bounds_and_nonidempotence(tmp_path,bad):
    with bound_host(tmp_path,'I') as (m,a,r,s,c,call):
        if bad=='unknown_nonidempotent':m.__dict__[s['bindings']['effect_state']]=lambda request:{'state':'unknown','idempotent':False}
        if bad=='retry_limit':m.STATE['retries']=3
        if bad=='bad_reservation':m.__dict__[s['bindings']['reserve_retry']]=lambda request,action:True
        if bad=='completed_during_assessment':c.effect=lambda:m.STATE.update(completed=True)
        assert call()=='blocked' and not m.STATE['effects']


def test_post_execution_child_verifier_failure_preserves_real_child(tmp_path):
    with bound_host(tmp_path,'J') as (m,a,r,s,c,call):
        def fail(*args):raise OSError('synthetic verifier failure')
        m.__dict__[s['bindings']['verify_child']]=fail
        result=call()
        assert result['disposition']=='inspect' and result['child']['owner']=='alt'
        assert m.STATE['effects']==['second']


def test_partial_plan_preserves_completed_results_and_does_not_replay(tmp_path):
    with bound_host(tmp_path,'G') as (m,a,r,s,c,call):
        c.label='unresolved'
        first_name='perform_primary_'+s['source']['file'].removeprefix('host_').removesuffix('.py')
        old=m.__dict__[first_name]
        def first(request):
            result=old(request);m.STATE['valid']=False;return result
        m.__dict__[first_name]=first
        with pytest.raises(PartialPlanError) as caught:call()
        assert caught.value.completed_results==('first',) and caught.value.failed_step=='second'
        assert m.STATE['effects']==['first']


def test_multiple_generated_routers_share_atomic_budget_across_threads(tmp_path):
    ledger=BudgetCoordinator(max_calls_per_task=1,max_cost_per_task=10,max_total_calls=1,max_total_cost=20,max_in_flight=8,max_tasks=64)
    with bound_host(tmp_path/'a',ledger=ledger,scope='shared-thread-fixture') as h1, bound_host(tmp_path/'b',ledger=ledger,scope='shared-thread-fixture') as h2:
        request={'task_id':'shared-task','evidence':['finite evidence']}
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda i:(h1 if i%2 else h2)[5](request),range(16)))
        assert results.count('second')==1
        assert results.count('first')==15
        assert h1[4].calls+h2[4].calls==1 and ledger.snapshot()['calls']==1
        assert len(h1[0].STATE['effects'])+len(h2[0].STATE['effects'])==16


def test_one_workflow_cannot_replace_its_shared_coordinator(tmp_path):
    with bound_host(tmp_path/'a',scope='one-owner-fixture') as h1,bound_host(tmp_path/'b',scope='one-owner-fixture') as h2:
        assert h1[5]()=='second'
        assert h2[5]()=='blocked' and not h2[0].STATE['effects'] and h2[4].calls==0
