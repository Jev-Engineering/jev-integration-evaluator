"""Kill bounded, deliberate safety regressions using unchanged session tests.

Runs only copies of this package and its existing disposable synthetic fixtures.
This is mutation evidence, not independent corpus or external code-review evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
REL=Path('jev_integration_evaluator/repository_run.py')
TEST='tests/test_repository_run.py::'
MUTATIONS=[
 ('session_head_not_checked', 'if existing and value["trusted_session_head"] != head:',
  'if False and existing and value["trusted_session_head"] != head:',
  TEST+'test_stored_receipts_never_authenticate_themselves_for_resume[None]'),
 ('bundle_scope_not_bound', 'return bool(state["bundle"] and scope["bundle_digest"] == state["bundle"]["digest"])',
  'return True',TEST+'test_wrong_bundle_digest_grants_no_execution'),
 ('source_addition_not_invalidating', 'if _file_map(report) != expected:',
  'if False and _file_map(report) != expected:',TEST+'test_source_drift_blocks_before_any_execution[added]'),
 ('unanchored_status_claims_verified', 'return _summary(journal, "recorded_untrusted", "supply_externally_retained_session_head")',
  'return _summary(journal, "verified", "supply_externally_retained_session_head")',
  TEST+'test_resume_without_scope_is_read_only_untrusted_not_verified'),
 ('failure_history_discarded', '    if failure:\n        state["failures"].append(',
  '    if False and failure:\n        state["failures"].append(',TEST+'test_retry_bound_and_all_failed_schedules_are_retained'),
]


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.absolute()
    if out.exists() or out==ROOT or out.is_relative_to(ROOT):
        parser.error('Use a fresh output directory outside the checkout')
    out.mkdir(mode=0o700)
    original=(ROOT/REL).read_text();rows=[]
    # The unchanged implementation must pass the same oracles first.
    control=subprocess.run([sys.executable,'-m','pytest','-q',*[m[3] for m in MUTATIONS]],cwd=ROOT,
                           capture_output=True,text=True,timeout=120)
    control_ok=control.returncode==0
    for name,before,after,test in MUTATIONS:
        if not control_ok or original.count(before)!=1:
            rows.append(dict(mutation=name,test=test,status='not_run',reason='control_or_source_anchor_failed'))
            continue
        with tempfile.TemporaryDirectory(prefix='mutant-',dir=out) as temp:
            trial=Path(temp)/'source'
            shutil.copytree(ROOT,trial,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','build','dist','.git','*.egg-info'))
            (trial/REL).write_text(original.replace(before,after,1))
            try:
                execution=subprocess.run([sys.executable,'-m','pytest','-q',test],cwd=trial,
                                         capture_output=True,text=True,timeout=120)
                killed=execution.returncode==1 and ('FAILED '+test) in execution.stdout
                status='killed' if killed else 'survived_or_invalid_execution'
                rows.append(dict(mutation=name,test=test,status=status,returncode=execution.returncode))
            except subprocess.TimeoutExpired:
                rows.append(dict(mutation=name,test=test,status='timeout'))
    result=dict(status='passed' if control_ok and all(r['status']=='killed' for r in rows) else 'failed',
                classification='synthetic_mutation_qualification',control_passed=control_ok,
                scheduled_mutations=len(MUTATIONS),killed_mutations=sum(r['status']=='killed' for r in rows),
                source_sha256=hashlib.sha256(original.encode()).hexdigest(),results=rows,
                independent_corpus_qualified=False,external_review_performed=False)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result));return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
