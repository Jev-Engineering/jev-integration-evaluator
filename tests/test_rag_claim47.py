"""Claim consumer behavior, independent of passage assessment."""

import importlib.util
import asyncio
from pathlib import Path
import sys


PATH = Path(__file__).resolve().parents[1] / "examples" / "rag-system" / "pipeline.py"
SPEC = importlib.util.spec_from_file_location("rag_claim47_pipeline", PATH)
p = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p
SPEC.loader.exec_module(p)


def fixture():
    passage = p.Passage("P1", "registry", "doc:1", "Permit is active", "source-claim", "supports")
    bundle = p.select_evidence("Permit status?", [passage], "current")
    ref = p.EvidenceRef("P1", 0, 16, "Permit is active")
    return bundle, ref


def test_legacy_claim_helper_still_returns_raw_classifier_output():
    class LLM:
        def classify(self, request, claims, context):
            return {"unvalidated": [request, claims, context]}

    assert p.claim_check(LLM(), "q", ["c"], "s") == {"unvalidated": ["q", ["c"], "s"]}


def test_deterministic_exact_span_is_real_but_not_semantic_support():
    bundle, ref = fixture()
    draft = p.DraftAnswer((p.AtomicClaim("c1", "Permit is inactive", (ref,)),))
    request = p.ClaimRequest(frozenset({"c1"}))
    assert p.review_claims(bundle, draft, request, policy="deterministic").status == "released"

    class Assessor:
        def assess(self, request, claims, evidence):
            return {"c1": p.ClaimAssessment("contradicted", ("P1",))}

    result = p.review_claims(bundle, draft, request, policy="jev", assessor=Assessor())
    assert result.status == "blocked" and result.final is None


def test_noncritical_claim_removed_and_citations_rechecked():
    bundle, ref = fixture()
    draft = p.DraftAnswer((p.AtomicClaim("c1", "Permit is active", (ref,)),
                           p.AtomicClaim("c2", "Permit is inactive", (ref,))))
    request = p.ClaimRequest(frozenset({"c1"}))

    class Assessor:
        def assess(self, request, claims, evidence):
            return {"c1": p.ClaimAssessment("supported", ("P1",)),
                    "c2": p.ClaimAssessment("unsupported", ("P1",))}

    result = p.review_claims(bundle, draft, request, policy="jev", assessor=Assessor())
    assert result.status == "revised"
    assert [c.claim_id for c in result.final.claims] == ["c1"]
    assert result.final.claims[0].citations == (ref,)


def test_dependency_blocks_removal():
    bundle, ref = fixture()
    draft = p.DraftAnswer((p.AtomicClaim("c1", "Permit is active", (ref,)),
                           p.AtomicClaim("c2", "Extra claim", (ref,))))
    request = p.ClaimRequest(frozenset({"c1"}), (("c1", "c2"),))

    class Assessor:
        def assess(self, request, claims, evidence):
            return {"c1": p.ClaimAssessment("supported", ("P1",)),
                    "c2": p.ClaimAssessment("unsupported", ("P1",))}

    assert p.review_claims(bundle, draft, request, policy="jev", assessor=Assessor()).status == "blocked"


def test_fabricated_span_blocks_before_assessor():
    bundle, ref = fixture()
    bad = p.EvidenceRef(ref.passage_id, 0, 6, "Absent")
    draft = p.DraftAnswer((p.AtomicClaim("c1", "Claim", (bad,)),))

    class Assessor:
        def assess(self, request, claims, evidence):
            raise AssertionError("must not run")

    result = p.review_claims(bundle, draft, p.ClaimRequest(frozenset({"c1"})),
                             policy="jev", assessor=Assessor())
    assert result.status == "blocked" and result.reason == "critical_citation_invalid"


def test_malformed_missing_timeout_and_uncertain_request_more_evidence():
    bundle, ref = fixture()
    draft = p.DraftAnswer((p.AtomicClaim("c1", "Claim", (ref,)),))
    request = p.ClaimRequest(frozenset({"c1"}))

    class Assessor:
        def __init__(self, response):
            self.response = response

        def assess(self, request, claims, evidence):
            if isinstance(self.response, BaseException):
                raise self.response
            return self.response

    responses = [None, {}, {"c1": p.ClaimAssessment("approve", ("P1",))},
                 {"c1": p.ClaimAssessment("uncertain", ("P1",))}, TimeoutError(),
                 asyncio.CancelledError()]
    for response in responses:
        outcome = p.review_claims(bundle, draft, request, policy="jev", assessor=Assessor(response))
        assert outcome.status == "request_more_evidence" and outcome.final is None


def test_actual_generation_consumer_uses_fixed_unfiltered_passages_once():
    bundle, ref = fixture()

    class Retriever:
        calls = 0

        def retrieve(self, query):
            self.calls += 1
            return bundle.passages

    class Generator:
        calls = 0

        def generate(self, query, passages):
            self.calls += 1
            assert passages == bundle.passages
            return p.DraftAnswer((p.AtomicClaim("c1", "Permit is active", (ref,)),))

    retriever, generator = Retriever(), Generator()

    class Audit:
        calls = 0

        def record(self, query, bundle, draft, outcome):
            self.calls += 1
            return True

    audit = Audit()
    result = p.answer_with_claim_review(retriever, generator, "query",
                                        p.ClaimRequest(frozenset({"c1"})), policy="deterministic", audit=audit)
    assert result.outcome.status == "released"
    assert retriever.calls == generator.calls == 1
    assert audit.calls == 1


def test_audit_failure_vetoes_delivery_without_retry():
    bundle, ref = fixture()

    class Retriever:
        def retrieve(self, query):
            return bundle.passages

    class Generator:
        calls = 0

        def generate(self, query, passages):
            self.calls += 1
            return p.DraftAnswer((p.AtomicClaim("c1", "Permit is active", (ref,)),))

    class Audit:
        calls = 0

        def record(self, query, bundle, draft, outcome):
            self.calls += 1
            raise RuntimeError("audit unavailable")

    generator, audit = Generator(), Audit()
    result = p.answer_with_claim_review(Retriever(), generator, "query",
                                        p.ClaimRequest(frozenset({"c1"})),
                                        policy="deterministic", audit=audit)
    assert result.outcome.status == "request_more_evidence"
    assert result.outcome.final is None and result.outcome.reason == "audit_failed"
    assert generator.calls == audit.calls == 1
