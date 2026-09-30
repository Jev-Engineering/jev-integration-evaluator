"""Authorized, reviewable local implementation plans with stale-source protection."""
from __future__ import annotations
import difflib
import hashlib
import os
import re
import subprocess
from pathlib import Path
from .io import InputError, atomic_text, digest, file_hash, safe_child, write_json, redact
from .questions import api_questions

FORBIDDEN = re.compile(r"(?i)(^|/)(\.git|\.env(?:\.[^/]*)?|credentials?|secrets?)(/|$)|\.(pem|key|p12)$")


def make_patch_plan(root: str | Path, changes: list[dict], candidate_ids: list[str]) -> dict:
    root=Path(root).resolve()
    if not root.is_dir(): raise InputError("Repository root is not a directory")
    if not changes or not candidate_ids: raise InputError("A patch needs changes and source opportunity IDs")
    entries=[]; paths=set()
    for change in changes:
        rel=change.get("file","")
        if FORBIDDEN.search(rel): raise InputError("Patch touches a protected path")
        p=safe_child(root,rel)
        path_key=rel.casefold() if os.name == 'nt' else rel
        if path_key in paths: raise InputError("Duplicate patch path")
        paths.add(path_key)
        if set(change)-{"file","new_content"}: raise InputError("Changes only allow file and new_content")
        new=change.get("new_content")
        if not isinstance(new,str) or len(new.encode())>2_000_000: raise InputError("New content must be bounded text")
        if p.exists() and not p.is_file(): raise InputError("Patch target is not a regular file")
        old=p.read_bytes().decode("utf-8") if p.exists() else ""
        entries.append({"file":rel,"operation":"update" if p.exists() else "create",
                        "old_sha256":file_hash(p) if p.exists() else None,
                        "new_sha256":hashlib.sha256(new.encode()).hexdigest(),"new_content":new,
                        "diff":"".join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile="a/"+rel,tofile="b/"+rel))})
    body={"schema_version":"1.0","repository_identity":digest(str(root)),"candidate_ids":candidate_ids,"changes":entries,
          "authorization_scope":"Apply exactly these local text changes; no install, test execution, git push, merge, or deployment"}
    body["plan_digest"]=digest(body)
    return body


def apply_patch_plan(root: str | Path, plan: dict, approval: str, *, progress=None,
                     expected_identities: dict | None = None) -> dict:
    if os.name == 'nt':
        from . import capabilities as cap
        try:
            cap._windows_check_directory_path(root, purpose='source_mutation')
        except (cap.CapabilityError, OSError):
            raise InputError('windows_source_root_unavailable') from None
    root=Path(root).resolve()
    body={k:v for k,v in plan.items() if k!="plan_digest"}
    if digest(body)!=plan.get("plan_digest") or approval!=plan.get("plan_digest"):
        raise InputError("Exact plan digest approval is required")
    if plan.get("repository_identity")!=digest(str(root)): raise InputError("Plan belongs to a different repository path")
    before={}; paths=set()
    for c in plan["changes"]:
        path_key=c["file"].casefold() if os.name == 'nt' else c["file"]
        if path_key in paths or FORBIDDEN.search(c["file"]): raise InputError("Duplicate/protected path in patch")
        paths.add(path_key)
        p=safe_child(root,c["file"])
        if hashlib.sha256(c["new_content"].encode()).hexdigest()!=c["new_sha256"]: raise InputError("New content hash mismatch")
        if os.name == 'nt' and c['old_sha256'] is not None:
            from .windows_source_mutation import reconcile_pending_reviewed_write
            if reconcile_pending_reviewed_write(p, c['old_sha256'], c['new_sha256'], root):
                raise InputError('Interrupted owned source write reconciled; review a new plan')
        actual=file_hash(p) if p.exists() else None
        if actual!=c["old_sha256"]: raise InputError("Stale patch: target changed after planning")
        before[c["file"]]=p.read_bytes() if p.exists() else None
    written=[]; owned_identities={}
    try:
        for c in plan["changes"]:
            p=safe_child(root,c["file"])
            # Recheck just before writing. For concurrent writers use a dedicated worktree.
            if (file_hash(p) if p.exists() else None)!=c["old_sha256"]: raise InputError("Concurrent source change")
            if progress is not None: progress("write_started", c)
            if os.name == 'nt':
                from .windows_source_mutation import write_reviewed_text
                owned_identities[c['file']] = write_reviewed_text(
                    p, c['new_content'], c['old_sha256'], repository_root=root,
                    expected_identity=(expected_identities or {}).get(c['file']))
            else:
                atomic_text(p,c["new_content"])
            written.append(c)
            if progress is not None:
                completed = ({**c, 'owned_identity': owned_identities[c['file']]}
                             if os.name == 'nt' else c)
                progress("write_completed", completed)
    except Exception:
        for c in reversed(written):
            p=safe_child(root,c["file"])
            if os.name == 'nt':
                from .windows_source_mutation import remove_owned_created, write_reviewed_text
                original=before[c['file']]
                if original is None:
                    remove_owned_created(p, owned_identities[c['file']], c['new_sha256'])
                else:
                    write_reviewed_text(p, original.decode('utf-8'), c['new_sha256'],
                                        expected_identity=owned_identities[c['file']],
                                        repository_root=root)
                continue
            if p.exists() and file_hash(p)==c["new_sha256"]:
                original=before[c["file"]]
                if original is None: p.unlink()
                else:
                    # Original text was UTF-8 checked during planning; preserve bytes/newlines exactly.
                    atomic_text(p,original.decode("utf-8"))
        raise
    return {"status":"applied","plan_digest":plan["plan_digest"],"files":[c["file"] for c in written],
            "tests_executed":False,"push_merge_deploy":False,
            "diff_summary":[{"file":c["file"],"operation":c["operation"],"old_sha256":c["old_sha256"],"new_sha256":c["new_sha256"]} for c in written]}


