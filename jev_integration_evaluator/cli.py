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
from .io import InputError, atomic_text, digest, read_json, read_jsonl, write_json


_NODE_RECOVERY_ACTIONS = ('node-package-recovery-plan', 'node-package-recover',
                          'node-install-recovery-plan', 'node-install-recover')


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
    from .repository_discovery import add_arguments as discovery_arguments
    discovery_arguments(sub.add_parser("repository-discovery",help="Discover, prepare an inventory and apply semantic review without target execution"))
    sub.add_parser("repository-placement", help="Review complete source scope and select experimental placements without execution")
    sub.add_parser("repository-run", help="Inspect a repository or resume an explicitly scoped implementation session")
    for name, description in (
        ("discover-capabilities", "Discover bounded source capabilities without executing target code"),
        ("nominate-candidate", "Admit a source-anchored nomination; semantic and binding review remain pending"),
    ):
        s=sub.add_parser(name,help=description)
        s.add_argument("--repo",required=True); s.add_argument("--out",required=True)
        s.add_argument("--policy",help="External discovery policy; target configuration is not executed")
        if name=="nominate-candidate":
            s.add_argument("--nomination",required=True)
            s.add_argument("--report-sha256",required=True)
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
    s=common("observed-link","Freeze a source-bound implementation/study identity; no collection or activation")
    s.add_argument("--repo",required=True);s.add_argument("--bundle",required=True)
    s.add_argument("--study",required=True);s.add_argument("--placement-set",required=True)
    s.add_argument("--study-digest",required=True);s.add_argument("--placement-digest",required=True)
    s.add_argument("--receipt-sha256",required=True);s.add_argument("--out",required=True)
    s.add_argument("--monitor-plan");s.add_argument("--monitor-digest")
    for name, description in (
        ("observed-check", "Recheck a frozen implementation/study link against current source"),
        ("observed-collect-offline", "Collect only approved synthetic paired fixtures with independent labels"),
        ("observed-evaluate", "Recompute a linked study and raw gate evidence without activation"),
    ):
        s=common(name,description)
        s.add_argument("--repo",required=True);s.add_argument("--bundle",required=True)
        s.add_argument("--study",required=True);s.add_argument("--placement-set",required=True)
        s.add_argument("--link",required=True);s.add_argument("--link-digest",required=True)
        s.add_argument("--receipt-sha256",required=True);s.add_argument("--out",required=True)
        s.add_argument("--monitor-plan")
        if name=="observed-collect-offline":
            s.add_argument("--request",required=True);s.add_argument("--fixtures",required=True)
            s.add_argument("--labels",required=True);s.add_argument("--approve-request",required=True)
        if name=="observed-evaluate":
            s.add_argument("--collection",required=True);s.add_argument("--collection-digest",required=True)
            s.add_argument("--gate-bundle");s.add_argument("--holdout-report")
            s.add_argument("--holdout-plan");s.add_argument("--holdout-rows")
            s.add_argument("--monitor-rows");s.add_argument("--monitor-as-of")
    s=common("implementation-recipes", "List executable bounded Python recipes and unsupported shapes")
    s.add_argument("--json",action="store_true",help="Machine-readable catalog (also the default)")
    s=sub.add_parser('template', help='Inspect and render packaged source-bound integration templates')
    template_sub=s.add_subparsers(dest='template_action',required=True)
    template_sub.add_parser('list',help='List packaged template versions').add_argument('--json',action='store_true')
    s=template_sub.add_parser('inspect',help='Inspect the versioned manifest and lifecycle matrix')
    s.add_argument('template_id'); s.add_argument('--version',default='1.0.0')
    for action in ('validate','materialize'):
        s=template_sub.add_parser(action,help='Validate current source and strict template parameters' if action=='validate' else 'Create exclusive external planner inputs without changing the host')
        s.add_argument('--repo',required=True); s.add_argument('--request',required=True)
        s.add_argument('--tooling',help='External trusted Node and TypeScript directory for JS recipe C')
        if action=='materialize': s.add_argument('--out',required=True)
    s=template_sub.add_parser('bind',help='Derive reviewed Python console bindings without editing the host')
    s.add_argument('--repo',required=True); s.add_argument('--request',required=True)
    s.add_argument('--binding',required=True); s.add_argument('--out',required=True)
    s=template_sub.add_parser('package',help='Plan offline packaging of an already applied and verified Python host')
    s.add_argument('--request',required=True); s.add_argument('--out',required=True)
    s=template_sub.add_parser('package-build',help='Run explicitly approved offline PEP 517 build')
    s.add_argument('--plan',required=True); s.add_argument('--approve-plan-sha256',required=True)
    s=template_sub.add_parser('package-status',help='Inspect an owned package generation without building')
    s.add_argument('--plan',required=True)
    s=template_sub.add_parser('install-plan',help='Plan an owned offline environment from a built wheel')
    s.add_argument('--package-plan',required=True); s.add_argument('--package-receipt',required=True); s.add_argument('--out',required=True)
    s=template_sub.add_parser('connected-installed-bind',help='Derive a read-only source-to-installed binding from anchored receipts')
    s.add_argument('--package-plan',required=True); s.add_argument('--package-receipt',required=True)
    s.add_argument('--install-plan',required=True); s.add_argument('--install-receipt',required=True)
    s.add_argument('--trusted-package-receipt-sha256',required=True)
    s.add_argument('--trusted-install-receipt-sha256',required=True); s.add_argument('--out',required=True)
    s=template_sub.add_parser('connected-composite-installed-bind',help='Derive exact installed origins for reviewed composite Python placements')
    s.add_argument('--package-plan',required=True); s.add_argument('--package-receipt',required=True)
    s.add_argument('--install-plan',required=True); s.add_argument('--install-receipt',required=True)
    s.add_argument('--trusted-package-receipt-sha256',required=True)
    s.add_argument('--trusted-install-receipt-sha256',required=True); s.add_argument('--out',required=True)
    for action in ('install','install-status','install-recover'):
        s=template_sub.add_parser(action,help='Install, inspect, or explicitly recover one owned environment')
        s.add_argument('--plan',required=True)
        if action!='install-status': s.add_argument('--approve-plan-sha256',required=True)
        if action=='install-recover': s.add_argument('--approve-generation-sha256')
    s=template_sub.add_parser('package-recover',help='Adopt a verified wheel or remove an independently inspected partial build')
    s.add_argument('--plan',required=True); s.add_argument('--approve-plan-sha256',required=True)
    s.add_argument('--approve-generation-sha256')
    s=template_sub.add_parser('delivery-plan',help='Bind a verified installed console and independent observation schedule')
    s.add_argument('--install-plan',required=True); s.add_argument('--trusted-install-receipt-sha256',required=True)
    s.add_argument('--observation',required=True); s.add_argument('--launch-environment')
    s.add_argument('--out',required=True)
    s=template_sub.add_parser('connected-plan',help='Bind a registered installed console to exact connected shadow references')
    s.add_argument('--install-plan',required=True); s.add_argument('--trusted-install-receipt-sha256',required=True)
    s.add_argument('--trusted-package-receipt-sha256',required=True)
    s.add_argument('--installed-binding',required=True); s.add_argument('--trusted-binding-sha256',required=True)
    s.add_argument('--observation',required=True); s.add_argument('--launch-environment',required=True)
    s.add_argument('--host-profile',choices=['retrieval-d-v1','completion-e-v1','graph-l-v1','registered-dual-connected-v1','retention-h-v1','claim-m-v1'],
                   help='Omit for the legacy registered Alpha profile')
    s.add_argument('--out',required=True)
    s=template_sub.add_parser('connected-configure',help='Create one private connected shadow session from an exact plan')
    s.add_argument('--session',required=True); s.add_argument('--plan',required=True)
    s.add_argument('--approve-plan-sha256',required=True)
    for action in ('connected-launch','connected-stop'):
        s=template_sub.add_parser(action,help='Apply one exact expiring connected session scope')
        s.add_argument('--session',required=True); s.add_argument('--scope',required=True)
        s.add_argument('--approve-scope-sha256',required=True)
    for action in ('connected-resume','connected-status'):
        s=template_sub.add_parser(action,help='Reconcile or inspect the exact connected session without replay')
        s.add_argument('--session',required=True)
        s.add_argument('--trusted-session-head',required=action=='connected-resume')
    s=template_sub.add_parser('connected-generation-plan',help='Derive an unsigned stopped generation transfer grant')
    s.add_argument('--old-session',required=True); s.add_argument('--new-plan',required=True)
    s.add_argument('--trusted-old-head',required=True)
    s.add_argument('--old-dependencies',required=True); s.add_argument('--new-dependencies',required=True)
    s.add_argument('--limits',required=True); s.add_argument('--action',choices=['upgrade','rollback'],required=True)
    s.add_argument('--issued-at',required=True); s.add_argument('--expires-at',required=True)
    s.add_argument('--out',required=True)
    for action in ('connected-generation-transfer','connected-generation-status','connected-generation-reconcile'):
        s=template_sub.add_parser(action,help='Transfer or inspect one authenticated stopped connected generation')
        s.add_argument('--old-session',required=True); s.add_argument('--new-session',required=True)
        s.add_argument('--trusted-old-head',required=True); s.add_argument('--grant',required=True)
        s.add_argument('--signature-file',required=True)
        if action=='connected-generation-transfer':
            s.add_argument('--new-plan',required=True); s.add_argument('--approve-new-plan-sha256',required=True)
            s.add_argument('--old-dependencies',required=True); s.add_argument('--new-dependencies',required=True)
    s=template_sub.add_parser('journey-create',help='Start one source-to-runtime delivery run before source application')
    s.add_argument('--session',required=True); s.add_argument('--source-root',required=True)
    s.add_argument('--bundle',required=True); s.add_argument('--source-kind',choices=['single','composite'],default='single')
    s=template_sub.add_parser('journey-record',help='Anchor one verified prerequisite plan or receipt without running effects')
    s.add_argument('--session',required=True); s.add_argument('--trusted-journey-head',required=True)
    s.add_argument('--stage',choices=['baseline_anchored','source_verified','package_planned',
                                     'package_built','install_planned','installed'],required=True)
    s.add_argument('--plan'); s.add_argument('--receipt'); s.add_argument('--trusted-receipt-sha256')
    s=template_sub.add_parser('journey-status',help='Read-only reconciliation of one source-to-runtime run')
    s.add_argument('--session',required=True); s.add_argument('--trusted-journey-head')
    s=template_sub.add_parser('journey-promote',help='Create an off-mode runtime child with the existing run ID')
    s.add_argument('--session',required=True); s.add_argument('--trusted-journey-head',required=True)
    s.add_argument('--observation',required=True); s.add_argument('--launch-environment')
    s=template_sub.add_parser('journey-recover-promotion',help='Complete an exact interrupted pre-launch child creation')
    s.add_argument('--session',required=True); s.add_argument('--trusted-journey-head',required=True)
    s=template_sub.add_parser('deploy',help='Create a private delivery session or launch its exact installed console')
    s.add_argument('--session',required=True); s.add_argument('--plan'); s.add_argument('--scope')
    s.add_argument('--approve-scope-sha256')
    s=template_sub.add_parser('resume',help='Reconcile pending delivery intent without replaying effects')
    s.add_argument('--session',required=True); s.add_argument('--trusted-session-head',required=True)
    s=template_sub.add_parser('status',help='Read current delivery and process state without running the host')
    s.add_argument('--session',required=True); s.add_argument('--trusted-session-head')
    s=template_sub.add_parser('observe',help='Check independently authored host postconditions')
    s.add_argument('--session',required=True); s.add_argument('--trusted-session-head',required=True)
    s=template_sub.add_parser('upgrade',help='Select a new verified owned generation after bounded old stop')
    s.add_argument('--session',required=True); s.add_argument('--plan',required=True)
    s.add_argument('--scope',required=True); s.add_argument('--approve-scope-sha256',required=True)
    for action in ('stop','disable','rollback'):
        s=template_sub.add_parser(action,help='Request bounded drain of the exact owned console process')
        s.add_argument('--session',required=True); s.add_argument('--scope',required=True)
        s.add_argument('--approve-scope-sha256',required=True)
    s=template_sub.add_parser('node-delivery-plan',help='Bind an anchored Node install to exact offline observations')
    s.add_argument('--install-plan',required=True); s.add_argument('--trusted-install-receipt-sha256',required=True)
    s.add_argument('--observation',required=True); s.add_argument('--launch-environment',required=True)
    s.add_argument('--out',required=True)
    s=template_sub.add_parser('node-package-plan',help='Plan offline Node packaging of an applied and verified JS/TS host')
    s.add_argument('--request',required=True); s.add_argument('--out',required=True)
    s=template_sub.add_parser('node-package-build',help='Build one exactly approved offline Node package')
    s.add_argument('--plan',required=True); s.add_argument('--approve-plan-sha256',required=True)
    s=template_sub.add_parser('node-package-status',help='Inspect a Node package without building or replaying')
    s.add_argument('--plan',required=True); s.add_argument('--trusted-receipt-sha256')
    s=template_sub.add_parser('node-install-plan',help='Plan a Node generation from an externally anchored package receipt')
    s.add_argument('--package-plan',required=True); s.add_argument('--package-receipt',required=True)
    s.add_argument('--trusted-package-receipt-sha256',required=True); s.add_argument('--out',required=True)
    s=template_sub.add_parser('node-install',help='Install one exactly approved offline Node generation')
    s.add_argument('--plan',required=True); s.add_argument('--approve-plan-sha256',required=True)
    s=template_sub.add_parser('node-install-status',help='Inspect a Node generation without installing or launching')
    s.add_argument('--plan',required=True); s.add_argument('--trusted-receipt-sha256')
    for action in ('node-package-recovery-plan','node-install-recovery-plan'):
        s=template_sub.add_parser(action,help='Plan removal of one interrupted owned Node output without changing it')
        s.add_argument('--plan',required=True); s.add_argument('--out',required=True)
    for action in ('node-package-recover','node-install-recover'):
        s=template_sub.add_parser(action,help='Remove one exactly approved interrupted owned Node output')
        s.add_argument('--plan',required=True); s.add_argument('--recovery-plan',required=True)
        s.add_argument('--approve-plan-sha256',required=True)
        s.add_argument('--approve-recovery-sha256',required=True)
    s=template_sub.add_parser('node-connected-core',help='Prepare private exact installed scope for separate connected authority')
    s.add_argument('--request',required=True); s.add_argument('--out',required=True)
    s=template_sub.add_parser('node-connected-plan',help='Bind exact connected grants and raw observed gates without launch')
    s.add_argument('--request',required=True); s.add_argument('--out',required=True)
    s=template_sub.add_parser('node-connected-status',help='Recheck a connected descriptor and external anchor without launch')
    s.add_argument('--request',required=True); s.add_argument('--descriptor',required=True)
    s.add_argument('--trusted-descriptor-sha256',required=True)
    s=template_sub.add_parser('node-connected-session-create',help='Create one private connected Node session')
    s.add_argument('--session',required=True); s.add_argument('--request',required=True)
    s.add_argument('--descriptor',required=True); s.add_argument('--trusted-descriptor-sha256',required=True)
    s.add_argument('--observation',required=True); s.add_argument('--launch-environment',required=True)
    for action in ('node-connected-session-launch', 'node-connected-session-stop',
                   'node-connected-session-disable'):
        s=template_sub.add_parser(action,help='Perform one exact connected session action')
        s.add_argument('--session',required=True); s.add_argument('--scope',required=True)
        s.add_argument('--approve-scope-sha256',required=True)
    for action in ('node-connected-session-observe', 'node-connected-session-resume'):
        s=template_sub.add_parser(action,help='Inspect or reconcile an owned connected session')
        s.add_argument('--session',required=True); s.add_argument('--trusted-session-head',required=True)
    s=template_sub.add_parser('node-session-create',help='Create an owned unlaunched Node session')
    s.add_argument('--session',required=True); s.add_argument('--descriptor',required=True)
    for action in ('node-launch','node-stop','node-disable','node-upgrade','node-rollback'):
        s=template_sub.add_parser(action,help='Perform one exact scoped Node session action')
        s.add_argument('--session',required=True); s.add_argument('--scope',required=True)
        s.add_argument('--approve-scope-sha256',required=True)
        if action=='node-upgrade': s.add_argument('--descriptor',required=True)
    for action in ('node-resume','node-observe','node-status'):
        s=template_sub.add_parser(action,help='Read or reconcile owned Node session state')
        s.add_argument('--session',required=True)
        s.add_argument('--trusted-session-head',required=action!='node-status')
    s=common("implement-composite-plan", "Plan one reviewed multi-placement transaction")
    s.add_argument("--repo",required=True); s.add_argument("--inventory",required=True)
    s.add_argument("--selection",required=True); s.add_argument("--specs",required=True); s.add_argument("--out",required=True)
    s=common("implement-composite-verify", "Execute authorized synthetic combined host checks")
    s.add_argument("--phase",choices=["baseline","modified"],required=True)
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--approve-execution",action="store_true"); s.add_argument("--baseline-sha256")
    s=common("implement-composite-apply", "Apply one exact reviewed composite bundle")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--approve",required=True); s.add_argument("--baseline-sha256",required=True)
    s=common("implement-composite-status", "Inspect composite owned bytes and anchored receipt")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--trusted-receipt-sha256")
    s=common("implement-composite-rollback", "Restore only exact composite owned bytes")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True); s.add_argument("--approve",required=True)
    s=common("implement-plan", "Derive a reviewed, default-off host patch without executing or changing the target")
    s.add_argument("--repo",required=True); s.add_argument("--inventory",required=True)
    s.add_argument("--candidate",required=True); s.add_argument("--spec",required=True); s.add_argument("--out",required=True)
    s=common("implement-verify", "Execute separately authorized synthetic host checks and record observed evidence")
    s.add_argument("--phase",choices=["baseline","modified"],required=True)
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--approve-execution",action="store_true")
    s.add_argument("--baseline-sha256",help="Externally retained baseline receipt SHA256; required for modified checks")
    s.add_argument("--out",help="Optional receipt copy outside the target; the private bundle always retains its receipt")
    s=common("implement-apply", "Apply the exact reviewed bundle after independently retained baseline evidence")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--approve",required=True,help="Reviewed implementation bundle digest, not an authorization inferred from a file")
    s.add_argument("--baseline-sha256",required=True)
    s=common("implement-status", "Recompute file/integrity state without executing target code")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--trusted-receipt-sha256",help="Receipt digest from an external trusted verifier, never from an untrusted bundle")
    s=common("implement-rollback", "Restore only matching integration-owned bytes, including interrupted applications")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--approve",required=True,help="Separately reviewed rollback digest returned by status")
    s=common("js-plan", "Prepare a reviewed native JavaScript recipe C bundle without target execution")
    s.add_argument("--repo",required=True); s.add_argument("--spec",required=True)
    s.add_argument("--bundle",required=True); s.add_argument("--tooling",required=True)
    common("js-support", "Report bounded JS/TS A-M support without inspecting a target")
    s=common("js-verify", "Execute an explicitly authorized bounded JS/TS entrypoint schedule")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--tooling",required=True); s.add_argument("--cases",required=True)
    s.add_argument("--phase",choices=["baseline","modified"],required=True)
    s.add_argument("--approve-execution",action="store_true"); s.add_argument("--baseline-sha256")
    s=common("js-apply", "Apply an exact reviewed JS/TS bundle after anchored baseline")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--tooling",required=True); s.add_argument("--approve",required=True)
    s.add_argument("--baseline-sha256",required=True)
    s=common("js-status", "Read-only JS/TS owned file and receipt status")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--tooling",required=True); s.add_argument("--trusted-modified-sha256")
    s=common("js-recover", "Reconcile an interrupted JS/TS phase from exact owned bytes/receipt")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--tooling",required=True); s.add_argument("--operation",choices=["baseline","apply","modified"],required=True)
    s.add_argument("--trusted-receipt-sha256")
    s=common("js-rollback", "Restore only matching JS/TS owned bytes")
    s.add_argument("--repo",required=True); s.add_argument("--bundle",required=True)
    s.add_argument("--tooling",required=True); s.add_argument("--approve",required=True)
    return p


