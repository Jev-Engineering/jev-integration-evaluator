"""Frozen selective-risk validation on independent held-out Choice decisions.

The exact bound is one-sided Clopper–Pearson, computed by binomial-CDF inversion.
It certifies neither security nor distribution stability. No SciPy dependency.
"""
from __future__ import annotations

import math
from collections import Counter
from .calibration import calibration
from .contracts import seal, verify, validate_contract, utc_now
from .io import InputError, finite, digest

IDENTITY = ("observation_id", "task_hash", "cluster_id", "subgroup")
BINDING = ("model_id", "policy_version", "rubric_hash", "evidence_type")


def binomial_error_upper(errors: int, count: int, alpha: float = 0.05) -> float | None:
    """Exact one-sided (1-alpha) upper limit for independent Bernoulli errors."""
    if type(count) is not int or type(errors) is not int or count < 0 or not 0 <= errors <= count:
        raise InputError("Invalid binomial error counts")
    finite(alpha, "alpha", 1e-12, 0.5)
    if count == 0:
        return None
    if errors == count:
        return 1.0
    if errors == 0:
        return -math.expm1(math.log(alpha) / count)
    # Precompute log coefficients to keep repeated CDF evaluation stable.
    coeff = [math.lgamma(count + 1) - math.lgamma(i + 1) - math.lgamma(count - i + 1)
             for i in range(errors + 1)]
    def cdf(p: float) -> float:
        logs = [c + i * math.log(p) + (count - i) * math.log1p(-p) for i, c in enumerate(coeff)]
        peak = max(logs)
        return math.exp(peak) * math.fsum(math.exp(x - peak) for x in logs)
    low, high = errors / count, 1.0
    for _ in range(65):
        mid = (low + high) / 2
        if mid == low or mid == high:
            break
        if cdf(mid) > alpha:
            low = mid
        else:
            high = mid
    return high


def _rows(rows: list[dict], split: str) -> dict:
    if not rows:
        raise InputError("Labeled calibration/holdout observations are required")
    ids = set()
    for r in rows:
        if any(not isinstance(r.get(k), str) or not r[k] for k in IDENTITY + BINDING):
            raise InputError("Observation identity, subgroup and model/policy/rubric provenance are required")
        if r["observation_id"] in ids:
            raise InputError("Duplicate observation identity")
        ids.add(r["observation_id"])
        if r.get("split") != split or r.get("kind") != "choice":
            raise InputError("Expected Choice observations on the specified split")
        if r["evidence_type"] not in ("synthetic", "observed"):
            raise InputError("Unknown observation evidence type")
        finite(r.get("confidence"), "provider confidence", 0, 1)
        if r.get("choice") not in r.get("probabilities", {}):
            raise InputError("Explicit selected Choice label is required")
    binding = {k: rows[0][k] for k in BINDING}
    if any(any(r[k] != v for k, v in binding.items()) for r in rows):
        raise InputError("Mixed model/policy/rubric/evidence provenance")
    labels = set(rows[0]["probabilities"])
    if any(set(r["probabilities"]) != labels for r in rows):
        raise InputError("Candidate choices changed within calibration/holdout cohort")
    for subgroup in sorted({r["subgroup"] for r in rows}):
        calibration([r for r in rows if r["subgroup"] == subgroup])
    return {**binding, "labels": sorted(labels)}


def _accept(r: dict, policy: dict) -> bool:
    action_floor = policy["action_probability_floors"].get(r["choice"], policy["probability_floor"])
    return (r["choice"] not in policy["abstention_labels"]
            and r["probabilities"][r["choice"]] >= max(policy["probability_floor"], action_floor)
            and r["confidence"] >= policy["confidence_floor"])


def _schedule(rows: list[dict]) -> dict[str, dict]:
    by_id = {}
    for r in rows:
        if any(not isinstance(r.get(k), str) or not r[k] for k in IDENTITY):
            raise InputError("Holdout schedule needs exact observation/task/cluster/subgroup identities")
        if set(r) != set(IDENTITY) or r["observation_id"] in by_id:
            raise InputError("Invalid or duplicate holdout schedule identity")
        by_id[r["observation_id"]] = r
    # Exact binomial intervals assume independent units: do not silently count replicates.
    for field in ("task_hash", "cluster_id"):
        if len({r[field] for r in rows}) != len(rows):
            raise InputError("Holdout requires one independent observation per task hash and cluster")
    if not by_id:
        raise InputError("Freeze a nonempty holdout schedule before looking at its outcomes")
    return by_id


