"""Bounded, source-bound discovery and nominations; never target execution.

This is an additive discovery contract, not a replacement recipe validator or
semantic reviewer. A nomination grants no execution, mutation, or activation
scope. Secure descriptor-relative source reads currently require POSIX.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import asdict, dataclass, fields
import fnmatch
import hashlib
import io
import json
import keyword
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tokenize
from typing import Any, Iterator

import jsonschema

VERSION = "python-static-capabilities-v1"
MAX_INPUT_BYTES = 262_144
SOURCE_LANGUAGES = {
    ".py": "python", ".pyi": "python_stub", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go",
    ".rs": "rust", ".java": "java", ".cs": "csharp", ".c": "c",
    ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".rb": "ruby",
    ".lua": "lua", ".luau": "luau", ".kt": "kotlin",
    ".swift": "swift", ".php": "php", ".sh": "shell", ".ps1": "powershell",
    ".sql": "sql",
}
IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    ".pytest_cache", "dist", "build", "vendor", "target", ".next", ".idea",
    ".mypy_cache", ".tox", ".nox",
})
CONFIG_NAMES = frozenset({
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "tsconfig.json", "pytest.ini", "tox.ini", "conftest.py", "Dockerfile",
    "docker-compose.yml", "compose.yaml", "Cargo.toml", "go.mod",
    "AGENTS.md", "README.md", "SETUP_PROMPT.md",
})
SENSITIVE = re.compile(r"(?i)(^\.env(?:\.|$)|credential|secret|id_rsa|id_ed25519|\.pem$|\.key$|\.p12$)")
HEX = re.compile(r"[0-9a-f]{64}\Z")


class CapabilityError(ValueError):
    """Stable redacted diagnostics; sensitive exception causes are suppressed."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise CapabilityError("invalid_json_value") from None


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return _hash(_json(value))


@dataclass(frozen=True)
class DiscoveryPolicy:
    """Caller-supplied bounds and exclusions, never read from target config."""

    max_entries: int = 20_000
    max_files: int = 1_000
    max_file_bytes: int = 1_048_576
    max_total_bytes: int = 16_777_216
    max_symbols: int = 2_000
    max_ast_nodes: int = 50_000
    max_depth: int = 16
    max_report_bytes: int = 4_194_304
    exclude: tuple[str, ...] = ()
    hard_real_time: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ceilings = {
            "max_entries": 100_000, "max_files": 10_000,
            "max_file_bytes": 4_194_304, "max_total_bytes": 67_108_864,
            "max_symbols": 10_000, "max_ast_nodes": 100_000,
            "max_depth": 32, "max_report_bytes": 16_777_216,
        }
        for name, ceiling in ceilings.items():
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise CapabilityError("invalid_discovery_policy")
        for name in ("exclude", "hard_real_time"):
            values = getattr(self, name)
            if type(values) is not tuple or len(values) > 100:
                raise CapabilityError("invalid_discovery_policy")
            if any(type(v) is not str or not v or len(v) > 512 or "\x00" in v
                   or "\\" in v or v.startswith("/") or ".." in v.split("/")
                   for v in values):
                raise CapabilityError("invalid_discovery_policy")

    @classmethod
    def from_json(cls, data: Any) -> DiscoveryPolicy:
        if type(data) is not dict or set(data) - {f.name for f in fields(cls)}:
            raise CapabilityError("invalid_discovery_policy")
        data = dict(data)
        for name in ("exclude", "hard_real_time"):
            if name in data:
                if type(data[name]) is not list:
                    raise CapabilityError("invalid_discovery_policy")
                data[name] = tuple(data[name])
        return cls(**data)


def _schema(name: str, value: Any) -> None:
    path = Path(__file__).parent / "data" / (name + ".schema.json")
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        # The exception text can contain the entire proposal or private source.
        raise CapabilityError("invalid_" + name.replace("-", "_")) from None


def _safe_rel(value: str) -> bool:
    if not value or "\\" in value or "\x00" in value or len(value) > 1024:
        return False
    p = PurePosixPath(value)
    return not p.is_absolute() and str(p) == value and all(
        x not in ("", ".", "..") for x in p.parts)


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, p.rstrip("/")) for p in patterns)


