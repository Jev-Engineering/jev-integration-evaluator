"""Strict serialization and local-only, bounded I/O helpers."""
from __future__ import annotations
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

class InputError(ValueError):
    """An input failed a documented invariant."""

def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")

def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()

def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def read_source(path: Path, reader):
    """Apply ``reader`` to one selected host source path.

    A native Windows read refusal becomes a fixed reason without the path.
    Elsewhere the operating-system error propagates unchanged.
    """
    try:
        return reader(path)
    except OSError as exc:
        if os.name != 'nt':
            raise
        from . import capabilities as cap
        denied = cap._windows_oserror_reason(exc) == 'access_denied'
        raise InputError('windows_source_read_access_denied' if denied
                         else 'windows_source_read_unavailable') from None

def finite(value: Any, name: str, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(f"{name} must be a finite number")
    if low is not None and value < low or high is not None and value > high:
        raise InputError(f"{name} is outside [{low}, {high}]")
    return float(value)

def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise InputError(f"Duplicate JSON key: {k}")
        result[k] = v
    return result

def loads(text: str) -> Any:
    def bad(v):
        raise InputError(f"Non-finite JSON value: {v}")
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=bad)

def read_json(path: str | Path, max_bytes: int = 64_000_000) -> Any:
    p = Path(path)
    if p.stat().st_size > max_bytes:
        raise InputError(f"Input exceeds {max_bytes} bytes: {p.name}")
    return loads(p.read_text(encoding="utf-8"))

def read_jsonl(path: str | Path, max_rows: int = 1_000_000) -> list[dict]:
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            if len(line) > 4_000_000 or len(rows) >= max_rows:
                raise InputError("JSONL exceeds configured size limit")
            row = loads(line)
            if not isinstance(row, dict):
                raise InputError(f"JSONL line {number} is not an object")
            rows.append(row)
    return rows

def atomic_text(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_symlink():
        raise InputError("Refusing to overwrite a symlink")
    fd, temp = tempfile.mkstemp(prefix=".jev-", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if p.exists():
            os.chmod(temp, p.stat().st_mode & 0o777)
        os.replace(temp, p)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def write_json(path: str | Path, data: Any) -> None:
    atomic_text(path, json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")

def safe_child(root: str | Path, relative: str) -> Path:
    base = Path(root).resolve()
    rp = Path(relative)
    if rp.is_absolute() or ".." in rp.parts or not relative or "\\" in relative:
        raise InputError("Expected a nonempty, normalized relative path")
    p = base.joinpath(rp)
    # Refuse every symlink component, including links which happen to stay in root.
    cursor = base
    for part in rp.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise InputError("Symlink traversal is not allowed")
    if not p.resolve().is_relative_to(base):
        raise InputError("Path escapes repository")
    return p

SECRET_KEY = re.compile(r"(?i)(api[_-]?key|secret|password|authorization|access[_-]?token|private[_-]?key)")
SECRET_TEXT = re.compile(r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|-----BEGIN[^\n]*PRIVATE KEY-----)")

def redact(value: Any) -> Any:
    """Best-effort redaction, not a DLP guarantee. Raw source is never logged by default."""
    if isinstance(value, dict):
        return {k: "[REDACTED]" if SECRET_KEY.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return SECRET_TEXT.sub("[REDACTED]", value)
    return value

def markdown(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
