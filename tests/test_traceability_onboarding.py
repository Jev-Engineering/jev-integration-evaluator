import copy,sys,importlib.util
from dataclasses import asdict
from pathlib import Path
import pytest,jsonschema
from jev_integration_evaluator.io import InputError,digest,read_json,read_jsonl,write_json
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.onboarding import onboard
from jev_integration_evaluator.implementation import scaffold_integration
from jev_integration_evaluator.traceability import link_artifact
from jev_integration_evaluator.runtime import SafeRouter,HostGate,Thresholds
from jev_integration_evaluator.client import FixtureClient
from jev_integration_evaluator.traces import AuditLog,correlate_traces
from jev_integration_evaluator.statistics import ablation_analysis,exact_mcnemar
from jev_integration_evaluator.questions import validate_questions


def test_onboarding_reuses_answers_and_bounds_questions(root,cfg):
    scan=scan_repo(root/'examples/coding-agent',cfg)
    start=onboard(scan,{'objective':'better completion','trace_path':None})
    assert len(start['questions'])<=5
    assert 'objective' not in {q['field'] for q in start['questions']}
    assert start['safe_defaults']['network'] is False
    done=onboard(scan,dict(objective='x',latency_budget_ms=100,cost_budget_per_task=.01,risk_tolerance='strict',environment='test',benchmark_path=None,trace_path=None))
    assert done['state']=='ready_for_analysis'
    extra=onboard(scan,done['answers'],mode='implementation')
    assert extra['questions'][0]['field']=='modification_authority'


def test_link_preserves_exact_source_to_implementation_chain(root,cfg,tmp_path):
    scan=scan_repo(root/'examples/coding-agent',cfg);c=scan['candidates'][0]
    manifest=scaffold_integration(scan,c['candidate_id'],tmp_path/'adapter')
    result=link_artifact(scan,c['candidate_id'],'implementation',tmp_path/'adapter/integration-manifest.json')
    assert result['candidates'][0]['traceability']['implementation'][0]['sha256']
    jsonschema.validate(result,read_json(root/'schemas/inventory.schema.json'))
    receipt={'candidate_id':c['candidate_id'],'source_sha256':c['source']['source_sha256'],'experiment_id':c['recommended_experiment']['id'],'test_id':'safe-boundary','status':'passed'}
    write_json(tmp_path/'test.json',receipt)
    link_artifact(scan,c['candidate_id'],'test',tmp_path/'test.json')
    assert c['traceability']['tests'][0]['kind']=='test'
    receipt['source_sha256']='0'*64;write_json(tmp_path/'test.json',receipt)
    with pytest.raises(InputError):link_artifact(scan,c['candidate_id'],'test',tmp_path/'test.json')


def test_linked_outcome_does_not_grant_authority(root,cfg,tmp_path):
    scan=scan_repo(root/'examples/coding-agent',cfg);c=scan['candidates'][0]
    receipt={'candidate_id':c['candidate_id'],'source_sha256':c['source']['source_sha256'],'experiment_id':c['recommended_experiment']['id'],'result':{'recommendation':'needs_more_evidence','evidence_type':'synthetic'}}
    write_json(tmp_path/'result.json',receipt);link_artifact(scan,c['candidate_id'],'outcome',tmp_path/'result.json')
    assert c['traceability']['outcome']['kind']=='outcome'
    assert c['deployment_status']=='not_validated'


def test_runtime_audit_correlates_to_source(root,cfg,example_event,tmp_path):
    scan=scan_repo(root/'examples/coding-agent',cfg);c=scan['candidates'][0]
    client=FixtureClient(read_json(root/'examples/research/fixture-responses.json'))
    runtime=cfg['runtime'];runtime['mode']='active'
    activation=dict(approved=True,calibration_validated=True,model=runtime['model'],policy_version='v1',questions_hash=digest(example_event['questions']),thresholds_hash=digest(asdict(Thresholds())),holdout_evidence_ref='synthetic-test-only')
    with SafeRouter(client,runtime,activation=activation,audit_log=AuditLog(tmp_path/'audit.jsonl')) as router:
        router.route(task_id='testtask',state=example_event['state'],questions=example_event['questions'],primary_question='action',baseline_action='stop',gate=HostGate(('inspect','stop')),provenance={'candidate_id':c['candidate_id'],'experiment_id':c['recommended_experiment']['id'],'source_location':c['source']})
    result=correlate_traces(scan,read_jsonl(tmp_path/'audit.jsonl'),cfg)
    assert result['trace_correlation']['matched_source_keys']==1
    assert c['runtime_evidence']['model_calls']==1
    assert c['runtime_evidence']['tasks']==1
    assert c['runtime_evidence']['failure_rate'] is None


