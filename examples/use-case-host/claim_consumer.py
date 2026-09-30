"""Finite offline M claim disposition with separately readable raw effects.

The source claim reviewer retains citation and critical-claim policy. This
fixture's assessor accepts only one exact, host-owned assertion and passage;
neither passage stance metadata nor a model label confers release authority.
The finite task registry retains the original claim-task and adds claim-one and
claim-two for the separately bound two-task console. Each task writes its own
independently observed private support, audit and release files.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from . import claim_oracle as oracle


PASSAGE = "Permit is active"
CLAIM_ID = "permit-status"
PASSAGE_ID = "permit-record-1"
SOURCE_ID = "fixture-permit-register-v1"


def raw(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _destination(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ValueError(name + " is required")
    path = Path(value.replace("{pid}", str(os.getpid())))
    if (not path.is_absolute() or path.exists() or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError("claim effect path must be fresh and unlinked")
    info = path.parent.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("claim effect parent must be owner-private")
    return path


def _write(path: Path, data: bytes) -> None:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600), "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _readback(path: Path, expected: bytes) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or os.read(descriptor, len(expected) + 1) != expected):
            raise ValueError("claim raw effect readback failed")
    finally:
        os.close(descriptor)


class ExactFixtureAssessor:
    def assess(self, request, claims, bundle):
        result = {}
        for claim in claims:
            ref = claim.citations[0]
            passage = bundle.citation(ref.passage_id)
            exact = (passage.text == PASSAGE and passage.source_id == SOURCE_ID
                     and passage.span == "0:16" and ref.start == 0
                     and ref.end == len(PASSAGE) and ref.quote == PASSAGE)
            label = ("supported" if exact and claim.text == PASSAGE else
                     "uncertain" if exact and claim.text == "Permit may be active" else
                     "contradicted" if exact and claim.text == "Permit is inactive" else
                     "unsupported")
            result[claim.claim_id] = oracle.ClaimAssessment(
                label, (ref.passage_id,))
        return result


def fixture_request(variant: str) -> dict:
    """Finite synthetic generator input, chosen by the reviewed host."""
    if variant not in {"accept", "revise", "request_evidence", "fabricated", "partial"}:
        raise ValueError("unregistered claim fixture variant")
    claim = "Permit may be active" if variant == "request_evidence" else PASSAGE
    return {"task_id": "claim-task", "claim": claim,
            "quote": "No permit" if variant == "fabricated" else
                     "Permit" if variant == "partial" else PASSAGE,
            "start": 0, "end": 6 if variant == "partial" else len(PASSAGE)}


def fixture_draft(request: dict, variant: str) -> oracle.DraftAnswer:
    """Construct a bounded draft; the host still decides disposition."""
    if variant not in {"accept", "revise", "request_evidence", "fabricated", "partial"}:
        raise ValueError("unregistered claim fixture variant")
    claims = [oracle.AtomicClaim(CLAIM_ID, request["claim"],
        (oracle.EvidenceRef(PASSAGE_ID, request["start"], request["end"],
                            request["quote"]),))]
    if variant == "revise":
        claims.append(oracle.AtomicClaim("unsupported-detail", "Permit expires tomorrow",
            (oracle.EvidenceRef(PASSAGE_ID, 0, len(PASSAGE), PASSAGE),)))
    return oracle.DraftAnswer(tuple(claims))


def expected(task_id: str, *, disposition: str = "released",
             removed: tuple[str, ...] = ()) -> tuple[bytes, bytes, bytes]:
    support = {"claim_id": CLAIM_ID, "passage_id": PASSAGE_ID, "source_id": SOURCE_ID,
               "span": "0:16", "citation_start": 0, "citation_end": len(PASSAGE),
               "quote": PASSAGE, "decision": "supported"}
    audit = {"task_id": task_id, "claim_id": CLAIM_ID,
             "support_sha256": hashlib.sha256(raw(support)).hexdigest(),
             "policy": "exact-fixture-support-v1"}
    if disposition == "revised":
        audit.update({"disposition": disposition, "removed_claim_ids": list(removed)})
    effect = {"task_id": task_id, "claim_id": CLAIM_ID, "claim": PASSAGE,
              "status": disposition, "audit_sha256": hashlib.sha256(raw(audit)).hexdigest(),
              "support_sha256": hashlib.sha256(raw(support)).hexdigest()}
    if disposition == "revised":
        effect["removed_claim_ids"] = list(removed)
    return raw(support), raw(audit), raw(effect)


def commit(request: dict, *, host_approved: bool,
           generated: oracle.DraftAnswer | None = None) -> dict:
    """Apply finite host disposition; release only after exact raw readback."""
    if (type(request) is not dict or set(request) != {"task_id", "claim", "quote", "start", "end"}
            or request.get("task_id") not in {"claim-task", "claim-one", "claim-two"}
            or type(request.get("claim")) is not str
            or type(request.get("quote")) is not str
            or type(request.get("start")) is not int
            or type(request.get("end")) is not int
            or host_approved is not True):
        raise ValueError("claim host permission or shape refused")
    passage = oracle.Passage(PASSAGE_ID, SOURCE_ID, "0:16", PASSAGE,
                             CLAIM_ID, "supports")
    bundle = oracle.select_evidence("permit status", (passage,), "current")
    critical = oracle.AtomicClaim(CLAIM_ID, request["claim"],
        (oracle.EvidenceRef(PASSAGE_ID, request["start"], request["end"],
                            request["quote"]),))
    draft = generated if generated is not None else oracle.DraftAnswer((critical,))
    if (not isinstance(draft, oracle.DraftAnswer) or not draft.claims
            or draft.claims[0] != critical):
        raise ValueError("generated critical claim differs from host request")
    outcome = oracle.review_claims(bundle, draft,
        oracle.ClaimRequest(frozenset({CLAIM_ID})), policy="jev",
        assessor=ExactFixtureAssessor())
    if outcome.status == "request_more_evidence":
        return {"disposition": "request_more_evidence", "reason": outcome.reason}
    if (outcome.status not in {"released", "revised"}
            or outcome.final is None
            or outcome.final.claims != (oracle.AtomicClaim(CLAIM_ID, PASSAGE,
                (oracle.EvidenceRef(PASSAGE_ID, 0, len(PASSAGE), PASSAGE),)),)
            or (CLAIM_ID, "supported") not in outcome.decisions):
        raise ValueError("critical claim unsupported or citation invalid")
    removed = tuple(claim.claim_id for claim in draft.claims
                    if claim.claim_id != CLAIM_ID)
    if outcome.status == "revised" and not removed:
        raise ValueError("empty claim revision refused")
    support, audit, effect = (_destination(name) for name in
        ("M_SUPPORT_PATH", "M_AUDIT_PATH", "M_CLAIM_PATH"))
    if len({support, audit, effect}) != 3 or len({p.parent for p in (support, audit, effect)}) != 1:
        raise ValueError("claim effects require distinct private files")
    support_raw, audit_raw, effect_raw = expected(
        request["task_id"], disposition=outcome.status, removed=removed)
    # Audit is durable before a releasable effect. A partial trio remains
    # occupied and requires external reconciliation; it never authorizes retry.
    _write(support, support_raw)
    _write(audit, audit_raw)
    _readback(support, support_raw)
    _readback(audit, audit_raw)
    _write(effect, effect_raw)
    _readback(effect, effect_raw)
    return {"reported": "ok"} if outcome.status == "released" else {
        "reported": "ok", "disposition": "revised"}
