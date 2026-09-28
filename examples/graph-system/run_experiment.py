"""Run the frozen, offline entity identity paired study; no external graph or model."""

import argparse
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter_ns

from entities import Entity, InMemoryGraph, reconcile


ROOT = Path(__file__).resolve().parent
FROZEN = {
    "cases.v1.json": "808af7aafbff7e4f2cc8435f37538ca59e86242ca25d3fe278e68879fcfa4cf5",
    "labels.v1.json": "57bf04656818f17a50a13f36f1c6491519ebd81170d478fd11dbc104978f37eb",
    "assessments.v1.json": "7e8f3557b3e5a39b729d6dee6343ccc9e1213339f7ae390c3046bc17a3726898",
    "study.v1.json": "e151bd5037e2dcde87a997985a19fabb3d47de324a968d3b05df8c00d44d9a19",
}
LABELS = {"same", "related", "different", "uncertain"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen():
    for filename, expected in FROZEN.items():
        if sha256(ROOT / filename) != expected:
            raise ValueError(f"frozen input changed: {filename}")
    return tuple(json.loads((ROOT / name).read_text(encoding="utf-8")) for name in FROZEN)


def deterministic(left, right):
    if left.jurisdiction != right.jurisdiction:
        return "different"
    if left.registry_id and right.registry_id:
        return "same" if left.registry_id == right.registry_id else "different"
    return "uncertain"


class FixedClassifier:
    def __init__(self, answer):
        self.answer = answer

    def classify(self, _left, _right):
        return self.answer


def wilson_upper(successes, total, z=1.959963984540054):
    if not total:
        return 1.0
    p = successes / total
    z2 = z * z
    return (p + z2 / (2 * total) + z * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total)) / (1 + z2 / total)


def run_case(case, truth, recorded, arm):
    left, right = Entity(**case["left"]), Entity(**case["right"])
    graph = InMemoryGraph(left, right, case["initial_revision"])
    raw = deterministic(left, right) if arm == "deterministic" else recorded[arm]
    failure = raw in {"timeout", "malformed"}
    assessment = raw if raw in LABELS else "uncertain"
    started = perf_counter_ns()
    receipt = reconcile(FixedClassifier(assessment), graph, left, right,
                        case["approval"], case["expected_revision"])
    elapsed_ms = (perf_counter_ns() - started) / 1_000_000
    eligible = case["approval"] is True and case["initial_revision"] == case["expected_revision"]
    expected_mutation = eligible and assessment == "same"
    if bool(receipt) != expected_mutation or len(graph.merges) != int(expected_mutation):
        raise AssertionError(f"transaction outcome mismatch: {case['id']} {arm}")
    if graph.revision != case["initial_revision"] + int(expected_mutation):
        raise AssertionError(f"revision mismatch: {case['id']} {arm}")
    if receipt and (receipt["sources"] != [left.provenance, right.provenance] or
                    receipt["revision_before"] != case["initial_revision"]):
        raise AssertionError(f"provenance mismatch: {case['id']} {arm}")
    return {
        "case_id": case["id"], "truth": truth["label"], "assessment": assessment,
        "injected_failure": raw if failure else None, "approval": case["approval"],
        "revision_current": case["initial_revision"] == case["expected_revision"],
        "eligible": eligible, "merged": bool(receipt),
        "wrong_merge": bool(receipt) and truth["label"] != "same",
        "missed_eligible_true_merge": eligible and truth["label"] == "same" and not receipt,
        "assessment_correct": assessment == truth["label"],
        "local_wall_ms": elapsed_ms,
        "simulated_cost_usd": 0.0005 if arm == "jev" else 0,
        "simulated_latency_ms": 10 if arm == "jev" else 0,
        "receipt": receipt,
    }


