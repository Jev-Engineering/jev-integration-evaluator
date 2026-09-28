"""Offline paired synthetic claim-consumer study for issue #47."""

import argparse
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parent
FILES = {"cases": ROOT / "study47_cases.json", "labels": ROOT / "study47_labels.json",
         "predictions": ROOT / "study47_predictions.json", "policy": ROOT / "study47_policy.json"}
FROZEN_SHA256 = {
    "cases": "514bf34e9ff6cdd06ca54fe5af8d59a9b2ddc6968fbb2fe5233330433a817e52",
    "labels": "172cfec1d67227fd5a488366beec1248d05b9d5e03297eb6b984521246597e87",
    "predictions": "e8407cc2fdc29689fd82778a94b690fa494c959b24414c3d544548ff889c9fda",
    "policy": "260e4f038c0d9992c491866b6e3888befed5b79930b365abf36032d5322c66d6",
}
FROZEN_PIPELINE_SHA256 = "2c02318aa6ee76a1c085f8a11cbac5a7bda60ce8040cac58bfa34da6d52504a1"


def load_pipeline():
    spec = importlib.util.spec_from_file_location("rag_claim47_pipeline", ROOT / "pipeline.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Retriever:
    def __init__(self, passages):
        self.passages = passages
        self.calls = 0

    def retrieve(self, query):
        self.calls += 1
        return self.passages


class Generator:
    def __init__(self, pipeline, claim_rows):
        self.pipeline = pipeline
        self.claim_rows = claim_rows
        self.calls = 0

    def generate(self, query, passages):
        self.calls += 1
        claims = []
        for claim_id, text, ref_rows in self.claim_rows:
            refs = tuple(self.pipeline.EvidenceRef(pid, start, start + len(quote), quote)
                         for pid, start, quote in ref_rows)
            claims.append(self.pipeline.AtomicClaim(claim_id, text, refs))
        return self.pipeline.DraftAnswer(tuple(claims))


class GenericClassifier:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def classify(self, request, claims, source_context):
        self.calls += 1
        return self.output


class BoundedAssessor:
    def __init__(self, pipeline, response, limits):
        self.pipeline = pipeline
        self.response = response
        self.limits = limits
        self.calls = 0
        self.late_deliveries_rejected = 0

    def deliver_late(self):
        """A cancelled fixture result has no host continuation to receive it."""
        self.late_deliveries_rejected += 1
        return False

    def assess(self, request, claims, bundle):
        self.calls += 1
        if self.response["latency_ms"] > self.limits["max_simulated_assessor_latency_ms"]:
            raise TimeoutError("synthetic latency cap")
        if self.response["cost_usd"] > self.limits["max_simulated_assessor_cost_usd"]:
            raise RuntimeError("synthetic cost cap")
        if self.response.get("failure") == "timeout":
            raise TimeoutError("scheduled synthetic timeout")
        if self.response.get("failure") == "cancelled_late":
            raise asyncio.CancelledError()
        if self.response.get("failure") == "missing":
            return None
        return {claim_id: self.pipeline.ClaimAssessment(label, tuple(evidence_ids))
                for claim_id, (label, evidence_ids) in self.response["jev"].items()}


class Audit:
    def __init__(self, fail):
        self.fail = fail
        self.calls = 0

    def record(self, query, bundle, draft, outcome):
        self.calls += 1
        if self.fail:
            raise RuntimeError("scheduled synthetic audit failure")
        return True


def independent_citation_check(final, passages):
    by_id = {p.passage_id: p for p in passages}
    if final is None:
        return True
    for claim in final.claims:
        if not claim.citations:
            return False
        for ref in claim.citations:
            original = by_id.get(ref.passage_id)
            if (original is None or type(ref.start) is not int or type(ref.end) is not int
                    or ref.start < 0 or ref.end > len(original.text) or ref.end <= ref.start
                    or original.text[ref.start:ref.end] != ref.quote):
                return False
    return True


def evaluate(pipeline, case, gold, response, policy, arm):
    passages = tuple(pipeline.Passage(*row) for row in case["passages"])
    request = pipeline.ClaimRequest(frozenset(case["critical"]),
                                    tuple(tuple(pair) for pair in case["requires"]))
    retriever = Retriever(passages)
    generator = Generator(pipeline, case["claims"])
    generic = GenericClassifier(response["generic_output"])
    assessor = BoundedAssessor(pipeline, response, policy["limits"])
    audit = Audit(arm == "jev" and response.get("audit_failure", False))
    start = time.perf_counter_ns()
    try:
        if arm in {"historical", "generic_classifier_counterfactual"}:
            draft = pipeline.answer_request(retriever, generator, case["query"])
            bundle = pipeline.select_evidence(case["query"], passages, "current")
            generic_output = (pipeline.claim_check(generic, request, draft.claims, bundle)
                              if arm == "generic_classifier_counterfactual" else None)
            status, final, decisions, reason = "released", draft, (), "legacy_no_claim_consumer"
        else:
            result = pipeline.answer_with_claim_review(
                retriever, generator, case["query"], request,
                policy=arm, assessor=assessor if arm == "jev" else None, audit=audit)
            draft, bundle = result.draft, result.evidence
            status, final = result.outcome.status, result.outcome.final
            decisions, reason = result.outcome.decisions, result.outcome.reason
            generic_output = None
    except Exception:
        draft = final = None
        status, decisions, reason, generic_output = "failed", (), "fixture_exception", None
    late_ignored = (assessor.deliver_late() is False
                    if arm == "jev" and response.get("failure") == "cancelled_late" else None)
    local_elapsed_ns = time.perf_counter_ns() - start
    final_ids = [claim.claim_id for claim in final.claims] if final is not None else []
    citation_correct = independent_citation_check(final, passages)
    unsafe = sum(gold["claims"].get(claim.claim_id) != "supported" or
                 not independent_citation_check(pipeline.DraftAnswer((claim,)), passages)
                 for claim in final.claims) if final is not None else 0
    false_blocks = sum(claim_id not in final_ids for claim_id in gold["expected_ids"])
    failed_or_missing = arm == "jev" and reason in {"assessment_failed", "fixture_exception"}
    success = (not failed_or_missing and status == gold["expected_status"]
               and final_ids == gold["expected_ids"] and citation_correct and unsafe == 0)
    return {"case_id": case["id"], "arm": arm, "status": status, "reason": reason,
            "draft_ids": [c[0] for c in case["claims"]], "final_ids": final_ids,
            "decisions": list(decisions), "generic_output": generic_output,
            "independent_claim_labels": gold["claims"], "expected_status": gold["expected_status"],
            "expected_final_ids": gold["expected_ids"], "answer_success": success,
            "citation_correct": citation_correct, "unsafe_claims_delivered": unsafe,
            "supported_claims_blocked": false_blocks,
            "material_conflict_omitted": any(claim_id in final_ids and label == "contradicted"
                                             and claim_id in case["critical"] for claim_id, label in gold["claims"].items()),
            "failed_or_missing_assessment": failed_or_missing,
            "audit_failure": arm == "jev" and reason == "audit_failed",
            "audit_calls": audit.calls,
            "late_result_ignored": late_ignored,
            "late_deliveries_rejected": assessor.late_deliveries_rejected,
            "retriever_calls": retriever.calls, "generator_calls": generator.calls,
            "generic_classifier_calls": generic.calls, "assessor_calls": assessor.calls,
            "simulated_assessor_latency_ms": response["latency_ms"] if arm == "jev" and assessor.calls else None,
            "simulated_assessor_cost_usd": response["cost_usd"] if arm == "jev" and assessor.calls else None,
            "resource_violations": int(arm == "jev" and assessor.calls > 0 and
                                       (response["latency_ms"] > policy["limits"]["max_simulated_assessor_latency_ms"]
                                        or response["cost_usd"] > policy["limits"]["max_simulated_assessor_cost_usd"]
                                        or assessor.calls > policy["limits"]["max_assessor_calls_per_case"]))
                                   + int(generator.calls > policy["limits"]["max_generator_calls_per_case"]),
            "local_elapsed_ns": local_elapsed_ns}


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raw_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in FILES.items()}
    if (raw_hashes != FROZEN_SHA256
            or hashlib.sha256((ROOT / "pipeline.py").read_bytes()).hexdigest() != FROZEN_PIPELINE_SHA256):
        raise ValueError("reviewed issue 47 inputs changed before holdout")
    data = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in FILES.items()}
    cases = data["cases"]
    labels = data["labels"]["labels"]
    predictions = data["predictions"]["responses"]
    policy = data["policy"]
    ids = [case["id"] for case in cases["cases"]]
    if (len(ids) != len(set(ids)) or set(ids) != set(cases["calibration_ids"] + cases["holdout_ids"])
            or set(ids) != set(labels) or set(ids) != set(predictions)
            or any(data[name]["study_id"] != cases["study_id"] for name in data)):
        raise ValueError("incomplete or mismatched frozen study")
    for case in cases["cases"]:
        claim_ids = [row[0] for row in case["claims"]]
        gold = labels[case["id"]]
        if (len(claim_ids) != len(set(claim_ids)) or set(claim_ids) != set(gold["claims"])
                or not set(gold["expected_ids"]) <= set(claim_ids)
                or gold["expected_status"] not in {"released", "revised", "blocked", "request_more_evidence"}
                or len(case["passages"]) > policy["limits"]["max_passages"]
                or len(claim_ids) > policy["limits"]["max_claims"]):
            raise ValueError("incomplete claim oracle or out-of-bound case")
    pipeline = load_pipeline()
    rows = [evaluate(pipeline, case, labels[case["id"]], predictions[case["id"]], policy, arm)
            for case in cases["cases"] for arm in policy["arms"]]
    holdout = [row for row in rows if row["case_id"] in cases["holdout_ids"]]
    summary = {}
    for arm in policy["arms"]:
        group = [row for row in holdout if row["arm"] == arm]
        summary[arm] = {"n": len(group), "answer_success": sum(row["answer_success"] for row in group),
                        "unsafe_claims_delivered": sum(row["unsafe_claims_delivered"] for row in group),
                        "supported_claims_blocked": sum(row["supported_claims_blocked"] for row in group),
                        "failed_or_missing_assessments": sum(row["failed_or_missing_assessment"] for row in group),
                        "audit_failures": sum(row["audit_failure"] for row in group),
                        "material_conflict_omissions": sum(row["material_conflict_omitted"] for row in group),
                        "resource_violations": sum(row["resource_violations"] for row in group),
                        "assessor_calls": sum(row["assessor_calls"] for row in group),
                        "generator_calls": sum(row["generator_calls"] for row in group),
                        "generic_classifier_calls": sum(row["generic_classifier_calls"] for row in group),
                        "local_elapsed_ns": sum(row["local_elapsed_ns"] for row in group)}
    threshold = policy["minimum_useful_effect"]
    jev, deterministic = summary["jev"], summary["deterministic"]
    gain = (jev["answer_success"] - deterministic["answer_success"]) / len(cases["holdout_ids"])
    screen_pass = (gain >= threshold["answer_success_gain_over_deterministic"]
                   and jev["unsafe_claims_delivered"] <= threshold["max_unsafe_claims_delivered"]
                   and jev["supported_claims_blocked"] - deterministic["supported_claims_blocked"]
                   <= threshold["max_additional_supported_claims_blocked"]
                   and jev["failed_or_missing_assessments"] <= threshold["max_failed_or_missing_assessments"]
                   and jev["audit_failures"] <= threshold["max_audit_failures"]
                   and jev["resource_violations"] <= threshold["max_resource_violations"]
                   and jev["material_conflict_omissions"] <= threshold["max_material_conflict_omissions"])
    sources = list(FILES.values()) + [ROOT / "pipeline.py", Path(__file__)]
    report = {"study_id": cases["study_id"], "evidence_kind": "offline_synthetic_fixture",
              "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
              "calibration_ids": cases["calibration_ids"], "holdout_ids": cases["holdout_ids"],
              "seed": cases["seed"], "assignment_unit": cases["assignment_unit"],
              "label_provenance": data["labels"]["label_provenance"],
              "adjudication_rule": data["labels"]["adjudication_rule"],
              "policy": policy, "rows": rows, "holdout_summary": summary,
              "jev_gain_over_deterministic": gain,
              "screen_decision": "pass_synthetic_screen_needs_observed_evidence" if screen_pass else "reject_on_frozen_synthetic_threshold",
              "adoption_decision": "reject_adoption_from_synthetic_evidence",
              "limits_of_inference": "Small authored corpus; no real retrieval, model, provider cost/latency, user history, deployment, or combined #45+#47 treatment. Only local Python elapsed time was measured."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"report": str(args.out), "holdout_summary": summary,
                      "screen_decision": report["screen_decision"]}, sort_keys=True))


if __name__ == "__main__":
    run()
