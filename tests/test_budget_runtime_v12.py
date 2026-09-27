"""Responses/receipts here are artificial unit fixtures, never deployment evidence."""
import copy
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from jev_integration_evaluator.budget import BudgetCoordinator, BudgetDenied, Reservation
from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.runtime import SafeRouter
from test_runtime_client import Client, activation, kwargs
from test_runtime_v11 import receipt


def ledger(**overrides):
    c=dict(max_calls_per_task=10,max_cost_per_task=1,max_total_calls=20,max_total_cost=2,max_in_flight=8,max_tasks=30)
    c.update(overrides);return BudgetCoordinator(**c)


@pytest.mark.parametrize('key,value',[('max_calls_per_task',True),('max_total_calls',0),('max_tasks',-1),('max_in_flight',1.5),
 ('max_cost_per_task',float('nan')),('max_total_cost',float('inf')),('max_total_cost',-1),('max_cost_per_task',True)])
def test_ledger_rejects_invalid_limits(key,value):
    with pytest.raises(InputError):ledger(**{key:value})


def test_shared_atomic_admission_and_no_refund():
    b=ledger(max_total_calls=17,max_calls_per_task=30,max_in_flight=100)
    def work(i):
        try:
            r=b.reserve('task',.01);b.settle(r,actual_cost=0);return 1
        except BudgetDenied:return 0
    with ThreadPoolExecutor(max_workers=20) as pool:allowed=sum(pool.map(work,range(100)))
    assert allowed==17 and b.snapshot()['calls']==17
    assert b.snapshot()['reserved_cost']==pytest.approx(.17)
    assert b.snapshot()['in_flight']==0 and b.snapshot()['refunds']==0


@pytest.mark.parametrize('settings,reason',[
 ({'max_calls_per_task':1},'shared_task_call_budget'),({'max_total_calls':1},'shared_total_call_budget'),
 ({'max_cost_per_task':.15},'shared_task_cost_budget'),({'max_total_cost':.15},'shared_total_cost_budget')])
def test_limits_are_shared_and_fail_closed(settings,reason):
    b=ledger(**settings);r=b.reserve('task',.1);b.settle(r)
    with pytest.raises(BudgetDenied,match=reason):b.reserve('task',.1)


def test_inflight_capacity_closure_tombstone_and_capacity_bound():
    b=ledger(max_in_flight=1,max_tasks=1);r=b.reserve('secret-task-name',.1)
    with pytest.raises(BudgetDenied,match='concurrency'):b.reserve('secret-task-name',0)
    b.close_task('secret-task-name');assert not b.permits_result('secret-task-name')
    b.settle(r)
    with pytest.raises(BudgetDenied,match='closed'):b.reserve('secret-task-name',0)
    with pytest.raises(BudgetDenied,match='registry_full'):b.reserve('new',0)
    assert 'secret-task-name' not in str(b.snapshot())


def test_settlement_exactly_once_and_overrun_suspends():
    b=ledger();r=b.reserve('t',.1);b.settle(r,actual_cost=.3)
    assert b.snapshot()['reserved_cost']==pytest.approx(.3)
    assert b.snapshot()['suspended'] and b.snapshot()['cost_bound_overruns']==1
    with pytest.raises(InputError):b.settle(r)
    with pytest.raises(InputError):b.settle(Reservation('unknown'))
    with pytest.raises(BudgetDenied,match='suspended'):b.reserve('new',0)


@pytest.mark.parametrize('task,cost',[('',0),(True,0),('x',True),('x',-1),('x',float('nan'))])
def test_reservation_input_contract(task,cost):
    with pytest.raises(InputError):ledger().reserve(task,cost)


def test_two_routers_share_task_caps_cache_does_not_charge(cfg,example_event,response):
    c=cfg['runtime'];c.update(mode='active',cache_ttl_s=60)
    b=ledger(max_calls_per_task=1);client=Client(response)
    args=kwargs(example_event,immutable_state=True,cache_scope='immutable-unit')
    with SafeRouter(client,c,activation=activation(c,example_event),budget_coordinator=b) as r1, \
         SafeRouter(client,c,activation=activation(c,example_event),budget_coordinator=b) as r2:
        assert r1.route(**args).source=='jev_assessment'
        assert r1.route(**args).source=='jev_assessment'
        assert r2.route(**args).reason=='shared_task_call_budget'
        r1.release_task('task')  # Local legacy reset cannot reset the shared ledger.
        assert r1.route(**kwargs(example_event)).reason=='shared_task_call_budget'
        b.close_task('task')
        assert r1.route(**args).source=='baseline'
    assert client.calls==1 and b.snapshot()['calls']==1


