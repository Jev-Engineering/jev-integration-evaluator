"""Synthetic, injected RAG seams. No provider or retrieval client is constructed."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Passage:
    """A retrieved span with stable citation identity and source provenance."""

    passage_id: str
    source_id: str
    span: str
    text: str
    claim_id: str
    stance: str  # supports, contradicts, uncertain; metadata, not truth


@dataclass(frozen=True)
class EvidenceBundle:
    query: str
    passages: tuple[Passage, ...]
    decisions: tuple[tuple[str, str], ...]
    status: str  # ready, insufficient, assessment_failed

    def citation(self, passage_id: str) -> Passage:
        matches = [p for p in self.passages if p.passage_id == passage_id]
        if len(matches) != 1:
            raise ValueError("citation is absent or ambiguous")
        return matches[0]


@dataclass(frozen=True)
class GenerationResult:
    answer: object
    evidence: EvidenceBundle


def answer_request(retriever, llm, query):
    """Historical unfiltered fixture behavior, retained for baseline callers."""
    chunks = retriever.retrieve(query)
    answer = llm.generate(query, chunks)
    return answer


def _validate_passages(passages):
    if len(passages) > 32:
        raise ValueError("retrieval exceeds the 32-passage fixture limit")
    ids = set()
    for passage in passages:
        if not isinstance(passage, Passage):
            raise ValueError("retrieval must return Passage records")
        if not all((passage.passage_id, passage.source_id, passage.span, passage.claim_id)):
            raise ValueError("passage identity and provenance are required")
        if passage.stance not in {"supports", "contradicts", "uncertain"}:
            raise ValueError("unregistered passage stance")
        if passage.passage_id in ids:
            raise ValueError("duplicate passage identity")
        ids.add(passage.passage_id)


def _lexical_decisions(query, passages):
    terms = set(re.findall(r"[a-z0-9]+", query.lower())) - {"a", "an", "the", "is", "of", "for", "what", "status"}
    return {p.passage_id: "relevant" if terms & set(re.findall(r"[a-z0-9]+", p.text.lower())) else "irrelevant"
            for p in passages}


def select_evidence(query, passages, policy, assessor=None):
    """Select evidence, retaining material conflicts under host-owned policy."""
    passages = tuple(passages)
    _validate_passages(passages)
    if policy == "current":
        decisions = {p.passage_id: "relevant" for p in passages}
    elif policy == "lexical":
        decisions = _lexical_decisions(query, passages)
    elif policy == "jev":
        try:
            if assessor is None:
                raise ValueError("assessor is required")
            decisions = assessor.assess(query, passages)
            if (not isinstance(decisions, dict) or set(decisions) != {p.passage_id for p in passages}
                    or any(value not in {"relevant", "irrelevant", "uncertain"} for value in decisions.values())):
                raise ValueError("malformed assessment")
        except Exception:
            return EvidenceBundle(query, (), (), "assessment_failed")
    else:
        raise ValueError("unregistered evidence policy")

    selected = {p.passage_id for p in passages if decisions[p.passage_id] != "irrelevant"}
    material_claims = {p.claim_id for p in passages if p.passage_id in selected}
    selected.update(p.passage_id for p in passages if p.claim_id in material_claims
                    and p.stance in {"contradicts", "uncertain"})
    chosen = tuple(p for p in passages if p.passage_id in selected)
    return EvidenceBundle(query, chosen, tuple((p.passage_id, decisions[p.passage_id]) for p in passages),
                          "ready" if chosen else "insufficient")


def answer_with_evidence(retriever, llm, query, *, policy, assessor=None):
    """Host consumer: generation runs once and only with selected spans."""
    bundle = select_evidence(query, retriever.retrieve(query), policy, assessor)
    if bundle.status != "ready":
        return GenerationResult(None, bundle)
    return GenerationResult(llm.generate(query, bundle), bundle)


def claim_check(llm, request, claims, source_context):
    answer = llm.classify(request, claims, source_context)
    return answer