def _open_directory(path: Path) -> tuple[Path, int]:
    """Open every absolute path component without following symlinks.

    The descriptor, not a subsequently resolved pathname, owns the traversal.
    This is filesystem-safe preparation, not an OS execution sandbox.
    """
    if (os.name != "posix" or os.open not in os.supports_dir_fd
            or not hasattr(os, "O_NOFOLLOW") or os.listdir not in os.supports_fd):
        raise CapabilityError("unsupported_secure_filesystem")
    absolute = Path(os.path.abspath(path))
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in absolute.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        return absolute, fd
    except BaseException:
        os.close(fd)
        raise


def _secure_root(repo: str | Path) -> tuple[Path, int, os.stat_result]:
    try:
        root = Path(repo).absolute()
        if root.is_symlink():
            raise CapabilityError("symlink_repository_root")
        root, fd = _open_directory(root)
        try:
            ident = os.fstat(fd)
        except BaseException:
            os.close(fd)
            raise
        return root, fd, ident
    except OSError as exc:
        raise CapabilityError("repository_unavailable") from None


def _read_at(parent: int, name: str, limit: int) -> tuple[bytes, int]:
    fd = -1
    try:
        # O_NONBLOCK prevents a raced FIFO from blocking before fstat rejects it.
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise CapabilityError("non_regular_file")
        if before.st_nlink != 1:
            raise CapabilityError("hardlink_excluded")
        if before.st_size > limit:
            raise CapabilityError("file_byte_budget")
        parts = []
        remaining = limit + 1
        while remaining:
            part = os.read(fd, min(remaining, 65_536))
            if not part:
                break
            parts.append(part)
            remaining -= len(part)
        raw = b"".join(parts)
        after = os.fstat(fd)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                              s.st_ctime_ns, s.st_mode)
        if identity(before) != identity(after) or identity(after) != identity(current):
            raise CapabilityError("source_changed_during_read")
        if len(raw) > limit:
            raise CapabilityError("file_byte_budget")
        return raw, stat.S_IMODE(before.st_mode)
    except OSError as exc:
        raise CapabilityError("source_unavailable") from None
    finally:
        if fd >= 0:
            os.close(fd)


def _walk(fd: int, policy: DiscoveryPolicy, notes: list[dict],
          counts: Counter, prefix: str = "", depth: int = 0) -> Iterator[tuple[str, bytes, int]]:
    if depth > policy.max_depth:
        notes.append({"path": prefix, "reason": "directory_depth_budget"})
        return
    # scandir(fd) streams directory entries; do not materialize an unbounded list.
    try:
        with os.scandir(fd) as entries:
            names = []
            for entry in entries:
                counts["entries"] += 1
                if counts["entries"] > policy.max_entries:
                    notes.append({"path": prefix, "reason": "entry_budget"})
                    counts["stopped"] = 1
                    return
                names.append(entry.name)
    except OSError:
        notes.append({"path": prefix, "reason": "directory_unavailable"})
        return
    for name in sorted(names):
        if counts["stopped"]:
            return
        path = f"{prefix}/{name}" if prefix else name
        if SENSITIVE.search(name) or _matches(path, policy.exclude):
            counts["excluded"] += 1
            continue
        if not _safe_rel(path):
            notes.append({"path": "", "reason": "unsupported_path"})
            continue
        try:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                notes.append({"path": path, "reason": "symlink_excluded"})
                continue
            if stat.S_ISDIR(info.st_mode):
                if name in IGNORED_DIRS or name.endswith(".egg-info"):
                    counts["excluded"] += 1
                    continue
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=fd)
                try:
                    if (os.fstat(child).st_dev, os.fstat(child).st_ino) != (info.st_dev, info.st_ino):
                        raise CapabilityError("source_changed_during_read")
                    yield from _walk(child, policy, notes, counts, path, depth + 1)
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(info.st_mode):
                notes.append({"path": path, "reason": "non_regular_file"})
                continue
            ext = PurePosixPath(path).suffix.lower()
            if ext not in SOURCE_LANGUAGES and name not in CONFIG_NAMES and not path.startswith(".github/workflows/"):
                continue
            if counts["files"] >= policy.max_files:
                notes.append({"path": path, "reason": "file_count_budget"})
                counts["stopped"] = 1
                return
            remaining = policy.max_total_bytes - counts["bytes"]
            if remaining <= 0:
                notes.append({"path": path, "reason": "total_byte_budget"})
                counts["stopped"] = 1
                return
            raw, mode = _read_at(fd, name, min(policy.max_file_bytes, remaining))
            counts["files"] += 1
            counts["bytes"] += len(raw)
            yield path, raw, mode
        except CapabilityError as exc:
            notes.append({"path": path, "reason": exc.code})
        except OSError:
            notes.append({"path": path, "reason": "source_unavailable"})


