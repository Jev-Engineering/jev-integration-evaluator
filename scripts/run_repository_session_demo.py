"""Exercise the session through real edited A-M fixture hosts, entirely offline.

This command authorizes only its own freshly generated disposable test hosts.
It is not a path-input independent corpus or a provider/bootstrap experiment.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import platform
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev_integration_evaluator import repository_run as run
from jev_integration_evaluator.integrations import lifecycle as engine
from jev_integration_evaluator.io import file_hash,read_json,write_json
from implementation_fixtures import fixture


def demonstrate(output: Path) -> dict:
    output=output.absolute()
    if output==ROOT or output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use a fresh private output directory outside the checkout')
    output.mkdir(mode=0o700)
    rows=[]
    for pattern in 'ABCDEFGHIJKLM':
        with tempfile.TemporaryDirectory(prefix='session-'+pattern+'-',dir=output) as directory:
            work=Path(directory);root=work/'target';session=work/'session'
            inventory,spec=fixture(root,pattern,tag='session_demo_'+pattern.lower())
            before={p.name:file_hash(p) for p in root.iterdir()}
            context=run.request_context(objective='Synthetic '+pattern+' session qualification',saved_answers={'benefit_estimate':None})
            inspection=run.inspect_repository(root,context=context)
            scope=dict(schema_version='1.0',kind='repository-run-scope-v1',reference='synthetic-fixture-operator',
                repository_identity=inspection['report']['repository_identity'],context_sha256=inspection['context_sha256'],
                bundle_digest=None,trusted_session_head=None,trusted_baseline_receipt=None,trusted_modified_receipt=None,
                rollback_digest=None,execution_environment='trusted_host',grants={**run.ZERO_GRANTS,'prepare':True})
            planned=run.run_repository(root,session,context=context,
                prepared=dict(schema_version='1.0',adapter=run.ADAPTER,inventory=inventory,spec=spec),scope=scope,stop_after='plan')
            assert planned['status']=='planned' and before=={p.name:file_hash(p) for p in root.iterdir()}
            scope.update(bundle_digest=planned['bundle_digest'],trusted_session_head=planned['session_head_sha256'],
                         grants={**run.ZERO_GRANTS,'baseline':True,'apply':True,'modified':True})
            verified=run.run_repository(root,session,scope=scope)
            assert verified['status']=='verified',verified['status']
            assert run.run_repository(root,session)['status']=='recorded_untrusted'
            state=json.loads((session/'journal.jsonl').read_text().splitlines()[-1])['state']
            bundle=Path(state['bundle']['path']);plan=read_json(bundle/'implementation-plan.json')
            receipt=read_json(bundle/'verification-receipt.json')
            assert all(r['status']=='passed' for r in receipt['results'])
            scope.update(trusted_session_head=verified['session_head_sha256'],rollback_digest=engine.rollback_digest(plan),
                         grants={**run.ZERO_GRANTS,'rollback':True})
            restored=run.run_repository(root,session,scope=scope,recover=True)
            assert restored['status']=='rolled_back' and before=={p.name:file_hash(p) for p in root.iterdir()}
            rows.append(dict(recipe=spec['recipe']['id'],baseline_cases=len(spec['verification']['cases']),
                modified_cases=receipt['scheduled_cases'],passed_modified_cases=len(receipt['results']),
                retained_schedules=len(verified['retained_schedules']),final_status='rolled_back',source_restored=True))
    result=dict(status='passed',classification='synthetic_wiring',python=platform.python_version(),platform=platform.platform(),
        engine_identity=engine.engine_identity(),recipes=rows,targets_applied_unverified=0,provider_connectivity='not_tested',
        benefit_demonstrated=False,runtime_activation_authorized=False,independent_corpus_qualified=False)
    write_json(output/'summary.json',result)
    return result


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=demonstrate(args.out)
        print(json.dumps({'status':result['status'],'recipes':len(result['recipes']),'targets_applied_unverified':0}))
        return 0
    except (ValueError,OSError,AssertionError) as error:
        print(json.dumps({'status':'failed','error':type(error).__name__}),file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
