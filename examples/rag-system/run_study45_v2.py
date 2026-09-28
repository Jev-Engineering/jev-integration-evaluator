"""New untouched v2 holdout with separately frozen synthetic oracle labels."""

import argparse
import hashlib
import json
from pathlib import Path
import time

import run_study45 as v1


ROOT = Path(__file__).resolve().parent
FILES = {"cases": ROOT / "study45_v2_cases.json",
         "labels": ROOT / "study45_v2_labels.json",
         "predictions": ROOT / "study45_v2_predictions.json"}
FROZEN_SHA256 = {
    "cases": "38fc79c772ea88f11f8468b4a581f89c7a228ef2ada1a696ea76d8983c0d216d",
    "labels": "a935221bfa4925d063947326ff68ca7216b93d70e262385fa575d3c82ba2f1f4",
    "predictions": "2eec149bc291117b57955a68f62fde97cc4b441027d03355a932375b9dfed5ab",
}


class FrozenAssessor:
    def __init__(self, response, limits):
        self.response = response
        self.limits = limits
        self.calls = 0

    def assess(self, query, passages):
        self.calls += 1
        if self.response["simulated_latency_ms"] > self.limits["max_simulated_assessor_latency_ms_per_case"]:
            raise TimeoutError("simulated latency cap")
        if self.response["simulated_cost_usd"] > self.limits["max_simulated_assessor_cost_usd_per_case"]:
            raise RuntimeError("simulated cost cap")
        if self.response.get("failure") == "timeout":
            raise TimeoutError("scheduled synthetic timeout")
        if self.response.get("failure") == "missing":
            return None
        return self.response["labels"]


