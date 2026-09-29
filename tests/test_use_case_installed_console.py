"""Offline installed invocation of the reviewed six-consumer fixture host.

This is a package/normal-command test, not a generated use-case transform or
an external provider observation. The records are written by the host itself.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import venv
import zipfile

import pytest

from jev_integration_evaluator.io import file_hash
from jev_integration_evaluator.use_case_templates import use_case_matrix
from tests.test_use_case_console_host import prepare_use_case_host


pytestmark = pytest.mark.skipif(
    not (sys.platform == "linux" and platform.machine().lower() == "x86_64"
         and sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 13)),
    reason="Offline installed fixture profile is Linux x86-64 CPython 3.13")


def _run(argv: list[str], cwd: Path, env: dict[str, str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                            text=True, timeout=timeout)
    assert result.returncode == 0, result.stderr
    return result


def test_installed_normal_console_preserves_distinct_offline_consumer_records(tmp_path: Path):
    wheelhouse_name = os.environ.get("JEV_TEMPLATE_WHEELHOUSE")
    if not wheelhouse_name:
        pytest.skip("Explicitly prepared offline wheelhouse required")
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    assert wheelhouse.is_dir()

    source = prepare_use_case_host(tmp_path / "source")
    matrix = use_case_matrix()
    pinned = {row["id"]: row["source_sha256"] for row in matrix["rows"]}
    assert {"C", "L", "D", "E", "M", "H"} == set(pinned)
    assert file_hash(source / "use_case_fixture/console.py") == matrix["host"]["console_sha256"]
    assert file_hash(source / "use_case_fixture/graph.py") == pinned["L"]
    assert file_hash(source / "use_case_fixture/rag.py") == pinned["D"] == pinned["M"]
    assert file_hash(source / "use_case_fixture/completion.py") == pinned["E"]
    assert file_hash(source / "use_case_fixture/retention.py") == pinned["H"]

    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin/python"
    script = environment / "bin/use-case-offline"
    clean = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "LANG": "C.UTF-8"}
    tools = [list(wheelhouse.glob(f"{name}-*.whl")) for name in ("setuptools", "wheel")]
    assert all(len(rows) == 1 for rows in tools)
    _run([str(python), "-m", "pip", "install", "--no-index", "--no-deps",
          *(str(rows[0]) for rows in tools)], tmp_path, clean)
    dist = tmp_path / "dist"
    dist.mkdir()
    _run([str(python), "-m", "pip", "wheel", "--no-index", "--no-deps",
          "--no-build-isolation", "--wheel-dir", str(dist), str(source)],
         tmp_path, clean)
    wheels = list(dist.glob("jev_use_case_offline_fixture-1.0.0-*.whl"))
    assert len(wheels) == 1
    wheel_sha256 = file_hash(wheels[0])
    with zipfile.ZipFile(wheels[0]) as archive:
        for name, expected in (
            ("console", matrix["host"]["console_sha256"]),
            ("graph", pinned["L"]), ("rag", pinned["D"]),
            ("completion", pinned["E"]), ("retention", pinned["H"]),
        ):
            assert hashlib.sha256(archive.read(f"use_case_fixture/{name}.py")).hexdigest() == expected
    _run([str(python), "-m", "pip", "install", "--no-index", "--no-deps",
          str(wheels[0])], tmp_path, clean)
    assert script.is_file() and wheel_sha256 == hashlib.sha256(wheels[0].read_bytes()).hexdigest()

    effects = tmp_path / "effects"
    effects.mkdir(mode=0o700)
    ready = tmp_path / "ready.bin"
    launch = {**clean, "JEV_RUNTIME_MODE": "off", "USE_CASE_EFFECT_DIR": str(effects),
              "USE_CASE_READY_PATH": str(ready)}
    blocked = subprocess.run([str(script)], cwd=tmp_path,
                             env={**launch, "JEV_RUNTIME_MODE": "active"},
                             capture_output=True, text=True, timeout=20)
    assert blocked.returncode == 2 and not ready.exists() and not list(effects.iterdir())
    _run([str(script)], tmp_path, launch, timeout=20)
    assert ready.read_bytes() == b"ready\n"
    assert {path.name for path in effects.iterdir()} == {f"{case}.json" for case in pinned}
    records = {case: json.loads((effects / f"{case}.json").read_text(encoding="utf-8"))
               for case in pinned}

    graph = records["L"]
    assert graph["unapproved"] is None and graph["stale"] is None
    assert graph["revision"] == 5 and len(graph["merges"]) == 1
    assert graph["receipt"] == graph["merges"][0] == graph["audits"][0]
    assert graph["receipt"]["sources"] == ["registry-left", "registry-right"]
    retrieval = records["D"]
    assert retrieval["empty_status"] == "insufficient" and retrieval["empty_answer"] is None
    assert retrieval["selected_ids"] == ["support", "conflict"]
    assert retrieval["conflict_source"] == "source-two" and retrieval["generator_calls"] == 1
    completion = records["E"]
    assert completion["success_report_only_verified"] is False
    assert completion["raw_final_verified"] is True
    assert completion["final"]["status"] == "closed"
    claim = records["M"]
    assert claim["fabricated_critical"] == "blocked"
    assert claim["valid_claim"] == "released" and claim["audit_records"] == 1
    assert claim["released_ids"] == ["c1"]
    retention = records["H"]
    assert retention["user_choice"] == "/prune"
    assert retention["retained_items"] == retention["raw_items"][:1]
    assert retention["prune"]["retained_ids"] == ["pin"]
    assert retention["compact_unchanged"]["wrong_mode_mutation"] is False
    assert retention["compact_mutation_blocked"] is True
    assert retention["later_recall"]["success"] is True

    _run([str(python), "-m", "pip", "uninstall", "-y",
          "jev-use-case-offline-fixture"], tmp_path, clean)
    assert not script.exists()
