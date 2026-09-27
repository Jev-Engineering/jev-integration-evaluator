import copy
import itertools
import random
import pytest
from jev_integration_evaluator.io import digest,InputError
from jev_integration_evaluator.scenarios import robust_optimize,DEFAULT_WEIGHTS
from scripts.v12_fixtures import estimates,scenario_spec


def inventory(n=2):
    return {'scan_fingerprint':digest('synthetic'), 'candidates':[
        {'candidate_id':f'C{i}','tier':1,'source':{'source_sha256':digest(i)},'pattern':'C',
         'semantic_review':{'approved':True,'reviewer':'synthetic-unit-author','reason':'Test fixture',
                            'source_sha256':digest(i)}} for i in range(n)],'interactions':[]}


@pytest.fixture
def problem(cfg):
    inv=inventory();spec=scenario_spec(inv['candidates']);limits=cfg['constraints']
    limits.update(max_calls_per_task=1,max_cost_per_task=1,max_added_latency_ms=1000,max_complexity=5)
    return inv,spec,limits


def test_nominal_winner_not_robust_winner(problem):
    inv,spec,limits=problem;r=robust_optimize(inv,spec,limits)
    assert r['recommended_balanced_set']['candidate_ids']==['C1']
    assert r['scenario_optima_on_common_feasible_set']['nominal']['candidate_ids']==['C0']
    assert r['optimality_proven_for_declared_model'] and not r['deployment_authorized']


def test_no_positive_worst_case_means_no_integration(problem):
    inv,spec,limits=problem
    for s in spec['scenarios']:
        for e in s['estimates'].values():e['quality_gain']=-1
    r=robust_optimize(inv,spec,limits)
    assert r['recommended_balanced_set']['candidate_ids']==[]
    assert r['status']=='no_robustly_useful_integration_set'


@pytest.mark.parametrize('metric,value',[('added_latency_ms',1e6),('added_cost',10),('calls_per_task',2),
 ('risk',1),('throughput',0),('complexity',99)])
def test_every_scenario_must_meet_each_resource_limit(problem,metric,value):
    inv,spec,limits=problem;limits['max_risk']=.5;limits['required_throughput']=1
    spec['scenarios'][1]['estimates']['C1'][metric]=value
    assert robust_optimize(inv,spec,limits)['recommended_balanced_set']['candidate_ids']==[]


@pytest.mark.parametrize('mutation',['tier','review','reason','reviewer','hash','missing_source','deterministic','realtime','none','missing_estimate'])
def test_ineligible_candidates_never_recommended(problem,mutation):
    inv,spec,limits=problem;c=inv['candidates'][1]
    if mutation=='tier':c['tier']=0
    elif mutation=='review':c['semantic_review']['approved']=False
    elif mutation in ('reason','reviewer'):c['semantic_review'][mutation]=''
    elif mutation=='hash':c['semantic_review']['source_sha256']=digest('stale')
    elif mutation=='missing_source':c.pop('source');c['semantic_review'].pop('source_sha256')
    elif mutation=='deterministic':c['deterministic_alternative']='mandatory'
    elif mutation=='realtime':c['hard_real_time']=True
    elif mutation=='none':c['pattern']='NONE'
    elif mutation=='missing_estimate':del spec['scenarios'][1]['estimates']['C1']
    r=robust_optimize(inv,spec,limits)
    assert 'C1' not in r['recommended_balanced_set']['candidate_ids'] and len(r['excluded'])==1


def test_dependencies_conflicts_and_cycle_contract(problem):
    inv,spec,limits=problem;spec['requires']={'C1':['C0']}
    assert robust_optimize(inv,spec,limits)['recommended_balanced_set']['candidate_ids']==[]
    limits['max_calls_per_task']=2
    spec['scenarios'][1]['estimates']['C0']['quality_gain']=.01
    assert robust_optimize(inv,spec,limits)['recommended_balanced_set']['candidate_ids']==['C0','C1']
    inv['interactions']=[{'a':'C0','b':'C1','conflict':True}]
    assert robust_optimize(inv,spec,limits)['recommended_balanced_set']['candidate_ids']!=['C0','C1']
    spec['requires']['C0']=['C1']
    with pytest.raises(InputError,match='Cyclic'):robust_optimize(inv,spec,limits)


