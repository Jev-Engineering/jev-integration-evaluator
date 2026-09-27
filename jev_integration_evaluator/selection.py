"""Source-bound placement selection, separate from execution and adoption.

This is a data-only decision contract. ``prepare_experimental_plan`` delegates
source/binding validation and actual code preparation to the existing engine;
no selector result grants target execution, mutation, live spend or activation.
"""
from __future__ import annotations

import copy
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import seal, validate_contract, verify
from .io import InputError, canonical, digest
from .optimizer import REQUIRED, optimize

VERSION = "placement-selection-v1"
MAX_INVENTORY_BYTES = 16_000_000
MAX_REQUEST_BYTES = 262_144
MAX_CANDIDATES = 2_000
MAX_OPTIMIZER_CANDIDATES = 64
MAX_INTERACTIONS = 10_000
CONSTRAINT_KEYS = (
    "max_added_latency_ms", "max_cost_per_task", "max_calls_per_task",
    "max_complexity", "max_risk", "required_throughput",
)
LIVE_BOUND_KEYS = ("max_total_cost", "max_total_calls", "max_concurrent_calls")
SELECTION_SCHEMAS = ("placement-selection-request", "placement-selection", "placement-estimates",
                     "placement-interaction", "placement-selection-envelope", "placement-selection-summary")