def execute(args):
    cfg=load_config(getattr(args,"config",None)); cmd=args.command
    if cmd=='template':
        from .template_catalog import (list_templates, inspect_template,
                                       validate_template_request, materialize_template, bind_template)
        from .io import write_json
        if args.template_action=='list': return list_templates()
        if args.template_action=='inspect': return inspect_template(args.template_id,args.version)
        if args.template_action in ('validate','materialize'):
            request=read_json(args.request)
            if args.template_action=='validate': return validate_template_request(args.repo,request,tooling_dir=args.tooling)
            return materialize_template(args.repo,request,args.out,tooling_dir=args.tooling)
        if args.template_action=='bind':
            return bind_template(args.repo,read_json(args.request),read_json(args.binding),args.out)
        if args.template_action=='connected-installed-bind':
            from .template_connected_binding import derive_installed_binding
            from .template_installation import write_plan_exclusive
            package_plan=read_json(args.package_plan)
            report=derive_installed_binding(package_plan,read_json(args.package_receipt),
                read_json(args.install_plan),read_json(args.install_receipt),
                trusted_package_receipt_sha256=args.trusted_package_receipt_sha256,
                trusted_install_receipt_sha256=args.trusted_install_receipt_sha256)
            write_plan_exclusive(args.out,report,host_root=package_plan['request']['host_root'])
            return report
        if args.template_action=='connected-composite-installed-bind':
            from .template_connected_composite_binding import derive_installed_composite_binding
            from .template_installation import write_plan_exclusive
            package_plan=read_json(args.package_plan)
            report=derive_installed_composite_binding(package_plan,read_json(args.package_receipt),
                read_json(args.install_plan),read_json(args.install_receipt),
                trusted_package_receipt_sha256=args.trusted_package_receipt_sha256,
                trusted_install_receipt_sha256=args.trusted_install_receipt_sha256)
            write_plan_exclusive(args.out,report,host_root=package_plan['request']['host_root'])
            return report
        if args.template_action.startswith('connected-'):
            if args.template_action.startswith('connected-generation-'):
                from .template_connected_generation import (
                    plan_connected_generation_transfer, transfer_connected_generation,
                    connected_generation_status, reconcile_connected_generation)
                action=args.template_action
                if action=='connected-generation-plan':
                    result=plan_connected_generation_transfer(args.old_session,read_json(args.new_plan),
                        trusted_old_head=args.trusted_old_head,
                        old_dependency_plan=read_json(args.old_dependencies),
                        new_dependency_plan=read_json(args.new_dependencies),
                        limits=read_json(args.limits),action=args.action,
                        issued_at=args.issued_at,expires_at=args.expires_at)
                    from .template_installation import write_plan_exclusive
                    write_plan_exclusive(args.out,result,
                        host_root=read_json(args.new_plan)['off_provenance']['install_plan']['package_plan']['request']['host_root'])
                    return result
                common=dict(grant=read_json(args.grant),signature_file=args.signature_file,
                            trusted_old_head=args.trusted_old_head)
                if action=='connected-generation-transfer':
                    return transfer_connected_generation(args.old_session,args.new_session,
                        read_json(args.new_plan),approved_new_plan_sha256=args.approve_new_plan_sha256,
                        old_dependency_plan=read_json(args.old_dependencies),
                        new_dependency_plan=read_json(args.new_dependencies),**common)
                if action=='connected-generation-reconcile':
                    return reconcile_connected_generation(args.old_session,args.new_session,**common)
                return connected_generation_status(args.old_session,args.new_session,**common)
            from .template_connected_delivery import (
                plan_connected_delivery, create_connected_session, launch_connected_session,
                resume_connected_session, connected_session_status, stop_connected_session)
            action=args.template_action
            if action=='connected-plan':
                result=plan_connected_delivery(read_json(args.install_plan),
                    trusted_install_receipt_sha256=args.trusted_install_receipt_sha256,
                    trusted_package_receipt_sha256=args.trusted_package_receipt_sha256,
                    installed_binding=read_json(args.installed_binding),
                    trusted_binding_sha256=args.trusted_binding_sha256,
                    observation=read_json(args.observation),
                    launch_environment=read_json(args.launch_environment),
                    host_profile=args.host_profile)
                from .template_installation import write_plan_exclusive
                write_plan_exclusive(args.out,result,
                    host_root=result['off_provenance']['install_plan']['package_plan']['request']['host_root'])
                return result
            if action=='connected-configure':
                return create_connected_session(args.session,read_json(args.plan),
                    approved_plan_sha256=args.approve_plan_sha256)
            if action=='connected-launch':
                return launch_connected_session(args.session,scope=read_json(args.scope),
                    approved_scope_sha256=args.approve_scope_sha256)
            if action=='connected-stop':
                return stop_connected_session(args.session,scope=read_json(args.scope),
                    approved_scope_sha256=args.approve_scope_sha256)
            if action=='connected-resume':
                return resume_connected_session(args.session,trusted_session_head=args.trusted_session_head)
            return connected_session_status(args.session,trusted_session_head=args.trusted_session_head)
        if args.template_action.startswith('node-'):
            from .template_node_installation import (
                plan_node_package, build_node_package, package_status as node_package_status,
                plan_node_install, install_node_package, installation_status as node_install_status)
            from .template_installation import write_plan_exclusive
            action=args.template_action
            if action=='node-package-plan':
                result=plan_node_package(read_json(args.request))
                write_plan_exclusive(args.out,result,host_root=result['request']['host_root'])
                return result
            if action=='node-package-build':
                return build_node_package(read_json(args.plan),approved_plan_sha256=args.approve_plan_sha256)
            if action=='node-package-status':
                return node_package_status(read_json(args.plan),trusted_receipt_sha256=args.trusted_receipt_sha256)
            if action=='node-install-plan':
                result=plan_node_install(read_json(args.package_plan),read_json(args.package_receipt),
                    trusted_package_receipt_sha256=args.trusted_package_receipt_sha256)
                write_plan_exclusive(args.out,result,
                    host_root=result['package_plan']['request']['host_root'])
                return result
            if action=='node-install':
                return install_node_package(read_json(args.plan),approved_plan_sha256=args.approve_plan_sha256)
            if action=='node-install-status':
                return node_install_status(read_json(args.plan),trusted_receipt_sha256=args.trusted_receipt_sha256)
            if action in _NODE_RECOVERY_ACTIONS:
                from .template_node_installation import (
                    plan_node_package_recovery, recover_node_package,
                    plan_node_install_recovery, recover_node_installation)
                plan=read_json(args.plan)
                package=action.startswith('node-package-')
                if action.endswith('-recovery-plan'):
                    result=(plan_node_package_recovery if package else plan_node_install_recovery)(plan)
                    write_plan_exclusive(args.out,result,host_root=(
                        plan if package else plan['package_plan'])['request']['host_root'])
                    return result
                return (recover_node_package if package else recover_node_installation)(
                    plan,read_json(args.recovery_plan),
                    approved_plan_sha256=args.approve_plan_sha256,
                    approved_recovery_sha256=args.approve_recovery_sha256)
            if action in ('node-connected-core', 'node-connected-plan', 'node-connected-status'):
                from .template_node_connected import (inspect_connected_core,
                    plan_node_connected, connected_status)
                request=read_json(args.request)
                if action=='node-connected-status':
                    return connected_status(request,read_json(args.descriptor),
                        trusted_descriptor_sha256=args.trusted_descriptor_sha256)
                if action=='node-connected-core':
                    core, _, _ = inspect_connected_core(request)
                    write_plan_exclusive(args.out,core,
                        host_root=request['install_plan']['package_plan']['request']['host_root'])
                    return {'status':'scope_prepared', 'core_sha256':digest(core)}
                result=plan_node_connected(request)
                write_plan_exclusive(args.out,result,
                    host_root=request['install_plan']['package_plan']['request']['host_root'])
                return {'status':'connected_bound_unlaunched',
                        'descriptor_sha256':result['descriptor_sha256'], 'mode':result['mode']}
            if action.startswith('node-connected-session-'):
                from .template_node_connected_session import (
                    create_connected_session, launch_connected_session,
                    observe_connected_session, reconcile_connected_session,
                    stop_connected_session)
                if action == 'node-connected-session-create':
                    return create_connected_session(args.session,read_json(args.request),
                        read_json(args.descriptor), read_json(args.observation),
                        read_json(args.launch_environment),
                        trusted_descriptor_sha256=args.trusted_descriptor_sha256)
                if action == 'node-connected-session-observe':
                    return observe_connected_session(args.session,
                        trusted_session_head=args.trusted_session_head)
                if action == 'node-connected-session-resume':
                    return reconcile_connected_session(args.session,
                        trusted_session_head=args.trusted_session_head)
                if action == 'node-connected-session-launch':
                    return launch_connected_session(args.session,read_json(args.scope),
                        approved_scope_sha256=args.approve_scope_sha256)
                return stop_connected_session(args.session,read_json(args.scope),
                    approved_scope_sha256=args.approve_scope_sha256,
                    disable=action == 'node-connected-session-disable')
            from .template_node_delivery import plan_node_delivery
            from .template_node_session import (create_node_session, launch_node_session,
                resume_node_session, observe_node_session, node_session_status,
                stop_node_session, upgrade_node_session, rollback_node_session)
            if action=='node-delivery-plan':
                result=plan_node_delivery(read_json(args.install_plan),
                    trusted_install_receipt_sha256=args.trusted_install_receipt_sha256,
                    observation=read_json(args.observation),
                    launch_environment=read_json(args.launch_environment))
                from .template_installation import write_plan_exclusive
                write_plan_exclusive(args.out,result,
                    host_root=result['install_plan']['package_plan']['request']['host_root'])
                return result
            if action=='node-session-create':
                return create_node_session(args.session,read_json(args.descriptor))
            if action=='node-resume':
                return resume_node_session(args.session,trusted_session_head=args.trusted_session_head)
            if action=='node-observe':
                return observe_node_session(args.session,trusted_session_head=args.trusted_session_head)
            if action=='node-status':
                return node_session_status(args.session,trusted_session_head=args.trusted_session_head)
            scope=read_json(args.scope)
            approved=args.approve_scope_sha256
            if action=='node-launch':
                return launch_node_session(args.session,scope=scope,approved_scope_sha256=approved)
            if action=='node-upgrade':
                return upgrade_node_session(args.session,read_json(args.descriptor),
                    scope=scope,approved_scope_sha256=approved)
            if action=='node-rollback':
                return rollback_node_session(args.session,scope=scope,approved_scope_sha256=approved)
            return stop_node_session(args.session,scope=scope,approved_scope_sha256=approved,
                disable=action=='node-disable')
        if args.template_action in ('journey-create','journey-record','journey-status','journey-promote','journey-recover-promotion'):
            from .template_delivery_journey import (create_journey, record_journey,
                                                    journey_status, promote_journey,
                                                    recover_journey_promotion)
            if args.template_action=='journey-create':
                return create_journey(args.session,source_root=args.source_root,
                                      bundle=args.bundle,source_kind=args.source_kind)
            if args.template_action=='journey-record':
                return record_journey(args.session,trusted_journey_head=args.trusted_journey_head,
                    stage=args.stage,plan=read_json(args.plan) if args.plan else None,
                    receipt=read_json(args.receipt) if args.receipt else None,
                    trusted_receipt_sha256=args.trusted_receipt_sha256)
            if args.template_action=='journey-status':
                return journey_status(args.session,trusted_journey_head=args.trusted_journey_head)
            if args.template_action=='journey-recover-promotion':
                return recover_journey_promotion(args.session,
                    trusted_journey_head=args.trusted_journey_head)
            return promote_journey(args.session,trusted_journey_head=args.trusted_journey_head,
                observation=read_json(args.observation),
                launch_environment=read_json(args.launch_environment) if args.launch_environment else {})
        if args.template_action in ('delivery-plan','deploy','resume','status','observe','stop','disable','rollback','upgrade'):
            from .template_delivery import (plan_delivery, create_session, launch_session,
                                            resume_session, session_status, observe_session,
                                            stop_session, rollback_session, upgrade_session)
            if args.template_action=='delivery-plan':
                environment=read_json(args.launch_environment) if args.launch_environment else {}
                result=plan_delivery(read_json(args.install_plan),
                    trusted_install_receipt_sha256=args.trusted_install_receipt_sha256,
                    observation=read_json(args.observation),launch_environment=environment)
                from .template_installation import write_plan_exclusive
                write_plan_exclusive(args.out,result,
                    host_root=result['install_plan']['package_plan']['request']['host_root'])
                return result
            if args.template_action=='deploy':
                if bool(args.plan)==bool(args.scope):
                    raise InputError('template_deploy_requires_exactly_plan_or_scope')
                if args.plan:
                    return create_session(args.session,read_json(args.plan))
                if not args.approve_scope_sha256:
                    raise InputError('exact_delivery_scope_digest_required')
                return launch_session(args.session,scope=read_json(args.scope),
                    approved_scope_sha256=args.approve_scope_sha256)
            if args.template_action=='resume':
                return resume_session(args.session,trusted_session_head=args.trusted_session_head)
            if args.template_action=='status':
                return session_status(args.session,trusted_session_head=args.trusted_session_head)
            if args.template_action=='observe':
                return observe_session(args.session,trusted_session_head=args.trusted_session_head)
            if args.template_action=='upgrade':
                return upgrade_session(args.session,read_json(args.plan),
                    scope=read_json(args.scope),approved_scope_sha256=args.approve_scope_sha256)
            if args.template_action=='rollback':
                return rollback_session(args.session,scope=read_json(args.scope),
                    approved_scope_sha256=args.approve_scope_sha256)
            return stop_session(args.session,scope=read_json(args.scope),
                approved_scope_sha256=args.approve_scope_sha256,
                disable=args.template_action=='disable')
        from .template_installation import (plan_package, build_package, package_status, plan_install,
                                            install_package, installation_status, recover_installation,
                                            recover_package, write_plan_exclusive)
        def private_json(path):
            try: return read_json(path)
            except (OSError, ValueError): raise InputError('template_installation_input_unavailable_or_invalid') from None
        if args.template_action=='package':
            result=plan_package(private_json(args.request))
            write_plan_exclusive(args.out,result,host_root=result['request']['host_root']); return result
        if args.template_action=='package-build':
            return build_package(private_json(args.plan),approved_plan_sha256=args.approve_plan_sha256)
        if args.template_action=='package-status':
            return package_status(private_json(args.plan))
        if args.template_action=='package-recover':
            return recover_package(private_json(args.plan),approved_plan_sha256=args.approve_plan_sha256,
                                   approved_generation_sha256=args.approve_generation_sha256)
        if args.template_action=='install-plan':
            result=plan_install(private_json(args.package_plan),private_json(args.package_receipt))
            write_plan_exclusive(args.out,result,host_root=result['package_plan']['request']['host_root']); return result
        plan=private_json(args.plan)
        if args.template_action=='install-status': return installation_status(plan)
        if args.template_action=='install-recover':
            return recover_installation(plan,approved_plan_sha256=args.approve_plan_sha256,
                                        approved_generation_sha256=args.approve_generation_sha256)
        return install_package(plan,approved_plan_sha256=args.approve_plan_sha256)
    if cmd=="implementation-recipes":
        from .integrations.recipes import recipe_catalog
        return recipe_catalog()
    if cmd=="implement-composite-plan":
        from .integrations.composite import plan_composite
        return plan_composite(args.repo,read_json(args.inventory),read_json(args.selection),read_json(args.specs),args.out)
    if cmd=="implement-composite-verify":
        from .integrations.composite import verify_composite
        return verify_composite(args.repo,args.bundle,args.phase,approve_execution=args.approve_execution,
                                baseline_sha256=args.baseline_sha256)
    if cmd=="implement-composite-apply":
        from .integrations.composite import apply_composite
        return apply_composite(args.repo,args.bundle,args.approve,baseline_sha256=args.baseline_sha256)
    if cmd=="implement-composite-status":
        from .integrations.composite import status_composite
        return status_composite(args.repo,args.bundle,trusted_receipt_sha256=args.trusted_receipt_sha256)
    if cmd=="implement-composite-rollback":
        from .integrations.composite import rollback_composite
        return rollback_composite(args.repo,args.bundle,args.approve)
    if cmd=="implement-plan":
        from .integrations.lifecycle import plan_implementation
        return plan_implementation(args.repo,read_json(args.inventory),args.candidate,read_json(args.spec),args.out)
    if cmd=="implement-verify":
        from .integrations.verification import verify_implementation
        if args.out:
            output=Path(args.out).absolute()
            if any(p.is_symlink() for p in (output,*output.parents)) or output.resolve().is_relative_to(Path(args.repo).resolve()):
                raise InputError("Receipt copies must remain outside the target and cannot traverse symlinks")
            if output.resolve().is_relative_to(Path(args.bundle).resolve()):
                raise InputError("Use the bundle's automatic receipt instead of overwriting an internal artifact")
        result=verify_implementation(args.repo,args.bundle,args.phase,approve_execution=args.approve_execution,
                                     baseline_sha256=args.baseline_sha256)
        if args.out: write_json(args.out,read_json(result["receipt_path"]))
        return result
    if cmd=="implement-apply":
        from .integrations.lifecycle import apply_implementation
        return apply_implementation(args.repo,args.bundle,args.approve,baseline_sha256=args.baseline_sha256)
    if cmd=="implement-status":
        from .integrations.lifecycle import implementation_status
        return implementation_status(args.repo,args.bundle,trusted_receipt_sha256=args.trusted_receipt_sha256)
    if cmd=="implement-rollback":
        from .integrations.lifecycle import rollback_implementation
        return rollback_implementation(args.repo,args.bundle,args.approve)
    if cmd.startswith("js-"):
        from .integrations import js_lifecycle as js
        if cmd=="js-support":
            from .integrations.js_backend import js_support_matrix
            return js_support_matrix()
        if cmd=="js-plan":
            return js.plan_js(args.repo,read_json(args.spec),args.bundle,tooling_dir=args.tooling)
        if cmd=="js-verify":
            return js.verify_js(args.repo,args.bundle,args.phase,read_json(args.cases),
                                tooling_dir=args.tooling,approve_execution=args.approve_execution,
                                baseline_sha256=args.baseline_sha256)
        if cmd=="js-apply":
            return js.apply_js(args.repo,args.bundle,args.approve,
                               baseline_sha256=args.baseline_sha256,tooling_dir=args.tooling)
        if cmd=="js-status":
            return js.status_js(args.repo,args.bundle,tooling_dir=args.tooling,
                                trusted_modified_sha256=args.trusted_modified_sha256)
        if cmd=="js-recover":
            return js.recover_js(args.repo,args.bundle,args.operation,tooling_dir=args.tooling,
                                 trusted_receipt_sha256=args.trusted_receipt_sha256)
        if cmd=="js-rollback":
            return js.rollback_js(args.repo,args.bundle,args.approve,tooling_dir=args.tooling)
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
        if args.kind in ("repository-nominated-inventory-v1", "repository-semantic-review-v1", "repository-reviewed-inventory-v1",
                         "repository-coverage-review-v1", "repository-conclusion-v1"):
            from .capabilities import _load
            from .contracts import validate_contract
            from .nomination_inventory import MAX_RECORD_BYTES
            data=_load(Path(args.input),max_bytes=MAX_RECORD_BYTES)
            validate_contract(data,args.kind)
            if args.kind=="repository-conclusion-v1":
                from .capabilities import _digest, CapabilityError
                if _digest({k:v for k,v in data.items() if k!="conclusion_sha256"})!=data["conclusion_sha256"]:
                    raise CapabilityError("repository_conclusion_digest_mismatch")
            return {"status":"valid","kind":args.kind,"records":1,"source_revalidated":False}
        if args.kind in ("repository-capabilities", "candidate-nomination", "admitted-nomination"):
            from .capabilities import _schema, _digest, _load, MAX_INPUT_BYTES
            limit=16_777_217 if args.kind=="repository-capabilities" else MAX_INPUT_BYTES
            data=_load(Path(args.input),max_bytes=limit)
            _schema(args.kind,data)
            if args.kind=="repository-capabilities":
                if _digest({k:v for k,v in data.items() if k!="report_sha256"})!=data["report_sha256"]:
                    raise InputError("Capability report digest mismatch")
            return {"status":"valid","kind":args.kind,"records":1,"source_revalidated":False}
        import jsonschema
        schema=read_json(Path(__file__).parent/"data"/(args.kind+".schema.json"))
        if args.kind=="config": data={"jev_analysis":load_config(args.input)}
        else: data=_records(args.input)
        rows=data if isinstance(data,list) and args.kind in ("run","decision","trace","opportunity","monitor-outcome","deployment-gate") else [data]
        for row in rows:
            jsonschema.Draft202012Validator(schema).validate(row)
            if args.kind=="implementation-spec":
                from .integrations.contracts import validate_spec
                validate_spec(row)
            if args.kind in ('implementation-plan','implementation-receipt'):
                from .contracts import verify
                verify(row)
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
    if cmd=="observed-link":
        from .observed_evidence import freeze_link
        return _save(args.out,freeze_link(args.repo,args.bundle,read_json(args.study),
            read_json(args.placement_set),expected_study_digest=args.study_digest,
            expected_placement_digest=args.placement_digest,
            trusted_implementation_receipt_sha256=args.receipt_sha256,
            monitor_plan=read_json(args.monitor_plan) if args.monitor_plan else None,
            expected_monitor_digest=args.monitor_digest))
    if cmd in ("observed-check","observed-collect-offline","observed-evaluate"):
        from .observed_evidence import check_link, collect_offline, evaluate_linked
        link,study,placement=read_json(args.link),read_json(args.study),read_json(args.placement_set)
        check_link(args.repo,args.bundle,study,placement,link,
            expected_link_digest=args.link_digest,
            trusted_implementation_receipt_sha256=args.receipt_sha256,
            monitor_plan=read_json(args.monitor_plan) if args.monitor_plan else None)
        if cmd=="observed-check":
            return _save(args.out,{"status":"current", "link_digest":args.link_digest,
                                   "target_executed":False,"activation_eligible":False})
        if cmd=="observed-collect-offline":
            return _save(args.out,collect_offline(link,study,read_json(args.request),
                _records(args.fixtures),_records(args.labels),
                approved_request_sha256=args.approve_request,
                expected_link_digest=args.link_digest,root=args.repo,bundle=args.bundle,
                placement_set=placement,
                trusted_implementation_receipt_sha256=args.receipt_sha256,
                monitor_plan=read_json(args.monitor_plan) if args.monitor_plan else None))
        return _save(args.out,evaluate_linked(link,study,read_json(args.collection),
            expected_link_digest=args.link_digest,
            expected_collection_digest=args.collection_digest,
            root=args.repo,bundle=args.bundle,placement_set=placement,
            trusted_implementation_receipt_sha256=args.receipt_sha256,
            gate_bundle=read_json(args.gate_bundle) if args.gate_bundle else None,
            holdout_report=read_json(args.holdout_report) if args.holdout_report else None,
            holdout_plan=read_json(args.holdout_plan) if args.holdout_plan else None,
            holdout_rows=_records(args.holdout_rows) if args.holdout_rows else None,
            monitor_plan=read_json(args.monitor_plan) if args.monitor_plan else None,
            monitor_rows=_records(args.monitor_rows) if args.monitor_rows else None,
            monitor_as_of=args.monitor_as_of))
    raise InputError("Unknown command")