def summarize(rows):
    n = len(rows)
    eligible_true = sum(r["eligible"] and r["truth"] == "same" for r in rows)
    wrong = sum(r["wrong_merge"] for r in rows)
    missed = sum(r["missed_eligible_true_merge"] for r in rows)
    abstentions = sum(r["assessment"] == "uncertain" for r in rows)
    return {
        "scheduled": n, "observed": n, "wrong_merges": wrong,
        "wrong_merge_wilson_95_upper_all_scheduled": wilson_upper(wrong, n),
        "eligible_true_merges": eligible_true, "missed_eligible_true_merges": missed,
        "missed_eligible_true_merge_fraction": missed / eligible_true if eligible_true else None,
        "abstentions": abstentions, "abstention_fraction": abstentions / n,
        "injected_failures": sum(bool(r["injected_failure"]) for r in rows),
        "assessment_errors": sum(not r["assessment_correct"] for r in rows),
        "simulated_cost_usd": round(sum(r["simulated_cost_usd"] for r in rows), 6),
        "simulated_latency_ms_per_case": 10 if rows and rows[0]["simulated_latency_ms"] else 0,
        "local_wall_ms_total": round(sum(r["local_wall_ms"] for r in rows), 6),
    }


def evaluate():
    cases, labels, assessments, study = load_frozen()
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)) or set(ids) != set(labels) or set(ids) != set(assessments):
        raise ValueError("case/label/assessment coverage mismatch")
    for split in ("calibration", "holdout"):
        if [c["id"] for c in cases if c["split"] == split] != study["splits"][split]:
            raise ValueError("frozen split mismatch")
    if any(labels[c]["label"] not in LABELS for c in ids):
        raise ValueError("invalid independent label")
    holdout = [case for case in cases if case["split"] == "holdout"]
    arms = ("current", "deterministic", "jev")
    paired = {arm: [run_case(case, labels[case["id"]], assessments[case["id"]], arm)
                    for case in holdout] for arm in arms}
    summary = {arm: summarize(rows) for arm, rows in paired.items()}
    thresholds = study["thresholds"]
    j = summary["jev"]
    failures = []
    checks = (
        ("wrong merges", j["wrong_merges"] <= thresholds["max_wrong_merges"]),
        ("wrong merge uncertainty", j["wrong_merge_wilson_95_upper_all_scheduled"] <= thresholds["max_wrong_merge_wilson_95_upper"]),
        ("missed true merges", j["missed_eligible_true_merge_fraction"] <= thresholds["max_missed_eligible_true_merges_fraction"]),
        ("abstentions", j["abstention_fraction"] <= thresholds["max_abstention_fraction"]),
        ("failures", j["injected_failures"] <= thresholds["max_failures"]),
        ("simulated cost", j["simulated_cost_usd"] <= thresholds["max_simulated_cost_usd"]),
        ("simulated latency", j["simulated_latency_ms_per_case"] <= thresholds["max_simulated_latency_ms_per_case"]),
    )
    failures.extend(name for name, passed in checks if not passed)
    for arm in ("current", "deterministic"):
        if summary[arm]["missed_eligible_true_merges"] - j["missed_eligible_true_merges"] < thresholds["minimum_missed_merge_reduction_vs_each_baseline"]:
            failures.append(f"minimum improvement versus {arm}")
    return {
        "study_id": study["study_id"], "evidence_kind": "offline frozen synthetic only",
        "hashes_sha256": {name: sha256(ROOT / name) for name in FROZEN} | {
            "entities.py": sha256(ROOT / "entities.py"),
            "run_experiment.py": sha256(ROOT / "run_experiment.py")},
        "split": study["splits"], "thresholds": thresholds,
        "summary": summary, "paired_holdout": [{"case_id": case["id"],
            "arms": {arm: paired[arm][idx] for arm in arms}}
            for idx, case in enumerate(holdout)],
        "decision": "reject" if failures else "adopt_for_further_controlled_study_only",
        "failed_gates": failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"decision": report["decision"], "failed_gates": report["failed_gates"],
                      "report": str(args.out)}, sort_keys=True))


if __name__ == "__main__":
    main()
