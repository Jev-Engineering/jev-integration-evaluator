"""Synthetic review-boundary regressions; no host/provider execution.

These tests deliberately construct unit-level inventory data. They do not qualify
source discovery, nomination admission, implementation recipes or live outcomes.
"""
from __future__ import annotations

import copy
import hashlib

import pytest

from jev_integration_evaluator.config import WEIGHTS, load_config
from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.scoring import apply_reviews, score_candidate


SOURCE = hashlib.sha256(b"independent synthetic scoring fixture\n").hexdigest()


def inventory(*, alternative="weak", realtime=False, pattern="C", ids=("JEV-TEST-A",)):
    cfg = load_config()
    candidates = []
    for cid in ids:
        candidate = {
            "candidate_id": cid,
            "pattern": pattern,
            "source": {"source_sha256": SOURCE},
            "deterministic_alternative": alternative,
            "hard_real_time": realtime,
            "semantic_review": {
                "approved": False, "reviewer": None, "reason": None,
                "source_sha256": SOURCE,
            },
            "dimensions": {
                name: {
                    "value": float(weight > 0), "lower": 0.0, "upper": 1.0,
                    "status": "unknown", "rationale": "Synthetic test input; not a measurement",
                    "evidence_refs": [cid + ":fixture"],
                }
                for name, weight in WEIGHTS.items()
            },
            "estimates": {"quality_gain": None, "added_cost": None, "provenance": None},
        }
        candidates.append(score_candidate(candidate, cfg))
    return {"candidates": candidates, "constraints": {"activation": False}}


def review(**changes):
    result = {
        "source_sha256": SOURCE,
        "approved": True,
        "reviewer": "synthetic-unit-fixture",
        "reason": "Synthetic test review only; grants no authority.",
    }
    result.update(changes)
    return result


@pytest.mark.parametrize("alternative", ["preferred", "mandatory"])
@pytest.mark.parametrize("replacement", ["none", "weak", "equivalent"])
@pytest.mark.parametrize("approved", [True, False])
@pytest.mark.parametrize("pattern", ["B", "C"])
def test_review_cannot_remove_existing_deterministic_exclusion(alternative, replacement, approved, pattern):
    scan = inventory(alternative=alternative, pattern=pattern)
    before = copy.deepcopy(scan)
    with pytest.raises(InputError, match="deterministic"):
        apply_reviews(scan, {"JEV-TEST-A": review(
            deterministic_alternative=replacement, approved=approved)}, load_config())
    assert scan == before


@pytest.mark.parametrize("approved", [True, False])
def test_mandatory_classification_cannot_be_downgraded_to_preferred(approved):
    scan = inventory(alternative="mandatory")
    before = copy.deepcopy(scan)
    with pytest.raises(InputError, match="mandatory"):
        apply_reviews(scan, {"JEV-TEST-A": review(
            deterministic_alternative="preferred", approved=approved)}, load_config())
    assert scan == before


@pytest.mark.parametrize("pattern", ["B", "C", "NONE"])
@pytest.mark.parametrize("approved", [True, False])
def test_review_cannot_clear_hard_real_time_constraint(pattern, approved):
    scan = inventory(realtime=True, pattern=pattern)
    before = copy.deepcopy(scan)
    with pytest.raises(InputError, match="real.time"):
        apply_reviews(scan, {"JEV-TEST-A": review(hard_real_time=False, approved=approved)}, load_config())
    assert scan == before


@pytest.mark.parametrize("alternative,realtime,pattern,update", [
    ("preferred", False, "C", {}),
    ("mandatory", False, "C", {}),
    ("weak", True, "C", {}),
    ("preferred", False, "NONE", {}),
    ("preferred", False, "C", {"deterministic_alternative": "preferred"}),
    ("mandatory", False, "C", {"deterministic_alternative": "mandatory"}),
    ("weak", True, "C", {"hard_real_time": True}),
])
def test_approval_or_high_score_does_not_override_retained_gates(alternative, realtime, pattern, update):
    scan = inventory(alternative=alternative, realtime=realtime, pattern=pattern)
    result = apply_reviews(scan, {"JEV-TEST-A": review(**update)}, load_config())
    candidate = result["candidates"][0]
    assert result is scan
    assert candidate["placement_score"] == 1.0
    assert candidate["tier"] == 0
    assert candidate["recommendation"] == "do_not_use"
    assert candidate["deployment_status"] == "not_validated"


@pytest.mark.parametrize("update", [
    {"hard_real_time": True},
    {"deterministic_alternative": "preferred"},
    {"deterministic_alternative": "mandatory"},
    {"hard_real_time": True, "deterministic_alternative": "mandatory"},
])
def test_reviews_can_add_stricter_exclusions(update):
    result = apply_reviews(inventory(), {"JEV-TEST-A": review(**update)}, load_config())
    assert result["candidates"][0]["tier"] == 0


def test_preferred_can_be_strengthened_to_mandatory():
    result = apply_reviews(inventory(alternative="preferred"), {
        "JEV-TEST-A": review(deterministic_alternative="mandatory")}, load_config())
    assert result["candidates"][0]["deterministic_alternative"] == "mandatory"
    assert result["candidates"][0]["tier"] == 0


