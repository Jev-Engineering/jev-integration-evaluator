"""Independent behavioral oracle for project-owned path-input hosts."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


HOST = Path(__file__).parent / "path_corpus" / "opaque_host"
CORPUS = HOST.parent


def test_opaque_host_source_binding():
    expected = json.loads((HOST / "expected.json").read_text(encoding="utf-8"))
    assert expected["evidence_kind"] == "synthetic_independent_oracle"
    assert {
        name: hashlib.sha256((HOST / name).read_bytes()).hexdigest()
        for name in expected["source_sha256"]
    } == expected["source_sha256"]


@pytest.mark.parametrize("host_name", ["opaque_host", "package_host", "supported_host", "missing_callbacks",
                                       "deterministic_only", "unsupported_language"])
def test_project_owned_corpus_source_binding(host_name):
    host = CORPUS / host_name
    expected = json.loads((host / "expected.json").read_text(encoding="utf-8"))
    assert expected["evidence_kind"] == "synthetic_independent_oracle"
    assert {name: hashlib.sha256((host / name).read_bytes()).hexdigest()
            for name in expected["source_sha256"]} == expected["source_sha256"]


@pytest.mark.parametrize(("item", "action", "permit", "expected"), [
    ("alpha", "read", "yes", {"result": "done:read:alpha", "events": [["read", "alpha"]]}),
    ("beta", "summarize", "yes", {"result": "done:summarize:beta", "events": [["summarize", "beta"]]}),
    ("gamma", "delete", "yes", {"result": "denied", "events": []}),
    ("delta", "read", "no", {"result": "denied", "events": []}),
])
def test_package_host_independent_baseline(item, action, permit, expected):
    host = CORPUS / "package_host"
    done = subprocess.run([sys.executable, "-B", "-S", str(host / "runner.py"),
                           item, action, permit], cwd=host, capture_output=True,
                          text=True, timeout=5, check=True)
    assert done.stderr == ""
    assert json.loads(done.stdout) == expected


@pytest.mark.parametrize(
    ("item", "action", "expected"),
    [
        ("alpha", "read", {"observation": {"result": "done:read:alpha", "event_count": 1}, "events": [["read", "alpha"]]}),
        ("beta", "summarize", {"observation": {"result": "done:summarize:beta", "event_count": 1}, "events": [["summarize", "beta"]]}),
        ("gamma", "delete", {"observation": {"result": "denied", "event_count": 0}, "events": []}),
    ],
)
def test_opaque_host_baseline(item, action, expected):
    completed = _run_host(HOST, item, action)
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == expected


def _run_host(root, item, action):
    return subprocess.run(
        [sys.executable, "-B", "-S", str(root / "main.py"), item, action],
        cwd=root, capture_output=True, text=True, timeout=5, check=True,
        env={"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", **{
            key: value for key, value in os.environ.items()
            if key in ("SYSTEMROOT", "WINDIR", "PATH", "HOME", "LANG", "LC_ALL")}},
    )


@pytest.mark.parametrize(
    ("mutation", "before", "after", "item", "action", "expected"),
    [
        ("validation_removed", 'if action not in ALLOWED:', 'if False:', "gamma", "delete",
         {"observation": {"result": "denied", "event_count": 0}, "events": []}),
        ("effect_duplicated", 'return store.perform(action, value)',
         'store.perform(action, value)\n    return store.perform(action, value)', "alpha", "read",
         {"observation": {"result": "done:read:alpha", "event_count": 1}, "events": [["read", "alpha"]]}),
        ("result_forged", 'return f"done:{action}:{item}"', 'return "done:read:alpha"',
         "beta", "summarize", {"observation": {"result": "done:summarize:beta", "event_count": 1},
                                 "events": [["summarize", "beta"]]}),
        ("postcondition_forged", '"event_count": len(store.events)', '"event_count": 0',
         "alpha", "read", {"observation": {"result": "done:read:alpha", "event_count": 1},
                              "events": [["read", "alpha"]]}),
    ],
)
def test_independent_oracle_rejects_adversarial_host_mutations(
    tmp_path, mutation, before, after, item, action, expected
):
    target = tmp_path / mutation
    shutil.copytree(HOST, target)
    file = target / "service.py"
    source = file.read_text(encoding="utf-8")
    assert source.count(before) == 1
    file.write_text(source.replace(before, after), encoding="utf-8")
    actual = json.loads(_run_host(target, item, action).stdout)
    assert actual != expected, mutation


@pytest.mark.skipif(os.name != "posix", reason="repository discovery requires a POSIX filesystem")
def test_public_repository_run_path_input_reports_current_support():
    completed = subprocess.run(
        [sys.executable, "-m", "jev_integration_evaluator", "repository-run", str(HOST)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        timeout=30, check=True,
    )
    report = json.loads(completed.stdout)
    expected = json.loads((HOST / "expected.json").read_text(encoding="utf-8"))
    assert report["kind"] == "repository-run-inspection-v1"
    assert report["status"] == "insufficient_evidence"
    assert report["report"]["discovery_outcome"] == "unsupported_or_unresolved"
    assert report["target_executed"] is False
    assert report["target_modified"] is False
    assert {row["file"]: row["sha256"] for row in report["report"]["files"]} == expected["source_sha256"]


@pytest.mark.skipif(os.name != "posix", reason="repository discovery requires a POSIX filesystem")
@pytest.mark.parametrize(("host_name", "status", "discovery_outcome"), [
    ("package_host", "insufficient_evidence", "unsupported_or_unresolved"),
    ("missing_callbacks", "deterministic_rejection", "deterministic_rejection"),
    ("deterministic_only", "insufficient_evidence", "unsupported_or_unresolved"),
    ("unsupported_language", "incomplete_analysis", "incomplete_analysis"),
])
def test_public_path_truthfully_reports_unqualified_corpus_cases(host_name, status, discovery_outcome):
    host = CORPUS / host_name
    done = subprocess.run([sys.executable, "-m", "jev_integration_evaluator",
                           "repository-run", str(host)], cwd=CORPUS.parents[1],
                          capture_output=True, text=True, timeout=30, check=True)
    assert done.stderr == ""
    report = json.loads(done.stdout)
    assert report["status"] == status
    assert report["report"]["discovery_outcome"] == discovery_outcome
    assert report["target_executed"] is False
    assert report["target_modified"] is False


@pytest.mark.skipif(os.name != "posix", reason="repository discovery requires a POSIX filesystem")
def test_public_path_reports_truncated_source_coverage(tmp_path):
    host = tmp_path / "incomplete"
    host.mkdir()
    (host / "huge.py").write_bytes(b"# synthetic oversized source\n" + b" " * 1_048_577)
    done = subprocess.run([sys.executable, "-m", "jev_integration_evaluator",
                           "repository-run", str(host)], cwd=CORPUS.parents[1],
                          capture_output=True, text=True, timeout=30, check=True)
    assert done.stderr == ""
    report = json.loads(done.stdout)
    assert report["status"] == "incomplete_analysis"
    assert report["report"]["coverage"]["complete_within_policy"] is False
    assert report["target_executed"] is False and report["target_modified"] is False


@pytest.mark.skipif(os.name != "posix", reason="repository discovery requires a POSIX filesystem")
def test_deterministic_host_complete_negative_review_is_scoped():
    from jev_integration_evaluator import capabilities as cap
    from jev_integration_evaluator.config import DEFAULT
    from jev_integration_evaluator.nomination_inventory import discover_repository_capabilities
    from jev_integration_evaluator.repository_conclusion import (
        REVIEW_CONTRACT, conclude_repository, coverage_review_schedule,
    )

    host = CORPUS / "deterministic_only"
    report = discover_repository_capabilities(host, DEFAULT)
    schedule = coverage_review_schedule(report, DEFAULT)
    opinions = {letter: {"disposition": "not_useful",
                         "reason": "Exact integer arithmetic is sufficient for this synthetic host."}
                for letter in "ABCDEFGHIJKLM"}
    review = {
        "schema_version": "1.0", "contract": REVIEW_CONTRACT,
        **{key: schedule[key] for key in (
            "report_sha256", "conclusion_engine_sha256", "settings_sha256", "objective_sha256")},
        "reviewer": "independent-corpus-reviewer",
        "files": [{**row, "patterns": opinions} for row in schedule["files"]],
        "seams": [{**row, "patterns": opinions} for row in schedule["seams"]],
    }
    outcome = conclude_repository(host, report, DEFAULT, review=review,
                                  expected_review_sha256=cap._digest(review))
    assert outcome["outcome"] == "no_useful_placement"
    assert outcome["coverage"]["complete_anchored_review"] is True
    assert outcome["scope"]["global_absence_proven"] is False
    assert not any(outcome["authorization"].values())
