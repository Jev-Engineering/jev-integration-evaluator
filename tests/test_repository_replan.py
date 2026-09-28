"""Bounded pre-effect replans preserve old decisions and require fresh scopes."""
from __future__ import annotations

import copy
import json
import os

import pytest

from jev_integration_evaluator import repository_run as run
from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.integrations import lifecycle as engine
from jev_integration_evaluator.integrations.errors import UnsupportedShape
from scripts.implementation_fixtures import fixture


pytestmark = pytest.mark.skipif(os.name != "posix", reason="secure sessions require POSIX")


def _inputs(root):
    inventory, spec = fixture(root, "C")
    return dict(schema_version="1.0", adapter=run.ADAPTER, inventory=inventory, spec=spec)


def _changed(data, timeout):
    value = copy.deepcopy(data)
    value["spec"]["verification"]["timeout_s"] = timeout
    return value


def _scope(root, context, result=None, *, reviewed_response=None, **grants):
    inspection = run.inspect_repository(root, context=context)
    return dict(schema_version="1.0", kind="repository-run-scope-v1",
                reference="synthetic-separate-operator-review",
                repository_identity=inspection["report"]["repository_identity"],
                context_sha256=inspection["context_sha256"],
                bundle_digest=result["bundle_digest"] if result else None,
                trusted_session_head=result["session_head_sha256"] if result else None,
                trusted_baseline_receipt=None, trusted_modified_receipt=None,
                rollback_digest=None, execution_environment="trusted_host",
                grants={**run.ZERO_GRANTS, **grants},
                prepared_sha256=cap._digest(reviewed_response) if reviewed_response else None)


def _head(session):
    return json.loads((session / "journal.jsonl").read_text().splitlines()[-1])["record_sha256"]


def test_replan_before_effect_retains_old_bundle_and_cannot_replan_after_effect(tmp_path):
    root, session = tmp_path / "target", tmp_path / "session"
    data = _inputs(root)
    context = run.request_context()
    first = run.run_repository(root, session, context=context, prepared=data,
                               scope=_scope(root, context, prepare=True), stop_after="plan")
    old_bundle = session / "implementation-bundle-1"
    assert old_bundle.is_dir()
    revised = _changed(data, 21)
    with pytest.raises(run.SessionError, match="prepared_review_changed_fresh_replan_required"):
        run.run_repository(root, session, prepared=revised)
    with pytest.raises(run.SessionError, match="replan_scope_must_bind_exact_prepared_response"):
        run.run_repository(root, session, prepared=revised,
                           scope=_scope(root, context, first,
                                        reviewed_response=_changed(data, 22), prepare=True),
                           replan=True)
    second = run.run_repository(root, session, prepared=revised,
                                scope=_scope(root, context, first, reviewed_response=revised, prepare=True,
                                             baseline=True, apply=True, modified=True),
                                replan=True)
    assert second["status"] == "missing_scope"
    assert second["stage"] == "planned"
    assert second["attempts"]["baseline"] == 0
    assert second["attempts"]["apply"] == 0
    assert second["run_id"] == first["run_id"]
    assert second["decision_epoch"] == 1
    assert second["attempts"]["plan"] == 2
    assert second["bundle_digest"] != first["bundle_digest"]
    assert second["replan_history"][0]["bundle"]["digest"] == first["bundle_digest"]
    assert old_bundle.is_dir()
    assert (session / "implementation-bundle-2").is_dir()
    with pytest.raises(run.SessionError, match="replan_scope_or_limit_unavailable"):
        run.run_repository(root, session, prepared=_changed(data, 22),
                           scope=_scope(root, context, second, reviewed_response=_changed(data, 22), prepare=True), replan=True)
    baseline = run.run_repository(root, session,
                                  scope=_scope(root, context, second, baseline=True),
                                  stop_after="baseline")
    assert baseline["status"] == "baseline_passed"
    with pytest.raises(run.SessionError, match="replan_after_effect_forbidden"):
        run.run_repository(root, session, prepared=_changed(data, 22),
                           scope=_scope(root, context, baseline, reviewed_response=_changed(data, 22), prepare=True), replan=True)


