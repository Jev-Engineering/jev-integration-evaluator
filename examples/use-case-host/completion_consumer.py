"""Host-owned raw completion effect for the offline E fixture.

An executor's success report is never the completion postcondition. The two
fresh files contain the actual state and an effect receipt for independent
readback. This fixture does not authorize retries or provider operation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat


def _raw(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _destination(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ValueError(name + " is required")
    path = Path(value.replace("{pid}", str(os.getpid())))
    if (not path.is_absolute() or path.exists() or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError("completion effect path must be fresh and unlinked")
    info = path.parent.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("completion effect parent must be owner-private")
    return path


def _write(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def commit(request: dict, *, host_approved: bool) -> dict:
    """Apply one finite approved close-and-label operation, then record bytes."""
    if (type(request) is not dict or type(request.get("task_id")) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request["task_id"])
            or request.get("operation") != "close_and_label"
            or host_approved is not True):
        raise ValueError("completion host permission or operation refused")
    state = _destination("E_RAW_STATE_PATH")
    receipt = _destination("E_EFFECT_RECEIPT_PATH")
    if state == receipt or state.parent != receipt.parent:
        raise ValueError("completion effects must use distinct private files")
    before = {"task_id": request["task_id"], "status": "open", "revision": 0,
              "labels": [], "unrequested": []}
    after = {"task_id": request["task_id"], "status": "closed", "revision": 2,
             "labels": ["verified"], "unrequested": []}
    effect = {"task_id": request["task_id"], "operation": "close_and_label",
              "before_sha256": hashlib.sha256(_raw(before)).hexdigest(),
              "after_sha256": hashlib.sha256(_raw(after)).hexdigest()}
    _write(state, _raw(after))
    _write(receipt, _raw(effect))
    return {"reported": "ok"}