def _defs(tree: ast.AST, prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, ast.AST, bool]]:
    def visit(node: ast.AST, scope: tuple[str, ...], module_level: bool) -> Iterator[tuple[str, ast.AST, bool]]:
        is_scope = isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield ".".join(scope + (node.name,)), node, module_level
        following = scope + (node.name,) if is_scope else scope
        for child in ast.iter_child_nodes(node):
            yield from visit(child, following, isinstance(node, ast.Module))
    yield from visit(tree, prefix, False)


def _body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body.pop(0)
    return body


def _parameter(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    a = node.args
    positional = a.posonlyargs + a.args
    if len(positional) == 1 and not (a.defaults or a.kwonlyargs or a.vararg or a.kwarg):
        return positional[0].arg
    return None


def _tail(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    body, param = _body(node), _parameter(node)
    if param is None or len(body) != 1 or not isinstance(body[0], ast.Return):
        return None
    value = body[0].value
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id != param and len(value.args) == 1
            and isinstance(value.args[0], ast.Name) and value.args[0].id == param
            and not value.keywords):
        return value.func.id
    return None


def _deterministic(node: ast.FunctionDef | ast.AsyncFunctionDef,
                   unique: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
                   bindings: Counter, resolve_module_calls: bool,
                   visited: frozenset[str] = frozenset()) -> bool:
    """Conservative exclusion, not proof of program purity or equivalence."""
    if node.name in visited or node.decorator_list:
        return False
    body = _body(node)
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    expr = body[0].value
    if expr is None:
        return True
    allowed = (ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp,
               ast.BoolOp, ast.Compare, ast.IfExp, ast.Tuple, ast.List, ast.Dict,
               ast.Set, ast.operator, ast.unaryop, ast.boolop, ast.cmpop)
    if all(isinstance(x, allowed) for x in ast.walk(expr)):
        return True
    # Enclosing locals or dynamic module namespaces can shadow any callee.
    if not resolve_module_calls:
        return False
    callee = _tail(node)
    # These are deterministic-operation exclusions, not an assertion that the
    # builtin's argument is pure. A local definition is inspected instead.
    if callee in {"abs", "all", "any", "bool", "float", "int", "len", "max",
                  "min", "round", "sorted", "str", "sum", "tuple"} and not bindings[callee]:
        return True
    return bool(callee in unique and _deterministic(
        unique[callee], unique, bindings, True, visited | {node.name}))


def _top_bindings(tree: ast.Module) -> Counter:
    """Count module bindings, including definition-time expression writes."""
    counts: Counter = Counter()

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Lambda):
            # Defaults execute in the enclosing scope; the body has its own
            # locals and does not execute when the lambda is constructed.
            for expr in [*node.args.defaults, *(x for x in node.args.kw_defaults if x is not None)]:
                visit(expr)
            return
        if isinstance(node, ast.comprehension):
            # Iteration targets are comprehension-local. Assignment expressions
            # in filters/results still bind in the enclosing scope.
            visit(node.iter)
            for expr in node.ifs:
                visit(expr)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            counts[node.name] += 1
            for expr in [*node.decorator_list, *node.args.defaults,
                         *(x for x in node.args.kw_defaults if x is not None),
                         *(a.annotation for a in [*node.args.posonlyargs, *node.args.args,
                                                   *node.args.kwonlyargs,
                                                   *([node.args.vararg] if node.args.vararg else []),
                                                   *([node.args.kwarg] if node.args.kwarg else [])]
                           if a.annotation is not None)]:
                visit(expr)
            if node.returns is not None:
                visit(node.returns)
            return
        if isinstance(node, ast.ClassDef):
            counts[node.name] += 1
            # Class execution may rebind globals; conservatively do not qualify
            # flat-module recipes in any module containing a class (see below).
            for expr in [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]:
                visit(expr)
            return
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                counts[alias.asname or alias.name.split(".")[0]] += 1
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            counts[node.id] += 1
        if isinstance(node, ast.ExceptHandler) and node.name:
            counts[node.name] += 1
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            counts[node.name] += 1
        if isinstance(node, ast.MatchMapping) and node.rest:
            counts[node.rest] += 1
        for child in ast.iter_child_nodes(node):
            visit(child)
    for stmt in tree.body:
        visit(stmt)
    return counts


