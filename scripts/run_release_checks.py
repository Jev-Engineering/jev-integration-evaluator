"""Release check runner: regenerates validation examples and tests generated code only; no model/network calls."""
from pathlib import Path
import sys,json,time,copy,importlib.util,importlib.metadata,subprocess,platform
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.reports import write_reports
from jev_integration_evaluator.io import read_json,read_jsonl,write_json,digest,file_hash
from jev_integration_evaluator.statistics import compare_runs,ablation_analysis,economics,long_horizon
from jev_integration_evaluator.calibration import calibration
from jev_integration_evaluator.client import FixtureClient
from jev_integration_evaluator.replay import replay_decisions
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.optimizer import optimize
from jev_integration_evaluator.implementation import scaffold_integration
from jev_integration_evaluator.traceability import link_artifact
cfg=load_config();cfg['validation']['bootstrap_samples']=2000;cfg['validation']['bayesian_samples']=5000
out=R/'validation';out.mkdir(exist_ok=True)
# Remove exploratory output; final examples are reproducible from the release scripts.
import shutil
for name in ('initial-scan','offline-runtime'):
 shutil.rmtree(out/name,ignore_errors=True)
scans={}
for name in ('coding-agent','rag-system','graph-system','generic-service','polyglot'):
 s=scan_repo(R/'examples'/name,cfg);scans[name]=s
 write_reports(s,out/'examples'/name,cfg)
write_json(out/'example-scan-summary.json',{name:{'candidate_count':len(s['candidates']),'patterns':sorted({c['pattern'] for c in s['candidates']}),'tier_counts':{str(t):sum(c['tier']==t for c in s['candidates']) for t in range(4)},'parser_counts':s['coverage']['parser_counts'],'warnings':s['coverage']['warnings'],'scan_fingerprint':s['scan_fingerprint']} for name,s in scans.items()})
base=read_jsonl(R/'examples/research/baseline.jsonl');treatment=read_jsonl(R/'examples/research/router-verifier.jsonl')
result=compare_runs(base,treatment,cfg);write_json(out/'synthetic-results.json',result)
write_json(out/'synthetic-calibration.json',calibration(read_jsonl(R/'examples/research/calibration-test.jsonl')))
variants={name:read_jsonl(R/'examples/research'/path) for name,path in read_json(R/'examples/research/variants.json').items()}
write_json(out/'synthetic-ablations.json',ablation_analysis(base,variants,cfg))
write_json(out/'synthetic-replay.json',replay_decisions(read_jsonl(R/'examples/research/decisions.jsonl'),FixtureClient(read_json(R/'examples/research/fixture-responses.json'))))
write_json(out/'economic-arithmetic-check.json',{'evidence_type':'hypothetical_arithmetic_not_live_savings','analysis':economics(.04,.40,.006,fixed_cost=100,volume=20000)})
write_json(out/'long-horizon-example.json',long_horizon(.99,100))
# Deliberately disclosed synthetic optimization scenario using actual example source seams.
reviewed=copy.deepcopy(scans['coding-agent']);reviews={}
for c in reviewed['candidates']:
 if c['source']['symbol']=='dispatch_once' and c['pattern'] in ('A','C','E'):
  reviews[c['candidate_id']]={'source_sha256':c['source']['source_sha256'],'reviewer':'synthetic-scenario-demonstration','reason':'Read the injectable fixture: model output reaches a registered executor and only an exit code is checked. Resource/benefit figures below are SYNTHETIC assumptions to demonstrate constrained selection, not model measurements.','approved':True,'estimates':{'quality_gain':.15,'reliability_gain':.1,'failure_reduction':.08,'model_call_reduction':.5,'added_latency_ms':40,'added_cost':.0008,'calls_per_task':1,'complexity':.5,'maintenance':.02,'false_positive_rate':.003,'false_negative_rate':.02,'risk':.05,'throughput':50,'provenance':'SYNTHETIC per-task scenario: USD; milliseconds; hypothetical gains, not a live JEV experiment.'}}
