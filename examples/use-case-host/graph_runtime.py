"""Host-owned finite graph effect for the reviewed L source fixture.

This module is copied into the separate L test host. It uses the exact pinned
graph module, and treats classifier output as a proposal under host approval,
revision and audit. It has no provider or database connection.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import graph


def merge(request: dict, state: dict) -> int:
    left = graph.Entity("left", "Acme", "US", "one", "registry-left")
    right = graph.Entity("right", "Acme", "US", "one", "registry-right")
    store = graph.InMemoryGraph(left, right, revision=state["revision"])
    audit_rows: list[dict] = []

    class Same:
        def classify(self, *_):
            return "same"

    def audit(row: dict) -> None:
        if row["sources"] != ["registry-left", "registry-right"]:
            raise ValueError("graph provenance changed")
        audit_rows.append(dict(row))

    receipt = graph.reconcile(Same(), store, left, right,
                              state["approval"], state["expected_revision"], audit=audit)
    if receipt is None or len(store.merges) != 1 or audit_rows != store.merges:
        raise RuntimeError("graph merge did not satisfy host postconditions")
    path_name = os.environ.get("GRAPH_EFFECT_PATH")
    if path_name:
        path = Path(path_name)
        if not path.is_absolute() or path.exists() or path.is_symlink():
            raise ValueError("graph effect path must be fresh and absolute")
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"receipt": receipt, "merges": store.merges,
                       "audits": audit_rows, "revision": store.revision}, stream,
                      sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    return store.revision
