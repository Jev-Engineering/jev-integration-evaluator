"""A small existing application with real, externally visible registered actions.

The event file is the independent oracle. No template or verifier writes it.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import stat
from threading import RLock
import time

from jev_integration_evaluator.runtime import HostGate


GUARD = RLock()
ACTIONS = {"inspect", "summarize"}


def _owned_path(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value and variable == "REGISTERED_ALPHA_EFFECTS":
        probe_directory = os.environ.get("REGISTERED_ALPHA_PROBE_EFFECTS_DIR")
        if probe_directory:
            value = str(Path(probe_directory) / ("effects-" + str(os.getpid()) + ".jsonl"))
    if not value:
        raise RuntimeError("missing_" + variable.lower())
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise RuntimeError("unsafe_" + variable.lower())
    if path.parent.stat().st_uid != os.getuid() or stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise RuntimeError("nonprivate_" + variable.lower())
    return path


def _events() -> list[dict]:
    path = _owned_path("REGISTERED_ALPHA_EFFECTS")
    if not path.exists():
        return []
    if path.stat().st_size > 1_000_000:
        raise RuntimeError("effect_file_oversize")
    with path.open("r", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if any(type(row) is not dict or set(row) != {"task_id", "action", "item"} for row in rows):
        raise RuntimeError("effect_file_invalid")
    return rows


def _record(request: dict, action: str) -> int:
    path = _owned_path("REGISTERED_ALPHA_EFFECTS")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
            raise RuntimeError("effect_file_invalid")
        fcntl.flock(fd, fcntl.LOCK_EX)
        if any(row["task_id"] == request["task_id"] for row in _events()):
            raise RuntimeError("duplicate_task_effect")
        row = {"task_id": request["task_id"], "action": "inspect-v2" if action == "inspect" else action, "item": request["item"]}
        os.write(fd, (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    return 0


def inspect_item(request: dict) -> int:
    if not host_validate(request, "inspect"):
        return host_blocked(request, "host_policy")
    _hold_if_requested()
    return _record(request, "inspect")


def summarize_item(request: dict) -> int:
    if not host_validate(request, "summarize") or request.get("approved") is not True:
        return host_blocked(request, "host_policy")
    _hold_if_requested()
    return _record(request, "summarize")


def _hold_if_requested() -> None:
    """Expose a live in-flight point with a finite timeout, not a fake health flag."""
    if os.environ.get("REGISTERED_ALPHA_HOLD") != "1":
        return
    ready = _owned_path("REGISTERED_ALPHA_READY")
    release = _owned_path("REGISTERED_ALPHA_RELEASE")
    fd = os.open(ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, b"in-flight\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    deadline = time.monotonic() + 15
    while not release.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("independent_host_release_missing")
        time.sleep(0.01)


def original_dispatch(request: dict) -> int:
    return inspect_item(request)


def select_registered_tool(request: dict) -> int:
    return original_dispatch(request)


def public_entry(request: dict) -> int:
    return select_registered_tool(request)


def host_runtime(request: dict):
    raise RuntimeError("runtime_owner_requires_explicit_startup")


def host_evidence(request: dict) -> dict:
    return {"item_kind": "fixture", "intent": request["intent"]}


def host_baseline_action(request: dict) -> str:
    return "inspect"


def host_registry(request: dict) -> dict:
    return {"inspect": inspect_item, "summarize": summarize_item}


def host_gate(request: dict, action: str) -> HostGate:
    return HostGate(tuple(sorted(ACTIONS)), hard_block=request.get("permit") is not True,
                    approval_required=action == "summarize",
                    approval_granted=request.get("approved") is True,
                    baseline_permitted=request.get("permit") is True)


def host_validate(request: dict, action: str) -> bool:
    return (request.get("permit") is True and action in ACTIONS
            and request.get("item") in {"fixture-one", "fixture-two"}
            and type(request.get("task_id")) is str and bool(request["task_id"]))


def host_blocked(request: dict, reason: str) -> int:
    return 2


def host_guard(request: dict) -> RLock:
    return GUARD


def host_observe(request: dict) -> dict:
    return {"count": len(_events())}


def host_postcondition(request: dict, result: int, observations: dict) -> bool:
    return (result == 0 and observations["after"]["count"]
            == observations["before"]["count"] + 1)