class SelectionError(InputError):
    """Redacted, stable diagnostics; source and proposal text are never echoed."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _bounded(value: Any, limit: int) -> bytes:
    try:
        encoded = canonical(value)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise SelectionError("invalid_json_value") from None
    if len(encoded) > limit:
        raise SelectionError("selection_input_byte_limit")
    return encoded


def _validate(value: dict, kind: str) -> None:
    try:
        validate_contract(value, kind)
    except (InputError, RecursionError):
        raise SelectionError("invalid_" + kind.replace("-", "_")) from None



def selection_engine_sha256() -> str:
    """Identify the selector, validator and optimizer bytes, not their pathname."""
    import hashlib
    root = Path(__file__).resolve().parent
    files = ["selection.py", "optimizer.py", "contracts.py", "io.py", "data/inventory.schema.json"]
    files += ["data/" + name + ".schema.json" for name in SELECTION_SCHEMAS]
    try:
        hashes = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
    except OSError:
        raise SelectionError("selection_engine_unavailable") from None
    return digest({"selection_version": VERSION, "files": hashes})

def request_sha256(request: dict) -> str:
    """A hash binds bytes. Computing it does not authenticate or approve them."""
    _bounded(request, MAX_REQUEST_BYTES)
    _validate(request, "placement-selection-request")
    return digest(request)



def _inventory_consistency(inventory: dict) -> None:
    """Validate supplied record agreement; this does not read live source."""
    identity = inventory["analysis_identity"]
    try:
        files = inventory["files"]
        configs = inventory["configuration_evidence"]
        if not isinstance(configs, list):
            raise SelectionError("invalid_analysis_records")
        indexed = {row["file"]: row for row in files}
        if len(indexed) != len(files):
            raise SelectionError("duplicate_source_file")
        for row in [*files, *configs]:
            path = row["file"]
            sha = row["sha256"]
            if (not isinstance(path, str) or not isinstance(sha, str) or len(sha) != 64
                    or any(c not in "0123456789abcdef" for c in sha)):
                raise SelectionError("invalid_analysis_records")
            normalized = PurePosixPath(path)
            if (not path or "\\" in path or "\x00" in path or normalized.is_absolute()
                    or str(normalized) != path or ".." in normalized.parts):
                raise SelectionError("invalid_source_path")
        expected = {
            "source_digest": digest(sorted((f["file"], f["sha256"]) for f in files)),
            "configuration_digest": digest(sorted((f["file"], f["sha256"]) for f in configs)),
            "parser_digest": digest(sorted((f["file"], f["parser"]) for f in files)),
            "coverage_digest": digest(inventory["coverage"]),
        }
        if any(identity[key] != value for key, value in expected.items()):
            raise SelectionError("analysis_record_mismatch")
        for candidate in inventory["candidates"]:
            source = candidate["source"]
            row = indexed.get(source["file"])
            if (row is None or source["file_sha256"] != row["sha256"]
                    or source["parser"] != row["parser"]
                    or source["end_line"] < source["start_line"]):
                raise SelectionError("candidate_source_record_mismatch")
    except SelectionError:
        raise
    except (KeyError, TypeError, ValueError):
        raise SelectionError("invalid_analysis_records") from None


def _review_state(candidate: dict) -> str:
    # Never trust a caller's tier or optimizer eligibility as the only gate.
    if (candidate["tier"] == 0 or candidate["pattern"] == "NONE"
            or candidate.get("hard_real_time") is True
            or candidate["deterministic_alternative"] in ("mandatory", "preferred")):
        return "deterministic_rejection"
    review = candidate["semantic_review"]
    if review["source_sha256"] != candidate["source"]["source_sha256"]:
        return "stale_semantic_review"
    if not all(isinstance(review.get(k), str) and review[k].strip()
               for k in ("reviewer", "reason")):
        return "semantic_review_required"
    if review["approved"] is not True:
        return "semantic_rejection"
    return "reviewed_candidate"


def _coverage_complete(inventory: dict) -> bool:
    """Conservative bounded-analysis completeness, never universal absence."""
    coverage = inventory.get("coverage", {})
    # Unknown coverage is not complete. Policy exclusions differ from unread
    # source: the legacy inventory cannot reliably distinguish all such rows,
    # so any ignored row prevents a negative conclusion here.
    counts = coverage.get("parser_counts")
    return (
        coverage.get("truncated") is False
        and coverage.get("warnings") == []
        and coverage.get("ignored") == []
        and isinstance(counts, dict)
        and all(k in ("python_ast", "typescript_ast") for k in counts)
        and all(type(v) is int and v >= 0 for v in counts.values())
        and coverage.get("files_analyzed") == sum(counts.values())
        and sum(counts.values()) == len(inventory["files"])
        and inventory.get("depth") != "QUICK"
    )


def _unselected_status(rows: list[dict], complete: bool) -> str:
    if not complete:
        return "incomplete_analysis"
    if not rows:
        return "no_candidates_discovered"
    states = {r["review_status"] for r in rows}
    if states == {"deterministic_rejection"}:
        return "deterministic_rejection"
    if states <= {"deterministic_rejection", "semantic_rejection"}:
        return "no_useful_placement_within_reviewed_inventory"
    if "stale_semantic_review" in states:
        return "stale_semantic_review"
    return "semantic_review_required"


def select_placement(inventory: dict, request: dict, *,
                     approved_request_sha256: str | None = None) -> dict:
    """Assess a caller-supplied inventory without reading/executing the target.

    A source-matched semantic review is necessary but is NOT fresh filesystem
    verification. The full inventory digest is pinned by the request. Actual
    source drift and recipe support are checked again by the implementation
    engine before a bundle can be prepared. A supplied approval must come from
    the caller's trusted channel; JSON fields cannot authorize themselves.
    """
    _bounded(inventory, MAX_INVENTORY_BYTES)
    _validate(inventory, "inventory")
    requested_digest = request_sha256(request)
    engine = selection_engine_sha256()
    if request["selection_engine_sha256"] != engine:
        raise SelectionError("selection_engine_mismatch")
    if request["inventory_sha256"] != digest(inventory):
        raise SelectionError("inventory_identity_mismatch")
    if (not inventory.get("analysis_identity")
            or digest(inventory["analysis_identity"]) != inventory["scan_fingerprint"]):
        raise SelectionError("analysis_identity_mismatch")
    _inventory_consistency(inventory)
    candidates = inventory["candidates"]
    if len(candidates) > MAX_CANDIDATES:
        raise SelectionError("candidate_limit")
    for candidate in candidates:
        _validate(candidate["estimates"], "placement-estimates")
    by_id = {c["candidate_id"]: c for c in candidates}
    if len(by_id) != len(candidates):
        raise SelectionError("duplicate_candidate_id")
    if len(inventory["interactions"]) > MAX_INTERACTIONS:
        raise SelectionError("interaction_limit")
    pairs = set()
    for interaction in inventory["interactions"]:
        _validate(interaction, "placement-interaction")
        pair = tuple(sorted((interaction["a"], interaction["b"])))
        if pair in pairs:
            raise SelectionError("duplicate_candidate_interaction")
        pairs.add(pair)
        if (interaction["a"] not in by_id or interaction["b"] not in by_id
                or interaction["a"] == interaction["b"]):
            raise SelectionError("invalid_candidate_interaction")
    selected_id = request["candidate_id"]
    if selected_id is not None and selected_id not in by_id:
        raise SelectionError("unknown_selected_candidate")
    rows = [{"candidate_id": c["candidate_id"],
             "source_sha256": c["source"]["source_sha256"],
             "review_status": _review_state(c),
             "missing_estimates": [k for k in REQUIRED if c["estimates"].get(k) is None],
             "estimate_provenance_present": isinstance(c["estimates"].get("provenance"), str)
                 and bool(c["estimates"]["provenance"].strip())}
            for c in sorted(candidates, key=lambda c: c["candidate_id"])]
    complete = _coverage_complete(inventory)
    result = {
        "schema_version": "1.0", "selection_version": VERSION,
        "selection_engine_sha256": engine,
        "mode": request["mode"], "request_sha256": requested_digest,
        "inventory_sha256": digest(inventory),
        "inventory_fingerprint": inventory["scan_fingerprint"],
        "coverage_complete_within_inventory": complete,
        "status": _unselected_status(rows, complete),
        "candidate_assessments": rows, "selected_candidate_ids": [],
        "selected_estimates": {}, "optimizer_result": None,
        "preparation_scope_ref": request["preparation_scope_ref"],
        "implementation_status": "not_checked",
        "live_limits": copy.deepcopy(request["live_limits"]),
        "missing_live_bounds": [k for k in LIVE_BOUND_KEYS if request["live_limits"][k] is None],
        "execution_authorized": False, "target_mutation_authorized": False,
        "live_spend_authorized": False, "runtime_activation_authorized": False,
        "benefit_demonstrated": False, "adoption_recommendation": None,
    }
    if request["mode"] == "experimental":
        row = next(r for r in rows if r["candidate_id"] == selected_id)
        result["status"] = row["review_status"]
        if row["review_status"] == "reviewed_candidate":
            if approved_request_sha256 is None:
                result["status"] = "selection_review_required"
            elif approved_request_sha256 != requested_digest:
                raise SelectionError("selection_approval_mismatch")
            else:
                result["status"] = "experimental_selected"
                result["selected_candidate_ids"] = [selected_id]
                result["selected_estimates"] = {
                    selected_id: copy.deepcopy(by_id[selected_id]["estimates"])}
    else:
        reviewed = {r["candidate_id"] for r in rows if r["review_status"] == "reviewed_candidate"}
        if len(reviewed) > MAX_OPTIMIZER_CANDIDATES:
            raise SelectionError("optimization_candidate_limit")
        if reviewed:
            # Do not send rejected/stale rows to a legacy optimizer that accepts
            # minimal historical records. Do retain those exclusions above.
            optimization_input = copy.deepcopy(inventory)
            optimization_input["candidates"] = [c for c in optimization_input["candidates"]
                                                  if c["candidate_id"] in reviewed]
            optimization_input["interactions"] = [x for x in optimization_input["interactions"]
                                                    if x["a"] in reviewed and x["b"] in reviewed]
            try:
                opt = optimize(optimization_input, request["constraints"], exact_limit=12, beam_width=128)
            except (InputError, KeyError, ValueError, TypeError, OverflowError):
                raise SelectionError("invalid_optimization_inputs") from None
            result["optimizer_result"] = opt
            chosen = opt["recommended_balanced_set"]["candidate_ids"]
            result["selected_candidate_ids"] = chosen
            result["selected_estimates"] = {cid: copy.deepcopy(by_id[cid]["estimates"]) for cid in chosen}
            result["status"] = (
                "estimate_based_optimization" if chosen
                else "insufficient_estimates" if any(r["missing_estimates"] for r in rows
                                                       if r["candidate_id"] in reviewed)
                else "missing_estimate_provenance" if any(not r["estimate_provenance_present"] for r in rows
                                                         if r["candidate_id"] in reviewed)
                else "no_feasible_positive_set_under_declared_model")
    _bounded(result, MAX_INVENTORY_BYTES)
    result = seal(result)
    _validate(result, "placement-selection")
    return result


def verify_selection(inventory: dict, request: dict, selection: dict, *,
                     approved_request_sha256: str | None = None) -> None:
    """Recompute decisions; a self-consistent forged selection is not accepted."""
    _bounded(selection, MAX_INVENTORY_BYTES)
    _validate(selection, "placement-selection")
    try:
        verify(selection)
    except InputError:
        raise SelectionError("selection_integrity_mismatch") from None
    actual = select_placement(inventory, request,
                              approved_request_sha256=approved_request_sha256)
    if actual != selection:
        raise SelectionError("selection_recomputation_mismatch")


def prepare_experimental_plan(root: str | Path, inventory: dict, request: dict,
                              spec: dict, output: str | Path, *,
                              approved_request_sha256: str) -> dict:
    """Prepare real edits with existing binding/source validators, never apply.

    The reviewed selection binds the exact binding specification as well as the
    full inventory. Separate baseline execution and exact apply approvals are
    still required by the existing lifecycle. Missing/stale/unsupported inputs
    never produce a supposedly usable implementation.
    """
    from .integrations.errors import MissingBinding, UnsupportedShape
    from .integrations.lifecycle import plan_implementation

    selection = select_placement(inventory, request,
                                 approved_request_sha256=approved_request_sha256)
    if request["mode"] != "experimental":
        raise SelectionError("experimental_request_required")
    if selection["status"] != "experimental_selected":
        return {"selection": selection, "implementation": None}
    _bounded(spec, 2_000_000)
    if request["implementation_spec_sha256"] is None:
        raise SelectionError("reviewed_specification_required")
    if request["implementation_spec_sha256"] != digest(spec):
        raise SelectionError("specification_identity_mismatch")
    try:
        implementation = plan_implementation(root, inventory, request["candidate_id"], spec, output)
    except UnsupportedShape:
        return {"selection": selection, "implementation": {
            "status": "unsupported_implementation", "target_modified": False,
            "target_executed": False}}
    except MissingBinding:
        return {"selection": selection, "implementation": {
            "status": "missing_prerequisite", "target_modified": False,
            "target_executed": False}}
    except InputError:
        raise SelectionError("implementation_validation_failed") from None
    except OSError:
        raise SelectionError("implementation_io_unavailable") from None
    return {"selection": selection, "implementation": implementation}


def main(argv: list[str] | None = None) -> int:
    """Bounded stdin envelope, redacted stdout summary; no implicit execution."""
    import argparse
    import json
    import re
    import sys
    from .io import loads

    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise SelectionError("invalid_selection_arguments")

    parser = Parser(description=(
        "Read one bounded JSON envelope from stdin: schema_version, inventory, "
        "request, and specification (null unless preparing a plan). "
        "Print metadata only. This command never applies or executes a target."))
    parser.add_argument("--approve-request", metavar="EXTERNALLY_REVIEWED_SHA256")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--bundle", type=Path)
    try:
        args = parser.parse_args(argv)
        if args.approve_request is not None and not re.fullmatch("[0-9a-f]{64}", args.approve_request):
            raise SelectionError("invalid_selection_approval")
        if args.prepare != (args.repo is not None and args.bundle is not None):
            raise SelectionError("invalid_preparation_arguments")
        if not args.prepare and (args.repo is not None or args.bundle is not None):
            raise SelectionError("invalid_preparation_arguments")
        if args.prepare and args.approve_request is None:
            raise SelectionError("external_selection_approval_required")
        limit = MAX_INVENTORY_BYTES + MAX_REQUEST_BYTES + 2_000_000 + 1024
        raw = sys.stdin.buffer.read(limit + 1)
        if len(raw) > limit:
            raise SelectionError("selection_input_byte_limit")
        try:
            envelope = loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            raise SelectionError("invalid_selection_envelope") from None
        if (not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "inventory", "request", "specification"}
                or envelope["schema_version"] != "1.0"
                or not isinstance(envelope["inventory"], dict)
                or not isinstance(envelope["request"], dict)):
            raise SelectionError("invalid_selection_envelope")
        _validate(envelope, "placement-selection-envelope")
        implementation = None
        if args.prepare:
            if not isinstance(envelope["specification"], dict):
                raise SelectionError("reviewed_specification_required")
            prepared = prepare_experimental_plan(
                args.repo, envelope["inventory"], envelope["request"],
                envelope["specification"], args.bundle,
                approved_request_sha256=args.approve_request)
            selection, implementation = prepared["selection"], prepared["implementation"]
        else:
            if envelope["specification"] is not None:
                raise SelectionError("unexpected_specification_without_preparation")
            selection = select_placement(envelope["inventory"], envelope["request"],
                                          approved_request_sha256=args.approve_request)
        # Do not echo source locations, request text, estimates' provenance,
        # scope references, host output, or private bundle paths to stdout.
        summary = {
            "schema_version": "1.0", "selection_version": VERSION,
            "selection_engine_sha256": selection["selection_engine_sha256"],
            "selection_status": selection["status"],
            "selection_sha256": selection["contract_digest"],
            "request_sha256": selection["request_sha256"],
            "selected_candidate_ids": selection["selected_candidate_ids"],
            "implementation_status": implementation["status"] if implementation else "not_prepared",
            "bundle_digest": implementation.get("bundle_digest") if implementation else None,
            "target_modified": False, "target_executed": False,
            "live_spend_authorized": False, "runtime_activation_authorized": False,
            "benefit_demonstrated": False,
        }
        _validate(summary, "placement-selection-summary")
        print(json.dumps(summary, sort_keys=True, allow_nan=False))
        return 0  # A truthful unsupported/blocked decision is a valid result.
    except SelectionError as exc:
        print(json.dumps({"schema_version": "1.0", "error": exc.code}), file=sys.stderr)
        return 2
    except (OSError, UnicodeError):
        print(json.dumps({"schema_version": "1.0", "error": "selection_environment_failure"}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"schema_version": "1.0", "error": "selection_cancelled"}), file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
