"""Host and oracle checks for the offline coding-agent completion fixture."""

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "coding-agent"
if str(FIXTURE) not in sys.path:
    sys.path.insert(0, str(FIXTURE))

import completion_oracle as oracle  # noqa: E402
import completion_study as study  # noqa: E402


def calibration(case_id):
    cases = study.load("cases")["cases"]
    scorer = study.load("scorer")["labels"]
    return next(row for row in cases if row["id"] == case_id), next(row for row in scorer if row["id"] == case_id)


def test_historical_one_argument_executor_and_false_success():
    case, labels = calibration("c02")
    outcome = study.run_case(case, "current", study.load("policy"), study.load("assessments"))
    scored = oracle.score_trace(case, labels, outcome["trace"], outcome["raw_final"], outcome["receipts"])
    assert outcome["executor_calls"] == 1
    assert outcome["reported_complete"] is True
    assert scored["verified_completion"] is False


def test_guarded_completion_and_raw_oracle_checkpoint():
    case, labels = calibration("c01")
    outcome = study.run_case(case, "deterministic", study.load("policy"), study.load("assessments"))
    scored = oracle.score_trace(case, labels, outcome["trace"], outcome["raw_final"], outcome["receipts"])
    assert scored["verified_completion"] is True
    assert outcome["reported_complete"] is True
    assert [receipt["status"] for receipt in outcome["receipts"]] == ["executed", "executed"]


def test_wrong_task_permission_and_exact_action_binding_fail_closed():
    case, _ = calibration("c02")
    policy = study.load("policy")
    proposal = study.Proposal(case["steps"][0])
    wrong = copy.deepcopy(proposal)
    wrong.arguments["task_id"] = "other"
    assert study.action_rejection(wrong, case["initial_raw_state"], case, policy) == "wrong_task"
    denied = copy.deepcopy(case)
    denied["granted_permissions"] = []
    assert study.action_rejection(proposal, denied["initial_raw_state"], denied, policy) == "permission_denied"
    executor = study.FakeExecutor(case, policy)
    altered = copy.deepcopy(proposal)
    altered.arguments["status"] = "blocked"
    result = executor.execute_tool(altered)
    assert result.success is False
    assert executor.receipts[0]["status"] == "rejected_no_script"
    assert executor.raw == case["initial_raw_state"]


def test_host_rejection_receipts_and_exception_preserve_raw_state():
    case, _ = calibration("c02")
    policy = study.load("policy")
    denied = copy.deepcopy(case)
    denied["granted_permissions"] = []
    outcome = study.run_case(denied, "deterministic", policy, study.load("assessments"))
    assert outcome["receipts"][0]["status"] == "rejected_permission_denied"
    assert outcome["executor_calls"] == 0
    assert outcome["raw_final"] == case["initial_raw_state"]
    wrong = copy.deepcopy(case)
    wrong["steps"][0]["arguments"]["task_id"] = "other-task"
    outcome = study.run_case(wrong, "deterministic", policy, study.load("assessments"))
    assert outcome["receipts"][0]["status"] == "rejected_wrong_task"
    assert outcome["executor_calls"] == 0
    failed = copy.deepcopy(case)
    failed["steps"][0]["scripted_effect"] = "raise"
    failed["steps"][0]["result_success"] = False
    guarded = study.run_case(failed, "deterministic", policy, study.load("assessments"))
    assert guarded["receipts"][0]["status"] == "exception"
    assert guarded["stop_reason"] == "executor_error"
    assert guarded["raw_final"] == case["initial_raw_state"]
    historical = study.run_case(failed, "current", policy, study.load("assessments"))
    assert historical["receipts"][0]["status"] == "exception"
    assert historical["planner_calls"] > 1


def test_legal_goal_wrong_and_faulty_extra_are_distinct():
    case, _ = calibration("c06")
    policy = study.load("policy")
    legal = study.FakeExecutor(case, policy)
    legal.execute_tool(study.Proposal(case["steps"][0]))
    assert legal.receipts[0]["status"] == "executed"
    assert legal.raw["status"] == "blocked"
    assert oracle.exact_goal(legal.raw, case["objective"]) is False
    faulty_case, _ = calibration("c01")
    faulty_case = copy.deepcopy(faulty_case)
    faulty_case["steps"][0]["scripted_effect"] = "faulty_extra"
    faulty = study.FakeExecutor(faulty_case, policy)
    faulty.execute_tool(study.Proposal(faulty_case["steps"][0]))
    assert faulty.receipts[0]["status"] == "executor_contract_violation"
    assert faulty.raw["unrequested"] == ["synthetic-extra"]
    assert oracle.exact_goal(faulty.raw, faulty_case["objective"]) is False
    extra_label = copy.deepcopy(faulty_case["initial_raw_state"])
    extra_label.update(status="closed", labels=["verified", "unexpected"], revision=1)
    assert oracle.exact_goal(extra_label, faulty_case["objective"]) is False


def test_stale_missing_timeout_capture_ids_and_bounded_assessment():
    case, _ = calibration("c07")
    store = study.FakeExecutor(case, study.load("policy"))
    observer = study.Observer(store)
    before = observer.observe()
    store.execute_tool(study.Proposal(case["steps"][0]))
    stale = observer.after(before, "stale")
    assert stale["capture_id"] == before["capture_id"]
    assert not study.fresh_after(before, stale, store.receipts[-1], case)
    forged = observer.after(before, "fresh")
    forged["capture_id"] = f"{case['objective']['task_id']}-c99"
    assert not study.fresh_after(before, forged, store.receipts[-1], case)
    for fault in ("missing", "timeout"):
        absent = observer.after(before, fault)
        assert absent["capture_id"] is None and absent["snapshot"] is None
    assert not study.fresh_after(before, absent, store.receipts[-1], case)


