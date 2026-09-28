"""Three-arm offline synthetic retention fixture; never touches user history."""

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

from agent import retain_history
from retention_oracle import raw_postconditions, score_recall


HERE = Path(__file__).resolve().parent
DATA = HERE / "retention"
ROOT = HERE.parent.parent
FILES = {
    "source": HERE / "agent.py",
    "runner": HERE / "retention_study.py",
    "oracle": HERE / "retention_oracle.py",
    "histories": DATA / "histories.json",
    "reader_questions": DATA / "reader-questions.json",
    "scorer": DATA / "scorer-only.json",
    "proposals": DATA / "synthetic-proposals.json",
    "injections": DATA / "injection-schedule.json",
    "attacks": DATA / "attack-proposals.json",
    "projection": DATA / "projection-contract.json",
    "policy": DATA / "policy.json",
    "report_schema": ROOT / "schemas" / "coding-agent-retention-report-v1.schema.json",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    return json.loads(FILES[name].read_text(encoding="utf-8"))


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, (int(fraction * len(values) + 0.999999) - 1))]


def chooser_projection(case, contract):
    keys = contract["chooser"]["exact_top_level_keys"]
    if set(keys) != {"visible_task", "mode", "token_budget", "revision", "items", "pins", "supersession"}:
        raise ValueError("chooser projection contract drift")
    projection = {key: deepcopy(case[key]) for key in keys if key != "items"}
    item_keys = contract["chooser"]["item_keys"]
    projection["items"] = [{key: deepcopy(item[key]) for key in item_keys} for item in case["items"]]
    if set(projection) != set(keys):
        raise ValueError("chooser projection shape")
    if any(set(item) != set(item_keys) for item in projection["items"]):
        raise ValueError("chooser item projection shape")
    return projection


class FakeMemory:
    """Isolated fake memory with raw readback and a guarded CAS transaction."""

    def __init__(self, case):
        self.case = case
        self.items = deepcopy(case["items"])
        self.revision = case["revision"]
        self.mode = case["mode"]
        self.token_budget = case["token_budget"]
        self.pins = deepcopy(case["pins"])
        self.backend_calls = 0
        self.committed = False
        self.rollback_count = 0

    def load(self):
        return deepcopy(self.items)

    def prune(self, choice, budget):
        """Historical memory interface: faithfully accepts chosen IDs and count budget."""
        self.backend_calls += 1
        if not isinstance(choice, list) or any(type(item_id) is not str for item_id in choice):
            raise ValueError("historical choice shape")
        retained = [item for item in self.items if item["id"] in choice]
        self.items = deepcopy(retained)
        self.revision += 1
        self.committed = True
        return self.load()

    def guarded_commit(self, selected_ids, expected_revision, expected_digest,
                       expected_mode, expected_budget, expected_pins, fault):
        """CAS, one staged write, independent readback, exact rollback on false success."""
        preimage = self.load()
        pre_revision = self.revision
        initial_digest = hashlib.sha256(json.dumps(preimage, sort_keys=True).encode()).hexdigest()
        if (self.revision != expected_revision or initial_digest != expected_digest
                or self.mode != expected_mode or self.token_budget != expected_budget
                or self.pins != expected_pins):
            return "stale_memory"
        if len(selected_ids) != len(set(selected_ids)) or not set(selected_ids) <= {item["id"] for item in preimage}:
            return "invalid_selection"
        if not {pin["id"] for pin in self.pins} <= set(selected_ids):
            return "missing_pin"
        target = [item for item in preimage if item["id"] in selected_ids]
        if sum(item["token_count"] for item in target) > self.token_budget:
            return "over_budget_selection"
        self.backend_calls += 1
        if fault["kind"] == "fake_write_false_success_partial":
            self.items = deepcopy(target[:1])
        else:
            self.items = deepcopy(target)
        self.revision += 1
        readback = self.load()
        if (readback != target or self.revision != pre_revision + 1 or
                self.mode != expected_mode or self.token_budget != expected_budget or
                self.pins != expected_pins):
            self.items = preimage
            self.revision = pre_revision
            self.rollback_count += 1
            return "failed_readback_rolled_back"
        self.committed = True
        return "committed"


class HistoricalLLM:
    def __init__(self, ids):
        self.ids = ids
        self.calls = 0

    def choose(self, entries):
        self.calls += 1
        return deepcopy(self.ids)


def deterministic_ids(case):
    pins = {pin["id"] for pin in case["pins"]}
    selected = set(pins)
    used = sum(item["token_count"] for item in case["items"] if item["id"] in pins)
    for item in reversed(case["items"]):
        if item["id"] not in pins and used + item["token_count"] <= case["token_budget"]:
            selected.add(item["id"])
            used += item["token_count"]
    return selected


