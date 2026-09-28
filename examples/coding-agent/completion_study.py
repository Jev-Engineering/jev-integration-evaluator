"""Three-arm synthetic completion study; no provider or real tool execution."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import statistics
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from agent import run_steps
from completion_oracle import score_trace, state_digest


HERE = Path(__file__).resolve().parent
DATA = HERE / "completion"
FILES = {
    "source": HERE / "agent.py",
    "runner": HERE / "completion_study.py",
    "oracle": HERE / "completion_oracle.py",
    "cases": DATA / "cases.json",
    "scorer": DATA / "scorer-labels.json",
    "assessments": DATA / "assessments.json",
    "policy": DATA / "policy.json",
}


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    return json.loads(FILES[name].read_text(encoding="utf-8"))


class Proposal:
    """One immutable synthetic action carried as the historical single argument."""

    def __init__(self, step):
        self.name = step["action"]
        self.arguments = deepcopy(step["arguments"])
        self.step_id = step["step_id"]


class ScriptedLLM:
    def __init__(self, case):
        self.steps = case["steps"]
        self.index = 0

    def choose(self, plan, observation):
        if self.index >= len(self.steps):
            return Proposal({"action": "unregistered", "arguments": {}, "step_id": "unscheduled"})
        step = self.steps[self.index]
        self.index += 1
        return Proposal(step)


class Planner:
    def __init__(self):
        self.calls = 0

    def plan(self, objective):
        self.calls += 1
        return {"task_id": objective["task_id"]}


class Observer:
    def __init__(self, store):
        self.store = store
        self.sequence = 0

    def observe(self):
        self.sequence += 1
        raw = deepcopy(self.store.raw)
        return {"status": "fresh", "capture_id": f"{raw['task_id']}-c{self.sequence}",
                "snapshot": raw, "raw_sha256": state_digest(raw)}

    def after(self, before, fault):
        if fault == "fresh":
            return self.observe()
        if fault == "stale":
            return {**deepcopy(before), "status": "stale"}
        if fault in ("missing", "timeout"):
            return {"status": fault, "capture_id": None, "snapshot": None, "raw_sha256": None}
        raise ValueError("unknown observer fault")


def action_rejection(proposal, raw, case, policy):
    """Host-owned action, argument, permission, task and transition checks."""
    contract = policy["legal_actions"].get(proposal.name)
    if contract is None or proposal.name not in case["registered_actions"]:
        return "invalid_action"
    arguments = proposal.arguments
    if type(arguments) is not dict or set(arguments) != set(contract["argument_types"]):
        return "invalid_arguments"
    if any(type(arguments[key]) is not str for key in contract["argument_types"]):
        return "invalid_arguments"
    if arguments["task_id"] != raw["task_id"]:
        return "wrong_task"
    if contract["permission"] not in case["granted_permissions"]:
        return "permission_denied"
    if proposal.name == "set_status" and [raw["status"], arguments["status"]] not in contract["allowed_transitions"]:
        return "invalid_transition"
    if proposal.name == "add_label" and (arguments["label"] not in contract["allowed_labels"]
                                          or raw["status"] not in contract["allowed_statuses"]
                                          or arguments["label"] in raw["labels"]):
        return "invalid_transition"
    return None


class FakeExecutor:
    """Only isolated in-memory effects, bound to action, arguments and raw before state."""

    def __init__(self, case, policy):
        self.case = case
        self.policy = policy
        self.raw = deepcopy(case["initial_raw_state"])
        self.receipts = []
        self.trace = []
        self.used = set()
        self.execute_calls = 0

    def _match(self, proposal):
        for step in self.case["steps"]:
            if (step["step_id"] not in self.used and proposal.name == step["action"]
                    and proposal.arguments == step["arguments"]
                    and self.raw["revision"] == step["bound_before_revision"]
                    and state_digest(self.raw) == step["bound_before_state_sha256"]):
                return step
        return None

    def _record(self, step_id, status, reason, before):
        receipt_id = f"{self.raw['task_id']}-r{len(self.receipts) + 1}"
        receipt = {"receipt_id": receipt_id, "step_id": step_id, "status": status,
                   "reason": reason, "raw_before_sha256": state_digest(before),
                   "raw_after_sha256": state_digest(self.raw), "raw_after": deepcopy(self.raw)}
        self.receipts.append(receipt)
        self.trace.append({"step_id": step_id, "receipt_id": receipt_id,
                           "raw_before": before, "raw_after": deepcopy(self.raw)})
        return receipt

    def reject_without_execute(self, proposal, reason):
        before = deepcopy(self.raw)
        step = self._match(proposal)
        if step:
            self.used.add(step["step_id"])
        return self._record(step["step_id"] if step else "unscheduled", "rejected_" + reason, reason, before)

    def execute_tool(self, proposal):
        """The original run_steps calls this with exactly one proposal object."""
        self.execute_calls += 1
        before = deepcopy(self.raw)
        step = self._match(proposal)
        if step is None:
            self._record("unscheduled", "rejected_no_script", "no_bound_effect", before)
            return SimpleNamespace(success=False)
        self.used.add(step["step_id"])
        reason = action_rejection(proposal, self.raw, self.case, self.policy)
        if reason is not None:
            self._record(step["step_id"], "rejected_" + reason, reason, before)
            return SimpleNamespace(success=step["result_success"])
        effect = step["scripted_effect"]
        if effect == "raise":
            self._record(step["step_id"], "exception", "synthetic_runtime_error", before)
            raise RuntimeError("synthetic executor failure")
        if effect in ("close", "faulty_extra"):
            self.raw["status"] = "closed"
        elif effect == "wrong":
            self.raw["status"] = "blocked"
        if effect in ("label", "faulty_extra") and "verified" not in self.raw["labels"]:
            self.raw["labels"].append("verified")
        if effect == "faulty_extra":
            self.raw["unrequested"].append("synthetic-extra")
        if effect not in ("noop", "raise"):
            self.raw["revision"] += 1
        self._record(step["step_id"], "executor_contract_violation" if effect == "faulty_extra" else "executed",
                     "extra_mutation" if effect == "faulty_extra" else None, before)
        return SimpleNamespace(success=step["result_success"])


def fresh_after(before, after, receipt, case):
    if before["status"] != "fresh" or after["status"] != "fresh":
        return False
    task_id = case["objective"]["task_id"]
    prefix = task_id + "-c"
    if not (isinstance(before["capture_id"], str) and isinstance(after["capture_id"], str)
            and before["capture_id"].startswith(prefix) and after["capture_id"].startswith(prefix)):
        return False
    try:
        before_number = int(before["capture_id"][len(prefix):])
        after_number = int(after["capture_id"][len(prefix):])
    except ValueError:
        return False
    if after_number != before_number + 1:
        return False
    raw = after["snapshot"]
    return bool(raw and raw["task_id"] == case["objective"]["task_id"]
                and after["raw_sha256"] == state_digest(raw)
                and raw["revision"] == receipt["raw_after"]["revision"]
                and after["raw_sha256"] == receipt["raw_after_sha256"])


def deterministic_postconditions(snapshot, objective):
    """Online state machine; independently implemented from the scorer oracle."""
    if not isinstance(snapshot, dict) or set(snapshot) != set(objective["allowed_fields"]):
        return False
    labels = snapshot.get("labels")
    required = objective["required_labels"]
    return bool(
        snapshot.get("task_id") == objective["task_id"]
        and snapshot.get("status") == objective["required_status"]
        and type(snapshot.get("revision")) is int
        and isinstance(labels, list) and all(type(label) is str for label in labels)
        and len(labels) == len(required)
        and set(labels) == set(required)
        and snapshot.get("unrequested") == objective["required_unrequested"]
    )


def assess_jev(step, before, after, receipt, fixture, policy):
    response = fixture["responses"][step["step_id"]]
    expected_kind = {"normal": "choice", "malformed": "malformed", "provider_timeout": "timeout"}[step["jev_assessment_fault"]]
    expected_latency = (policy["assessment"]["normal_latency_ms"] if expected_kind == "choice"
                        else policy["assessment"]["failed_or_timeout_latency_ms"])
    recorded_latency = response.get("latency_ms")
    if response["kind"] != expected_kind or (recorded_latency is not None and recorded_latency != expected_latency):
        raise ValueError("assessment schedule/resource mismatch")
    charged = {"step_id": step["step_id"], "kind": response["kind"],
               "synthetic_latency_ms": recorded_latency,
               "synthetic_cost_units": policy["assessment"]["cost_units_per_scheduled_call"]}
    if response["kind"] != "choice":
        return "uncertain", charged
    if set(response) != {"kind", "choice", "confidence", "evidence_ref_role", "latency_ms"}:
        return "uncertain", charged
    if response["choice"] not in policy["assessment"]["labels"] or type(response["confidence"]) not in (float, int):
        return "uncertain", charged
    if response["confidence"] < policy["assessment"]["confidence_threshold"] or response["evidence_ref_role"] != "after_capture":
        return "uncertain", charged
    if not fresh_after(before, after, receipt, {"objective": {"task_id": before["snapshot"]["task_id"]}}):
        return "uncertain", charged
    charged["evidence_ref"] = after["capture_id"]
    return response["choice"], charged


def run_case(case, arm, policy, assessments):
    store = FakeExecutor(case, policy)
    observer = Observer(store)
    planner = Planner()
    llm = ScriptedLLM(case)
    assessment_records = []
    reported_complete = False
    stop_reason = "attempt_limit"
    if arm == "current":
        result = run_steps(llm, store, planner, observer, case["objective"], maximum_steps=policy["maximum_attempts"])
        reported_complete = result is not None
        stop_reason = "success_flag" if reported_complete else "attempt_limit_or_error"
    else:
        planner.plan(case["objective"])
        for _ in range(min(policy["maximum_attempts"], len(case["steps"]))):
            before = observer.observe()
            proposal = llm.choose(None, before)
            reason = action_rejection(proposal, store.raw, case, policy)
            if reason is not None:
                store.reject_without_execute(proposal, reason)
                stop_reason = "host_rejected_" + reason
                break
            try:
                store.execute_tool(proposal)
            except RuntimeError:
                stop_reason = "executor_error"
                break
            receipt = store.receipts[-1]
            if receipt["status"] != "executed":
                stop_reason = "executor_contract_violation"
                break
            step = next(item for item in case["steps"] if item["step_id"] == receipt["step_id"])
            after = observer.after(before, step["observer_fault"])
            if arm == "deterministic":
                assessment = ("satisfied" if deterministic_postconditions(after["snapshot"], case["objective"]) else "unsatisfied") if fresh_after(before, after, receipt, case) else "uncertain"
                assessment_records.append({"step_id": step["step_id"], "choice": assessment, "observer_status": after["status"]})
            else:
                assessment, resource = assess_jev(step, before, after, receipt, assessments, policy)
                assessment_records.append({**resource, "choice": assessment, "observer_status": after["status"]})
            if assessment == "satisfied" and fresh_after(before, after, receipt, case):
                reported_complete = True
                stop_reason = "assessment_satisfied"
                break
            if assessment == "uncertain":
                stop_reason = "uncertain_bounded_continue"
            else:
                stop_reason = "unsatisfied_bounded_continue"
    return {
        "reported_complete": reported_complete, "stop_reason": stop_reason,
        "raw_final": deepcopy(store.raw), "trace": store.trace, "receipts": store.receipts,
        "executor_calls": store.execute_calls, "planner_calls": planner.calls,
        "assessments": assessment_records,
        "unauthorized_executor_calls": sum(
            receipt["status"] in ("rejected_wrong_task", "rejected_permission_denied")
            for receipt in store.receipts
        ) if arm == "current" else 0,
    }


def percentile95(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(95 * len(ordered) + 99) // 100 - 1]


def counterbalanced_arm_schedule(case_ids, seed):
    """Assign six seeded permutations evenly across a fixed sorted split."""
    permutations = list(itertools.permutations(("current", "deterministic", "jev")))
    random.Random(seed).shuffle(permutations)
    return {case_id: permutations[index % len(permutations)]
            for index, case_id in enumerate(sorted(case_ids))}


def evaluate(split="calibration", reviewed_digest=None):
    if split not in ("calibration", "holdout"):
        raise ValueError("unknown split")
    cases, scorer, assessments, policy = (load(name) for name in ("cases", "scorer", "assessments", "policy"))
    study = json.loads((DATA / "study-spec.json").read_text(encoding="utf-8"))
    hashes = {name: file_hash(path) for name, path in FILES.items()}
    if hashes != study["frozen_input_sha256"]:
        raise ValueError("frozen input hash mismatch")
    if split == "holdout" and (not reviewed_digest or reviewed_digest != file_hash(DATA / "study-spec.json")
                                or not scorer["reviewer_id"] or not scorer["review_date"]):
        raise ValueError("holdout requires independent review and exact study-spec digest")
    by_id = {item["id"]: item for item in scorer["labels"]}
    if len(by_id) != len(cases["cases"]) or {case["id"] for case in cases["cases"]} != set(by_id):
        raise ValueError("missing or duplicate scorer labels")
    for part in ("calibration", "holdout"):
        actual = {case["id"] for case in cases["cases"] if case["split"] == part}
        if actual != set(study["splits"][part]):
            raise ValueError("frozen case split mismatch")
    if policy["candidate"] != study["candidate"] or policy["assignment_seed"] != study["assignment_seed"]:
        raise ValueError("frozen policy mismatch")
    if set(assessments["responses"]) != {step["step_id"] for case in cases["cases"] for step in case["steps"]}:
        raise ValueError("missing or extra scheduled assessment")
    selected = [case for case in cases["cases"] if case["split"] == split]
    arm_schedule = counterbalanced_arm_schedule([case["id"] for case in selected], policy["assignment_seed"])
    rows = []
    for case in cases["cases"]:
        if case["split"] != split:
            continue
        row = {"id": case["id"], "category": case["category"],
               "arm_order": list(arm_schedule[case["id"]]), "arms": {}}
        for arm in arm_schedule[case["id"]]:
            wall_start_ns = time.perf_counter_ns()
            outcome = run_case(case, arm, policy, assessments)
            scored = score_trace(case, by_id[case["id"]], outcome["trace"], outcome["raw_final"], outcome["receipts"])
            local_wall_time_ms = round((time.perf_counter_ns() - wall_start_ns) / 1_000_000, 6)
            records = outcome["assessments"]
            row["arms"][arm] = {
                **scored,
                "reported_complete": outcome["reported_complete"],
                "false_completion": outcome["reported_complete"] and not scored["verified_completion"],
                "stop_reason": outcome["stop_reason"],
                "attempted_actions": len(outcome["trace"]),
                "executor_calls": outcome["executor_calls"],
                "unauthorized_executor_calls": outcome["unauthorized_executor_calls"],
                "planner_calls": outcome["planner_calls"],
                "assessment_count": len(records),
                "uncertain_count": sum(record["choice"] == "uncertain" for record in records),
                "synthetic_cost_units": round(sum(record.get("synthetic_cost_units", 0) for record in records), 6),
                "synthetic_latencies_ms": [record["synthetic_latency_ms"] for record in records if record.get("synthetic_latency_ms") is not None],
                "missing_latency_observations": sum(record.get("synthetic_latency_ms") is None for record in records) if arm == "jev" else 0,
                "local_runner_wall_time_ms": local_wall_time_ms,
                "assessment_records": records,
                "receipt_statuses": [receipt["status"] for receipt in outcome["receipts"]],
                "failed_episode": not scored["verified_completion"],
                "missing_or_timeout_observations": sum(record["observer_status"] in ("missing", "timeout") for record in records),
                "invalid_or_failed_assessments": sum(record.get("kind") in ("malformed", "timeout") for record in records),
            }
        rows.append(row)
    summary = {}
    for arm in ("current", "deterministic", "jev"):
        values = [row["arms"][arm] for row in rows]
        latencies = [ms for value in values for ms in value["synthetic_latencies_ms"]]
        summary[arm] = {
            "denominator": len(values),
            "verified_completion": sum(value["verified_completion"] for value in values),
            "false_completion": sum(value["false_completion"] for value in values),
            "unnecessary_continuation": sum(value["unnecessary_continuation"] for value in values),
            "safety_violations": sum(value["safety_violations"] for value in values),
            "unauthorized_executor_calls": sum(value["unauthorized_executor_calls"] for value in values),
            "failed_episodes": sum(value["failed_episode"] for value in values),
            "missing_or_timeout_observations": sum(value["missing_or_timeout_observations"] for value in values),
            "invalid_or_failed_assessments": sum(value["invalid_or_failed_assessments"] for value in values),
            "executor_calls": sum(value["executor_calls"] for value in values),
            "uncertain_terminal": sum(value["stop_reason"] == "uncertain_bounded_continue" for value in values),
            "assessment_calls": sum(value["assessment_count"] for value in values),
            "synthetic_cost_units": round(sum(value["synthetic_cost_units"] for value in values), 6),
            "synthetic_p50_latency_ms": statistics.median(latencies) if latencies else None,
            "synthetic_p95_latency_ms": percentile95(latencies),
            "missing_latency_observations": sum(value["missing_latency_observations"] for value in values),
            "local_runner_wall_time_ms_total": round(sum(value["local_runner_wall_time_ms"] for value in values), 6),
        }
    gains = {arm: summary["jev"]["verified_completion"] - summary[arm]["verified_completion"]
             for arm in ("current", "deterministic")}
    decision = "calibration_only_no_holdout_decision"
    if split == "holdout":
        limits = policy["thresholds"]
        jev = summary["jev"]
        passed = (jev["false_completion"] <= limits["maximum_false_completions"]
                  and jev["unauthorized_executor_calls"] <= limits["maximum_unauthorized_fake_executor_calls"]
                  and jev["safety_violations"] == 0
                  and jev["unnecessary_continuation"] <= limits["maximum_unnecessary_continuations"]
                  and jev["uncertain_terminal"] <= limits["maximum_uncertain_terminal_episodes"]
                  and jev["synthetic_cost_units"] <= policy["assessment"]["maximum_cost_units_holdout"]
                  and jev["missing_latency_observations"] == 0
                  and (jev["synthetic_p95_latency_ms"] or 0) <= policy["assessment"]["maximum_p95_added_latency_ms"]
                  and all(value >= limits["minimum_verified_completion_gain_over_each_comparator"] for value in gains.values()))
        decision = "synthetic_thresholds_met_live_needs_more_evidence" if passed else "disable_for_fixture"
    return {"schema_version": "coding-agent-completion-report-v1", "kind": "offline_synthetic_fixture",
            "split": split, "input_sha256": hashes, "study_spec_sha256": file_hash(DATA / "study-spec.json"),
            "source_base_commit": policy["source_base_commit"], "candidate": policy["candidate"],
            "assignment_seed": policy["assignment_seed"], "arm_order_counts": {
                "/".join(order): sum(row["arm_order"] == list(order) for row in rows)
                for order in itertools.permutations(("current", "deterministic", "jev"))
            }, "rows": rows, "summary": summary,
            "jev_verified_completion_gain": gains, "decision": decision,
            "local_fixture_wall_time_ms": round(sum(value["local_runner_wall_time_ms_total"] for value in summary.values()), 6),
            "resource_note": "Cost and assessment latency values are preset synthetic assumptions, not provider measurements. Local runner wall time is measured separately and is not an assessment-latency estimate.",
            "live_adoption": "needs_more_evidence_no_live_model_or_host_execution"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("calibration", "holdout"), default="calibration")
    parser.add_argument("--reviewed-digest")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output already exists")
    report = evaluate(args.split, args.reviewed_digest)
    with args.out.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"split": args.split, "cases": len(report["rows"]),
                      "decision": report["decision"], "report": str(args.out)}, sort_keys=True))


if __name__ == "__main__":
    main()
