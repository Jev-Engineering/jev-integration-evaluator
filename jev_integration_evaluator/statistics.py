"""Paired, cluster-aware usefulness analysis without an inference-service dependency."""
from __future__ import annotations
import math
import random
from collections import Counter, defaultdict
from statistics import mean, stdev, NormalDist
from .io import InputError, finite, digest
from .optimizer import pareto_front

METRICS = ("quality", "tokens", "model_calls", "latency_ms", "cost", "retries", "tool_calls", "human_escalations",
           "unsafe_actions_prevented", "unsafe_actions", "false_blocks", "replans", "verified_progress", "long_horizon_completion")
REQUIRED_RECORD = ("task_id", "replicate", "task_hash", "dataset_id", "treatment", "code_revision", "model_id", "policy_version", "prompt_hash", "mode", "success", "evidence_type")


def quantile(xs, q):
    if not xs: return None
    ys = sorted(xs); pos = q*(len(ys)-1); lo = int(pos); hi = min(lo+1, len(ys)-1)
    return ys[lo]*(1-(pos-lo))+ys[hi]*(pos-lo)


def paired_records(baseline: list[dict], treatment: list[dict]) -> list[tuple[dict, dict]]:
    def index(rows):
        result = {}
        if not rows: raise InputError("Run contains no records")
        for r in rows:
            missing = [k for k in REQUIRED_RECORD if k not in r]
            if missing: raise InputError("Run record missing: " + ", ".join(missing))
            if any(not isinstance(r[k], str) or not r[k] for k in REQUIRED_RECORD if k not in ("replicate", "success")): raise InputError("Run identity fields must be nonempty strings")
            if type(r["success"]) is not bool: raise InputError("Every run must retain a boolean outcome, including failures/timeouts")
            if type(r["replicate"]) is not int or r["replicate"] < 0: raise InputError("replicate must be a nonnegative integer")
            if r["mode"] in ("shadow", "predicted"): raise InputError("Shadow disagreement cannot establish rescues or task success")
            if r["mode"] not in ("baseline", "active", "canary", "replay"): raise InputError("Unsupported run mode")
            if r["evidence_type"] not in ("synthetic", "observed"): raise InputError("evidence_type must be synthetic or observed")
            for k in METRICS:
                if k in r: finite(r[k], k, 0)
            for k in ("quality", "long_horizon_completion"):
                if k in r: finite(r[k], k, 0, 1)
            key = (r["task_id"], r["replicate"])
            if key in result: raise InputError("Duplicate task/replicate pair")
            result[key] = r
        for k in ("dataset_id", "treatment", "code_revision", "model_id", "policy_version", "prompt_hash", "mode", "evidence_type"):
            if len({r[k] for r in rows}) != 1: raise InputError(f"Mixed {k} within an arm; stratify before comparison")
        if len({r.get("evaluation_scope", "task_success") for r in rows}) != 1:
            raise InputError("Mixed evaluation scope within an arm")
        return result
    b, t = index(baseline), index(treatment)
    if set(b) != set(t): raise InputError("Paired task sets differ; retain and account for every scheduled task")
    result = []
    for key in sorted(b):
        x, y = b[key], t[key]
        for field in ("task_hash", "dataset_id", "evidence_type"):
            if x[field] != y[field]: raise InputError(f"Mismatched paired {field}")
        if x.get("evaluation_scope", "task_success") != y.get("evaluation_scope", "task_success"): raise InputError("Paired evaluation scopes differ")
        if x.get("seed") != y.get("seed"): raise InputError("Paired random seeds differ")
        if x.get("cluster_id", x["task_id"]) != y.get("cluster_id", y["task_id"]): raise InputError("Paired cluster IDs differ")
        result.append((x,y))
    return result


def clusters_for(pairs, metric):
    groups = defaultdict(list)
    for b, t in pairs:
        if metric not in b or metric not in t: continue
        groups[b.get("cluster_id", b["task_id"])].append(float(t[metric])-float(b[metric]))
    return list(groups.values())