def test_completed_replan_is_adopted_after_crash_without_replanning(tmp_path, monkeypatch):
    root, session = tmp_path / "target", tmp_path / "session"
    data = _inputs(root)
    context = run.request_context()
    first = run.run_repository(root, session, context=context, prepared=data,
                               scope=_scope(root, context, prepare=True), stop_after="plan")
    revised = _changed(data, 21)
    original = engine.plan_implementation

    def finish_then_interrupt(*args, **kwargs):
        original(*args, **kwargs)
        raise KeyboardInterrupt()

    monkeypatch.setattr(engine, "plan_implementation", finish_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        run.run_repository(root, session, prepared=revised,
                           scope=_scope(root, context, first, reviewed_response=revised, prepare=True), replan=True)
    monkeypatch.setattr(engine, "plan_implementation",
                        lambda *args, **kwargs: pytest.fail("completed replan repeated"))
    assert (session / "implementation-bundle-1").is_dir()
    anchored = _scope(root, context, first, prepare=True)
    anchored["trusted_session_head"] = _head(session)
    recovered = run.run_repository(root, session, scope=anchored)
    assert recovered["status"] == "missing_scope"
    assert recovered["stage"] == "planned"
    assert recovered["decision_epoch"] == 1
    assert recovered["attempts"]["plan"] == 2
    assert recovered["replan_history"][0]["bundle"]["digest"] == first["bundle_digest"]


def test_incomplete_replan_preserves_output_and_needs_bounded_retry(tmp_path, monkeypatch):
    root, session = tmp_path / "target", tmp_path / "session"
    data = _inputs(root)
    context = run.request_context(bounds={**run.DEFAULT_BOUNDS, "max_attempts": 3})
    first = run.run_repository(root, session, context=context, prepared=data,
                               scope=_scope(root, context, prepare=True), stop_after="plan")
    revised = _changed(data, 21)
    original = engine.plan_implementation

    def interrupt_before_plan(*args, **kwargs):
        out = args[4]
        out.mkdir(mode=0o700)
        (out / "incomplete").write_text("private partial plan")
        raise KeyboardInterrupt()

    monkeypatch.setattr(engine, "plan_implementation", interrupt_before_plan)
    with pytest.raises(KeyboardInterrupt):
        run.run_repository(root, session, prepared=revised,
                           scope=_scope(root, context, first, reviewed_response=revised, prepare=True), replan=True)
    monkeypatch.setattr(engine, "plan_implementation", original)
    anchored = _scope(root, context, first, prepare=True)
    anchored["trusted_session_head"] = _head(session)
    blocked = run.run_repository(root, session, scope=anchored)
    assert blocked["status"] == "blocked_recovery"
    retried = run.run_repository(root, session, prepared=revised,
                                 scope=_scope(root, context, blocked, prepare=True),
                                 retry=True, stop_after="plan")
    assert retried["status"] == "planned"
    assert retried["attempts"]["plan"] == 3
    assert retried["decision_epoch"] == 1
    assert (session / "implementation-bundle-2" / "incomplete").is_file()
    assert (session / "implementation-bundle-1").is_dir()


def test_failed_plan_can_replan_but_pending_effect_cannot(tmp_path, monkeypatch):
    root, session = tmp_path / "target", tmp_path / "session"
    data = _inputs(root)
    context = run.request_context()
    original = engine.plan_implementation
    monkeypatch.setattr(engine, "plan_implementation",
                        lambda *args, **kwargs: (_ for _ in ()).throw(UnsupportedShape("synthetic shape")))
    failed = run.run_repository(root, session, context=context, prepared=data,
                                scope=_scope(root, context, prepare=True))
    assert failed["status"] == "unsupported"
    monkeypatch.setattr(engine, "plan_implementation", original)
    revised = _changed(data, 21)
    replanned = run.run_repository(root, session, prepared=revised,
                                   scope=_scope(root, context, failed, reviewed_response=revised, prepare=True),
                                   replan=True, stop_after="plan")
    assert replanned["status"] == "planned"
    assert replanned["replan_history"][0]["stage"] == "plan_failed"
    assert replanned["failed_attempts"] == 1

    original_verify = run.verify_implementation
    monkeypatch.setattr(run, "verify_implementation",
                        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        run.run_repository(root, session,
                           scope=_scope(root, context, replanned, baseline=True),
                           stop_after="baseline")
    monkeypatch.setattr(run, "verify_implementation", original_verify)
    pending_scope = _scope(root, context, replanned, reviewed_response=_changed(data, 22), prepare=True)
    pending_scope["trusted_session_head"] = _head(session)
    with pytest.raises(run.SessionError, match="replan_after_effect_forbidden"):
        run.run_repository(root, session, prepared=_changed(data, 22),
                           scope=pending_scope, replan=True)


def test_replan_rejects_source_drift_without_changing_decision_epoch(tmp_path):
    root, session = tmp_path / "target", tmp_path / "session"
    data = _inputs(root)
    context = run.request_context()
    first = run.run_repository(root, session, context=context, prepared=data,
                               scope=_scope(root, context, prepare=True), stop_after="plan")
    source = root / data["spec"]["source"]["file"]
    source.write_text(source.read_text() + "# changed after review\n")
    with pytest.raises(run.SessionError, match="source_drift_decisions_invalidated"):
        run.run_repository(root, session, prepared=_changed(data, 21),
                           scope=_scope(root, context, first, reviewed_response=_changed(data, 21), prepare=True), replan=True)
    journal_state = json.loads((session / "journal.jsonl").read_text().splitlines()[-1])["state"]
    assert journal_state["decision_epoch"] == 0
    assert journal_state["replan_history"] == []