def _module_scope_nodes(node: ast.AST) -> Iterator[ast.AST]:
    """Include conditional module declarations, but do not enter local scopes."""
    yield node
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
        return
    for child in ast.iter_child_nodes(node):
        yield from _module_scope_nodes(child)


def _analyze_python(path: str, raw: bytes, policy: DiscoveryPolicy) -> tuple[list[dict], list[dict], list[dict]]:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        if encoding.lower().replace("_", "-") not in ("utf-8", "utf8") or raw.startswith(b"\xef\xbb\xbf"):
            raise CapabilityError("unsupported_source_encoding")
        text = raw.decode("utf-8")
        if b"\x00" in raw or re.search(r"\r(?!\n)", text):
            raise CapabilityError("unsupported_source_encoding")
        tree = ast.parse(text, filename="<bounded-source>")
        for count, _ in enumerate(ast.walk(tree), 1):
            if count > policy.max_ast_nodes:
                raise CapabilityError("ast_node_budget")
        definitions = list(_defs(tree))
        duplicates = Counter(name for name, _, _ in definitions)
        bindings = _top_bindings(tree)
        unique = {node.name: node for _, node, top in definitions
                  if top and bindings[node.name] == 1}
        module_nodes = list(_module_scope_nodes(tree))
        unsafe_module = any(isinstance(n, ast.ClassDef) for n in module_nodes) or any(
            isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
            for n in module_nodes) or any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in ("eval", "exec", "globals", "locals", "setattr", "__import__")
            for n in ast.walk(tree))
        module_name = Path(path).stem
        supported_module = (re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*\.py", path) is not None
                            and not keyword.iskeyword(module_name)
                            and module_name not in set(sys.stdlib_module_names) | {
                                "jev_integration_evaluator", "jsonschema", "yaml"})
        results = []
        for qualified, node, top in definitions:
            selector = path + "::" + qualified
            eligibility = "unknown"
            reasons = []
            if _matches(selector, policy.hard_real_time):
                eligibility, reasons = "ineligible", ["hard_real_time_exclusion"]
            elif _deterministic(node, unique, bindings, top and not unsafe_module):
                eligibility, reasons = "ineligible", ["deterministic_operation_shape"]
            callee = _tail(node)
            supported = (top and type(node) is ast.FunctionDef and not node.decorator_list
                         and not getattr(node, "type_params", []) and callee is not None
                         and callee != node.name and duplicates[qualified] == 1
                         and bindings[node.name] == 1 and callee in unique
                         and type(unique[callee]) is ast.FunctionDef
                         and not unique[callee].decorator_list
                         and not any(isinstance(n, (ast.Yield, ast.YieldFrom, ast.Await))
                                     for n in ast.walk(unique[callee]))
                         and _parameter(unique[callee]) is not None
                         and callee not in ("eval", "exec", "__import__")
                         and supported_module and not unsafe_module)
            shape = "module-tail-call-v1-preflight" if supported else "unsupported_or_unresolved"
            if not supported:
                reasons.append("legacy_recipe_preconditions_not_established")
            if duplicates[qualified] != 1 or (qualified == node.name and bindings[node.name] != 1):
                reasons.append("ambiguous_symbol")
            source = {
                "file": path, "qualified_symbol": qualified,
                "start_line": node.lineno, "end_line": node.end_lineno,
                "file_sha256": _hash(raw),
                "ast_sha256": _hash(ast.dump(node, include_attributes=False).encode("utf-8")),
            }
            results.append({
                "seam_id": _digest([VERSION, source]), "source": source,
                "kind": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                "module_level": top, "shape": shape, "eligibility": eligibility,
                "semantic_suitability": "unreviewed", "binding_review": "not_performed",
                "execution_qualified": False, "reasons": reasons,
            })
        registries = []
        for stmt in tree.body:
            if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name) or not isinstance(stmt.value, ast.Dict):
                continue
            keys, values = stmt.value.keys, stmt.value.values
            if keys and all(isinstance(k, ast.Constant) and type(k.value) is str for k in keys) and all(isinstance(v, ast.Name) for v in values):
                name = stmt.targets[0].id
                labels = [k.value for k in keys]
                if bindings[name] == 1 and len(set(labels)) == len(labels) and all(v.id in unique for v in values):
                    registries.append({"file": path, "symbol": name,
                                       "start_line": stmt.lineno, "end_line": stmt.end_lineno,
                                       "file_sha256": _hash(raw), "entry_count": len(keys),
                                       "status": "static_possibility_not_binding_review"})
        return results, registries, []
    except CapabilityError as exc:
        return [], [], [{"path": path, "reason": exc.code}]
    except (SyntaxError, UnicodeError, ValueError, RecursionError):
        return [], [], [{"path": path, "reason": "python_parse_unavailable"}]


