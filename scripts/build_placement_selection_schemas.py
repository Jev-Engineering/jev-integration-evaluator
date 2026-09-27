"""Rebuild the additive selection contracts; never read or execute a target."""
from __future__ import annotations
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
CID = {"type": "string", "pattern": "^JEV-[A-Z0-9-]+$", "maxLength": 128}
BOOL = {"type": "boolean"}
NULL_HASH = {"anyOf": [HASH, {"type": "null"}]}


def text(maximum=2048, minimum=1):
    return {"type": "string", "minLength": minimum, "maxLength": maximum}


def integer(minimum=0, maximum=100_000):
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


def obj(props, required=None):
    return {"type": "object", "properties": props,
            "required": list(props) if required is None else required,
            "additionalProperties": False}


def arr(item, maximum, minimum=0, unique=False):
    result = {"type": "array", "items": item, "minItems": minimum, "maxItems": maximum}
    if unique:
        result["uniqueItems"] = True
    return result


def enum(*values):
    return {"enum": list(values)}


def const(value):
    return {"const": value}


def nullable(value):
    return {"anyOf": [value, {"type": "null"}]}


def generate():
    package_data = ROOT / "jev_integration_evaluator" / "data"
    cap = json.loads((package_data / "repository-capabilities.schema.json").read_text())
    inventory = json.loads((package_data / "inventory.schema.json").read_text())
    estimates = copy.deepcopy(inventory["properties"]["candidates"]["items"]["properties"]["estimates"])
    source = copy.deepcopy(cap["properties"]["seams"]["items"]["properties"]["source"])
    disposition = enum("no_useful_placement", "useful", "unresolved")
    bounds = obj({"max_calls_total": nullable(integer(0, 1_000_000)),
                  "max_cost_total_usd": nullable({"type": "number", "minimum": 0, "maximum": 1_000_000}),
                  "deadline_seconds": nullable({"type": "number", "minimum": 0, "maximum": 604800})})
    denied = obj({k: const(False) for k in ("execution", "mutation", "egress", "installation", "publication", "activation")})
    pattern = enum(*"ABCDEFGHIJKLM", "NONE")
    row = obj({
        "candidate_id": CID, "pattern": pattern, "seam_id": NULL_HASH,
        "state": enum("excluded", "unsupported", "semantic_rejection", "semantic_review_required", "experimental_review_required"),
        "reasons": arr(text(128), 16, 1),
        "source": obj({"file": text(1024), "symbol": text(1024),
                       "start_line": integer(1, 10000000), "end_line": integer(1, 10000000),
                       "file_sha256": HASH, "source_sha256": HASH}),
        "estimates": estimates,
        "missing_estimates": arr(enum("quality_gain", "reliability_gain", "failure_reduction", "model_call_reduction", "added_latency_ms", "added_cost", "calls_per_task", "complexity", "maintenance", "false_positive_rate", "false_negative_rate", "risk", "throughput"), 13, unique=True),
        "binding_review": const("not_performed"), "implementation_verified": const(False),
    })
    common = {"runtime_mode": const("off"), "benefit_supported": const(False),
              "authority_authenticated": const(False), "authorization": denied}
    scope_summary = obj({
        "provided": BOOL, "complete": BOOL,
        "files_total": integer(0, 10000), "files_reviewed": integer(0, 10000),
        "seams_total": integer(0, 10000), "seams_reviewed": integer(0, 10000),
        "missing_files": arr(text(1024), 10000, unique=True),
        "missing_seams": arr(HASH, 10000, unique=True),
        "unresolved": integer(0, 20000), "useful": integer(0, 20000),
        "no_useful_judgment": BOOL, "review_sha256": NULL_HASH,
    })
    context = obj({
        "schema_version": const("1.0"), "contract": const("repository-placement-context-v1"),
        "selection_engine_sha256": HASH, "report_sha256": HASH, "prepared_sha256": HASH,
        "reviewed_sha256": HASH, "semantic_review_sha256": HASH,
        "settings_sha256": HASH, "policy_sha256": HASH,
        "snapshot_scope": const("bounded_source_and_configuration_not_full_repository"),
        "outcome": enum("incomplete_analysis", "insufficient_evidence", "no_useful_placement", "experimental_review_required", "nomination_required", "no_candidates_discovered", "deterministic_rejection", "unsupported", "source_scope_review_required", "semantic_review_required"),
        "next_action": enum("resolve_analysis_coverage", "reconcile_conflicting_semantic_reviews", "retain_baseline_within_reviewed_scope", "complete_source_scope_review", "review_explicit_experimental_selection", "nominate_source_reviewed_placement", "review_source_scope_or_nominate", "retain_mandatory_exclusions", "qualify_missing_implementation_strategy", "review_complete_source_scope", "review_source_matched_candidates"),
        "coverage_complete_within_policy": BOOL, "excluded_entries": integer(),
        "scope_review": scope_summary, "candidates": arr(row, 10000),
        "experimental_candidate_ids": arr(CID, 10000, unique=True),
        "conflicts": arr(obj({"a": CID, "b": CID}), 100000),
        "optimization": obj({"declared_model_status": enum("no_justified_integration_set", "conditional_on_declared_estimates"),
                             "eligible_candidates": integer(0, 10000),
                             "status": enum("insufficient_estimates", "no_supported_benefit_claim"),
                             "benefit_supported": const(False), "no_useful_placement_inferred": const(False)}),
        **common, "context_sha256": HASH,
    })
    selection = obj({
        "schema_version": const("1.0"), "contract": const("repository-placement-selection-v1"),
        "context_sha256": HASH, "selection_review_sha256": HASH,
        "report_sha256": HASH, "reviewed_sha256": HASH, "selection_engine_sha256": HASH,
        "status": enum("blocked", "experimental_selection"),
        "requested_candidate_ids": arr(CID, 32, 1, True),
        "selected_candidate_ids": arr(CID, 32, 0, True),
        "requested_count": integer(1, 32), "selected_count": integer(0, 32),
        "failures": arr(obj({"candidate_id": CID, "reason": text(128)}), 1024),
        "placements": arr(row, 32), "resource_bounds": bounds,
        "missing_resource_bounds": arr(enum("max_calls_total", "max_cost_total_usd", "deadline_seconds"), 3, unique=True),
        "next_action": enum("resolve_selection_failures", "prepare_source_bound_bindings"),
        "requires_composite_transaction": BOOL,
        "binding_review": const("not_performed"), "implementation_verified": const(False),
        **common, "selection_sha256": HASH,
    })
    selection_review = obj({
        "schema_version": const("1.0"), "contract": const("repository-placement-review-v1"),
        "context_sha256": HASH, "candidate_ids": arr(CID, 32, 1, True),
        "reviewer": text(256), "reason": text(2048), "approved": BOOL,
        "mode": const("experimental"), "resource_bounds": bounds,
    })
    scope_review = obj({
        "schema_version": const("1.0"), "contract": const("repository-scope-review-v1"),
        "report_sha256": HASH, "prepared_sha256": HASH,
        "reviewer": text(256), "reason": text(2048),
        "pattern_scope": const("all_existing_A_M_placements"),
        "snapshot_scope": const("bounded_source_and_configuration_not_full_repository"),
        "files": arr(obj({"file": text(1024), "file_sha256": HASH,
                          "line_count": integer(0, 4194304), "coverage": const("entire_file"),
                          "disposition": disposition, "reason": text(2048)}), 10000),
        "seams": arr(obj({"seam_id": HASH, "source": source,
                          "disposition": disposition, "reason": text(2048)}), 10000),
    })
    for name, schema in [("repository-placement-context-v1", context),
                         ("repository-placement-selection-v1", selection),
                         ("repository-placement-review-v1", selection_review),
                         ("repository-scope-review-v1", scope_review)]:
        data = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "urn:jev-integration-evaluator:" + name, **schema}
        encoded = (json.dumps(data, indent=2, allow_nan=False) + "\n").encode()
        for parent in (package_data, ROOT / "schemas"):
            (parent / (name + ".schema.json")).write_bytes(encoded)


if __name__ == "__main__":
    generate()
