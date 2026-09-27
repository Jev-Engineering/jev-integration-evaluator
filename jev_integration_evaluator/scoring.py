"""Transparent weighted scores, evidence intervals, and hard rejection gates."""
from __future__ import annotations
import math
from .config import WEIGHTS
from .io import InputError, finite


def initial_dimensions(f, node, any_tests, c):
    ref = c["candidate_id"] + ":source"
    def item(value, rationale, status="inferred", lo=None, hi=None):
        return {"value": value, "lower": max(0, value-0.20) if lo is None else lo,
                "upper": min(1, value+0.20) if hi is None else hi,
                "status": status, "rationale": rationale, "evidence_refs": [ref]}
    unknown = lambda why: item(0.5, why, "unknown", 0.0, 1.0)
    roles = f["roles"]
    model = "model" in roles
    deterministic = c["deterministic_alternative"] in ("preferred", "mandatory")
    d = {
        "semantic_uncertainty": item(0.0 if deterministic else 0.85 if model else 0.5, "Model/semantic pipeline proxy; not measured task ambiguity"),
        "decision_boundedness": item(0.95 if c["choices"] else 0.0, "A candidate bounded rubric exists; validate coverage and label exclusivity"),
        "downstream_consequence": item(min(1, 0.55 + 0.15*("write" in roles)+0.05*min(4,node["reachable_nodes"])), "Static reachability and side-effect proxy; not a causal estimate"),
        "decision_frequency": unknown("Requires source-correlated task traces"),
        "cost_of_wrong_decision": unknown("Requires failure costs or impact estimates from the owner"),
        "recoverability_value": item(0.85 if c["pattern"] in ("E", "F", "I", "L") else 0.6, "Pattern-specific opportunity to detect or recover failures"),
        "observability": item(0.75 if "observe" in roles or "verify" in roles else 0.4, "Observation/verification call sightings"),
        "deterministic_alternative_quality": item(1.0 if deterministic else 0.2, "Explicit anti-pattern gate, or unresolved semantic need"),
        "current_failure_rate": unknown("No empirical failure rate inferred from source"),
        "current_llm_dependency": item(float(model), "Recognized concrete model-call signature", "observed", float(model), float(model)),
        "latency_sensitivity": unknown("Owner budget and measured critical path required"),
        "cost_sensitivity": unknown("Owner budget and prices required"),
        "implementation_complexity": item(min(1, 0.25+0.05*len(f["branches"])+0.05*len(f["exceptions"])), "Local branch/exception proxy; integration work may differ"),
        "testability": item(0.8 if any_tests else 0.4, "Repository test presence proxy, not candidate test coverage"),
        "expected_reuse": item(min(1, 0.4+0.1*node["fan_out"]), "Static call fan-out proxy; downstream fan-out is not runtime reuse"),
        "confidence_calibration_value": item(0.85 if model or "write" in roles else 0.5, "Potential value of abstention at this boundary"),
    }
    return d


