"""Calibration-only checks for the frozen v2 scorer and resource guard."""

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1] / "examples" / "rag-system"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("rag_study45_v2_test", ROOT / "run_study45_v2.py")
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


def test_calibration_uses_separate_oracle_and_prediction_files():
    cases = json.loads((ROOT / "study45_v2_cases.json").read_text())
    labels = json.loads((ROOT / "study45_v2_labels.json").read_text())
    predictions = json.loads((ROOT / "study45_v2_predictions.json").read_text())
    case = cases["cases"][0]
    assert case["id"] == "V2-C01"
    assert "gold" not in case and "assess" not in case
    pipeline = study.v1.load_pipeline()
    row = study.evaluate(pipeline, case, labels["labels"][case["id"]],
                         predictions["responses"][case["id"]], "jev", predictions["limits"])
    assert row["answer_success"]
    assert row["assessor_calls"] == row["generator_calls"] == 1


def test_timeout_missing_and_cost_excess_fail_closed_without_generation():
    pipeline = study.v1.load_pipeline()
    case = {"id": "calibration-failure", "query": "What is Test status?",
            "passages": [["p1", "registry", "T1:1", "Test is active", "test", "supports"]]}
    gold = {"relevant": ["p1"], "expected": "supported", "citation": "p1"}
    limits = {"max_simulated_assessor_latency_ms_per_case": 100,
              "max_simulated_assessor_cost_usd_per_case": 0.001}
    for response in ({"failure": "timeout", "simulated_latency_ms": 100, "simulated_cost_usd": 0.0005},
                     {"failure": "missing", "simulated_latency_ms": 40, "simulated_cost_usd": 0.0005},
                     {"labels": {"p1": "relevant"}, "simulated_latency_ms": 40, "simulated_cost_usd": 0.002}):
        row = study.evaluate(pipeline, case, gold, response, "jev", limits)
        assert row["evidence_status"] == "assessment_failed"
        assert not row["answer_success"]
        assert row["generator_calls"] == 0
