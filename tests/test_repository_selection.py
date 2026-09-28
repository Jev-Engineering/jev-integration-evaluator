"""Durable selection checks use only disposable synthetic host source."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from jev_integration_evaluator.io import digest
from jev_integration_evaluator.repository_run import (
    ADAPTER, ZERO_GRANTS, SessionError, inspect_repository, request_context, run_repository,
)
from jev_integration_evaluator.selection import selection_engine_sha256, request_sha256
from scripts.implementation_fixtures import fixture


def _input(tmp_path):
    root = tmp_path / "host"
    inventory, spec = fixture(root, "C", tag="repository_selection")
    request = {
        "schema_version": "1.0", "selection_engine_sha256": selection_engine_sha256(),
        "mode": "experimental", "inventory_sha256": digest(inventory),
        "candidate_id": spec["candidate_id"],
        "decision_review": {"reviewer": "synthetic-test", "reason": "Offline experiment",
                            "evidence_refs": ["synthetic-fixture"]},
        "preparation_scope_ref": "synthetic-local-preparation",
        "implementation_spec_sha256": digest(spec), "constraints": None,
        "live_limits": {"max_total_cost": None, "max_total_calls": None,
                        "max_concurrent_calls": None},
    }
    return root, {"schema_version": "1.0", "kind": "inventory-selection-v1",
                  "inventory": inventory, "request": request}, request_sha256(request), spec


def test_selection_is_saved_and_recomputed_on_resume(tmp_path):
    root, selection, approval, _ = _input(tmp_path)
    session = tmp_path / "session"
    first = run_repository(root, session, selection=selection,
                           approved_selection_sha256=approval)
    assert first["status"] == "insufficient_evidence"
    assert first["selection_record"]["status"] == "experimental_selected"
    resumed = run_repository(root, session)
    assert resumed["selection_record"] == first["selection_record"]
    assert resumed["run_id"] == first["run_id"]


def test_selection_without_external_review_cannot_select(tmp_path):
    root, selection, approval, _ = _input(tmp_path)
    session = tmp_path / "session"
    result = run_repository(root, session, selection=selection)
    assert result["status"] == "selection_review_required"
    assert result["selection_record"]["approved_request_sha256"] is None
    promoted = run_repository(root, session, approved_selection_sha256=approval)
    assert promoted["run_id"] == result["run_id"]
    assert promoted["selection_record"]["status"] == "experimental_selected"
    assert promoted["selection_record"]["sha256"] == result["selection_record"]["sha256"]
    assert run_repository(root, session)["selection_record"] == promoted["selection_record"]


def test_source_change_marks_retained_selection_stale(tmp_path):
    root, selection, approval, _ = _input(tmp_path)
    session = tmp_path / "session"
    first = run_repository(root, session, selection=selection,
                           approved_selection_sha256=approval)
    source = root / selection["inventory"]["files"][0]["file"]
    source.write_bytes(source.read_bytes() + b"\n# synthetic drift\n")
    stale = run_repository(root, session)
    assert stale["status"] == "stale_selection"
    assert stale["run_id"] == first["run_id"]


def test_no_useful_inventory_is_scoped_to_reviewed_inventory(tmp_path):
    root, selection, _, _ = _input(tmp_path)
    inventory = copy.deepcopy(selection["inventory"])
    for candidate in inventory["candidates"]:
        candidate["semantic_review"] = {
            "approved": False, "reviewer": "synthetic-independent-rejection",
            "reason": "Synthetic deterministic alternative meets the objective",
            "source_sha256": candidate["source"]["source_sha256"],
        }
    selection["inventory"] = inventory
    selection["request"]["mode"] = "optimize"
    selection["request"]["candidate_id"] = None
    selection["request"]["decision_review"] = None
    selection["request"]["preparation_scope_ref"] = None
    selection["request"]["implementation_spec_sha256"] = None
    from jev_integration_evaluator.config import load_config
    selection["request"]["constraints"] = load_config()["constraints"]
    selection["request"]["inventory_sha256"] = digest(inventory)
    result = run_repository(root, tmp_path / "session", selection=selection)
    assert result["status"] == "no_useful_placement_within_reviewed_inventory"


@pytest.mark.parametrize("outcome", ["no_candidates_in_supplied_inventory", "deterministic_rejection",
                                     "incomplete_analysis", "stale_semantic_review",
                                     "insufficient_estimates", "estimate_based_optimization"])
def test_repository_command_retains_distinct_inventory_outcomes(tmp_path, outcome):
    from jev_integration_evaluator.config import load_config
    from jev_integration_evaluator.optimizer import REQUIRED
    root, selection, _, _ = _input(tmp_path)
    inventory, request = selection["inventory"], selection["request"]
    request.update(mode="optimize", candidate_id=None, decision_review=None,
                   preparation_scope_ref=None, implementation_spec_sha256=None,
                   constraints=load_config()["constraints"])
    if outcome == "no_candidates_in_supplied_inventory":
        inventory["candidates"] = []
        inventory["interactions"] = []
    elif outcome == "deterministic_rejection":
        for candidate in inventory["candidates"]:
            candidate["tier"] = 0
    elif outcome == "incomplete_analysis":
        inventory["coverage"]["truncated"] = True
        inventory["analysis_identity"]["coverage_digest"] = digest(inventory["coverage"])
        inventory["scan_fingerprint"] = digest(inventory["analysis_identity"])
    elif outcome == "stale_semantic_review":
        for candidate in inventory["candidates"]:
            candidate["semantic_review"]["source_sha256"] = "a" * 64
    elif outcome == "estimate_based_optimization":
        for candidate in inventory["candidates"]:
            candidate["estimates"].update({key: 0.0 for key in REQUIRED})
            candidate["estimates"].update(quality_gain=0.3, reliability_gain=0.1,
                                           throughput=100, provenance="Synthetic declared assumptions")
    request["inventory_sha256"] = digest(inventory)
    result = run_repository(root, tmp_path / "session", selection=selection)
    assert result["status"] == outcome
    assert result["benefit_demonstrated"] is False
    assert result["runtime_activation_authorized"] is False


def test_selected_experiment_binds_exact_planner_input(tmp_path):
    root, selection, approval, spec = _input(tmp_path)
    session = tmp_path / "session"
    spec = copy.deepcopy(spec)
    spec["experiment_id"] += "-changed-after-review"
    # A locally modified specification must be refused before plan.
    prepared = {"schema_version": "1.0", "adapter": ADAPTER,
                "inventory": selection["inventory"], "spec": spec}
    report = inspect_repository(root)
    scope = {"schema_version": "1.0", "kind": "repository-run-scope-v1",
             "reference": "synthetic-local-operator", "repository_identity": report["report"]["repository_identity"],
             "context_sha256": report["context_sha256"], "bundle_digest": None,
             "trusted_session_head": None, "trusted_baseline_receipt": None,
             "trusted_modified_receipt": None, "rollback_digest": None,
             "execution_environment": "trusted_host", "grants": {**ZERO_GRANTS, "prepare": True}}
    with pytest.raises(SessionError, match="prepared_specification_does_not_match_selection"):
        run_repository(root, session, selection=selection,
                       approved_selection_sha256=approval, prepared=prepared, scope=scope)


def test_selected_experiment_prepares_existing_lifecycle_bundle(tmp_path):
    root, selection, approval, spec = _input(tmp_path)
    report = inspect_repository(root)
    scope = {"schema_version": "1.0", "kind": "repository-run-scope-v1",
             "reference": "synthetic-local-operator", "repository_identity": report["report"]["repository_identity"],
             "context_sha256": report["context_sha256"], "bundle_digest": None,
             "trusted_session_head": None, "trusted_baseline_receipt": None,
             "trusted_modified_receipt": None, "rollback_digest": None,
             "execution_environment": "trusted_host", "grants": {**ZERO_GRANTS, "prepare": True}}
    prepared = {"schema_version": "1.0", "adapter": ADAPTER,
                "inventory": selection["inventory"], "spec": spec}
    planned = run_repository(root, tmp_path / "session", selection=selection,
                             approved_selection_sha256=approval, prepared=prepared,
                             scope=scope, stop_after="plan")
    assert planned["status"] == "planned"
    assert planned["bundle_digest"]
    assert planned["selection_record"]["status"] == "experimental_selected"
    execution = {**scope, "bundle_digest": planned["bundle_digest"],
                 "trusted_session_head": planned["session_head_sha256"],
                 "grants": {**ZERO_GRANTS, "baseline": True, "apply": True,
                            "modified": True}}
    finished = run_repository(root, tmp_path / "session", scope=execution)
    assert finished["status"] == "verified"
    assert finished["selection_record"] == planned["selection_record"]
    readback = run_repository(root, tmp_path / "session", scope={
        **execution, "trusted_session_head": finished["session_head_sha256"]})
    assert readback["status"] == "verified"


def test_whole_source_review_negative_is_exposed_and_revalidated(tmp_path):
    from jev_integration_evaluator import capabilities as cap
    from jev_integration_evaluator import nomination_inventory as bridge
    from jev_integration_evaluator import placement_selection as source_selection
    from jev_integration_evaluator.config import DEFAULT
    root = tmp_path / "source-host"
    root.mkdir()
    (root / "opaque.py").write_text(
        'def b(x):\n    return x["operation"](x)\n\ndef q(x):\n    return b(x)\n', encoding="utf-8")
    cfg = copy.deepcopy(DEFAULT)
    cfg["repository"]["typescript_ast"] = False
    defaults = cap.DiscoveryPolicy()
    selected_policy = replace(
        defaults,
        max_files=min(defaults.max_files, cfg["repository"]["max_files"]),
        max_file_bytes=min(defaults.max_file_bytes, cfg["repository"]["max_file_bytes"]),
    )
    report = bridge.discover_repository_capabilities(root, cfg, policy=selected_policy)
    seam = next(s for s in report["seams"] if s["source"]["qualified_symbol"] == "q")
    proposal = {"schema_version": "1.0", "discovery_version": cap.VERSION,
                "report_sha256": report["report_sha256"], "seam_id": seam["seam_id"],
                "source": copy.deepcopy(seam["source"]), "pattern": "C",
                "proposer": "synthetic-fixture-author", "rationale": "Finite local policy experiment",
                "evidence": [{"file": seam["source"]["file"],
                              "file_sha256": seam["source"]["file_sha256"],
                              "start_line": seam["source"]["start_line"],
                              "end_line": seam["source"]["end_line"]}]}
    prepared = bridge.prepare_nominated_inventory(root, report, [proposal], cfg,
                                                  policy=selected_policy)
    reviews = {c["candidate_id"]: {"source_sha256": c["source"]["source_sha256"],
                "approved": False, "reviewer": "synthetic-reviewer",
                "reason": "The finite deterministic alternative suffices in this fixture"}
               for c in prepared["inventory"]["candidates"]}
    semantic = {"schema_version": "1.0", "prepared_sha256": prepared["prepared_sha256"],
                "reviews": reviews}
    scope = {"schema_version": "1.0", "contract": source_selection.SCOPE_REVIEW,
             "report_sha256": report["report_sha256"],
             "prepared_sha256": prepared["prepared_sha256"],
             "reviewer": "synthetic-scope-reviewer", "reason": "Entire synthetic source reviewed",
             "pattern_scope": source_selection.PATTERN_SCOPE,
             "snapshot_scope": report["snapshot_scope"],
             "files": [{"file": f["file"], "file_sha256": f["sha256"],
                        "line_count": f["line_count"], "coverage": "entire_file",
                        "disposition": "no_useful_placement", "reason": "No useful A-M placement"}
                       for f in report["files"]],
             "seams": [{"seam_id": s["seam_id"], "source": copy.deepcopy(s["source"]),
                        "disposition": "no_useful_placement", "reason": "Reviewed exact seam"}
                       for s in report["seams"]]}
    selection = {"schema_version": "1.0", "kind": "source-selection-v1",
                 "report": report, "prepared": prepared, "semantic_review": semantic,
                 "settings": cfg, "scope_review": scope, "selection_review": None}
    from jev_integration_evaluator.repository_selection import assess_selection
    frozen = json.loads(cap._json(selection))
    reconstructed = bridge.prepare_nominated_inventory(
        root, frozen["report"], frozen["prepared"]["nominations"],
        frozen["settings"], policy=selected_policy)
    def differing_paths(left, right, path=""):
        if isinstance(left, dict) and isinstance(right, dict):
            return [child for key in sorted(set(left) | set(right))
                    for child in differing_paths(left.get(key), right.get(key), path + "/" + str(key))]
        if isinstance(left, list) and isinstance(right, list):
            return [child for index in range(max(len(left), len(right)))
                    for child in differing_paths(left[index] if index < len(left) else None,
                                                 right[index] if index < len(right) else None,
                                                 path + "/" + str(index))]
        return [path] if left != right else []
    assert reconstructed == frozen["prepared"], differing_paths(reconstructed, frozen["prepared"])
    assert selected_policy == cap.DiscoveryPolicy.from_json(report["policy"])
    assert assess_selection(root, selection, policy=selected_policy)["status"] == "no_useful_placement"
    with pytest.raises(cap.CapabilityError, match="selection_policy_differs_from_session"):
        assess_selection(root, selection, policy=cap.DiscoveryPolicy())
    wrong_session = tmp_path / "wrong-policy-session"
    with pytest.raises(SessionError, match="invalid_or_stale_new_selection"):
        run_repository(root, wrong_session, selection=selection)
    assert not list(wrong_session.glob("selection-*.json"))
    session = tmp_path / "source-session"
    context = request_context(policy=selected_policy)
    result = run_repository(root, session, selection=selection, context=context)
    assert result["status"] == "no_useful_placement"
    assert run_repository(root, session)["status"] == "no_useful_placement"
    (root / "opaque.py").write_text((root / "opaque.py").read_text() + "\n# changed\n")
    assert run_repository(root, session)["status"] == "stale_selection"


@pytest.mark.parametrize("stage", ["planned", "verified"])
def test_selection_cannot_be_injected_after_bundle_or_effect(tmp_path, stage):
    root, selection, approval, spec = _input(tmp_path)
    session = tmp_path / "session"
    inspection = inspect_repository(root)
    scope = {"schema_version": "1.0", "kind": "repository-run-scope-v1",
             "reference": "synthetic-local-operator",
             "repository_identity": inspection["report"]["repository_identity"],
             "context_sha256": inspection["context_sha256"], "bundle_digest": None,
             "trusted_session_head": None, "trusted_baseline_receipt": None,
             "trusted_modified_receipt": None, "rollback_digest": None,
             "execution_environment": "trusted_host", "grants": {**ZERO_GRANTS, "prepare": True}}
    prepared = {"schema_version": "1.0", "adapter": ADAPTER,
                "inventory": selection["inventory"], "spec": spec}
    planned = run_repository(root, session, prepared=prepared, scope=scope, stop_after="plan")
    assert planned["status"] == "planned"
    if stage == "verified":
        execution = {**scope, "bundle_digest": planned["bundle_digest"],
                     "trusted_session_head": planned["session_head_sha256"],
                     "grants": {**ZERO_GRANTS, "baseline": True, "apply": True,
                                "modified": True}}
        assert run_repository(root, session, scope=execution)["status"] == "verified"
    journal_before = (session / "journal.jsonl").read_bytes()
    source_before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(SessionError, match="selection_must_precede_planning_and_effects"):
        run_repository(root, session, selection=selection,
                       approved_selection_sha256=approval)
    assert (session / "journal.jsonl").read_bytes() == journal_before
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == source_before


@pytest.mark.parametrize("entry", ["module", "central", "script"])
def test_public_repository_commands_accept_selection_file(tmp_path, entry):
    root, selection, _, _ = _input(tmp_path)
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection), encoding="utf-8")
    source = Path(__file__).resolve().parents[1]
    commands = {
        "module": [sys.executable, "-m", "jev_integration_evaluator.repository_run"],
        "central": [sys.executable, "-m", "jev_integration_evaluator", "repository-run"],
        "script": [sys.executable, str(source / "scripts" / "run_repository.py")],
    }
    result = subprocess.run([*commands[entry], str(root), "--session", str(tmp_path / "session"),
                             "--selection", str(selection_path)], cwd=source,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["status"] == "selection_review_required"
    assert value["selection_record"]["path"] == "inventory"