def main(argv=None):
    supplied=list(sys.argv[1:] if argv is None else argv)
    if supplied and supplied[0]=='windows-connected':
        from .windows_template_connected_cli import main as windows_connected_main
        return windows_connected_main(supplied[1:])
    if supplied and supplied[0]=="repository-discovery":
        # Route before generic argparse so untrusted argument values cannot leak
        # through its diagnostics. The staged CLI owns exclusive private output.
        from .repository_discovery import main as discovery_main
        return discovery_main(supplied[1:])
    if supplied and supplied[0]=="repository-placement":
        # This staged command owns bounded external inputs and private outputs.
        from .placement_selection import main as placement_main
        return placement_main(supplied[1:])
    if supplied and supplied[0]=="repository-run":
        # The session command validates private inputs and emits bounded errors.
        from .repository_run import main as repository_run_main
        return repository_run_main(supplied[1:])
    args=parser().parse_args(argv)
    try:
        if args.command in ("discover-capabilities", "nominate-candidate"):
            from .capabilities import main as capabilities_main
            forwarded=["discover" if args.command=="discover-capabilities" else "nominate",
                       "--repo",args.repo,"--out",args.out]
            if args.policy: forwarded.extend(["--policy",args.policy])
            if args.command=="nominate-candidate":
                forwarded.extend(["--nomination",args.nomination,"--report-sha256",args.report_sha256])
            # The capability CLI owns strict input parsing, redacted diagnostics
            # and exclusive private outputs. Do not use generic _save/stdout here.
            return capabilities_main(forwarded)
        result=execute(args)
        # Artifacts contain details; concise stdout remains useful in scripts.
        if args.command=='template' and args.template_action in (
                 'package','package-build','package-status','package-recover','install-plan',
                 'install','install-status','install-recover', 'node-package-plan',
                 'node-package-build','node-package-status','node-install-plan',
                 'node-install','node-install-status', 'node-connected-core',
                 'node-connected-plan','node-connected-status',*_NODE_RECOVERY_ACTIONS):
            display={'schema_version':'1.0','status': result.get('status') or {
                'package':'planned','package-build':'built','install-plan':'planned',
                'install':'installed', 'node-package-plan':'planned',
                'node-package-build':'packaged','node-install-plan':'planned',
                'node-install':'installed', 'node-package-recovery-plan':'recovery_planned',
                'node-install-recovery-plan':'recovery_planned',
                'node-connected-core':'scope_prepared',
                'node-connected-plan':'connected_bound_unlaunched'}.get(args.template_action,'recorded')}
            for field in ('plan_sha256','receipt_sha256','generation_sha256','journal_head_sha256',
                          'core_sha256','descriptor_sha256','mode','provider_requests',
                          'recovery_sha256','recovery_journal_head','recovered_attempts'):
                if field in result: display[field]=result[field]
        elif getattr(args,"out",None) and args.command not in ("scan","architecture","report","scaffold","implement-plan","implement-verify","implement-composite-plan","template"):
            display={"status":"written","output":args.out}
            if isinstance(result,dict):
                for k in ("recommendation","pair_count","evidence_type","status"): 
                    if k in result: display[k]=result[k]
        else: display=result
        print(json.dumps(display,indent=2,allow_nan=False))
        if args.command in ("implement-verify","implement-composite-verify") and result.get("status")=="verification_failed":
            return 3
        if args.command in ("implement-status","implement-composite-status") and result.get("status") in ("blocked_recovery","verification_failed"):
            return 3
        if getattr(args,"enforce",False):
            passed=(result.get("recommendation")=="keep" if args.command=="study-evaluate" else
                    result.get("eligible_for_continued_canary") is True if args.command=="monitor-check" else
                    result.get("eligible_for_activation") is True)
            if not passed: return 3
        return 0
    except (InputError,ValueError,KeyError,TypeError,OSError) as exc:
        # Input errors include only invariant names and paths, never request bodies or credentials.
        if args.command=='template':
            from .template_catalog import template_error
            if args.template_action in ('package','package-build','package-status',
                    'package-recover','install-plan','install','install-status',
                    'install-recover','node-package-plan','node-package-build',
                    'node-package-status','node-install-plan','node-install',
                    'node-install-status','node-connected-core','node-connected-plan',
                    'node-connected-status',*_NODE_RECOVERY_ACTIONS) and isinstance(exc,OSError):
                exc=InputError('template_installation_io_unavailable')
            print(json.dumps(template_error(exc)),file=sys.stderr)
            return 2
        error={"error":type(exc).__name__,"message":str(exc)}
        if args.command.startswith("implement-"):
            error["status"]=getattr(exc,"implementation_status","blocked")
        print(json.dumps(error),file=sys.stderr)
        return 2
    except Exception as exc:
        # jsonschema validation errors may embed sensitive instance content; do not print it.
        print(json.dumps({"error":type(exc).__name__,"message":"Operation failed; inspect the local input/schema without sharing secrets"}),file=sys.stderr)
        return 2
