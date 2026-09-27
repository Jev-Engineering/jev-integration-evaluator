"""Frozen paired-study schedules, split leakage checks, and full-denominator evaluation."""
from __future__ import annotations

import copy
from collections import Counter
from .contracts import seal, verify, validate_contract, utc_now
from .io import InputError, digest
from .statistics import paired_records, compare_runs, METRICS

ARM_FIELDS = ("treatment", "code_revision", "model_id", "policy_version", "prompt_hash", "mode")


def _schedule(spec: dict) -> dict[tuple[str, int], dict]:
    rows = spec["schedule"]
    index = {}
    split_members = {field: {} for field in ("task_id", "task_hash", "cluster_id")}
    for row in rows:
        key = (row["task_id"], row["replicate"])
        if key in index:
            raise InputError("Duplicate scheduled task/replicate")
        index[key] = row
        for field, seen in split_members.items():
            value = row[field]
            if value in seen and seen[value] != row["split"]:
                raise InputError("Cross-split leakage of " + field)
            seen[value] = row["split"]
    if not any(r["split"] == "test" for r in rows):
        raise InputError("Frozen schedule must include held-out test tasks")
    if spec["baseline"]["treatment"] == spec["jev"]["treatment"]:
        raise InputError("Baseline and JEV treatment identities must differ")
    if spec["baseline"]["mode"] != "baseline":
        raise InputError("Baseline arm must use baseline mode")
    if spec["jev"]["mode"] not in ("active", "canary", "replay"):
        raise InputError("Shadow decisions cannot serve as observed task outcomes")
    if "holdout_binding" in spec:
        for field in ("model_id", "policy_version"):
            if spec["holdout_binding"][field] != spec["jev"][field]:
                raise InputError("Frozen holdout binding differs from the JEV arm " + field)
    if set(spec["required_metrics"]) - set(METRICS):
        raise InputError("Unknown preregistered metric")
    return index


def freeze_study(spec: dict, cfg: dict, *, inventory: dict | None = None) -> dict:
    """Freeze before collection. A local timestamp cannot prove pre-registration time."""
    validate_contract(spec, "study-spec")
    _schedule(spec)
    from .gates import validate_gate_manifest
    validate_gate_manifest(spec, inventory)
    result = seal({
        "schema_version": "1.2" if spec.get("deployment_gates") else "1.1", "kind": "paired_study", "frozen_at": utc_now(),
        "specification": spec,
        "analysis_config": {"validation": cfg["validation"], "constraints": cfg["constraints"]},
        "registration_status": "local_manifest_not_external_registration",
        "stop_rule": "fixed_schedule_one_confirmatory_analysis_no_optional_stopping",
        "authorization": "no_network_no_execution_no_deployment",
    })
    validate_contract(result, "study")
    return result


