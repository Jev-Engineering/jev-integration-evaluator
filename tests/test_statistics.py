import copy,math
import pytest
from jev_integration_evaluator.statistics import paired_records,compare_runs,exact_mcnemar,economics,long_horizon,ablation_analysis,bayesian_paired
from jev_integration_evaluator.calibration import calibration,select_threshold
from jev_integration_evaluator.io import InputError,read_jsonl

def test_synthetic_paired_results_and_p95(runs,cfg):
    b,t=runs;o=compare_runs(b,t,cfg)
    assert o['pair_count']==80
    assert o['cells']=={'both_pass':48,'both_fail':8,'rescues':24,'regressions':0}
    assert o['absolute_improvement']==pytest.approx(.3)
    assert o['rescue_regression_ratio'] is None
    assert o['recommendation']=='needs_more_evidence'
    assert o['metrics']['latency_ms']['paired_added_p95']==80
    assert o['efficiency']['baseline']['successful_tasks_per_model_calls']==pytest.approx(48/400)

def test_seeded_analysis_reproducible(runs,cfg):
    assert compare_runs(*runs,cfg)==compare_runs(*runs,cfg)

@pytest.mark.parametrize('a,b,p',[(10,0,2/1024),(0,0,1),(5,5,1),(1,0,1),(9,1,22/1024)])
def test_exact_mcnemar(a,b,p): assert exact_mcnemar(a,b)['p_value']==pytest.approx(p)

@pytest.mark.parametrize('bad',['missing','duplicate','task_hash','seed','model','mode','scope','missing_outcome','nan','string_identity'])
def test_paired_integrity_rejections(runs,bad):
    b,t=copy.deepcopy(runs)
    if bad=='missing':t.pop()
    if bad=='duplicate':t.append(t[0])
    if bad=='task_hash':t[0]['task_hash']='different'
    if bad=='seed':t[0]['seed']+=1
    if bad=='model':t[0]['model_id']='different'
    if bad=='mode':t[0]['mode']='shadow'
    if bad=='scope':t[0]['evaluation_scope']='decision_accuracy'
    if bad=='missing_outcome':del t[0]['success']
    if bad=='nan':t[0]['cost']=float('nan')
    if bad=='string_identity':t[0]['task_id']=[]
    with pytest.raises(InputError): paired_records(b,t)

def test_clusters_withhold_ordinary_mcnemar(runs,cfg):
    b,t=runs
    for arm in (b,t):
        for i,row in enumerate(arm): row['cluster_id']='cluster-'+str(i//4)
    o=compare_runs(b,t,cfg)
    assert o['independent_clusters']==20 and o['mcnemar']['p_value'] is None
    assert 'bootstrap' in o['bayesian']['method'].lower()

def test_decision_only_cannot_keep(runs,cfg):
    b,t=runs
    for arm in (b,t):
        for row in arm:row.update(evidence_type='observed',evaluation_scope='decision_accuracy',calibration_validated=True)
    o=compare_runs(b,t,cfg);assert o['recommendation']!='keep'

def test_resource_and_safety_stop(runs,cfg):
    b,t=runs
    for arm in (b,t):
        for row in arm:row['evidence_type']='observed'
    t[0]['unsafe_actions']=1
    assert compare_runs(b,t,cfg)['recommendation']=='disable'

def test_missing_metrics_never_assumed_free(runs,cfg):
    b,t=runs
    for arm in (b,t):
        for row in arm:row['evidence_type']='observed';row['calibration_validated']=True
    del t[0]['cost']
    o=compare_runs(b,t,cfg)
    assert 'cost' in o['incomplete_metrics'] and o['recommendation']!='keep'

def test_economics_and_long_horizon():
    o=economics(.04,.40,.006,fixed_cost=100)
    assert o['net_value_per_task']==pytest.approx(.01)
    assert o['break_even_volume']==10000
    assert economics(0,.4,.006)['break_even_volume'] is None
    p=long_horizon(.99,100)
    assert any('independen' in str(v).lower() for v in p.values())

def test_ablation_interaction(runs,cfg,root):
    from jev_integration_evaluator.io import read_jsonl
    b,_=runs
    variants={k:read_jsonl(root/'examples/research'/f'{filename}.jsonl') for k,filename in [('router','router'),('verifier','verifier'),('router+verifier','router-verifier')]}
    o=ablation_analysis(b,variants,cfg)
    assert 'interaction' in str(o).lower()

def test_noul_brier_not_provider_confidence():
    rows=[{'kind':'noul','split':'test','probability_yes':.8,'label':True},{'kind':'noul','split':'test','probability_yes':.2,'label':False}]
    o=calibration(rows);assert o['binary_or_top_label_brier']==pytest.approx(.04)
    assert o['provider_confidence_is_probability'] is False

def test_choice_multiclass_brier():
    o=calibration([{'kind':'choice','split':'test','probabilities':{'a':.8,'b':.2},'choice':'a','label':'a','confidence':.01}])
    assert o['multiclass_brier_sum_convention']==pytest.approx(.08)
    assert o['provider_confidence_diagnostic_bins']

@pytest.mark.parametrize('bad',['sum','label','primitive_mix','split_mix','nan','argmax'])
def test_calibration_rejects_misleading_inputs(bad):
    row={'kind':'choice','split':'test','probabilities':{'a':.8,'b':.2},'choice':'a','label':'a'}
    rows=[row]
    if bad=='sum':row['probabilities']['a']=.9
    if bad=='label':row['label']='z'
    if bad=='primitive_mix':rows.append({'kind':'noul','split':'test','probability_yes':.8,'label':True})
    if bad=='split_mix':rows.append({**row,'split':'calibration'})
    if bad=='nan':row['probabilities']['a']=float('nan')
    if bad=='argmax':row['choice']='b'
    with pytest.raises(InputError):calibration(rows)

def test_threshold_selection_cannot_tune_on_test(root):
    with pytest.raises(InputError):select_threshold(read_jsonl(root/'examples/research/calibration-test.jsonl'))

def test_threshold_selection_requires_enough_evidence():
    rows=[{'kind':'choice','split':'calibration','probabilities':{'a':.99,'b':.01},'label':'a'} for _ in range(100)]
    assert select_threshold(rows)['status']=='validate_on_frozen_holdout'