def discover_repository(repo: str | Path, policy: DiscoveryPolicy | None = None) -> dict:
    policy = policy or DiscoveryPolicy()
    if not isinstance(policy, DiscoveryPolicy):
        raise CapabilityError("invalid_discovery_policy")
    root, fd, root_stat = _secure_root(repo)
    notes: list[dict] = []
    counts: Counter = Counter()
    records, seams, registries = [], [], []
    try:
        for path, raw, mode in _walk(fd, policy, notes, counts):
            language = SOURCE_LANGUAGES.get(PurePosixPath(path).suffix.lower(), "configuration")
            parser = "not_requested"
            if language == "python":
                found, possible, issues = _analyze_python(path, raw, policy)
                parser = "unavailable" if issues else "python_ast"
                notes.extend(issues)
                if len(seams) + len(found) > policy.max_symbols:
                    notes.append({"path": path, "reason": "symbol_budget"})
                else:
                    seams.extend(found)
                    registries.extend(possible)
            elif language != "configuration":
                notes.append({"path": path, "reason": "parser_not_used_by_this_contract"})
            records.append({"file": path, "sha256": _hash(raw), "mode": mode,
                            "language": language, "parser": parser,
                            "line_count": len(raw.splitlines()),
                            "configuration_sighting": PurePosixPath(path).name in CONFIG_NAMES or path.startswith(".github/workflows/"),
                            "test_sighting": any(p.startswith("test") or p in ("tests", "__tests__") for p in PurePosixPath(path).parts)})
        current = root.stat()
        if (current.st_dev, current.st_ino) != (root_stat.st_dev, root_stat.st_ino):
            raise CapabilityError("repository_identity_changed")
    finally:
        os.close(fd)
    # A second descriptor-relative pass checks the full bounded byte set and
    # enumeration, not just the selected function. No target command is invoked.
    _, check_fd, check_stat = _secure_root(root)
    verify_notes: list[dict] = []
    verify_counts: Counter = Counter()
    try:
        verify = [(p, _hash(b), m) for p, b, m in _walk(check_fd, policy, verify_notes, verify_counts)]
    finally:
        os.close(check_fd)
    if ((check_stat.st_dev, check_stat.st_ino) != (root_stat.st_dev, root_stat.st_ino)
            or verify != [(r["file"], r["sha256"], r["mode"]) for r in records]
            or any(n["reason"] == "source_changed_during_read" for n in notes + verify_notes)):
        raise CapabilityError("source_changed_during_discovery")
    notes.extend(n for n in verify_notes if n not in notes)
    paths = {r["file"] for r in records}
    layouts = set()
    for path in paths:
        if not path.endswith(".py"):
            continue
        parts = path.split("/")
        if len(parts) == 1:
            layouts.add("flat_module")
        elif parts[0] == "src":
            layouts.add("src_layout_sighting")
        elif "/".join(parts[:-1]) + "/__init__.py" in paths:
            layouts.add("regular_package_sighting")
        else:
            layouts.add("namespace_or_directory_unresolved")
    if notes:
        outcome = "incomplete_analysis"
    elif not seams:
        outcome = "no_candidates_discovered"
    elif all(s["eligibility"] == "ineligible" for s in seams):
        outcome = "deterministic_rejection"
    elif not any(s["shape"] == "module-tail-call-v1-preflight" and s["eligibility"] != "ineligible" for s in seams):
        outcome = "unsupported_or_unresolved"
    else:
        outcome = "review_required"
    result = {
        "schema_version": "1.0", "discovery_version": VERSION,
        "engine_sha256": _digest({
            "source": _hash(Path(__file__).read_bytes()),
            "schemas": {name: _hash((Path(__file__).parent / "data" / (name + ".schema.json")).read_bytes())
                        for name in ("admitted-nomination", "candidate-nomination", "repository-capabilities")},
        }),
        "parser_identity": f"{sys.implementation.name}-{sys.version_info.major}.{sys.version_info.minor}-ast",
        "repository_identity": _digest([str(root), root_stat.st_dev, root_stat.st_ino]),
        "policy": json.loads(_json(asdict(policy))),
        "snapshot_scope": "bounded_source_and_configuration_not_full_repository",
        "snapshot_sha256": _digest(records), "files": records,
        "layouts": sorted(layouts), "seams": seams, "registry_possibilities": registries,
        "coverage": {"entries_considered": min(counts["entries"], policy.max_entries),
                     "files_read": len(records), "bytes_read": counts["bytes"],
                     "excluded_entries": counts["excluded"], "complete_within_policy": not notes,
                     "limitations": sorted(notes, key=lambda n: (n["path"], n["reason"]))},
        "discovery_outcome": outcome,
        "authorization": {"execution": False, "mutation": False, "egress": False, "activation": False},
    }
    result["report_sha256"] = _digest(result)
    if len(_json(result)) > policy.max_report_bytes:
        raise CapabilityError("report_byte_budget")
    _schema("repository-capabilities", result)
    return result


