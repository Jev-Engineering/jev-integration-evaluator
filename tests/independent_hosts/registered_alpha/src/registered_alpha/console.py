"""Normal console command for the independent registered-action application."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from .host import public_entry


class Audit:
    def append(self, record) -> None:
        path = Path(os.environ["JEV_ALPHA_AUDIT"])
        if (not path.is_absolute() or path.is_symlink()
                or any(parent.is_symlink() for parent in path.parents)
                or path.parent.stat().st_uid != os.getuid()
                or stat.S_IMODE(path.parent.stat().st_mode) & 0o077):
            raise RuntimeError("audit_path_must_be_owner_private")
        serialized = json.dumps(record, sort_keys=True, default=str).encode("utf-8")
        summary = {"record_sha256": hashlib.sha256(serialized).hexdigest()}
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
                raise RuntimeError("audit_file_invalid")
            os.write(fd, (json.dumps(summary, sort_keys=True) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)


def limits() -> dict:
    return {"max_calls_per_task": 2, "max_cost_per_task": 2, "max_total_calls": 2,
            "max_total_cost": 2, "max_in_flight": 1, "max_tasks": 1}


def audit() -> Audit:
    return Audit()


def dependencies() -> dict:
    base = Path(__file__).resolve().parent
    return {"files": [{"path": str(base / name),
                       "sha256": hashlib.sha256((base / name).read_bytes()).hexdigest()}
                      for name in ("requirements.lock", "runtime.json")]}


def options() -> dict:
    return {}


def _binary_choice(name: str, default: str) -> bool:
    value = os.environ.get(name, default)
    if value not in ("0", "1"):
        raise ValueError("invalid_" + name.lower())
    return value == "1"


def make_request() -> dict:
    intent = os.environ.get("JEV_ALPHA_INTENT", "inspect")
    if intent not in ("inspect", "summarize"):
        raise ValueError("invalid_jev_alpha_intent")
    item = os.environ.get("JEV_ALPHA_ITEM", "fixture-one")
    if item not in ("fixture-one", "fixture-two"):
        raise ValueError("invalid_jev_alpha_item")
    task_id = os.environ.get("JEV_ALPHA_TASK_ID", "alpha-baseline")
    if not task_id or len(task_id) > 64 or not task_id.isascii() or not all(
            character.isalnum() or character in "_-" for character in task_id):
        raise ValueError("invalid_jev_alpha_task_id")
    return {"task_id": task_id,
            "item": item, "intent": intent,
            "permit": _binary_choice("JEV_ALPHA_PERMIT", "1"),
            "approved": _binary_choice("JEV_ALPHA_APPROVED", "0")}


def main() -> int:
    request = make_request()
    return public_entry(request)