@pytest.mark.parametrize("replacement", ["none", "weak", "equivalent"])
def test_none_pattern_cannot_be_waived(replacement):
    scan = inventory(alternative="preferred", pattern="NONE")
    before = copy.deepcopy(scan)
    with pytest.raises(InputError, match="deterministic"):
        apply_reviews(scan, {"JEV-TEST-A": review(deterministic_alternative=replacement)}, load_config())
    assert scan == before


@pytest.mark.parametrize("changes", [
    {"source_sha256": "0" * 64},
    {"approved": 1},
    {"reviewer": ""},
    {"reason": ""},
    {"unsupported_field": "never-evaluated"},
    {"hard_real_time": "false"},
    {"deterministic_alternative": "unrecognized"},
    {"estimates": {"unsupported_estimate": 1}},
    {"dimensions": {"unknown_dimension": {}}},
    {"dimensions": {"semantic_uncertainty": {
        "value": 2.0, "lower": 0.0, "upper": 1.0, "status": "unknown",
        "rationale": "invalid fixture", "evidence_refs": ["fixture"],
    }}},
])
def test_failed_batch_preserves_every_original_candidate(changes):
    scan = inventory(ids=("JEV-TEST-A", "JEV-TEST-B"))
    before = copy.deepcopy(scan)
    updates = {"JEV-TEST-A": review(), "JEV-TEST-B": review(**changes)}
    original_updates = copy.deepcopy(updates)
    with pytest.raises(InputError):
        apply_reviews(scan, updates, load_config())
    assert scan == before
    assert updates == original_updates


def test_unknown_later_candidate_does_not_leave_earlier_approval():
    scan = inventory()
    before = copy.deepcopy(scan)
    with pytest.raises(InputError, match="Unknown candidate"):
        apply_reviews(scan, {"JEV-TEST-A": review(), "not-in-inventory": review()}, load_config())
    assert scan == before


@pytest.mark.parametrize("replacement_source", [SOURCE, "0" * 64])
def test_duplicate_candidate_ids_are_rejected_without_mutation(replacement_source):
    scan = inventory(ids=("JEV-TEST-A", "JEV-TEST-A"))
    scan["candidates"][1]["source"]["source_sha256"] = replacement_source
    before = copy.deepcopy(scan)
    with pytest.raises(InputError, match="Duplicate candidate"):
        apply_reviews(scan, {"JEV-TEST-A": review()}, load_config())
    assert scan == before


def test_success_detaches_mutable_proposal_data():
    scan = inventory()
    dimension = {
        "value": 0.5, "lower": 0.0, "upper": 1.0, "status": "unknown",
        "rationale": "Synthetic unresolved dimension", "evidence_refs": ["fixture"],
    }
    updates = {"JEV-TEST-A": review(dimensions={"semantic_uncertainty": dimension})}
    result = apply_reviews(scan, updates, load_config())
    expected = copy.deepcopy(result)
    dimension["value"] = 999
    dimension["evidence_refs"].append("unreviewed-after-validation")
    assert result == expected


def test_success_preserves_existing_candidate_and_list_references():
    scan = inventory(ids=("JEV-TEST-B", "JEV-TEST-A"))
    candidates = scan["candidates"]
    selected = candidates[0]
    result = apply_reviews(scan, {selected["candidate_id"]: review()}, load_config())
    assert result is scan and scan["candidates"] is candidates
    assert any(candidate is selected for candidate in candidates)
    assert selected["semantic_review"]["approved"] is True
    assert candidates == sorted(candidates, key=lambda c: (-c["tier"], -c["placement_score"], c["candidate_id"]))


def test_invalid_unreviewed_candidate_cannot_leave_partial_batch_mutation():
    scan = inventory(ids=("JEV-TEST-A", "JEV-TEST-B"))
    scan["candidates"][1].pop("placement_score")
    before = copy.deepcopy(scan)
    with pytest.raises(InputError, match="candidate score"):
        apply_reviews(scan, {"JEV-TEST-A": review()}, load_config())
    assert scan == before


def test_successful_review_preserves_unknowns_and_no_activation():
    cfg = load_config()
    before_cfg = copy.deepcopy(cfg)
    scan = inventory(ids=("JEV-TEST-B", "JEV-TEST-A"))
    updates = {cid: review() for cid in ("JEV-TEST-A", "JEV-TEST-B")}
    before_updates = copy.deepcopy(updates)
    assert apply_reviews(scan, updates, cfg) is scan
    assert [c["candidate_id"] for c in scan["candidates"]] == ["JEV-TEST-A", "JEV-TEST-B"]
    for candidate in scan["candidates"]:
        assert candidate["semantic_review"]["approved"] is True
        assert candidate["source"]["source_sha256"] == SOURCE
        assert candidate["estimates"] == {"quality_gain": None, "added_cost": None, "provenance": None}
        assert candidate["deployment_status"] == "not_validated"
        assert set(candidate["unknown_dimensions"]) == set(WEIGHTS)
        assert candidate["tier"] != 3
    assert scan["constraints"] == {"activation": False}
    assert cfg == before_cfg
    assert cfg["runtime"]["mode"] == "off"
    assert updates == before_updates


def test_rejection_does_not_retain_old_approval():
    scan = inventory()
    apply_reviews(scan, {"JEV-TEST-A": review()}, load_config())
    apply_reviews(scan, {"JEV-TEST-A": review(approved=False)}, load_config())
    assert scan["candidates"][0]["semantic_review"]["approved"] is False
    assert scan["candidates"][0]["tier"] == 1
