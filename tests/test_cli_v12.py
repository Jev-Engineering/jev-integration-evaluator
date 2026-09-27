import copy
import pytest
from jev_integration_evaluator.cli import main
from jev_integration_evaluator.io import read_json,read_jsonl,write_json,InputError
from scripts.run_v12_demo import run_demo
from scripts.v12_fixtures import monitor_fixture,inventory
from jev_integration_evaluator.traces import AuditLog,correlate_traces


def test_new_workflow_end_to_end_offline(tmp_path):
    out=tmp_path/'demo';summary=run_demo(out)
    assert summary['gate_count']==2 and summary['task_pairs']==80
    assert summary['network_requests']==0 and summary['host_actions_executed']==0
    assert len(summary['commands'])==17
    assert summary['shared_fixture_calls']==2 and summary['synthetic_adoption_blocked']
    assert (out/'robust-placement-sets.report.md').is_file()
    assert (out/'monitor-healthy.report.md').is_file()
    with pytest.raises(InputError):run_demo(out)


def test_monitor_enforcement_and_invalid_input_exit_codes(tmp_path):
    plan,rows,now=monitor_fixture();write_json(tmp_path/'plan.json',plan);write_json(tmp_path/'rows.json',rows)
    args=['monitor-check','--plan',str(tmp_path/'plan.json'),'--input',str(tmp_path/'rows.json'),'--as-of',now,
          '--out',str(tmp_path/'report.json'),'--expected-digest',plan['contract_digest']]
    assert main(args)==0 and main(args+['--enforce'])==3
    rows[0]['cost']=-1;write_json(tmp_path/'rows.json',rows)
    assert main(args)==2


def test_cached_response_tokens_are_not_counted_as_new_inference(cfg,tmp_path):
    scan,candidates=inventory(cfg);c=candidates[0];log=AuditLog(tmp_path/'audit.jsonl')
    for cached in (False,True):
        log.append({'type':'assessment','cache_hit':cached,'task_id_hash':'same-task',
                    'evidence_type':'synthetic','source_location':c['source'],
                    'latency_ms':1,'usage':{'input_tokens':100,'output_tokens':2}})
    result=correlate_traces(scan,read_jsonl(tmp_path/'audit.jsonl'),cfg)
    target=next(x for x in result['candidates'] if x['candidate_id']==c['candidate_id'])
    assert target['runtime_evidence']['tokens']==102
    assert target['runtime_evidence']['model_calls']==1
