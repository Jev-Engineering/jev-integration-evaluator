"""Question linting and bounded metamorphic probes for typed decision rubrics.

These checks measure invariance under explicitly documented transformations, not
security or real task success. Generated probes never execute host actions.
"""
from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict
from .client import validate_response
from .contracts import seal, verify, validate_contract
from .io import InputError, digest, finite
from .questions import validate_questions


def request_fingerprint(state, questions: dict, model: str) -> str:
    """Bind presentation order as well as content; canonical JSON alone erases it."""
    return digest({"state": state, "questions": questions, "model": model,
                   "question_order": list(questions),
                   "choice_orders": {k: list(q["criteria"]) for k, q in questions.items() if q["type"] == "choice"}})


def lint_questions(questions: dict) -> dict:
    validate_questions(questions)
    findings = []
    seen = {}
    def normalized(text):
        return re.sub(r"\s+", " ", str(text).strip().casefold()).rstrip("? .")
    for key, q in questions.items():
        instructions = q["instructions"]
        text = normalized(instructions.get("question", instructions) if isinstance(instructions, dict) else instructions)
        if re.fullmatch(r"(?:is|are) (?:this|it|these) (?:good|safe|correct|okay|ok)", text):
            findings.append({"question": key, "code": "vague_global_judgment", "severity": "warning"})
        signature = digest({"instructions": text, "type": q["type"], "criteria": q["criteria"]})
        if signature in seen:
            findings.append({"question": key, "other_question": seen[signature], "code": "duplicate_question", "severity": "warning"})
        seen[signature] = key
        criteria = q["criteria"]
        values = list(criteria.values()) if isinstance(criteria, dict) else list(criteria or [])
        if len({normalized(v) for v in values}) != len(values):
            findings.append({"question": key, "code": "indistinguishable_criteria_text", "severity": "error"})
        if q["type"] == "choice":
            if not any(re.search(r"uncertain|unknown|abstain|insufficient|review", str(k), re.I) for k in criteria):
                findings.append({"question": key, "code": "no_explicit_abstention_label", "severity": "warning"})
            if any(k.casefold() in {"yes", "no", "true", "false", "safe", "unsafe", "allow", "deny"} for k in criteria):
                findings.append({"question": key, "code": "semantic_label_polarity_requires_probe", "severity": "warning"})
    return {"questions": len(questions), "findings": findings,
            "requires_revision": any(f["severity"] == "error" for f in findings),
            "semantics_verified": False, "network_requests": 0,
            "limitations": ["Deterministic lint flags are leads, not semantic correctness judgments.",
                            "Review answerability, atomicity, evidence availability and redundant questions separately."]}


def make_robustness_suite(state, questions: dict, primary: str, model: str, *, truth: str | None = None) -> dict:
    validate_questions(questions)
    if primary not in questions or questions[primary]["type"] != "choice":
        raise InputError("Robustness probes need a primary Choice question")
    labels = list(questions[primary]["criteria"])
    if truth is not None and truth not in labels:
        raise InputError("Ground truth must be an existing Choice label")
    if not isinstance(model, str) or not model:
        raise InputError("A pinned model identity is required")
    probes = []
    for variant in ("original", "test_retest", "reverse_order", "opaque_labels", "rotate_label_bindings"):
        qs = copy.deepcopy(questions)
        criteria = questions[primary]["criteria"]
        mapping = {x: x for x in labels}
        if variant == "reverse_order":
            qs[primary]["criteria"] = {x: criteria[x] for x in reversed(labels)}
        elif variant == "opaque_labels":
            mapping = {"k_" + digest([i, old])[:10]: old for i, old in enumerate(labels)}
            qs[primary]["criteria"] = {new: criteria[old] for new, old in mapping.items()}
        elif variant == "rotate_label_bindings":
            mapping = {new: old for new, old in zip(labels[1:] + labels[:1], labels)}
            qs[primary]["criteria"] = {new: criteria[old] for new, old in mapping.items()}
        validate_questions(qs)
        probes.append({"probe_id": variant, "questions": qs, "label_to_original": mapping,
                       "request_hash": request_fingerprint(state, qs, model)})
    result = seal({"schema_version": "1.1", "kind": "rubric_robustness", "model": model,
                   "state": copy.deepcopy(state), "primary_question": primary, "ground_truth": truth,
                   "probes": probes, "lint": lint_questions(questions), "remote_calls_required": len(probes),
                   "invariance_assumption": "Labels are opaque handles; criterion bodies define their meanings. Review textual cross-references before interpreting renamed-label probes.",
                   "authorization": "local_plan_only_no_network_no_host_actions"})
    validate_contract(result, "robustness-suite")
    return result


