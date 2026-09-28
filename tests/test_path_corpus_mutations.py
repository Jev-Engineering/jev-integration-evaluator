"""Independent policy/effect mutation checks on the package host."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


HOST = Path(__file__).parent / "path_corpus" / "package_host"


def observe(root: Path, item: str, action: str, permit: str) -> dict:
    done = subprocess.run([sys.executable, "-B", "-S", str(root / "runner.py"),
                           item, action, permit], cwd=root, capture_output=True,
                          text=True, timeout=5, check=True)
    assert done.stderr == ""
    return json.loads(done.stdout)


@pytest.mark.parametrize(("name", "before", "after", "inputs", "expected"), [
    ("permission_removed", "if not approved(request, action):", "if False:",
     ("alpha", "read", "no"), {"result": "denied", "events": []}),
    ("unregistered_action", 'frozenset({"read", "summarize"})',
     'frozenset({"read", "summarize", "delete"})',
     ("beta", "delete", "yes"), {"result": "denied", "events": []}),
    ("effect_duplicated", "events = [(action, item)]", "events = [(action, item), (action, item)]",
     ("gamma", "read", "yes"), {"result": "done:read:gamma", "events": [["read", "gamma"]]}),
    ("result_forged", 'f"done:{action}:{item}"', '"done:read:wrong"',
     ("delta", "summarize", "yes"),
     {"result": "done:summarize:delta", "events": [["summarize", "delta"]]}),
])
def test_independent_package_oracle_rejects_mutation(tmp_path, name, before, after, inputs, expected):
    target = tmp_path / name
    shutil.copytree(HOST, target)
    path = target / "app" / "pipeline.py"
    source = path.read_text(encoding="utf-8")
    assert source.count(before) == 1
    path.write_text(source.replace(before, after), encoding="utf-8")
    assert observe(target, *inputs) != expected