def admit_nomination(repo: str | Path, nomination: dict, *,
                     expected_report_sha256: str,
                     policy: DiscoveryPolicy | None = None) -> dict:
    """Re-read source with caller policy; agent data cannot modify that policy."""
    if len(_json(nomination)) > MAX_INPUT_BYTES:
        raise CapabilityError("nomination_byte_budget")
    _schema("candidate-nomination", nomination)
    if type(expected_report_sha256) is not str or not HEX.fullmatch(expected_report_sha256):
        raise CapabilityError("invalid_report_anchor")
    report = discover_repository(repo, policy)
    if (report["report_sha256"] != expected_report_sha256
            or nomination["report_sha256"] != expected_report_sha256):
        raise CapabilityError("stale_report_or_policy")
    selected = [s for s in report["seams"] if s["seam_id"] == nomination["seam_id"]]
    if len(selected) != 1:
        raise CapabilityError("unknown_or_ambiguous_seam")
    seam = selected[0]
    if seam["source"] != nomination["source"]:
        raise CapabilityError("source_anchor_mismatch")
    if "ambiguous_symbol" in seam["reasons"]:
        raise CapabilityError("ambiguous_symbol")
    if seam["eligibility"] == "ineligible":
        raise CapabilityError(seam["reasons"][0])
    by_file = {f["file"]: f for f in report["files"]}
    if not any(e["file"] == seam["source"]["file"] and e["start_line"] <= seam["source"]["start_line"]
               and e["end_line"] >= seam["source"]["end_line"] for e in nomination["evidence"]):
        raise CapabilityError("missing_seam_evidence")
    for evidence in nomination["evidence"]:
        if not _safe_rel(evidence["file"]) or evidence["file"] not in by_file:
            raise CapabilityError("excluded_or_unknown_evidence")
        record = by_file[evidence["file"]]
        if (evidence["file_sha256"] != record["sha256"]
                or not 1 <= evidence["start_line"] <= evidence["end_line"] <= record["line_count"]):
            raise CapabilityError("evidence_anchor_mismatch")
    result = {
        "schema_version": "1.0", "discovery_version": VERSION,
        "candidate_id": "JEV-NOM-" + _digest([seam["source"], nomination["pattern"]])[:24].upper(),
        "report_sha256": report["report_sha256"], "nomination_sha256": _digest(nomination),
        "source": seam["source"], "pattern": nomination["pattern"],
        "proposer": nomination["proposer"], "rationale": nomination["rationale"],
        "evidence": nomination["evidence"], "shape": seam["shape"],
        "status": "nominated_pending_semantic_and_binding_review",
        "semantic_review": "not_performed", "benefit": None,
        "execution_qualified": False,
        "analysis_complete_within_policy": report["coverage"]["complete_within_policy"],
        "authorization": {"execution": False, "mutation": False, "egress": False, "activation": False},
    }
    _schema("admitted-nomination", result)
    return result


