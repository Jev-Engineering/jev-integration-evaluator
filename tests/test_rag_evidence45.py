"""Host contract checks for the synthetic RAG evidence fixture."""

import importlib.util
from pathlib import Path
import sys

import pytest


PATH = Path(__file__).resolve().parents[1] / "examples" / "rag-system" / "pipeline.py"
SPEC = importlib.util.spec_from_file_location("rag_pipeline45_test", PATH)
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


class Retrieval:
    def __init__(self, passages):
        self.passages = passages

    def retrieve(self, query):
        return self.passages


class Generator:
    def __init__(self):
        self.calls = 0
        self.received = None

    def generate(self, query, evidence):
        self.calls += 1
        self.received = evidence
        return "generated"


def passage(id, claim="requested", stance="supports"):
    return pipeline.Passage(id, "source", "1:2", "text", claim, stance)


def test_legacy_baseline_forwards_all_chunks():
    generator = Generator()
    chunks = ["old chunk"]
    assert pipeline.answer_request(Retrieval(chunks), generator, "query") == "generated"
    assert generator.received is chunks


def test_assessed_selection_reaches_generator_with_provenance_and_conflict():
    support, conflict, noise = passage("p1"), passage("p2", stance="contradicts"), passage("p3", claim="other")

    class Assessor:
        def assess(self, query, passages):
            return {"p1": "relevant", "p2": "irrelevant", "p3": "irrelevant"}

    generator = Generator()
    result = pipeline.answer_with_evidence(Retrieval([support, conflict, noise]), generator, "query",
                                           policy="jev", assessor=Assessor())
    assert result.answer == "generated"
    assert [p.passage_id for p in generator.received.passages] == ["p1", "p2"]
    assert generator.received.citation("p2") is conflict
    assert generator.received.citation("p2").source_id == "source"
    with pytest.raises(ValueError):
        generator.received.citation("p3")


@pytest.mark.parametrize("bad", [None, {"p1": "relevant"}, {"p1": "approve", "p2": "irrelevant"}])
def test_malformed_assessment_fails_closed_without_generation(bad):
    class Assessor:
        def assess(self, query, passages):
            return bad

    generator = Generator()
    result = pipeline.answer_with_evidence(Retrieval([passage("p1"), passage("p2")]), generator,
                                           "query", policy="jev", assessor=Assessor())
    assert result.evidence.status == "assessment_failed"
    assert result.answer is None
    assert generator.calls == 0


def test_timeout_and_empty_selection_do_not_generate():
    class Timeout:
        def assess(self, query, passages):
            raise TimeoutError()

    generator = Generator()
    assert pipeline.answer_with_evidence(Retrieval([passage("p1")]), generator, "query", policy="jev",
                                         assessor=Timeout()).evidence.status == "assessment_failed"
    assert pipeline.answer_with_evidence(Retrieval([]), generator, "query", policy="lexical").evidence.status == "insufficient"
    assert generator.calls == 0


def test_duplicate_id_and_invalid_provenance_rejected_before_assessment():
    with pytest.raises(ValueError):
        pipeline.select_evidence("query", [passage("p1"), passage("p1")], "current")
    with pytest.raises(ValueError):
        pipeline.select_evidence("query", [pipeline.Passage("p1", "", "1:2", "text", "c", "supports")], "current")


def test_study_does_not_count_failed_assessment_as_correct_abstention():
    path = PATH.with_name("run_study45.py")
    spec = importlib.util.spec_from_file_location("rag_study45_test", path)
    study = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(study)
    case = {"id": "failure", "query": "query", "passages": [["p1", "s", "1:2", "text", "c", "supports"]],
            "assess": {"p1": "invalid"}, "gold": {"relevant": [], "expected": "abstain"}}
    row = study.evaluate_case(pipeline, case, "jev")
    assert row["evidence_status"] == "assessment_failed"
    assert not row["answer_success"]