def _verify_suite(suite: dict) -> None:
    validate_contract(suite, "robustness-suite")
    verify(suite)
    if len({p["probe_id"] for p in suite["probes"]}) != len(suite["probes"]):
        raise InputError("Duplicate probe identity")
    if not any(p["probe_id"] == "original" for p in suite["probes"]):
        raise InputError("Original control probe is required")
    original = next(p for p in suite["probes"] if p["probe_id"] == "original")
    primary = suite["primary_question"]
    if primary not in original["questions"] or original["questions"][primary]["type"] != "choice":
        raise InputError("Original probe must contain the primary Choice")
    original_criteria = original["questions"][primary]["criteria"]
    canonical_labels = set(original_criteria)
    if original["label_to_original"] != {label: label for label in canonical_labels}:
        raise InputError("Original probe must use the identity label mapping")
    if suite["ground_truth"] is not None and suite["ground_truth"] not in canonical_labels:
        raise InputError("Ground truth is outside the original choices")
    for p in suite["probes"]:
        validate_questions(p["questions"])
        q = p["questions"].get(suite["primary_question"], {})
        mapping = p["label_to_original"]
        if q.get("type") != "choice" or set(mapping) != set(q["criteria"]) or set(mapping.values()) != canonical_labels or len(mapping) != len(canonical_labels):
            raise InputError("Probe label map is not a bijection of the original choices")
        if any(q["criteria"][label] != original_criteria[canonical] for label, canonical in mapping.items()):
            raise InputError("Probe changed criterion meanings instead of only their labels/order")
        restored = copy.deepcopy(p["questions"])
        restored[primary]["criteria"] = copy.deepcopy(original_criteria)
        if restored != original["questions"]:
            raise InputError("Probe changed an unperturbed question or instruction")
        if p["request_hash"] != request_fingerprint(suite["state"], p["questions"], suite["model"]):
            raise InputError("Probe request identity mismatch")


