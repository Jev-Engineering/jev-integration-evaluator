"""Offline safe-retention contract checks; holdout cases are metadata only."""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "coding-agent"
if str(FIXTURE) not in sys.path:
    sys.path.insert(0, str(FIXTURE))

import retention_oracle as oracle  # noqa: E402
import retention_study as study  # noqa: E402


def calibration(case_id):
    case = next(x for x in study.load("histories")["cases"] if x["id"] == case_id)
    proposal = next((x for x in study.load("proposals")["proposals"] if x["case_id"] == case_id), None)
    fault = next(x["fault"] for x in study.load("injections")["injections"] if x["case_id"] == case_id)
    question = next(x["question"] for x in study.load("reader_questions")["questions"] if x["case_id"] == case_id)
    scorer = next(x for x in study.load("scorer")["labels"] if x["case_id"] == case_id)
    return case, proposal, fault, question, scorer


def test_historical_chooser_receives_original_one_argument_shape():
    case, proposal, _, _, _ = calibration("c01")
    memory = study.FakeMemory(case)
    class RecordingLLM:
        calls = 0
        def choose(self, entries):
            self.calls += 1
            assert isinstance(entries, list) and entries[0]["id"] == "c01-i01"
            return proposal["historical_keep_ids"]
    llm = RecordingLLM()
    result = study.retain_history(llm, memory, case["legacy_count_budget"])
    assert llm.calls == memory.backend_calls == 1
    assert {item["id"] for item in result} == set(proposal["historical_keep_ids"])


def test_strict_chooser_and_reader_projections_ignore_hidden_mutations():
    case, _, _, question, scorer = calibration("c03")
    contract = study.load("projection")
    before = study.chooser_projection(case, contract)
    altered = copy.deepcopy(case)
    altered["expected_answer"] = scorer["expected_answer"]
    altered["fault"] = {"kind": "forged"}
    altered["items"][0]["required_source_ids"] = scorer["required_source_ids"]
    assert study.chooser_projection(altered, contract) == before
    reader = oracle.reader_projection(question, case["items"], case["supersession"])
    assert set(reader) == set(contract["reader"]["exact_top_level_keys"])
    assert set(reader["retained_items"][0]) == set(contract["reader"]["item_keys"])
    assert "expected_answer" not in json.dumps(reader)


def test_pin_only_shortfall_and_compact_are_no_write():
    case, proposal, fault, _, _ = calibration("c06")
    store, status, assessments = study.guarded(case, "jev", proposal, fault, None, study.load("projection"))
    assert status == "insufficient_budget" and assessments == []
    assert store.backend_calls == 0 and store.load() == case["items"]
    case, proposal, fault, _, _ = calibration("c08")
    for arm in ("deterministic", "jev"):
        store, status, assessments = study.guarded(case, arm, proposal, fault, None, study.load("projection"))
        assert status == "requires_separate_compaction" and assessments == []
        assert store.backend_calls == 0 and store.load() == case["items"]
        for attack in ({"boundary": "mode_argument", "attempted_mode": "/prune"},
                       {"boundary": "guarded_host_api_prune_request", "attempted_mode": "/compact"}):
            store, status, assessments = study.guarded(case, arm, proposal, fault, attack, study.load("projection"))
            assert status == "requires_separate_compaction" and assessments == [] and store.backend_calls == 0
            assert store.host_requests == 1 and store.attack_receipt["rejected"] is True
            assert store.attack_receipt["boundary"] == attack["boundary"]
            assert store.attack_receipt.get("attempted_mode", store.attack_receipt.get("attempted_operation")) == (
                "/prune" if attack["boundary"] == "mode_argument" else "prune")


def test_keep_overflow_and_assessment_limit_fail_closed_on_calibration_clone():
    case, proposal, fault, _, _ = calibration("c03")
    narrow = copy.deepcopy(case)
    narrow["token_budget"] = 5
    store, status, assessments = study.guarded(narrow, "jev", proposal, fault, None, study.load("projection"))
    assert status == "needs_review" and assessments
    assert store.backend_calls == 0 and store.load() == case["items"]
    many = copy.deepcopy(case)
    for number in range(6, 17):
        extra = copy.deepcopy(case["items"][1])
        extra["id"] = f"c03-extra-{number}"
        many["items"].append(extra)
    store, status, assessments = study.guarded(many, "jev", proposal, fault, None, study.load("projection"))
    assert status == "assessment_limit_exceeded" and assessments == [] and store.backend_calls == 0