def test_errors_release_concurrency_but_keep_spend(cfg,example_event,response):
    c=cfg['runtime'];c['mode']='active';b=ledger(max_in_flight=1,max_calls_per_task=1)
    with SafeRouter(Client(response,fail=True),c,activation=activation(c,example_event),budget_coordinator=b) as r:
        assert r.route(**kwargs(example_event,estimated_cost_upper_bound=.001)).source=='baseline'
        assert b.snapshot()['in_flight']==0 and b.snapshot()['reserved_cost']==.001
        assert r.route(**kwargs(example_event)).reason=='shared_task_call_budget'


def test_client_cannot_mutate_validated_question_snapshot(cfg,example_event,response):
    class Mutator(Client):
        def evaluate(self,state,questions,*args):
            questions['action']['criteria'].clear();state.clear();return copy.deepcopy(self.response)
    c=cfg['runtime'];c['mode']='active';old=copy.deepcopy(example_event)
    with SafeRouter(Mutator(response),c,activation=activation(c,example_event)) as r:
        assert r.route(**kwargs(example_event)).source=='jev_assessment'
    assert example_event==old


def test_failed_audit_never_populates_cache(cfg,example_event,response):
    class BadLog:
        def append(self,event):raise OSError('synthetic storage error')
    c=cfg['runtime'];c.update(mode='active',cache_ttl_s=60);client=Client(response)
    with SafeRouter(client,c,activation=activation(c,example_event),audit_log=BadLog()) as r:
        args=kwargs(example_event,immutable_state=True,cache_scope='fixture')
        assert r.route(**args).source=='baseline' and not r.cache
        r.log=None
        assert r.route(**args).source=='jev_assessment'
    assert client.calls==2


@pytest.mark.parametrize('change',['price','timeout','canary_fraction','scope','primary','evidence','shared_budget'])
def test_runtime_receipt_binds_operational_configuration(cfg,example_event,response,change):
    c=cfg['runtime'];c['mode']='active';b=ledger();a=receipt(c,example_event);client=Client(response)
    with SafeRouter(client,c,activation=a,budget_coordinator=b,require_expiring_activation=True,require_runtime_binding=True) as r:
        r.activation['runtime_contract_hash']=r.runtime_contract_hash(example_event['questions'],'action','sufficient')
        assert r.route(**kwargs(example_event)).source=='jev_assessment'
        if change=='price':r.config['input_usd_per_million']=3
        if change=='timeout':r.config['timeout_ms']+=1
        if change=='canary_fraction':r.config['canary_fraction']=.5
        if change=='scope':r.canary_scope='different'
        if change=='shared_budget':r.budget_coordinator=ledger(max_total_calls=21)
        args=kwargs(example_event)
        if change=='primary':
            # The same labels cannot carry another question's approval.
            assert r.runtime_contract_hash(example_event['questions'],'different','sufficient')!=r.activation['runtime_contract_hash']
            r.activation['runtime_contract_hash']=r.runtime_contract_hash(example_event['questions'],'different','sufficient')
        if change=='evidence':args['evidence_question']=None
        assert r.route(**args).source=='baseline'
    assert client.calls==1


def test_legacy_receipt_rejected_by_new_strict_mode(cfg,example_event,response):
    c=cfg['runtime'];c['mode']='active';client=Client(response)
    with SafeRouter(client,c,activation=receipt(c,example_event),require_expiring_activation=True,require_runtime_binding=True) as r:
        assert r.route(**kwargs(example_event)).source=='baseline'
    assert client.calls==0


@pytest.mark.parametrize('shared',[False,True])
def test_inflight_admission_and_closure(cfg,example_event,response,shared):
    started=threading.Event();release=threading.Event();output=[]
    class Blocking(Client):
        def evaluate(self,*args):
            self.calls+=1;started.set();assert release.wait(3);return copy.deepcopy(self.response)
    c=cfg['runtime'];c.update(mode='active',timeout_ms=5000)
    b=ledger(max_in_flight=1) if shared else None;client=Blocking(response)
    with SafeRouter(client,c,activation=activation(c,example_event),budget_coordinator=b,max_concurrent_calls=1) as r:
        thread=threading.Thread(target=lambda:output.append(r.route(**kwargs(example_event))))
        thread.start()
        try:
            assert started.wait(3)
            assert r.route(**kwargs(example_event,task_id='another')).reason=='router_concurrency_limit'
            if b:b.close_task('task')
            else:r.suspend()
        finally:release.set();thread.join(5)
        assert not thread.is_alive() and output[0].source=='baseline'
    if b:assert b.snapshot()['in_flight']==0


def test_shared_shadow_budget_is_not_bypassed(cfg,example_event,response):
    c=cfg['runtime'];c['mode']='shadow';b=ledger(max_total_calls=1);client=Client(response)
    for i in range(2):
        with SafeRouter(client,c,budget_coordinator=b) as r:
            assert r.route(**kwargs(example_event,task_id=f't{i}')).source=='baseline'
            # Drain the already submitted trusted fixture rather than cancel it.
            for future in list(r.futures):future.result(timeout=3)
    assert client.calls==1 and b.snapshot()['calls']==1
