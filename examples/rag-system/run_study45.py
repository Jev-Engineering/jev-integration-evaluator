"""Frozen, offline synthetic passage-selection experiment for issue #45."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "study45.json"
PIPELINE = ROOT / "pipeline.py"


def load_pipeline():
    import sys
    spec = importlib.util.spec_from_file_location("rag_study45_pipeline", PIPELINE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Retriever:
    def __init__(self, passages):
        self.passages = passages

    def retrieve(self, query):
        return self.passages


class Assessor:
    def __init__(self, labels):
        self.labels = labels
        self.calls = 0

    def assess(self, query, passages):
        self.calls += 1
        return dict(self.labels)


class FixtureGenerator:
    """Fixed answer consumer; its outputs are synthetic, never model quality."""

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.calls = 0

    def generate(self, query, bundle):
        self.calls += 1
        passages = bundle.passages if isinstance(bundle, self.pipeline.EvidenceBundle) else bundle
        first = next((p for p in passages if p.stance == "supports"), None)
        if first is None:
            return {"status": "abstain", "citations": []}
        conflicts = [p for p in passages if p.claim_id == first.claim_id and p.stance == "contradicts"]
        return {"status": "conflicted" if conflicts else "supported",
                "citations": [first.passage_id] + [p.passage_id for p in conflicts]}


def evaluate_case(pipeline, case, arm):
    passages = tuple(pipeline.Passage(*row) for row in case["passages"])
    generator = FixtureGenerator(pipeline)
    assessor = Assessor(case["assess"])
    start = time.perf_counter_ns()
    try:
        result = pipeline.answer_with_evidence(Retriever(passages), generator, case["query"],
                                               policy=arm, assessor=assessor if arm == "jev" else None)
        answer = result.answer or {"status": "abstain", "citations": []}
        selected = [p.passage_id for p in result.evidence.passages]
        decisions = dict(result.evidence.decisions)
        status = result.evidence.status
        # A citation must identify exactly one original retrieved passage.
        citation_correct = all(sum(p.passage_id == citation for p in passages) == 1
                               and citation in selected for citation in answer["citations"])
    except Exception:
        answer, selected, decisions, status, citation_correct = (
            {"status": "failure", "citations": []}, [], {}, "failure", False)
    elapsed_ns = time.perf_counter_ns() - start
    gold = case["gold"]
    answer_success = (status in {"ready", "insufficient"} and answer["status"] == gold["expected"]
                      and citation_correct and
                      (gold.get("citation") is None or gold["citation"] in answer["citations"])
                      and (gold.get("conflict") is None or gold["conflict"] in answer["citations"]))
    return {"case_id": case["id"], "arm": arm, "selected_ids": selected,
            "passage_labels": {p.passage_id: {"independent_relevant": p.passage_id in gold["relevant"],
                                                "assessment": decisions.get(p.passage_id),
                                                "selected": p.passage_id in selected} for p in passages},
            "evidence_status": status, "answer": answer, "expected_answer": gold,
            "answer_success": answer_success,
            "contradiction_omitted": bool(gold.get("conflict") and gold["conflict"] not in answer["citations"]),
            "citation_correct": citation_correct, "generator_calls": generator.calls,
            "assessor_calls": assessor.calls, "local_elapsed_ns": elapsed_ns,
            "simulated_model_cost": None}


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    assert {c["id"] for c in spec["cases"]} == set(spec["calibration_ids"] + spec["holdout_ids"])
    pipeline = load_pipeline()
    rows = [evaluate_case(pipeline, case, arm) for case in spec["cases"]
            for arm in ("current", "lexical", "jev")]
    holdout = [r for r in rows if r["case_id"] in spec["holdout_ids"]]
    summary = {}
    for arm in ("current", "lexical", "jev"):
        group = [r for r in holdout if r["arm"] == arm]
        summary[arm] = {"n": len(group), "answer_success": sum(r["answer_success"] for r in group),
                        "contradiction_omissions": sum(r["contradiction_omitted"] for r in group),
                        "failures": sum(r["evidence_status"] in {"failure", "assessment_failed"} for r in group),
                        "generator_calls": sum(r["generator_calls"] for r in group),
                        "assessor_calls": sum(r["assessor_calls"] for r in group),
                        "selected_passages": sum(len(r["selected_ids"]) for r in group),
                        "local_elapsed_ns": sum(r["local_elapsed_ns"] for r in group)}
    threshold = spec["minimum_useful_effect"]
    gain = (summary["jev"]["answer_success"] - summary["lexical"]["answer_success"]) / len(spec["holdout_ids"])
    passes = (gain >= threshold["answer_success_gain_over_lexical"]
              and summary["jev"]["contradiction_omissions"] <= threshold["max_contradiction_omissions"]
              and summary["jev"]["failures"] <= threshold["max_missing_outcomes"]
              and summary["jev"]["assessor_calls"] <= len(spec["holdout_ids"]) * threshold["max_assessor_calls_per_case"])
    report = {"study_id": spec["study_id"], "evidence_kind": "offline_synthetic_fixture",
              "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (SPEC, PIPELINE, Path(__file__))},
              "seed": spec["seed"], "calibration_ids": spec["calibration_ids"],
              "holdout_ids": spec["holdout_ids"], "rubric": spec["rubric"],
              "threshold": threshold, "stop_rule": spec["stop_rule"],
              "rows": rows, "holdout_summary": summary, "jev_gain_over_lexical": gain,
              "threshold_passed": passes,
              "disposition": "synthetic_screen_only_needs_observed_evidence" if passes else "reject_on_frozen_synthetic_threshold",
              "limits": "No provider, paid model, production retrieval, real answer quality, model latency, or model cost measured. Small authored cases are not an independent 30-cluster study. Local elapsed time is only Python fixture runtime."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"report": str(args.out), "holdout_summary": summary,
                      "disposition": report["disposition"]}, sort_keys=True))


if __name__ == "__main__":
    run()
