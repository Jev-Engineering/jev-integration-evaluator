"""All-placement acceptance evidence, bound to one frozen downstream treatment.

Recompute holdout checks from their exact schedules and rows; a reported boolean
is not sufficient. This verifies content and consistency, not author identity.
"""
from __future__ import annotations

from .contracts import validate_contract
from .holdout import validate_holdout
from .io import InputError, digest
from .questions import validate_questions
from .robustness import request_fingerprint

SOURCE_FIELDS = ("file", "symbol", "file_sha256", "source_sha256")


def gate_rubric_hash(questions: dict, model_id: str, primary_question: str) -> str:
    """Bind presentation order AND the exact question whose labels were scored.

    A multi-question response can use identical labels for different questions;
    their holdout evidence must not be interchangeable.
    """
    validate_questions(questions)
    if primary_question not in questions or questions[primary_question]["type"] != "choice":
        raise InputError("Gate rubric needs a registered primary Choice")
    return digest({"kind": "gate_rubric_v1.2", "primary_question": primary_question,
                   "ordered_questions_hash": request_fingerprint(None, questions, model_id)})


def validate_gate_manifest(spec: dict, inventory: dict | None = None, *, require_inventory: bool = True) -> None:
    gates = spec.get("deployment_gates")
    if not gates:
        return
    if spec.get("holdout_binding") or spec.get("holdout_report_digest"):
        raise InputError("Use either the all-gate manifest or the legacy single holdout binding")
    gate_ids = [g["gate_id"] for g in gates]
    if len(gate_ids) != len(set(gate_ids)):
        raise InputError("Deployment gate IDs must be unique")
    roles = set()
    for gate in gates:
        validate_contract(gate, "deployment-gate")
        questions = gate["questions"]
        validate_questions(questions)
        primary = gate["primary_question"]
        if primary not in questions or questions[primary]["type"] != "choice":
            raise InputError("Every deployment gate requires a registered primary Choice")
        role = (gate["candidate_id"], primary)
        if role in roles:
            raise InputError("Duplicate candidate/primary-question gate")
        roles.add(role)
        labels = set(questions[primary]["criteria"])
        policy = gate["acceptance_policy"]
        if set(policy["action_probability_floors"]) - labels or set(policy["abstention_labels"]) - labels:
            raise InputError("Gate policy refers to unregistered choices")
        # Per-gate models/policies may differ; the top-level JEV arm identifies
        # the complete treatment, not a misleading shared model across gates.
    if inventory is None:
        if require_inventory:
            raise InputError("An all-gate study requires the current reviewed inventory")
        return
    identity = inventory.get("analysis_identity")
    if (not isinstance(identity, dict) or digest(identity) != inventory.get("scan_fingerprint")
            or inventory["scan_fingerprint"] != spec["placement_inventory_fingerprint"]):
        raise InputError("Current inventory fingerprint differs from frozen gate study")
    candidates = {}
    for c in inventory.get("candidates", []):
        cid = c["candidate_id"]
        if cid in candidates:
            raise InputError("Duplicate inventory candidate identity")
        candidates[cid] = c
    for gate in gates:
        c = candidates.get(gate["candidate_id"])
        if not c:
            raise InputError("Frozen gate candidate is absent from the current inventory")
        if {k: c.get("source", {}).get(k) for k in SOURCE_FIELDS} != gate["source"]:
            raise InputError("Deployment gate source body or file context has changed")
        review = c.get("semantic_review", {})
        if (c.get("tier", 0) == 0 or c.get("deterministic_alternative") in ("preferred", "mandatory")
                or c.get("hard_real_time", False) or c.get("pattern") == "NONE"
                or review.get("approved") is not True or not review.get("reason") or not review.get("reviewer")
                or review.get("source_sha256") != c["source"]["source_sha256"]):
            raise InputError("Deployment gate requires a current approved, nonrejected semantic review")


