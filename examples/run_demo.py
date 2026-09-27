"""Offline runtime demonstration. All responses are explicitly synthetic fixtures."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataclasses import asdict
import argparse
from jev_integration_evaluator.client import FixtureClient
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import read_json,read_jsonl,digest,write_json
from jev_integration_evaluator.runtime import SafeRouter,HostGate,Thresholds
from jev_integration_evaluator.traces import AuditLog,verify_log


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='demo-output')
    args=parser.parse_args()
    here=Path(__file__).resolve().parent
    event=read_jsonl(here/'research/decisions.jsonl')[0]
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    cfg=load_config()['runtime'];cfg['mode']='active'
    activation={'approved':True,'calibration_validated':True,'model':cfg['model'],'policy_version':'synthetic-demo',
                'questions_hash':digest(event['questions']),'thresholds_hash':digest(asdict(Thresholds())),
                'holdout_evidence_ref':'synthetic-demo-only-not-an-activation-receipt-for-real-use'}
    client=FixtureClient(read_json(here/'research/fixture-responses.json'))
    with SafeRouter(client,cfg,policy_version='synthetic-demo',activation=activation,audit_log=AuditLog(out/'audit.jsonl')) as router:
        result=router.route(task_id=event['decision_id'],state=event['state'],questions=event['questions'],
            primary_question='action',evidence_question='sufficient',baseline_action=event['baseline_decision'],
            gate=HostGate(('inspect','stop')))
    summary={'evidence_type':'synthetic','baseline':'stop','proposal':result.action,'reason':result.reason,
             'actions_executed':0,'remote_requests':0,'fixture_calls':client.calls,
             'audit':verify_log(read_jsonl(out/'audit.jsonl'))}
    write_json(out/'summary.json',summary)
    print(summary)

if __name__=='__main__': main()
