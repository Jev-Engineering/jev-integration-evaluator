"""Normal console command for the independent registered-action application."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import uuid

from jev_integration_evaluator import capabilities as cap

from .host import public_entry, _native_acl_sha256


class Audit:
    def append(self, record) -> None:
        base = Path(os.environ["REGISTERED_ALPHA_AUDIT"])
        expected = os.environ.get('REGISTERED_ALPHA_OBSERVATION_ACL_SHA256')
        if (not base.is_absolute() or not expected
                or _native_acl_sha256(base.parent) != expected):
            raise RuntimeError("audit_path_must_be_owner_private")
        serialized = json.dumps(record, sort_keys=True, default=str).encode("utf-8")
        summary = {"record_sha256": hashlib.sha256(serialized).hexdigest()}
        path = base.parent / ('audit-' + str(uuid.uuid4()) + '.json')
        _, io_path = cap._windows_absolute_path(path)
        fd = cap._windows_create_private_file(io_path)
        try:
            os.write(fd, (json.dumps(summary, sort_keys=True) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        if _native_acl_sha256(path) != _native_acl_sha256(base.parent / 'delivery.lock'):
            raise RuntimeError('audit_file_acl_changed')


def _entrypoint_marker() -> None:
    path = Path(os.environ['REGISTERED_ALPHA_ENTRYPOINT'])
    expected = os.environ['REGISTERED_ALPHA_OBSERVATION_ACL_SHA256']
    if not path.is_absolute() or _native_acl_sha256(path.parent) != expected:
        raise RuntimeError('entrypoint_marker_invalid')
    _, io_path = cap._windows_absolute_path(path)
    fd = cap._windows_create_private_file(io_path)
    try:
        os.write(fd, b'entrypoint reached\n')
        os.fsync(fd)
    finally:
        os.close(fd)


def limits() -> dict:
    return {"max_calls_per_task": 2, "max_cost_per_task": 2, "max_total_calls": 2,
            "max_total_cost": 2, "max_in_flight": 1, "max_tasks": 2}


def audit() -> Audit:
    return Audit()


def dependencies() -> dict:
    base = Path(__file__).resolve().parent
    return {"files": [{"path": str(base / name),
                       "sha256": hashlib.sha256((base / name).read_bytes()).hexdigest()}
                      for name in ("requirements.lock", "runtime.json")]}


def options() -> dict:
    from .connected_authority import options as connected_options
    return connected_options()


def _binary_choice(name: str, default: str) -> bool:
    value = os.environ.get(name, default)
    if value not in ("0", "1"):
        raise ValueError("invalid_" + name.lower())
    return value == "1"


def make_request() -> dict:
    _entrypoint_marker()
    intent = os.environ.get("REGISTERED_ALPHA_INTENT", "inspect")
    if intent not in ("inspect", "summarize"):
        raise ValueError("invalid_jev_alpha_intent")
    item = os.environ.get("REGISTERED_ALPHA_ITEM", "fixture-one")
    if item not in ("fixture-one", "fixture-two"):
        raise ValueError("invalid_jev_alpha_item")
    task_id = os.environ.get("REGISTERED_ALPHA_TASK_ID", "alpha-baseline")
    if not task_id or len(task_id) > 64 or not task_id.isascii() or not all(
            character.isalnum() or character in "_-" for character in task_id):
        raise ValueError("invalid_jev_alpha_task_id")
    return {"task_id": task_id,
            "item": item, "intent": intent,
            "permit": _binary_choice("REGISTERED_ALPHA_PERMIT", "1"),
            "approved": _binary_choice("REGISTERED_ALPHA_APPROVED", "0")}


def main() -> int:
    request = make_request()
    return public_entry(request)
