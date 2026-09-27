"""Constrained placement sets. Unknown resources do not become free resources."""
from __future__ import annotations
from itertools import combinations
from .io import InputError, finite

RESOURCE = {"added_latency_ms": "max_added_latency_ms", "added_cost": "max_cost_per_task",
            "calls_per_task": "max_calls_per_task", "complexity": "max_complexity"}
REQUIRED = ["quality_gain", "reliability_gain", "failure_reduction", "model_call_reduction",
            *RESOURCE, "maintenance", "false_positive_rate", "false_negative_rate", "risk", "throughput"]


def pareto_front(rows: list[dict], directions: dict[str, str]) -> list[dict]:
    """Point-estimate dominance only; uncertainty requires separate inference."""
    if not directions or any(v not in ("max", "min") for v in directions.values()):
        raise InputError("Pareto directions must be max or min")
    values = []
    for row in rows:
        v = {k: finite(row[k], k) * (1 if d == "max" else -1) for k, d in directions.items()}
        values.append(v)
    result = []
    for i, row in enumerate(rows):
        dominated = any(i != j and all(values[j][k] >= values[i][k] for k in directions)
                        and any(values[j][k] > values[i][k] for k in directions) for j in range(len(rows)))
        if not dominated: result.append(row)
    return result


def optimize(scan: dict, constraints: dict, exact_limit: int = 18, beam_width: int = 512) -> dict:
    if exact_limit < 0 or exact_limit > 22 or beam_width < 1:
        raise InputError("Invalid optimizer search limits")
    for key in ("max_added_latency_ms", "max_cost_per_task", "max_calls_per_task", "max_complexity", "max_risk", "required_throughput"):
        finite(constraints[key], key, 0)
    candidates, excluded = [], []
    for c in scan["candidates"]:
        e = c["estimates"]
        missing = [k for k in REQUIRED if e.get(k) is None]
        review = c.get("semantic_review", {})
        rejected = (c["tier"] == 0 or c.get("pattern") == "NONE"
                    or c.get("hard_real_time") is True
                    or c.get("deterministic_alternative") in ("preferred", "mandatory"))
        # Preserve minimal legacy optimization records, but never ignore stale
        # source metadata when a real inventory includes it. New selection
        # contracts require full source-bound inventory validation separately.
        source = c.get("source")
        stale = source is not None and (not isinstance(source, dict)
                    or not source.get("source_sha256")
                    or review.get("source_sha256") != source["source_sha256"])
        reason = ("Tier 0 / rejected" if rejected else "Stale semantic review" if stale
                  else "Semantic review not approved" if review.get("approved") is not True
                  else "Unknown estimates: " + ", ".join(missing) if missing else None)
        if reason:
            excluded.append({"candidate_id": c["candidate_id"], "reason": reason}); continue
        if not e.get("provenance"):
            excluded.append({"candidate_id": c["candidate_id"], "reason": "Estimates need provenance, units, and assumptions"}); continue
        for k in REQUIRED:
            finite(e[k], k, None if k in ("quality_gain", "reliability_gain", "failure_reduction", "model_call_reduction") else 0)
        for k in ("risk", "false_positive_rate", "false_negative_rate"):
            finite(e[k], k, 0, 1)
        candidates.append(c)
    candidates.sort(key=lambda c: c["candidate_id"])
    ids = {c["candidate_id"] for c in scan["candidates"]}
    interactions = scan.get("interactions", [])
    for x in interactions:
        if x["a"] not in ids or x["b"] not in ids or x["a"] == x["b"]:
            raise InputError("Interaction refers to missing/identical candidates")
        finite(x.get("utility_delta", 0), "interaction utility")
    def evaluate(indices):
        cs = [candidates[i] for i in indices]
        chosen = {c["candidate_id"] for c in cs}
        if any(x.get("conflict") and {x["a"], x["b"]} <= chosen for x in interactions): return None
        totals = {k: sum(c["estimates"][k] for c in cs) for k in RESOURCE}
        if any(totals[k] > constraints[b] + 1e-12 for k, b in RESOURCE.items()): return None
        if any(c["estimates"]["risk"] > constraints["max_risk"] or c["estimates"]["throughput"] < constraints["required_throughput"] for c in cs): return None
        quality = sum(c["estimates"]["quality_gain"] for c in cs)
        reliability = sum(c["estimates"]["reliability_gain"] for c in cs)
        failure = sum(c["estimates"]["failure_reduction"] for c in cs)
        calls_saved = sum(c["estimates"]["model_call_reduction"] for c in cs)
        # A disclosed stakeholder utility, not a universal measure of benefit.
        gain = quality + reliability + 0.5*failure + 0.05*calls_saved
        penalties = sum(0.1*c["estimates"]["maintenance"] + c["estimates"]["false_positive_rate"] + c["estimates"]["false_negative_rate"] for c in cs)
        penalties += 0.15*totals["added_cost"]/max(constraints["max_cost_per_task"], 1e-12)
        penalties += 0.10*totals["added_latency_ms"]/max(constraints["max_added_latency_ms"], 1e-12)
        penalties += 0.08*totals["complexity"]/max(constraints["max_complexity"], 1e-12)
        synergy = sum(x.get("utility_delta", 0) for x in interactions if x.get("status") == "measured" and {x["a"], x["b"]} <= chosen)
        return {"candidate_ids": sorted(chosen), "utility": gain-penalties+synergy, "quality_gain": quality,
                "reliability_gain": reliability, "failure_reduction": failure,
                "model_call_reduction": calls_saved, "measured_interaction_utility": synergy, **totals}
    n = len(candidates)
    mode = "exact_enumeration" if n <= exact_limit else "bounded_beam_heuristic"
    if n <= exact_limit:
        feasible = []
        for count in range(n+1):
            for subset in combinations(range(n), count):
                row = evaluate(subset)
                if row is not None: feasible.append(row)
    else:
        beam = [()]
        # Keep feasible low-utility prefixes too; nevertheless this is not an optimality proof.
        for i in range(n):
            expanded = [(s, evaluate(s)) for s in set(beam + [s+(i,) for s in beam])]
            expanded = [(s, r) for s, r in expanded if r is not None]
            expanded.sort(key=lambda item: (-item[1]["utility"], item[1]["calls_per_task"], item[0]))
            beam = [s for s, _ in expanded[:beam_width]]
            if () not in beam: beam.append(())
        feasible = [evaluate(s) for s in beam]
    baseline = evaluate(())
    balanced = max(feasible, key=lambda r: (r["utility"], -r["calls_per_task"], -len(r["candidate_ids"])))
    positive = [r for r in feasible if r["utility"] > 0 and r["utility"] >= 0.8*balanced["utility"]]
    minimal = min(positive, key=lambda r: (r["calls_per_task"], len(r["candidate_ids"]), r["added_cost"], -r["utility"])) if positive else baseline
    reliability_set = max([r for r in feasible if r["utility"] >= 0], key=lambda r: (r["reliability_gain"], r["utility"], -r["calls_per_task"]))
    # Quadratic Pareto on all 2^n subsets is unnecessary. Retain the 512 highest-utility and extrema;
    # label this frontier as a display subset, not the full mathematical frontier.
    display_pool = sorted(feasible, key=lambda r: -r["utility"])[:512]
    for r in (baseline, minimal, balanced, reliability_set):
        if r not in display_pool: display_pool.append(r)
    return {"method": mode, "optimality_proven_for_declared_model": mode == "exact_enumeration",
            "eligible_candidates": n, "feasible_sets_examined": len(feasible), "excluded": excluded,
            "recommended_minimal_set": minimal, "recommended_balanced_set": balanced,
            "recommended_maximum_reliability_set": reliability_set,
            "pareto_display_subset": pareto_front(display_pool, {"quality_gain": "max", "reliability_gain": "max", "added_cost": "min", "added_latency_ms": "min"}),
            "status": "no_justified_integration_set" if not balanced["candidate_ids"] else "conditional_on_declared_estimates",
            "assumptions": ["Latency uses a conservative serial sum; replace with measured joint critical paths before rollout.",
                            "Quality/reliability/failure deltas are additive hypotheses; avoid double-counting the same outcome.",
                            "No positive credit for unmeasured synergy; duplicate routing decisions conflict by default.",
                            "Throughput and risk are per-component feasibility checks, not an end-to-end safety guarantee.",
                            "The reliability set maximizes the supplied reliability proxy, not proven end-to-end reliability.",
                            "Utility coefficients and the minimal-set 80% retention target are disclosed defaults in optimizer.py."]}
