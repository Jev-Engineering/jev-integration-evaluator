"""Host-owned /prune consumer for the exact reviewed retention fixture.

The retained-state file is the effect. It contains raw items, not a success
claim. The caller must provide a fresh absolute path in an owner-private
directory; no provider or generative compaction is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from . import retention_oracle


def _source() -> dict:
    values = (("pinned", "region east", "verified_source", "reviewed-one"),
              ("work", "task open", "tool", "run-one"),
              ("old", "noise item", "tool", "run-old"))
    items = [{"id": name, "text": value, "source_kind": kind,
              "source_ref": reference, "capture_revision": 1,
              "token_count": len(value.split()),
              "byte_sha256": retention_oracle.digest(value)}
             for name, value, kind, reference in values]
    return {"items": items, "pins": [{"id": "pinned"}]}


def _fresh_effect(path_name: str) -> Path:
    path = Path(path_name)
    if (not path.is_absolute() or path.exists() or path.is_symlink()
            or any(part.is_symlink() for part in (path, *path.parents))):
        raise ValueError("retained state path must be fresh, absolute and unlinked")
    parent = path.parent
    info = parent.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("retained state parent must be owner-private")
    return path


def commit(request: dict, selected: list[dict], *, token_budget: int = 6) -> list[str]:
    if type(token_budget) is not int or not 0 <= token_budget <= 6:
        raise ValueError("host token budget must be an integer in [0, 6]")
    if type(request) is not dict or request.get("command") != "/prune":
        raise ValueError("explicit /prune choice required; /compact is separate")
    if (type(selected) is not list or not selected
            or any(type(item) is not dict or type(item.get("id")) is not str
                   for item in selected)):
        raise ValueError("finite retained items required")
    selected_ids = [item["id"] for item in selected]
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("unique retained IDs required")
    declared = {
        "pinned": {"id": "pinned", "text": "never discard this constraint", "pinned": True},
        "work": {"id": "work", "text": "current work"},
        "old": {"id": "old", "text": "obsolete"},
    }
    if any(item != declared.get(item["id"]) for item in selected):
        raise ValueError("selected source item changed")
    case = _source()
    by_id = {item["id"]: item for item in case["items"]}
    if not set(selected_ids) <= set(by_id):
        raise ValueError("unknown retained ID")
    retained = [by_id[name] for name in selected_ids]
    checks = retention_oracle.raw_postconditions(case, retained, True, "/prune", token_budget)
    if any(checks[name] for name in ("pin_loss", "byte_or_provenance_loss",
                                      "over_budget_commit", "wrong_mode_mutation")):
        raise ValueError("retention postcondition failed")
    path_name = os.environ.get("H_RETAINED_PATH")
    if not path_name:
        raise ValueError("H_RETAINED_PATH is required for a retained-state effect")
    path = _fresh_effect(path_name.replace("{pid}", str(os.getpid())))
    raw = (json.dumps(retained, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return selected_ids[:]
