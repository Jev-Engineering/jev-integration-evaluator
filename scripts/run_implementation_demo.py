"""Offline A–M host integration lifecycle; every assessment is explicitly synthetic.

Writes only the requested output and new temporary synthetic workspaces. It never
uses a live provider, publishes Git changes, or activates a real application. The
explicit demo invocation authorizes only these disposable fixture operations.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import platform
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev_integration_evaluator.io import InputError,read_json,write_json,file_hash
from jev_integration_evaluator.integrations.lifecycle import engine_identity
from implementation_fixtures import fixture


def command(*argv,expected=0):
    result=subprocess.run([sys.executable,'-m','jev_integration_evaluator',*map(str,argv)],cwd=ROOT,
                          capture_output=True,text=True,timeout=120)
    if result.returncode!=expected:
        raise InputError('Synthetic demo command failed: '+str(argv[0])+'; exit '+str(result.returncode)+'; '+result.stderr[-2000:])
    return json.loads(result.stdout)


def run(output,patterns='ABCDEFGHIJKLM'):
    output=Path(output).resolve()
    if output==ROOT or output.is_relative_to(ROOT):raise InputError('Keep demo evidence outside the package checkout')
    if output.exists() and any(output.iterdir()):raise InputError('Demo output must be new or empty')
    if not patterns or len(set(patterns))!=len(patterns) or not set(patterns)<=set('ABCDEFGHIJKLM'):raise InputError('Use unique A–M recipe letters')
    output.mkdir(parents=True,exist_ok=True)
    results=[];started=time.monotonic()
    for pattern in patterns:
        with tempfile.TemporaryDirectory(prefix='synthetic-'+pattern+'-',dir=output) as td:
            work=Path(td);seed=work/'seed';target=work/'target';bundle=work/'private-bundle'
            # Build source separately, then COPY it to the actual new target.
            fixture(seed,pattern,tag='demo_'+pattern.lower())
            shutil.copytree(seed,target)
            inventory,spec=fixture(target,pattern,tag='demo_'+pattern.lower())
            # fixture() scans/reviews the actual destination. No identity/root weakening.
            before={p.name:file_hash(p) for p in target.iterdir()}
            invpath,sp=work/'reviewed.json',work/'spec.json'
            write_json(invpath,inventory);write_json(sp,spec)
            command('validate','--kind','implementation-spec','--input',sp)
            catalog=command('implementation-recipes','--json')
            assert spec['recipe']['id'] in {r['id'] for r in catalog['recipes']}
            planned=command('implement-plan','--repo',target,'--inventory',invpath,'--candidate',spec['candidate_id'],'--spec',sp,'--out',bundle)
            if before!={p.name:file_hash(p) for p in target.iterdir()}:raise InputError('Planning modified a synthetic target')
            baseline=command('implement-verify','--phase','baseline','--repo',target,'--bundle',bundle,'--approve-execution')
            applied=command('implement-apply','--repo',target,'--bundle',bundle,'--approve',planned['bundle_digest'],'--baseline-sha256',baseline['receipt_sha256'])
            verified=command('implement-verify','--phase','modified','--repo',target,'--bundle',bundle,'--approve-execution','--baseline-sha256',baseline['receipt_sha256'])
            untrusted=command('implement-status','--repo',target,'--bundle',bundle)
            anchored=command('implement-status','--repo',target,'--bundle',bundle,'--trusted-receipt-sha256',verified['receipt_sha256'])
            if untrusted['status']!='applied_unverified' or anchored['status']!='verified':raise InputError('Receipt trust boundary failed')
            rolled=command('implement-rollback','--repo',target,'--bundle',bundle,'--approve',applied['rollback_digest'])
            if before!={p.name:file_hash(p) for p in target.iterdir()} or rolled['status']!='rolled_back':raise InputError('Synthetic target not restored')
            results.append({'recipe':spec['recipe']['id'],'shape':spec['recipe']['shape'],
                            'baseline_cases':baseline['scheduled_cases'],'modified_cases':verified['scheduled_cases'],
                            'passed_modified_cases':verified['passed_cases'],'contract_assertions':verified['contract_assertions'],
                            'bundle_digest':planned['bundle_digest'],'baseline_receipt_sha256':baseline['receipt_sha256'],
                            'verification_receipt_sha256':verified['receipt_sha256'],'unanchored_status':untrusted['status'],
                            'anchored_status':anchored['status'],'final_target_status':rolled['status'],'target_bytes_restored':True,
                            'classification':'synthetic'})
    result={'status':'passed','classification':'synthetic','engine_identity':engine_identity(),'python':platform.python_version(),
            'platform':platform.platform(),'duration_s':round(time.monotonic()-started,3),'recipes':results,
            'network_requests':0,'runtime_activation_authorized':False,'benefit_demonstrated':False,
            'targets_applied_unverified':0,'raw_target_source_or_preimages_published':False,
            'evidence_scope':'Local observed CLI/subprocess execution of explicitly synthetic fixtures; no live deployment evidence'}
    write_json(output/'summary.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True)
    parser.add_argument('--patterns',default='ABCDEFGHIJKLM',help='Selected fixture letters; default executes all thirteen')
    args=parser.parse_args()
    try:
        result=run(args.out,args.patterns)
        print(json.dumps({'status':result['status'],'recipes':len(result['recipes']),'summary':str(Path(args.out)/'summary.json'),
                          'targets_applied_unverified':0,'classification':'synthetic'},indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'failed','error':type(exc).__name__,'message':str(exc)}),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
