"""Frozen operational windows with complete assignment denominators and drift checks.

These are operational guardrails, NOT sequential hypothesis tests or causal
estimates. A healthy window never increases exposure or authorizes deployment.
"""
from __future__ import annotations

import math
from collections import Counter
from statistics import mean
from .cohorts import canary_arm
from .contracts import seal, verify, validate_contract, utc_now, parse_utc
from .io import InputError, finite, digest, markdown

METRICS = ("latency_ms", "cost", "unsafe_actions", "fallbacks", "decisions", "action_counts")
STATUS = ("completed", "failed", "timeout", "cancelled", "not_run")


def _assignments(spec: dict) -> list[dict]:
    ids, hashes = set(), set()
    clusters = {}
    result = []
    for row in spec["tasks"]:
        if row["task_id"] in ids or row["task_hash"] in hashes:
            raise InputError("Monitoring schedule requires unique task IDs and hashes")
        ids.add(row["task_id"]); hashes.add(row["task_hash"])
        arm = canary_arm(row["task_id"], spec["assignment_salt"], spec["canary_fraction"])
        if row["cluster_id"] in clusters:
            # Multiple task records for one independent unit can amplify counts
            # even without a formal significance test. Require host aggregation.
            raise InputError("Aggregate correlated monitoring tasks to one scheduled cluster")
        clusters[row["cluster_id"]] = arm
        result.append({**row, "arm": arm})
    return result


def _validate_spec(spec: dict) -> list[dict]:
    validate_contract(spec, "monitor-spec")
    start, end = parse_utc(spec["starts_at"]), parse_utc(spec["ends_at"])
    if end <= start:
        raise InputError("Monitoring window end must be later than its start")
    if not math.isclose(math.fsum(spec["action_reference"].values()), 1, abs_tol=1e-10, rel_tol=0):
        raise InputError("Frozen reference action proportions must sum to one")
    assignments = _assignments(spec)
    cohorts = {r["cohort"] for r in assignments}
    if not set(spec["required_cohorts"]) <= cohorts:
        raise InputError("Required monitoring cohort is absent from the schedule")
    for group in [None] + spec["required_cohorts"]:
        counts = Counter(r["arm"] for r in assignments if group is None or r["cohort"] == group)
        if any(counts[arm] < spec["minimum_tasks_per_arm"] for arm in ("baseline", "jev")):
            raise InputError("Frozen monitoring cohort has too few assigned tasks in an arm")
    return assignments


def freeze_monitor(spec: dict) -> dict:
    assignments = _validate_spec(spec)
    result = seal({"schema_version": "1.2", "kind": "frozen_monitor", "frozen_at": utc_now(),
                   "specification": spec, "assignments": assignments,
                   "authorization": "no_network_no_execution_no_exposure_expansion"})
    validate_contract(result, "monitor")
    return result


def _p95(values: list[float]) -> float | None:
    return sorted(values)[math.ceil(.95 * len(values)) - 1] if values else None


