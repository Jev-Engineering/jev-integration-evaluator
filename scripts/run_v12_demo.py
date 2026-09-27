"""Exercise multi-placement selection, gate evidence, budgets and monitoring offline.

Every model/study/monitor outcome is synthetic. No target code, remote service or
host action is invoked. Expected enforcement failures are explicitly asserted.
"""
from __future__ import annotations
import argparse
import copy
import json
import sys
from datetime import datetime,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev_integration_evaluator.cli import main as cli
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import InputError,read_json,read_jsonl,write_json
from jev_integration_evaluator.budget import BudgetCoordinator
from jev_integration_evaluator.runtime import SafeRouter,HostGate
from jev_integration_evaluator.client import FixtureClient
from scripts.v12_fixtures import all_gate_study,scenario_spec,monitor_fixture


def run_demo(out: Path) -> dict:
    out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise InputError('Choose a new or empty output directory for the synthetic demonstration')
    commands=[]
    def invoke(*args,expected=0):
        argv=[str(x) for x in args];code=cli(argv)
        commands.append({'command':argv,'exit_code':code})
        if code!=expected:raise InputError('Unexpected offline command exit status')
    cfg=load_config();cfg['validation'].update(bootstrap_samples=250,bayesian_samples=500)
    write_json(out/'config.json',{'jev_analysis':cfg})
    inv,old,b,j,bundle,fixtures=all_gate_study(cfg)
    write_json(out/'reviewed-inventory.json',inv)
    ids={g['candidate_id'] for g in old['specification']['deployment_gates']}
    scenario=scenario_spec([c for c in inv['candidates'] if c['candidate_id'] in ids])
    write_json(out/'scenarios.json',scenario)
    invoke('optimize-robust','--inventory',out/'reviewed-inventory.json','--spec',out/'scenarios.json',
           '--config',out/'config.json','--out',out/'robust-placement-sets.json')
    for gate,entry,cal,spec,report in fixtures:
        prefix=gate['gate_id']
        write_json(out/(prefix+'-calibration.json'),cal)
        write_json(out/(prefix+'-threshold-spec.json'),spec)
        write_json(out/(prefix+'-threshold-policy.json'),entry['threshold_plan'])
        write_json(out/(prefix+'-holdout.json'),entry['holdout_rows'])
        invoke('threshold-check','--plan',out/(prefix+'-threshold-policy.json'),'--input',out/(prefix+'-holdout.json'),
               '--expected-digest',entry['threshold_plan']['contract_digest'],'--out',out/(prefix+'-holdout-report.json'),'--enforce',expected=3)
        assert read_json(out/(prefix+'-holdout-report.json'))['contract_digest']==gate['holdout_report_digest']
    write_json(out/'study-spec.json',old['specification']);write_json(out/'gate-bundle.json',bundle)
    invoke('study-freeze','--spec',out/'study-spec.json','--inventory',out/'reviewed-inventory.json',
           '--config',out/'config.json','--out',out/'study.json')
    plan=read_json(out/'study.json')
    for row in b+j:row['study_digest']=plan['contract_digest']
    write_json(out/'baseline.json',b);write_json(out/'treatment.json',j)
    for cmd in ('study-check','study-evaluate'):
        args=[cmd,'--plan',out/'study.json','--inventory',out/'reviewed-inventory.json',
              '--baseline',out/'baseline.json','--jev',out/'treatment.json','--expected-digest',plan['contract_digest'],
              '--out',out/(cmd+'.json')]
        if cmd=='study-evaluate':args+=['--gate-bundle',out/'gate-bundle.json','--enforce']
        invoke(*args,expected=3 if cmd=='study-evaluate' else 0)
    monitor,rows,asof=monitor_fixture()
    write_json(out/'monitor-spec.json',monitor['specification'])
    invoke('monitor-freeze','--spec',out/'monitor-spec.json','--out',out/'monitor.json')
    monitor=read_json(out/'monitor.json')
    for row in rows:row['monitor_digest']=monitor['contract_digest']
    write_json(out/'monitor-outcomes.json',rows)
    invoke('monitor-check','--plan',out/'monitor.json','--input',out/'monitor-outcomes.json',
           '--as-of',asof,'--expected-digest',monitor['contract_digest'],'--out',out/'monitor-healthy.json','--enforce',expected=3)
    broken=copy.deepcopy(rows);next(r for r in broken if r['arm']=='jev')['unsafe_actions']=1
    write_json(out/'monitor-incident-outcomes.json',broken)
    invoke('monitor-check','--plan',out/'monitor.json','--input',out/'monitor-incident-outcomes.json',
           '--as-of',asof,'--expected-digest',monitor['contract_digest'],'--out',out/'monitor-incident.json','--enforce',expected=3)
    incomplete=copy.deepcopy(rows[:-1]);incomplete[0]['cost']=None
    write_json(out/'monitor-incomplete-outcomes.json',incomplete)
    invoke('monitor-check','--plan',out/'monitor.json','--input',out/'monitor-incomplete-outcomes.json',
           '--as-of',(datetime.fromisoformat(asof)+timedelta(minutes=2)).isoformat(),
           '--expected-digest',monitor['contract_digest'],'--out',out/'monitor-incomplete.json','--enforce',expected=3)
    for kind,name in (('scenario-spec','scenarios.json'),('gate-bundle','gate-bundle.json'),
                      ('study-spec','study-spec.json'),('study','study.json'),('monitor-spec','monitor-spec.json'),
                      ('monitor','monitor.json'),('monitor-outcome','monitor-outcomes.json')):
        invoke('validate','--kind',kind,'--input',out/name)
    # Three synthetic shadow submissions across two routers; only two admissions.
    event=read_jsonl(ROOT/'examples/research/decisions.jsonl')[0]
    client=FixtureClient(read_json(ROOT/'examples/research/fixture-responses.json'))
    budget=BudgetCoordinator(max_calls_per_task=2,max_cost_per_task=.01,max_total_calls=2,max_total_cost=.01)
    runtime=copy.deepcopy(cfg['runtime']);runtime['mode']='shadow'
    decisions=[];calls=0
    with SafeRouter(client,runtime,budget_coordinator=budget) as one,SafeRouter(client,runtime,budget_coordinator=budget) as two:
        for router in (one,two,one):
            d=router.route(task_id='synthetic-shared-task',state=event['state'],questions=event['questions'],
                           primary_question='action',evidence_question='sufficient',baseline_action='stop',
                           gate=HostGate(('inspect','stop')),estimated_cost_upper_bound=.001)
            decisions.append({'action':d.action,'source':d.source})
            for future in list(router.futures):future.result(timeout=5)
        calls=one.stats['calls']+two.stats['calls']
    assert calls==2 and budget.snapshot()['calls']==2 and all(d['source']=='baseline' for d in decisions)
    write_json(out/'shared-budget-demo.json',{'evidence_type':'synthetic','ledger':budget.snapshot(),
               'model_fixture_calls':calls,'returned_decisions':decisions,'host_actions_executed':0})
    study=read_json(out/'study-evaluate.json')
    assert study['gate_evidence']['all_gates_numerically_pass'] and not study['gate_evidence']['all_gates_verified']
    assert study['recommendation']=='needs_more_evidence'
    assert read_json(out/'monitor-healthy.json')['status']=='within_declared_limits'
    assert read_json(out/'monitor-incident.json')['recommendation']=='suspend'
    assert read_json(out/'monitor-incomplete.json')['status']=='incomplete_overdue_window'
    summary={'version':'1.2.0','evidence_type':'synthetic','network_requests':0,'target_code_executed':False,
             'host_actions_executed':0,'task_pairs':len(b),'gate_count':len(fixtures),
             'calibration_observations':sum(len(f[2]) for f in fixtures),
             'holdout_observations':sum(len(f[1]['holdout_rows']) for f in fixtures),
             'monitor_tasks':len(rows),'shared_fixture_calls':calls,'shadow_submissions':3,
             'study_recommendation':study['recommendation'],'synthetic_adoption_blocked':True,
             'monitor_incident_suspension_is_recommendation_only':True,'commands':commands}
    write_json(out/'demo-summary.json',summary)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path);args=parser.parse_args(argv)
    try:
        summary=run_demo(args.out);print(json.dumps({k:v for k,v in summary.items() if k!='commands'},indent=2));return 0
    except (InputError,OSError) as exc:print(str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
