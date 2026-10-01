"""Read-only, source-bound inventory with partial offline L, D, E, M and H qualifications.

These records describe offline host fixtures. They grant no implementation,
installation, runtime, or provider authority.
"""
from __future__ import annotations

import copy
from importlib.resources import files
from pathlib import Path

from .contracts import validate_contract
from .io import InputError, file_hash, read_json


RESOURCE = "use-case-template-matrix-v1.json"
# Every lifecycle cell a row states explicitly. A cell is evidence-bound: a
# qualified cell names the test modules that exercise it and any other cell
# names none.
EVIDENCE_CELLS = ("materialize", "bind", "apply", "install", "configure", "normal_start",
                  "launch", "verify", "status", "disable", "upgrade", "rollback",
                  "connected_shadow", "connected_upgrade", "provider", "benefit")
# These need observed evidence that an offline synthetic test cannot supply.
NEVER_OFFLINE_QUALIFIED = ("connected_upgrade", "provider", "benefit")


def _qualified(row: dict, cell: str) -> bool:
    return str(row.get(cell, "pending")).startswith("qualified_offline_")


def use_case_matrix() -> dict:
    matrix = read_json(Path(str(files("jev_integration_evaluator").joinpath("data", RESOURCE))))
    validate_contract(matrix, "use-case-template-matrix-v1")
    if matrix["schema_version"] != "1.0" or tuple(row["id"] for row in matrix["rows"]) != (
        "C", "L", "D", "E", "M", "H"
    ):
        raise InputError("Unsupported use-case matrix version or rows")
    for row in matrix["rows"]:
        if tuple(row["evidence"]) != EVIDENCE_CELLS:
            raise InputError("Use-case matrix row omits or reorders an evidence cell")
        if any(_qualified(row, cell) != bool(row["evidence"][cell]) for cell in EVIDENCE_CELLS):
            raise InputError("Use-case matrix cell and its evidence disagree")
        if any(_qualified(row, cell) for cell in NEVER_OFFLINE_QUALIFIED):
            raise InputError("Use-case matrix qualifies an observed-only cell")
        pinned = {row["source"], row.get("consumer_adapter")}
        if any(interface["file"] not in pinned for interface in row["host_interfaces"]):
            raise InputError("Use-case host interface is outside the pinned source contract")
    return copy.deepcopy(matrix)


def inspect_use_case_source(source_root: str | Path, case_id: str) -> dict:
    """Check exact reviewed fixture bytes without importing or executing them."""
    rows = {row["id"]: row for row in use_case_matrix()["rows"]}
    if case_id not in rows:
        raise InputError("Unknown use-case ID")
    row = rows[case_id]
    root = Path(source_root).resolve(strict=True)
    source = root.joinpath(*row["source"].split("/"))
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):
        raise InputError("Use-case source is missing or outside source root")
    observed = file_hash(source)
    if observed != row["source_sha256"]:
        raise InputError("Use-case source changed; review and refresh contract")
    adapter_sha256 = None
    if case_id in ("L", "D", "E", "M", "H"):
        adapter = root.joinpath(*row["consumer_adapter"].split("/"))
        if (adapter.is_symlink() or not adapter.is_file()
                or not adapter.resolve().is_relative_to(root)):
            raise InputError("Use-case consumer adapter is missing or outside source root")
        adapter_sha256 = file_hash(adapter)
        if adapter_sha256 != row["consumer_adapter_sha256"]:
            raise InputError("Use-case consumer adapter changed; review and refresh contract")
    corpus_sha256 = None
    if case_id == "D":
        corpus = root.joinpath(*row["consumer_corpus"].split("/"))
        if (corpus.is_symlink() or not corpus.is_file()
                or not corpus.resolve().is_relative_to(root)):
            raise InputError("Retrieval corpus is missing or outside source root")
        corpus_sha256 = file_hash(corpus)
        if corpus_sha256 != row["consumer_corpus_sha256"]:
            raise InputError("Retrieval corpus changed; review and refresh contract")
    return {"schema_version": "1.0", "id": case_id, "status": "source_matched",
            "source_sha256": observed, "target_imported": False, "target_executed": False,
            "installed_verified": False, "consumer_adapter_sha256": adapter_sha256,
            "consumer_corpus_sha256": corpus_sha256}