def evaluate_probe_results(suite: dict, records: list[dict]) -> dict:
    _verify_suite(suite)
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise InputError("Probe results must be a list of structured records")
    probes = {p["probe_id"]: p for p in suite["probes"]}
    if len(records) != len(probes) or {r.get("probe_id") for r in records} != set(probes):
        raise InputError("Keep every scheduled probe, including evaluation failures")
    normalized = {}
    kinds = set()
    for r in records:
        p = probes[r["probe_id"]]
        if r.get("request_hash") != p["request_hash"]:
            raise InputError("Probe response belongs to a different ordered request")
        kind = r.get("evidence_type")
        if kind not in ("observed", "synthetic"):
            raise InputError("Probe result needs observed/synthetic evidence type")
        kinds.add(kind)
        if r.get("status") == "failed":
            normalized[r["probe_id"]] = {"probe_id": r["probe_id"], "valid": False, "error_class": r.get("error_class", "EvaluationFailure")}
            continue
        if r.get("status") != "completed":
            raise InputError("Probe status must be completed or failed")
        try:
            validate_response(r["response"], p["questions"], suite["model"])
        except (InputError, KeyError, TypeError, ValueError):
            normalized[r["probe_id"]] = {"probe_id": r["probe_id"], "valid": False, "error_class": "InvalidTypedResponse"}
            continue
        a = r["response"]["answers"][suite["primary_question"]]
        probs = {p["label_to_original"][label]: value for label, value in a["probabilities"].items()}
        selected = p["label_to_original"][a["choice"]]
        normalized[r["probe_id"]] = {"probe_id": r["probe_id"], "valid": True,
                                       "canonical_choice": selected, "probabilities": probs,
                                       "request_hash": p["request_hash"], "response_digest": digest(r["response"]),
                                       "provider_confidence": a["confidence"], "usage": r["response"]["usage"],
                                       "correct": selected == suite["ground_truth"] if suite["ground_truth"] is not None else None}
    if len(kinds) != 1:
        raise InputError("Do not mix synthetic and observed probes")
    control = normalized["original"]
    for value in normalized.values():
        if value["valid"] and control["valid"]:
            value["agrees_with_original"] = value["canonical_choice"] == control["canonical_choice"]
            value["total_variation_from_original"] = sum(abs(p - control["probabilities"][k]) for k, p in value["probabilities"].items()) / 2
    failures = sum(not v["valid"] for v in normalized.values())
    disagreements = sum(v.get("agrees_with_original") is False for v in normalized.values())
    return seal({"schema_version": "1.1", "suite_digest": suite["contract_digest"],
                 "evidence_type": next(iter(kinds)), "scheduled_probes": len(probes),
                 "valid_responses": len(probes) - failures, "evaluation_failures": failures,
                 "disagreements_with_original": disagreements, "probes": list(normalized.values()),
                 "status": "investigate" if failures or disagreements else "no_inconsistency_observed_in_this_suite",
                 "deployment_authorized": False,
                 "limitations": ["Five probes on one state do not estimate population accuracy or model robustness.",
                                  "Agreement can mean consistently wrong; truth is required for decision correctness.",
                                  "Test-retest controls stochastic variation. Ties can change the selected label without distribution movement.",
                                  "No perturbation result is an observed counterfactual downstream task outcome.",
                                  "Offline fixtures are synthetic and cannot establish live model behavior."]})


def run_robustness(suite: dict, client, *, max_calls: int = 5, max_total_cost: float = 0.01,
                   cost_upper_bound_per_call: float | None = None, timeout_ms: int = 2000) -> dict:
    _verify_suite(suite)
    if type(max_calls) is not int or max_calls < len(suite["probes"]):
        raise InputError("Call budget must cover the entire frozen probe schedule")
    finite(max_total_cost, "maximum total cost", 0)
    if type(timeout_ms) is not int or timeout_ms < 1:
        raise InputError("timeout_ms must be a positive integer")
    if cost_upper_bound_per_call is not None:
        finite(cost_upper_bound_per_call, "cost upper bound", 0)
    if client.is_remote and (cost_upper_bound_per_call is None or cost_upper_bound_per_call * len(suite["probes"]) > max_total_cost):
        raise InputError("Explicit cost bounds must cover every remote probe before any request")
    if getattr(client, "order_sensitive", False) is not True:
        raise InputError("Robustness probing requires an order-preserving, order-sensitive client")
    records = []
    for p in suite["probes"]:
        r = {"probe_id": p["probe_id"], "request_hash": p["request_hash"],
             "evidence_type": getattr(client, "evidence_type", "observed")}
        try:
            response = client.evaluate(copy.deepcopy(suite["state"]), copy.deepcopy(p["questions"]), suite["model"], timeout_ms)
            r.update(status="completed", response=response)
        except Exception as exc:
            r.update(status="failed", error_class=type(exc).__name__)
        records.append(r)
    result = evaluate_probe_results(suite, records)
    result["execution"] = {"attempted_calls": len(records), "max_calls": max_calls,
                           "remote": bool(client.is_remote), "actual_cost": None,
                           "cost_status": "unknown_not_inferred_from_responses",
                           "reserved_cost_upper_bound": cost_upper_bound_per_call * len(records) if client.is_remote else 0.0,
                           "network_authorized_by_client_construction": bool(client.is_remote)}
    return seal(result)