def score_candidate(c: dict, cfg: dict) -> dict:
    if set(c["dimensions"]) != set(WEIGHTS): raise InputError("Every scoring dimension must be present")
    weights = cfg["scoring"]
    denom = sum(max(0, w) for w in weights.values())
    raw = lower = upper = 0.0
    breakdown = {}
    unknowns = []
    for name, d in c["dimensions"].items():
        value = finite(d["value"], name, 0, 1)
        lo = finite(d["lower"], name+" lower", 0, 1); hi = finite(d["upper"], name+" upper", 0, 1)
        if not lo <= value <= hi: raise InputError("Dimension interval does not contain its value")
        if not d.get("rationale") or not d.get("evidence_refs"): raise InputError("Unexplained scores are prohibited")
        w = weights[name]
        raw += w*value; lower += w*(lo if w >= 0 else hi); upper += w*(hi if w >= 0 else lo)
        breakdown[name] = {**d, "weight": w, "contribution": w*value/denom}
        if d["status"] == "unknown": unknowns.append(name)
    clamp = lambda v: max(0.0, min(1.0, v/denom))
    score = clamp(raw)
    rejected = c["deterministic_alternative"] in ("preferred", "mandatory") or c["pattern"] == "NONE"
    reject_reasons = []
    if rejected: reject_reasons.append("Deterministic/generative anti-pattern gate; score cannot override it")
    if c.get("hard_real_time", False): rejected = True; reject_reasons.append("Hard real-time control is unsuitable for a remote semantic gate")
    c.update({"placement_score": round(score, 6), "score_interval": [round(clamp(lower),6), round(clamp(upper),6)],
              "score_breakdown": breakdown, "score_formula": "clip(sum(weight*dimension)/sum(positive weights),0,1)",
              "unknown_dimensions": unknowns, "rejection_reasons": reject_reasons})
    review = c.get("semantic_review", {})
    reviewed = review.get("approved") is True and review.get("source_sha256") == c["source"]["source_sha256"] and bool(review.get("reason")) and bool(review.get("reviewer"))
    if rejected: tier = 0
    elif not reviewed: tier = 1
    elif score >= cfg["thresholds"]["high_leverage"] and c.get("runtime_evidence", {}).get("matched_events", 0) >= 30 and c.get("runtime_evidence", {}).get("evidence_type")=="observed": tier = 3
    elif score >= cfg["thresholds"]["strong_candidate"]: tier = 2
    else: tier = 1
    c["tier"] = tier
    c["recommendation"] = "do_not_use" if tier == 0 else "experimental" if tier == 1 else "high_leverage_candidate" if tier == 3 else "strong_candidate"
    c["deployment_status"] = "not_validated"
    return c


def apply_reviews(scan: dict, reviews: dict, cfg: dict) -> dict:
    known = {c["candidate_id"]: c for c in scan["candidates"]}
    for cid, update in reviews.items():
        if cid not in known: raise InputError(f"Unknown candidate {cid}")
        c = known[cid]
        if update.get("source_sha256") != c["source"]["source_sha256"]: raise InputError("Stale semantic review")
        allowed = {"source_sha256", "reviewer", "reason", "approved", "dimensions", "estimates", "deterministic_alternative", "hard_real_time"}
        if set(update) - allowed: raise InputError("Unsupported review field")
        if type(update.get("approved")) is not bool: raise InputError("Review approved must be an explicit boolean")
        if not update.get("reviewer") or not update.get("reason"): raise InputError("Review must identify reviewer and evidence reasoning")
        c["semantic_review"] = {k: update[k] for k in ("source_sha256", "reviewer", "reason", "approved")}
        for name, d in update.get("dimensions", {}).items():
            if name not in WEIGHTS: raise InputError("Unknown dimension")
            c["dimensions"][name] = d
        if "deterministic_alternative" in update:
            if update["deterministic_alternative"] not in ("none", "weak", "equivalent", "preferred", "mandatory"):
                raise InputError("Invalid deterministic alternative")
            # Anti-pattern classifications can only be changed by rerunning discovery, not a review score edit.
            if c["pattern"] == "NONE" and update["deterministic_alternative"] not in ("preferred", "mandatory"):
                raise InputError("Cannot waive a deterministic anti-pattern by a scoring override")
            c["deterministic_alternative"] = update["deterministic_alternative"]
        if "estimates" in update:
            if set(update["estimates"]) - set(c["estimates"]): raise InputError("Unknown estimate field")
            c["estimates"].update(update["estimates"])
        if "hard_real_time" in update:
            if type(update["hard_real_time"]) is not bool: raise InputError("hard_real_time must be boolean")
            c["hard_real_time"] = update["hard_real_time"]
        score_candidate(c, cfg)
    scan["candidates"].sort(key=lambda c: (-c["tier"], -c["placement_score"], c["candidate_id"]))
    return scan
