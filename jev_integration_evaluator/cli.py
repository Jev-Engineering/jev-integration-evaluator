"""Executable workflow for scanning, review, evaluation, and approved local changes."""
from __future__ import annotations
import argparse
import csv
import io
import json
import sys
from pathlib import Path
from .config import load_config
from . import __version__
from .io import InputError, atomic_text, read_json, read_jsonl, write_json


def _records(path):
    return read_jsonl(path) if str(path).endswith(".jsonl") else read_json(path)


def _save(path, value):
    if path: write_json(path,value)
    return value


def parser():
    p=argparse.ArgumentParser(prog="jev-integration-evaluator",description="Find and validate high-leverage JEV decision boundaries; local-only by default.")
    p.add_argument("--version",action="version",version="jev-integration-evaluator "+__version__)
    sub=p.add_subparsers(dest="command",required=True)
    def common(name,help):
        q=sub.add_parser(name,help=help); q.add_argument("--config"); return q
    s=common("scan","Scan source and generate all analysis artifacts")
    s.add_argument("--repo",required=True); s.add_argument("--out",required=True)
    s.add_argument("--depth",choices=["QUICK","STANDARD","RESEARCH"]); s.add_argument("--traces"); s.add_argument("--reviews")
    s=common("architecture","Build architecture artifacts using the same source analyzer")
    s.add_argument("--repo",required=True); s.add_argument("--out",required=True)
    s=common("onboard","Reuse repository facts and ask only missing intake fields")
    s.add_argument("--inventory",required=True); s.add_argument("--answers"); s.add_argument("--mode",choices=["analysis","implementation"],default="analysis"); s.add_argument("--out")
    s=common("score","Apply evidence-backed review overrides and regenerate scores")
    s.add_argument("--inventory",required=True); s.add_argument("--reviews",required=True); s.add_argument("--out",required=True)
    s=common("report","Regenerate human/machine reports from a saved inventory")
    s.add_argument("--inventory",required=True); s.add_argument("--results"); s.add_argument("--out",required=True)
    s=common("optimize","Choose constrained placement sets; unknown estimates block admission")
    s.add_argument("--inventory",required=True); s.add_argument("--out",required=True); s.add_argument("--exact-limit",type=int,default=18); s.add_argument("--beam-width",type=int,default=512)
    s=common("compare","Paired task/episode evaluation with clustered uncertainty")
    s.add_argument("--baseline",required=True); s.add_argument("--jev",required=True); s.add_argument("--out",required=True)
    s=common("calibrate","Probability calibration and confidence diagnostics")
    s.add_argument("--input",required=True); s.add_argument("--out",required=True); s.add_argument("--bins",type=int,default=10); s.add_argument("--plot"); s.add_argument("--select-threshold",action="store_true")
    s=common("failures","Paired failure-class transitions")
    s.add_argument("--baseline",required=True); s.add_argument("--jev",required=True); s.add_argument("--out",required=True)
    s=common("ablate","Compare task-matched treatment arms and router/verifier interaction")
    s.add_argument("--baseline",required=True); s.add_argument("--variants",required=True,help="JSON map of variant names to run-file paths, relative to the map file"); s.add_argument("--out",required=True)
    s=common("pareto","Point-estimate Pareto front of measured configurations")
    s.add_argument("--input",required=True); s.add_argument("--directions",required=True,help='JSON, e.g. {"quality":"max","cost":"min"}'); s.add_argument("--out",required=True)
    s=common("economics","Engineering expected-value and break-even calculation")
    for name,default in (("failure-reduction",None),("failure-cost",None),("added-cost",None),("fixed-cost",0),("maintenance-per-task",0),("additional-savings",0)):
        s.add_argument("--"+name,type=float,default=default,required=default is None)
    s.add_argument("--volume",type=int); s.add_argument("--out")
    s=common("horizon","Explicitly approximate long-horizon reliability and dependence bounds")
    s.add_argument("--p",type=float,required=True); s.add_argument("--steps",type=int,required=True); s.add_argument("--out")
    s=common("replay","Replay typed decisions from exact offline fixtures or an approved API")
    s.add_argument("--input",required=True); s.add_argument("--fixtures"); s.add_argument("--allow-network",action="store_true"); s.add_argument("--out",required=True)
    s.add_argument("--max-calls",type=int,default=5); s.add_argument("--max-total-cost",type=float,default=.01); s.add_argument("--cost-upper-bound-per-call",type=float)
    s=common("cache","Analyze recorded cache metrics")
    s.add_argument("--input",required=True); s.add_argument("--out",required=True)
    s=common("verify-log","Verify hash-chain integrity; authenticity is a separate concern")
    s.add_argument("--input",required=True); s.add_argument("--out")
    s.add_argument("--expected-final-hash"); s.add_argument("--expected-events",type=int)
    s=common("rollback-check","Evaluate measured canary rollback limits")
    s.add_argument("--window",required=True); s.add_argument("--limits",required=True); s.add_argument("--out")
    s=common("scaffold","Generate an executable proposal adapter; does not wire host code")
    s.add_argument("--inventory",required=True); s.add_argument("--candidate",required=True); s.add_argument("--out",required=True)
    s=common("patch-plan","Create an exact-content local patch for review, without changing the target")
    s.add_argument("--repo",required=True); s.add_argument("--changes",required=True); s.add_argument("--candidate",action="append",required=True); s.add_argument("--out",required=True)
    s=common("apply","Apply only an explicitly approved content-hashed patch plan")
    s.add_argument("--repo",required=True); s.add_argument("--plan",required=True); s.add_argument("--approve",required=True); s.add_argument("--out")
    s=common("worktree","Create an authorized scoped Git worktree")
    s.add_argument("--repo",required=True); s.add_argument("--destination",required=True); s.add_argument("--branch",required=True); s.add_argument("--approve-create",action="store_true")
    s=common("run-tests","Execute target tests only with separate execution authorization")
    s.add_argument("--repo",required=True); s.add_argument("--approve-execution",action="store_true"); s.add_argument("--timeout",type=int,default=120); s.add_argument("--out"); s.add_argument("argv",nargs=argparse.REMAINDER)
    s=common("link","Link a source-matched implementation, test, or outcome artifact")
    s.add_argument("--inventory",required=True);s.add_argument("--candidate",required=True);s.add_argument("--kind",choices=["implementation","test","outcome"],required=True)
    s.add_argument("--artifact",required=True);s.add_argument("--out",required=True)
    s=common("validate","Validate JSON/YAML against bundled schemas")
    s.add_argument("--kind",required=True,choices=[p.name.removesuffix(".schema.json") for p in sorted((Path(__file__).parent/"data").glob("*.schema.json"))])
    s.add_argument("--input",required=True)
    s=common("diff","Compare source snapshots without inheriting stale approvals")
    s.add_argument("--before",required=True); s.add_argument("--after",required=True); s.add_argument("--out",required=True)
    s.add_argument("--allow-repository-mismatch",action="store_true")
    s=common("study-freeze","Freeze a disjoint schedule, versions, metrics and analysis settings before collection")
    s.add_argument("--spec",required=True); s.add_argument("--out",required=True); s.add_argument("--inventory")
    for name in ("study-check","study-evaluate"):
        s=common(name,"Check every scheduled paired outcome against the frozen study")
        s.add_argument("--plan",required=True); s.add_argument("--baseline",required=True); s.add_argument("--jev",required=True)
        s.add_argument("--expected-digest"); s.add_argument("--out",required=True)
        s.add_argument("--inventory")
        if name=="study-evaluate":
            s.add_argument("--holdout-report"); s.add_argument("--gate-bundle")
            s.add_argument("--enforce",action="store_true",help="Exit 3 unless the frozen study supports keep; this does not authorize deployment")
    s=common("threshold-freeze","Freeze a chosen acceptance gate and untouched holdout schedule")
    s.add_argument("--input",required=True); s.add_argument("--spec",required=True); s.add_argument("--out",required=True)
    s=common("threshold-check","Evaluate exact held-out selective-risk bounds without threshold tuning")
    s.add_argument("--input",required=True); s.add_argument("--plan",required=True); s.add_argument("--out",required=True)
    s.add_argument("--expected-digest"); s.add_argument("--enforce",action="store_true",help="Exit 3 unless observed held-out evidence passes")
    s=common("rubric-lint","Check bounded-question contracts, duplicates and ambiguous rubric leads")
    s.add_argument("--input",required=True); s.add_argument("--out",required=True)
    s=common("robustness-plan","Generate five order/label/test-retest probes; no model call")
    s.add_argument("--input",required=True,help="JSON with state, questions, primary_question, optional model/ground_truth")
    s.add_argument("--out",required=True)
    s=common("robustness-run","Run a whole probe schedule with explicit call/cost/egress limits")
    s.add_argument("--plan",required=True); s.add_argument("--fixtures"); s.add_argument("--allow-network",action="store_true")
    s.add_argument("--max-calls",type=int,default=5); s.add_argument("--max-total-cost",type=float,default=.01)
    s.add_argument("--cost-upper-bound-per-call",type=float); s.add_argument("--out",required=True)
    s=common("robustness-report","Analyze separately recorded probe responses with exact request matching")
    s.add_argument("--plan",required=True); s.add_argument("--input",required=True); s.add_argument("--out",required=True)
    s=common("optimize-robust","Choose placements feasible under every declared scenario")
    s.add_argument("--inventory",required=True); s.add_argument("--spec",required=True); s.add_argument("--out",required=True)
    s.add_argument("--exact-limit",type=int,default=16); s.add_argument("--beam-width",type=int,default=256)
    s=common("monitor-freeze","Freeze canary task assignments, reference mix and operational guardrails")
    s.add_argument("--spec",required=True); s.add_argument("--out",required=True)
    s=common("monitor-check","Check every scheduled canary outcome; no exposure expansion")
    s.add_argument("--plan",required=True); s.add_argument("--input",required=True); s.add_argument("--out",required=True)
    s.add_argument("--expected-digest"); s.add_argument("--as-of",help="Explicit UTC evaluation time for reproducible offline replay")
    s.add_argument("--enforce",action="store_true",help="Exit 3 unless observed, pinned, complete and fresh monitoring passes")
    return p