def evaluate(pipeline, case, gold, response, arm, limits):
    passages = tuple(pipeline.Passage(*row) for row in case["passages"])
    generator = v1.FixtureGenerator(pipeline)
    assessor = FrozenAssessor(response, limits)
    start = time.perf_counter_ns()
    try:
        result = pipeline.answer_with_evidence(v1.Retriever(passages), generator, case["query"],
                                               policy=arm, assessor=assessor if arm == "jev" else None)
        selected = [p.passage_id for p in result.evidence.passages]
        decisions = dict(result.evidence.decisions)
        answer = result.answer or {"status": "abstain", "citations": []}
        status = result.evidence.status
        citation_correct = all(sum(p.passage_id == citation for p in passages) == 1
                               and citation in selected for citation in answer["citations"])
    except Exception:
        selected, decisions, answer, status, citation_correct = (
            [], {}, {"status": "failure", "citations": []}, "failure", False)
    local_elapsed_ns = time.perf_counter_ns() - start
    success = (status in {"ready", "insufficient"} and citation_correct
               and answer["status"] == gold["expected"]
               and ("citation" not in gold or gold["citation"] in answer["citations"])
               and ("conflict" not in gold or gold["conflict"] in answer["citations"]))
    return {"case_id": case["id"], "arm": arm, "evidence_status": status,
            "passage_labels": {p.passage_id: {"independent_relevant": p.passage_id in gold["relevant"],
                                                "assessment": decisions.get(p.passage_id),
                                                "selected": p.passage_id in selected} for p in passages},
            "selected_ids": selected, "answer": answer, "expected_answer": gold,
            "answer_success": success, "citation_correct": citation_correct,
            "contradiction_omitted": bool(gold.get("conflict") and gold["conflict"] not in answer["citations"]),
            "assessor_calls": assessor.calls, "generator_calls": generator.calls,
            "simulated_assessor_latency_ms": response["simulated_latency_ms"] if arm == "jev" else None,
            "simulated_assessor_cost_usd": response["simulated_cost_usd"] if arm == "jev" else None,
            "latency_limit_violated": arm == "jev" and response["simulated_latency_ms"] > limits["max_simulated_assessor_latency_ms_per_case"],
            "cost_limit_violated": arm == "jev" and response["simulated_cost_usd"] > limits["max_simulated_assessor_cost_usd_per_case"],
            "local_elapsed_ns": local_elapsed_ns}


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    observed_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in FILES.items()}
    if observed_hashes != FROZEN_SHA256:
        raise ValueError("reviewed v2 study inputs changed before execution")
    data = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in FILES.items()}
    cases = data["cases"]
    labels = data["labels"]["labels"]
    predictions = data["predictions"]
    ids = [case["id"] for case in cases["cases"]]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(cases["calibration_ids"] + cases["holdout_ids"])
    assert set(ids) == set(labels) == set(predictions["responses"])
    assert all(data[name]["study_id"] == cases["study_id"] for name in data)
    for case in cases["cases"]:
        passage_ids = {row[0] for row in case["passages"]}
        gold = labels[case["id"]]
        assert len(passage_ids) == len(case["passages"])
        assert set(gold["relevant"]) <= passage_ids
        assert all(gold[key] in passage_ids for key in ("citation", "conflict") if key in gold)
    pipeline = v1.load_pipeline()
    rows = [evaluate(pipeline, case, labels[case["id"]], predictions["responses"][case["id"]],
                     arm, predictions["limits"])
            for case in cases["cases"] for arm in predictions["arms"]]
    holdout = [row for row in rows if row["case_id"] in cases["holdout_ids"]]
    summary = {}
    for arm in predictions["arms"]:
        group = [row for row in holdout if row["arm"] == arm]
        summary[arm] = {"n": len(group), "answer_success": sum(row["answer_success"] for row in group),
                        "failed_or_missing": sum(row["evidence_status"] in {"failure", "assessment_failed"} for row in group),
                        "contradiction_omissions": sum(row["contradiction_omitted"] for row in group),
                        "assessor_calls": sum(row["assessor_calls"] for row in group),
                        "generator_calls": sum(row["generator_calls"] for row in group),
                        "latency_limit_violations": sum(row["latency_limit_violated"] for row in group),
                        "cost_limit_violations": sum(row["cost_limit_violated"] for row in group),
                        "local_elapsed_ns": sum(row["local_elapsed_ns"] for row in group)}
    threshold = predictions["minimum_useful_effect"]
    gain = (summary["jev"]["answer_success"] - summary["lexical"]["answer_success"]) / len(cases["holdout_ids"])
    jev = summary["jev"]
    screen_pass = (gain >= threshold["answer_success_gain_over_lexical"]
                   and jev["failed_or_missing"] <= threshold["max_missing_or_failed_outcomes"]
                   and jev["contradiction_omissions"] <= threshold["max_contradiction_omissions"]
                   and jev["cost_limit_violations"] <= threshold["max_cost_limit_violations"]
                   and jev["latency_limit_violations"] <= threshold["max_latency_limit_violations"]
                   and jev["assessor_calls"] <= len(cases["holdout_ids"]) * predictions["limits"]["max_assessor_calls_per_case"]
                   and jev["generator_calls"] <= len(cases["holdout_ids"]) * predictions["limits"]["max_generator_calls_per_case"])
    source_paths = list(FILES.values()) + [ROOT / "pipeline.py", ROOT / "run_study45.py", Path(__file__)]
    report = {"study_id": cases["study_id"], "evidence_kind": "offline_synthetic_fixture",
              "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
              "seed": cases["seed"], "assignment_unit": cases["assignment_unit"],
              "calibration_ids": cases["calibration_ids"], "holdout_ids": cases["holdout_ids"],
              "label_provenance": data["labels"]["label_provenance"],
              "adjudication_rule": data["labels"]["adjudication_rule"],
              "rubric": predictions["rubric"], "generator_rule": predictions["generator_rule"],
              "limits": predictions["limits"], "threshold": threshold, "stop_rule": predictions["stop_rule"],
              "rows": rows, "holdout_summary": summary, "jev_gain_over_lexical": gain,
              "screen_decision": "pass_synthetic_screen" if screen_pass else "reject_on_frozen_synthetic_threshold",
              "adoption_decision": "reject_adoption_from_synthetic_evidence",
              "next_evidence": "needs_independent_real_task_and_provider_observation",
              "limits_of_inference": "Fixture predictions, costs and latency are authored simulations. Local elapsed time is Python runtime only. No provider, real retrieval, real answer quality, model cost or model latency measured. Labels have no independent human adjudication."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"report": str(args.out), "holdout_summary": summary,
                      "screen_decision": report["screen_decision"],
                      "adoption_decision": report["adoption_decision"]}, sort_keys=True))


if __name__ == "__main__":
    run()
