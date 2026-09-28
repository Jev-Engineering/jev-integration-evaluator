"""Calibration-only checks of historical and counterfactual study arms."""

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1] / "examples" / "rag-system"
SPEC = importlib.util.spec_from_file_location("rag_claim47_study", ROOT / "run_study47.py")
study = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = study
SPEC.loader.exec_module(study)


def test_calibration_historical_never_calls_generic_classifier():
    cases = json.loads((ROOT / "study47_cases.json").read_text())
    labels = json.loads((ROOT / "study47_labels.json").read_text())["labels"]
    predictions = json.loads((ROOT / "study47_predictions.json").read_text())["responses"]
    policy = json.loads((ROOT / "study47_policy.json").read_text())
    case = cases["cases"][0]
    assert case["id"] == "C01"
    assert "gold" not in case and "jev" not in case
    pipeline = study.load_pipeline()
    historical = study.evaluate(pipeline, case, labels[case["id"]], predictions[case["id"]],
                                policy, "historical")
    generic = study.evaluate(pipeline, case, labels[case["id"]], predictions[case["id"]],
                             policy, "generic_classifier_counterfactual")
    assert historical["generator_calls"] == generic["generator_calls"] == 1
    assert historical["generic_classifier_calls"] == 0
    assert generic["generic_classifier_calls"] == 1
    assert historical["final_ids"] == generic["final_ids"]
    assert historical["generic_output"] is None
    assert generic["generic_output"] == predictions[case["id"]]["generic_output"]


def test_calibration_semantic_case_separates_deterministic_and_jev():
    cases = json.loads((ROOT / "study47_cases.json").read_text())
    labels = json.loads((ROOT / "study47_labels.json").read_text())["labels"]
    predictions = json.loads((ROOT / "study47_predictions.json").read_text())["responses"]
    policy = json.loads((ROOT / "study47_policy.json").read_text())
    case = cases["cases"][1]
    assert case["id"] == "C02"
    pipeline = study.load_pipeline()
    deterministic = study.evaluate(pipeline, case, labels[case["id"]], predictions[case["id"]],
                                   policy, "deterministic")
    jev = study.evaluate(pipeline, case, labels[case["id"]], predictions[case["id"]], policy, "jev")
    assert deterministic["status"] == "released" and not deterministic["answer_success"]
    assert jev["status"] == "blocked" and jev["answer_success"]


def test_cancelled_late_and_audit_failure_do_not_deliver():
    cases = json.loads((ROOT / "study47_cases.json").read_text())
    labels = json.loads((ROOT / "study47_labels.json").read_text())["labels"]
    policy = json.loads((ROOT / "study47_policy.json").read_text())
    case = cases["cases"][0]
    response = {"generic_output": "possible", "failure": "cancelled_late",
                "latency_ms": 50, "cost_usd": 0.0004}
    pipeline = study.load_pipeline()
    cancelled = study.evaluate(pipeline, case, labels[case["id"]], response, policy, "jev")
    assert cancelled["status"] == "request_more_evidence"
    assert cancelled["final_ids"] == []
    assert cancelled["late_result_ignored"] is True
    assert cancelled["late_deliveries_rejected"] == 1
    response = {"generic_output": "possible", "jev": {"c1": ["supported", ["p1"]]},
                "latency_ms": 50, "cost_usd": 0.0004, "audit_failure": True}
    audit_failed = study.evaluate(pipeline, case, labels[case["id"]], response, policy, "jev")
    assert audit_failed["status"] == "request_more_evidence"
    assert audit_failed["reason"] == "audit_failed"
    assert audit_failed["final_ids"] == [] and audit_failed["audit_calls"] == 1