def bootstrap_ci(groups, samples=2000, level=0.95, seed=731):
    if not groups: return {"interval": [None, None], "clusters": 0}
    finite(level, "confidence level", 0.5, 0.999)
    if type(samples) is not int or not 1 <= samples <= 1_000_000: raise InputError("Invalid bootstrap sample count")
    rng = random.Random(seed)
    draws = []
    for _ in range(samples):
        chosen = [groups[rng.randrange(len(groups))] for _ in groups]
        draws.append(sum(sum(g) for g in chosen)/sum(len(g) for g in chosen))
    alpha = 1-level
    return {"interval": [quantile(draws, alpha/2), quantile(draws, 1-alpha/2)], "clusters": len(groups),
            "method": "paired cluster percentile bootstrap; task-weighted mean", "samples": samples, "level": level,
            "warning": "Few clusters or no observed variation can produce misleadingly narrow/degenerate intervals" if len(groups)<20 or len(set(draws))<2 else None}


def exact_mcnemar(rescues: int, regressions: int) -> dict:
    if any(type(n) is not int or n<0 for n in (rescues,regressions)): raise InputError("McNemar counts must be nonnegative integers")
    n = rescues+regressions
    if n == 0: return {"discordant_pairs": 0, "p_value": 1.0, "method": "exact two-sided conditional binomial"}
    k = min(rescues, regressions)
    logs = [math.lgamma(n+1)-math.lgamma(i+1)-math.lgamma(n-i+1)-n*math.log(2) for i in range(k+1)]
    m = max(logs)
    p = min(1.0, 2*math.exp(m)*sum(math.exp(x-m) for x in logs))
    return {"discordant_pairs": n, "p_value": p, "method": "exact two-sided conditional binomial"}


def bayesian_paired(pairs, samples=5000, delta=0.02, seed=731):
    if type(samples) is not int or not 1 <= samples <= 1_000_000: raise InputError("Invalid posterior draw count")
    finite(delta, "minimum useful effect", 0, 1)
    rng = random.Random(seed)
    groups = clusters_for(pairs, "success")
    if not groups: raise InputError("No paired outcomes")
    draws = []
    if len(groups) == len(pairs):
        counts = Counter((int(b["success"]), int(t["success"])) for b,t in pairs)
        order = [(0,0), (0,1), (1,0), (1,1)]
        for _ in range(samples):
            v = [rng.gammavariate(counts[k]+0.5, 1) for k in order]
            draws.append((v[1]-v[2])/sum(v))
        method = "Paired four-cell multinomial with symmetric Dirichlet(0.5,0.5,0.5,0.5) prior"
        assumption = "Independent/exchangeable task-pair clusters; prior sensitivity remains necessary"
    else:
        for _ in range(samples):
            weights = [rng.expovariate(1.0) for _ in groups]
            draws.append(sum(w*sum(g) for w,g in zip(weights, groups))/sum(w*len(g) for w,g in zip(weights,groups)))
        method = "Cluster Bayesian bootstrap with Dirichlet(1,...,1) weights on observed clusters"
        assumption = "Independent clusters; support is limited to observed clusters and cannot express unseen failure modes"
    p0 = sum(x>0 for x in draws)/samples; pd = sum(x>delta for x in draws)/samples
    return {"method": method, "assumption": assumption, "p_improvement_gt_zero": p0,
            "minimum_useful_effect": delta, "p_improvement_gt_minimum": pd,
            "credible_interval_95": [quantile(draws,0.025),quantile(draws,0.975)], "samples": samples,
            "monte_carlo_se_p_useful": math.sqrt(pd*(1-pd)/samples)}


