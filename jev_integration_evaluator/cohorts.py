"""Stable task-level canary assignment shared by runtime and frozen monitoring."""
from __future__ import annotations
import hashlib
from .io import InputError, finite


def canary_arm(task_id: str, salt: str, fraction: float) -> str:
    if not isinstance(task_id, str) or not task_id or not isinstance(salt, str) or not salt:
        raise InputError("Canary assignment requires nonempty task and scope IDs")
    finite(fraction, "canary fraction", 0, 1)
    bucket = int(hashlib.sha256((salt + ":" + task_id).encode()).hexdigest()[:16], 16) / 2**64
    return "jev" if bucket < fraction else "baseline"