write_json(R/'examples/research/synthetic-reviews.json',reviews)
apply_reviews(reviewed,reviews,cfg)
write_json(out/'synthetic-reviewed-inventory.json',reviewed)
write_json(out/'synthetic-placement-sets.json',optimize(reviewed,cfg['constraints']))
# Generate executable integration artifact, link it and a test/outcome receipt. Host wiring is explicit, not claimed.
c=next(c for c in reviewed['candidates'] if c['candidate_id'] in reviews and c['pattern']=='A')
adapterdir=out/'generated-adapter';shutil.rmtree(adapterdir,ignore_errors=True)
manifest=scaffold_integration(reviewed,c['candidate_id'],adapterdir)
link_artifact(reviewed,c['candidate_id'],'implementation',adapterdir/'integration-manifest.json')
# This smoke test runs only the generated adapter against a MustNotCall fixture.
env={**__import__('os').environ,'PYTHONPATH':str(R)+__import__('os').pathsep+str(adapterdir)}
test=subprocess.run([sys.executable,'-m','pytest','-q','test_adapter.py'],cwd=adapterdir,env=env,capture_output=True,text=True,timeout=30)
(out/'generated-adapter-test.txt').write_text(test.stdout+test.stderr)
if test.returncode:raise RuntimeError('Generated adapter smoke test failed')
receipt={'candidate_id':c['candidate_id'],'source_sha256':c['source']['source_sha256'],'experiment_id':c['recommended_experiment']['id'],'test_id':'generated-adapter-default-off','status':'passed','command':'python -m pytest -q test_adapter.py','evidence_type':'synthetic','summary':'One generated default-off contract test passed; no host callsite wiring or live JEV assessment.'}
write_json(out/'adapter-test-receipt.json',receipt);link_artifact(reviewed,c['candidate_id'],'test',out/'adapter-test-receipt.json')
write_json(out/'synthetic-outcome-receipt.json',{'candidate_id':c['candidate_id'],'source_sha256':c['source']['source_sha256'],'experiment_id':c['recommended_experiment']['id'],'result':result})
link_artifact(reviewed,c['candidate_id'],'outcome',out/'synthetic-outcome-receipt.json')
write_json(out/'linked-synthetic-inventory.json',reviewed)
# Unfamiliar installed third-party source smoke; no importing/running target modules.
smokes=[]
for name in ('click','httpx'):
 spec=importlib.util.find_spec(name)
 if spec is None or spec.origin is None:continue
 source=Path(spec.origin).parent
 started=time.monotonic();scan=scan_repo(source,cfg);elapsed=time.monotonic()-started
 smokes.append({'package':name,'installed_version':importlib.metadata.version(name),'target':'installed third-party source tree, read-only; no target import/test/network','files_analyzed':scan['coverage']['files_analyzed'],'symbols':scan['coverage']['symbols'],'parser_counts':scan['coverage']['parser_counts'],'candidate_count':len(scan['candidates']),'tier_counts':{str(t):sum(c['tier']==t for c in scan['candidates']) for t in range(4)},'truncated':scan['coverage']['truncated'],'warnings':scan['coverage']['warnings'],'scan_fingerprint':scan['scan_fingerprint'],'elapsed_seconds':round(elapsed,3),'semantic_accuracy_validated':False,'all_original_third_party_source_excluded_from_package':True})
write_json(out/'third-party-source-smoke.json',smokes)
print(json.dumps({'patterns':sorted({c['pattern'] for s in scans.values() for c in s['candidates']}),'smoke':smokes,'synthetic_optimization':read_json(out/'synthetic-placement-sets.json')['recommended_balanced_set'],'synthetic_ablation_interaction':read_json(out/'synthetic-ablations.json')['router_verifier_interaction']['difference_in_differences']},indent=2))
