"""Operational-protocol tests use fabricated outcomes only."""
import copy
from datetime import datetime,timedelta,timezone
import pytest
from jev_integration_evaluator.io import InputError,digest
from jev_integration_evaluator.monitoring import freeze_monitor,evaluate_monitor,suspend_from_monitor
from jev_integration_evaluator.runtime import SafeRouter
from jev_integration_evaluator.cohorts import canary_arm
from scripts.v12_fixtures import monitor_fixture
from test_runtime_client import Client,kwargs
from test_runtime_v11 import receipt


@pytest.fixture
def monitoring():return monitor_fixture()


def test_complete_window_keeps_denominator_and_synthetic_block(monitoring):
    p,r,n=monitoring;x=evaluate_monitor(p,r,as_of=n,expected_digest=p['contract_digest'])
    assert x['operational_checks_pass'] and x['received_tasks']==x['scheduled_tasks']==80
    assert not x['eligible_for_continued_canary'] and not x['exposure_expansion_authorized']


def test_observed_branch_requires_independent_pin():
    p,r,n=monitor_fixture(evidence='observed') # Artificial branch coverage, not observed research.
    assert not evaluate_monitor(p,r,as_of=n)['eligible_for_continued_canary']
    x=evaluate_monitor(p,r,as_of=n,expected_digest=p['contract_digest'])
    assert x['eligible_for_continued_canary'] and not x['deployment_authorized']


@pytest.mark.parametrize('arm',['baseline','jev'])
def test_missing_outcomes_never_improve_denominator(monitoring,arm):
    p,r,n=monitoring;r=[x for x in r if x['arm']!=arm]
    x=evaluate_monitor(p,r,as_of=n)
    assert x['status']=='awaiting_outcomes' and x['missing_tasks']>0
    assert all(c['metrics']['failure_rate_increase'] is None for c in x['checks'])
    late=(datetime.fromisoformat(n)+timedelta(seconds=40)).isoformat()
    assert evaluate_monitor(p,r,as_of=late)['status']=='incomplete_overdue_window'


@pytest.mark.parametrize('metric',['success','latency_ms','cost','unsafe_actions','fallbacks','decisions','action_counts'])
def test_unknown_measurements_cannot_pass(monitoring,metric):
    p,r,n=monitoring;r[0][metric]=None;x=evaluate_monitor(p,r,as_of=n)
    assert x['incomplete_tasks']==1 and not x['operational_checks_pass']


def test_known_incident_survives_missing_cost(monitoring):
    p,r,n=monitoring;row=next(x for x in r if x['arm']=='jev');row.update(cost=None,unsafe_actions=1)
    x=evaluate_monitor(p,r,as_of=n)
    assert x['status']=='guardrail_breach' and x['recommendation']=='suspend'
    assert x['checks'][0]['metrics']['unsafe_actions']==1 and x['checks'][0]['unsafe_count_status']=='known_lower_bound'


@pytest.mark.parametrize('guardrail',['failure_rate','timeout_rate','failure_rate_increase','p95_added_latency_ms','mean_added_cost','fallback_rate','action_distribution_tv'])
def test_fixed_guardrails_breach(monitoring,guardrail):
    p,r,n=monitoring
    for row in r:
        if row['arm']!='jev':continue
        if guardrail=='failure_rate':row.update(success=False,run_status='failed')
        if guardrail=='timeout_rate':row.update(success=False,run_status='timeout')
        if guardrail=='failure_rate_increase':row.update(success=False,run_status='failed')
        if guardrail=='p95_added_latency_ms':row['latency_ms']=1000
        if guardrail=='mean_added_cost':row['cost']=1
        if guardrail=='fallback_rate':row['fallbacks']=1
        if guardrail=='action_distribution_tv':row['action_counts']={'previously-unseen-action':1}
    x=evaluate_monitor(p,r,as_of=n)
    assert x['status']=='guardrail_breach' and guardrail in x['checks'][0]['breaches']


def test_zero_action_evidence_does_not_pass(monitoring):
    p,r,n=monitoring
    for row in r:row.update(decisions=0,fallbacks=0,action_counts={})
    assert evaluate_monitor(p,r,as_of=n)['status']=='insufficient_action_evidence'


@pytest.mark.parametrize('mutation',['duplicate','unscheduled','arm','task_hash','cluster_id','cohort','window_id','study_digest',
 'monitor_digest','evidence_type','future','before_window','negative_duration','false_success','partial_actions','too_many_fallbacks'])
