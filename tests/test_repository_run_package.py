"""Repository sessions preserve package-binding evidence through real stages."""
from __future__ import annotations

import os

import pytest

from jev_integration_evaluator import repository_run as run
from jev_integration_evaluator.integrations import lifecycle as engine
from scripts.implementation_fixtures import fixture


pytestmark = pytest.mark.skipif(os.name != "posix", reason="secure sessions require POSIX")


def _scope(root, context, *, result=None, bundle_digest=None, **grants):
    inspection = run.inspect_repository(root, context=context)
    return dict(schema_version="1.0", kind="repository-run-scope-v1",
                reference="synthetic-package-binding-operator-review",
                repository_identity=inspection["report"]["repository_identity"],
                context_sha256=inspection["context_sha256"],
                bundle_digest=bundle_digest,
                trusted_session_head=result["session_head_sha256"] if result else None,
                trusted_baseline_receipt=None, trusted_modified_receipt=None,
                rollback_digest=None, execution_environment="trusted_host",
                grants={**run.ZERO_GRANTS, **grants})


def _package(root, bundle, tag):
    inventory, spec = fixture(root, "C", layout="src", tag=tag)
    planned = engine.plan_implementation(root, inventory, spec["candidate_id"], spec, bundle)
    assert spec["package_binding"]["module"].startswith("fixture_pkg.")
    return planned["bundle_digest"]


def test_package_binding_one_invocation_resume_and_contributing_source_drift(tmp_path):
    context = run.request_context(objective="Evaluate the reviewed package seam")

    direct_root, direct_bundle = tmp_path / "direct-target", tmp_path / "direct-bundle"
    direct_digest = _package(direct_root, direct_bundle, "session_direct")
    direct_session = tmp_path / "direct-session"
    direct = run.run_repository(direct_root, direct_session, context=context, bundle=direct_bundle,
                                scope=_scope(direct_root, context, bundle_digest=direct_digest,
                                             baseline=True, apply=True, modified=True))
    assert direct["status"] == "verified"
    assert direct["attempts"]["baseline"] == 1
    assert direct["attempts"]["apply"] == 1
    assert direct["attempts"]["modified"] == 1
    assert run.run_repository(direct_root, direct_session)["status"] == "recorded_untrusted"
    anchored = run.run_repository(direct_root, direct_session,
                                  scope=_scope(direct_root, context, result=direct,
                                               bundle_digest=direct_digest))
    assert anchored["status"] == "verified"
    assert anchored["run_id"] == direct["run_id"]
    assert anchored["attempts"] == direct["attempts"]

    staged_root, staged_bundle = tmp_path / "staged-target", tmp_path / "staged-bundle"
    staged_digest = _package(staged_root, staged_bundle, "session_staged")
    staged_session = tmp_path / "staged-session"
    baseline = run.run_repository(staged_root, staged_session, context=context, bundle=staged_bundle,
                                  scope=_scope(staged_root, context, bundle_digest=staged_digest,
                                               baseline=True), stop_after="baseline")
    assert baseline["status"] == "baseline_passed"
    resumed = run.run_repository(staged_root, staged_session,
                                 scope=_scope(staged_root, context, result=baseline,
                                              bundle_digest=staged_digest, apply=True, modified=True))
    assert resumed["status"] == "verified"
    assert resumed["run_id"] == baseline["run_id"]
    assert resumed["attempts"] == dict(plan=0, baseline=1, apply=1, modified=1, rollback=0)

    initializer = staged_root / "src/fixture_pkg/__init__.py"
    initializer.write_text('"""Changed after reviewed verification."""\n')
    with pytest.raises(run.SessionError, match="bundle_integrity_or_source_contract_invalid"):
        run.run_repository(staged_root, staged_session,
                           scope=_scope(staged_root, context, result=resumed,
                                        bundle_digest=staged_digest))
