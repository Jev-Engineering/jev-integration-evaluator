"""Read-only, source-bound inventory of illustrative use-case contracts.

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


def use_case_matrix() -> dict:
    matrix = read_json(Path(str(files("jev_integration_evaluator").joinpath("data", RESOURCE))))
    validate_contract(matrix, "use-case-template-matrix-v1")
    if matrix["schema_version"] != "1.0" or tuple(row["id"] for row in matrix["rows"]) != (
        "C", "L", "D", "E", "M", "H"
    ):
        raise InputError("Unsupported use-case matrix version or rows")
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
    return {"schema_version": "1.0", "id": case_id, "status": "source_matched",
            "source_sha256": observed, "target_imported": False, "target_executed": False,
            "installed_verified": False}
