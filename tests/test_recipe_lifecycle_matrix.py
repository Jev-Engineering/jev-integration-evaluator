"""Every recipe row has explicit, evidence-bound lifecycle cells (issue 59)."""
from itertools import combinations
from pathlib import Path

import jsonschema
import pytest

from jev_integration_evaluator.integrations.recipes import RECIPES
from jev_integration_evaluator.io import InputError, read_json
from jev_integration_evaluator import recipe_lifecycle
from jev_integration_evaluator.recipe_lifecycle import (
    NEVER_OFFLINE_QUALIFIED, QUALIFIED, expected_row_ids, recipe_lifecycle_matrix,
    recipe_lifecycle_row,
)
from jev_integration_evaluator.use_case_templates import use_case_matrix


ROOT = Path(__file__).resolve().parents[1]
JS_ROW = "javascript.recipe-c@1.0.0"
STATUSES = {"implemented_unqualified", QUALIFIED, "unsupported", "pending", "not_applicable"}
REQUIRED_STAGES = ("source_transform", "template_materialize", "entrypoint_bind",
                   "package_install", "supervised_launch_off", "disable", "upgrade", "rollback",
                   "connected_shadow", "connected_upgrade", "canary_active",
                   "provider_operation", "measured_benefit")
# Stages that need a built and installed host, as opposed to a source fixture.
INSTALLED_STAGES = ("package_install", "supervised_launch_off", "disable", "upgrade",
                    "rollback", "connected_shadow", "connected_upgrade")
TRANSFORM_ONLY = ("python.B", "python.F", "python.G", "python.I", "python.J", "python.K")
# Recipe matrix stage -> use-case matrix fields that must already be qualified there.
USE_CASE_FIELDS = {
    "source_transform": ("apply", "verify"), "template_materialize": ("materialize",),
    "entrypoint_bind": ("bind",), "package_install": ("install",),
    "supervised_launch_off": ("launch",), "disable": ("disable",), "upgrade": ("upgrade",),
    "rollback": ("rollback",), "connected_shadow": ("connected_shadow",),
    "connected_upgrade": ("connected_upgrade",),
}


def _schema(directory):
    return read_json(ROOT / directory / "recipe-lifecycle-matrix-v1.schema.json")


def _cells(row):
    yield from row["stages"].items()
    yield from row["platforms"].items()


def test_matrix_is_schema_valid_and_schema_copies_are_identical():
    root = ROOT / "schemas" / "recipe-lifecycle-matrix-v1.schema.json"
    packaged = ROOT / "jev_integration_evaluator" / "data" / root.name
    assert root.read_bytes() == packaged.read_bytes()
    schema = _schema("schemas")
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(recipe_lifecycle_matrix())


def test_rows_are_exactly_thirteen_python_recipes_and_the_javascript_entry():
    ids = [row["id"] for row in recipe_lifecycle_matrix()["rows"]]
    assert ids == [*RECIPES, JS_ROW] == list(expected_row_ids())
    assert ids[:13] == ["python." + letter for letter in "ABCDEFGHIJKLM"]
    assert len(ids) == len(set(ids)) == 14
    manifest = read_json(ROOT / "jev_integration_evaluator/data/javascript-recipe-c.template.json")
    assert JS_ROW == manifest["template_id"] + "@" + manifest["template_version"]
    assert manifest["compatibility"]["supported_recipes"] == ["javascript.C"]
    for row in recipe_lifecycle_matrix()["rows"][:13]:
        assert row["language"] == "python"
        assert row["recipe"] == row["id"] + "@" + RECIPES[row["id"]].version
        assert row["title"] == RECIPES[row["id"]].title
    assert recipe_lifecycle_row(JS_ROW)["language"] == "javascript_typescript"


def test_every_row_has_every_stage_and_platform_cell():
    matrix = recipe_lifecycle_matrix()
    assert tuple(matrix["stages"]) == REQUIRED_STAGES
    assert matrix["platforms"] == ["linux", "windows_native", "node"]
    for row in matrix["rows"]:
        assert tuple(row["stages"]) == REQUIRED_STAGES
        assert list(row["platforms"]) == matrix["platforms"]
        for _, cell in _cells(row):
            assert cell["status"] in STATUSES
            assert isinstance(cell["evidence"], list)


def test_qualified_cells_cite_existing_test_modules_and_unclaimed_cells_cite_none():
    for row in recipe_lifecycle_matrix()["rows"]:
        for name, cell in _cells(row):
            if cell["status"] == QUALIFIED:
                assert cell["evidence"], (row["id"], name)
            if cell["status"] in ("pending", "unsupported", "not_applicable"):
                assert cell["evidence"] == [], (row["id"], name)
            for path in cell["evidence"]:
                assert path.startswith("tests/test_") and path.endswith(".py")
                assert (ROOT / path).is_file(), (row["id"], name, path)


def test_provider_canary_active_and_benefit_are_never_qualified():
    for row in recipe_lifecycle_matrix()["rows"]:
        for name in NEVER_OFFLINE_QUALIFIED:
            assert row["stages"][name] == {"status": "pending", "evidence": []}, (row["id"], name)
        for cell in row["platforms"].values():
            assert not set(cell["stages"]) & set(NEVER_OFFLINE_QUALIFIED)


