"""Bounded local reconnaissance, AST facts, conservative call graph, decision discovery.

Parsing is not executing. Python and JS/TS have real AST paths. Other text languages
produce explicitly unverified review leads, not authoritative semantic recommendations.
"""
from __future__ import annotations
import ast
import fnmatch
import hashlib
import json
import os
import re
import subprocess
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any
from .io import InputError, canonical, digest, file_hash, safe_child, redact
from .patterns import PATTERNS, roles_for_calls

LANGUAGES = {".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript", ".go": "go", ".rs": "rust", ".java": "java", ".cs": "csharp", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".rb": "ruby", ".lua": "lua", ".luau": "luau", ".kt": "kotlin", ".swift": "swift", ".php": "php", ".sh": "shell", ".ps1": "powershell", ".sql": "sql"}
IGNORE_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build", "vendor", "target", ".next", ".idea", ".mypy_cache"}
CONFIG_NAMES = {"pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "go.mod", "Dockerfile", "docker-compose.yml", "compose.yaml", "AGENTS.md", "README.md", "SETUP_PROMPT.md"}
SENSITIVE = re.compile(r"(?i)(^\.env(?:\.|$)|credential|secret|id_rsa|id_ed25519|\.pem$|\.key$|\.p12$)")


def _own_nodes(node):
    """Do not attribute nested function bodies to their enclosing function."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        if current is not node and isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(current))))


def _call_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _call_name(node.value) + "." + node.attr
    if isinstance(node, ast.Subscript):
        return _call_name(node.value) + "[" + (_call_name(node.slice) or "dynamic") + "]"
    if isinstance(node, ast.Call):
        return _call_name(node.func) + "()"
    return "<dynamic>"


def _python(source: str, file: str) -> tuple[list[dict], list[str], list[dict]]:
    tree = ast.parse(source, filename=file)
    imports = []
    aliases = {}
    for n in tree.body:
        if isinstance(n, ast.Import):
            for a in n.names:
                imports.append(a.name)
                aliases[a.asname or a.name.split(".")[0]] = a.name
        elif isinstance(n, ast.ImportFrom):
            mod = "." * n.level + (n.module or "")
            imports.append(mod)
            for a in n.names:
                aliases[a.asname or a.name] = mod + "." + a.name
    functions = []
    def visit(n, scope):
        if isinstance(n, ast.ClassDef):
            scope = scope + [n.name]
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbol = ".".join(scope + [n.name])
            f = {"symbol": symbol, "start_line": n.lineno, "end_line": n.end_lineno,
                 "calls": [], "branches": [], "loops": [], "exceptions": [], "returns": [],
                 "literals": [], "identifiers": [], "attributes": [], "operators": [],
                 "dataflow": [], "parser": "python_ast", "import_aliases": aliases}
            for x in _own_nodes(n):
                if isinstance(x, ast.Call):
                    name = _call_name(x.func)
                    first = name.split(".")[0]
                    resolved = aliases.get(first, first) + name[len(first):]
                    f["calls"].append({"name": name, "resolved_name": resolved, "line": x.lineno})
                if isinstance(x, ast.Name): f["identifiers"].append(x.id)
                if isinstance(x, ast.Attribute): f["attributes"].append(x.attr)
                if isinstance(x, (ast.If, ast.IfExp, ast.Match)): f["branches"].append(x.lineno)
                if isinstance(x, (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.GeneratorExp)): f["loops"].append(x.lineno)
                if isinstance(x, (ast.Try, ast.ExceptHandler, ast.Raise)): f["exceptions"].append(x.lineno)
                if isinstance(x, ast.Return): f["returns"].append({"line": x.lineno, "kind": type(x.value).__name__})
                if isinstance(x, ast.Constant) and isinstance(x.value, str): f["literals"].append({"value": x.value[:2000], "line": x.lineno})
                if isinstance(x, (ast.BinOp, ast.Compare, ast.BoolOp, ast.Subscript)): f["operators"].append(type(x).__name__)
                if isinstance(x, (ast.Assign, ast.AnnAssign)) and x.value is not None:
                    targets = x.targets if isinstance(x, ast.Assign) else [x.target]
                    f["dataflow"].append({"target": ",".join(_call_name(t) for t in targets),
                        "calls": [_call_name(c.func) for c in _own_nodes(x.value) if isinstance(c, ast.Call)],
                        "reads": [c.id for c in _own_nodes(x.value) if isinstance(c, ast.Name)], "line": x.lineno})
            functions.append(f)
            scope = scope + [n.name]
        for child in ast.iter_child_nodes(n):
            visit(child, scope)
    visit(tree, [])
    statements=[n for n in tree.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Import,ast.ImportFrom))]
    if statements:
        synthetic=ast.FunctionDef(name="<module>",args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=statements,decorator_list=[])
        synthetic.lineno=min(n.lineno for n in statements)
        synthetic.end_lineno=max(n.end_lineno for n in statements)
        before=len(functions)
        visit(synthetic,[])
        functions=functions[:before]+functions[before:before+1]
    return functions, imports, []


def _typescript(source: str, file: str):
    helper = Path(__file__).parent / "data" / "typescript_ast.cjs"
    # cwd is trusted skill tooling, NOT the target. Target Node plugins are never loaded.
    run = subprocess.run(["node", str(helper)], input=json.dumps({"file": file, "source": source}),
                         text=True, capture_output=True, timeout=12, cwd=helper.parent)
    if run.returncode:
        raise InputError("TypeScript AST unavailable (trusted tooling needs Node + TypeScript >=5,<7)")
    data = json.loads(run.stdout)
    if data["errors"]:
        raise InputError("TypeScript syntax diagnostics prevent a trusted AST result")
    return data["functions"], data["imports"], data["errors"]


def _fallback(source: str, file: str):
    # Explicitly lexical: retain line offsets, erase comments, then collect only review leads.
    masked = re.sub(r"/\*.*?\*/", lambda m: "\n" * m[0].count("\n"), source, flags=re.S)
    masked = re.sub(r"(?m)//[^\n]*|^[ \t]*#[^\n]*", "", masked)
    calls = [{"name": m[1], "line": masked.count("\n", 0, m.start()) + 1}
             for m in re.finditer(r"\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(", masked)
             if m[1] not in ("if", "for", "while", "switch", "catch")]
    nlines = max(1, len(source.splitlines()))
    return [{"symbol": "<file-review>", "start_line": 1, "end_line": nlines,
             "calls": calls, "branches": [1] if re.search(r"\b(if|switch|match)\b", masked) else [],
             "loops": [1] if re.search(r"\b(for|while|loop)\b", masked) else [],
             "exceptions": [1] if re.search(r"\b(try|catch|rescue)\b", masked) else [],
             "returns": [], "literals": [], "identifiers": [], "attributes": [], "operators": [],
             "dataflow": [], "parser": "lexical_review_only"}], [], []


def _patterns(f: dict) -> tuple[list[str], dict, str | None]:
    calls = f["calls"]
    roles = roles_for_calls(calls + [{"name": c["resolved_name"], "line": c["line"]} for c in calls if c.get("resolved_name") != c["name"] and c.get("resolved_name")])
    has = lambda role: bool(roles.get(role))
    names = " ".join(c["name"].lower() for c in calls)
    ids = " ".join(f["identifiers"] + f["attributes"] + [f["symbol"]]).lower()
    structure = bool(f["branches"] or f["loops"] or f["dataflow"] or f["returns"])
    pats = []
    if has("model") and has("tool"): pats += ["A", "C"]
    elif has("tool") and (f["branches"] or "[" in names): pats += ["C"]
    if has("write"): pats += ["B"]
    if has("retrieve") and (has("model") or structure): pats += ["D"]
    if (has("tool") or has("write")) and (has("verify") or any(k in ids for k in ("returncode", "exit_code", "status_code", "success", "postcondition"))): pats += ["E"]
    if f["loops"] and has("model") and (has("tool") or has("observe")): pats += ["F"]
    if has("plan") and (has("tool") or has("write")): pats += ["G"]
    if has("context") and (structure or has("model")): pats += ["H"]
    if f["exceptions"] and (f["loops"] or "retry" in ids) and (has("model") or has("tool") or has("write")): pats += ["I"]
    if has("agent") and (has("model") or f["branches"] or "[" in names): pats += ["J"]
    if has("review") and ("diff" in ids or "acceptance" in ids) and structure: pats += ["K"]
    if has("graph") and (has("write") or structure): pats += ["L"]
    if has("model") and (f["returns"] or "answer" in ids or "citation" in ids): pats += ["M"]
    reason = None
    if any(("jev" in c["name"].lower() or "typesafe" in c["name"].lower()) and any(k in c["name"].lower() for k in ("generate_code", "generate_sql", "write_essay", "generate_shell", "summarize")) for c in calls):
        reason = "JEV is being used for open-ended generation; keep generation separate from assessment."
        pats = ["NONE"]
    # Pure operations / exact checks: no model, side effects, retrieval, or unknown calls.
    pure_calls = (not calls or all(any(c is m or c["name"] == m["name"] for m in roles.get("deterministic", [])) for c in calls))
    if pure_calls and (f["operators"] or has("deterministic")) and not (has("model") or has("write") or has("retrieve")):
        reason = "Exact computation or state validation has a preferred deterministic implementation."
        pats = ["NONE"]
    # Names alone can create a review lead, but never a source-verified placement.
    if not pats and re.search(r"choose|select|route|classify|retry|verify|merge|compact", f["symbol"], re.I):
        pats = ["C"]
        reason = "Name-only review lead: insufficient structural evidence for recommending JEV."
    return list(dict.fromkeys(pats)), roles, reason


def _git_metadata(root: Path) -> dict:
    result = {"revision": None, "dirty": None}
    # Read-only git commands; no hooks, submodules, or target commands are run.
    for key, cmd in (("revision", ["rev-parse", "HEAD"]), ("dirty", ["status", "--porcelain", "--untracked-files=no"])):
        try:
            p = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=" + os.devnull, "-C", str(root), *cmd], capture_output=True,
                               text=True, timeout=5, env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
            if p.returncode == 0:
                result[key] = bool(p.stdout.strip()) if key == "dirty" else p.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return result


def scan_repo(root: str | Path, cfg: dict) -> dict:
    root = Path(root).resolve()
    if not root.is_dir(): raise InputError("Repository root must be a directory")
    functions, file_records, ignored, configs, warnings = [], [], [], [], []
    languages = Counter()
    max_files = min(cfg["repository"]["max_files"], 500 if cfg["depth"] == "QUICK" else cfg["repository"]["max_files"])
    processed = 0
    truncated = False
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS and not (Path(parent) / d).is_symlink()
                         and not any(fnmatch.fnmatch((Path(parent) / d).relative_to(root).as_posix(), pat.rstrip("/")) for pat in cfg["repository"]["exclude"]))
        for name in sorted(files):
            path = Path(parent) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink() or SENSITIVE.search(name) or any(fnmatch.fnmatch(rel, p) for p in cfg["repository"]["exclude"]):
                ignored.append({"file": rel, "reason": "symlink, sensitive filename, or exclusion"}); continue
            ext = path.suffix.lower()
            if ext not in LANGUAGES and name not in CONFIG_NAMES and not rel.startswith(".github/workflows/"):
                continue
            if processed >= max_files:
                truncated = True; break
            try:
                if path.stat().st_size > cfg["repository"]["max_file_bytes"]:
                    ignored.append({"file": rel, "reason": "file-size budget"}); continue
                raw = path.read_bytes()
                if b"\x00" in raw: continue
                source = raw.decode("utf-8")
            except (OSError, UnicodeError) as exc:
                warnings.append({"file": rel, "reason": type(exc).__name__}); continue
            processed += 1
            sha = hashlib.sha256(raw).hexdigest()
            if ext not in LANGUAGES:
                # Dependency/framework facts are term sightings, not confirmed installations.
                markers = [term for term in ("openai", "anthropic", "typesafe", "langchain", "langgraph", "neo4j", "fastapi", "pytest", "redis", "postgres", "docker", "kubernetes", "celery", "opentelemetry") if term in source.lower()]
                configs.append({"file": rel, "sha256": sha, "markers": markers})
                continue
            lang = LANGUAGES[ext]; languages[lang] += 1
            warning = None
            try:
                if lang == "python": fs, imports, _ = _python(source, rel)
                elif lang in ("javascript", "typescript") and cfg["repository"]["typescript_ast"]: fs, imports, _ = _typescript(source, rel)
                else: fs, imports, _ = _fallback(source, rel)
            except (SyntaxError, InputError, OSError, subprocess.SubprocessError, RecursionError) as exc:
                fs, imports, _ = _fallback(source, rel)
                warning = type(exc).__name__ + ": AST unavailable; review-only fallback"
                warnings.append({"file": rel, "reason": warning})
            duplicate_counts=Counter(f["symbol"] for f in fs)
            ordinals=Counter()
            for f in fs:
                original=f["symbol"]
                if duplicate_counts[original]>1:
                    ordinals[original]+=1
                    f["symbol"]=original+"#definition-"+str(ordinals[original])
            if any(v>1 for v in duplicate_counts.values()):
                warnings.append({"file":rel,"reason":"Repeated qualified symbols disambiguated by declaration order; ambiguous call targets remain unresolved"})
            lines = source.splitlines()
            for f in fs:
                snippet = "\n".join(lines[f["start_line"]-1:f["end_line"]])
                f.update({"file": rel, "language": lang, "file_sha256": sha, "source_sha256": hashlib.sha256(snippet.encode()).hexdigest(),
                          "node_id": f"{rel}::{f['symbol']}", "imports": imports, "is_test": any(x.startswith("test") or x in ("tests", "__tests__") for x in Path(rel).parts) or ".test." in rel or ".spec." in rel})
                f["patterns"], f["roles"], f["discovery_note"] = _patterns(f)
            functions.extend(fs)
            file_records.append({"file": rel, "sha256": sha, "language": lang, "parser": fs[0]["parser"] if fs else ("python_ast" if lang == "python" else "typescript_ast"), "symbols": len(fs), "imports": imports})
        if truncated: break
    if truncated: warnings.append({"reason": "File budget reached; coverage is incomplete, not an exhaustive negative result"})
    architecture = build_architecture(functions)
    candidates = discover(functions, architecture, cfg)
    result = {"schema_version": "1.0", "repository_name": root.name, "git": _git_metadata(root),
            "depth": cfg["depth"], "coverage": {"languages": dict(languages), "files_analyzed": len(file_records),
              "files_considered": processed, "symbols": len(functions), "truncated": truncated,
              "parser_counts": dict(Counter(f["parser"] for f in file_records)), "ignored": ignored, "warnings": warnings,
              "limitations": ["Call edges are conservative static approximations, not a complete dynamic call graph.",
                             "Python and JavaScript/TypeScript use ASTs when available; all other languages require agent-led source review.",
                             "Unknown dynamic dispatch, reflection, macro expansion, framework callbacks, and deployment effects need traces or review.",
                             "Tests and dependency sightings indicate availability, not correctness or installed versions."]},
            "files": file_records, "configuration_evidence": configs, "architecture": architecture,
            "candidates": candidates, "interactions": detect_interactions(candidates),
            "scan_fingerprint": digest(sorted((x["file"], x["sha256"]) for x in file_records))}
    from .lifecycle import analysis_identity
    result["analysis_identity"] = analysis_identity(file_records, configs, cfg, result["coverage"])
    result["scan_fingerprint"] = digest(result["analysis_identity"])
    return result


def build_architecture(functions: list[dict]) -> dict:
    nodes = {f["node_id"]: f for f in functions}
    by_file = defaultdict(dict)
    module_map = {}
    for f in functions:
        by_file[f["file"]][f["symbol"]] = f["node_id"]
        module = str(Path(f["file"]).with_suffix("")).replace("/", ".")
        module_map[module + "." + f["symbol"]] = f["node_id"]
    edges, unresolved = [], []
    for f in functions:
        for c in f["calls"]:
            name = c["name"]
            target = by_file[f["file"]].get(name)
            if name.startswith("self.") or name.startswith("this."):
                scope = f["symbol"].rsplit(".", 1)[0]
                target = by_file[f["file"]].get(scope + "." + name.split(".", 1)[1])
            target = target or module_map.get(c.get("resolved_name", ""))
            if target:
                edges.append({"source": f["node_id"], "target": target, "line": c["line"], "kind": "static_candidate"})
            else:
                unresolved.append({"source": f["node_id"], "call": name, "line": c["line"]})
    adjacency = defaultdict(set)
    for e in edges: adjacency[e["source"]].add(e["target"])
    public_nodes = []
    for f in functions:
        seen = {f["node_id"]}; q = deque([(f["node_id"], 0)]); depth = 0
        while q:
            node, d = q.popleft(); depth = max(depth, d)
            for dest in adjacency[node]:
                if dest not in seen: seen.add(dest); q.append((dest, d+1))
        public_nodes.append({"id": f["node_id"], "file": f["file"], "symbol": f["symbol"], "lines": [f["start_line"], f["end_line"]],
                             "roles": sorted(f["roles"]), "calls": redact(f["calls"]), "branches": f["branches"], "loops": f["loops"],
                             "exceptions": f["exceptions"], "dataflow": f["dataflow"],
                             "fan_out": len(adjacency[f["node_id"]]), "reachable_nodes": len(seen)-1,
                             "dependency_depth_lower_bound": depth, "parser": f["parser"], "is_test": f["is_test"]})
    return {"nodes": public_nodes, "edges": edges, "unresolved_calls": unresolved,
            "modules": [{"file": k, "symbols": sorted(v)} for k, v in sorted(by_file.items())],
            "side_effect_map": [{"node": f["node_id"], "calls": f["roles"]["write"]} for f in functions if "write" in f["roles"]],
            "flow_maps": {role: [f["node_id"] for f in functions if role in f["roles"]] for role in ("tool", "model", "retrieve", "observe", "graph", "context", "agent")}}


def discover(functions: list[dict], architecture: dict, cfg: dict) -> list[dict]:
    from .questions import design_questions
    from .scoring import initial_dimensions, score_candidate
    graph_nodes = {n["id"]: n for n in architecture["nodes"]}
    any_tests = any(f["is_test"] for f in functions)
    out = []
    for f in functions:
        if f["is_test"]: continue
        for pattern in f["patterns"]:
            spec = PATTERNS[pattern]
            lexical = f["parser"] == "lexical_review_only" or (f["discovery_note"] or "").startswith("Name-only")
            deterministic = "preferred" if pattern == "NONE" else "weak"
            if pattern == "B" and not set(f["roles"]) & {"model", "plan", "agent"}:
                deterministic = "preferred"
            node = graph_nodes[f["node_id"]]
            cid = "JEV-" + digest([f["file"], f["symbol"], pattern])[:12].upper()
            evidence = {"file": f["file"], "symbol": f["symbol"], "start_line": f["start_line"], "end_line": f["end_line"],
                        "file_sha256": f["file_sha256"], "source_sha256": f["source_sha256"], "parser": f["parser"]}
            candidate = {"candidate_id": cid, "pattern": pattern, "category": spec["category"], "source": evidence,
                         "evidence_status": "review_required" if lexical else "structurally_supported",
                         "semantic_review": {"approved": False, "reviewer": None, "reason": None, "source_sha256": f["source_sha256"]},
                         "current_behavior": {"description": "Observed calls and control structures; purpose requires source review.",
                                              "calls": [c["name"] for c in f["calls"]], "branches": len(f["branches"]), "loops": len(f["loops"]), "exceptions": len(f["exceptions"]),
                                              "failure_modes": [{"status": "hypothesis", "description": spec["benefit"]}]},
                         "evidence": [{"id": cid + ":source", "kind": f["parser"], "source": evidence,
                                       "facts": {"roles": sorted(f["roles"]), "calls": f["calls"], "dataflow": f["dataflow"]}}],
                         "deterministic_alternative": deterministic,
                         "proposed_jev_role": {"type": "bounded_choice" if pattern != "NONE" else "none", "timing": spec["timing"]},
                         "jev_questions": design_questions(pattern, cid), "choices": list(spec["choices"]),
                         "deterministic_checks": spec["deterministic"],
                         "expected_benefits": [{"description": spec["benefit"], "status": "unmeasured_hypothesis"}],
                         "risks": ["Incorrect high-confidence classification", "Added latency/cost", "Evidence loss or stale state", "Correlated evaluator errors"],
                         "leverage": {"fan_out": node["fan_out"], "dependency_depth_lower_bound": node["dependency_depth_lower_bound"],
                                      "reachable_nodes": node["reachable_nodes"], "state_corruption_risk": "possible" if "write" in f["roles"] else "unknown", "expected_recovery_cost": None},
                         "fallback": {"low_confidence": "existing validated baseline or inspect", "unavailable": "existing validated baseline", "unsafe_baseline": "block or request authorized review"},
                         "policy": {"default_mode": "off", "thresholds_status": "unvalidated", "requires_calibration_before_active": True,
                                    "decision_owner": "deterministic_host", "hard_blocks_override_model": True,
                                    "illustrative_probability_floor": 0.95 if pattern in ("B", "L", "K") else 0.90,
                                    "illustrative_confidence_floor": 0.90 if pattern in ("B", "L", "K") else 0.75,
                                    "inspect_probability_floor": 0.65, "timeout_ms": cfg["runtime"]["timeout_ms"],
                                    "bypass": ["feature disabled", "deterministic result sufficient", "unchanged valid cached state", "budget or deadline exhausted"],
                                    "cache": "only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization"},
                         "estimates": {"quality_gain": None, "reliability_gain": None, "failure_reduction": None,
                                       "model_call_reduction": None, "added_latency_ms": None, "added_cost": None,
                                       "calls_per_task": None, "complexity": None, "maintenance": None, "false_positive_rate": None,
                                       "false_negative_rate": None, "risk": None, "throughput": None, "provenance": None},
                         "recommended_experiment": {"id": cid + "-EXP-01", "paired_replay": True, "shadow_first": True,
                                                    "primary_metric": "verified task success", "status": "planned", "holdout_required": True},
                         "traceability": {"source": cid + ":source", "questions": [], "implementation": [], "tests": [], "experiment": cid + "-EXP-01", "outcome": None},
                         "limitations": [f["discovery_note"]] if f["discovery_note"] else []}
            candidate["traceability"]["questions"] = [q["id"] for q in candidate["jev_questions"]]
            candidate["dimensions"] = initial_dimensions(f, node, any_tests, candidate)
            score_candidate(candidate, cfg)
            out.append(candidate)
    return sorted(out, key=lambda c: (-c["tier"], -c["placement_score"], c["candidate_id"]))


def detect_interactions(candidates: list[dict]) -> list[dict]:
    complement = {frozenset(p) for p in (("A", "E"), ("C", "E"), ("D", "M"), ("G", "B"), ("H", "I"), ("L", "B"))}
    by_file = defaultdict(list)
    for c in candidates:
        if c["pattern"] != "NONE": by_file[c["source"]["file"]].append(c)
    result = []
    for cs in by_file.values():
        for i, a in enumerate(cs):
            for b in cs[i+1:]:
                same = a["source"]["symbol"] == b["source"]["symbol"]
                pair = frozenset((a["pattern"], b["pattern"]))
                kind = "redundant" if same and pair == frozenset(("A", "C")) else "complementary" if pair in complement else "shared_boundary" if same else None
                if kind:
                    result.append({"a": a["candidate_id"], "b": b["candidate_id"], "kind": kind,
                                   "status": "hypothesis", "utility_delta": 0.0,
                                   "conflict": kind == "redundant", "reason": "Same source boundary" if same else "Same-file architectural hypothesis; verify call path",
                                   "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"})
    return result