def test_oracle_rejects_mutated_raw_and_receipt():
    case, labels = calibration("c01")
    outcome = study.run_case(case, "deterministic", study.load("policy"), study.load("assessments"))
    trace = copy.deepcopy(outcome["trace"])
    trace[-1]["raw_after"]["status"] = "open"
    with pytest.raises(ValueError, match="receipt/raw checkpoint mismatch"):
        oracle.score_trace(case, labels, trace, outcome["raw_final"], outcome["receipts"])
    receipts = copy.deepcopy(outcome["receipts"])
    receipts[-1]["reason"] = "forged"
    receipts[-1]["status"] = "executor_contract_violation"
    with pytest.raises(ValueError, match="executor contract receipt mismatch"):
        oracle.score_trace(case, labels, outcome["trace"], outcome["raw_final"], receipts)
    receipts = copy.deepcopy(outcome["receipts"])
    receipts[-1]["raw_before_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="receipt/raw checkpoint mismatch"):
        oracle.score_trace(case, labels, outcome["trace"], outcome["raw_final"], receipts)


def test_oracle_is_independent_of_online_checker(monkeypatch):
    case, labels = calibration("c04")
    monkeypatch.setattr(study, "deterministic_postconditions", lambda snapshot, objective: True)
    outcome = study.run_case(case, "deterministic", study.load("policy"), study.load("assessments"))
    scored = oracle.score_trace(case, labels, outcome["trace"], outcome["raw_final"], outcome["receipts"])
    assert outcome["reported_complete"] is True
    assert scored["verified_completion"] is False


def test_assessment_resource_schedule_cannot_be_repriced():
    case, _ = calibration("c01")
    responses = study.load("assessments")
    responses["responses"]["c01-s1"]["latency_ms"] = 0
    with pytest.raises(ValueError, match="assessment schedule/resource mismatch"):
        study.run_case(case, "jev", study.load("policy"), responses)


def test_missing_assessment_latency_is_preserved_for_counting():
    case, _ = calibration("c01")
    responses = study.load("assessments")
    responses["responses"]["c01-s1"]["latency_ms"] = None
    outcome = study.run_case(case, "jev", study.load("policy"), responses)
    assert outcome["assessments"][0]["synthetic_latency_ms"] is None
    assert outcome["assessments"][0]["synthetic_cost_units"] == 0.002


def test_seeded_holdout_arm_orders_are_exactly_counterbalanced():
    ids = [f"h{number:02d}" for number in range(1, 25)]
    schedule = study.counterbalanced_arm_schedule(ids, 460149)
    assert schedule == study.counterbalanced_arm_schedule(reversed(ids), 460149)
    assert len(set(schedule.values())) == 6
    assert all(list(schedule.values()).count(order) == 4 for order in set(schedule.values()))


def test_prepared_holdout_roles_are_static_only():
    cases = {case["id"]: case for case in study.load("cases")["cases"]}
    assert cases["h10"]["steps"][0]["expected_rejection"] == "wrong_task"
    assert cases["h11"]["steps"][0]["expected_rejection"] == "permission_denied"
    assert cases["h18"]["steps"][0]["expected_receipt"] == "executed_legal_goal_wrong"
    assert cases["h19"]["steps"][0]["expected_receipt"] == "executor_contract_violation"
    assert cases["h19"]["steps"][0]["scripted_effect"] == "faulty_extra"


def test_calibration_report_schema_and_holdout_gate():
    spec = json.loads((FIXTURE / "completion" / "study-spec.json").read_text())
    spec_schema = json.loads((ROOT / "schemas" / "coding-agent-completion-study-v1.schema.json").read_text())
    validate(spec, spec_schema)
    report = study.evaluate("calibration")
    schema = json.loads((ROOT / "schemas" / "coding-agent-completion-report-v1.schema.json").read_text())
    validate(report, schema)
    for field in ("synthetic_p50_latency_ms", "synthetic_p95_latency_ms", "missing_latency_observations", "local_runner_wall_time_ms_total"):
        mutated = copy.deepcopy(report)
        del mutated["summary"]["jev"][field]
        with pytest.raises(ValidationError):
            validate(mutated, schema)
    for field in ("missing_latency_observations", "local_runner_wall_time_ms"):
        mutated = copy.deepcopy(report)
        del mutated["rows"][0]["arms"]["jev"][field]
        with pytest.raises(ValidationError):
            validate(mutated, schema)
    mutated = copy.deepcopy(report)
    del mutated["local_fixture_wall_time_ms"]
    with pytest.raises(ValidationError):
        validate(mutated, schema)
    assert len(report["rows"]) == 8
    assert all(summary["denominator"] == 8 for summary in report["summary"].values())
    assert sum(report["arm_order_counts"].values()) == 8
    assert all(sorted(row["arm_order"]) == ["current", "deterministic", "jev"] for row in report["rows"])
    assert report["summary"]["jev"]["synthetic_p50_latency_ms"] is not None
    assert report["summary"]["jev"]["synthetic_p95_latency_ms"] is not None
    assert report["summary"]["jev"]["missing_latency_observations"] == 0
    assert report["local_fixture_wall_time_ms"] > 0
    with pytest.raises(ValueError, match="holdout requires independent review"):
        study.evaluate("holdout")
