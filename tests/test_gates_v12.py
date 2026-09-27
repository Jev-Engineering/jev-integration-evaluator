"""Fabricated observations exercise protocol checks, not JEV effectiveness."""
import copy
import pytest
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import InputError,digest
from jev_integration_evaluator.gates import evaluate_gate_bundle,validate_gate_manifest,gate_rubric_hash
from jev_integration_evaluator.study import freeze_study,validate_study,evaluate_study
from jev_integration_evaluator.contracts import seal
from scripts.v12_fixtures import all_gate_study


@pytest.fixture(scope='module')
def prototype():
    c=load_config();c['validation'].update(bootstrap_samples=120,bayesian_samples=200)
    return all_gate_study(c)


@pytest.fixture
def study12(prototype):return copy.deepcopy(prototype)


def test_every_gate_recomputed_and_synthetic_cannot_activate(study12):
    inv,plan,b,j,bundle,fixtures=study12
    result=evaluate_study(plan,b,j,inventory=inv,gate_bundle=bundle,expected_digest=plan['contract_digest'])
    assert result['gate_evidence']['all_gates_numerically_pass']
    assert not result['gate_evidence']['all_gates_verified']
    assert result['gate_evidence']['allocated_alpha']==.05
    assert result['recommendation']=='needs_more_evidence' and not result['deployment_authorized']
    assert len(result['gate_evidence']['gates'])==2


@pytest.mark.parametrize('mutation',['missing_gate','extra_gate','duplicate_gate','manifest','omitted_row','changed_label','wrong_plan','fake_boolean'])
def test_bundle_requires_actual_complete_matching_gate_evidence(study12,mutation):
    inv,plan,b,j,bundle,_=study12
    if mutation=='missing_gate':bundle['gates'].pop()
    if mutation=='extra_gate':bundle['gates'].append({**copy.deepcopy(bundle['gates'][0]),'gate_id':'extra'})
    if mutation=='duplicate_gate':bundle['gates'].append(copy.deepcopy(bundle['gates'][0]))
    if mutation=='manifest':bundle['gate_manifest_digest']=digest('different')
    if mutation=='omitted_row':bundle['gates'][0]['holdout_rows'].pop()
    if mutation=='changed_label':bundle['gates'][0]['holdout_rows'][0]['label']='stop'
    if mutation=='wrong_plan':bundle['gates'][0]['threshold_plan']=bundle['gates'][1]['threshold_plan']
    if mutation=='fake_boolean':bundle['gates'][0]={'gate_id':'gate-0','eligible_for_activation':True}
    with pytest.raises(InputError):evaluate_gate_bundle(plan['specification'],bundle)


@pytest.mark.parametrize('mutation',['inventory_missing','fingerprint','source','review','reviewer','reason','tier','deterministic','realtime','primary','unknown_label','duplicate_gate','legacy'])
def test_freeze_requires_current_sources_and_gate_contract(study12,cfg,mutation):
    inv,plan,b,j,bundle,_=study12;spec=copy.deepcopy(plan['specification']);g=spec['deployment_gates'][0]
    c=next(c for c in inv['candidates'] if c['candidate_id']==g['candidate_id'])
    if mutation=='inventory_missing':inv=None
    if mutation=='fingerprint':inv['scan_fingerprint']=digest('stale')
    if mutation=='source':c['source']['file_sha256']=digest('new-context')
    if mutation=='review':c['semantic_review']['source_sha256']=digest('old-source')
    if mutation in ('reason','reviewer'):c['semantic_review'][mutation]=''
    if mutation=='tier':c['tier']=0
    if mutation=='deterministic':c['deterministic_alternative']='mandatory'
    if mutation=='realtime':c['hard_real_time']=True
    if mutation=='primary':g['primary_question']='missing'
    if mutation=='unknown_label':g['acceptance_policy']['action_probability_floors']['not-registered']=.95
    if mutation=='duplicate_gate':spec['deployment_gates'][1]['gate_id']=g['gate_id']
    if mutation=='legacy':spec.update(holdout_report_digest=digest('x'),holdout_binding={'model_id':spec['jev']['model_id'],
          'policy_version':spec['jev']['policy_version'],'rubric_hash':digest('r'),'policy_digest':digest('p')})
    with pytest.raises(InputError):freeze_study(spec,cfg,inventory=inv)


@pytest.mark.parametrize('change',['policy','probability','abstention','question','primary_role','evidence_type','alpha','task_leakage','cluster_leakage'])
def test_evidence_cannot_be_reused_across_changed_gates(study12,change):
    inv,plan,b,j,bundle,_=study12;spec=plan['specification'];g=spec['deployment_gates'][0]
    if change=='policy':g['policy_version']='changed'
    if change=='probability':g['acceptance_policy']['probability_floor']=.91
    if change=='abstention':g['acceptance_policy']['abstention_labels']=['stop']
    if change=='question':g['questions']['action']['instructions']='Different semantic instruction'
    if change=='primary_role':
        g['questions']['other']=copy.deepcopy(g['questions']['action']);g['primary_question']='other'
    if change=='evidence_type':spec['evidence_type']='observed'
    if change=='alpha':spec['gate_familywise_alpha']=.01
    if change in ('task_leakage','cluster_leakage'):
        key='task_hash' if change=='task_leakage' else 'cluster_id'
        spec['schedule'][0][key]=bundle['gates'][0]['threshold_plan']['calibration_identities'][0][key]
    bundle['gate_manifest_digest']=digest(spec['deployment_gates'])
    with pytest.raises(InputError):evaluate_gate_bundle(spec,bundle)


def test_primary_question_role_changes_identity_even_for_identical_label_sets():
    from scripts.v12_fixtures import questions
    q=questions();q['other']=copy.deepcopy(q['action'])
    assert gate_rubric_hash(q,'jev-1.13.0','action')!=gate_rubric_hash(q,'jev-1.13.0','other')
    with pytest.raises(InputError):gate_rubric_hash(q,'jev-1.13.0','missing')


def test_all_gate_outcomes_bind_treatment_and_full_denominator(study12):
    inv,p,b,j,bundle,_=study12
    with pytest.raises(InputError):validate_study(p,b[:-1],j[:-1],inventory=inv)
    j[0]['gate_manifest_digest']=digest('other-treatment')
    with pytest.raises(InputError):validate_study(p,b,j,inventory=inv)


def test_missing_bundle_never_supports_keep(study12,monkeypatch):
    inv,p,b,j,_,_=study12
    monkeypatch.setattr('jev_integration_evaluator.study.compare_runs',lambda *a:{'recommendation':'keep','recommendation_reasons':[]})
    r=evaluate_study(p,b,j,inventory=inv,expected_digest=p['contract_digest'])
    assert r['recommendation']=='needs_more_evidence' and not r['holdout_evidence_verified']


def test_observed_only_branch_still_needs_pinned_study_digest(cfg,monkeypatch):
    # All values remain fabricated unit-test data, despite the branch label.
    inv,p,b,j,bundle,_=all_gate_study(cfg,evidence='observed')
    monkeypatch.setattr('jev_integration_evaluator.study.compare_runs',lambda *a:{'recommendation':'keep','recommendation_reasons':[]})
    r=evaluate_study(p,b,j,inventory=inv,gate_bundle=bundle)
    assert r['holdout_evidence_verified'] and r['recommendation']=='needs_more_evidence'
    r=evaluate_study(p,b,j,inventory=inv,gate_bundle=bundle,expected_digest=p['contract_digest'])
    assert r['recommendation']=='keep' and not r['deployment_authorized']
