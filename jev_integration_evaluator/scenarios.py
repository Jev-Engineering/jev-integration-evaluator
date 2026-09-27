"""Scenario-robust placement selection without invented probabilities or evidence.

All declared scenarios must meet resource limits. Utility is a disclosed design
preference, not observed JEV performance. Regret uses the common feasible set.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
import re
from .contracts import seal, validate_contract
from .io import InputError, finite, digest, markdown
from .optimizer import RESOURCE, REQUIRED

DEFAULT_WEIGHTS = {
    "quality_gain": 1.0, "reliability_gain": 1.0, "failure_reduction": .5,
    "model_call_reduction": .05, "maintenance": .1, "false_positive_rate": 1.0,
    "false_negative_rate": 1.0, "cost_penalty": .15, "latency_penalty": .10,
    "complexity_penalty": .08,
}


def _estimates(value: dict) -> dict:
    if not isinstance(value, dict) or set(REQUIRED) - set(value):
        raise InputError("Every scenario estimate needs all utility and resource dimensions")
    result = {}
    for key in REQUIRED:
        result[key] = finite(value[key], "scenario " + key,
                             None if key in ("quality_gain", "reliability_gain", "failure_reduction", "model_call_reduction") else 0,
                             1 if key in ("risk", "false_positive_rate", "false_negative_rate") else None)
    return result


def robust_optimize(scan: dict, spec: dict, constraints: dict, *, exact_limit: int = 16,
                    beam_width: int = 256) -> dict:
    validate_contract(spec, "scenario-spec")
    if type(exact_limit) is not int or not 0 <= exact_limit <= 18:
        raise InputError("exact_limit must be 0..18")
    if type(beam_width) is not int or not 1 <= beam_width <= 2048:
        raise InputError("beam_width must be 1..2048")
    limits = {k: finite(constraints[k], k, 0) for k in
              ("max_added_latency_ms", "max_cost_per_task", "max_calls_per_task",
               "max_complexity", "max_risk", "required_throughput")}
    candidates = {}
    for c in scan["candidates"]:
        cid = c["candidate_id"]
        if cid in candidates:
            raise InputError("Duplicate inventory candidate ID")
        candidates[cid] = c
    if len(candidates) > 1000:
        raise InputError("Scenario optimization is bounded to 1000 inventory candidates")
    ids = set(candidates)
    scenario_ids = [s["scenario_id"] for s in spec["scenarios"]]
    if len(set(scenario_ids)) != len(scenario_ids):
        raise InputError("Scenario IDs must be unique")
    requires = {cid: set(deps) for cid, deps in spec["requires"].items()}
    if set(requires) - ids or any(deps - ids for deps in requires.values()):
        raise InputError("Prerequisite refers to a missing candidate")
    # Reject cycles rather than silently manufacturing an all-or-nothing bundle.
    pending = {cid: set(requires.get(cid, ())) for cid in ids}
    done = set()
    while pending:
        ready = {cid for cid, deps in pending.items() if deps <= done}
        if not ready:
            raise InputError("Cyclic placement prerequisites")
        done.update(ready)
        for cid in ready:
            pending.pop(cid)
    conflicts = set()
    base_interactions = {}
    for item in scan.get("interactions", []):
        a, b = item["a"], item["b"]
        if a not in ids or b not in ids or a == b:
            raise InputError("Invalid inventory interaction")
        key = tuple(sorted((a, b)))
        if key in base_interactions:
            raise InputError("Duplicate inventory interaction")
        base_interactions[key] = item
        if item.get("conflict"):
            conflicts.add(key)
    scenario_values, deltas = {}, {}
    ignored_positive_interactions = 0
    for scenario in spec["scenarios"]:
        sid = scenario["scenario_id"]
        if set(scenario["estimates"]) - ids:
            raise InputError("Scenario estimate refers to a missing candidate")
        scenario_values[sid] = {cid: _estimates(e) for cid, e in scenario["estimates"].items()}
        # Only explicitly supplied interactions enter scenario utility. Missing
        # measured interactions are not copied from a different experiment.
        seen = set(); delta = {}
        for item in scenario["interactions"]:
            a, b = item["a"], item["b"]
            if a not in ids or b not in ids or a == b:
                raise InputError("Invalid scenario interaction")
            key = tuple(sorted((a, b)))
            if key in seen:
                raise InputError("Duplicate scenario interaction")
            seen.add(key)
            amount = finite(item["utility_delta"], "interaction delta")
            if amount > 0 and item["status"] != "measured":
                amount = 0.0
                ignored_positive_interactions += 1
            delta[key] = amount
        deltas[sid] = delta
    excluded = {}
    for cid, c in candidates.items():
        review = c.get("semantic_review", {})
        if (c.get("tier", 0) == 0 or c.get("deterministic_alternative") in ("preferred", "mandatory")
                or c.get("hard_real_time", False) or c.get("pattern") == "NONE"):
            excluded[cid] = "rejected_or_tier_zero"
        elif review.get("approved") is not True or not review.get("reviewer") or not review.get("reason"):
            excluded[cid] = "semantic_review_not_approved"
        elif (not re.fullmatch(r"[0-9a-f]{64}", str(c.get("source", {}).get("source_sha256", "")))
              or review.get("source_sha256") != c.get("source", {}).get("source_sha256")):
            excluded[cid] = "semantic_review_source_mismatch"
        elif any(cid not in values for values in scenario_values.values()):
            excluded[cid] = "missing_estimates_in_one_or_more_scenarios"
    changed = True
    while changed:
        changed = False
        for cid in ids - excluded.keys():
            if requires.get(cid, set()) & excluded.keys():
                excluded[cid] = "required_placement_ineligible"
                changed = True
    eligible = sorted(ids - excluded.keys())
    weights = {k: finite(spec["utility_weights"][k], "utility weight", 0) for k in DEFAULT_WEIGHTS}
    if not any(weights[k] > 0 for k in ("quality_gain", "reliability_gain", "failure_reduction", "model_call_reduction")):
        raise InputError("At least one gain weight must be positive")
    retention = spec["minimal_retention"]
    rejection_counts = Counter()
    evaluated = 0
    cache = {}
    def evaluate(chosen):
        nonlocal evaluated
        chosen = tuple(sorted(chosen))
        if chosen in cache:
            return cache[chosen]
        evaluated += 1
        # Cache only heuristic states below; exact enumeration should stay bounded.
        members = set(chosen)
        if any(not deps <= members for cid, deps in requires.items() if cid in members):
            rejection_counts["missing_prerequisite"] += 1
            return None
        if any(set(pair) <= members for pair in conflicts):
            rejection_counts["conflicting_placements"] += 1
            return None
        by_scenario = {}
        feasible = True
        for sid in scenario_ids:
            estimates = [scenario_values[sid][cid] for cid in chosen]
            totals = {key: sum(e[key] for e in estimates) for key in RESOURCE}
            failures = [key for key, limit in RESOURCE.items() if totals[key] > limits[limit]]
            if any(e["risk"] > limits["max_risk"] for e in estimates):
                failures.append("risk")
            if any(e["throughput"] < limits["required_throughput"] for e in estimates):
                failures.append("throughput")
            if failures:
                feasible = False
                for key in failures:
                    rejection_counts[sid + ":" + key] += 1
            gains = {k: sum(e[k] for e in estimates) for k in
                     ("quality_gain", "reliability_gain", "failure_reduction", "model_call_reduction")}
            utility = sum(weights[k] * v for k, v in gains.items())
            utility -= sum(sum(weights[k] * e[k] for k in
                               ("maintenance", "false_positive_rate", "false_negative_rate")) for e in estimates)
            for key, weight in (("added_cost", "cost_penalty"), ("added_latency_ms", "latency_penalty"),
                                ("complexity", "complexity_penalty")):
                utility -= weights[weight] * totals[key] / max(limits[RESOURCE[key]], 1e-12)
            interaction = sum(v for pair, v in deltas[sid].items() if set(pair) <= members)
            utility += interaction
            by_scenario[sid] = {"utility": utility, "interaction_utility": interaction, **gains, **totals}
        if not feasible:
            return None
        return {"candidate_ids": list(chosen), "worst_case_utility": min(x["utility"] for x in by_scenario.values()),
                "worst_case_calls": max(x["calls_per_task"] for x in by_scenario.values()),
                "worst_case_cost": max(x["added_cost"] for x in by_scenario.values()),
                "by_scenario": by_scenario}
    exact = len(eligible) <= exact_limit
    # Cap the product rather than allowing an 18-candidate, 64-scenario explosion.
    if exact and 2 ** len(eligible) * len(scenario_ids) > 250_000:
        exact = False
    if exact:
        feasible = []
        for n in range(len(eligible) + 1):
            for subset in combinations(eligible, n):
                row = evaluate(subset)
                if row is not None:
                    feasible.append(row)
    else:
        def closure(members):
            result = set(members)
            pending = list(result)
            while pending:
                for dep in requires.get(pending.pop(), ()):
                    if dep not in result:
                        result.add(dep); pending.append(dep)
            return tuple(sorted(result))
        beam = {()}
        for cid in eligible:
            expanded = beam | {closure((*members, cid)) for members in beam}
            rows = []
            for subset in sorted(expanded):
                row = evaluate(subset)
                cache[subset] = row
                if row is not None:
                    rows.append((subset, row))
            rows.sort(key=lambda pair: (-pair[1]["worst_case_utility"], pair[1]["worst_case_calls"], pair[0]))
            beam = {s for s, _ in rows[:beam_width]} | {()}
            # Bound cached memory by discarding states no longer in the beam.
            cache = {s: cache[s] for s in beam if s in cache}
        feasible = [evaluate(s) for s in sorted(beam)]
        feasible = [r for r in feasible if r is not None]
    baseline = next(r for r in feasible if not r["candidate_ids"])
    def tie(row):
        return (-row["worst_case_utility"], row["worst_case_calls"], len(row["candidate_ids"]), tuple(row["candidate_ids"]))
    best = min(feasible, key=tie)
    good = [r for r in feasible if r["worst_case_utility"] > 0 and
            r["worst_case_utility"] >= retention * best["worst_case_utility"]]
    minimal = min(good, key=lambda r: (r["worst_case_calls"], len(r["candidate_ids"]), r["worst_case_cost"], tie(r))) if good else baseline
    oracles = {sid: min(feasible, key=lambda r: (-r["by_scenario"][sid]["utility"], r["worst_case_calls"], tuple(r["candidate_ids"])))
               for sid in scenario_ids}
    for row in feasible:
        row["maximum_regret"] = max(oracles[sid]["by_scenario"][sid]["utility"] - row["by_scenario"][sid]["utility"]
                                     for sid in scenario_ids)
    regret = min(feasible, key=lambda r: (r["maximum_regret"], tie(r)))
    result = {
        "schema_version": "1.2", "kind": "scenario_optimization",
        "inventory_fingerprint": scan.get("scan_fingerprint"), "scenario_spec_digest": digest(spec),
        "method": "exact_enumeration" if exact else "bounded_dependency_closure_beam",
        "optimality_proven_for_declared_model": exact,
        "eligible_candidates": len(eligible), "sets_evaluated": evaluated, "common_feasible_sets_examined": len(feasible),
        "excluded": [{"candidate_id": cid, "reason": reason} for cid, reason in sorted(excluded.items())],
        "rejections": dict(sorted(rejection_counts.items())), "ignored_unmeasured_positive_interactions": ignored_positive_interactions,
        "recommended_minimal_set": minimal, "recommended_balanced_set": best, "minimax_regret_set": regret,
        "scenario_optima_on_common_feasible_set": {sid: {"candidate_ids": row["candidate_ids"], "utility": row["by_scenario"][sid]["utility"]}
                                                   for sid, row in oracles.items()},
        "scenarios": [{k: s[k] for k in ("scenario_id", "evidence_type", "provenance")} for s in spec["scenarios"]],
        "utility_weights": weights, "constraints": limits, "minimal_retention": retention,
        "status": "conditional_robust_placement_set" if best["candidate_ids"] else "no_robustly_useful_integration_set",
        "deployment_authorized": False,
        "assumptions": ["Scenarios are user-declared sensitivity cases, not assigned probabilities or confidence intervals.",
                        "Feasibility must hold in every supplied scenario; omitted scenarios are not covered.",
                        "Utility deltas remain additive hypotheses; joint resource/interaction measurements are preferable.",
                        "Latency is a serial sum; risk/throughput limits are per placement, not end-to-end guarantees.",
                        "Minimax regret compares only sets feasible across all scenarios, not each scenario's unrestricted oracle.",
                        "Positive interaction credit requires an explicit measured status and provenance; negative assumed penalties are allowed.",
                        "Beam results and their regret comparator cover only retained states and are not optimality proofs."]}
    return seal(result)


def render_scenarios(report: dict) -> str:
    lines = ["# JEV scenario-robust placement selection", "", "Status: **" + report["status"] + "**.", "",
             "These are conditional design choices, not observed effectiveness or deployment approval.", "",
             "| Choice | Candidates | Worst utility | Worst calls | Maximum regret |", "|---|---|---:|---:|---:|"]
    for name in ("recommended_minimal_set", "recommended_balanced_set", "minimax_regret_set"):
        r = report[name]
        lines.append(f"| {name} | {markdown(', '.join(r['candidate_ids']) or 'None')} | {r['worst_case_utility']:.6f} | {r['worst_case_calls']:.3f} | {r['maximum_regret']:.6f} |")
    lines += ["", "## Declared scenarios", ""]
    lines += [f"{markdown(s['scenario_id'])}: {s['evidence_type']}. {markdown(s['provenance'])}" for s in report["scenarios"]]
    lines += ["", "## Assumptions and limits", "", "\n\n".join(report["assumptions"]), ""]
    return "\n".join(lines)
