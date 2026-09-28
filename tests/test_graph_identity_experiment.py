"""Host-gate and frozen-study checks for the offline graph fixture."""

import importlib.util
import sys
from asyncio import CancelledError
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "examples" / "graph-system"
sys.path.insert(0, str(ROOT))
from entities import Entity, InMemoryGraph, reconcile  # noqa: E402


def load_runner():
    spec = importlib.util.spec_from_file_location("graph_identity_study", ROOT / "run_experiment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pair():
    return (Entity("a", "Cedar", "CA", "CA-1", "source-a"),
            Entity("b", "Cedar", "CA", "CA-1", "source-b"))


class Answer:
    def __init__(self, value):
        self.value = value

    def classify(self, left, right):
        return self.value


@pytest.mark.parametrize("answer,approval,revision", [
    ("same", False, 0), ("related", True, 0), ("different", True, 0),
    ("uncertain", True, 0), (None, True, 0), ("same", True, 1),
])
def test_host_gates_prevent_merge(answer, approval, revision):
    left, right = pair()
    graph = InMemoryGraph(left, right)
    assert reconcile(Answer(answer), graph, left, right, approval, revision) is None
    assert graph.revision == 0
    assert graph.merges == []


def test_revision_changed_during_assessment_cannot_merge():
    left, right = pair()
    graph = InMemoryGraph(left, right)

    class RacingClassifier:
        def classify(self, _left, _right):
            graph.revision += 1
            return "same"

    assert reconcile(RacingClassifier(), graph, left, right, True, 0) is None
    assert graph.merges == []


@pytest.mark.parametrize("failure", [TimeoutError, ConnectionError, CancelledError])
def test_classifier_failure_abstains_without_mutation(failure):
    left, right = pair()
    graph = InMemoryGraph(left, right)

    class FailingClassifier:
        def classify(self, _left, _right):
            raise failure("injected")

    assert reconcile(FailingClassifier(), graph, left, right, True, 0) is None
    assert graph.revision == 0
    assert graph.merges == []


def test_unhashable_malformed_assessment_abstains_and_is_counted():
    runner = load_runner()
    cases, labels, _assessments, _study = runner.load_frozen()
    case = next(case for case in cases if case["id"] == "h01")
    result = runner.run_case(case, labels["h01"], {"jev": []}, "jev")
    assert result["assessment"] == "uncertain"
    assert result["injected_failure"] == "malformed"
    assert result["missed_eligible_true_merge"] is True
    assert result["merged"] is False
    assert runner.summarize([result])["injected_failures"] == 1


def test_audit_failure_occurs_before_mutation():
    left, right = pair()
    graph = InMemoryGraph(left, right)
    seen = []

    def failing_audit(receipt):
        seen.append(receipt.copy())
        raise OSError("audit unavailable")

    assert reconcile(Answer("same"), graph, left, right, True, 0,
                     audit=failing_audit) is None
    assert len(seen) == 1
    assert graph.revision == 0
    assert graph.merges == []


def test_merge_receipt_preserves_sources_and_revision():
    left, right = pair()
    graph = InMemoryGraph(left, right)
    receipt = reconcile(Answer("same"), graph, left, right, True, 0)
    assert receipt == {"left_key": "a", "right_key": "b",
                       "sources": ["source-a", "source-b"],
                       "revision_before": 0, "revision_after": 1}
    assert reconcile(Answer("same"), graph, left, right, True, 0) is None
    assert graph.merges == [receipt]


def test_frozen_paired_study_counts_failures_and_rejects():
    report = load_runner().evaluate()
    assert len(report["paired_holdout"]) == 16
    assert all(value["scheduled"] == value["observed"] == 16
               for value in report["summary"].values())
    assert report["summary"]["current"]["wrong_merges"] == 3
    assert report["summary"]["deterministic"]["wrong_merges"] == 0
    assert report["summary"]["jev"]["wrong_merges"] == 1
    assert report["summary"]["jev"]["injected_failures"] == 2
    assert report["decision"] == "reject"
    by_id = {row["case_id"]: row for row in report["paired_holdout"]}
    assert not any(by_id[case]["arms"][arm]["merged"]
                   for case in ("h11", "h12", "h13")
                   for arm in ("current", "deterministic", "jev"))
    assert all(by_id[case]["arms"]["jev"]["assessment"] == "uncertain"
               for case in ("h14", "h15"))


def test_changed_frozen_input_is_rejected(tmp_path, monkeypatch):
    runner = load_runner()
    (tmp_path / "cases.v1.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="frozen input changed"):
        runner.load_frozen()
