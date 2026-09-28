"""Synthetic, injected RAG seams. No provider or retrieval client is constructed."""

from dataclasses import dataclass
import asyncio
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


@dataclass(frozen=True)
class EvidenceRef:
    passage_id: str
    start: int
    end: int
    quote: str


@dataclass(frozen=True)
class AtomicClaim:
    claim_id: str
    text: str
    citations: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class DraftAnswer:
    claims: tuple[AtomicClaim, ...]


@dataclass(frozen=True)
class ClaimRequest:
    critical_claim_ids: frozenset[str]
    requires_together: tuple[tuple[str, str], ...] = ()  # (dependent, dependency)


@dataclass(frozen=True)
class ClaimAssessment:
    label: str  # supported, contradicted, unsupported, uncertain
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClaimOutcome:
    status: str  # released, revised, blocked, request_more_evidence
    final: DraftAnswer | None
    decisions: tuple[tuple[str, str], ...]
    reason: str


@dataclass(frozen=True)
class ClaimGenerationResult:
    draft: DraftAnswer
    evidence: EvidenceBundle
    outcome: ClaimOutcome


def _claim_shapes(draft, request):
    if (not isinstance(draft, DraftAnswer) or not isinstance(draft.claims, tuple)
            or not 1 <= len(draft.claims) <= 4):
        return False
    ids = [claim.claim_id for claim in draft.claims if isinstance(claim, AtomicClaim)]
    if len(ids) != len(draft.claims) or len(ids) != len(set(ids)) or not all(ids):
        return False
    if (not isinstance(request, ClaimRequest)
            or not isinstance(request.critical_claim_ids, frozenset)
            or not request.critical_claim_ids <= set(ids)
            or not isinstance(request.requires_together, tuple)):
        return False
    if any(not isinstance(pair, tuple) or len(pair) != 2 for pair in request.requires_together):
        return False
    if any(a not in ids or b not in ids or a == b for a, b in request.requires_together):
        return False
    return all(isinstance(c.text, str) and 0 < len(c.text) <= 500
               and isinstance(c.citations, tuple) and len(c.citations) <= 3 for c in draft.claims)


def _valid_citations(claim, bundle):
    if not claim.citations:
        return False
    ids = set()
    for ref in claim.citations:
        if not isinstance(ref, EvidenceRef) or not isinstance(ref.passage_id, str):
            return False
        if ref.passage_id in ids:
            return False
        ids.add(ref.passage_id)
        try:
            passage = bundle.citation(ref.passage_id)
        except ValueError:
            return False
        if (type(ref.start) is not int or type(ref.end) is not int
                or not 0 <= ref.start < ref.end <= len(passage.text)
                or not isinstance(ref.quote, str) or len(ref.quote) > 200
                or passage.text[ref.start:ref.end] != ref.quote):
            return False
    return True


def _remove_or_block(draft, request, failed_ids):
    ids = {claim.claim_id for claim in draft.claims}
    if failed_ids & request.critical_claim_ids:
        return ClaimOutcome("blocked", None, (), "critical_claim_failed")
    kept = ids - failed_ids
    if not kept or any(a in kept and b not in kept for a, b in request.requires_together):
        return ClaimOutcome("blocked", None, (), "dependent_or_empty_answer")
    final = DraftAnswer(tuple(claim for claim in draft.claims if claim.claim_id in kept))
    return ClaimOutcome("revised", final, (), "noncritical_claim_removed")


def review_claims(bundle, draft, request, *, policy, assessor=None):
    """Host-owned synthetic claim consumer; model labels never release by themselves."""
    if not isinstance(bundle, EvidenceBundle) or bundle.status != "ready":
        return ClaimOutcome("request_more_evidence", None, (), "evidence_unavailable")
    if not _claim_shapes(draft, request):
        return ClaimOutcome("blocked", None, (), "invalid_draft_or_request")
    invalid = {claim.claim_id for claim in draft.claims if not _valid_citations(claim, bundle)}
    eligible = tuple(claim for claim in draft.claims if claim.claim_id not in invalid)
    if invalid & request.critical_claim_ids:
        return ClaimOutcome("blocked", None, (), "critical_citation_invalid")
    if not eligible:
        return ClaimOutcome("blocked", None, (), "no_valid_claim")
    if policy == "deterministic":
        decisions = {claim.claim_id: ("unsupported" if claim.claim_id in invalid else "supported")
                     for claim in draft.claims}
    elif policy == "jev":
        try:
            if assessor is None:
                raise ValueError("assessor required")
            assessed = assessor.assess(request, eligible, bundle)
            if not isinstance(assessed, dict) or set(assessed) != {claim.claim_id for claim in eligible}:
                raise ValueError("missing or extra claim decisions")
            for claim in eligible:
                item = assessed[claim.claim_id]
                cited = {ref.passage_id for ref in claim.citations}
                if (not isinstance(item, ClaimAssessment)
                        or item.label not in {"supported", "contradicted", "unsupported", "uncertain"}
                        or not isinstance(item.evidence_ids, tuple)
                        or not item.evidence_ids
                        or len(item.evidence_ids) != len(set(item.evidence_ids))
                        or not set(item.evidence_ids) <= cited):
                    raise ValueError("malformed claim decision")
            decisions = {claim.claim_id: ("unsupported" if claim.claim_id in invalid
                                           else assessed[claim.claim_id].label) for claim in draft.claims}
        except (Exception, asyncio.CancelledError):
            return ClaimOutcome("request_more_evidence", None, (), "assessment_failed")
    else:
        raise ValueError("unregistered claim policy")
    ordered = tuple((claim.claim_id, decisions[claim.claim_id]) for claim in draft.claims)
    if "uncertain" in decisions.values():
        return ClaimOutcome("request_more_evidence", None, ordered, "uncertain_claim")
    failed = {claim_id for claim_id, label in decisions.items() if label != "supported"}
    if failed:
        result = _remove_or_block(draft, request, failed)
        if result.final is not None and any(not _valid_citations(c, bundle) for c in result.final.claims):
            return ClaimOutcome("blocked", None, ordered, "revised_citation_invalid")
        return ClaimOutcome(result.status, result.final, ordered, result.reason)
    return ClaimOutcome("released", draft, ordered, "all_claims_passed")


def answer_with_claim_review(retriever, generator, query, request, *, policy, assessor=None, audit=None):
    """Generate once; a host audit must succeed before any final delivery."""
    passages = tuple(retriever.retrieve(query))
    bundle = select_evidence(query, passages, "current")
    if bundle.status != "ready":
        return ClaimGenerationResult(DraftAnswer(()), bundle,
                                     ClaimOutcome("request_more_evidence", None, (), "evidence_unavailable"))
    draft = generator.generate(query, passages)
    outcome = review_claims(bundle, draft, request, policy=policy, assessor=assessor)
    if outcome.final is not None:
        try:
            if audit is None or audit.record(query, bundle, draft, outcome) is not True:
                raise ValueError("audit unavailable or failed")
        except (Exception, asyncio.CancelledError):
            outcome = ClaimOutcome("request_more_evidence", None, outcome.decisions, "audit_failed")
    return ClaimGenerationResult(draft, bundle, outcome)