def evaluate_monitor(plan: dict, rows: list[dict], *, expected_digest: str | None = None,
                     as_of: str | None = None) -> dict:
    validate_contract(plan, "monitor")
    verify(plan, expected=expected_digest)
    spec = plan["specification"]
    assignments = _validate_spec(spec)
    if assignments != plan["assignments"]:
        raise InputError("Recorded monitoring assignments differ from the frozen task scope")
    if not isinstance(rows, list):
        raise InputError("Monitoring outcomes must be a list of task records")
    now = parse_utc(as_of or utc_now())
    start, end = parse_utc(spec["starts_at"]), parse_utc(spec["ends_at"])
    assigned = {r["task_id"]: r for r in assignments}
    seen = {}; incomplete = set()
    for row in rows:
        validate_contract(row, "monitor-outcome")
        task = row["task_id"]
        if task in seen or task not in assigned:
            raise InputError("Duplicate or unscheduled monitoring outcome")
        if any(row[k] != assigned[task][k] for k in ("task_hash", "cluster_id", "cohort", "arm")):
            raise InputError("Monitoring task identity or canary assignment changed")
        if any(row[k] != spec[k] for k in ("deployment_id", "window_id", "study_digest", "evidence_type")):
            raise InputError("Monitoring outcome differs from frozen deployment/window/evidence identity")
        if row["monitor_digest"] != plan["contract_digest"]:
            raise InputError("Monitoring outcome differs from the frozen policy")
        began, finished = parse_utc(row["started_at"]), parse_utc(row["finished_at"])
        if not start <= began < end or finished < began or finished > now:
            raise InputError("Monitoring outcome has an invalid or future observation time")
        if row["run_status"] != "completed" and row["success"] is True:
            raise InputError("Failed or incomplete monitoring task cannot count as success")
        if row.get("success") is None or any(row.get(k) is None for k in METRICS):
            incomplete.add(task)
        # Keep known safety events from incomplete records; never silently drop
        # an incident merely because a billing or latency field is missing.
        for key in ("latency_ms", "cost", "unsafe_actions", "fallbacks", "decisions"):
            if row.get(key) is not None:
                finite(row[key], key, 0)
        if row.get("fallbacks") is not None and row.get("decisions") is not None and row["fallbacks"] > row["decisions"]:
            raise InputError("Fallback count exceeds decision count")
        if row.get("action_counts") is not None:
            count = sum(row["action_counts"].values())
            if row.get("decisions") is not None and count != row["decisions"]:
                raise InputError("Action counts must cover every recorded decision, including fallbacks and abstentions")
        seen[task] = row
    missing = set(assigned) - set(seen)
    all_complete = not missing and not incomplete
    group_checks = []
    any_breach = False
    insufficient_actions = False
    for cohort in [None] + spec["required_cohorts"]:
        expected = [r for r in assignments if cohort is None or r["cohort"] == cohort]
        members = [seen[r["task_id"]] for r in expected if r["task_id"] in seen]
        arms = {arm: [r for r in members if r["arm"] == arm] for arm in ("baseline", "jev")}
        complete = all(r["task_id"] in seen and r["task_id"] not in incomplete for r in expected)
        counts = {arm: sum(r["arm"] == arm for r in expected) for arm in arms}
        metrics = {"unsafe_actions": sum(r.get("unsafe_actions") or 0 for r in arms["jev"])}
        # Only compute comparative point summaries when the entire group is
        # observed; a missing arm member must not improve the denominator.
        metrics.update({k: None for k in spec["limits"] if k != "unsafe_actions"})
        distribution_status = "unavailable_in_incomplete_window"
        if complete:
            b, j = arms["baseline"], arms["jev"]
            metrics["failure_rate"] = mean(not r["success"] for r in j)
            metrics["timeout_rate"] = mean(r["run_status"] == "timeout" for r in j)
            metrics["failure_rate_increase"] = mean(not r["success"] for r in j) - mean(not r["success"] for r in b)
            metrics["p95_added_latency_ms"] = _p95([r["latency_ms"] for r in j]) - _p95([r["latency_ms"] for r in b])
            metrics["mean_added_cost"] = mean(r["cost"] for r in j) - mean(r["cost"] for r in b)
            decisions = sum(r["decisions"] for r in j)
            metrics["fallback_rate"] = sum(r["fallbacks"] for r in j) / decisions if decisions else None
            action_counts = Counter()
            for r in j:
                action_counts.update(r["action_counts"])
            action_n = sum(action_counts.values())
            if action_n >= spec["minimum_action_observations"]:
                reference = spec["action_reference"]
                # Unknown labels retain their own mass, rather than disappearing.
                metrics["action_distribution_tv"] = .5 * math.fsum(abs(action_counts[k] / action_n - reference.get(k, 0))
                                                                    for k in set(reference) | set(action_counts))
                distribution_status = "descriptive_fixed_reference_comparison"
            else:
                distribution_status = "insufficient_action_observations"
                insufficient_actions = True
            if decisions == 0:
                insufficient_actions = True
        breaches = [k for k, limit in spec["limits"].items() if metrics[k] is not None and metrics[k] > limit]
        any_breach = any_breach or bool(breaches)
        group_checks.append({"cohort": cohort, "scheduled_tasks": counts,
                             "received_tasks": {arm: len(rs) for arm, rs in arms.items()},
                             "complete": complete, "metrics": metrics, "breaches": breaches,
                             "action_distribution_status": distribution_status,
                             "unsafe_count_status": "complete" if complete else "known_lower_bound"})
    before_close = now < end
    lateness = max(0.0, (now - end).total_seconds())
    overdue = lateness > spec["reporting_grace_s"]
    stale = lateness > spec["reporting_grace_s"] + spec["max_report_age_s"]
    if any_breach:
        status = "guardrail_breach"
        recommendation = "suspend"
    elif stale:
        status = "stale_window"
        recommendation = "suspend"
    elif not all_complete and overdue:
        status = "incomplete_overdue_window"
        recommendation = "suspend"
    elif before_close:
        status = "window_open"
        recommendation = "await_complete_window"
    elif not all_complete:
        status = "awaiting_outcomes"
        recommendation = "await_complete_window"
    elif insufficient_actions:
        status = "insufficient_action_evidence"
        recommendation = "inspect"
    else:
        status = "within_declared_limits"
        recommendation = "maintain_current_exposure"
    operational_pass = status == "within_declared_limits"
    result = seal({"schema_version": "1.2", "kind": "monitor_report", "monitor_digest": plan["contract_digest"],
                   "deployment_id": spec["deployment_id"], "study_digest": spec["study_digest"], "window_id": spec["window_id"],
                   "evidence_type": spec["evidence_type"], "as_of": now.isoformat(), "status": status,
                   "recommendation": recommendation, "operational_checks_pass": operational_pass,
                   "eligible_for_continued_canary": operational_pass and spec["evidence_type"] == "observed" and expected_digest is not None,
                   "scheduled_tasks": len(assignments), "received_tasks": len(rows),
                   "missing_tasks": len(missing), "incomplete_tasks": len(incomplete),
                   "missing_task_id_hashes": sorted(digest(x) for x in missing),
                   "incomplete_task_id_hashes": sorted(digest(x) for x in incomplete),
                   "checks": group_checks, "externally_pinned_digest": expected_digest is not None,
                   "stale": stale, "deployment_authorized": False, "exposure_expansion_authorized": False,
                   "limits": ["Metrics are operational point summaries, not statistical significance or causal estimates.",
                              "Empirical p95 uses nearest rank; the latency difference is between arm quantiles, not a paired latency quantile.",
                              "No optional-stopping or repeated-window probability guarantee is claimed.",
                              "Missing outcomes and unknown costs cannot silently pass monitoring.",
                              "Frozen reference action drift is descriptive and does not alone establish model quality degradation.",
                              "Assignment IDs, observed labels and local timestamps need independently trusted provenance.",
                              "A healthy window does not prove overall safety or authorize a larger canary."]})
    return result


