"""Read-only bridge from the two placement selectors to repository sessions.

The caller's review and any supplied approval digest are evidence only. This
module never grants preparation, execution, mutation, spending, or activation.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import capabilities as cap
from . import placement_selection as source_selection
from . import selection as inventory_selection
from .io import digest


def assess_selection(root: str | Path, entry: dict, *, policy: cap.DiscoveryPolicy,
                     approved_request_sha256: str | None = None) -> dict:
    """Recompute a bounded selection against current source and review inputs."""
    raw = cap._json(entry)
    if len(raw) > 16_000_000:
        raise cap.CapabilityError("repository_selection_byte_limit")
    entry = json.loads(raw)
    if type(entry) is not dict or entry.get("schema_version") != "1.0":
        raise cap.CapabilityError("invalid_repository_selection")
    cap._schema("repository-run-selection-v1", entry)
    if entry.get("kind") == "inventory-selection-v1":
        if set(entry) != {"schema_version", "kind", "inventory", "request"}:
            raise cap.CapabilityError("invalid_repository_selection")
        report = cap.discover_repository(root, policy)
        source = {row["file"]: row["sha256"] for row in report["files"]}
        inventory = entry["inventory"]
        for row in [*inventory["files"], *inventory["configuration_evidence"]]:
            if source.get(row.get("file")) != row.get("sha256"):
                raise cap.CapabilityError("stale_selection_source")
        result = inventory_selection.select_placement(
            inventory, entry["request"],
            approved_request_sha256=approved_request_sha256)
        return {"path": "inventory", "status": result["status"],
                "selection_sha256": digest(result), "selection": result,
                "inventory_sha256": digest(inventory),
                "request_sha256": result["request_sha256"],
                "selected_candidate_ids": result["selected_candidate_ids"],
                "implementation_spec_sha256": entry["request"]["implementation_spec_sha256"],
                "report_sha256": report["report_sha256"],
                "source_files": {row["file"]: row["sha256"] for row in report["files"]},
                "authority_authenticated": False}
    if entry.get("kind") == "source-selection-v1":
        expected = {"schema_version", "kind", "report", "prepared", "semantic_review",
                    "settings", "scope_review", "selection_review"}
        if set(entry) != expected:
            raise cap.CapabilityError("invalid_repository_selection")
        policy = cap.DiscoveryPolicy.from_json(entry["report"]["policy"])
        args = (root, entry["report"], entry["prepared"],
                entry["semantic_review"], entry["settings"])
        context = source_selection.prepare_placement_context(
            *args, scope_review=entry["scope_review"], policy=policy)
        review = entry["selection_review"]
        if review is None:
            result = None
            status = context["outcome"]
        else:
            result = source_selection.select_experimental_placements(
                root, entry["report"], entry["prepared"], entry["semantic_review"],
                review, entry["settings"], scope_review=entry["scope_review"], policy=policy)
            status = result["status"]
        reviewed = source_selection._fresh(root, entry["report"], entry["prepared"],
                                          entry["semantic_review"], entry["settings"], policy)
        return {"path": "source", "status": status,
                "selection_sha256": result["selection_sha256"] if result else None,
                "selection": result, "context": context,
                "inventory_sha256": digest(reviewed["inventory"]),
                "request_sha256": None,
                "selected_candidate_ids": result["selected_candidate_ids"] if result else [],
                "implementation_spec_sha256": None,
                "report_sha256": entry["report"]["report_sha256"],
                "authority_authenticated": False}
    raise cap.CapabilityError("unsupported_repository_selection")