def prepare_worktree(root: str | Path, destination: str | Path, branch: str, approved: bool=False) -> dict:
    if approved is not True: raise InputError("Worktree/branch creation requires explicit approval")
    root=Path(root).resolve(); dest=Path(destination).resolve()
    if dest.exists() or dest.is_relative_to(root): raise InputError("Use a new directory outside the source repository")
    if not re.fullmatch(r"jev/[A-Za-z0-9][A-Za-z0-9._/-]{0,100}",branch) or ".." in branch or "//" in branch:
        raise InputError("Use a valid jev/<scoped-name> branch")
    result=subprocess.run(["git","-C",str(root),"worktree","add","-b",branch,str(dest)],capture_output=True,text=True,timeout=30)
    if result.returncode: raise InputError("git worktree creation failed; inspect local Git status")
    return {"worktree":str(dest),"branch":branch,"status":"created"}


def run_authorized_tests(root, command: list[str], *, approve_execution: bool=False, timeout_s: int=120):
    """Authorized argv execution with bounded capture, not a security sandbox."""
    import signal
    import threading
    if approve_execution is not True: raise InputError("Tests execute repository code and require explicit execution authorization")
    if not command or any(not isinstance(x,str) or not x for x in command): raise InputError("Expected a command argument vector, not a shell string")
    if type(timeout_s) not in (int,float) or not 0 < timeout_s <= 3600: raise InputError("Test timeout must be in (0,3600] seconds")
    env={k:v for k,v in os.environ.items() if not re.search(r"(?i)api.?key|secret|password|token",k)}
    process=subprocess.Popen(command,cwd=Path(root).resolve(),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             shell=False,start_new_session=os.name=="posix")
    streams=[bytearray(),bytearray()]; counters=[0,0]; output_limit=threading.Event()
    def terminate():
        try:
            if os.name=="posix": os.killpg(process.pid,signal.SIGKILL)
            else: process.kill()
        except ProcessLookupError: pass
    def drain(index,pipe):
        try:
            while True:
                chunk=pipe.read(4096)
                if not chunk: break
                counters[index]+=len(chunk)
                streams[index].extend(chunk)
                if len(streams[index])>20000: del streams[index][:-20000]
                if counters[index]>1_000_000:
                    output_limit.set();terminate();break
        finally: pipe.close()
    workers=[threading.Thread(target=drain,args=(i,pipe),daemon=True) for i,pipe in enumerate((process.stdout,process.stderr))]
    for worker in workers:worker.start()
    timeout=False
    try:process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:timeout=True;terminate();process.wait()
    for worker in workers:worker.join(timeout=2)
    descendants_terminated=any(worker.is_alive() for worker in workers)
    if descendants_terminated:
        terminate()
        for worker in workers:worker.join(timeout=2)
    return {"command":command,"returncode":None if timeout else process.returncode,
            "stdout":redact(bytes(streams[0]).decode("utf-8",errors="replace")),
            "stderr":redact(bytes(streams[1]).decode("utf-8",errors="replace")),
            "status":"timeout" if timeout else "passed" if process.returncode==0 and not output_limit.is_set() and not descendants_terminated else "failed",
            "output_limit_exceeded":output_limit.is_set(),"descendants_terminated":descendants_terminated,"sandboxed":False,
            "warning":"Environment filtering and bounded capture are not a sandbox; use an isolated runner for untrusted code"}