def guarded(case, arm, proposal, fault, attack, projection_contract):
    store = FakeMemory(case)
    view = chooser_projection(case, projection_contract)
    if set(view) != set(projection_contract["chooser"]["exact_top_level_keys"]):
        raise ValueError("chooser leak")
    assessments = []
    mode = view["mode"]
    if mode != "/prune":
        # Attacks enter this guarded host API, never the backend store.
        if attack is not None and attack["boundary"] not in ("mode_argument", "guarded_host_api_prune_request"):
            raise ValueError("unknown attack boundary")
        return store, "requires_separate_compaction" if mode == "/compact" else "invalid_mode", assessments
    pins = {pin["id"] for pin in view["pins"]}
    pin_tokens = sum(item["token_count"] for item in view["items"] if item["id"] in pins)
    if pin_tokens > view["token_budget"]:
        return store, "insufficient_budget", assessments
    unpinned = [item for item in view["items"] if item["id"] not in pins]
    if arm == "jev" and len(unpinned) > 12:
        return store, "assessment_limit_exceeded", assessments
    if arm == "deterministic":
        selected = deterministic_ids(view)
    else:
        if proposal is None:
            raise ValueError("missing JEV proposal")
        binding = proposal["jev_input_binding"]
        digest = hashlib.sha256(json.dumps(case["items"], sort_keys=True).encode()).hexdigest()
        if binding != {"revision": view["revision"], "items_sha256": digest}:
            return store, "stale_assessment_binding", assessments
        responses = proposal["jev_per_item"]
        if set(responses) != {item["id"] for item in unpinned}:
            raise ValueError("missing or extra scheduled assessment")
        selected = set(pins)
        for item in unpinned:
            response = responses[item["id"]]
            latency = response.get("latency_ms")
            if latency not in (18, 30, 45, None) or response.get("cost_units") != 0.003:
                raise ValueError("assessment resource schedule mismatch")
            label = response.get("label")
            expected_latency = (45 if response.get("fault") == "late" else
                                30 if label in ("timeout", "malformed") else 18)
            if latency is not None and latency != expected_latency:
                raise ValueError("assessment latency/failure mismatch")
            if label not in ("keep", "drop") or type(response.get("confidence")) not in (float, int) or response["confidence"] < 0.8 or latency is None or latency > 30:
                label = "uncertain"
            assessments.append({"item_id": item["id"], "choice": label, "synthetic_latency_ms": latency,
                                "charged_latency_ms": latency if latency is not None else 30,
                                "synthetic_cost_units": 0.003, "fault_kind": response.get("label") if label == "uncertain" else None})
            if label in ("keep", "uncertain"):
                selected.add(item["id"])
    selected_tokens = sum(item["token_count"] for item in view["items"] if item["id"] in selected)
    if selected_tokens > view["token_budget"]:
        return store, "needs_review", assessments
    revision = view["revision"]
    if fault["kind"] == "revision_change_before_commit":
        store.revision = fault["new_revision"]
    expected_digest = case["fake_memory_initial_digest"]
    if fault["kind"] == "stale_proposal_revision":
        revision = fault["proposal_revision"]
    status = store.guarded_commit(selected, revision, expected_digest,
                                  view["mode"], view["token_budget"], view["pins"], fault)
    return store, status, assessments


def run_case(case, arm, proposal, fault, attack, question, scorer, projection_contract):
    started = time.perf_counter_ns()
    if arm == "current":
        if case["mode"] != "/prune":
            raise ValueError("historical arm has mode N/A")
        store = FakeMemory(case)
        llm = HistoricalLLM(proposal["historical_keep_ids"])
        retain_history(llm, store, case["legacy_count_budget"])
        status = "historical_choice" if store.backend_calls else "historical_no_prune"
        assessments = []
    else:
        store, status, assessments = guarded(case, arm, proposal, fault, attack, projection_contract)
        llm = None
    readback = store.load()
    raw = raw_postconditions(case, readback, store.committed, case["mode"], case["token_budget"])
    missing_reader = fault["kind"] == "reader_missing_result"
    recall = score_recall(question, scorer, readback, missing_reader=missing_reader)
    task_success = (recall["success"] is True and case["mode"] == "/prune" and
                    status in ("committed", "historical_choice", "historical_no_prune") and
                    not any(raw[key] for key in ("pin_loss", "byte_or_provenance_loss", "over_budget_commit")) and
                    raw["retained_tokens"] <= case["token_budget"])
    # The reader receives only a newly constructed allowlisted projection inside score_recall.
    local_ms = round((time.perf_counter_ns() - started) / 1_000_000, 6)
    return {"status": status, "backend_calls": store.backend_calls, "rollback_count": store.rollback_count,
            "committed": store.committed, "historical_choice_calls": llm.calls if llm else 0,
            "assessment_count": len(assessments), "assessment_records": assessments,
            "synthetic_cost_units": round(sum(a["synthetic_cost_units"] for a in assessments), 6),
            "synthetic_episode_latency_ms": sum(a["charged_latency_ms"] for a in assessments),
            "missing_latency_observations": sum(a["synthetic_latency_ms"] is None for a in assessments),
            "local_runner_wall_time_ms": local_ms, **raw, "recall": recall,
            "later_task_success": task_success}