def suspend_from_monitor(plan: dict, rows: list[dict], routers: dict, *, expected_digest: str,
                         approved_deployment_id: str) -> dict:
    """Explicit host hook: recompute current evidence and only latch routers OFF.

    This function never reads a precomputed pass/rollback boolean and never resumes
    a router. The host must separately authorize this hook and supply the actual
    deployed routers. Synthetic inputs cannot control a deployed router.
    """
    if not expected_digest:
        raise InputError("Host suspension requires an independently retained monitor digest")
    report = evaluate_monitor(plan, rows, expected_digest=expected_digest)
    spec = plan["specification"]
    if spec["evidence_type"] != "observed" or spec["deployment_id"] != approved_deployment_id:
        raise InputError("Host suspension requires observed evidence and exact deployment approval scope")
    from .runtime import SafeRouter
    if set(routers) != set(spec["runtime_contracts"]):
        raise InputError("Host router set differs from the frozen monitored deployment")
    for gate_id, router in routers.items():
        if (not isinstance(router, SafeRouter) or not router.require_runtime_binding
                or router.activation.get("runtime_contract_hash") != spec["runtime_contracts"][gate_id]
                or router.activation.get("deployment_id") != spec["deployment_id"]
                or router.activation.get("study_digest") != spec["study_digest"]
                or router.canary_scope != spec["assignment_salt"]
                or router.config["mode"] != "canary"
                or router.config["canary_fraction"] != spec["canary_fraction"]):
            raise InputError("Host router activation differs from frozen monitor scope")
    suspended = []
    if report["recommendation"] == "suspend":
        for gate_id, router in routers.items():
            router.suspend()
            suspended.append(gate_id)
    return seal({**report, "host_suspended_gate_ids": sorted(suspended), "host_resume_performed": False})


def render_monitor(report: dict) -> str:
    lines = ["# JEV canary operational window", "", f"Status: **{report['status']}**. Recommendation: **{report['recommendation']}**.", "",
             f"Evidence: {report['evidence_type']}. Scheduled: {report['scheduled_tasks']}; received: {report['received_tasks']}; missing: {report['missing_tasks']}; incomplete: {report['incomplete_tasks']}.", "",
             "No exposure expansion or deployment is authorized by this report.", "",
             "| Cohort | Complete | Breached guardrails |", "|---|---|---|"]
    for c in report["checks"]:
        lines.append(f"| {markdown(c['cohort'] or 'Pooled')} | {c['complete']} | {markdown(', '.join(c['breaches']) or 'None observed')} |")
    lines += ["", "## Interpretation limits", "", "\n\n".join(report["limits"]), ""]
    return "\n".join(lines)