def scaffold_integration(scan: dict, candidate_id: str, output: str | Path) -> dict:
    candidates={c["candidate_id"]:c for c in scan["candidates"]}
    if candidate_id not in candidates: raise InputError("Candidate not found")
    c=candidates[candidate_id]
    if c["tier"]==0: raise InputError("Rejected deterministic placement cannot be scaffolded")
    out=Path(output)
    if out.exists() and any(out.iterdir()): raise InputError("Scaffold output must be a new or empty directory")
    out.mkdir(parents=True,exist_ok=True)
    questions=api_questions(c["jev_questions"])
    source=c["source"]
    adapter='''"""Generated proposal adapter. No actions execute here. Source identity: SOURCE_ID."""
from jev_integration_evaluator.runtime import SafeRouter, HostGate
QUESTIONS = QUESTIONS_VALUE
PRIMARY = PRIMARY_VALUE
EVIDENCE = EVIDENCE_VALUE
PROVENANCE = PROVENANCE_VALUE

def create_router(client, runtime_config: dict, *, policy_version: str = "v1",
                  activation: dict | None = None, thresholds=None, action_thresholds=None, audit_log=None,
                  budget_coordinator=None, max_concurrent_calls: int = 8, canary_scope: str | None = None):
    """New integrations bind expiring receipts to the full runtime policy and question roles."""
    return SafeRouter(client, runtime_config, policy_version=policy_version, activation=activation,
                      thresholds=thresholds, action_thresholds=action_thresholds,
                      audit_log=audit_log, require_expiring_activation=True, require_runtime_binding=True,
                      budget_coordinator=budget_coordinator, max_concurrent_calls=max_concurrent_calls,
                      canary_scope=canary_scope)

def propose(router: SafeRouter, *, task_id: str, state: dict, baseline: str, gate: HostGate,
            immutable_state: bool = False, cache_scope: str | None = None,
            estimated_cost_upper_bound: float | None = None):
    return router.route(task_id=task_id, state=state, questions=QUESTIONS,
                        primary_question=PRIMARY, evidence_question=EVIDENCE,
                        baseline_action=baseline, gate=gate, immutable_state=immutable_state,
                        cache_scope=cache_scope, estimated_cost_upper_bound=estimated_cost_upper_bound, provenance=PROVENANCE)
'''.replace("SOURCE_ID",candidate_id).replace("QUESTIONS_VALUE",repr(questions)).replace("PRIMARY_VALUE",repr(c["jev_questions"][0]["id"])).replace("EVIDENCE_VALUE",repr(c["jev_questions"][1]["id"])).replace("PROVENANCE_VALUE",repr({"candidate_id":candidate_id,"experiment_id":c["recommended_experiment"]["id"],"source_location":source}))
    atomic_text(out/"adapter.py",adapter)
    atomic_text(out/"test_adapter.py",'''from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.runtime import SafeRouter, HostGate
from adapter import propose, create_router

class MustNotCall:
    is_remote = False
    def evaluate(self, *args):
        raise AssertionError("Default-off integration called a model")

def test_default_off_preserves_baseline():
    with create_router(MustNotCall(), load_config()["runtime"]) as router:
        result = propose(router, task_id="smoke", state={}, baseline="inspect",
                         gate=HostGate(("inspect",)))
        assert result.action == "inspect"
        assert result.reason == "feature_off"
        assert router.require_expiring_activation is True
        assert router.require_runtime_binding is True
''')
    manifest={"candidate_id":candidate_id,"source":source,"questions_hash":digest(questions),"feature_flag_default":"off",
              "wiring_status":"adapter_generated_not_yet_connected_to_host_callsite","factory_requires_expiring_activation":True,"factory_requires_runtime_binding":True,"generated_files":["adapter.py","test_adapter.py","integration-manifest.json","WIRING.md"],
              "experiment_id":c["recommended_experiment"]["id"],"baseline_preserved":True}
    write_json(out/"integration-manifest.json",manifest)
    atomic_text(out/"WIRING.md",f'''# Wire {candidate_id} into the host\n\nSource: `{source['file']}::{source['symbol']}` lines {source['start_line']}–{source['end_line']}.\n\nThe generated adapter is executable, but no host source was rewritten. An authorized agent must inspect this exact source, bind the rubric labels to legal host actions, build the minimal state, call `propose`, and recheck deterministic policy at the execution boundary. Do not treat an assessment as authorization.\n\nCreate a worktree when appropriate, run the existing baseline, add this adapter behind an off-by-default flag, and generate a content-hashed patch plan containing the host call-site edit. Review that diff and approve its exact digest before applying it. Add unit/integration/failure-injection fixtures, run the host's tests only with execution approval, and collect shadow evidence. Use `create_router` to require expiring, ordered-question-bound activation receipts. Freeze chosen thresholds and validate an untouched holdout; collect a separately frozen paired study before canary/active adoption. `suspend()` and `revoke_activation()` latch off new and in-flight proposals; host policy must recheck before execution.\n\nFor multi-placement operation, pass the SAME `BudgetCoordinator` and `canary_scope` to every router. Bind the host receipt to `router.runtime_contract_hash(QUESTIONS, PRIMARY, EVIDENCE)` after selecting the exact runtime configuration; changing question roles, exposure or budget scope requires renewed review. Read `references/operational-evidence-v1.2.md` for all-gate studies and fixed-window monitoring.\n\nTraceability: `{c['recommended_experiment']['id']}`; questions `{digest(questions)}`.\n\nFallback: unavailable/timeout/invalid/low-confidence → permitted baseline or inspect; failed host authorization → block/request approval. Never widen permissions to make the integration work.\n''')
    return manifest