def evaluate_gate_bundle(spec: dict, bundle: dict | None) -> dict:
    gates = spec["deployment_gates"]
    if bundle is None:
        return {"status": "missing_all_gate_evidence", "all_gates_verified": False,
                "all_gates_numerically_pass": False, "missing_gate_ids": [g["gate_id"] for g in gates],
                "gates": [], "deployment_authorized": False}
    validate_contract(bundle, "gate-bundle")
    if bundle["gate_manifest_digest"] != digest(gates):
        raise InputError("Evidence bundle differs from the frozen gate manifest")
    entries = {r["gate_id"]: r for r in bundle["gates"]}
    if len(entries) != len(bundle["gates"]) or set(entries) != {g["gate_id"] for g in gates}:
        raise InputError("Supply exactly one evidence bundle for every frozen gate, with no extra gates")
    report_rows = []
    total_alpha = 0.0
    test_schedule = [r for r in spec["schedule"] if r["split"] == "test"]
    for gate in gates:
        supplied = entries[gate["gate_id"]]
        plan = supplied["threshold_plan"]
        report = validate_holdout(plan, supplied["holdout_rows"], expected_digest=gate["threshold_policy_digest"])
        if report["contract_digest"] != gate["holdout_report_digest"]:
            raise InputError("Recomputed gate report differs from the preregistered holdout digest")
        if any(report["binding"][k] != gate[k] for k in ("model_id", "policy_version")):
            raise InputError("Gate model or policy differs from held-out evidence")
        ordered_hash = gate_rubric_hash(gate["questions"], gate["model_id"], gate["primary_question"])
        if report["binding"]["rubric_hash"] != ordered_hash:
            raise InputError("Gate holdout must bind the ordered question set and primary role")
        if set(report["binding"]["labels"]) != set(gate["questions"][gate["primary_question"]]["criteria"]):
            raise InputError("Gate holdout label set differs from the registered primary Choice")
        if report["acceptance_policy"] != gate["acceptance_policy"]:
            raise InputError("Runtime acceptance policy differs from the exactly tested gate")
        if report["binding"]["evidence_type"] != spec["evidence_type"]:
            raise InputError("Gate and downstream task evidence classifications differ")
        for field in ("task_hash", "cluster_id"):
            prior = {r[field] for r in plan["calibration_identities"] + plan["holdout_schedule"]}
            if prior & {r[field] for r in test_schedule}:
                raise InputError("Downstream test cohort overlaps gate calibration/holdout " + field)
        total_alpha += report["familywise_alpha"]
        report_rows.append({"gate_id": gate["gate_id"], "candidate_id": gate["candidate_id"],
                            "threshold_policy_digest": report["policy_digest"],
                            "holdout_report_digest": report["contract_digest"],
                            "numerical_checks_pass": report["numerical_checks_pass"],
                            "eligible_for_activation": report["eligible_for_activation"],
                            "evidence_type": report["binding"]["evidence_type"]})
    if total_alpha > spec["gate_familywise_alpha"] + 1e-12:
        raise InputError("Per-gate risk-check alpha budgets exceed the frozen all-gate familywise budget")
    verified = all(r["eligible_for_activation"] for r in report_rows)
    return {"status": "all_gates_verified" if verified else "all_gates_not_qualified",
            "gate_manifest_digest": digest(gates), "all_gates_verified": verified,
            "all_gates_numerically_pass": all(r["numerical_checks_pass"] for r in report_rows),
            "gates": report_rows, "missing_gate_ids": [], "allocated_alpha": total_alpha,
            "familywise_alpha": spec["gate_familywise_alpha"], "deployment_authorized": False,
            "limits": ["The alpha allocation uses a union bound across gates and the existing within-gate subgroup checks.",
                       "Gate calibration and holdout units may not overlap downstream test task hashes or clusters.",
                       "Choice acceptance checks do not separately validate Noul inspection, fallback or host security paths.",
                       "A downstream study evaluates the actual combined treatment; individual gates do not prove joint benefit.",
                       "Hashes and observed labels remain untrusted assertions without independent provenance review."]}