def test_deterministic_recency_uses_immutable_sequence_not_input_order():
    case, _, _, _, _ = calibration("c03")
    selected = study.deterministic_ids(case)
    reordered = copy.deepcopy(case)
    reordered["items"] = list(reversed(reordered["items"]))
    assert study.deterministic_ids(reordered) == selected


def test_stale_binding_and_atomic_false_success_rollback():
    case, proposal, fault, _, _ = calibration("c03")
    stale = copy.deepcopy(proposal)
    stale["jev_input_binding"] = {"revision": 6, "items_sha256": "0" * 64}
    store, status, assessments = study.guarded(case, "jev", stale, fault, None, study.load("projection"))
    assert status == "stale_assessment_binding" and assessments == [] and store.backend_calls == 0
    store, status, assessments = study.guarded(case, "jev", proposal, {"kind": "fake_write_false_success_partial"}, None, study.load("projection"))
    assert status == "failed_readback_rolled_back" and assessments
    assert store.backend_calls == store.rollback_count == 1
    assert store.load() == case["items"] and store.revision == case["revision"]


def test_reachable_timeout_and_malformed_are_uncertain_and_charged():
    case, proposal, fault, _, _ = calibration("c03")
    changed = copy.deepcopy(proposal)
    changed["jev_per_item"]["c03-i02"] = {"label": "timeout", "confidence": None, "latency_ms": 30, "cost_units": 0.003}
    store, _, records = study.guarded(case, "jev", changed, fault, None, study.load("projection"))
    timeout = next(record for record in records if record["item_id"] == "c03-i02")
    assert timeout["choice"] == "uncertain" and timeout["synthetic_latency_ms"] == 30
    assert sum(record["synthetic_cost_units"] for record in records) == pytest.approx(len(records) * 0.003)
    assert store.backend_calls <= 1
    missing = copy.deepcopy(proposal)
    missing["jev_per_item"]["c03-i02"]["latency_ms"] = None
    _, _, records = study.guarded(case, "jev", missing, fault, None, study.load("projection"))
    charged = next(record for record in records if record["item_id"] == "c03-i02")
    assert charged["choice"] == "uncertain" and charged["synthetic_latency_ms"] is None
    assert charged["charged_latency_ms"] == 30 and charged["synthetic_cost_units"] == 0.003


def test_transaction_rechecks_mode_budget_pins_and_revision_before_write():
    case, _, _, _, _ = calibration("c03")
    selected = {item["id"] for item in case["items"] if item["id"] in ("c03-i01", "c03-i04")}
    for changed in ("mode", "token_budget", "pins", "revision"):
        memory = study.FakeMemory(case)
        if changed == "mode":
            memory.mode = "/compact"
        elif changed == "token_budget":
            memory.token_budget = 1
        elif changed == "pins":
            memory.pins = []
        else:
            memory.revision += 1
        status = memory.guarded_commit(selected, case["revision"], case["fake_memory_initial_digest"],
                                       case["mode"], case["token_budget"], case["pins"], {"kind": "none"})
        assert status == "stale_memory" and memory.backend_calls == 0
        assert memory.load() == case["items"]


def test_reader_requires_original_source_citation_and_postconditions():
    case, _, _, question, scorer = calibration("c03")
    result = oracle.score_recall(question, scorer, case["items"], case["supersession"])
    assert result["success"] is True
    missing = [item for item in case["items"] if item["id"] != scorer["required_source_ids"][0]]
    assert oracle.score_recall(question, scorer, missing, case["supersession"])["success"] is False
    mutated = copy.deepcopy(case["items"])
    mutated[0]["source_ref"] = "synthetic://forged"
    assert oracle.raw_postconditions(case, mutated, True, "/prune", case["token_budget"])["byte_or_provenance_loss"]