def freeze_threshold(rows: list[dict], spec: dict) -> dict:
    validate_contract(spec, "threshold-spec")
    binding = _rows(rows, "calibration")
    schedule = _schedule(spec["holdout_schedule"])
    for field in ("observation_id", "task_hash", "cluster_id"):
        if {r[field] for r in rows} & {r[field] for r in schedule.values()}:
            raise InputError("Calibration/holdout leakage of " + field)
    labels = set(binding["labels"])
    if set(spec["action_probability_floors"]) - labels or set(spec["abstention_labels"]) - labels:
        raise InputError("Threshold policy refers to unregistered action labels")
    if not set(spec["required_subgroups"]) <= {r["subgroup"] for r in schedule.values()}:
        raise InputError("Required subgroup is absent from frozen holdout schedule")
    policy = {k: spec[k] for k in ("probability_floor", "confidence_floor", "action_probability_floors", "abstention_labels")}
    selected = [r for r in rows if _accept(r, policy)]
    body = {
        "schema_version": "1.1", "kind": "frozen_threshold", "frozen_at": utc_now(),
        "binding": binding, "policy": policy,
        "maximum_error": spec["maximum_error"], "alpha": spec["alpha"],
        "minimum_accepted": spec["minimum_accepted"], "required_subgroups": spec["required_subgroups"],
        "holdout_schedule": list(schedule.values()),
        "calibration_identities": [{k: r[k] for k in IDENTITY} for r in rows],
        "calibration_digest": digest(rows),
        "selection_diagnostic": {"observations": len(rows), "accepted": len(selected),
                                 "errors": sum(r["choice"] != r["label"] for r in selected),
                                 "certified": False},
        "status": "frozen_requires_untouched_holdout",
        "limitations": ["Freeze the chosen thresholds before evaluating the scheduled holdout.",
                        "This local record cannot prove that the holdout was previously unseen.",
                        "Confidence is a provider statistic used as a gate, not a correctness probability."],
    }
    result = seal(body)
    validate_contract(result, "threshold-policy")
    return result


def validate_holdout(plan: dict, rows: list[dict], *, expected_digest: str | None = None) -> dict:
    validate_contract(plan, "threshold-policy")
    verify(plan, expected=expected_digest)
    binding = _rows(rows, "test")
    if binding != plan["binding"]:
        raise InputError("Held-out model/policy/rubric/label/evidence identity differs from frozen selection")
    scheduled = _schedule(plan["holdout_schedule"])
    if set(scheduled) != {r["observation_id"] for r in rows}:
        raise InputError("Held-out cohort differs from frozen schedule; failed/missing evaluations cannot be dropped")
    for r in rows:
        if {k: r[k] for k in IDENTITY} != scheduled[r["observation_id"]]:
            raise InputError("Held-out observation identity differs from schedule")
    for field in ("observation_id", "task_hash", "cluster_id"):
        if {r[field] for r in rows} & {r[field] for r in plan["calibration_identities"]}:
            raise InputError("Held-out observations overlap calibration on " + field)
    families = [None] + plan["required_subgroups"]
    adjusted_alpha = plan["alpha"] / len(families)
    results = []
    for group in families:
        population = [r for r in rows if group is None or r["subgroup"] == group]
        accepted = [r for r in population if _accept(r, plan["policy"])]
        errors = sum(r["choice"] != r["label"] for r in accepted)
        upper = binomial_error_upper(errors, len(accepted), adjusted_alpha)
        enough = len(accepted) >= plan["minimum_accepted"]
        results.append({
            "subgroup": group, "observations": len(population), "accepted": len(accepted), "errors": errors,
            "coverage": len(accepted) / len(population) if population else None,
            "empirical_error": errors / len(accepted) if accepted else None,
            "error_upper_bound": upper, "alpha": adjusted_alpha,
            "passes": enough and upper is not None and upper <= plan["maximum_error"],
            "status": "evaluated" if enough else "insufficient_independent_accepted_observations",
        })
    passes = all(r["passes"] for r in results)
    observed = binding["evidence_type"] == "observed"
    result = seal({
        "schema_version": "1.1", "kind": "holdout_validation", "policy_digest": plan["contract_digest"],
        "binding": binding, "holdout_digest": digest(rows), "scheduled_observations": len(scheduled),
        "method": "one-sided exact Clopper-Pearson; Bonferroni over pooled and preregistered subgroup checks",
        "familywise_alpha": plan["alpha"], "maximum_error": plan["maximum_error"],
        "minimum_accepted": plan["minimum_accepted"], "acceptance_policy": plan["policy"],
        "checks": results, "numerical_checks_pass": passes,
        "eligible_for_activation": passes and observed, "deployment_authorized": False,
        "status": "validated" if passes and observed else "synthetic_only" if passes else "needs_more_evidence_or_lower_risk",
        "externally_pinned_digest": expected_digest is not None,
        "limitations": ["Assumes independent, representative Bernoulli errors among accepted decisions.",
                        "Unique task/cluster IDs cannot prove statistical independence.",
                        "Do not reuse this holdout to choose another threshold, subgroup or rubric.",
                        "This validates the recorded acceptance gate, not the host's different inspection or fallback paths.",
                        "Distribution shift, adversarial security and source correctness are not certified.",
                        "Synthetic responses can exercise the computation but cannot justify activation."],
    })

    validate_contract(result, "holdout-report")
    return result


