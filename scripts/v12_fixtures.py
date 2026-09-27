"""Explicitly synthetic fixtures shared by the offline v1.2 demo and tests.

Nothing here is an activation certificate or real performance measurement.
Tests may change evidence_type only to exercise otherwise unreachable branches.
"""
from __future__ import annotations
import copy
from pathlib import Path
from datetime import datetime, timedelta, timezone
from jev_integration_evaluator.io import digest, read_jsonl
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scenarios import DEFAULT_WEIGHTS
from jev_integration_evaluator.gates import gate_rubric_hash, SOURCE_FIELDS
from jev_integration_evaluator.holdout import freeze_threshold, validate_holdout
from jev_integration_evaluator.study import freeze_study
from jev_integration_evaluator.monitoring import freeze_monitor

ROOT = Path(__file__).resolve().parents[1]


def estimates(gain=.15, cost=.001, latency=10, calls=1):
    return dict(quality_gain=gain,reliability_gain=0,failure_reduction=0,model_call_reduction=0,
                added_latency_ms=latency,added_cost=cost,calls_per_task=calls,complexity=.1,
                maintenance=0,false_positive_rate=0,false_negative_rate=0,risk=.01,throughput=100)


def inventory(cfg):
    inv = scan_repo(ROOT/'examples/coding-agent', cfg)
    chosen = []
    for c in inv['candidates']:
        if c['tier'] == 0 or c.get('deterministic_alternative') in ('preferred','mandatory'):
            continue
        # Only for this authored synthetic source fixture, not an auto-review rule.
        c['semantic_review'] = {'approved':True,'reviewer':'synthetic-demo-author',
                                'reason':'Authored bounded agent fixture; synthetic demonstration only.',
                                'source_sha256':c['source']['source_sha256']}
        chosen.append(c)
        if len(chosen) == 2:
            break
    if len(chosen) != 2:
        raise AssertionError('Synthetic example no longer supplies two eligible candidates')
    return inv, chosen


def scenario_spec(candidates):
    a,b=[c['candidate_id'] for c in candidates[:2]]
    return {'schema_version':'1.2','requires':{},'minimal_retention':.9,
            'utility_weights':dict(DEFAULT_WEIGHTS),
            'scenarios':[{'scenario_id':'nominal','evidence_type':'synthetic','provenance':'Fabricated demo assumptions, not model measurements.',
                          'estimates':{a:estimates(.30),b:estimates(.15)},'interactions':[]},
                         {'scenario_id':'adverse','evidence_type':'synthetic','provenance':'Fabricated stress assumptions; not a confidence interval.',
                          'estimates':{a:estimates(-.10),b:estimates(.12)},'interactions':[]}]}


def questions():
    return {'action':{'type':'choice','instructions':'Select the action supported by the supplied evidence.',
                      'criteria':{'inspect':'Additional inspection is supported.','stop':'Stopping is supported.'}}}


def gate_fixture(candidate, index=0, *, evidence='synthetic', n=120):
    q=questions(); model='jev-1.13.0'; policy='synthetic-policy-'+str(index)
    rh=gate_rubric_hash(q,model,'action')
    def row(i,split):
        uid=f'gate-{index}-{split}-{i}'
        return {'observation_id':uid,'task_hash':digest(uid),'cluster_id':uid,'subgroup':'ordinary',
                'kind':'choice','split':split,'model_id':model,'policy_version':policy,'rubric_hash':rh,
                'evidence_type':evidence,'probabilities':{'inspect':.99,'stop':.01},'choice':'inspect',
                'confidence':.95,'label':'inspect'}
    cal=[row(i,'calibration') for i in range(40)]
    test=[row(i,'test') for i in range(n)]
    policy_spec={'probability_floor':.9,'confidence_floor':.75,'action_probability_floors':{},
                 'abstention_labels':[],'maximum_error':.05,'alpha':.025,'minimum_accepted':30,
                 'required_subgroups':['ordinary'],
                 'holdout_schedule':[{k:r[k] for k in ('observation_id','task_hash','cluster_id','subgroup')} for r in test]}
    plan=freeze_threshold(cal,policy_spec)
    report=validate_holdout(plan,test,expected_digest=plan['contract_digest'])
    gate={'gate_id':f'gate-{index}','candidate_id':candidate['candidate_id'],
          'source':{k:candidate['source'][k] for k in SOURCE_FIELDS},'model_id':model,'policy_version':policy,
          'questions':q,'primary_question':'action','acceptance_policy':copy.deepcopy(report['acceptance_policy']),
          'threshold_policy_digest':plan['contract_digest'],'holdout_report_digest':report['contract_digest']}
    entry={'gate_id':gate['gate_id'],'threshold_plan':plan,'holdout_rows':test}
    return gate,entry,cal,policy_spec,report


