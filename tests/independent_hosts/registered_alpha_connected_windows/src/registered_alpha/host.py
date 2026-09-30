"""A small existing application with real, externally visible registered actions.

The event file is the independent oracle. No template or verifier writes it.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
from threading import RLock
import time

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.runtime import HostGate


GUARD = RLock()
ACTIONS = {"inspect", "summarize"}


def _native_acl_sha256(path: Path) -> str:
    """Read the current owner and DACL through Win32 without shell or network."""
    display, _ = cap._windows_absolute_path(path)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    advapi.GetFileSecurityW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD))
    advapi.GetFileSecurityW.restype = wintypes.BOOL
    required = wintypes.DWORD()
    flags = 0x00000001 | 0x00000004
    advapi.GetFileSecurityW(display, flags, None, 0, ctypes.byref(required))
    if required.value == 0 or required.value > 65_536:
        raise RuntimeError('windows_acl_unavailable')
    buffer = ctypes.create_string_buffer(required.value)
    if not advapi.GetFileSecurityW(display, flags, buffer, len(buffer),
                                   ctypes.byref(required)):
        raise RuntimeError('windows_acl_unavailable')
    return hashlib.sha256(buffer.raw[:required.value]).hexdigest()


def _owned_path(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value and variable == 'REGISTERED_ALPHA_EFFECTS':
        probe = os.environ.get('REGISTERED_ALPHA_PROBE_EFFECTS_DIR')
        if probe:
            value = str(Path(probe) / ('effects-' + str(os.getpid()) + '.json'))
    if not value:
        raise RuntimeError("missing_" + variable.lower())
    path = Path(value)
    expected_acl = os.environ.get('REGISTERED_ALPHA_OBSERVATION_ACL_SHA256')
    if (not path.is_absolute() or not expected_acl or len(expected_acl) != 64
            or any(c not in '0123456789abcdef' for c in expected_acl)):
        raise RuntimeError("unsafe_" + variable.lower())
    try:
        cap._windows_check_directory_path(path.parent, purpose='output')
        if _native_acl_sha256(path.parent) != expected_acl:
            raise RuntimeError('private_directory_acl_changed')
    except cap.CapabilityError:
        raise RuntimeError("nonprivate_" + variable.lower())
    return path


def _events() -> list[dict]:
    directory = _owned_path("REGISTERED_ALPHA_EFFECTS").parent
    rows = []
    for path in sorted(directory.glob('effect-*.json')):
        if _native_acl_sha256(path) != _native_acl_sha256(directory / 'delivery.lock'):
            raise RuntimeError('effect_file_acl_changed')
        rows.append(json.loads(cap._windows_secure_input(path, 1_000_000)))
    if any(type(row) is not dict or set(row) != {"task_id", "action", "item"} for row in rows):
        raise RuntimeError("effect_file_invalid")
    return rows


def _record(request: dict, action: str) -> int:
    base = _owned_path("REGISTERED_ALPHA_EFFECTS")
    prefix = ('effect-' + str(os.getpid()) + '-' if
              os.environ.get('REGISTERED_ALPHA_PROBE_EFFECTS_DIR') else 'effect-')
    path = base.parent / (prefix + request['task_id'] + '.json')
    row = {"task_id": request["task_id"], "action": action, "item": request["item"]}
    _, io_path = cap._windows_absolute_path(path)
    fd = cap._windows_create_private_file(io_path)
    try:
        os.write(fd, (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    if _native_acl_sha256(path) != _native_acl_sha256(base.parent / 'delivery.lock'):
        raise RuntimeError('effect_file_acl_changed')
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
    _, io_path = cap._windows_absolute_path(ready)
    fd = cap._windows_create_private_file(io_path)
    try:
        os.write(fd, b"in-flight\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    deadline = time.monotonic() + 600
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
    if os.environ.get('REGISTERED_ALPHA_INTEGRATION'):
        marker = _owned_path('REGISTERED_ALPHA_INTEGRATION')
        if not marker.exists():
            _, io_path = cap._windows_absolute_path(marker)
            fd = cap._windows_create_private_file(io_path)
            try:
                os.write(fd, b'integration reachable\n')
                os.fsync(fd)
            finally:
                os.close(fd)
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