def failure_transitions(pairs):
    transitions = Counter()
    baseline, treatment = Counter(), Counter()
    for b, t in pairs:
        x = "pass" if b["success"] else b.get("failure_class", "unclassified")
        y = "pass" if t["success"] else t.get("failure_class", "unclassified")
        transitions[(x,y)] += 1; baseline[x] += 1; treatment[y] += 1
    classes = sorted(set(baseline)|set(treatment))
    return {"transitions": [{"baseline": x, "jev": y, "count": n} for (x,y),n in sorted(transitions.items())],
            "class_changes": [{"class": x, "baseline": baseline[x], "jev": treatment[x], "delta": treatment[x]-baseline[x]} for x in classes],
            "warning": "A failure changing categories is not a rescue"}


def economics(failure_reduction: float, failure_cost: float, added_cost: float, fixed_cost: float = 0,
              maintenance_per_task: float = 0, additional_savings: float = 0, volume: int | None = None) -> dict:
    finite(failure_reduction, "failure_reduction", -1, 1)
    for k,v in (("failure_cost", failure_cost), ("fixed_cost", fixed_cost), ("maintenance_per_task", maintenance_per_task)):
        finite(v,k,0)
    finite(added_cost,"added_cost"); finite(additional_savings,"additional_savings")
    if volume is not None and (type(volume) is not int or volume < 0): raise InputError("volume must be a nonnegative integer")
    savings = failure_reduction*failure_cost+additional_savings
    net = savings-added_cost-maintenance_per_task
    return {"expected_savings_per_task": savings, "net_value_per_task": net,
            "break_even_volume": math.ceil(fixed_cost/net) if net>0 else None,
            "break_even_status": "finite" if net>0 else "no_positive_unit_value",
            "total_net_value": volume*net-fixed_cost if volume is not None else None,
            "assumptions": "Failure reduction and cost estimates must use matching task cohorts; include adverse false-block/regression costs. Do not double-count inference savings already included in added_cost."}


def long_horizon(p: float, n: int) -> dict:
    finite(p,"per-step success",0,1)
    if type(n) is not int or n < 0: raise InputError("steps must be a nonnegative integer")
    return {"iid_approximation": p**n, "union_bound_lower": max(0, 1-n*(1-p)),
            "marginal_upper": p if n else 1.0,
            "assumptions": "p^n requires identical independent step success or equal conditional success at each required step; correlations and changing state can invalidate it. Bounds assume each step has marginal success at least p for the lower bound, exactly p for the upper bound."}


