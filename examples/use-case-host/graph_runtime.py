"""Host-owned finite graph effect for the reviewed L source fixture.

This module is copied into the separate L test host. It uses the exact pinned
graph module, and treats classifier output as a proposal under host approval,
revision and audit. It has no provider or database connection.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from dataclasses import asdict

from . import graph


def merge(request: dict, state: dict) -> int:
    if (type(request) is not dict or type(request.get("task_id")) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request["task_id"])
            or request.get("graph_action") != "reconcile_same"):
        raise ValueError("finite graph action and task ID required")
    if (type(state.get("revision")) is not int or state["revision"] < 0
            or type(state.get("expected_revision")) is not int
            or type(state.get("approval")) is not bool):
        raise ValueError("graph revision and approval inputs required")
    path_name = os.environ.get("GRAPH_EFFECT_PATH")
    if not path_name:
        raise ValueError("GRAPH_EFFECT_PATH is required")
    path = Path(path_name.replace("{pid}", str(os.getpid())))
    if (not path.is_absolute() or path.exists() or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError("graph effect path must be fresh, absolute and unlinked")
    parent = path.parent.stat()
    if (not stat.S_ISDIR(parent.st_mode) or
            (os.name == "posix" and (parent.st_uid != os.getuid()
                                     or stat.S_IMODE(parent.st_mode) != 0o700))):
        raise ValueError("graph effect parent must be owner-private")
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
    raw = {"task_id": request["task_id"], "receipt": receipt,
           "entities": {key: asdict(entity) for key, entity in store.entities.items()},
           "merges": store.merges, "audits": audit_rows, "revision": store.revision}
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as stream:
        json.dump(raw, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return store.revision
