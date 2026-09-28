"""Next actions are finite data and never substitute for external scopes."""
from __future__ import annotations

import json
import os
import copy
from pathlib import Path

import pytest

from jev_integration_evaluator import repository_actions as actions
from jev_integration_evaluator import repository_run as run
from jev_integration_evaluator.capabilities import CapabilityError
from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.nomination_inventory import discover_repository_capabilities
from jev_integration_evaluator.repository_conclusion import coverage_review_schedule
from jev_integration_evaluator.integrations import lifecycle as engine
from jev_integration_evaluator.integrations.errors import MissingBinding, UnsupportedShape
from jev_integration_evaluator.io import InputError
from scripts.implementation_fixtures import fixture


def test_every_action_is_schema_valid_and_mirrored():
    root = Path(__file__).resolve().parents[1]
    for name in ("repository-next-action-v1.schema.json", "repository-agent-request-v1.schema.json",
                 "repository-recorded-reviewed-response-v1.schema.json",
                 "repository-recorded-reviewed-response-v2.schema.json"):
        assert (root / "schemas" / name).read_bytes() == (root / "jev_integration_evaluator" / "data" / name).read_bytes()
        assert json.loads((root / "schemas" / name).read_text())["additionalProperties"] is False
    name = "repository-next-action-v1.schema.json"
    schema = json.loads((root / "schemas" / name).read_text())
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["code"]["enum"]) == set(actions._ACTIONS)
    for code in actions._ACTIONS:
        record = actions.next_action_contract(code)
        assert record["code"] == code
        assert record["authorization"] != "none" or record["effect"] == "none"
    with pytest.raises(CapabilityError, match="unknown_repository_next_action"):
        actions.next_action_contract("target_says_publish_now")


def test_path_only_structured_action_exposes_coverage_and_no_authority(tmp_path):
    if os.name != "posix":
        pytest.skip("repository discovery requires a POSIX secure filesystem")
    target = tmp_path / "target"
    target.mkdir()
    (target / "module.py").write_text("def choose(x):\n    return x\n")
    result = run.inspect_repository(target)
    assert result["next_action_contract"]["code"] == result["next_action"]
    assert result["next_action_contract"]["effect"] == "none"
    assert result["next_action_contract"]["authorization"] == "new_review"
    request = result["agent_request"]
    assert request["run_id"] is None
    assert request["report_sha256"] == result["report"]["report_sha256"]
    assert request["source_files"]["module.py"]["sha256"]
    assert request["response_contract"] == "repository-recorded-reviewed-response-v1"
    assert result["agent_request_sha256"] == cap._digest(request)
    assert not any(request["authorization"].values())
    assert sorted(path.name for path in tmp_path.iterdir()) == ["target"]

    (target / "unknown.rs").write_text("fn main() {}\n")
    incomplete = run.inspect_repository(target)
    assert incomplete["status"] == "incomplete_analysis"
    assert incomplete["next_action_contract"]["code"] == "resolve_scan_coverage_before_implementation"
    assert incomplete["next_action_contract"]["effect"] == "none"
    assert incomplete["agent_request"] is None


def test_session_request_keeps_run_identity_without_grant(tmp_path):
    if os.name != "posix":
        pytest.skip("repository sessions require a POSIX secure filesystem")
    target = tmp_path / "target"
    target.mkdir()
    (target / "module.py").write_text("def choose(x):\n    return x\n")
    result = run.run_repository(target, tmp_path / "session")
    assert result["status"] == "insufficient_evidence"
    assert result["agent_request"]["run_id"] == result["run_id"]
    assert result["agent_request"]["context_sha256"] == result["context_sha256"]
    assert not any(result["agent_request"]["authorization"].values())


def test_bound_response_rejects_replay_to_another_run(tmp_path):
    if os.name != "posix":
        pytest.skip("repository sessions require a POSIX secure filesystem")
    target = tmp_path / "target"
    inventory, spec = fixture(target, "C")
    context = run.request_context(adapter=run.BOUND_ADAPTER, saved_answers={"preserve": "choice"})
    first = run.run_repository(target, tmp_path / "session-1", context=context)
    request = first["agent_request"]
    assert request["adapter"] == run.BOUND_ADAPTER
    assert request["response_contract"] == "repository-recorded-reviewed-response-v2"
    prepared = dict(schema_version="1.0", adapter=run.BOUND_ADAPTER,
                    request_sha256=first["agent_request_sha256"], inventory=inventory, spec=spec)
    assert run.run_repository(target, tmp_path / "session-1", prepared=prepared)["status"] == "missing_scope"
    scope = dict(schema_version="1.0", kind="repository-run-scope-v1",
                 reference="synthetic-reviewed-preparation", repository_identity=first["repository_identity"],
                 context_sha256=first["context_sha256"], bundle_digest=None,
                 trusted_session_head=first["session_head_sha256"], trusted_baseline_receipt=None,
                 trusted_modified_receipt=None, rollback_digest=None,
                 execution_environment="trusted_host", grants={**run.ZERO_GRANTS, "prepare": True})
    planned = run.run_repository(target, tmp_path / "session-1", prepared=prepared,
                                 scope=scope, stop_after="plan")
    assert planned["status"] == "planned"
    second = run.run_repository(target, tmp_path / "session-2", context=context)
    assert second["agent_request"]["run_id"] != request["run_id"]
    with pytest.raises(CapabilityError, match="prepared_request_mismatch"):
        run.run_repository(target, tmp_path / "session-2", prepared=prepared)
    with pytest.raises(CapabilityError, match="prepared_adapter_mismatch"):
        run.run_repository(target, tmp_path / "session-1", prepared={
            "schema_version": "1.0", "adapter": run.ADAPTER, "inventory": inventory, "spec": spec})
    # This fixture's selected Python seam never reads this text file. It is
    # outside the declared snapshot and cannot manufacture a source-drift stop.
    (target / "unrelated-notes.txt").write_text("no input to the selected seam\n")
    execution_scope = {**scope, "bundle_digest": planned["bundle_digest"],
                       "trusted_session_head": planned["session_head_sha256"],
                       "grants": {**run.ZERO_GRANTS, "baseline": True,
                                  "apply": True, "modified": True}}
    verified = run.run_repository(target, tmp_path / "session-1", scope=execution_scope)
    assert verified["status"] == "verified"