def compare_runs(baseline: list[dict], treatment: list[dict], cfg: dict) -> dict:
    pairs = paired_records(baseline, treatment)
    n = len(pairs); v = cfg["validation"]
    bmean = mean(b["success"] for b,t in pairs); tmean = mean(t["success"] for b,t in pairs)
    rescues = sum(not b["success"] and t["success"] for b,t in pairs)
    regressions = sum(b["success"] and not t["success"] for b,t in pairs)
    success_groups = clusters_for(pairs,"success")
    independent = len(success_groups) == n
    ci = bootstrap_ci(success_groups,v["bootstrap_samples"],v["confidence_level"],v["seed"])
    posterior = bayesian_paired(pairs,v["bayesian_samples"],v["minimum_useful_effect"],v["seed"])
    metrics = {}
    incomplete = []
    for k in METRICS:
        subset = [(b,t) for b,t in pairs if k in b and k in t]
        if not subset: continue
        deltas = [t[k]-b[k] for b,t in subset]
        sd = stdev(deltas) if len(deltas)>1 else 0
        metrics[k] = {"paired_count": len(subset), "baseline_mean": mean(b[k] for b,t in subset), "jev_mean": mean(t[k] for b,t in subset),
                      "mean_delta": mean(deltas), "paired_standardized_effect_dz": mean(deltas)/sd if sd else None,
                      "bootstrap": bootstrap_ci(clusters_for(subset,k),v["bootstrap_samples"],v["confidence_level"],v["seed"])}
        if len(subset)<n: incomplete.append(k)
    if "latency_ms" in metrics:
        bs=[b["latency_ms"] for b,t in pairs if "latency_ms" in b and "latency_ms" in t]
        ts=[t["latency_ms"] for b,t in pairs if "latency_ms" in b and "latency_ms" in t]
        metrics["latency_ms"]["baseline_p50"]=quantile(bs,.50)
        metrics["latency_ms"]["baseline_p95"]=quantile(bs,.95)
        metrics["latency_ms"]["jev_p50"]=quantile(ts,.50)
        metrics["latency_ms"]["jev_p95"]=quantile(ts,.95)
        metrics["latency_ms"]["p95_difference"]=quantile(ts,.95)-quantile(bs,.95)
        metrics["latency_ms"]["paired_added_p95"]=quantile([t-b for b,t in zip(bs,ts)],.95)
    efficiency = {}
    for label, records in (("baseline",baseline),("jev",treatment)):
        successes = sum(r["success"] for r in records)
        ef = {}
        for k in ("model_calls","tokens","cost","latency_ms","tool_calls"):
            if all(k in r for r in records):
                total = sum(r[k] for r in records)
                ef["successful_tasks_per_"+k] = successes/total if total else None
                if k in ("model_calls","tool_calls") and all("verified_progress" in r for r in records):
                    ef["verified_progress_per_"+k] = sum(r["verified_progress"] for r in records)/total if total else None
        efficiency[label] = ef
    synthetic = baseline[0]["evidence_type"] == "synthetic"
    recommendation, reasons = "needs_more_evidence", []
    safety_harm = "unsafe_actions" in metrics and metrics["unsafe_actions"]["mean_delta"] > 0
    exceeds_latency = "latency_ms" in metrics and metrics["latency_ms"]["paired_added_p95"] > cfg["constraints"]["max_added_latency_ms"]
    exceeds_cost = "cost" in metrics and metrics["cost"]["mean_delta"] > cfg["constraints"]["max_cost_per_task"]
    if safety_harm or exceeds_latency or exceeds_cost or ci["interval"][1] < 0:
        recommendation = "disable"; reasons.append("Observed safety/resource regression or success interval below zero")
    elif len(success_groups) >= v["min_pairs"] and ci["interval"][0] > v["minimum_useful_effect"] and posterior["p_improvement_gt_minimum"] >= 0.95:
        # A measured result supports consideration, not automatically a deployment authorization.
        complete_operational = all(k in metrics and metrics[k]["paired_count"] == n for k in ("latency_ms","cost","unsafe_actions","false_blocks"))
        if complete_operational and metrics["false_blocks"]["mean_delta"]<=0 and all(t.get("calibration_validated") is True for b,t in pairs) and not synthetic and baseline[0].get("evaluation_scope", "task_success")=="task_success":
            recommendation = "keep"; reasons.append("Declared useful-effect, operational, and calibration evidence gates passed; host approval remains required")
        else:
            reasons.append("Useful-effect evidence exists, but complete operational/calibration validation is missing or synthetic")
    elif tmean>bmean:
        recommendation = "modify" if len(success_groups)>=v["min_pairs"] and not synthetic else "needs_more_evidence"
        reasons.append("Point improvement does not establish a useful enough effect")
    if synthetic:
        recommendation = "needs_more_evidence"; reasons.append("Synthetic fixtures validate tooling, not JEV usefulness")
    if baseline[0].get("evaluation_scope", "task_success") != "task_success":
        recommendation = "needs_more_evidence"
        reasons.append("Decision-label accuracy is not observed downstream task success")
    if not independent: reasons.append("Replicates are clustered; ordinary McNemar is withheld")
    if incomplete: reasons.append("Some metric cohorts are incomplete; do not interpret their deltas as whole-cohort results")
    pareto_rows = []
    if all(k in metrics and metrics[k]["paired_count"]==n for k in ("cost","latency_ms")):
        pareto_rows = [{"configuration":"baseline", "success":bmean, "cost":metrics["cost"]["baseline_mean"], "latency_ms":metrics["latency_ms"]["baseline_mean"]},
                       {"configuration":"jev", "success":tmean, "cost":metrics["cost"]["jev_mean"], "latency_ms":metrics["latency_ms"]["jev_mean"]}]
    return {"schema_version":"1.0", "pair_count":n, "independent_clusters":len(success_groups), "evidence_type":"synthetic" if synthetic else "observed",
            "evaluation_scope":baseline[0].get("evaluation_scope", "task_success"),
            "baseline_success":bmean, "jev_success":tmean, "absolute_improvement":tmean-bmean,
            "relative_improvement":(tmean-bmean)/bmean if bmean else None,
            "cells":{"both_pass":sum(b["success"] and t["success"] for b,t in pairs),"both_fail":sum(not b["success"] and not t["success"] for b,t in pairs),"rescues":rescues,"regressions":regressions},
            "rescue_regression_ratio":rescues/regressions if regressions else None,
            "ratio_status":"defined" if regressions else "no_discordance" if not rescues else "infinite_no_observed_regressions",
            "mcnemar":exact_mcnemar(rescues,regressions) if independent else {"p_value":None,"reason":"Repeated/clustered pairs violate ordinary McNemar independence"},
            "success_bootstrap":ci,"bayesian":posterior,"metrics":metrics,"incomplete_metrics":incomplete,
            "failure_analysis":failure_transitions(pairs),"efficiency":efficiency,
            "pareto_point_estimates":pareto_front(pareto_rows,{"success":"max","cost":"min","latency_ms":"min"}) if pareto_rows else [],
            "recommendation":recommendation,"recommendation_reasons":reasons,
            "provenance":{"baseline_digest":digest(baseline),"jev_digest":digest(treatment),"seed":v["seed"],
                          "baseline_treatment":baseline[0]["treatment"],"jev_treatment":treatment[0]["treatment"]},
            "limitations":["Bootstrap intervals are percentile intervals, not BCa; report low-cluster and degeneracy warnings.",
                           "Decision-only replay cannot establish counterfactual downstream task success.",
                           "Correlated judges, multiple comparisons, task leakage, adaptive stopping, and treatment drift require design controls.",
                           "Keep is an evaluation disposition, never permission to deploy or weaken policy."]}


