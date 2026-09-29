"""One finite offline console host over six distinct pinned fixture consumers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from jev_integration_evaluator.io import file_hash
from jev_integration_evaluator.use_case_templates import inspect_use_case_source, use_case_matrix


ROOT = Path(__file__).resolve().parents[1]
MODULES = {"C": "agent", "L": "graph", "D": "rag", "E": "completion",
           "M": "rag", "H": "retention"}


def prepare_use_case_host(destination: Path) -> Path:
    """Copy only current reviewed source bytes into a regular package host."""
    matrix = use_case_matrix()
    host_spec = matrix["host"]
    console_source = ROOT / host_spec["console"]
    project_source = ROOT / host_spec["project"]
    assert file_hash(console_source) == host_spec["console_sha256"]
    assert file_hash(project_source) == host_spec["project_sha256"]
    destination.mkdir(mode=0o700)
    package = destination / "use_case_fixture"
    package.mkdir(mode=0o700)
    (package / "__init__.py").write_text('"""Reviewed offline use-case host."""\n', encoding="utf-8")
    shutil.copyfile(console_source, package / "console.py")
    assert file_hash(package / "console.py") == host_spec["console_sha256"]
    for row in matrix["rows"]:
        case_id = row["id"]
        assert inspect_use_case_source(ROOT, case_id)["status"] == "source_matched"
        source = ROOT / row["source"]
        target = package / (MODULES[case_id] + ".py")
        if not target.exists():
            shutil.copyfile(source, target)
        assert file_hash(target) == row["source_sha256"]
    shutil.copyfile(project_source, destination / "pyproject.toml")
    assert file_hash(destination / "pyproject.toml") == host_spec["project_sha256"]
    return destination


def test_one_normal_console_preserves_six_raw_use_case_outcomes(tmp_path):
    host = prepare_use_case_host(tmp_path / "host")
    effects = tmp_path / "effects"
    effects.mkdir(mode=0o700)
    ready = tmp_path / "ready.bin"
    platform_env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR")
                    if name in os.environ}
    env = {**platform_env, "PYTHONPATH": str(host), "JEV_RUNTIME_MODE": "off",
           "USE_CASE_EFFECT_DIR": str(effects), "USE_CASE_READY_PATH": str(ready)}
    blocked = subprocess.run([sys.executable, "-m", "use_case_fixture.console"],
                             cwd=tmp_path, env={**env, "JEV_RUNTIME_MODE": "active"},
                             capture_output=True, text=True, timeout=15)
    assert blocked.returncode == 2 and not ready.exists() and not list(effects.iterdir())
    run = subprocess.run([sys.executable, "-m", "use_case_fixture.console"],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr
    assert ready.read_bytes() == b"ready\n"
    assert {path.stem for path in effects.iterdir()} == set(MODULES)
    rows = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in effects.iterdir()}
    assert rows["C"]["denied"] is False and rows["C"]["allowed"] is True
    assert rows["C"]["calls"] == [["read_file", {"path": "fixture"}]]
    assert rows["L"]["unapproved"] is None and rows["L"]["stale"] is None
    assert rows["L"]["revision"] == 5 and len(rows["L"]["merges"]) == 1
    assert rows["L"]["audits"] == rows["L"]["merges"]
    assert rows["L"]["receipt"]["sources"] == ["registry-left", "registry-right"]
    assert rows["D"] == {"empty_answer": None, "empty_status": "insufficient",
                         "selected_ids": ["support", "conflict"],
                         "conflict_source": "source-two", "generator_calls": 1}
    assert rows["E"]["success_report_only_verified"] is False
    assert rows["E"]["raw_final_verified"] is True
    assert rows["E"]["final"]["status"] == "closed"
    assert rows["M"] == {"fabricated_critical": "blocked", "valid_claim": "released",
                         "audit_records": 1, "released_ids": ["c1"]}
    assert rows["H"]["user_choice"] == "/prune"
    assert rows["H"]["prune"]["retained_ids"] == ["pin"]
    assert not any(rows["H"]["prune"][name] for name in
                   ("pin_loss", "byte_or_provenance_loss", "over_budget_commit", "wrong_mode_mutation"))
    assert rows["H"]["compact_unchanged"]["wrong_mode_mutation"] is False
    assert rows["H"]["compact_mutation_blocked"] is True
    assert rows["H"]["later_recall"]["success"] is True


def test_console_refuses_invalid_hold_and_existing_effects(tmp_path):
    host = prepare_use_case_host(tmp_path / "host")
    effects = tmp_path / "effects"
    effects.mkdir(mode=0o700)
    ready = tmp_path / "ready.bin"
    platform_env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR")
                    if name in os.environ}
    env = {**platform_env, "PYTHONPATH": str(host), "JEV_RUNTIME_MODE": "off",
           "USE_CASE_EFFECT_DIR": str(effects), "USE_CASE_READY_PATH": str(ready)}

    def run(extra):
        return subprocess.run([sys.executable, "-m", "use_case_fixture.console"],
                              cwd=tmp_path, env={**env, **extra},
                              capture_output=True, text=True, timeout=15)

    for hold in ("nonsense", "nan", "6"):
        assert run({"USE_CASE_HOLD_SECONDS": hold}).returncode == 2
        assert not list(effects.iterdir()) and not ready.exists()

    existing = effects / "C.json"
    existing.write_bytes(b"unrelated\n")
    assert run({}).returncode == 2
    assert existing.read_bytes() == b"unrelated\n" and not ready.exists()
    existing.unlink()

    ready.write_bytes(b"unrelated ready\n")
    assert run({}).returncode == 2
    assert ready.read_bytes() == b"unrelated ready\n" and not list(effects.iterdir())