def test_duplicate_functions_do_not_overwrite_graph(tmp_path,cfg):
    (tmp_path/'same.py').write_text('def choose(x):\n    return x\ndef choose(x):\n    return x+1\n')
    scan=scan_repo(tmp_path,cfg)
    ids=[c['candidate_id'] for c in scan['candidates']]
    assert len(ids)==len(set(ids))==2
    assert len(scan['architecture']['nodes'])==2
    assert scan['coverage']['warnings']


def test_python_module_level_decision_detected(tmp_path,cfg):
    (tmp_path/'main.py').write_text('proposal = llm.choose(state)\nresult = executor.execute_tool(proposal)\n')
    s=scan_repo(tmp_path,cfg)
    assert any(c['pattern']=='A' and c['source']['symbol']=='<module>' for c in s['candidates'])


def test_ablation_combined_alias_produces_actual_interaction(root,cfg,runs):
    baseline,_=runs
    variants={k:read_jsonl(root/'examples/research'/f'{p}.jsonl') for k,p in [('router','router'),('verifier','verifier'),('router+verifier','router-verifier')]}
    r=ablation_analysis(baseline,variants,cfg)
    assert r['router_verifier_interaction']['difference_in_differences']==pytest.approx(.15)
    assert r['router_verifier_interaction']['bootstrap']['interval'] is not None


@pytest.mark.parametrize('a,b',[(-1,0),(0,-1),(True,2),(1.2,3)])
def test_mcnemar_input_validation(a,b):
    with pytest.raises(InputError):exact_mcnemar(a,b)


def test_host_approval_strings_cannot_bypass_gate(cfg,example_event,root):
    client=FixtureClient(read_json(root/'examples/research/fixture-responses.json'))
    with SafeRouter(client,cfg['runtime']) as r:
        with pytest.raises(InputError):r.route(task_id='x',state={},questions=example_event['questions'],primary_question='action',baseline_action='stop',gate=HostGate(('stop',),approval_required=True,approval_granted='false'))
    assert client.calls==0


@pytest.mark.parametrize('kind,criteria',[('choice',{'a':'only one'}),('score',['one']),('score',list(range(11))),('noul',{'yes':'wrong key','no':'wrong key'})])
def test_invalid_question_shapes(kind,criteria):
    with pytest.raises(InputError):validate_questions({'x':{'type':kind,'instructions':'a criterion','criteria':criteria}})


def test_package_validator_runs(root):
    spec=importlib.util.spec_from_file_location('jev_package_validator',root/'scripts/validate_package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.validate()['status']=='passed'


def test_synthetic_trace_never_creates_high_leverage_tier(root,cfg):
    from jev_integration_evaluator.scoring import apply_reviews
    scan=scan_repo(root/'examples/coding-agent',cfg);c=scan['candidates'][0]
    cfg['thresholds']['high_leverage']=.1;cfg['thresholds']['strong_candidate']=.05
    apply_reviews(scan,{c['candidate_id']:{'source_sha256':c['source']['source_sha256'],'reviewer':'test','reason':'Synthetic demonstration only','approved':True}},cfg)
    events=[{'source_location':c['source'],'task_id':str(i),'evidence_type':'synthetic','success':False} for i in range(30)]
    correlate_traces(scan,events,cfg)
    assert c['runtime_evidence']['evidence_type']=='synthetic'
    assert c['tier']!=3
    assert c['dimensions']['current_failure_rate']['status']=='inferred'