def verify_holdout_report(report: dict) -> None:
    """Check self-integrity and numerical consistency, not the reporter's identity."""
    validate_contract(report, "holdout-report")
    verify(report)
    checks = report["checks"]
    if checks[0]["subgroup"] is not None or len({c["subgroup"] for c in checks}) != len(checks):
        raise InputError("Holdout checks require a pooled check followed by unique subgroups")
    alpha = report["familywise_alpha"] / len(checks)
    for check in checks:
        n, k = check["accepted"], check["errors"]
        if not 0 <= k <= n <= check["observations"]:
            raise InputError("Inconsistent holdout counts")
        upper = binomial_error_upper(k, n, alpha)
        passes = n >= report["minimum_accepted"] and upper is not None and upper <= report["maximum_error"]
        actual_upper = check["error_upper_bound"]
        bounds_match = actual_upper is None if upper is None else actual_upper is not None and math.isclose(actual_upper, upper, rel_tol=1e-10, abs_tol=1e-12)
        coverage = n / check["observations"] if check["observations"] else None
        empirical = k / n if n else None
        def equal_number(actual, expected):
            return actual is None if expected is None else actual is not None and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12)
        if (check["passes"] != passes or not math.isclose(check["alpha"], alpha, rel_tol=1e-12)
                or not bounds_match or not equal_number(check["coverage"], coverage)
                or not equal_number(check["empirical_error"], empirical)):
            raise InputError("Inconsistent held-out risk bound or empirical counts")
    if checks[0]["observations"] != report["scheduled_observations"]:
        raise InputError("Pooled report must cover the entire held-out schedule")
    if any(sum(c[field] for c in checks[1:]) > checks[0][field] for field in ("observations", "accepted", "errors")):
        raise InputError("Disjoint subgroup counts exceed pooled counts")
    passes = all(c["passes"] for c in checks)
    if (report["numerical_checks_pass"] != passes or report["eligible_for_activation"] !=
            (passes and report["binding"]["evidence_type"] == "observed")):
        raise InputError("Holdout eligibility is inconsistent with recorded evidence")


def render_holdout_report(report: dict) -> str:
    import html
    verify_holdout_report(report)
    def fmt(value):
        return 'unknown' if value is None else f'{value:.6f}'
    lines = ['# JEV held-out acceptance-gate validation', '',
             f"Evidence type: **{report['binding']['evidence_type']}**. Status: **{report['status']}**.", '',
             '**This report never authorizes deployment.** Synthetic outcomes cannot qualify an integration for activation.', '',
             f"Frozen risk limit: {report['maximum_error']:.6f}; familywise alpha: {report['familywise_alpha']:.6f}.", '',
             '| Check | Scheduled observations | Accepted | Errors | Coverage | Error upper bound | Pass |',
             '|---|---:|---:|---:|---:|---:|---|']
    for check in report['checks']:
        group = html.escape(check['subgroup'] or 'Pooled').replace('|', r'\|').replace('\n', ' ')
        lines.append(f"| {group} | {check['observations']} | {check['accepted']} | {check['errors']} | {fmt(check['coverage'])} | {fmt(check['error_upper_bound'])} | {check['passes']} |")
    lines += ['', '## Limits', '', '\n\n'.join(report['limitations']), '',
              'Retain the frozen policy and report digests independently. Local files do not authenticate data collection, labels, or approval.', '',
              'Report digest: `' + report['contract_digest'] + '`.', '']
    return '\n'.join(lines)
