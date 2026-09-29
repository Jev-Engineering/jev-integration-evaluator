"""Finite host-owned retrieval and answer release for the offline D fixture.

The corpus is an existing external file with pinned bytes. Code composes one
bounded status answer only from exact unopposed source text. It records missing
and conflicting provenance without treating a stance label as source truth.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from . import retrieval_oracle as rag


CORPUS_SHA256 = "46b07c036fedc22cd4073d0f1db2466d13856389b86db84b725f51b9e4a77c67"


def _private_file(name: str, *, fresh: bool) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ValueError(name + " is required")
    path = Path(value.replace("{pid}", str(os.getpid())))
    if (not path.is_absolute() or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError("retrieval path must be absolute and unlinked")
    parent = path.parent.stat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise ValueError("retrieval parent must be owner-private")
    if fresh:
        if path.exists():
            raise ValueError("retrieval effect path must be fresh")
    else:
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or not 0 < info.st_size <= 65536):
            raise ValueError("retrieval corpus must be a private regular file")
    return path


def _corpus() -> dict:
    path = _private_file("D_CORPUS_PATH", fresh=False)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CORPUS_SHA256:
        raise ValueError("reviewed corpus bytes changed")
    value = json.loads(raw)
    if (type(value) is not dict or value.get("revision") != 7
            or type(value.get("passages")) is not list
            or len(value["passages"]) != 4):
        raise ValueError("reviewed corpus shape changed")
    return value


class _Retriever:
    def __init__(self, passages: tuple[rag.Passage, ...]):
        self.passages = passages

    def retrieve(self, query: str) -> tuple[rag.Passage, ...]:
        if query != "approved":
            raise ValueError("unregistered retrieval query")
        return self.passages


def answer_handoff(query: str, bundle: rag.EvidenceBundle, rows: list[dict]) -> dict:
    """Build a release decision from exact passages and retained corpus lineage.

    This is a small code-owned answer consumer, not a model substitute for an
    arbitrary question. Incomplete or disputed evidence cannot release text.
    """
    if (query != "approved" or not isinstance(bundle, rag.EvidenceBundle)
            or bundle.query != query):
        raise ValueError("unregistered answer handoff")
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows) or any(
        row.get("provenance") != row["source_id"] + ":" + row["span"]
        for row in rows
    ):
        raise ValueError("ambiguous or missing corpus provenance")
    initial = dict(bundle.decisions)
    if (len(initial) != len(bundle.decisions) or set(initial) != set(by_id)
            or any(value not in {"relevant", "irrelevant", "uncertain"}
                   for value in initial.values())):
        raise ValueError("ambiguous initial relevance")
    def provenance(row: dict) -> dict:
        return {"passage_id": row["id"], "source_id": row["source_id"],
                "span": row["span"], "quote": row["text"],
                "claim_id": row["claim_id"], "stance": row["stance"],
                "provenance": row["provenance"],
                "initial_relevance": initial[row["id"]]}
    selected = []
    for passage in bundle.passages:
        row = by_id.get(passage.passage_id)
        if (row is None or passage.passage_id not in initial
                or (passage.source_id, passage.span, passage.text,
                    passage.claim_id, passage.stance) !=
                   (row["source_id"], row["span"], row["text"],
                    row["claim_id"], row["stance"])):
            raise ValueError("answer passage differs from reviewed provenance")
        selected.append(provenance(row))
    selected_ids = {item["passage_id"] for item in selected}
    if len(selected_ids) != len(selected):
        raise ValueError("duplicate answer passage")
    # Any known opposing or uncertain status passage is material, even if the
    # initial relevance decision called it irrelevant.
    required = {row["id"] for row in rows if row["claim_id"] == "status"}
    missing_passages = sorted(required - selected_ids)
    missing_provenance = [provenance(by_id[passage_id]) for passage_id in missing_passages]
    supports = [item for item in selected
                if item["claim_id"] == "status" and item["stance"] == "supports"
                and item["quote"] == "status approved"]
    missing_claims = [] if supports else ["status"]
    disputed = [item for item in selected if item["claim_id"] == "status"
                and (item["stance"] != "supports" or item["quote"] != "status approved")]
    if bundle.status != "ready" or missing_claims or missing_passages:
        disposition, answer = "withheld_missing", None
    elif disputed:
        disposition, answer = "withheld_conflict", None
    else:
        disposition = "released"
        answer = {"text": "The reviewed source reports status approved.",
                  "claim_id": "status", "passage_ids": [item["passage_id"] for item in supports]}
    return {"schema_version": "1.0", "kind": "retrieval-answer-handoff-v1",
            "query": query, "disposition": disposition, "answer": answer,
            "passages": selected, "missing_claim_ids": missing_claims,
            "missing_passage_ids": missing_passages,
            "missing_passages": missing_provenance}


class _AnswerConsumer:
    """The actual bounded source-to-answer consumer in the normal host path."""

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def generate(self, query: str, bundle: rag.EvidenceBundle) -> dict:
        return answer_handoff(query, bundle, self.rows)


def commit(request: dict, selected: list[dict], *, host_approved: bool) -> list[str]:
    if (type(request) is not dict or request.get("query") != "approved"
            or type(request.get("expected_revision")) is not int
            or host_approved is not True):
        raise ValueError("retrieval query, revision or host approval refused")
    corpus = _corpus()
    if request["expected_revision"] != corpus["revision"]:
        raise ValueError("stale corpus revision")
    rows = corpus["passages"]
    if type(selected) is not list or not selected:
        raise ValueError("finite selected passages required")
    ids = [row.get("id") for row in selected if type(row) is dict]
    if len(ids) != len(selected) or len(ids) != len(set(ids)):
        raise ValueError("ambiguous selected passages")
    by_id = {row["id"]: row for row in rows}
    if any(row != by_id.get(row["id"]) for row in selected):
        raise ValueError("selected passage differs from reviewed corpus")
    passages = tuple(rag.Passage(row["id"], row["source_id"], row["span"],
                                 row["text"], row["claim_id"], row["stance"])
                     for row in rows)
    bundle = rag.select_evidence(request["query"], passages, "lexical")
    if bundle.status != "ready":
        raise ValueError("no usable retrieval evidence")
    required = {p.passage_id for p in bundle.passages}
    if not required <= set(ids):
        raise ValueError("selected passages omit material evidence")
    result = rag.answer_with_evidence(_Retriever(passages), _AnswerConsumer(rows),
                                      request["query"], policy="lexical")
    if result.evidence != bundle or result.answer is None:
        raise ValueError("generation did not consume reviewed evidence")
    path = _private_file("D_EFFECT_PATH", fresh=True)
    if path == Path(os.environ["D_CORPUS_PATH"]):
        raise ValueError("effect path collides with corpus")
    effect = {"corpus_revision": corpus["revision"],
              "corpus_sha256": CORPUS_SHA256,
              "status": result.evidence.status,
              "selected_ids": [p.passage_id for p in result.evidence.passages],
              "decisions": [list(item) for item in result.evidence.decisions],
              "answer": result.answer}
    raw = (json.dumps(effect, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return ids
