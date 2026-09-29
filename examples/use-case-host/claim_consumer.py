"""Finite offline M claim disposition with separately readable raw effects.

The source claim reviewer retains citation and critical-claim policy. This
fixture's assessor accepts only one exact, host-owned assertion and passage;
neither passage stance metadata nor a model label confers release authority.
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


class ExactFixtureAssessor:
    def assess(self, request, claims, bundle):
        result = {}
        for claim in claims:
            ref = claim.citations[0]
            passage = bundle.citation(ref.passage_id)
            supported = (claim.text == PASSAGE and passage.text == PASSAGE
                         and passage.source_id == SOURCE_ID
                         and passage.span == "0:16"
                         and ref.start == 0 and ref.end == len(PASSAGE)
                         and ref.quote == PASSAGE)
            result[claim.claim_id] = oracle.ClaimAssessment(
                "supported" if supported else "unsupported", (ref.passage_id,))
        return result


def expected(task_id: str) -> tuple[bytes, bytes, bytes]:
    support = {"claim_id": CLAIM_ID, "passage_id": PASSAGE_ID, "source_id": SOURCE_ID,
               "span": "0:16", "quote": PASSAGE, "decision": "supported"}
    audit = {"task_id": task_id, "claim_id": CLAIM_ID,
             "support_sha256": hashlib.sha256(raw(support)).hexdigest(),
             "policy": "exact-fixture-support-v1"}
    effect = {"task_id": task_id, "claim_id": CLAIM_ID, "claim": PASSAGE,
              "status": "released", "audit_sha256": hashlib.sha256(raw(audit)).hexdigest(),
              "support_sha256": hashlib.sha256(raw(support)).hexdigest()}
    return raw(support), raw(audit), raw(effect)


def commit(request: dict, *, host_approved: bool) -> dict:
    """Release one reviewed assertion once after exact support and durable audit."""
    if (type(request) is not dict or set(request) != {"task_id", "claim", "quote", "start", "end"}
            or request.get("task_id") != "claim-task"
            or type(request.get("claim")) is not str
            or type(request.get("quote")) is not str
            or type(request.get("start")) is not int
            or type(request.get("end")) is not int
            or host_approved is not True):
        raise ValueError("claim host permission or shape refused")
    passage = oracle.Passage(PASSAGE_ID, SOURCE_ID, "0:16", PASSAGE,
                             CLAIM_ID, "supports")
    bundle = oracle.select_evidence("permit status", (passage,), "current")
    draft = oracle.DraftAnswer((oracle.AtomicClaim(CLAIM_ID, request["claim"],
        (oracle.EvidenceRef(PASSAGE_ID, request["start"], request["end"],
                            request["quote"]),)),))
    outcome = oracle.review_claims(bundle, draft,
        oracle.ClaimRequest(frozenset({CLAIM_ID})), policy="jev",
        assessor=ExactFixtureAssessor())
    if (outcome.status != "released" or outcome.final != draft
            or outcome.decisions != ((CLAIM_ID, "supported"),)):
        raise ValueError("critical claim unsupported or citation invalid")
    support, audit, effect = (_destination(name) for name in
        ("M_SUPPORT_PATH", "M_AUDIT_PATH", "M_CLAIM_PATH"))
    if len({support, audit, effect}) != 3 or len({p.parent for p in (support, audit, effect)}) != 1:
        raise ValueError("claim effects require distinct private files")
    support_raw, audit_raw, effect_raw = expected(request["task_id"])
    # Audit is durable before a releasable effect. A partial trio remains
    # occupied and requires external reconciliation; it never authorizes retry.
    _write(support, support_raw)
    _write(audit, audit_raw)
    _write(effect, effect_raw)
    return {"reported": "ok"}
