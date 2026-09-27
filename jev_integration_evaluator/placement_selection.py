"""Source-revalidated placement outcomes and explicitly reviewed experiments.

This module performs read-only preparation, not implementation, execution,
benefit certification, or activation. A review is caller-supplied data: neither
its author name nor a content hash authenticates an authority-bearing approval.
Existing source, semantic, binding, mutation, and execution gates stay separate.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

from . import capabilities as cap
from .config import DEFAULT
from .contracts import validate_contract
from .io import InputError, canonical, digest
from . import nomination_inventory as bridge
from .optimizer import REQUIRED, optimize

VERSION = "1.0"
CONTEXT = "repository-placement-context-v1"
SELECTION = "repository-placement-selection-v1"
SELECTION_REVIEW = "repository-placement-review-v1"
SCOPE_REVIEW = "repository-scope-review-v1"
MAX_BYTES = 16_000_000
MAX_SELECTIONS = 32
PATTERN_SCOPE = "all_existing_A_M_placements"
DENIED = {"execution": False, "mutation": False, "egress": False,
          "installation": False, "publication": False, "activation": False}
BOUND_KEYS = ("max_calls_total", "max_cost_total_usd", "deadline_seconds")


def _bounded(value: Any) -> None:
    """Accept plain bounded JSON, not executable adapters or custom objects."""
    stack = [(value, 0)]
    seen = 0
    while stack:
        item, depth = stack.pop()
        seen += 1
        if seen > 200_000 or depth > 64:
            raise cap.CapabilityError("selection_structure_budget")
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise cap.CapabilityError("invalid_selection_json")
            stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            stack.extend((v, depth + 1) for v in item)
        elif item is None or type(item) in (str, bool):
            continue
        elif type(item) is int:
            if item.bit_length() > 64:
                raise cap.CapabilityError("invalid_selection_number")
        elif type(item) is float:
            if not math.isfinite(item):
                raise cap.CapabilityError("invalid_selection_number")
        else:
            raise cap.CapabilityError("invalid_selection_json")
    try:
        if len(canonical(value)) > MAX_BYTES:
            raise cap.CapabilityError("selection_byte_budget")
    except (TypeError, ValueError, RecursionError) as exc:
        if isinstance(exc, cap.CapabilityError):
            raise
        raise cap.CapabilityError("invalid_selection_json") from None


def _validate(value: Any, contract: str) -> None:
    _bounded(value)
    try:
        validate_contract(value, contract)
    except InputError:
        raise cap.CapabilityError("invalid_" + contract.replace("-", "_")) from None


def _engine_identity() -> str:
    package = Path(__file__).parent
    return digest({
        "modules": {name: hashlib.sha256((package / (name + ".py")).read_bytes()).hexdigest()
                    for name in ("placement_selection", "optimizer")},
        "schemas": {name: hashlib.sha256((package / "data" / (name + ".schema.json")).read_bytes()).hexdigest()
                    for name in (CONTEXT, SELECTION, SELECTION_REVIEW, SCOPE_REVIEW)},
    })


def _seal(record: dict, field: str, contract: str) -> dict:
    record[field] = digest(record)
    _validate(record, contract)
    return record


def _fresh(repo: str | Path, report: dict, prepared: dict, review: dict,
           cfg: dict, policy: cap.DiscoveryPolicy | None) -> dict:
    for value in (report, prepared, review, cfg):
        _bounded(value)
    try:
        # This reconstructs discovery, admissions, inventory and semantic review.
        # In particular, no caller-authored inventory or rehashed wrapper is used.
        return bridge.review_nominated_inventory(repo, report, prepared, review,
                                                 cfg, policy=policy)
    except InputError:
        raise cap.CapabilityError("selection_source_review_rejected") from None


def _candidate_rows(report: dict, inventory: dict) -> list[dict]:
    rows = []
    for c in inventory["candidates"]:
        source = c["source"]
        matches = [s for s in report["seams"] if
                   (s["source"]["file"], s["source"]["qualified_symbol"],
                    s["source"]["file_sha256"]) ==
                   (source["file"], source["symbol"], source["file_sha256"])]
        seam = matches[0] if len(matches) == 1 else None
        review = c.get("semantic_review", {})
        # The legacy constructor sets approved=False before any review exists.
        # Only an authored, source-matched review can reject a placement.
        authored = (review.get("source_sha256") == source["source_sha256"]
                    and type(review.get("reviewer")) is str and bool(review["reviewer"].strip())
                    and type(review.get("reason")) is str and bool(review["reason"].strip()))
        reasons = []
        if (c["tier"] == 0 or c["pattern"] == "NONE"
                or c.get("hard_real_time") is True
                or c["deterministic_alternative"] in ("preferred", "mandatory")
                or (seam is not None and seam["eligibility"] == "ineligible")):
            state = "excluded"
            reasons.append("mandatory_deterministic_or_real_time_exclusion")
        elif seam is None or "ambiguous_symbol" in seam["reasons"]:
            state = "unsupported"
            reasons.append("missing_or_ambiguous_capability_seam")
        elif not authored:
            state = "semantic_review_required"
            reasons.append("source_matched_semantic_review_required")
        elif review.get("approved") is False:
            state = "semantic_rejection"
            reasons.append("source_matched_semantic_rejection")
        elif review.get("approved") is not True:
            state = "semantic_review_required"
            reasons.append("source_matched_semantic_review_required")
        elif seam["shape"] != "module-tail-call-v1-preflight":
            state = "unsupported"
            reasons.append("implementation_preconditions_not_established")
        else:
            state = "experimental_review_required"
            reasons.append("binding_preparation_and_separate_mutation_approval_required")
        rows.append({
            "candidate_id": c["candidate_id"], "pattern": c["pattern"],
            "seam_id": seam["seam_id"] if seam is not None else None,
            "state": state, "reasons": reasons,
            "source": {k: source[k] for k in ("file", "symbol", "start_line", "end_line",
                                               "file_sha256", "source_sha256")},
            "estimates": copy.deepcopy(c["estimates"]),
            "missing_estimates": [k for k in REQUIRED if c["estimates"].get(k) is None],
            "binding_review": "not_performed", "implementation_verified": False,
        })
    return sorted(rows, key=lambda row: row["candidate_id"])


def _scope_assessment(report: dict, prepared: dict, review: dict | None) -> dict:
    """A negative judgment needs full file AND seam coverage, not an empty list.

    The judgment is limited to the enumerated source/configuration and policy.
    Excluded files, unknown extensions, runtime-generated source, third-party
    dependencies and newly introduced placement recipes are outside that claim.
    """
    files = {f["file"]: f for f in report["files"]}
    seams = {s["seam_id"]: s for s in report["seams"]}
    result = {"provided": review is not None, "complete": False,
              "files_total": len(files), "files_reviewed": 0,
              "seams_total": len(seams), "seams_reviewed": 0,
              "missing_files": sorted(files), "missing_seams": sorted(seams),
              "unresolved": 0, "useful": 0, "no_useful_judgment": False,
              "review_sha256": None}
    if review is None:
        return result
    _validate(review, SCOPE_REVIEW)
    if (review["report_sha256"] != report["report_sha256"]
            or review["prepared_sha256"] != prepared["prepared_sha256"]):
        raise cap.CapabilityError("stale_source_scope_review")
    if not review["reviewer"].strip() or not review["reason"].strip():
        raise cap.CapabilityError("invalid_scope_review_text")
    seen_files, seen_seams = set(), set()
    decisions = []
    for row in review["files"]:
        path = row["file"]
        if path not in files or path in seen_files:
            raise cap.CapabilityError("unknown_or_duplicate_scope_file")
        seen_files.add(path)
        f = files[path]
        if (row["file_sha256"] != f["sha256"] or type(row["line_count"]) is not int
                or row["line_count"] != f["line_count"]):
            raise cap.CapabilityError("stale_scope_file_anchor")
        if not row["reason"].strip():
            raise cap.CapabilityError("invalid_scope_review_text")
        decisions.append(row["disposition"])
    for row in review["seams"]:
        sid = row["seam_id"]
        if sid not in seams or sid in seen_seams:
            raise cap.CapabilityError("unknown_or_duplicate_scope_seam")
        seen_seams.add(sid)
        if row["source"] != seams[sid]["source"]:
            raise cap.CapabilityError("stale_scope_seam_anchor")
        if not row["reason"].strip():
            raise cap.CapabilityError("invalid_scope_review_text")
        if row["disposition"] == "useful" and seams[sid]["eligibility"] == "ineligible":
            raise cap.CapabilityError("scope_review_cannot_waive_mandatory_exclusion")
        decisions.append(row["disposition"])
    complete = seen_files == set(files) and seen_seams == set(seams)
    result.update({
        "complete": complete, "files_reviewed": len(seen_files),
        "seams_reviewed": len(seen_seams),
        "missing_files": sorted(set(files) - seen_files),
        "missing_seams": sorted(set(seams) - seen_seams),
        "unresolved": decisions.count("unresolved"), "useful": decisions.count("useful"),
        # Avoid vacuous approval for a completely empty repository/schedule.
        "no_useful_judgment": bool(files) and complete and bool(decisions)
                              and all(d == "no_useful_placement" for d in decisions),
        "review_sha256": digest(review),
    })
    return result


def prepare_placement_context(repo: str | Path, report: dict, prepared: dict,
                              semantic_review: dict, cfg: dict, *,
                              scope_review: dict | None = None,
                              policy: cap.DiscoveryPolicy | None = None) -> dict:
    """Rebuild trusted source facts and return explicit read-only next actions."""
    engine = _engine_identity()
    reviewed = _fresh(repo, report, prepared, semantic_review, cfg, policy)
    inventory = reviewed["inventory"]
    rows = _candidate_rows(report, inventory)
    scope = _scope_assessment(report, prepared, scope_review)
    # These are review judgments, not measurements. Contradictory judgments are
    # unresolved even when one envelope has a more recent-looking timestamp.
    approved_ids = {c["candidate_id"] for c in inventory["candidates"]
                    if c.get("semantic_review", {}).get("approved") is True}
    contradictory = scope["no_useful_judgment"] and bool(approved_ids)
    coverage_complete = (report["coverage"]["complete_within_policy"] is True
                         and inventory["coverage"]["analysis_complete_within_policy"] is True
                         and not inventory["coverage"]["nomination_bridge"]["withheld_candidates"])
    available = [r["candidate_id"] for r in rows if r["state"] == "experimental_review_required"]
    if not coverage_complete:
        outcome, action = "incomplete_analysis", "resolve_analysis_coverage"
    elif contradictory:
        outcome, action = "insufficient_evidence", "reconcile_conflicting_semantic_reviews"
    elif scope["no_useful_judgment"]:
        outcome, action = "no_useful_placement", "retain_baseline_within_reviewed_scope"
    elif scope["provided"] and (not scope["complete"] or scope["unresolved"]):
        outcome, action = "insufficient_evidence", "complete_source_scope_review"
    elif available:
        outcome, action = "experimental_review_required", "review_explicit_experimental_selection"
    elif scope["useful"]:
        outcome, action = "nomination_required", "nominate_source_reviewed_placement"
    elif not rows:
        outcome, action = "no_candidates_discovered", "review_source_scope_or_nominate"
    elif all(r["state"] == "excluded" for r in rows):
        outcome, action = "deterministic_rejection", "retain_mandatory_exclusions"
    elif any(r["state"] == "unsupported" for r in rows):
        outcome, action = "unsupported", "qualify_missing_implementation_strategy"
    elif all(r["state"] in ("excluded", "semantic_rejection") for r in rows):
        outcome, action = "source_scope_review_required", "review_complete_source_scope"
    else:
        outcome, action = "semantic_review_required", "review_source_matched_candidates"
    optimization = optimize(copy.deepcopy(inventory), copy.deepcopy(cfg["constraints"]))
    # The optimizer's zero-valued baseline is not a measured zero-benefit finding.
    optimization_summary = {
        "declared_model_status": optimization["status"],
        "eligible_candidates": optimization["eligible_candidates"],
        "status": "insufficient_estimates" if any(r["missing_estimates"] for r in rows)
                  else "no_supported_benefit_claim",
        "benefit_supported": False,
        "no_useful_placement_inferred": False,
    }
    result = {
        "schema_version": VERSION, "contract": CONTEXT,
        "selection_engine_sha256": engine,
        "report_sha256": report["report_sha256"],
        "prepared_sha256": prepared["prepared_sha256"],
        "reviewed_sha256": reviewed["reviewed_sha256"],
        "semantic_review_sha256": digest(semantic_review),
        "settings_sha256": digest(cfg), "policy_sha256": digest(report["policy"]),
        "snapshot_scope": report["snapshot_scope"],
        "outcome": outcome, "next_action": action,
        "coverage_complete_within_policy": coverage_complete,
        "excluded_entries": report["coverage"]["excluded_entries"],
        "scope_review": scope, "candidates": rows,
        "experimental_candidate_ids": available,
        "conflicts": [{"a": x["a"], "b": x["b"]} for x in inventory["interactions"] if x.get("conflict")],
        "optimization": optimization_summary,
        "runtime_mode": "off", "benefit_supported": False,
        "authority_authenticated": False, "authorization": dict(DENIED),
    }
    # Close the analysis window. This does not claim filesystem transactionality.
    final = bridge.discover_repository_capabilities(repo, cfg, policy=policy)
    if canonical(final) != canonical(report) or _engine_identity() != engine:
        raise cap.CapabilityError("source_or_selection_engine_changed")
    return _seal(result, "context_sha256", CONTEXT)


def select_experimental_placements(repo: str | Path, report: dict, prepared: dict,
                                   semantic_review: dict, selection_review: dict,
                                   cfg: dict, *, scope_review: dict | None = None,
                                   policy: cap.DiscoveryPolicy | None = None) -> dict:
    """Choose an exact reviewed set without making unknown estimates numerical.

    The result is an experimental selection plan, not an implementation bundle.
    Multi-placement mutation requires the separately qualified composite path.
    Even finite spending bounds do not grant egress or execution authority.
    """
    _validate(selection_review, SELECTION_REVIEW)
    if not selection_review["reviewer"].strip() or not selection_review["reason"].strip():
        raise cap.CapabilityError("invalid_selection_review_text")
    context = prepare_placement_context(repo, report, prepared, semantic_review, cfg,
                                        scope_review=scope_review, policy=policy)
    if selection_review["context_sha256"] != context["context_sha256"]:
        raise cap.CapabilityError("stale_selection_review")
    bounds = selection_review["resource_bounds"]
    if bounds["max_calls_total"] is not None and type(bounds["max_calls_total"]) is not int:
        raise cap.CapabilityError("invalid_selection_call_bound")
    requested = selection_review["candidate_ids"]
    if len(requested) != len(set(requested)):
        raise cap.CapabilityError("duplicate_selected_candidate")
    by_id = {r["candidate_id"]: r for r in context["candidates"]}
    failures = []
    for cid in requested:
        if cid not in by_id:
            failures.append({"candidate_id": cid, "reason": "unknown_selected_candidate"})
        elif by_id[cid]["state"] != "experimental_review_required":
            failures.append({"candidate_id": cid, "reason": by_id[cid]["state"]})
    chosen = set(requested)
    # Interactions are reconstructed facts, not supplied selection overrides.
    interactions = context["conflicts"]
    for interaction in interactions:
        if {interaction["a"], interaction["b"]} <= chosen:
            for cid in sorted({interaction["a"], interaction["b"]}):
                failures.append({"candidate_id": cid, "reason": "conflicting_selected_placements"})
    if selection_review["approved"] is not True:
        failures.extend({"candidate_id": cid, "reason": "experimental_review_not_approved"}
                        for cid in requested)
    if context["outcome"] != "experimental_review_required":
        failures.extend({"candidate_id": cid, "reason": context["outcome"]} for cid in requested)
    failures = sorted({(r["candidate_id"], r["reason"]) for r in failures})
    selected = [] if failures else sorted(requested)
    result = {
        "schema_version": VERSION, "contract": SELECTION,
        "context_sha256": context["context_sha256"],
        "selection_review_sha256": digest(selection_review),
        "report_sha256": report["report_sha256"],
        "reviewed_sha256": context["reviewed_sha256"],
        "selection_engine_sha256": context["selection_engine_sha256"],
        "status": "blocked" if failures else "experimental_selection",
        "requested_candidate_ids": sorted(requested), "selected_candidate_ids": selected,
        "requested_count": len(requested), "selected_count": len(selected),
        "failures": [{"candidate_id": cid, "reason": reason} for cid, reason in failures],
        "placements": [copy.deepcopy(by_id[cid]) for cid in selected],
        "resource_bounds": copy.deepcopy(bounds),
        "missing_resource_bounds": [k for k in BOUND_KEYS if bounds[k] is None],
        "next_action": "resolve_selection_failures" if failures else "prepare_source_bound_bindings",
        "requires_composite_transaction": len(selected) > 1,
        "binding_review": "not_performed", "implementation_verified": False,
        "runtime_mode": "off", "benefit_supported": False,
        "authority_authenticated": False, "authorization": dict(DENIED),
    }
    final = prepare_placement_context(repo, report, prepared, semantic_review, cfg,
                                      scope_review=scope_review, policy=policy)
    if canonical(final) != canonical(context):
        raise cap.CapabilityError("source_or_review_changed_during_selection")
    return _seal(result, "selection_sha256", SELECTION)


def revalidate_experimental_selection(repo: str | Path, report: dict, prepared: dict,
                                      semantic_review: dict, selection_review: dict,
                                      selection: dict, cfg: dict, *,
                                      expected_selection_sha256: str,
                                      scope_review: dict | None = None,
                                      policy: cap.DiscoveryPolicy | None = None) -> dict:
    """Reconstruct a retained plan before any consumer considers using it.

    The expected digest must come from an independently retained channel. It is
    an identity anchor, not a grant of mutation, execution, or spending authority.
    """
    _validate(selection, SELECTION)
    if (type(expected_selection_sha256) is not str
            or not cap.HEX.fullmatch(expected_selection_sha256)):
        raise cap.CapabilityError("external_selection_anchor_required")
    fresh = select_experimental_placements(repo, report, prepared, semantic_review,
                                           selection_review, cfg,
                                           scope_review=scope_review, policy=policy)
    if (fresh["selection_sha256"] != expected_selection_sha256
            or canonical(fresh) != canonical(selection)):
        raise cap.CapabilityError("stale_or_tampered_experimental_selection")
    return fresh


def _external(path: Path, repo: Path) -> Any:
    root, resolved = repo.resolve(strict=True), path.resolve(strict=True)
    if resolved == root or root in resolved.parents:
        raise cap.CapabilityError("selection_input_must_be_external")
    return cap._load(path, max_bytes=MAX_BYTES)


def main(argv: list[str] | None = None) -> int:
    class Parser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            raise cap.CapabilityError("invalid_selection_arguments")

    parser = Parser(description=__doc__)
    parser.add_argument("operation", choices=("context", "select", "revalidate"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--semantic-review", type=Path, required=True)
    parser.add_argument("--selection-review", type=Path)
    parser.add_argument("--scope-review", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--expected-selection-sha256")
    parser.add_argument("--config-json", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        if args.operation == "context" and (args.selection_review or args.selection
                                              or args.expected_selection_sha256):
            raise cap.CapabilityError("unexpected_selection_arguments")
        if args.operation in ("select", "revalidate") and not args.selection_review:
            raise cap.CapabilityError("selection_review_required")
        if args.operation == "select" and (args.selection or args.expected_selection_sha256):
            raise cap.CapabilityError("unexpected_revalidation_arguments")
        if args.operation == "revalidate" and (not args.selection or not args.expected_selection_sha256):
            raise cap.CapabilityError("selection_and_external_anchor_required")
        cfg = _external(args.config_json, args.repo) if args.config_json else copy.deepcopy(DEFAULT)
        policy = cap.DiscoveryPolicy.from_json(_external(args.policy, args.repo)) if args.policy else None
        common = (args.repo, _external(args.report, args.repo),
                  _external(args.prepared, args.repo), _external(args.semantic_review, args.repo))
        kw = {"scope_review": _external(args.scope_review, args.repo) if args.scope_review else None,
              "policy": policy}
        if args.operation == "context":
            result = prepare_placement_context(*common, cfg, **kw)
        elif args.operation == "select":
            result = select_experimental_placements(*common,
                        _external(args.selection_review, args.repo), cfg, **kw)
        else:
            result = revalidate_experimental_selection(*common,
                        _external(args.selection_review, args.repo),
                        _external(args.selection, args.repo), cfg,
                        expected_selection_sha256=args.expected_selection_sha256, **kw)
        cap._write_out(args.out, args.repo, result)
        # Writing a well-formed blocked record is not successful selection.
        # Keep the complete requested denominator in the private artifact while
        # exposing only stable non-sensitive next-action/status codes publicly.
        outcome = result.get("status", result.get("outcome"))
        print(json.dumps({"status": "written", "artifact_sha256": digest(result),
                          "outcome": outcome, "next_action": result["next_action"]}))
        return 2 if outcome == "blocked" else 0
    except cap.CapabilityError as exc:
        print(json.dumps({"status": "blocked", "reason": exc.code}), file=sys.stderr)
        return 2
    except (OSError, InputError):
        print(json.dumps({"status": "blocked", "reason": "selection_input_or_filesystem_unavailable"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