def test_platform_cells_never_exceed_the_rows_own_qualified_stages():
    for row in recipe_lifecycle_matrix()["rows"]:
        qualified = {name for name, cell in row["stages"].items() if cell["status"] == QUALIFIED}
        cited = {path for cell in row["stages"].values() for path in cell["evidence"]}
        for name, cell in row["platforms"].items():
            assert (cell["status"] == QUALIFIED) == bool(cell["stages"]), (row["id"], name)
            assert set(cell["stages"]) <= qualified, (row["id"], name)
        assert set(row["platforms"]["linux"]["evidence"]) <= cited
        if row["language"] == "python":
            assert row["platforms"]["node"]["status"] == "not_applicable"
        else:
            assert row["platforms"]["windows_native"]["status"] == "unsupported"


def test_no_row_inherits_installed_evidence_from_another_row():
    rows = recipe_lifecycle_matrix()["rows"]
    installed = {row["id"]: {path for stage in INSTALLED_STAGES
                             for path in row["stages"][stage]["evidence"]} for row in rows}
    for left, right in combinations(installed, 2):
        assert not installed[left] & installed[right], (left, right)
    # Native Windows modules are only cited by the one row whose fixture they run.
    windows = [row["id"] for row in rows if row["platforms"]["windows_native"]["evidence"]]
    assert windows == ["python.C"]
    assert recipe_lifecycle_row("python.C")["platforms"]["windows_native"]["status"] == QUALIFIED
    assert all(row["platforms"]["windows_native"]["status"] in ("pending", "unsupported")
               for row in rows if row["id"] != "python.C")


def test_one_passing_c_host_does_not_qualify_other_recipes():
    for row_id in TRANSFORM_ONLY:
        row = recipe_lifecycle_row(row_id)
        assert row["stages"]["source_transform"]["status"] == QUALIFIED
        assert {cell["status"] for name, cell in row["stages"].items()
                if name != "source_transform"} == {"pending"}, row_id
    archived = recipe_lifecycle_row("python.A")
    assert {name for name, cell in archived["stages"].items() if cell["status"] == QUALIFIED} == {
        "source_transform", "template_materialize"}
    for row in recipe_lifecycle_matrix()["rows"]:
        assert any(cell["status"] != QUALIFIED for cell in row["stages"].values())
        assert any(cell["status"] != QUALIFIED for cell in row["platforms"].values())


def test_recipe_rows_do_not_claim_more_than_the_use_case_matrix():
    use_cases = {"python." + row["id"]: row for row in use_case_matrix()["rows"]}
    for row_id in ("python.L", "python.D", "python.E", "python.M", "python.H"):
        row, use_case = recipe_lifecycle_row(row_id), use_cases[row_id]
        for stage, fields in USE_CASE_FIELDS.items():
            if row["stages"][stage]["status"] == QUALIFIED:
                for field in fields:
                    assert use_case[field].startswith("qualified_offline_"), (row_id, stage, field)
        assert use_case["provider"] == "pending" and use_case["benefit"] == "unknown"


def test_reference_names_every_row_and_status():
    text = (ROOT / "references" / "recipe-lifecycle-matrix-v1.md").read_text(encoding="utf-8")
    for row in recipe_lifecycle_matrix()["rows"]:
        assert "`" + row["id"] + "`" in text
    for status in STATUSES:
        assert "`" + status + "`" in text


@pytest.mark.parametrize("mutation", ["overclaim", "missing_row", "platform_excess"])
def test_loader_rejects_overclaims_and_missing_rows(monkeypatch, mutation):
    matrix = recipe_lifecycle_matrix()
    if mutation == "overclaim":
        matrix["rows"][1]["stages"]["provider_operation"] = {
            "status": QUALIFIED, "evidence": ["tests/test_executable_recipes.py"]}
    elif mutation == "missing_row":
        del matrix["rows"][5]
    else:
        matrix["rows"][1]["platforms"]["linux"]["stages"].append("package_install")
    monkeypatch.setattr(recipe_lifecycle, "read_json", lambda path: (
        matrix if Path(path).name == recipe_lifecycle.RESOURCE else read_json(path)))
    with pytest.raises(InputError):
        recipe_lifecycle_matrix()


def test_schema_rejects_omitted_cells_and_qualification_without_evidence():
    validator = jsonschema.Draft202012Validator(_schema("jev_integration_evaluator/data"))
    omitted = recipe_lifecycle_matrix()
    del omitted["rows"][0]["stages"]["disable"]
    assert not validator.is_valid(omitted)
    unevidenced = recipe_lifecycle_matrix()
    unevidenced["rows"][2]["stages"]["package_install"]["evidence"] = []
    assert not validator.is_valid(unevidenced)
    inherited = recipe_lifecycle_matrix()
    inherited["rows"][1]["id"] = "python.C"
    assert not validator.is_valid(inherited)