def execute(args):
    cfg=load_config(getattr(args,"config",None)); cmd=args.command
    if cmd in ("scan","architecture"):
        from .scanner import scan_repo
        from .reports import write_reports
        if getattr(args,"depth",None): cfg["depth"]=args.depth
        # Report roots are user-supplied; scan metadata never executes target code.
        cfg["repository"]["root"]=str(Path(args.repo).resolve())
        scan=scan_repo(args.repo,cfg)
        if getattr(args,"traces",None):
            from .traces import correlate_traces
            correlate_traces(scan,_records(args.traces),cfg)
        if getattr(args,"reviews",None):
            from .scoring import apply_reviews
            apply_reviews(scan,read_json(args.reviews),cfg)
        return write_reports(scan,args.out,cfg)
    if cmd=="onboard":
        from .onboarding import onboard
        return _save(args.out,onboard(read_json(args.inventory),read_json(args.answers) if args.answers else None,args.mode))
    if cmd=="score":
        from .scoring import apply_reviews
        return _save(args.out,apply_reviews(read_json(args.inventory),read_json(args.reviews),cfg))
    if cmd=="report":
        from .reports import write_reports
        return write_reports(read_json(args.inventory),args.out,cfg,read_json(args.results) if args.results else None)
    if cmd=="optimize":
        from .optimizer import optimize
        return _save(args.out,optimize(read_json(args.inventory),cfg["constraints"],args.exact_limit,args.beam_width))
    if cmd=="compare":
        from .statistics import compare_runs
        return _save(args.out,compare_runs(_records(args.baseline),_records(args.jev),cfg))
    if cmd=="failures":
        from .statistics import paired_records,failure_transitions
        return _save(args.out,failure_transitions(paired_records(_records(args.baseline),_records(args.jev))))
    if cmd=="calibrate":
        from .calibration import calibration,select_threshold
        rows=_records(args.input); result=calibration(rows,args.bins)
        if args.select_threshold: result["threshold_selection"]=select_threshold(rows)
        _save(args.out,result)
        table=io.StringIO(); w=csv.DictWriter(table,fieldnames=list(result["bins"][0])); w.writeheader(); w.writerows(result["bins"])
        atomic_text(Path(args.out).with_suffix(".bins.csv"),table.getvalue())
        if args.plot:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            nonempty=[b for b in result["bins"] if b["count"]]
            fig,ax=plt.subplots(figsize=(6,5))
            ax.plot([0,1],[0,1],linestyle="--",label="Ideal probability calibration")
            ax.plot([b["mean_probability"] for b in nonempty],[b["empirical_rate"] for b in nonempty],marker="o",label="Observed bins")
            ax.set(xlabel="Mean predicted probability",ylabel="Empirical event rate",xlim=(0,1),ylim=(0,1),title="Held-out probability reliability")
            ax.legend(); fig.tight_layout(); fig.savefig(args.plot,dpi=160); plt.close(fig)
        return result
    if cmd=="ablate":
        from .statistics import ablation_analysis
        paths=read_json(args.variants); base=Path(args.variants).resolve().parent
        variants={k:_records(base/v) for k,v in paths.items()}
        return _save(args.out,ablation_analysis(_records(args.baseline),variants,cfg))
    if cmd=="pareto":
        from .optimizer import pareto_front
        from .io import loads
        return _save(args.out,pareto_front(_records(args.input),loads(args.directions)))
    if cmd=="economics":
        from .statistics import economics
        return _save(args.out,economics(args.failure_reduction,args.failure_cost,args.added_cost,args.fixed_cost,args.maintenance_per_task,args.additional_savings,args.volume))
    if cmd=="horizon":
        from .statistics import long_horizon
        return _save(args.out,long_horizon(args.p,args.steps))
    if cmd=="replay":
        from .client import FixtureClient,TypeSafeHTTPClient
        from .replay import replay_decisions
        if args.fixtures and args.allow_network: raise InputError("Select fixtures or network, not both")
        if not args.fixtures and not args.allow_network: raise InputError("Supply offline fixtures or explicitly allow network")
        client=FixtureClient(read_json(args.fixtures)) if args.fixtures else TypeSafeHTTPClient(allow_network=True)
        return _save(args.out,replay_decisions(_records(args.input),client,cfg["runtime"]["model"],cfg["runtime"]["timeout_ms"],max_calls=args.max_calls,max_total_cost=args.max_total_cost,cost_upper_bound_per_call=args.cost_upper_bound_per_call))
    if cmd=="cache":
        from .traces import cache_analysis
        return _save(args.out,cache_analysis(_records(args.input)))
    if cmd=="verify-log":
        from .traces import verify_log
        return _save(args.out,verify_log(_records(args.input),expected_final_hash=args.expected_final_hash,expected_events=args.expected_events))
    if cmd=="rollback-check":
        from .runtime import rollback_check
        return _save(args.out,rollback_check(read_json(args.window),read_json(args.limits)))
    if cmd=="scaffold":
        from .implementation import scaffold_integration
        return scaffold_integration(read_json(args.inventory),args.candidate,args.out)
    if cmd=="patch-plan":
        from .implementation import make_patch_plan
        return _save(args.out,make_patch_plan(args.repo,read_json(args.changes),args.candidate))
    if cmd=="apply":
        from .implementation import apply_patch_plan
        return _save(args.out,apply_patch_plan(args.repo,read_json(args.plan),args.approve))
    if cmd=="worktree":
        from .implementation import prepare_worktree
        return prepare_worktree(args.repo,args.destination,args.branch,args.approve_create)
    if cmd=="run-tests":
        from .implementation import run_authorized_tests
        argv=args.argv[1:] if args.argv[:1]==["--"] else args.argv
        return _save(args.out,run_authorized_tests(args.repo,argv,approve_execution=args.approve_execution,timeout_s=args.timeout))
    if cmd=="link":
        from .traceability import link_artifact
        return _save(args.out,link_artifact(read_json(args.inventory),args.candidate,args.kind,args.artifact))
    if cmd=="validate":
        import jsonschema
        schema=read_json(Path(__file__).parent/"data"/(args.kind+".schema.json"))
        if args.kind=="config": data={"jev_analysis":load_config(args.input)}
        else: data=_records(args.input)
        rows=data if isinstance(data,list) and args.kind in ("run","decision","trace","opportunity","monitor-outcome","deployment-gate") else [data]
        for row in rows: jsonschema.Draft202012Validator(schema).validate(row)
        return {"status":"valid","kind":args.kind,"records":len(rows)}
    if cmd=="diff":
        from .lifecycle import compare_snapshots, render_change_report
        result=compare_snapshots(read_json(args.before),read_json(args.after),allow_repository_mismatch=args.allow_repository_mismatch)
        _save(args.out,result)
        atomic_text(Path(args.out).with_suffix(".report.md"),render_change_report(result))
        return result
    if cmd=="study-freeze":
        from .study import freeze_study
        return _save(args.out,freeze_study(read_json(args.spec),cfg,inventory=read_json(args.inventory) if args.inventory else None))
    if cmd in ("study-check","study-evaluate"):
        from .study import validate_study,evaluate_study
        options={"expected_digest":args.expected_digest,"inventory":read_json(args.inventory) if args.inventory else None}
        if cmd=="study-evaluate":
            options["holdout_report"]=read_json(args.holdout_report) if args.holdout_report else None
            options["gate_bundle"]=read_json(args.gate_bundle) if args.gate_bundle else None
        function=evaluate_study if cmd=="study-evaluate" else validate_study
        return _save(args.out,function(read_json(args.plan),_records(args.baseline),_records(args.jev),**options))
    if cmd=="threshold-freeze":
        from .holdout import freeze_threshold
        return _save(args.out,freeze_threshold(_records(args.input),read_json(args.spec)))
    if cmd=="threshold-check":
        from .holdout import validate_holdout, render_holdout_report
        result=validate_holdout(read_json(args.plan),_records(args.input),expected_digest=args.expected_digest)
        _save(args.out,result)
        atomic_text(Path(args.out).with_suffix(".report.md"),render_holdout_report(result))
        return result
    if cmd=="rubric-lint":
        from .robustness import lint_questions
        return _save(args.out,lint_questions(read_json(args.input)))
    if cmd=="robustness-plan":
        from .robustness import make_robustness_suite
        event=read_json(args.input)
        return _save(args.out,make_robustness_suite(event["state"],event["questions"],event["primary_question"],event.get("model",cfg["runtime"]["model"]),truth=event.get("ground_truth")))
    if cmd=="robustness-run":
        from .robustness import run_robustness
        from .client import FixtureClient,TypeSafeHTTPClient
        if bool(args.fixtures)==bool(args.allow_network): raise InputError("Select exactly one of offline fixtures or explicit network egress")
        client=FixtureClient(read_json(args.fixtures),order_sensitive=True) if args.fixtures else TypeSafeHTTPClient(allow_network=True)
        return _save(args.out,run_robustness(read_json(args.plan),client,max_calls=args.max_calls,max_total_cost=args.max_total_cost,cost_upper_bound_per_call=args.cost_upper_bound_per_call,timeout_ms=cfg["runtime"]["timeout_ms"]))
    if cmd=="robustness-report":
        from .robustness import evaluate_probe_results
        return _save(args.out,evaluate_probe_results(read_json(args.plan),_records(args.input)))
    if cmd=="optimize-robust":
        from .scenarios import robust_optimize, render_scenarios
        result=robust_optimize(read_json(args.inventory),read_json(args.spec),cfg["constraints"],exact_limit=args.exact_limit,beam_width=args.beam_width)
        _save(args.out,result); atomic_text(Path(args.out).with_suffix(".report.md"),render_scenarios(result))
        return result
    if cmd=="monitor-freeze":
        from .monitoring import freeze_monitor
        return _save(args.out,freeze_monitor(read_json(args.spec)))
    if cmd=="monitor-check":
        from .monitoring import evaluate_monitor, render_monitor
        result=evaluate_monitor(read_json(args.plan),_records(args.input),expected_digest=args.expected_digest,as_of=args.as_of)
        _save(args.out,result); atomic_text(Path(args.out).with_suffix(".report.md"),render_monitor(result))
        return result
    raise InputError("Unknown command")


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        result=execute(args)
        # Artifacts contain details; concise stdout remains useful in scripts.
        if getattr(args,"out",None) and args.command not in ("scan","architecture","report","scaffold"):
            display={"status":"written","output":args.out}
            if isinstance(result,dict):
                for k in ("recommendation","pair_count","evidence_type","status"): 
                    if k in result: display[k]=result[k]
        else: display=result
        print(json.dumps(display,indent=2,allow_nan=False))
        if getattr(args,"enforce",False):
            passed=(result.get("recommendation")=="keep" if args.command=="study-evaluate" else
                    result.get("eligible_for_continued_canary") is True if args.command=="monitor-check" else
                    result.get("eligible_for_activation") is True)
            if not passed: return 3
        return 0
    except (InputError,ValueError,KeyError,TypeError,OSError) as exc:
        # Input errors include only invariant names and paths, never request bodies or credentials.
        print(json.dumps({"error":type(exc).__name__,"message":str(exc)}),file=sys.stderr)
        return 2
    except Exception as exc:
        # jsonschema validation errors may embed sensitive instance content; do not print it.
        print(json.dumps({"error":type(exc).__name__,"message":"Operation failed; inspect the local input/schema without sharing secrets"}),file=sys.stderr)
        return 2
