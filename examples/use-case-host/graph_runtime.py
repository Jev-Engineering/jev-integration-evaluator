"""Host-owned finite graph effect for the reviewed L source fixture.

This module is copied into the separate L test host. It uses the exact pinned
graph module, and treats classifier output as a proposal under host approval,
revision and audit. An explicit external SQLite path enables a durable fixture
transaction; neither path has a provider connection.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from dataclasses import asdict

from . import graph


def _private_path(name: str, label: str, *, fresh: bool) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ValueError(name + " is required")
    path = Path(value.replace("{pid}", str(os.getpid())))
    if (not path.is_absolute() or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)
            or (fresh and path.exists())):
        raise ValueError(label + " path must be fresh, absolute and unlinked")
    parent = path.parent.stat()
    if (not stat.S_ISDIR(parent.st_mode) or
            (os.name == "posix" and (parent.st_uid != os.getuid()
                                     or stat.S_IMODE(parent.st_mode) != 0o700))):
        raise ValueError(label + " parent must be owner-private")
    if path.exists():
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                (os.name == "posix" and (info.st_uid != os.getuid() or
                                         stat.S_IMODE(info.st_mode) != 0o600))):
            raise ValueError(label + " database identity changed")
    return path


def _sqlite_merge(path: Path, state: dict, left: graph.Entity,
                  right: graph.Entity) -> tuple[dict, dict]:
    """Commit audit and exact-revision merge in one SQLite transaction."""
    if not path.exists():
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        os.close(os.open(path, flags, 0o600))
    expected_entities = tuple((entity.key, entity.name, entity.jurisdiction,
                               entity.registry_id, entity.provenance)
                              for entity in (left, right))
    db = sqlite3.connect(path, timeout=0)
    try:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS entities (key TEXT PRIMARY KEY, name TEXT NOT NULL, "
                   "jurisdiction TEXT NOT NULL, registry_id TEXT, provenance TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS revision (value INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, receipt TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS merges (id INTEGER PRIMARY KEY, receipt TEXT NOT NULL)")
        recorded = db.execute("SELECT value FROM revision").fetchall()
        if not recorded:
            if state["revision"] != 0 or state["expected_revision"] != 0:
                raise RuntimeError("graph database initial revision refused")
            db.executemany("INSERT INTO entities VALUES (?, ?, ?, ?, ?)", expected_entities)
            db.execute("INSERT INTO revision VALUES (0)")
            recorded = [(0,)]
        current_entities = tuple(db.execute(
            "SELECT key, name, jurisdiction, registry_id, provenance FROM entities ORDER BY key"))
        if (len(recorded) != 1 or current_entities != expected_entities
                or recorded[0][0] != state["revision"]
                or recorded[0][0] != state["expected_revision"]
                or db.execute("SELECT COUNT(*) FROM merges").fetchone()[0] != recorded[0][0]
                or db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] != recorded[0][0]):
            raise RuntimeError("graph database identity or revision conflict")
        staged = graph.InMemoryGraph(left, right, revision=recorded[0][0])
        audit_rows: list[dict] = []
        def audit(row: dict) -> None:
            if row["sources"] != [left.provenance, right.provenance]:
                raise ValueError("graph provenance changed")
            audit_rows.append(dict(row))
        class Same:
            def classify(self, *_):
                return "same"
        receipt = graph.reconcile(Same(), staged, left, right, state["approval"],
                                  state["expected_revision"], audit=audit)
        if receipt is None or audit_rows != staged.merges or len(staged.merges) != 1:
            raise RuntimeError("graph merge did not satisfy host postconditions")
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
        db.execute("INSERT INTO audit(receipt) VALUES (?)", (encoded,))
        db.execute("INSERT INTO merges(receipt) VALUES (?)", (encoded,))
        changed = db.execute("UPDATE revision SET value = ? WHERE value = ?",
                             (staged.revision, recorded[0][0])).rowcount
        if changed != 1:
            raise RuntimeError("graph revision compare-and-swap failed")
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
    # A separate read-only connection checks the committed bytes, not the
    # staging graph or the connection that made the write.
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as reader:
        entities = tuple(reader.execute(
            "SELECT key, name, jurisdiction, registry_id, provenance FROM entities ORDER BY key"))
        revisions = reader.execute("SELECT value FROM revision").fetchall()
        audits = [json.loads(row[0]) for row in reader.execute("SELECT receipt FROM audit ORDER BY id")]
        merges = [json.loads(row[0]) for row in reader.execute("SELECT receipt FROM merges ORDER BY id")]
    if (entities != expected_entities or revisions != [(staged.revision,)]
            or audits[-1:] != [receipt] or merges[-1:] != [receipt]
            or len(audits) != staged.revision or len(merges) != staged.revision):
        raise RuntimeError("graph committed database readback failed")
    return receipt, {"entities": {key: asdict(entity) for key, entity in
                                  ((left.key, left), (right.key, right))},
                     "merges": merges, "audits": audits, "revision": staged.revision}


def merge(request: dict, state: dict) -> int:
    if (type(request) is not dict or type(request.get("task_id")) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request["task_id"])
            or request.get("graph_action") != "reconcile_same"):
        raise ValueError("finite graph action and task ID required")
    if (type(state.get("revision")) is not int or state["revision"] < 0
            or type(state.get("expected_revision")) is not int
            or type(state.get("approval")) is not bool):
        raise ValueError("graph revision and approval inputs required")
    path = _private_path("GRAPH_EFFECT_PATH", "graph effect", fresh=True)
    if state["approval"] is not True or state["revision"] != state["expected_revision"]:
        raise RuntimeError("graph merge did not satisfy host postconditions")
    left = graph.Entity("left", "Acme", "US", "one", "registry-left")
    right = graph.Entity("right", "Acme", "US", "one", "registry-right")
    if os.environ.get("GRAPH_DB_PATH"):
        database = _private_path("GRAPH_DB_PATH", "graph", fresh=False)
        receipt, recorded = _sqlite_merge(database, state, left, right)
        raw = {"task_id": request["task_id"], "receipt": receipt, **recorded}
        revision = recorded["revision"]
    else:
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
        revision = store.revision
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as stream:
        json.dump(raw, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return revision