def ablation_analysis(baseline, variants: dict[str,list[dict]], cfg):
    reports = {name:compare_runs(baseline,rows,cfg) for name,rows in variants.items()}
    pvals = [(k,v["mcnemar"]["p_value"]) for k,v in reports.items() if v["mcnemar"].get("p_value") is not None]
    pvals.sort(key=lambda kv:kv[1]); prev=0; m=len(pvals)
    for i,(name,p) in enumerate(pvals):
        prev=max(prev,min(1,(m-i)*p)); reports[name]["mcnemar"]["holm_adjusted_p_value"]=prev
    interaction = None
    if "router_verifier" in variants and "router+verifier" in variants:
        raise InputError("Use one canonical router/verifier combined arm, not both aliases")
    combined="router_verifier" if "router_verifier" in variants else "router+verifier"
    if {"router", "verifier", combined} <= set(variants):
        # Paired difference-in-differences on the same task instances.
        maps = {k:{(r["task_id"],r["replicate"]):r for r in rows} for k,rows in variants.items()}
        groups=defaultdict(list)
        for b in baseline:
            key=(b["task_id"],b["replicate"])
            d=int(maps[combined][key]["success"])-int(maps["router"][key]["success"])-int(maps["verifier"][key]["success"])+int(b["success"])
            groups[b.get("cluster_id",b["task_id"])].append(d)
        interaction={"difference_in_differences":sum(sum(g) for g in groups.values())/len(baseline),
                     "bootstrap":bootstrap_ci(list(groups.values()),cfg["validation"]["bootstrap_samples"],cfg["validation"]["confidence_level"],cfg["validation"]["seed"])}
    return {"variants":reports,"router_verifier_interaction":interaction,"multiplicity":"Holm correction for available McNemar comparisons; effect intervals remain marginal"}
