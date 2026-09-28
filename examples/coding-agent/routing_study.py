"""Offline, synthetic comparison for issue 48. Uses an isolated fake executor."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from agent import CAPABILITY_REGISTRY_VERSION, REGISTERED_CAPABILITIES, admissible, dispatch_once

HERE = Path(__file__).resolve().parent
INPUTS = {
    "source": HERE / "agent.py",
    "cases": HERE / "routing-cases-v1.json",
    "labels": HERE / "routing-labels-v1.json",
    "proposals": HERE / "routing-proposals-v1.json",
    "study": HERE / "routing-study-v1.json",
    "runner": HERE / "routing_study.py",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    return json.loads(INPUTS[name].read_text(encoding="utf-8-sig"))


def deterministic_choice(objective):
    """Frozen conservative cue router; ambiguous or unknown requests abstain."""
    words = set(objective.lower().split())
    cues = {
        "read_file": {"read", "inspect"},
        "search_repo": {"search", "locate", "find"},
        "write_file": {"write", "save"},
    }
    matches = [name for name, terms in cues.items() if words & terms]
    return matches[0] if len(matches) == 1 else None


class FixedChoice:
    def __init__(self, choice):
        self.choice = choice

    def choose(self, objective, legal):
        return self.choice


class FakeExecutor:
    """Records calls without touching files or a real tool."""
    def __init__(self):
        self.calls = []

    def execute_tool(self, name, *arguments):
        self.calls.append({"name": name, "arguments": list(arguments)})
        return type("Result", (), {"exit_code": 0})()


def historical_dispatch(choice, registry, executor):
    """Exact original fixture semantics: model choice, membership, then execute."""
    if choice in registry:
        return executor.execute_tool(choice).exit_code == 0
    return False


def check_fake_calls(arm, choice, registry, admitted, original_arguments, calls):
    """Assert recorded effects independently of the router and admission prediction."""
    should_call = (isinstance(choice, str) and choice in registry) if arm == "current" else admitted
    expected = ([{"name": choice, "arguments": [] if arm == "current" else [original_arguments]}]
                if should_call else [])
    if calls != expected:
        raise ValueError(f"fake executor postcondition failed for {arm}")


def evaluate():
    cases, labels, proposals, study = (load(name) for name in ("cases", "labels", "proposals", "study"))
    frozen = study["frozen_input_sha256"]
    if set(frozen) != set(INPUTS) - {"study"} or any(digest(INPUTS[name]) != expected for name, expected in frozen.items()):
        raise ValueError("frozen input hash mismatch")
    if study["registry_version"] != CAPABILITY_REGISTRY_VERSION:
        raise ValueError("registry version mismatch")
    case_ids = [case["id"] for case in cases["cases"]]
    if len(case_ids) != len(set(case_ids)) or set(case_ids) != set(labels["labels"]):
        raise ValueError("duplicate or missing case labels")
    if any(set(case) - {"id", "split", "objective", "arguments", "permissions", "registered"} for case in cases["cases"]):
        raise ValueError("case input contains oracle fields")
    for split in ("calibration", "holdout"):
        if set(study["splits"][split]) != {case["id"] for case in cases["cases"] if case["split"] == split}:
            raise ValueError("split mismatch")
    for arm in ("current", "jev"):
        if set(proposals["arms"][arm]) != set(case_ids):
            raise ValueError("missing or extra comparator proposals")
    rows = []
    for case in cases["cases"]:
        if case["split"] != "holdout":
            continue
        if len(case["registered"]) != len(set(case["registered"])) or any(name not in REGISTERED_CAPABILITIES for name in case["registered"]):
            raise ValueError("invalid registry snapshot")
        registry = {name: REGISTERED_CAPABILITIES[name] for name in case["registered"]}
        label = labels["labels"][case["id"]]["route"]
        if label is not None and not admissible(label, registry, case["arguments"], case["permissions"]):
            raise ValueError("independent label fails host postcondition")
        row = {"id": case["id"], "expected_route": label, "label_postcondition": labels["labels"][case["id"]]["postcondition"], "arms": {}}
        for arm in ("current", "deterministic", "jev", "guarded_current"):
            source_arm = "current" if arm == "guarded_current" else arm
            raw = (deterministic_choice(case["objective"]) if arm == "deterministic" else proposals["arms"][source_arm][case["id"]])
            invalid = False
            failure = False
            if arm == "jev":
                if not isinstance(raw, dict) or set(raw) != {"choice", "confidence"} or type(raw["confidence"]) not in (float, int) or not 0 <= raw["confidence"] <= 1:
                    choice, failure = None, True
                else:
                    choice = raw["choice"] if raw["confidence"] >= study["choice_threshold"] else None
            else:
                choice = raw
            if choice is not None and (not isinstance(choice, str) or choice not in registry):
                invalid = True
            original_arguments = deepcopy(case["arguments"])
            executor = FakeExecutor()
            if arm == "current":
                historical_dispatch(choice, registry, executor)
            else:
                dispatch_once(FixedChoice(choice), executor, case["objective"], registry,
                              arguments=case["arguments"], granted_permissions=case["permissions"])
            observed = [call["name"] for call in executor.calls]
            if len(observed) > 1:
                raise ValueError("fake executor called more than once")
            effective = observed[0] if observed else None
            admitted = bool(choice is not None and admissible(choice, registry, case["arguments"], case["permissions"]))
            check_fake_calls(arm, choice, registry, admitted, original_arguments, executor.calls)
            safety_violation = effective is not None and not admitted
            row["arms"][arm] = {
                "proposal": choice, "effective_route": effective, "correct": effective == label,
                "wrong_tool": effective is not None and effective != label,
                "unnecessary_abstention": effective is None and label is not None,
                "invalid_output": invalid, "failure": failure,
                "guard_rejection": choice is not None and not admitted and effective is None,
                "unsafe_fake_dispatch": safety_violation,
                "fake_executor_calls": executor.calls,
            }
        rows.append(row)
    limits = study["limits"]
    summary = {}
    for arm in ("current", "deterministic", "jev", "guarded_current"):
        metrics = {name: sum(int(row["arms"][arm][name]) for row in rows) for name in ("correct", "wrong_tool", "unnecessary_abstention", "invalid_output", "failure", "guard_rejection", "unsafe_fake_dispatch")}
        metrics["fake_executor_invocations"] = sum(len(row["arms"][arm]["fake_executor_calls"]) for row in rows)
        resource = study["resource_accounting"]["current" if arm == "guarded_current" else arm]
        metrics.update({"denominator": len(rows), "synthetic_p95_latency_ms": resource["latency_ms_per_case"], "synthetic_total_cost_units": round(len(rows) * resource["cost_units_per_case"], 6)})
        summary[arm] = metrics
    jev = summary["jev"]
    pass_limits = (jev["wrong_tool"] <= limits["maximum_wrong_tool"]
                   and jev["unnecessary_abstention"] <= limits["maximum_unnecessary_abstentions"]
                   and jev["unsafe_fake_dispatch"] <= limits["maximum_invalid_or_unauthorized_dispatches"]
                   and jev["synthetic_p95_latency_ms"] <= limits["maximum_p95_latency_ms"]
                   and jev["synthetic_total_cost_units"] <= limits["maximum_total_cost_units"])
    gain = {arm: jev["correct"] - summary[arm]["correct"] for arm in ("current", "deterministic")}
    decision = "synthetic_thresholds_met_no_activation_authority" if pass_limits and all(value >= limits["minimum_correct_gain_over_each_comparator"] for value in gain.values()) else "disable_for_fixture_no_incremental_evidence"
    return {
        "schema_version": "coding-agent-routing-report-v1", "kind": "offline_synthetic_fixture",
        "issue": 48, "source_base_commit": study["source_base_commit"],
        "input_sha256": {name: digest(path) for name, path in INPUTS.items()},
        "frozen_hashes_verified": True,
        "registry_version": CAPABILITY_REGISTRY_VERSION, "rubric_version": study["rubric_version"],
        "policy_version": study["policy_version"], "assignment_seed": study["assignment_seed"],
        "split": "holdout", "thresholds": limits,
        "resource_status": study["resource_accounting"]["status"],
        "local_fixture_wall_time_ms": None,
        "local_fixture_wall_time_status": "unknown; no wall-time measurement recorded",
        "outcomes": rows, "summary": summary, "jev_correct_gain": gain,
        "stop_rule": study["stop_rule"], "decision": decision,
        "limits": "Manual synthetic proposals are not live model measurements; only isolated fake executor calls were made, with no real tool or provider invocation.",
        "failure_coverage_limit": "The frozen holdout schedules no timeout or provider failure; separate unit tests verify fail-closed router exceptions.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output already exists")
    report = evaluate()
    with args.out.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"report": str(args.out), "decision": report["decision"], "holdout_cases": len(report["outcomes"])}, sort_keys=True))


if __name__ == "__main__":
    main()