def validate_study(plan: dict, baseline: list[dict], treatment: list[dict], *, expected_digest: str | None = None, inventory: dict | None = None) -> dict:
    validate_contract(plan, "study")
    verify(plan, expected=expected_digest)
    spec = plan["specification"]
    validate_contract(spec, "study-spec")
    schedule = _schedule(spec)
    from .gates import validate_gate_manifest
    validate_gate_manifest(spec, inventory)
    # Retain v1 pairing/metric guards, but also verify the separately frozen denominator.
    pairs = paired_records(baseline, treatment)
    expected = {key: r for key, r in schedule.items() if r["split"] == "test"}
    actual = {(b["task_id"], b["replicate"]) for b, _ in pairs}
    if actual != set(expected):
        raise InputError("Run cohort differs from frozen test schedule; include every scheduled failure/timeout")
    for arm_name, rows in (("baseline", baseline), ("jev", treatment)):
        for row in rows:
            s = expected[(row["task_id"], row["replicate"])]
            for field in ARM_FIELDS:
                if row[field] != spec[arm_name][field]:
                    raise InputError("Run differs from frozen " + arm_name + " " + field)
            for field in ("task_hash", "cluster_id"):
                if row.get(field) != s[field]:
                    raise InputError("Run differs from scheduled " + field)
            if spec.get("deployment_gates") and row.get("gate_manifest_digest") != digest(spec["deployment_gates"]):
                raise InputError("Scheduled outcome differs from frozen all-gate treatment manifest")
            if row.get("seed") != s.get("seed"):
                raise InputError("Run differs from scheduled random seed")
            for field, wanted in (("dataset_id", spec["dataset_id"]),
                                  ("experiment_id", spec["experiment_id"]),
                                  ("study_digest", plan["contract_digest"]),
                                  ("split", "test"), ("evaluation_scope", "task_success"),
                                  ("evidence_type", spec["evidence_type"])):
                if row.get(field) != wanted:
                    raise InputError("Run differs from frozen " + field)
            if any(k not in row for k in spec["required_metrics"]):
                raise InputError("Scheduled run is missing a preregistered operational metric")
            if row.get("run_status") not in ("completed", "failed", "timeout", "cancelled", "not_run"):
                raise InputError("Every scheduled result requires an explicit run_status")
            if row["run_status"] != "completed" and row["success"]:
                raise InputError("Incomplete/failed/timed-out scheduled run cannot count as success")
    return {
        "status": "valid", "study_digest": plan["contract_digest"],
        "scheduled_test_pairs": len(expected), "observed_pairs": len(pairs),
        "scheduled_split_counts": dict(Counter(r["split"] for r in schedule.values())),
        "baseline_status_counts": dict(Counter(r["run_status"] for r in baseline)),
        "jev_status_counts": dict(Counter(r["run_status"] for r in treatment)),
        "missing_from_both_arms": 0, "split_leakage": False,
        "externally_pinned_digest": expected_digest is not None,
        "limitations": ["Local hashes do not authenticate labels, timestamps or task execution.",
                        "Disjoint identifiers/hashes do not detect all semantically duplicated tasks.",
                        "Retain the manifest digest in a trusted system before running the study."],
    }


def evaluate_study(plan: dict, baseline: list[dict], treatment: list[dict], *, expected_digest: str | None = None,
                   holdout_report: dict | None = None, gate_bundle: dict | None = None,
                   inventory: dict | None = None) -> dict:
    checks = validate_study(plan, baseline, treatment, expected_digest=expected_digest, inventory=inventory)
    config = copy.deepcopy(plan["analysis_config"])
    # Frozen endpoints/constraints, not the caller's post-hoc CLI configuration.
    result = compare_runs(baseline, treatment, config)
    result["study_validation"] = checks
    result["analysis_status"] = "fixed_design_local_analysis"
    valid_holdout = False
    expected_holdout = plan["specification"].get("holdout_report_digest")
    if plan["specification"].get("deployment_gates"):
        if holdout_report is not None:
            raise InputError("An all-gate study cannot substitute one legacy holdout report")
        from .gates import evaluate_gate_bundle
        result["gate_evidence"] = evaluate_gate_bundle(plan["specification"], gate_bundle)
        valid_holdout = result["gate_evidence"]["all_gates_verified"]
        if result["recommendation"] == "keep" and expected_digest is None:
            result["recommendation"] = "needs_more_evidence"
            result["recommendation_reasons"].append("The all-gate study needs an independently retained study digest")
    elif gate_bundle is not None:
        raise InputError("Gate bundle supplied to a study with no frozen all-gate manifest")
    if holdout_report is not None:
        from .holdout import verify_holdout_report
        verify_holdout_report(holdout_report)
        wanted = plan["specification"].get("holdout_binding", {})
        actual = {k: holdout_report["binding"][k] for k in ("model_id", "policy_version", "rubric_hash")}
        actual["policy_digest"] = holdout_report["policy_digest"]
        valid_holdout = (holdout_report["eligible_for_activation"] is True and actual == wanted
                         and bool(expected_holdout) and expected_holdout == holdout_report["contract_digest"])
    if result["recommendation"] == "keep" and not valid_holdout:
        result["recommendation"] = "needs_more_evidence"
        result["recommendation_reasons"].append("Every frozen acceptance gate needs digest-matched observed held-out evidence; boolean calibration flags are insufficient")
    result["holdout_evidence_verified"] = valid_holdout
    result["deployment_authorized"] = False
    return seal(result)
