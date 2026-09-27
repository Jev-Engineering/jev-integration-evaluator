"""New synthetic qualification, not an independent host-corpus or live study."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from dataclasses import replace
import subprocess
import sys

import jsonschema
import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import nomination_inventory as bridge
from jev_integration_evaluator import placement_selection as selection
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.io import canonical, digest
from jev_integration_evaluator.optimizer import REQUIRED, optimize

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Inherited secure discovery contract requires POSIX")
ROOT = Path(__file__).resolve().parents[1]
OPAQUE = 'def b(x):\n    return x["operation"](x)\n\ndef q(x):\n    return b(x)\n'


@pytest.fixture
def factory(tmp_path):
    count = 0

    def make(source=OPAQUE, *, path="opaque.py", nominations=(("q", "C"),),
             approved=True, policy=None, extra=None):
        nonlocal count
        count += 1
        repo = tmp_path / ("host-" + str(count))
        repo.mkdir()
        if source is not None:
            target = repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        for name, value in (extra or {}).items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")
        cfg = copy.deepcopy(DEFAULT)
        cfg["repository"]["typescript_ast"] = False
        report = bridge.discover_repository_capabilities(repo, cfg, policy=policy)
        proposals = []
        for symbol, pattern in nominations:
            seam = next(s for s in report["seams"] if s["source"]["qualified_symbol"] == symbol)
            a = seam["source"]
            proposals.append({"schema_version": "1.0", "discovery_version": cap.VERSION,
                              "report_sha256": report["report_sha256"], "seam_id": seam["seam_id"],
                              "source": copy.deepcopy(a), "pattern": pattern,
                              "proposer": "synthetic-fixture-author",
                              "rationale": "Test a finite existing policy choice, not new execution authority.",
                              "evidence": [{"file": a["file"], "file_sha256": a["file_sha256"],
                                            "start_line": a["start_line"], "end_line": a["end_line"]}]})
        prepared = bridge.prepare_nominated_inventory(repo, report, proposals, cfg, policy=policy)
        updates = {}
        for c in prepared["inventory"]["candidates"]:
            excluded = c["tier"] == 0 or c.get("hard_real_time") is True or c["deterministic_alternative"] in ("preferred", "mandatory")
            updates[c["candidate_id"]] = {"source_sha256": c["source"]["source_sha256"],
                                         "approved": approved and not excluded,
                                         "reviewer": "synthetic-semantic-reviewer",
                                         "reason": "Fixture-supplied semantic judgment; not a measurement, binding review or execution permission."}
        review = {"schema_version": "1.0", "prepared_sha256": prepared["prepared_sha256"], "reviews": updates}
        return {"repo": repo, "report": report, "prepared": prepared,
                "semantic_review": review, "cfg": cfg, "policy": policy}
    return make


def context(case, scope=None):
    return selection.prepare_placement_context(**case, scope_review=scope)


def request(ctx, ids=None, **changes):
    result = {"schema_version": "1.0", "contract": selection.SELECTION_REVIEW,
              "context_sha256": ctx["context_sha256"],
              "candidate_ids": ctx["experimental_candidate_ids"] if ids is None else ids,
              "reviewer": "synthetic-experiment-reviewer",
              "reason": "Prepare an explicitly experimental, default-off placement; all benefit estimates remain unknown.",
              "approved": True, "mode": "experimental",
              "resource_bounds": {"max_calls_total": None, "max_cost_total_usd": None, "deadline_seconds": None}}
    result.update(changes)
    return result


def run_select(case, req=None, scope=None):
    req = req or request(context(case, scope))
    return selection.select_experimental_placements(**case, selection_review=req, scope_review=scope)


def scope_review(case, disposition="no_useful_placement"):
    report = case["report"]
    return {"schema_version": "1.0", "contract": selection.SCOPE_REVIEW,
            "report_sha256": report["report_sha256"],
            "prepared_sha256": case["prepared"]["prepared_sha256"],
            "reviewer": "synthetic-source-scope-reviewer",
            "reason": "Explicit whole-scope judgment for this synthetic fixture; excludes unenumerated source and live behavior.",
            "pattern_scope": selection.PATTERN_SCOPE, "snapshot_scope": report["snapshot_scope"],
            "files": [{"file": f["file"], "file_sha256": f["sha256"], "line_count": f["line_count"],
                       "coverage": "entire_file", "disposition": disposition,
                       "reason": "Whole-file semantics reviewed for every existing A-M placement."} for f in report["files"]],
            "seams": [{"seam_id": s["seam_id"], "source": copy.deepcopy(s["source"]),
                       "disposition": disposition,
                       "reason": "This exact AST-anchored seam was included in the semantic judgment."} for s in report["seams"]]}


def revalidate(case, ctx, req, record, **kw):
    return selection.revalidate_experimental_selection(
        **case, selection_review=req, selection=record,
        expected_selection_sha256=kw.pop("expected", record["selection_sha256"]), **kw)


def test_real_bridge_to_experimental_selection_keeps_unknowns(factory):
    case = factory()
    original = copy.deepcopy({k: v for k, v in case.items() if k not in ("repo", "policy")})
    ctx = context(case)
    assert ctx["outcome"] == "experimental_review_required"
    assert ctx["optimization"] == {"declared_model_status": "no_justified_integration_set",
                                    "eligible_candidates": 0, "status": "insufficient_estimates",
                                    "benefit_supported": False, "no_useful_placement_inferred": False}
    req = request(ctx)
    record = run_select(case, req)
    assert record["status"] == "experimental_selection"
    assert record["requested_count"] == record["selected_count"] == 1
    assert record["selected_candidate_ids"] == req["candidate_ids"]
    assert record["missing_resource_bounds"] == list(selection.BOUND_KEYS)
    assert record["placements"][0]["missing_estimates"] == REQUIRED
    assert all(v is None for v in record["placements"][0]["estimates"].values())
    assert record["binding_review"] == "not_performed"
    assert not record["implementation_verified"]
    assert record["runtime_mode"] == "off"
    assert record["authorization"] == selection.DENIED
    assert not record["benefit_supported"] and not record["authority_authenticated"]
    assert revalidate(case, ctx, req, record) == record
    assert original == {k: v for k, v in case.items() if k not in ("repo", "policy")}


def test_repeated_context_and_selection_are_deterministic(factory):
    case = factory()
    a, b = context(case), context(case)
    assert canonical(a) == canonical(b)
    assert run_select(case, request(a)) == run_select(case, request(b))


def test_rejected_candidate_is_not_repository_absence(factory):
    case = factory(approved=False)
    ctx = context(case)
    assert ctx["outcome"] == "source_scope_review_required"
    assert ctx["scope_review"]["no_useful_judgment"] is False
    assert ctx["experimental_candidate_ids"] == []


def test_no_useful_requires_source_review_beyond_candidate_inventory(factory):
    case = factory(approved=False)
    # The opaque callback b has no legacy candidate, but must still be reviewed.
    assert len(case["report"]["seams"]) > len(case["prepared"]["inventory"]["candidates"])
    scope = scope_review(case)
    ctx = context(case, scope)
    assert ctx["outcome"] == "no_useful_placement"
    assert ctx["snapshot_scope"] == "bounded_source_and_configuration_not_full_repository"
    assert ctx["scope_review"]["files_total"] == ctx["scope_review"]["files_reviewed"] == 1
    assert ctx["scope_review"]["seams_total"] == ctx["scope_review"]["seams_reviewed"] == 2
    assert ctx["scope_review"]["review_sha256"] == digest(scope)


@pytest.mark.parametrize("part", ["files", "seams"])
def test_partial_scope_review_retains_missing_denominator(factory, part):
    case = factory(approved=False)
    scope = scope_review(case)
    scope[part].pop()
    ctx = context(case, scope)
    assert ctx["outcome"] == "insufficient_evidence"
    assert ctx["scope_review"][part + "_total"] > ctx["scope_review"][part + "_reviewed"]
    assert len(ctx["scope_review"]["missing_" + part]) == 1
    assert not ctx["scope_review"]["no_useful_judgment"]


@pytest.mark.parametrize("part", ["files", "seams"])
@pytest.mark.parametrize("disposition", ["unresolved", "useful"])
def test_nonnegative_scope_judgments_never_turn_into_absence(factory, part, disposition):
    case = factory(approved=False)
    scope = scope_review(case)
    scope[part][0]["disposition"] = disposition
    ctx = context(case, scope)
    assert ctx["outcome"] == ("insufficient_evidence" if disposition == "unresolved" else "nomination_required")
    assert not ctx["scope_review"]["no_useful_judgment"]


def test_contradictory_positive_and_negative_reviews_fail_closed(factory):
    case = factory()
    ctx = context(case, scope_review(case))
    assert ctx["outcome"] == "insufficient_evidence"
    assert ctx["next_action"] == "reconcile_conflicting_semantic_reviews"
    rec = run_select(case, request(ctx), scope_review(case))
    assert rec["status"] == "blocked" and rec["selected_count"] == 0


def test_empty_repository_is_no_candidates_not_vacuous_no_useful(factory):
    case = factory(None, nominations=())
    ctx = context(case, scope_review(case))
    assert ctx["outcome"] == "no_candidates_discovered"
    assert not ctx["scope_review"]["no_useful_judgment"]
    assert ctx["scope_review"]["files_total"] == 0


def test_module_only_source_needs_file_review(factory):
    case = factory('VALUE = 4\n', nominations=())
    assert context(case)["outcome"] == "no_candidates_discovered"
    assert context(case, scope_review(case))["outcome"] == "no_useful_placement"


@pytest.mark.parametrize("name,contents", [("extra.ts", "export const x = 1;\n"),
                                            ("bad.py", "def ???\n"),
                                            ("worker.go", "package main\n"),
                                            ("proto.pyi", "def f() -> None: ...\n")])
def test_unparsed_sources_block_even_complete_negative_review(factory, name, contents):
    case = factory(approved=False, extra={name: contents})
    ctx = context(case, scope_review(case))
    assert ctx["outcome"] == "incomplete_analysis"
    assert not ctx["coverage_complete_within_policy"]


def test_directory_and_file_bounds_are_not_absence(factory):
    policy = cap.DiscoveryPolicy(max_files=1, max_file_bytes=DEFAULT["repository"]["max_file_bytes"])
    case = factory(None, nominations=(), policy=policy,
                   extra={"a.py": "x = 1\n", "b.py": "y = 2\n"})
    assert context(case, scope_review(case))["outcome"] == "incomplete_analysis"


def test_exclusions_are_recorded_and_never_silently_included(factory):
    policy = cap.DiscoveryPolicy(exclude=("private.py",), max_file_bytes=DEFAULT["repository"]["max_file_bytes"])
    case = factory(approved=False, policy=policy, extra={"private.py": "raise RuntimeError('never import')\n"})
    ctx = context(case, scope_review(case))
    assert ctx["outcome"] == "no_useful_placement"
    assert ctx["excluded_entries"] == 1
    assert ctx["snapshot_scope"] != "full_repository"


@pytest.mark.parametrize("path,source,symbol", [
    ("pkg/opaque.py", OPAQUE, "q"),
    ("opaque.py", 'async def b(x):\n    return x["operation"](x)\n\nasync def q(x):\n    return await b(x)\n', "q"),
    ("opaque.py", 'class Engine:\n    def q(self, x):\n        return x["operation"](x)\n', "Engine.q"),
])
def test_semantically_approved_unsupported_shapes_are_not_qualified(factory, path, source, symbol):
    case = factory(source, path=path, nominations=((symbol, "C"),))
    ctx = context(case)
    assert ctx["outcome"] == "unsupported"
    cid = ctx["candidates"][0]["candidate_id"]
    rec = run_select(case, request(ctx, [cid]))
    assert rec["selected_candidate_ids"] == []
    assert any(f["reason"] == "unsupported" for f in rec["failures"])


def test_deterministic_source_remains_excluded(factory):
    case = factory('def route(x):\n    return x + 1\n', nominations=())
    ctx = context(case)
    assert ctx["outcome"] == "deterministic_rejection"
    rec = run_select(case, request(ctx, [ctx["candidates"][0]["candidate_id"]]))
    assert not rec["selected_candidate_ids"]
    assert {r["reason"] for r in rec["failures"]} >= {"excluded", "deterministic_rejection"}


def test_hard_real_time_is_mandatory_for_heuristic_candidates(factory):
    source = OPAQUE.replace("def q", "def route")
    case = factory(source, nominations=(), policy=cap.DiscoveryPolicy(hard_real_time=("opaque.py::route",), max_file_bytes=DEFAULT["repository"]["max_file_bytes"]))
    ctx = context(case)
    assert ctx["outcome"] == "deterministic_rejection"
    cid = ctx["candidates"][0]["candidate_id"]
    assert run_select(case, request(ctx, [cid]))["selected_count"] == 0


def test_unreviewed_candidate_stays_unreviewed(factory):
    case = factory()
    case["semantic_review"]["reviews"] = {}
    assert context(case)["outcome"] == "semantic_review_required"


def test_unknown_candidate_blocks_entire_requested_set(factory):
    case = factory()
    ctx = context(case)
    req = request(ctx, [*ctx["experimental_candidate_ids"], "JEV-UNKNOWN"])
    rec = run_select(case, req)
    assert rec["requested_count"] == 2 and rec["selected_count"] == 0
    assert rec["placements"] == []
    assert rec["failures"] == [{"candidate_id": "JEV-UNKNOWN", "reason": "unknown_selected_candidate"}]


def test_explicit_experimental_rejection_blocks_every_requested_candidate(factory):
    case = factory()
    req = request(context(case), approved=False)
    rec = run_select(case, req)
    assert rec["status"] == "blocked" and rec["selected_count"] == 0
    assert {f["candidate_id"] for f in rec["failures"]} == set(req["candidate_ids"])


def test_conflicting_same_seam_selection_is_atomic(factory):
    case = factory(nominations=(("q", "A"), ("q", "C")))
    ctx = context(case)
    assert len(ctx["conflicts"]) == 1
    rec = run_select(case, request(ctx))
    assert rec["requested_count"] == 2 and rec["selected_count"] == 0
    assert {f["reason"] for f in rec["failures"]} == {"conflicting_selected_placements"}
    assert len(rec["failures"]) == 2


def test_compatible_set_does_not_claim_composite_implementation(factory):
    case = factory(OPAQUE + '\ndef z(x):\n    return b(x)\n', nominations=(("q", "C"), ("z", "C")))
    rec = run_select(case)
    assert rec["selected_count"] == 2 and rec["requires_composite_transaction"]
    assert not rec["implementation_verified"] and not any(rec["authorization"].values())


@pytest.mark.parametrize("value", [None, 0, 7])
def test_explicit_call_budget_does_not_become_spending_authority(factory, value):
    case = factory()
    req = request(context(case))
    req["resource_bounds"] = {"max_calls_total": value, "max_cost_total_usd": 0.1, "deadline_seconds": 5}
    rec = run_select(case, req)
    assert rec["resource_bounds"] == req["resource_bounds"]
    assert rec["missing_resource_bounds"] == (["max_calls_total"] if value is None else [])
    assert not any(rec["authorization"].values())


@pytest.mark.parametrize("value", [True, False, -1, 1.0, "1", float("nan"), float("inf"), 2**65])
def test_invalid_call_bounds_rejected(factory, value):
    case = factory()
    req = request(context(case))
    req["resource_bounds"]["max_calls_total"] = value
    with pytest.raises(cap.CapabilityError):
        run_select(case, req)


@pytest.mark.parametrize("target", ["source", "configuration", "policy", "semantic_review", "prepared", "report"])
def test_full_source_and_review_drift_is_rejected(factory, target):
    case = factory(extra={"pyproject.toml": '[project]\nname = "synthetic"\n'})
    ctx = context(case)
    req = request(ctx)
    if target == "source":
        (case["repo"] / "opaque.py").write_text(OPAQUE.replace('x["operation"]', 'x["other"]'))
    elif target == "configuration":
        (case["repo"] / "pyproject.toml").write_text('[project]\nname = "changed"\n')
    elif target == "policy":
        case["policy"] = replace(bridge._settings(case["cfg"], None)[1], exclude=("unused.txt",))
    elif target == "semantic_review":
        next(iter(case["semantic_review"]["reviews"].values()))["reason"] += " changed"
    elif target == "prepared":
        case["prepared"]["inventory"]["candidates"][0]["estimates"]["quality_gain"] = 0.9
        case["prepared"]["inventory_sha256"] = digest(case["prepared"]["inventory"])
        case["prepared"]["prepared_sha256"] = digest({k:v for k,v in case["prepared"].items() if k != "prepared_sha256"})
    else:
        case["report"]["coverage"]["excluded_entries"] += 1
        case["report"]["report_sha256"] = cap._digest({k:v for k,v in case["report"].items() if k != "report_sha256"})
    with pytest.raises(cap.CapabilityError):
        run_select(case, req)


@pytest.mark.parametrize("mutation", ["selected_set", "estimates", "bounds", "source", "denominator", "failure"])
def test_rehashed_selection_tampering_does_not_authenticate(factory, mutation):
    case = factory()
    ctx = context(case)
    req = request(ctx)
    record = run_select(case, req)
    changed = copy.deepcopy(record)
    if mutation == "selected_set":
        changed["selected_candidate_ids"] = []
    elif mutation == "estimates":
        changed["placements"][0]["estimates"]["quality_gain"] = 0.5
    elif mutation == "bounds":
        changed["resource_bounds"]["max_calls_total"] = 500
    elif mutation == "source":
        changed["placements"][0]["source"]["file_sha256"] = "f" * 64
    elif mutation == "denominator":
        changed["requested_count"] = 2
    else:
        changed["failures"] = [{"candidate_id": req["candidate_ids"][0], "reason": "forged"}]
    changed["selection_sha256"] = digest({k:v for k,v in changed.items() if k != "selection_sha256"})
    with pytest.raises(cap.CapabilityError):
        revalidate(case, ctx, req, changed)


@pytest.mark.parametrize("anchor", [None, "", "f" * 64, 1, True])
def test_independently_retained_identity_anchor_is_checked(factory, anchor):
    case = factory()
    ctx = context(case)
    req = request(ctx)
    record = run_select(case, req)
    with pytest.raises(cap.CapabilityError):
        revalidate(case, ctx, req, record, expected=anchor)


@pytest.mark.parametrize("part", ["files", "seams"])
@pytest.mark.parametrize("mutation", ["duplicate", "unknown", "anchor", "blank_reason", "extra"])
def test_scope_review_anchor_and_strictness(factory, part, mutation):
    case = factory(approved=False)
    scope = scope_review(case)
    row = scope[part][0]
    if mutation == "duplicate":
        scope[part].append(copy.deepcopy(row))
    elif mutation == "unknown":
        row["file" if part == "files" else "seam_id"] = "unknown.py" if part == "files" else "f" * 64
    elif mutation == "anchor":
        if part == "files": row["file_sha256"] = "f" * 64
        else: row["source"]["ast_sha256"] = "f" * 64
    elif mutation == "blank_reason":
        row["reason"] = "   "
    else:
        row["execute"] = True
    with pytest.raises(cap.CapabilityError):
        context(case, scope)


@pytest.mark.parametrize("field,value", [("approved", 1), ("mode", "active"), ("reviewer", " "),
                                          ("reason", ""), ("context_sha256", "f" * 64),
                                          ("candidate_ids", []), ("candidate_ids", ["JEV-X", "JEV-X"])])
def test_invalid_selection_review_is_not_approval(factory, field, value):
    case = factory()
    req = request(context(case))
    req[field] = value
    with pytest.raises(cap.CapabilityError):
        run_select(case, req)


@pytest.mark.parametrize("authority", ["execution", "mutation", "egress", "installation", "publication", "activation", "benefit_supported", "bindings", "estimates", "shell"])
def test_agent_review_cannot_inject_authority_or_observations(factory, authority):
    case = factory()
    req = request(context(case))
    req[authority] = True
    with pytest.raises(cap.CapabilityError):
        run_select(case, req)


def test_discovery_does_not_import_target_or_start_any_process(factory, monkeypatch, tmp_path):
    sentinel = tmp_path / "must-not-exist"
    case = factory(OPAQUE + '\nraise RuntimeError("target import forbidden")\n')
    def forbidden(*a, **kw):
        raise AssertionError("Unexpected target/tool execution")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    req = request(context(case))
    req["reason"] = f"__import__('pathlib').Path({str(sentinel)!r}).touch()"
    record = run_select(case, req)
    assert record["status"] == "experimental_selection"
    assert not sentinel.exists()


def test_negative_review_stales_when_unnominated_helper_changes(factory):
    case = factory(approved=False)
    scope = scope_review(case)
    (case["repo"] / "opaque.py").write_text(OPAQUE.replace('x["operation"]', 'x["changed"]'))
    with pytest.raises(cap.CapabilityError):
        context(case, scope)


def test_engine_drift_during_context_is_detected(factory, monkeypatch):
    case = factory()
    seq = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(selection, "_engine_identity", lambda: next(seq))
    with pytest.raises(cap.CapabilityError, match="source_or_selection_engine_changed"):
        context(case)


def test_cyclic_or_deep_data_is_bounded():
    x = []
    x.append(x)
    with pytest.raises(cap.CapabilityError, match="structure_budget"):
        selection._bounded(x)


@pytest.mark.parametrize("value", [set(), (1, 2), object(), {1: "not-json"}])
def test_non_json_objects_are_not_evaluated(value):
    with pytest.raises(cap.CapabilityError):
        selection._bounded(value)


def test_schema_mirrors_and_closed_input_output_contracts(factory):
    case = factory()
    ctx = context(case)
    req = request(ctx)
    record = run_select(case, req)
    scope = scope_review(case)
    for name, value in [(selection.CONTEXT, ctx), (selection.SELECTION, record),
                        (selection.SELECTION_REVIEW, req), (selection.SCOPE_REVIEW, scope)]:
        raw = (ROOT / "schemas" / (name + ".schema.json")).read_bytes()
        assert raw == (ROOT / "jev_integration_evaluator" / "data" / (name + ".schema.json")).read_bytes()
        schema = json.loads(raw)
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(value)
        invalid = copy.deepcopy(value)
        invalid["unexpected"] = True
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(invalid)


def test_optimizer_empty_set_is_not_absence(factory):
    case = factory()
    reviewed = bridge.review_nominated_inventory(case["repo"], case["report"], case["prepared"], case["semantic_review"], case["cfg"])
    optimized = optimize(reviewed["inventory"], case["cfg"]["constraints"])
    assert optimized["recommended_balanced_set"]["candidate_ids"] == []
    assert context(case)["outcome"] == "experimental_review_required"
    assert run_select(case)["selected_count"] == 1


def test_positive_scope_review_cannot_waive_mandatory_exclusion(factory):
    case = factory("def route(x):\n    return x + 1\n", nominations=())
    review = scope_review(case)
    review["seams"][0]["disposition"] = "useful"
    with pytest.raises(cap.CapabilityError, match="scope_review_cannot_waive_mandatory_exclusion"):
        context(case, review)


def cli_files(case, parent):
    """Write external synthetic contracts for actual isolated-interpreter calls."""
    paths = {}
    for name, value in (("report", case["report"]), ("prepared", case["prepared"]),
                        ("semantic-review", case["semantic_review"]), ("config-json", case["cfg"])):
        path = parent / (name + ".json")
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    return paths


def call_cli(case, paths, out, *extra, operation="context", cwd=None, env=None):
    argv = [sys.executable, "-I", str(ROOT / "scripts/select_repository_placements.py"),
            operation, "--repo", str(case["repo"]), "--out", str(out)]
    for key, path in paths.items():
        argv += ["--" + key, str(path)]
    argv += list(extra)
    return subprocess.run(argv, capture_output=True, text=True, timeout=30,
                          cwd=cwd or ROOT, env=env)


def test_central_cli_routes_source_scope_context(factory, tmp_path):
    case = factory(approved=False)
    paths = cli_files(case, tmp_path)
    review_path = tmp_path / "scope-review.json"
    review_path.write_text(json.dumps(scope_review(case)), encoding="utf-8")
    out = tmp_path / "central-context.json"
    argv = [sys.executable, "-m", "jev_integration_evaluator", "repository-placement",
            "context", "--repo", str(case["repo"]), "--out", str(out)]
    for key, path in paths.items():
        argv.extend(["--" + key, str(path)])
    argv.extend(["--scope-review", str(review_path)])
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out.read_text())["outcome"] == "no_useful_placement"
    assert "opaque.py" not in proc.stdout


def test_cli_redacts_unrecognized_argument(factory, tmp_path):
    case = factory()
    proc = call_cli(case, cli_files(case, tmp_path), tmp_path / "never.json",
                    "--secret-value=PRIVATE_SENTINEL")
    assert proc.returncode == 2
    assert json.loads(proc.stderr)["reason"] == "invalid_selection_arguments"
    assert "PRIVATE_SENTINEL" not in proc.stderr


def test_cli_full_context_selection_revalidation_external_private_output(factory, tmp_path):
    case = factory()
    paths = cli_files(case, tmp_path)
    ctxpath = tmp_path / "ctx.json"
    first = call_cli(case, paths, ctxpath)
    assert first.returncode == 0, first.stderr
    ctx = json.loads(ctxpath.read_text())
    assert ctx == context(case)
    reqpath = tmp_path / "selection-review.json"
    reqpath.write_text(json.dumps(request(ctx)))
    planpath = tmp_path / "plan.json"
    second = call_cli(case, paths, planpath, "--selection-review", str(reqpath), operation="select")
    assert second.returncode == 0, second.stderr
    plan = json.loads(planpath.read_text())
    copy_path = tmp_path / "revalidated.json"
    third = call_cli(case, paths, copy_path, "--selection-review", str(reqpath),
                     "--selection", str(planpath), "--expected-selection-sha256",
                     plan["selection_sha256"], operation="revalidate")
    assert third.returncode == 0, third.stderr
    assert json.loads(copy_path.read_text()) == plan
    for file in (ctxpath, planpath, copy_path):
        assert file.stat().st_mode & 0o777 == 0o600
    for proc in (first, second, third):
        assert proc.stderr == ""
        assert set(json.loads(proc.stdout)) == {"status", "artifact_sha256", "outcome", "next_action"}
        assert "operation" not in proc.stdout and "opaque.py" not in proc.stdout
    assert not any(plan["authorization"].values())
    assert (case["repo"] / "opaque.py").read_text() == OPAQUE


def test_cli_negative_judgment_and_partial_coverage_are_distinct(factory, tmp_path):
    case = factory(approved=False)
    paths = cli_files(case, tmp_path)
    scopepath = tmp_path / "scope.json"
    scope = scope_review(case)
    scopepath.write_text(json.dumps(scope))
    output = tmp_path / "negative.json"
    proc = call_cli(case, paths, output, "--scope-review", str(scopepath))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(output.read_text())["outcome"] == "no_useful_placement"
    scope["seams"].pop()
    scopepath.write_text(json.dumps(scope))
    output2 = tmp_path / "incomplete.json"
    proc2 = call_cli(case, paths, output2, "--scope-review", str(scopepath))
    assert proc2.returncode == 0, proc2.stderr
    assert json.loads(output2.read_text())["outcome"] == "insufficient_evidence"


@pytest.mark.parametrize("kind", ["report", "prepared", "semantic-review", "config-json"])
def test_cli_refuses_target_owned_input(factory, tmp_path, kind):
    case = factory()
    paths = cli_files(case, tmp_path)
    inside = case["repo"] / "target-owned.json"
    inside.write_bytes(paths[kind].read_bytes())
    paths[kind] = inside
    out = tmp_path / "never.json"
    proc = call_cli(case, paths, out)
    assert proc.returncode == 2
    assert json.loads(proc.stderr)["reason"] == "selection_input_must_be_external"
    assert not out.exists()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "duplicate_key", "malformed", "nan", "over_limit"])
def test_cli_hostile_input_fails_redacted_without_blocking(factory, tmp_path, kind):
    case = factory()
    paths = cli_files(case, tmp_path)
    p = tmp_path / "attack.json"
    marker = "sensitive-synthetic-marker"
    if kind == "symlink":
        p.symlink_to(paths["semantic-review"])
    elif kind == "hardlink":
        os.link(paths["semantic-review"], p)
    elif kind == "fifo":
        os.mkfifo(p)
    elif kind == "duplicate_key":
        p.write_text('{"reviewer":"' + marker + '","reviewer":"duplicate"}')
    elif kind == "malformed":
        p.write_text(marker)
    elif kind == "nan":
        p.write_text('{"' + marker + '":NaN}')
    else:
        p.write_bytes(b" " * (selection.MAX_BYTES + 1))
    paths["semantic-review"] = p
    out = tmp_path / "never.json"
    proc = call_cli(case, paths, out)
    assert proc.returncode == 2
    assert marker not in proc.stdout + proc.stderr
    assert str(p) not in proc.stdout + proc.stderr
    assert json.loads(proc.stderr)["status"] == "blocked"
    assert not out.exists()


@pytest.mark.parametrize("kind", ["existing", "symlink", "inside", "missing_parent"])
def test_cli_output_never_overwrites_or_writes_into_host(factory, tmp_path, kind):
    case = factory()
    paths = cli_files(case, tmp_path)
    out = tmp_path / "output.json"
    protected = tmp_path / "unrelated.txt"
    protected.write_text("preserve unrelated work")
    if kind == "existing":
        out.write_text("preserve existing output")
    elif kind == "symlink":
        out.symlink_to(protected)
    elif kind == "inside":
        out = case["repo"] / "output.json"
    else:
        out = tmp_path / "not-present" / "output.json"
    proc = call_cli(case, paths, out)
    assert proc.returncode == 2
    assert protected.read_text() == "preserve unrelated work"
    if kind == "existing":
        assert out.read_text() == "preserve existing output"
    elif kind not in ("symlink",):
        assert not out.exists()


def test_cli_isolated_interpreter_does_not_load_target_sitecustomize(factory, tmp_path):
    sentinel = tmp_path / "never-executed"
    case = factory(extra={"sitecustomize.py":
                         f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n"})
    paths = cli_files(case, tmp_path)
    env = dict(os.environ, PYTHONPATH=str(case["repo"]))
    proc = call_cli(case, paths, tmp_path / "out.json", cwd=case["repo"], env=env)
    assert proc.returncode == 0, proc.stderr
    assert not sentinel.exists()


@pytest.mark.parametrize("operation,extra,reason", [
    ("context", ["--expected-selection-sha256", "0" * 64], "unexpected_selection_arguments"),
    ("select", [], "selection_review_required"),
    ("revalidate", [], "selection_review_required"),
])
def test_cli_required_contract_arguments_are_checked(factory, tmp_path, operation, extra, reason):
    case = factory()
    paths = cli_files(case, tmp_path)
    proc = call_cli(case, paths, tmp_path / "never.json", *extra, operation=operation)
    assert proc.returncode == 2
    assert json.loads(proc.stderr)["reason"] == reason


def test_cli_blocked_selection_returns_nonzero_and_retains_requested_schedule(factory, tmp_path):
    case = factory()
    paths = cli_files(case, tmp_path)
    req = request(context(case), ["JEV-UNKNOWN"])
    reqpath = tmp_path / "selection-review.json"
    reqpath.write_text(json.dumps(req))
    out = tmp_path / "blocked.json"
    proc = call_cli(case, paths, out, "--selection-review", str(reqpath), operation="select")
    assert proc.returncode == 2
    assert proc.stderr == ""
    summary = json.loads(proc.stdout)
    assert summary["outcome"] == "blocked"
    assert summary["next_action"] == "resolve_selection_failures"
    record = json.loads(out.read_text())
    assert record["requested_candidate_ids"] == ["JEV-UNKNOWN"]
    assert record["selected_count"] == 0 and record["requested_count"] == 1
    assert record["failures"] == [{"candidate_id": "JEV-UNKNOWN", "reason": "unknown_selected_candidate"}]


@pytest.mark.parametrize("kind", ["cycle", "depth", "nodes", "bytes", "custom_object"])
def test_plain_json_structural_limits_reject_without_evaluating_objects(kind):
    if kind == "cycle":
        value = []
        value.append(value)
    elif kind == "depth":
        value = None
        for _ in range(66):
            value = [value]
    elif kind == "nodes":
        value = [None] * 200001
    elif kind == "bytes":
        value = "x" * selection.MAX_BYTES
    else:
        class Forbidden:
            def __iter__(self):
                raise AssertionError("Custom object evaluated")
            def __repr__(self):
                raise AssertionError("Custom object represented")
        value = Forbidden()
    with pytest.raises(cap.CapabilityError):
        selection._bounded(value)


def test_source_linked_examples_and_all_four_schema_mirrors():
    examples = ROOT / "examples/placement-selection"
    pairs = {"context": selection.CONTEXT, "negative-context": selection.CONTEXT,
             "selection-review": selection.SELECTION_REVIEW, "selection": selection.SELECTION,
             "scope-review": selection.SCOPE_REVIEW}
    for file, contract in pairs.items():
        data = json.loads((examples / (file + ".json")).read_text())
        selection._validate(data, contract)
    report = json.loads((examples / "report.json").read_text())
    raw = (examples / "host/opaque.py").read_bytes()
    assert report["files"][0]["sha256"] == hashlib.sha256(raw).hexdigest()
    scope = json.loads((examples / "scope-review.json").read_text())
    assert len(scope["files"]) == len(report["files"])
    assert len(scope["seams"]) == len(report["seams"])
    assert json.loads((examples / "context.json").read_text())["outcome"] == "experimental_review_required"
    assert json.loads((examples / "negative-context.json").read_text())["outcome"] == "no_useful_placement"


def test_copied_example_identity_is_not_reusable_after_relocation(tmp_path):
    examples = ROOT / "examples/placement-selection"
    host = tmp_path / "copied-host"
    host.mkdir()
    (host / "opaque.py").write_bytes((examples / "host/opaque.py").read_bytes())
    report = json.loads((examples / "report.json").read_text())
    prepared = json.loads((examples / "prepared.json").read_text())
    review = json.loads((examples / "semantic-review.json").read_text())
    cfg = json.loads((examples / "config.json").read_text())
    with pytest.raises(cap.CapabilityError):
        selection.prepare_placement_context(host, report, prepared, review, cfg)