def _load(path: Path, *, max_bytes: int = MAX_INPUT_BYTES) -> Any:
    if type(max_bytes) is not int or not 1 <= max_bytes <= 16_777_217:
        raise CapabilityError("input_byte_budget")
    directory_fd = -1
    try:
        try:
            _, directory_fd = _open_directory(path.parent)
            # Reuse source identity checks and nonblocking, no-follow reads.
            raw, _ = _read_at(directory_fd, path.name, max_bytes)
        except CapabilityError as exc:
            if exc.code == "file_byte_budget":
                raise CapabilityError("input_byte_budget") from None
            if exc.code == "unsupported_secure_filesystem":
                raise
            raise CapabilityError("input_unavailable_or_invalid") from None
        def pairs(items: list[tuple[str, Any]]) -> dict:
            obj: dict = {}
            for key, value in items:
                if key in obj:
                    raise CapabilityError("duplicate_json_key")
                obj[key] = value
            return obj
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(CapabilityError("non_finite_json")))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, CapabilityError):
            raise
        raise CapabilityError("input_unavailable_or_invalid") from None
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)


def _write_out(path: Path, repo: Path, value: dict) -> None:
    root = repo.resolve()
    parent = Path(os.path.abspath(path.parent))
    if parent == root or root in parent.parents:
        raise CapabilityError("output_must_be_outside_repository")
    directory_fd = fd = -1
    try:
        _, directory_fd = _open_directory(parent)
        # Relative open prevents a raced parent-path symlink from redirecting
        # the write. Existing outputs and symlinks are never overwritten.
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory_fd)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(_json(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory_fd)
    except OSError as exc:
        # Do not overwrite/delete another writer's output after a failure.
        raise CapabilityError("output_unavailable_or_exists") from None
    finally:
        if fd >= 0:
            os.close(fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("discover", "nominate"))
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--nomination", type=Path)
    parser.add_argument("--report-sha256")
    args = parser.parse_args(argv)
    try:
        policy = DiscoveryPolicy()
        if args.policy:
            external = args.policy.resolve(strict=True)
            root = args.repo.resolve(strict=True)
            if external == root or root in external.parents:
                raise CapabilityError("policy_must_be_external")
            policy = DiscoveryPolicy.from_json(_load(args.policy))
        if args.operation == "discover":
            if args.nomination or args.report_sha256:
                raise CapabilityError("unexpected_nomination_arguments")
            result = discover_repository(args.repo, policy)
        else:
            if not args.nomination or not args.report_sha256:
                raise CapabilityError("nomination_and_report_anchor_required")
            result = admit_nomination(args.repo, _load(args.nomination),
                                      expected_report_sha256=args.report_sha256, policy=policy)
        _write_out(args.out, args.repo, result)
        print(json.dumps({"status": "written", "artifact_sha256": _digest(result)}))
        return 0
    except CapabilityError as exc:
        print(json.dumps({"status": "blocked", "reason": exc.code}), file=sys.stderr)
        return 2
    except OSError:
        print(json.dumps({"status": "blocked", "reason": "filesystem_unavailable"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