def test_ineligible_prerequisite_propagates(problem):
    inv,spec,limits=problem;spec['requires']={'C1':['C0']};inv['candidates'][0]['tier']=0
    r=robust_optimize(inv,spec,limits)
    assert r['eligible_candidates']==0 and r['recommended_balanced_set']['candidate_ids']==[]


def test_unmeasured_synergy_never_creates_credit(problem):
    inv,spec,limits=problem;limits['max_calls_per_task']=2
    for s in spec['scenarios']:
        for e in s['estimates'].values():e['quality_gain']=-.1
        s['interactions']=[{'a':'C0','b':'C1','utility_delta':2,'status':'assumed','provenance':'Synthetic interaction assumption'}]
    r=robust_optimize(inv,spec,limits)
    assert not r['recommended_balanced_set']['candidate_ids'] and r['ignored_unmeasured_positive_interactions']==2
    for s in spec['scenarios']:s['interactions'][0]['status']='measured' # Artificial branch coverage only.
    assert robust_optimize(inv,spec,limits)['recommended_balanced_set']['candidate_ids']==['C0','C1']


@pytest.mark.parametrize('mutation',['null','nan','negative_cost','no_scenarios','unknown_id','unknown_dependency','duplicate_scenario','duplicate_id'])
def test_scenario_integrity(problem,mutation):
    inv,spec,limits=problem
    if mutation=='null':spec['scenarios'][0]['estimates']['C0']['added_cost']=None
    if mutation=='nan':spec['scenarios'][0]['estimates']['C0']['quality_gain']=float('nan')
    if mutation=='negative_cost':spec['scenarios'][0]['estimates']['C0']['added_cost']=-1
    if mutation=='no_scenarios':spec['scenarios']=[]
    if mutation=='unknown_id':spec['scenarios'][0]['estimates']['missing']=estimates()
    if mutation=='unknown_dependency':spec['requires']={'C0':['missing']}
    if mutation=='duplicate_scenario':spec['scenarios'].append(copy.deepcopy(spec['scenarios'][0]))
    if mutation=='duplicate_id':inv['candidates'].append(copy.deepcopy(inv['candidates'][0]))
    with pytest.raises(InputError):robust_optimize(inv,spec,limits)


def test_beam_discloses_no_optimality_proof(problem):
    inv,spec,limits=problem;r=robust_optimize(inv,spec,limits,exact_limit=0,beam_width=1)
    assert not r['optimality_proven_for_declared_model'] and 'beam' in r['method']
    assert r['recommended_balanced_set']['candidate_ids']==['C1']


@pytest.mark.parametrize('seed',range(12))
def test_exact_optimizer_matches_independent_small_oracle(cfg,seed):
    rng=random.Random(seed);inv=inventory(6)
    weights={k:0.0 for k in DEFAULT_WEIGHTS};weights['quality_gain']=1
    scenarios=[]
    for j in range(3):
        scenarios.append({'scenario_id':str(j),'evidence_type':'synthetic','provenance':'Random synthetic property test',
                          'estimates':{c['candidate_id']:estimates(rng.uniform(-.2,.5),cost=0,latency=0) for c in inv['candidates']},'interactions':[]})
    spec={'schema_version':'1.2','scenarios':scenarios,'requires':{},'utility_weights':weights,'minimal_retention':.9}
    limits=cfg['constraints'];limits.update(max_calls_per_task=3,max_complexity=5)
    result=robust_optimize(inv,spec,limits)
    oracle=max(min(sum(s['estimates'][f'C{i}']['quality_gain'] for i in subset) for s in scenarios)
               for n in range(4) for subset in itertools.combinations(range(6),n))
    assert result['recommended_balanced_set']['worst_case_utility']==pytest.approx(oracle)
    old=result['recommended_balanced_set']['worst_case_utility'];limits['max_calls_per_task']=4
    assert robust_optimize(inv,spec,limits)['recommended_balanced_set']['worst_case_utility']>=old-1e-12