def arm_orders(ids, seed, arms):
    permutations = list(itertools.permutations(arms))
    random.Random(seed).shuffle(permutations)
    return {case_id: permutations[index % len(permutations)] for index, case_id in enumerate(sorted(ids))}


def evaluate(split="calibration", reviewed_digest=None):
    if split not in ("calibration", "holdout"):
        raise ValueError("unknown split")
    spec = json.loads((DATA / "study-spec.json").read_text(encoding="utf-8"))
    hashes = {name: sha(path) for name, path in FILES.items()}
    if hashes != spec["frozen_input_sha256"]:
        raise ValueError("frozen input hash mismatch")
    scorer_data = load("scorer")
    if split == "holdout" and (reviewed_digest != sha(DATA / "study-spec.json") or
                               not all(row["reviewer_id"] and row["review_date"] for row in scorer_data["labels"])):
        raise ValueError("holdout requires independent scorer review and exact spec digest")
    histories = load("histories")["cases"]
    questions = {x["case_id"]: x for x in load("reader_questions")["questions"]}
    labels = {x["case_id"]: x for x in scorer_data["labels"]}
    proposals = {x["case_id"]: x for x in load("proposals")["proposals"]}
    faults = {x["case_id"]: x["fault"] for x in load("injections")["injections"]}
    attacks = {x["case_id"]: x for x in load("attacks")["attacks"]}
    contract = load("projection")
    if (set(contract["reader"]["exact_top_level_keys"]) != {"question", "retained_items"} or
            set(contract["reader"]["item_keys"]) != {"id", "text", "byte_sha256", "source_kind", "source_ref", "capture_revision"}):
        raise ValueError("reader projection contract drift")
    policy = load("policy")
    if policy["resource_schedule"] != {
            "normal_latency_ms": 18, "timeout_or_malformed_latency_ms": 30,
            "late_latency_ms": 45, "missing_latency_charge_ms": 30,
            "cost_units_per_scheduled_assessment": 0.003}:
        raise ValueError("frozen resource schedule mismatch")
    if set(questions) != {x["id"] for x in histories} or set(labels) != set(questions) or set(faults) != set(questions):
        raise ValueError("missing case companion")
    for part in ("calibration", "holdout"):
        if set(spec["splits"][part]) != {x["id"] for x in histories if x["split"] == part}:
            raise ValueError("frozen split mismatch")
    selected = [case for case in histories if case["split"] == split]
    efficacy_ids = [case["id"] for case in selected if case["mode"] == "/prune"]
    mode_ids = [case["id"] for case in selected if case["mode"] != "/prune"]
    efficacy_orders = arm_orders(efficacy_ids, policy["assignment_seed"], ("current", "deterministic", "jev"))
    mode_orders = arm_orders(mode_ids, policy["assignment_seed"], ("deterministic", "jev"))
    rows = []
    for case in selected:
        case_id = case["id"]
        order = efficacy_orders.get(case_id) or mode_orders[case_id]
        row = {"id": case_id, "category": case["category"], "mode": case["mode"],
               "arm_order": list(order), "arms": {}}
        for arm in order:
            row["arms"][arm] = run_case(case, arm, proposals.get(case_id), faults[case_id],
                                         attacks.get(case_id), questions[case_id]["question"], labels[case_id], contract)
        if case["mode"] != "/prune":
            row["arms"]["current"] = {"status": "not_applicable_no_historical_mode"}
        rows.append(row)
    summaries = {}
    for arm in ("current", "deterministic", "jev"):
        applicable = [row["arms"][arm] for row in rows if row["mode"] == "/prune"]
        safety = [row["arms"][arm] for row in rows if arm != "current" or row["mode"] == "/prune"]
        latencies = [record["charged_latency_ms"] for outcome in applicable for record in outcome["assessment_records"]]
        episodes = [outcome["synthetic_episode_latency_ms"] for outcome in applicable]
        summaries[arm] = {
            "efficacy_denominator": len(applicable), "safety_denominator": len(safety),
            "later_task_success": sum(outcome["later_task_success"] for outcome in applicable),
            "unresolved_contradiction_errors": sum(
                labels[row["id"]]["contradiction_rule"] == "cite_both_and_report_unresolved" and
                row["arms"][arm]["recall"]["success"] is False
                for row in rows if row["mode"] == "/prune"),
            "missing_reader_outcomes": sum(outcome["recall"]["missing"] for outcome in applicable),
            "pin_loss": sum(outcome["pin_loss"] for outcome in safety),
            "byte_or_provenance_loss": sum(outcome["byte_or_provenance_loss"] for outcome in safety),
            "over_budget_commits": sum(outcome["over_budget_commit"] for outcome in safety),
            "wrong_mode_mutations": sum(outcome["wrong_mode_mutation"] for outcome in safety),
            "backend_calls": sum(outcome["backend_calls"] for outcome in safety),
            "assessment_calls": sum(outcome["assessment_count"] for outcome in applicable),
            "missing_latency_observations": sum(outcome["missing_latency_observations"] for outcome in applicable),
            "synthetic_cost_units": round(sum(outcome["synthetic_cost_units"] for outcome in applicable), 6),
            "per_call_p50_ms": statistics.median(latencies) if latencies else None,
            "per_call_p95_ms": percentile(latencies, .95),
            "per_episode_p50_ms": statistics.median(episodes) if episodes else None,
            "per_episode_p95_ms": percentile(episodes, .95),
            "local_runner_wall_time_ms_total": round(sum(outcome["local_runner_wall_time_ms"] for outcome in safety), 6),
        }
    paired = {other: {
        "rescues": sum(row["arms"]["jev"]["later_task_success"] and not row["arms"][other]["later_task_success"]
                       for row in rows if row["mode"] == "/prune"),
        "regressions": sum(row["arms"][other]["later_task_success"] and not row["arms"]["jev"]["later_task_success"]
                           for row in rows if row["mode"] == "/prune"),
    } for other in ("current", "deterministic")}
    decision = "calibration_only_no_holdout_decision"
    if split == "holdout":
        jev = summaries["jev"]
        thresholds = policy["thresholds"]
        pass_gate = (jev["pin_loss"] == 0 and jev["byte_or_provenance_loss"] == 0 and
                     jev["over_budget_commits"] == 0 and jev["wrong_mode_mutations"] == 0 and
                     jev["synthetic_cost_units"] <= thresholds["max_holdout_cost_units"] and
                     jev["missing_latency_observations"] == 0 and
                     all(row["arms"]["jev"]["synthetic_cost_units"] <= thresholds["max_cost_units_per_episode"]
                         for row in rows if row["mode"] == "/prune") and
                     (jev["per_call_p95_ms"] or 0) <= thresholds["max_per_call_p95_ms"] and
                     (jev["per_episode_p95_ms"] or 0) <= thresholds["max_per_episode_p95_ms"] and
                     jev["unresolved_contradiction_errors"] <= summaries["deterministic"]["unresolved_contradiction_errors"] + thresholds["max_contradiction_error_increase"] and
                     paired["deterministic"]["regressions"] <= thresholds["max_extra_later_task_failures_vs_deterministic"] and
                     all(jev["later_task_success"] - summaries[arm]["later_task_success"] >=
                         thresholds["min_success_gain_each_comparator"] for arm in ("current", "deterministic")))
        decision = "synthetic_gates_met_live_needs_more_evidence" if pass_gate else "disable_for_fixture"
    return {"schema_version": "coding-agent-retention-report-v1", "kind": "offline_synthetic_fixture",
            "split": split, "candidate": policy["candidate"], "source_base_commit": policy["source_base_commit"],
            "input_sha256": hashes, "study_spec_sha256": sha(DATA / "study-spec.json"),
            "assignment_seed": policy["assignment_seed"], "rows": rows, "summary": summaries,
            "jev_paired_effects": paired,
            "decision": decision, "resource_note": "Costs and assessment latency are preset synthetic assumptions; local runner wall time is measured separately.",
            "comparison_note": "Historical retain_history uses an item-count threshold and its original chooser/prune interface; guarded arms enforce a token budget. Retained counts and tokens are reported separately.",
            "live_adoption": "not_authorized_no_real_history_or_provider"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("calibration", "holdout"), default="calibration")
    parser.add_argument("--reviewed-digest")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output already exists")
    report = evaluate(args.split, args.reviewed_digest)
    with args.out.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"split": args.split, "cases": len(report["rows"]), "decision": report["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