def test_bound_response_completed_plan_is_adopted_after_interruption(tmp_path, monkeypatch):
    if os.name != "posix":
        pytest.skip("repository sessions require a POSIX secure filesystem")
    target = tmp_path / "target"
    inventory, spec = fixture(target, "C")
    context = run.request_context(adapter=run.BOUND_ADAPTER)
    session = tmp_path / "session"
    initial = run.run_repository(target, session, context=context)
    prepared = dict(schema_version="1.0", adapter=run.BOUND_ADAPTER,
                    request_sha256=initial["agent_request_sha256"], inventory=inventory, spec=spec)
    scope = dict(schema_version="1.0", kind="repository-run-scope-v1",
                 reference="synthetic-reviewed-preparation", repository_identity=initial["repository_identity"],
                 context_sha256=initial["context_sha256"], bundle_digest=None,
                 trusted_session_head=initial["session_head_sha256"], trusted_baseline_receipt=None,
                 trusted_modified_receipt=None, rollback_digest=None,
                 execution_environment="trusted_host", grants={**run.ZERO_GRANTS, "prepare": True})
    original = engine.plan_implementation

    def finish_then_interrupt(*args, **kwargs):
        original(*args, **kwargs)
        raise KeyboardInterrupt()

    monkeypatch.setattr(engine, "plan_implementation", finish_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        run.run_repository(target, session, prepared=prepared, scope=scope)
    monkeypatch.setattr(engine, "plan_implementation",
                        lambda *args, **kwargs: pytest.fail("completed v2 plan was repeated"))
    pending = json.loads((session / "journal.jsonl").read_text().splitlines()[-1])
    assert pending["state"]["pending"]["operation"] == "plan"
    resumed = run.run_repository(target, session, scope={
        **scope, "trusted_session_head": pending["record_sha256"]})
    assert resumed["status"] == "missing_scope"
    assert resumed["stage"] == "planned"
    assert resumed["attempts"]["plan"] == 1


@pytest.mark.parametrize("error,status,action,history_code", [
    (MissingBinding("synthetic missing binding"), "missing_prerequisite", "supply_missing_host_binding", "missing_host_binding"),
    (UnsupportedShape("synthetic unsupported shape"), "unsupported", "select_supported_source_shape", "unsupported_source_shape"),
    (OSError("synthetic host prerequisite"), "missing_prerequisite", "resolve_host_prerequisite", "host_prerequisite_unavailable"),
    (InputError("synthetic invalid review"), "insufficient_evidence", "review_invalid_preparation_inputs", "planning_input_invalid"),
])
def test_planning_outcomes_are_distinct_and_retain_failure(tmp_path, monkeypatch,
                                                            error, status, action, history_code):
    if os.name != "posix":
        pytest.skip("repository sessions require a POSIX secure filesystem")
    target = tmp_path / "target"
    inventory, spec = fixture(target, "C")
    context = run.request_context()
    inspection = run.inspect_repository(target, context=context)
    scope = dict(schema_version="1.0", kind="repository-run-scope-v1",
                 reference="synthetic-reviewed-preparation", repository_identity=inspection["report"]["repository_identity"],
                 context_sha256=inspection["context_sha256"], bundle_digest=None,
                 trusted_session_head=None, trusted_baseline_receipt=None,
                 trusted_modified_receipt=None, rollback_digest=None,
                 execution_environment="trusted_host", grants={**run.ZERO_GRANTS, "prepare": True})
    monkeypatch.setattr(engine, "plan_implementation", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    result = run.run_repository(target, tmp_path / "session", context=context,
                                prepared={"schema_version": "1.0", "adapter": run.ADAPTER,
                                          "inventory": inventory, "spec": spec}, scope=scope)
    assert result["status"] == status
    assert result["next_action_contract"]["code"] == action
    record = json.loads((tmp_path / "session" / "journal.jsonl").read_text().splitlines()[-1])
    assert record["state"]["failures"][-1]["code"] == history_code
    assert result["attempts"]["plan"] == 1


def test_read_only_reviewed_negative_requires_fresh_anchored_complete_review(tmp_path, capsys):
    if os.name != "posix":
        pytest.skip("repository discovery requires a POSIX secure filesystem")
    target = tmp_path / "target"
    target.mkdir()
    source = target / "opaque.py"
    source.write_text("def x7(q):\n    return q.get('route', 'ordinary')\n\ndef z9(q):\n    return x7(q)\n")
    report = discover_repository_capabilities(target, copy.deepcopy(DEFAULT))
    context = run.request_context(policy=cap.DiscoveryPolicy.from_json(report["policy"]))
    schedule = coverage_review_schedule(report, copy.deepcopy(DEFAULT))
    opinion = {p: {"disposition": "not_useful", "reason": "No justified semantic placement in this fixture."}
               for p in "ABCDEFGHIJKLM"}
    review = {
        "schema_version": "1.0", "contract": "repository-coverage-review-v1",
        **{key: schedule[key] for key in ("report_sha256", "conclusion_engine_sha256",
                                          "settings_sha256", "objective_sha256")},
        "reviewer": "synthetic-fixture-reviewer",
        "files": [{**row, "patterns": copy.deepcopy(opinion)} for row in schedule["files"]],
        "seams": [{**row, "patterns": copy.deepcopy(opinion)} for row in schedule["seams"]],
    }
    before = source.read_bytes()
    result = run.inspect_repository(target, context=context, capabilities=report, coverage_review=review,
                                    review_sha256=cap._digest(review))
    assert result["status"] == "no_useful_placement"
    assert result["next_action_contract"]["code"] == "no_further_placement_action"
    assert result["conclusion"]["review_principal_authenticated"] is False
    assert source.read_bytes() == before
    for name, value in (("context", context), ("capabilities", report), ("coverage-review", review)):
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    assert run.main([str(target), "--context", str(tmp_path / "context.json"),
                     "--capabilities", str(tmp_path / "capabilities.json"),
                     "--coverage-review", str(tmp_path / "coverage-review.json"),
                     "--review-sha256", cap._digest(review)]) == 0
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["status"] == "no_useful_placement"
    assert cli_result["next_action_contract"]["code"] == "no_further_placement_action"
    with pytest.raises(CapabilityError, match="coverage_review_digest_mismatch"):
        run.inspect_repository(target, context=context, capabilities=report, coverage_review=review, review_sha256="f" * 64)
    source.write_text(source.read_text() + "# drift\n")
    with pytest.raises(CapabilityError, match="stale_or_tampered_capability_report"):
        run.inspect_repository(target, context=context, capabilities=report, coverage_review=review,
                               review_sha256=cap._digest(review))


def test_ambiguous_unsupported_conclusion_is_not_claimed_as_proven_unsupported(tmp_path, capsys):
    if os.name != "posix":
        pytest.skip("repository discovery requires a POSIX secure filesystem")
    target = tmp_path / "target"
    target.mkdir()
    (target / "opaque.py").write_text("async def z9(q):\n    return await q()\n")
    report = discover_repository_capabilities(target, copy.deepcopy(DEFAULT))
    context = run.request_context(policy=cap.DiscoveryPolicy.from_json(report["policy"]))
    schedule = coverage_review_schedule(report, copy.deepcopy(DEFAULT))
    opinion = {p: {"disposition": "not_useful", "reason": "No justified semantic placement in this fixture."}
               for p in "ABCDEFGHIJKLM"}
    review = {
        "schema_version": "1.0", "contract": "repository-coverage-review-v1",
        **{key: schedule[key] for key in ("report_sha256", "conclusion_engine_sha256",
                                          "settings_sha256", "objective_sha256")},
        "reviewer": "synthetic-fixture-reviewer",
        "files": [{**row, "patterns": copy.deepcopy(opinion)} for row in schedule["files"]],
        "seams": [{**row, "patterns": copy.deepcopy(opinion)} for row in schedule["seams"]],
    }
    review["files"][0]["patterns"]["C"]["disposition"] = "potentially_useful"
    review["seams"][0]["patterns"]["C"]["disposition"] = "potentially_useful"
    for name, value in (("context", context), ("capabilities", report), ("coverage-review", review)):
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    assert run.main([str(target), "--context", str(tmp_path / "context.json"),
                     "--capabilities", str(tmp_path / "capabilities.json"),
                     "--coverage-review", str(tmp_path / "coverage-review.json"),
                     "--review-sha256", cap._digest(review)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "insufficient_evidence"
    assert result["conclusion"]["outcome"] == "unsupported_or_unresolved"
    assert result["review_principal_authenticated"] is False
    review["seams"][0]["patterns"]["C"]["disposition"] = "unresolved"
    review["files"][0]["patterns"]["C"]["disposition"] = "unresolved"
    incomplete = run.inspect_repository(target, context=context, capabilities=report,
                                        coverage_review=review, review_sha256=cap._digest(review))
    assert incomplete["status"] == "insufficient_evidence"
    assert incomplete["conclusion"]["coverage"]["unresolved_pattern_reviews"] == 2