def test_reviewed_successor_and_unresolved_conflict_are_distinct():
    successor_case, _, _, successor_question, successor_scorer = calibration("c04")
    assert oracle.score_recall(successor_question, successor_scorer, successor_case["items"],
                               successor_case["supersession"])["success"] is True
    assert oracle.score_recall(successor_question, successor_scorer, successor_case["items"], [])["success"] is False
    conflict_case, _, _, conflict_question, conflict_scorer = calibration("c05")
    assert conflict_case["supersession"] == []
    assert oracle.score_recall(conflict_question, conflict_scorer, conflict_case["items"], [])["success"] is True


def test_static_holdout_fault_and_mode_schedule_only():
    faults = {x["case_id"]: x["fault"] for x in study.load("injections")["injections"]}
    proposals = {x["case_id"]: x for x in study.load("proposals")["proposals"]}
    attacks = {x["case_id"]: x for x in study.load("attacks")["attacks"]}
    assert proposals["h08"]["jev_input_binding"] == {"revision": 6, "items_sha256": "0" * 64}
    assert proposals["h14"]["jev_per_item"]["h14-i02"]["label"] == "timeout"
    assert faults["h16"]["kind"] == "fake_write_false_success_partial"
    assert attacks["h24"]["boundary"] == "guarded_host_api_prune_request"
    assert all(attack["maximum_assessment_calls"] == attack["maximum_prune_calls"] == 0 for attack in attacks.values())
    histories = study.load("histories")["cases"]
    by_id = {case["id"]: case for case in histories}
    h14 = by_id["h14"]
    expected_h14_digest = hashlib.sha256(json.dumps(h14["items"], sort_keys=True).encode()).hexdigest()
    assert proposals["h14"]["jev_input_binding"] == {"revision": h14["revision"], "items_sha256": expected_h14_digest}
    assert sum(item["token_count"] for item in h14["items"] if item["id"] in {pin["id"] for pin in h14["pins"]}) <= h14["token_budget"]
    assert len(h14["items"]) - len(h14["pins"]) <= 12
    h16 = by_id["h16"]
    assert sum(item["token_count"] for item in h16["items"] if item["id"] in {pin["id"] for pin in h16["pins"]}) <= h16["token_budget"]
    h16_selected = {pin["id"] for pin in h16["pins"]} | {item_id for item_id, response in proposals["h16"]["jev_per_item"].items() if response["label"] == "keep"}
    assert sum(item["token_count"] for item in h16["items"] if item["id"] in h16_selected) <= h16["token_budget"]
    assert all(oracle.digest(item["text"]) == item["byte_sha256"] and
               len(item["text"].split()) == item["token_count"] for case in histories for item in case["items"])


def test_calibration_schema_denominators_and_holdout_gate():
    spec = json.loads((FIXTURE / "retention" / "study-spec.json").read_text())
    spec_schema = json.loads((ROOT / "schemas" / "coding-agent-retention-study-v1.schema.json").read_text())
    validate(spec, spec_schema)
    report = study.evaluate("calibration")
    schema = json.loads((ROOT / "schemas" / "coding-agent-retention-report-v1.schema.json").read_text())
    validate(report, schema)
    assert len(report["rows"]) == 8
    assert [report["summary"][arm]["efficacy_denominator"] for arm in ("current", "deterministic", "jev")] == [7, 7, 7]
    assert [report["summary"][arm]["safety_denominator"] for arm in ("current", "deterministic", "jev")] == [7, 8, 8]
    assert report["decision"] == "calibration_only_no_holdout_decision"
    assert report["summary"]["jev"]["per_call_p95_ms"] is not None
    assert report["summary"]["jev"]["per_episode_p95_ms"] is not None
    assert report["summary"]["jev"]["unnecessary_retained_tokens"] >= 0
    assert sum(report["summary"]["jev"]["failure_class_counts"].values()) == 7
    altered = copy.deepcopy(report)
    del altered["summary"]["jev"]["per_episode_p95_ms"]
    with pytest.raises(ValidationError):
        validate(altered, schema)
    with pytest.raises(ValueError, match="holdout requires independent"):
        study.evaluate("holdout")
