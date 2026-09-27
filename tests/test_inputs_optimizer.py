import copy,json,math
import pytest
from jev_integration_evaluator.config import load_config,validate_config
from jev_integration_evaluator.io import InputError,loads,finite,digest,safe_child,write_json,read_json
from jev_integration_evaluator.optimizer import optimize,pareto_front

def candidate(name='JEV-A',**changes):
    e=dict(quality_gain=.3,reliability_gain=.1,failure_reduction=.1,model_call_reduction=1,added_latency_ms=50,added_cost=.001,calls_per_task=1,complexity=.2,maintenance=.02,false_positive_rate=.01,false_negative_rate=.01,risk=.1,throughput=10,provenance='Synthetic explicitly declared estimates; not a measurement')
    e.update(changes)
    return {'candidate_id':name,'tier':2,'semantic_review':{'approved':True},'estimates':e}

@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf'),True,'1'])
def test_finite_rejects_invalid(value):
    with pytest.raises(InputError): finite(value,'v',0)

@pytest.mark.parametrize('text',['{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}'])
def test_strict_json(text):
    with pytest.raises((InputError,ValueError)): loads(text)

@pytest.mark.parametrize('text',['jev_analysis:\n  unknown: true','jev_analysis:\n  mode: analysis\n  mode: implementation','jev_analysis:\n  runtime:\n    max_calls_per_task: 0','jev_analysis:\n  scoring:\n    semantic_uncertainty: -2','jev_analysis:\n  constraints:\n    max_cost_per_task: .nan'])
def test_invalid_configuration(tmp_path,text):
    p=tmp_path/'bad.yaml';p.write_text(text)
    with pytest.raises((InputError,ValueError)): load_config(p)

def test_config_partial_override(tmp_path):
    p=tmp_path/'ok.yaml';p.write_text('jev_analysis:\n  depth: QUICK\n  runtime:\n    mode: shadow\n')
    c=load_config(p);assert c['depth']=='QUICK' and c['runtime']['mode']=='shadow' and c['mode']=='analysis'

@pytest.mark.parametrize('path',['../x','/etc/passwd','a/../../x','x\\y'])
def test_path_traversal_rejected(tmp_path,path):
    with pytest.raises(InputError): safe_child(tmp_path,path)

def test_optimizer_budget_and_conflicts(cfg):
    rows=[candidate('A'),candidate('B'),candidate('C',quality_gain=.01)]
    scan={'candidates':rows,'interactions':[{'a':'A','b':'B','conflict':True,'utility_delta':100,'status':'hypothesis'}]}
    cfg['constraints']['max_calls_per_task']=1
    o=optimize(scan,cfg['constraints'])
    assert len(o['recommended_balanced_set']['candidate_ids'])==1
    assert o['optimality_proven_for_declared_model']
    assert o['recommended_balanced_set']['measured_interaction_utility']==0

def test_unknown_estimates_not_zero(cfg):
    c=candidate();c['estimates']['added_cost']=None
    o=optimize({'candidates':[c],'interactions':[]},cfg['constraints'])
    assert o['status']=='no_justified_integration_set' and o['excluded']

def test_empty_set_beats_negative_utility(cfg):
    o=optimize({'candidates':[candidate(quality_gain=-.9,reliability_gain=-.4)],'interactions':[]},cfg['constraints'])
    assert o['recommended_balanced_set']['candidate_ids']==[]

def test_measured_synergy_only(cfg):
    scan={'candidates':[candidate('A'),candidate('B')],'interactions':[{'a':'A','b':'B','conflict':False,'status':'hypothesis','utility_delta':2}]}
    o=optimize(scan,cfg['constraints']);assert o['recommended_balanced_set']['measured_interaction_utility']==0
    scan['interactions'][0]['status']='measured';o=optimize(scan,cfg['constraints'])
    assert o['recommended_balanced_set']['measured_interaction_utility']==2

def test_beam_labeled_approximate(cfg):
    o=optimize({'candidates':[candidate('A'),candidate('B')],'interactions':[]},cfg['constraints'],exact_limit=0,beam_width=4)
    assert not o['optimality_proven_for_declared_model']

def test_pareto_point_dominance():
    rows=[{'id':'a','quality':.9,'cost':1},{'id':'b','quality':.8,'cost':2},{'id':'c','quality':.7,'cost':.5}]
    assert {x['id'] for x in pareto_front(rows,{'quality':'max','cost':'min'})}=={'a','c'}

@pytest.mark.parametrize('field',['risk','added_cost','throughput','false_negative_rate'])
def test_optimizer_rejects_bad_estimates(cfg,field):
    c=candidate(**{field:-1})
    with pytest.raises(InputError): optimize({'candidates':[c],'interactions':[]},cfg['constraints'])
