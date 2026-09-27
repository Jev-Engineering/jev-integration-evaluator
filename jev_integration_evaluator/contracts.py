"""Small shared helpers for locally frozen, content-addressed evidence contracts."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
from pathlib import Path
from .io import InputError, digest, read_json


def validate_contract(value: dict, kind: str) -> None:
    import jsonschema
    schema = read_json(Path(__file__).parent / "data" / (kind + ".schema.json"))
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError:
        # Schema errors can contain sensitive instances. Expose only the contract name.
        raise InputError("Invalid " + kind + " contract") from None


def seal(value: dict, field: str = "contract_digest") -> dict:
    result = copy.deepcopy(value)
    result.pop(field, None)
    result[field] = digest(result)
    return result


def verify(value: dict, field: str = "contract_digest", expected: str | None = None) -> None:
    if not isinstance(value, dict) or digest({k: v for k, v in value.items() if k != field}) != value.get(field):
        raise InputError("Evidence contract digest mismatch")
    if expected is not None and value[field] != expected:
        raise InputError("Evidence contract differs from the externally retained digest")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise InputError("Expected an explicitly timezone-aware timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InputError("Invalid timestamp") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise InputError("Timestamp must include timezone")
    return dt.astimezone(timezone.utc)
