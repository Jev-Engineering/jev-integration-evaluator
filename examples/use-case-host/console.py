"""Finite offline console fixture for six distinct source-bound host consumers.

The five imported modules are copied byte-for-byte from the reviewed fixtures
by the test host builder. This command is deliberately not a provider client.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

from . import agent, completion, graph, rag, retention


def _registered_tool() -> dict:
    class Choice:
        def __init__(self, name):
            self.name = name

        def choose(self, *_):
            return self.name

    class Executor:
        def __init__(self):
            self.calls = []

        def execute_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return type("Result", (), {"exit_code": 0})()

    executor = Executor()
    denied = agent.dispatch_once(Choice("write_file"), executor, "read",
                                 agent.REGISTERED_CAPABILITIES,
                                 arguments={"path": "fixture", "content": "x"},
                                 granted_permissions=("read",))
    allowed = agent.dispatch_once(Choice("read_file"), executor, "read",
                                  agent.REGISTERED_CAPABILITIES,
                                  arguments={"path": "fixture"},
                                  granted_permissions=("read",))
    return {"denied": denied, "allowed": allowed, "calls": executor.calls}


def _graph_identity() -> dict:
    left = graph.Entity("left", "Acme", "US", "one", "registry-left")
    right = graph.Entity("right", "Acme", "US", "one", "registry-right")
    store = graph.InMemoryGraph(left, right, revision=4)

    class Same:
        def classify(self, *_):
            return "same"

    audits = []
    def audit(row):
        if row["sources"] != ["registry-left", "registry-right"]:
            raise ValueError("source mismatch")
        audits.append(dict(row))

    denied = graph.reconcile(Same(), store, left, right, False, 4)
    stale = graph.reconcile(Same(), store, left, right, True, 3)
    receipt = graph.reconcile(Same(), store, left, right, True, 4, audit=audit)
    return {"unapproved": denied, "stale": stale, "receipt": receipt,
            "revision": store.revision, "merges": store.merges, "audits": audits}


def _retrieval_evidence() -> dict:
    support = rag.Passage("support", "source-one", "0:15", "approved status", "status", "supports")
    conflict = rag.Passage("conflict", "source-two", "0:13", "denied status", "status", "contradicts")

    class Retriever:
        def __init__(self, passages):
            self.passages = passages

        def retrieve(self, _):
            return self.passages

    class Generator:
        def __init__(self):
            self.calls = 0

        def generate(self, _, bundle):
            self.calls += 1
            return [item.passage_id for item in bundle.passages]

    generator = Generator()
    empty = rag.answer_with_evidence(Retriever([]), generator, "approved", policy="lexical")
    selected = rag.answer_with_evidence(Retriever([support, conflict]), generator,
                                        "approved", policy="lexical")
    return {"empty_status": empty.evidence.status, "empty_answer": empty.answer,
            "selected_ids": selected.answer,
            "conflict_source": selected.evidence.citation("conflict").source_id,
            "generator_calls": generator.calls}


def _completion() -> dict:
    objective = {"task_id": "one", "allowed_fields": ["task_id", "status", "revision",
                                                       "labels", "unrequested"],
                 "required_status": "closed", "required_labels": ["verified"],
                 "required_unrequested": []}
    initial = {"task_id": "one", "status": "open", "revision": 1,
               "labels": [], "unrequested": []}
    reported_success = dict(initial, executor_success=True)
    final = {"task_id": "one", "status": "closed", "revision": 2,
             "labels": ["verified"], "unrequested": []}
    return {"initial": initial, "final": final,
            "success_report_only_verified": completion.exact_goal(reported_success, objective),
            "raw_final_verified": completion.exact_goal(final, objective),
            "final_sha256": completion.state_digest(final)}


def _claim_support() -> dict:
    passage = rag.Passage("p1", "source-one", "0:15", "alpha supported", "c1", "supports")
    bundle = rag.EvidenceBundle("alpha", (passage,), (("p1", "relevant"),), "ready")
    good = rag.AtomicClaim("c1", "alpha", (rag.EvidenceRef("p1", 0, 5, "alpha"),))
    fake = rag.AtomicClaim("c2", "beta", (rag.EvidenceRef("missing", 0, 4, "beta"),))
    blocked = rag.review_claims(bundle, rag.DraftAnswer((fake,)),
                                rag.ClaimRequest(frozenset({"c2"})), policy="deterministic")

    class Retriever:
        def retrieve(self, _):
            return [passage]

    class Generator:
        def generate(self, *_):
            return rag.DraftAnswer((good,))

    class Audit:
        def __init__(self):
            self.records = 0

        def record(self, *_):
            self.records += 1
            return True

    audit = Audit()
    released = rag.answer_with_claim_review(Retriever(), Generator(), "alpha",
                    rag.ClaimRequest(frozenset({"c1"})), policy="deterministic", audit=audit)
    return {"fabricated_critical": blocked.status, "valid_claim": released.outcome.status,
            "audit_records": audit.records,
            "released_ids": [item.claim_id for item in released.outcome.final.claims]}


def _retention() -> dict:
    pinned = {"id": "pin", "text": "region east", "source_kind": "verified_source",
              "source_ref": "reviewed-one", "capture_revision": 1,
              "token_count": 2, "byte_sha256": retention.digest("region east")}
    recent = {"id": "recent", "text": "noise item", "source_kind": "tool",
              "source_ref": "run-one", "capture_revision": 1,
              "token_count": 2, "byte_sha256": retention.digest("noise item")}
    case = {"items": [pinned, recent], "pins": [{"id": "pin"}]}
    pruned = [pinned]
    prune = retention.raw_postconditions(case, pruned, True, "/prune", 2)
    compact_unchanged = retention.raw_postconditions(case, case["items"], False, "/compact", 2)
    compact_mutated = retention.raw_postconditions(case, pruned, True, "/compact", 2)
    recall = retention.score_recall("authoritative region sources",
                 {"applicable": True, "expected_answer": "east",
                  "required_source_ids": ["pin"],
                  "required_source_sha256": {"pin": pinned["byte_sha256"]}}, pruned, [])
    return {"user_choice": "/prune", "raw_items": case["items"],
            "retained_items": pruned, "prune": prune,
            "compact_unchanged": compact_unchanged,
            "compact_mutation_blocked": compact_mutated["wrong_mode_mutation"],
            "later_recall": recall}


def main() -> int:
    if os.environ.get("JEV_RUNTIME_MODE") != "off":
        return 2
    directory = Path(os.environ["USE_CASE_EFFECT_DIR"])
    ready = Path(os.environ["USE_CASE_READY_PATH"])
    if not directory.is_absolute() or not ready.is_absolute() or not directory.is_dir():
        return 2
    outcomes = {"C": _registered_tool(), "L": _graph_identity(),
                "D": _retrieval_evidence(), "E": _completion(),
                "M": _claim_support(), "H": _retention()}
    for case_id, outcome in outcomes.items():
        (directory / (case_id + ".json")).write_text(
            json.dumps(outcome, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    ready.write_bytes(b"ready\n")
    hold = float(os.environ.get("USE_CASE_HOLD_SECONDS", "0"))
    if not 0 <= hold <= 5:
        return 2
    time.sleep(hold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
