"""Read-only recipe lifecycle inventory: one explicit cell per recipe and stage.

Each row is derived from tests in this repository. A cell grants no
implementation, installation, runtime or provider authority, and no row
inherits another row's result.
"""
from __future__ import annotations

import copy
from importlib.resources import files
from pathlib import Path

from .contracts import validate_contract
from .io import InputError, read_json


RESOURCE = "recipe-lifecycle-matrix-v1.json"
QUALIFIED = "qualified_offline_synthetic"
# These stages need observed evidence that offline synthetic tests cannot supply.
NEVER_OFFLINE_QUALIFIED = ("canary_active", "provider_operation", "measured_benefit")


def _packaged(name: str) -> dict:
    return read_json(Path(str(files("jev_integration_evaluator").joinpath("data", name))))


def expected_row_ids() -> tuple[str, ...]:
    """Every catalogued Python recipe plus the separate JS/TS recipe C entry."""
    from .integrations.recipes import RECIPES
    manifest = _packaged("javascript-recipe-c.template.json")
    return (*RECIPES, manifest["template_id"] + "@" + manifest["template_version"])


def recipe_lifecycle_matrix() -> dict:
    matrix = _packaged(RESOURCE)
    validate_contract(matrix, "recipe-lifecycle-matrix-v1")
    if tuple(row["id"] for row in matrix["rows"]) != expected_row_ids():
        raise InputError("Recipe lifecycle matrix rows differ from the recipe catalogs")
    for row in matrix["rows"]:
        if (tuple(row["stages"]) != tuple(matrix["stages"])
                or tuple(row["platforms"]) != tuple(matrix["platforms"])):
            raise InputError("Recipe lifecycle matrix row omits or reorders a cell")
        qualified = {name for name, cell in row["stages"].items() if cell["status"] == QUALIFIED}
        if qualified & set(NEVER_OFFLINE_QUALIFIED):
            raise InputError("Recipe lifecycle matrix qualifies an observed-only stage")
        for cell in row["platforms"].values():
            if not set(cell["stages"]) <= qualified:
                raise InputError("Recipe lifecycle platform cell exceeds its row's qualified stages")
    return copy.deepcopy(matrix)


def recipe_lifecycle_row(row_id: str) -> dict:
    for row in recipe_lifecycle_matrix()["rows"]:
        if row["id"] == row_id:
            return row
    raise InputError("Unknown recipe lifecycle row")
