"""Independent behavioral oracle for project-owned path-input hosts."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest


HOST = Path(__file__).parent / "path_corpus" / "opaque_host"


def test_opaque_host_source_binding():
    expected = json.loads((HOST / "expected.json").read_text(encoding="utf-8"))
    assert expected["evidence_kind"] == "synthetic_independent_oracle"
    assert {
        name: hashlib.sha256((HOST / name).read_bytes()).hexdigest()
        for name in expected["source_sha256"]
    } == expected["source_sha256"]


@pytest.mark.parametrize(
    ("item", "action", "expected"),
    [
        ("alpha", "read", {"observation": {"result": "done:read:alpha", "event_count": 1}, "events": [["read", "alpha"]]}),
        ("beta", "summarize", {"observation": {"result": "done:summarize:beta", "event_count": 1}, "events": [["summarize", "beta"]]}),
        ("gamma", "delete", {"observation": {"result": "denied", "event_count": 0}, "events": []}),
    ],
)
def test_opaque_host_baseline(item, action, expected):
    completed = subprocess.run(
        [sys.executable, "-B", "-S", str(HOST / "main.py"), item, action],
        cwd=HOST, capture_output=True, text=True, timeout=5, check=True,
    )
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == expected