def all_gate_study(cfg, *, evidence='synthetic'):
    inv,cs=inventory(cfg)
    fixtures=[gate_fixture(c,i,evidence=evidence) for i,c in enumerate(cs)]
    gates=[f[0] for f in fixtures]
    bundle={'schema_version':'1.2','gate_manifest_digest':digest(gates),'gates':[f[1] for f in fixtures]}
    b=read_jsonl(ROOT/'examples/research/baseline.jsonl')
    j=read_jsonl(ROOT/'examples/research/router-verifier.jsonl')
    fields=('treatment','code_revision','model_id','policy_version','prompt_hash','mode')
    spec={'experiment_id':'synthetic-v12-demo','dataset_id':b[0]['dataset_id'],'evidence_type':evidence,
          'primary_metric':'success','schedule':[{'task_id':r['task_id'],'replicate':r['replicate'],
          'task_hash':r['task_hash'],'cluster_id':r['task_id'],'split':'test','seed':r['seed']} for r in b],
          'baseline':{k:b[0][k] for k in fields},'jev':{k:j[0][k] for k in fields},
          'required_metrics':['cost','latency_ms','unsafe_actions','false_blocks'],
          'placement_inventory_fingerprint':inv['scan_fingerprint'],'gate_familywise_alpha':.05,
          'deployment_gates':gates}
    plan=freeze_study(spec,cfg,inventory=inv)
    for r in b+j:
        r.update(experiment_id=spec['experiment_id'],study_digest=plan['contract_digest'],split='test',
                 cluster_id=r['task_id'],run_status='completed',evidence_type=evidence,gate_manifest_digest=digest(gates))
    return inv,plan,b,j,bundle,fixtures


def monitor_fixture(*, evidence='synthetic', now=None, count=80):
    now=now or datetime(2026,9,26,12,0,tzinfo=timezone.utc)
    start=now-timedelta(minutes=10);end=now-timedelta(seconds=30)
    spec={'deployment_id':'synthetic-deployment','study_digest':digest('synthetic-study'),
          'runtime_contracts':{'gate-0':digest('synthetic-runtime-contract')},'window_id':'synthetic-window',
          'evidence_type':evidence,'starts_at':start.isoformat(),'ends_at':end.isoformat(),
          'reporting_grace_s':60,'max_report_age_s':600,'minimum_tasks_per_arm':5,
          'minimum_action_observations':5,'assignment_salt':'synthetic-canary-scope','canary_fraction':.5,
          'tasks':[{'task_id':f'task-{i}','task_hash':digest(['synthetic-monitor',i]),'cluster_id':f'cluster-{i}',
                    'cohort':'ordinary'} for i in range(count)],'required_cohorts':['ordinary'],
          'action_reference':{'inspect':1.0,'stop':0.0},
          'limits':{'unsafe_actions':0,'failure_rate':.2,'timeout_rate':.1,'failure_rate_increase':.1,
                    'p95_added_latency_ms':100,'mean_added_cost':.01,'fallback_rate':.2,'action_distribution_tv':.2}}
    plan=freeze_monitor(spec)
    rows=[]
    for a in plan['assignments']:
        rows.append({**a,'deployment_id':spec['deployment_id'],'study_digest':spec['study_digest'],
                     'window_id':spec['window_id'],'monitor_digest':plan['contract_digest'],'evidence_type':evidence,
                     'started_at':(start+timedelta(seconds=1)).isoformat(),
                     'finished_at':(start+timedelta(seconds=2)).isoformat(),'run_status':'completed','success':True,
                     'latency_ms':20.0 if a['arm']=='jev' else 10.0,'cost':.001,'unsafe_actions':0,
                     'fallbacks':0,'decisions':1,'action_counts':{'inspect':1}})
    return plan,rows,now.isoformat()
