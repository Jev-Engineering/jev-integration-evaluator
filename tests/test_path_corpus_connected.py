"""Path-input review and lifecycle against a separately authored host and oracle."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import repository_run as run
from jev_integration_evaluator.agent_review import retrieve_context
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.nomination_inventory import (
    _settings, discover_repository_capabilities, prepare_nominated_inventory,
    review_nominated_inventory,
)


SOURCE = Path(__file__).parent / "path_corpus" / "supported_host"
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Native POSIX source and session backend")


def test_supported_host_source_matches_separate_oracle():
    expected = json.loads((SOURCE / "expected.json").read_text())
    assert expected["evidence_kind"] == "synthetic_independent_oracle"
    assert {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
            for name in expected["source_sha256"]} == expected["source_sha256"]


def corpus_input(root: Path) -> tuple[dict, dict]:
    """Review source found at the supplied path; no fixture-generated binding spec."""
    policy = _settings(DEFAULT, None)[1]
    report = discover_repository_capabilities(root, DEFAULT, policy=policy)
    seam = next(s for s in report["seams"] if s["source"]["qualified_symbol"] == "reviewed_boundary")
    source = seam["source"]
    nomination = dict(schema_version="1.0", discovery_version=cap.VERSION,
                      report_sha256=report["report_sha256"], seam_id=seam["seam_id"],
                      source=source, pattern="E", proposer="independent-corpus",
                      rationale="Host has an existing finite action and a separately observed effect count.",
                      evidence=[{k: source[k] for k in ("file", "file_sha256", "start_line", "end_line")}])
    prepared = prepare_nominated_inventory(root, report, [nomination], DEFAULT, policy=policy)
    candidate = prepared["inventory"]["candidates"][0]
    review = dict(schema_version="1.0", prepared_sha256=prepared["prepared_sha256"],
                  reviews={candidate["candidate_id"]: dict(
                      source_sha256=candidate["source"]["source_sha256"],
                      reviewer="separate-corpus-review", reason="Existing host functions satisfy recipe E.",
                      approved=True)})
    inventory = review_nominated_inventory(root, report, prepared, review, DEFAULT, policy=policy)["inventory"]
    host_policy = dict(fallback="block", success_action="read", failure_action="summarize",
                       postconditions=[dict(path="after.events", operation="increased_by", value=1)])
    ownership = dict(configuration=dict(mode="off", model="jev-1.13.0", timeout_ms=2000,
                                        canary_fraction=0.05, max_calls_per_task=5,
                                        max_cost_per_task=0.01, circuit_failures=3,
                                        circuit_cooldown_s=30, cache_ttl_s=0, max_cache_entries=1000,
                                        input_usd_per_million=None, output_usd_per_million=None),
                     policy_version="independent-corpus-v1", canary_scope="independent-corpus",
                     task_field="task_id", max_evidence_bytes=96000, cost_upper_bound=0.0,
                     ownership="stable_host", coordinator="shared_process_local",
                     task_completion="host_owned", audit="required", immutable_cache=False)
    answers = dict(host_policy=host_policy, runtime_ownership=ownership)
    context = retrieve_context(root, inventory, candidate["candidate_id"], capability_report=report)
    request = dict(context=context, saved_answers=answers,
                   authority=dict(mutation=False, execution=False, egress=False,
                                  installation=False, activation=False))
    questions = dict(decision=dict(type="choice", instructions="Which finite disposition fits the observed result?",
                                   criteria=dict(succeeded="The read completed once.",
                                                 failed="The completed read needs inspection.",
                                                 uncertain="Evidence is insufficient.")),
                     sufficient=dict(type="noul", instructions="Is the observed event adequate?"))
    bindings = dict(runtime="host_runtime", evidence="host_evidence", baseline_action="host_baseline_action",
                    registry="host_registry", gate="host_gate", validate="host_validate",
                    blocked="host_blocked", guard="host_guard", observe="host_observe",
                    postcondition="host_postcondition", finish="host_finish")
    proposal = dict(schema_version="1.0", kind="offline-agent-review-proposal-v1",
                    request_sha256=digest(request), reviewer="independent-corpus-review",
                    reason="Existing host functions and source-matched finite decision.",
                    evidence=[dict(file="host.py", sha256=hashlib.sha256((root / "host.py").read_bytes()).hexdigest(),
                                   symbol="reviewed_boundary")],
                    recipe_id="python.E", bindings=bindings, questions=questions,
                    primary_question="decision", evidence_question="sufficient",
                    label_actions=dict(succeeded="read", failed="summarize", uncertain=None), unresolved=[])
    case = dict(id="single_read", request=dict(task_id="corpus-alpha", item="alpha", intent="read",
                                               permit=True, approved=False), initial_globals=dict(EVENTS=[]),
                baseline=dict(result="read:alpha", exception=None, calls=dict(do_read=1),
                              globals={"EVENTS": [["read", "alpha"]]}),
                active=dict(result=dict(result="read:alpha", action="read"), exception=None,
                            calls=dict(do_read=1), globals={"EVENTS": [["read", "alpha"]]}),
                assessment_label="succeeded")
    verification = dict(classification="synthetic", entry_point="public_entry",
                        effect_symbols=["do_read"], cases=[case], timeout_s=20,
                        baseline_command=[], modified_command=[])
    envelope = dict(schema_version="1.0", kind="repository-offline-agent-review-v1",
                    candidate_id=candidate["candidate_id"], capabilities=report, inventory=inventory,
                    proposal=proposal, verification=verification, related_files=[])
    session_context = run.request_context(policy=policy, adapter=run.BOUND_ADAPTER,
                                          objective="Classify an existing finite host outcome",
                                          saved_answers=answers)
    return envelope, session_context


def scope_for(root: Path, context: dict, previous: dict, **grants) -> dict:
    inspected = run.inspect_repository(root, context=context)
    baseline_ref = previous["receipt_references"]["baseline"]
    return dict(schema_version="1.0", kind="repository-run-scope-v1",
                reference="independent-synthetic-host-only",
                repository_identity=inspected["report"]["repository_identity"],
                context_sha256=inspected["context_sha256"], bundle_digest=previous.get("bundle_digest"),
                trusted_session_head=previous["session_head_sha256"],
                trusted_baseline_receipt=baseline_ref["sha256"] if baseline_ref else None,
                trusted_modified_receipt=None, rollback_digest=None,
                execution_environment="trusted_host", prepared_sha256=previous.get("prepared_sha256"),
                grants={**run.ZERO_GRANTS, **grants})


def public_host(root: Path, item: str, intent: str, grant: str = "permit") -> dict:
    done = subprocess.run([sys.executable, "-B", "-S", str(root / "main.py"), item, intent, grant],
                          cwd=root, capture_output=True, text=True, timeout=5, check=True)
    assert done.stderr == ""
    return json.loads(done.stdout)


@pytest.mark.parametrize(("item", "grant", "expected"), [
    ("alpha", "permit", {"result": "read:alpha", "events": [["read", "alpha"]]}),
    ("beta", "deny", {"result": "blocked", "events": []}),
])
def test_supported_host_independent_baseline(item, grant, expected):
    assert public_host(SOURCE, item, "read", grant) == expected


@pytest.mark.parametrize(("before", "after", "item", "grant", "expected"), [
    ('request.get("permit") is True and action in ALLOWED',
     'True and action in ALLOWED', "beta", "deny", {"result": "blocked", "events": []}),
    ('EVENTS.append(["read", request["item"]])',
     'EVENTS.extend([["read", request["item"]], ["read", request["item"]]])',
     "alpha", "permit", {"result": "read:alpha", "events": [["read", "alpha"]]}),
])
def test_independent_oracle_catches_policy_and_duplicate_effect_mutations(
        tmp_path, before, after, item, grant, expected):
    root = tmp_path / "mutated"
    shutil.copytree(SOURCE, root)
    source = (root / "host.py").read_text()
    assert source.count(before) == 1
    (root / "host.py").write_text(source.replace(before, after))
    assert public_host(root, item, "read", grant) != expected


def planned_supported(tmp_path):
    root, session = tmp_path / "host", tmp_path / "session"
    shutil.copytree(SOURCE, root)
    assert public_host(root, "alpha", "read") == {"result": "read:alpha", "events": [["read", "alpha"]]}
    envelope, context = corpus_input(root)
    original = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    ready = run.run_repository(root, session, context=context, agent_review_input=envelope)
    assert ready["status"] == "reviewed_specification_ready"
    planned = run.run_repository(root, session, agent_review_input=envelope,
                                 scope=scope_for(root, context, ready, prepare=True), stop_after="plan")
    assert planned["status"] == "planned", planned
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == original
    return root, session, envelope, context, ready, planned


def test_external_cli_input_prepares_exact_owned_plan(tmp_path):
    root, session = tmp_path / "host", tmp_path / "session"
    shutil.copytree(SOURCE, root)
    envelope, context = corpus_input(root)
    review_file, context_file, scope_file = (tmp_path / name for name in
                                            ("review.json", "context.json", "scope.json"))
    review_file.write_text(json.dumps(envelope), encoding="utf-8")
    context_file.write_text(json.dumps(context), encoding="utf-8")
    original = (root / "host.py").read_bytes()

    def invoke(*extra):
        done = subprocess.run([sys.executable, "-m", "jev_integration_evaluator",
                               "repository-run", str(root), "--session", str(session),
                               "--agent-review", str(review_file), *extra],
                              cwd=Path(__file__).resolve().parents[1],
                              capture_output=True, text=True, timeout=30, check=True)
        assert done.stderr == ""
        return json.loads(done.stdout)

    ready = invoke("--context", str(context_file))
    assert ready["status"] == "reviewed_specification_ready"
    scope_file.write_text(json.dumps(scope_for(root, context, ready, prepare=True)), encoding="utf-8")
    planned = invoke("--scope", str(scope_file), "--stop-after", "plan")
    assert planned["status"] == "planned"
    assert planned["attempts"]["plan"] == 1
    assert (root / "host.py").read_bytes() == original


def test_connected_independent_host_path(tmp_path):
    root, session, envelope, context, ready, planned = planned_supported(tmp_path)
    verified = run.run_repository(root, session,
                                  scope=scope_for(root, context, planned, baseline=True, apply=True, modified=True))
    assert verified["status"] == "verified", verified
    assert verified["attempts"] == dict(plan=1, baseline=1, apply=1, modified=1, rollback=0)
    assert verified["provider_connectivity"] == "not_tested"
    assert verified["runtime_activation_authorized"] is False
    state = json.loads((session / "journal.jsonl").read_text().splitlines()[-1])["state"]
    receipt = json.loads((Path(state["bundle"]["path"]) / "verification-receipt.json").read_text())
    assert receipt["status"] == "passed"
    assert "independent_postcondition_and_no_reexecution" in receipt["contract_assertions"]
    assert [(row["mode"], row["status"], row["observation"]["model_calls"],
             row["observation"]["calls"].get("do_read")) for row in receipt["results"]] == [
                 ("off", "passed", 0, 1), ("shadow", "passed", 0, 1),
                 ("active", "passed", 1, 1)]


def test_interrupted_after_baseline_resumes_without_duplicate_effect(tmp_path):
    root, session, _, context, _, planned = planned_supported(tmp_path)
    baseline = run.run_repository(root, session, scope=scope_for(root, context, planned, baseline=True),
                                  stop_after="baseline")
    assert baseline["status"] == "baseline_passed"
    assert baseline["attempts"] == dict(plan=1, baseline=1, apply=0, modified=0, rollback=0)
    verified = run.run_repository(root, session,
                                  scope=scope_for(root, context, baseline, apply=True, modified=True))
    assert verified["status"] == "verified", verified
    assert verified["attempts"] == dict(plan=1, baseline=1, apply=1, modified=1, rollback=0)
    assert run.run_repository(root, session)["status"] == "recorded_untrusted"


def test_interrupted_after_apply_resumes_without_reapplying_owned_bytes(tmp_path):
    root, session, _, context, _, planned = planned_supported(tmp_path)
    applied = run.run_repository(root, session,
                                 scope=scope_for(root, context, planned, baseline=True, apply=True),
                                 stop_after="apply")
    assert applied["status"] == "applied_unverified", applied
    assert applied["attempts"] == dict(plan=1, baseline=1, apply=1, modified=0, rollback=0)
    source_after_apply = (root / "host.py").read_bytes()
    verified = run.run_repository(root, session,
                                  scope=scope_for(root, context, applied, modified=True))
    assert verified["status"] == "verified", verified
    assert verified["attempts"] == dict(plan=1, baseline=1, apply=1, modified=1, rollback=0)
    assert (root / "host.py").read_bytes() == source_after_apply


def test_stale_review_and_concurrent_owned_edit_do_not_apply(tmp_path):
    root, session = tmp_path / "host", tmp_path / "session"
    shutil.copytree(SOURCE, root)
    envelope, context = corpus_input(root)
    ready = run.run_repository(root, session, context=context, agent_review_input=envelope)
    source = root / "host.py"
    source.write_bytes(source.read_bytes() + b"\n# concurrent owner edit\n")
    edited = source.read_bytes()
    with pytest.raises(run.SessionError, match="stale|drift|mismatch"):
        run.run_repository(root, session, agent_review_input=envelope,
                           scope=scope_for(root, context, ready, prepare=True), stop_after="plan")
    assert source.read_bytes() == edited
    state = json.loads((session / "journal.jsonl").read_text().splitlines()[-1])["state"]
    assert state["attempts"]["plan"] == 0


def test_forged_baseline_receipt_cannot_authorize_apply(tmp_path):
    root, session, _, context, _, planned = planned_supported(tmp_path)
    baseline = run.run_repository(root, session, scope=scope_for(root, context, planned, baseline=True),
                                  stop_after="baseline")
    assert baseline["status"] == "baseline_passed"
    state = json.loads((session / "journal.jsonl").read_text().splitlines()[-1])["state"]
    bundle = Path(state["bundle"]["path"])
    source_before = (root / "host.py").read_bytes()
    receipt = bundle / "baseline-receipt.json"
    receipt.write_bytes(receipt.read_bytes() + b" ")
    blocked = run.run_repository(root, session,
                                 scope=scope_for(root, context, baseline, apply=True, modified=True))
    assert blocked["status"] == "blocked_recovery", blocked
    assert (root / "_jev_reviewed_boundary.py").exists() is False
    assert (root / "host.py").read_bytes() == source_before
    state = json.loads((session / "journal.jsonl").read_text().splitlines()[-1])["state"]
    assert state["receipts"]["modified"] is None


def test_dirty_git_worktree_conflict_preserves_owner_edit(tmp_path):
    root, session = tmp_path / "host", tmp_path / "session"
    shutil.copytree(SOURCE, root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "host.py", "main.py", "expected.json"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "core.hooksPath=/dev/null",
                    "-c", "commit.gpgsign=false", "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "baseline"], check=True)
    envelope, context = corpus_input(root)
    ready = run.run_repository(root, session, context=context, agent_review_input=envelope)
    planned = run.run_repository(root, session, agent_review_input=envelope,
                                 scope=scope_for(root, context, ready, prepare=True), stop_after="plan")
    assert planned["status"] == "planned"
    baseline = run.run_repository(root, session, scope=scope_for(root, context, planned, baseline=True),
                                  stop_after="baseline")
    assert baseline["status"] == "baseline_passed"
    path = root / "host.py"
    path.write_bytes(path.read_bytes() + b"\n# independent concurrent edit\n")
    dirty = path.read_bytes()
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                            capture_output=True, text=True, check=True)
    assert " M host.py" in status.stdout
    with pytest.raises(run.SessionError, match="drift|changed|mismatch"):
        run.run_repository(root, session, scope=scope_for(root, context, baseline, apply=True))
    assert path.read_bytes() == dirty
    assert not (root / "_jev_reviewed_boundary.py").exists()


def test_post_apply_conflicting_edit_blocks_verification_without_replay(tmp_path):
    root, session, _, context, _, planned = planned_supported(tmp_path)
    applied = run.run_repository(root, session,
                                 scope=scope_for(root, context, planned, baseline=True, apply=True),
                                 stop_after="apply")
    assert applied["status"] == "applied_unverified"
    path = root / "host.py"
    path.write_bytes(path.read_bytes() + b"\n# conflicting post-apply owner edit\n")
    edited = path.read_bytes()
    with pytest.raises(run.SessionError, match="drift|changed|mismatch"):
        run.run_repository(root, session, scope=scope_for(root, context, applied, modified=True))
    assert path.read_bytes() == edited
    state = json.loads((session / "journal.jsonl").read_text().splitlines()[-1])["state"]
    assert state["attempts"]["apply"] == 1
    assert state["attempts"]["modified"] == 0