def test_rejects_inconsistent_outcomes(monitoring,mutation):
    p,r,n=monitoring
    if mutation=='duplicate':r.append(copy.deepcopy(r[0]))
    elif mutation=='unscheduled':r[0]['task_id']='not-scheduled'
    elif mutation=='arm':r[0]['arm']='jev' if r[0]['arm']=='baseline' else 'baseline'
    elif mutation in ('task_hash','study_digest','monitor_digest'):r[0][mutation]=digest('different')
    elif mutation in ('cluster_id','cohort','window_id'):r[0][mutation]='different'
    elif mutation=='evidence_type':r[0][mutation]='observed'
    elif mutation=='future':r[0]['finished_at']='2100-01-01T00:00:00+00:00'
    elif mutation=='before_window':r[0]['started_at']='2000-01-01T00:00:00+00:00'
    elif mutation=='negative_duration':r[0]['finished_at']=p['specification']['starts_at']
    elif mutation=='false_success':r[0]['run_status']='timeout'
    elif mutation=='partial_actions':r[0]['action_counts']={}
    elif mutation=='too_many_fallbacks':r[0]['fallbacks']=2
    with pytest.raises(InputError):evaluate_monitor(p,r,as_of=n)


@pytest.mark.parametrize('mutation',['task_id','task_hash','cluster_id','unknown_cohort','reference_sum','small_arm','naive_time','reversed_time'])
def test_freeze_schedule_and_reference_contract(monitoring,mutation):
    p,r,n=monitoring;s=copy.deepcopy(p['specification'])
    if mutation in ('task_id','task_hash','cluster_id'):s['tasks'][1][mutation]=s['tasks'][0][mutation]
    if mutation=='unknown_cohort':s['required_cohorts']=['missing']
    if mutation=='reference_sum':s['action_reference']['inspect']=.5
    if mutation=='small_arm':s['minimum_tasks_per_arm']=80
    if mutation=='naive_time':s['starts_at']='2026-09-26T01:00:00'
    if mutation=='reversed_time':s['ends_at']=s['starts_at']
    with pytest.raises(InputError):freeze_monitor(s)


def test_stale_and_open_windows_cannot_continue(monitoring):
    p,r,n=monitoring
    later=(datetime.fromisoformat(n)+timedelta(hours=1)).isoformat()
    assert evaluate_monitor(p,r,as_of=later)['status']=='stale_window'
    earlier=(datetime.fromisoformat(n)-timedelta(minutes=1)).isoformat()
    assert evaluate_monitor(p,r,as_of=earlier)['status']=='window_open'
    with pytest.raises(InputError):evaluate_monitor(p,r,as_of=n,expected_digest=digest('wrong'))


def test_assignments_match_runtime_algorithm_and_are_task_stable(monitoring):
    p,r,n=monitoring;s=p['specification']
    for a in p['assignments']:
        assert a['arm']==canary_arm(a['task_id'],s['assignment_salt'],s['canary_fraction'])
    assert canary_arm('task','s',0)=='baseline' and canary_arm('task','s',1)=='jev'


def test_explicit_host_hook_suspends_and_never_resumes(cfg,example_event,response):
    now=datetime.now(timezone.utc)
    p,rows,n=monitor_fixture(evidence='observed',now=now) # Explicitly fabricated unit-test data.
    c=cfg['runtime'];c.update(mode='canary',canary_fraction=.5)
    with SafeRouter(Client(response),c,activation=receipt(c,example_event),require_expiring_activation=True,
                    require_runtime_binding=True,canary_scope='synthetic-canary-scope') as router:
        h=router.runtime_contract_hash(example_event['questions'],'action','sufficient')
        router.activation.update(runtime_contract_hash=h,deployment_id='synthetic-deployment',study_digest=p['specification']['study_digest'])
        spec=copy.deepcopy(p['specification']);spec['runtime_contracts']={'gate-0':h};p=freeze_monitor(spec)
        for row in rows:row['monitor_digest']=p['contract_digest']
        routers={'gate-0':router}
        clean=suspend_from_monitor(p,rows,routers,expected_digest=p['contract_digest'],approved_deployment_id='synthetic-deployment')
        assert not clean['host_suspended_gate_ids'] and not router.suspended
        next(r for r in rows if r['arm']=='jev')['unsafe_actions']=1
        bad=suspend_from_monitor(p,rows,routers,expected_digest=p['contract_digest'],approved_deployment_id='synthetic-deployment')
        assert bad['host_suspended_gate_ids']==['gate-0'] and router.suspended
        for row in rows:row['unsafe_actions']=0
        suspend_from_monitor(p,rows,routers,expected_digest=p['contract_digest'],approved_deployment_id='synthetic-deployment')
        assert router.suspended
        with pytest.raises(InputError):suspend_from_monitor(p,rows,routers,expected_digest=p['contract_digest'],approved_deployment_id='different')
        with pytest.raises(InputError):suspend_from_monitor(p,rows,{},expected_digest=p['contract_digest'],approved_deployment_id='synthetic-deployment')
        router.canary_scope='wrong-scope'
        with pytest.raises(InputError):suspend_from_monitor(p,rows,routers,expected_digest=p['contract_digest'],approved_deployment_id='synthetic-deployment')


def test_synthetic_evidence_cannot_invoke_host_controls(monitoring):
    p,r,n=monitoring
    with pytest.raises(InputError):suspend_from_monitor(p,r,{},expected_digest=p['contract_digest'],approved_deployment_id='synthetic-deployment')
