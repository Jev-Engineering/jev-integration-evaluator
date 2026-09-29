"""Distinct H host: source-bound edit and raw retained-state effect."""
from __future__ import annotations

import json
import hashlib
import importlib.metadata
import importlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, implementation_status, plan_implementation, rollback_implementation)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.template_catalog import materialize_template, validate_template_request
from jev_integration_evaluator import template_delivery as delivery
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.use_case_templates import use_case_matrix
from scripts.implementation_fixtures import fixture
from tests.test_template_installation import _metadata
from tests.test_reusable_templates import fixture_module


ROOT = Path(__file__).resolve().parents[1]
CONSUMER_SHA256 = "687f86969341bd77d56f9ae5c7d13a2050b03faf829d28b424e3d1183173f127"
pytestmark = pytest.mark.skipif(
    not (sys.platform == "linux" and platform.machine().lower() == "x86_64"
         and sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 13)),
    reason="H installed host profile is Linux x86-64 CPython 3.13 only")


def _host(target: Path, version: str = "1.0.0"):
    assert version in ("1.0.0", "1.0.1")
    inventory, spec = fixture(target, "H", tag="retention_consumer", layout="package",
                              package_name="retention_host")
    package = target / "retention_host"
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "H")
    oracle_source = ROOT / row["source"]
    assert file_hash(oracle_source) == row["source_sha256"]
    shutil.copyfile(oracle_source, package / "retention_oracle.py")
    assert file_hash(package / "retention_oracle.py") == row["source_sha256"]
    consumer_source = ROOT / "examples/use-case-host/retention_consumer.py"
    assert file_hash(consumer_source) == CONSUMER_SHA256
    shutil.copyfile(consumer_source, package / "retention_consumer.py")
    source = target / spec["source"]["file"]
    raw = source.read_text(encoding="utf-8")
    old = ("STATE['kept'] = [item['id'] for item in action]\n"
           "    STATE['effects'].append('retain')\n"
           "    return STATE['kept'][:]")
    new = ("from . import retention_consumer\n"
           "    STATE['kept'] = retention_consumer.commit(request, action)\n"
           "    STATE['effects'].append('retain')\n"
           "    return STATE['kept'][:]")
    assert raw.count(old) == 1
    source.write_text(raw.replace(old, new), encoding="utf-8")
    host_module = Path(spec["source"]["file"]).stem
    entry = spec["verification"]["entry_point"]
    (package / "console.py").write_text(
        f"from .{host_module} import {entry}\n"
        "from pathlib import Path\nimport os\n"
        "def main():\n"
        "    request = {'task_id':'retention-task','command':'/prune'}\n"
        f"    {entry}(request)\n"
        "    ready = os.environ.get('H_READY_PATH')\n"
        "    if ready:\n"
        "        with Path(ready).open('x', encoding='utf-8') as stream:\n"
        "            stream.write('ready\\n')\n"
        "    import time\n"
        "    time.sleep(15)\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n", encoding="utf-8")
    tools = {name: importlib.metadata.version(name) for name in ("pip", "setuptools", "wheel")}
    (target / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools==' + tools["setuptools"] +
        '", "wheel==' + tools["wheel"] + '"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "jev-retention-host-fixture"\nversion = "' + version + '"\n'
        'requires-python = ">=3.13"\n'
        'dependencies = ["jev-integration-evaluator==1.3.0.dev12"]\n'
        '[project.scripts]\nretention-host = "retention_host.console:main"\n'
        '[tool.setuptools.packages.find]\ninclude = ["retention_host*"]\n', encoding="utf-8")

    cfg = load_config()
    cfg["repository"]["typescript_ast"] = False
    inventory = scan_repo(target, cfg)
    candidate = next(row for row in inventory["candidates"]
                     if row["source"]["symbol"] == "select_boundary_retention_consumer")
    reason = ("Reviewed H tail-call seam: raw retained items and pinned bytes "
              "are checked by deterministic host code under explicit /prune")
    apply_reviews(inventory, {candidate["candidate_id"]: {
        "source_sha256": candidate["source"]["source_sha256"],
        "approved": True, "reviewer": "offline-retention-host-author", "reason": reason}}, cfg)
    spec["candidate_id"] = candidate["candidate_id"]
    spec["experiment_id"] = candidate["recommended_experiment"]["id"]
    spec["inventory_sha256"] = digest(inventory)
    spec["inventory_fingerprint"] = inventory["scan_fingerprint"]
    spec["source"].update({"file_sha256": candidate["source"]["file_sha256"],
                           "source_sha256": candidate["source"]["source_sha256"]})
    spec["binding_review"]["source_sha256"] = candidate["source"]["source_sha256"]
    spec["binding_review"]["reason"] = reason
    request = {"schema_version": "1.0", "template_id": "python.bounded-tail-call",
               "template_version": "1.0.0", "backend": "python",
               "profile": "module-tail-call-v1", "reviewed_inventory": inventory,
               "implementation_spec": spec}
    return inventory, spec, request


def _scope(result: dict, plan: dict, action: str) -> dict:
    value = {"schema_version": "1.0", "kind": "template-delivery-scope-v1",
             "reference": "independent-retention-fixture-operator",
             "run_id": result["run_id"], "plan_sha256": plan["plan_sha256"],
             "trusted_session_head": result["session_head_sha256"],
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             "revoked": False,
             "grants": {name: name == action for name in
                        ("launch", "stop", "disable", "rollback", "upgrade")}}
    value["scope_sha256"] = digest(value)
    return value


def _probe_effect_path(tmp_path: Path, name: str) -> str:
    parent = tmp_path / name
    parent.mkdir(mode=0o700)
    return str(parent / "retained-{pid}.json")


def _assert_probe_effects(tmp_path: Path, name: str) -> None:
    files = list((tmp_path / name).glob("retained-*.json"))
    selections = {tuple(item["id"] for item in json.loads(path.read_text())) for path in files}
    assert len(files) >= 2
    assert {("pinned", "work"), ("pinned", "work", "old")} <= selections


def test_retention_host_plan_apply_raw_effect_and_rollback(tmp_path):
    target = tmp_path / "retention-target"
    inventory, spec, request = _host(target)
    assert validate_template_request(target, request)["status"] == "validated"
    materialize_template(target, request, tmp_path / "materialized")
    bundle = tmp_path / "bundle"
    planned = plan_implementation(target, inventory, spec["candidate_id"], spec, bundle)
    with pytest.MonkeyPatch.context() as probe_env:
        probe_env.setenv("H_RETAINED_PATH", _probe_effect_path(tmp_path, "probe-effects"))
        baseline = verify_implementation(target, bundle, "baseline", approve_execution=True)
        assert baseline["status"] == "baseline_passed"
        applied = apply_implementation(target, bundle, planned["bundle_digest"],
                                       baseline_sha256=baseline["receipt_sha256"])
        modified = verify_implementation(target, bundle, "modified", approve_execution=True,
                                         baseline_sha256=baseline["receipt_sha256"])
    assert modified["status"] == "verified"
    _assert_probe_effects(tmp_path, "probe-effects")
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified["receipt_sha256"])["status"] == "verified"
    effects = tmp_path / "effects"
    effects.mkdir(mode=0o700)
    effect, ready = effects / "retained.json", effects / "ready.txt"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(target), str(ROOT))),
           "H_RETAINED_PATH": str(effect), "H_READY_PATH": str(ready)}
    run = subprocess.run([sys.executable, "-m", "retention_host.console"],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert effect.is_file()
    retained = json.loads(effect.read_text(encoding="utf-8"))
    assert [item["id"] for item in retained] == ["pinned", "work", "old"]
    assert retained[0]["text"] == "region east"
    assert retained[0]["byte_sha256"] == __import__("hashlib").sha256(b"region east").hexdigest()
    assert ready.read_bytes() == b"ready\n"
    assert rollback_implementation(target, bundle, applied["rollback_digest"])["status"] == "rolled_back"


def test_retention_consumer_rejects_wrong_mode_pin_loss_and_source_drift(tmp_path, monkeypatch):
    target = tmp_path / "retention-target"
    _host(target)
    monkeypatch.syspath_prepend(str(target))
    consumer = importlib.import_module("retention_host.retention_consumer")
    effects = tmp_path / "effects"
    effects.mkdir(mode=0o700)
    effect = effects / "retained.json"
    monkeypatch.setenv("H_RETAINED_PATH", str(effect))
    pinned = {"id": "pinned", "text": "never discard this constraint", "pinned": True}
    work = {"id": "work", "text": "current work"}
    old = {"id": "old", "text": "obsolete"}
    for missing in (None, ""):
        if missing is None:
            monkeypatch.delenv("H_RETAINED_PATH")
        else:
            monkeypatch.setenv("H_RETAINED_PATH", missing)
        with pytest.raises(ValueError, match="H_RETAINED_PATH is required"):
            consumer.commit({"command": "/prune"}, [pinned, work])
        assert not effect.exists()
    monkeypatch.setenv("H_RETAINED_PATH", str(effect))
    with pytest.raises(ValueError, match="retention postcondition failed"):
        consumer.commit({"command": "/prune"}, [pinned, work, old], token_budget=4)
    assert not effect.exists()
    for request, selected in (
        ({"command": "/compact"}, [pinned, work]),
        ({"command": "/prune"}, [work]),
        ({"command": "/prune"}, [{**pinned, "text": "changed"}, work]),
    ):
        with pytest.raises(ValueError):
            consumer.commit(request, selected)
        assert not effect.exists()
    assert consumer.commit({"command": "/prune"}, [pinned, work]) == ["pinned", "work"]
    assert [item["id"] for item in json.loads(effect.read_text())] == ["pinned", "work"]


def test_retention_host_installed_supervised_offline_effect(tmp_path):
    wheelhouse_name = os.environ.get("JEV_TEMPLATE_WHEELHOUSE")
    if not wheelhouse_name:
        pytest.skip("Prepared offline template wheelhouse required")
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    target = tmp_path / "retention-target"
    inventory, spec, request = _host(target)
    assert validate_template_request(target, request)["status"] == "validated"
    template = tmp_path / "materialized"
    materialize_template(target, request, template)
    bundle = tmp_path / "bundle"
    planned = plan_implementation(target, inventory, spec["candidate_id"], spec, bundle)
    with pytest.MonkeyPatch.context() as probe_env:
        probe_env.setenv("H_RETAINED_PATH", _probe_effect_path(tmp_path, "probe-effects"))
        baseline = verify_implementation(target, bundle, "baseline", approve_execution=True)
        assert baseline["status"] == "baseline_passed"
        applied = apply_implementation(target, bundle, planned["bundle_digest"],
                                       baseline_sha256=baseline["receipt_sha256"])
        modified = verify_implementation(target, bundle, "modified", approve_execution=True,
                                         baseline_sha256=baseline["receipt_sha256"])
    assert modified["status"] == "verified"
    _assert_probe_effects(tmp_path, "probe-effects")
    wheels = sorted(wheelhouse.glob("*.whl"))
    rows = [{"filename": path.name, "sha256": file_hash(path)} for path in wheels]
    requirements = [{"name": name, "version": version,
                     "wheel": path.name, "sha256": file_hash(path)}
                    for path in wheels for name, version in [_metadata(path)]]
    environments = tmp_path / "environments"
    environments.mkdir(mode=0o700)
    config = {"jev_runtime": {"mode": "off", "credential_ref": None}}
    package_request = {
        "schema_version": "1.0", "host_root": str(target),
        "implementation_bundle": str(bundle),
        "trusted_modified_receipt_sha256": modified["receipt_sha256"],
        "template_directory": str(template),
        "reviewed_package_source_sha256": digest(installer._tree(target)),
        "reviewed_configuration_sha256": digest(config),
        "interpreter": sys.executable,
        "build_tools": {name: importlib.metadata.version(name)
                        for name in ("pip", "setuptools", "wheel")},
        "wheelhouse": str(wheelhouse), "wheels": rows, "requirements": requirements,
        "package_directory": str(tmp_path / "package"),
        "environment_parent": str(environments), "console_script": "retention-host",
        "configuration": config, "secret_references": {}}
    consumer_copy = target / "retention_host/retention_consumer.py"
    reviewed_bytes = consumer_copy.read_bytes()
    consumer_copy.write_bytes(reviewed_bytes + b"\n# unreviewed drift\n")
    with pytest.raises(installer.InstallationError):
        installer.plan_package(package_request)
    consumer_copy.write_bytes(reviewed_bytes)
    package_plan = installer.plan_package(package_request)
    package_receipt = installer.build_package(
        package_plan, approved_plan_sha256=package_plan["plan_sha256"])
    install_plan = installer.plan_install(package_plan, package_receipt)
    installed = installer.install_package(
        install_plan, approved_plan_sha256=install_plan["plan_sha256"])
    assert installer.installation_status(install_plan)["status"] == "installed_recorded"

    effects = tmp_path / "external-effects"
    effects.mkdir(mode=0o700)
    retained_path, ready_path = effects / "retained.json", effects / "ready.txt"
    values = (("pinned", "region east", "verified_source", "reviewed-one"),
              ("work", "task open", "tool", "run-one"),
              ("old", "noise item", "tool", "run-old"))
    expected_items = [{"id": name, "text": value, "source_kind": kind,
                       "source_ref": reference, "capture_revision": 1,
                       "token_count": len(value.split()),
                       "byte_sha256": hashlib.sha256(value.encode()).hexdigest()}
                      for name, value, kind, reference in values]
    expected_raw = (json.dumps(expected_items, sort_keys=True,
                               separators=(",", ":")) + "\n").encode()
    effect_sha = hashlib.sha256(expected_raw).hexdigest()
    ready_sha = hashlib.sha256(b"ready\n").hexdigest()
    observation = {"schema_version": "1.0", "kind": "template-delivery-observation-v1",
                   "checks": [{"role": "ready", "path": str(ready_path),
                               "before_sha256": None, "expected_sha256": ready_sha}]
                   + [{"role": role, "path": str(retained_path),
                       "before_sha256": None, "expected_sha256": effect_sha}
                      for role in ("entrypoint_reached", "integration_reachable",
                                   "outcome_verified")]}
    delivery_plan = delivery.plan_delivery(
        install_plan, trusted_install_receipt_sha256=installed["receipt_sha256"],
        observation=observation,
        launch_environment={"H_RETAINED_PATH": str(retained_path),
                            "H_READY_PATH": str(ready_path)})
    session = tmp_path / "delivery-session"
    created = delivery.create_session(session, delivery_plan)
    launch_scope = _scope(created, delivery_plan, "launch")
    observed = delivery.launch_session(session, scope=launch_scope,
        approved_scope_sha256=launch_scope["scope_sha256"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        observed = delivery.observe_session(
            session, trusted_session_head=observed["session_head_sha256"])
        if (observed["recorded_observations"]["ready"]
                and observed["recorded_observations"]["outcome_verified"]):
            break
        time.sleep(0.01)
    assert observed["recorded_observations"]["outcome_verified"] is True
    assert observed["recorded_observations"]["provider_reachable"] is False
    assert delivery.session_status(session,
        trusted_session_head=observed["session_head_sha256"])["current_installation"] == "current_verified"
    assert ready_path.read_bytes() == b"ready\n"
    assert retained_path.read_bytes() == expected_raw
    assert [item["id"] for item in json.loads(retained_path.read_text())] == [
        "pinned", "work", "old"]
    oracle = fixture_module("examples/coding-agent/retention_oracle.py",
                            "issue59_h_installed_recall")
    recall = oracle.score_recall("authoritative region sources", {
        "applicable": True, "expected_answer": "east", "required_source_ids": ["pinned"],
        "required_source_sha256": {"pinned": expected_items[0]["byte_sha256"]}},
        json.loads(retained_path.read_text()), [])
    assert recall["success"] is True and recall["citation_ids"] == ["pinned"]
    disable_scope = _scope(observed, delivery_plan, "disable")
    disabled = delivery.stop_session(session, scope=disable_scope,
        approved_scope_sha256=disable_scope["scope_sha256"], disable=True)
    assert disabled["stage"] == "disabled"

    new_target = tmp_path / "new-retention-target"
    new_inventory, new_spec, new_request = _host(new_target, version="1.0.1")
    assert validate_template_request(new_target, new_request)["status"] == "validated"
    new_template = tmp_path / "new-materialized"
    materialize_template(new_target, new_request, new_template)
    new_bundle = tmp_path / "new-bundle"
    new_planned = plan_implementation(new_target, new_inventory, new_spec["candidate_id"],
                                      new_spec, new_bundle)
    with pytest.MonkeyPatch.context() as probe_env:
        probe_env.setenv("H_RETAINED_PATH", _probe_effect_path(tmp_path, "new-probe-effects"))
        new_baseline = verify_implementation(new_target, new_bundle, "baseline",
                                             approve_execution=True)
        assert new_baseline["status"] == "baseline_passed"
        new_applied = apply_implementation(new_target, new_bundle,
                                           new_planned["bundle_digest"],
                                           baseline_sha256=new_baseline["receipt_sha256"])
        new_modified = verify_implementation(new_target, new_bundle, "modified",
            approve_execution=True, baseline_sha256=new_baseline["receipt_sha256"])
    assert new_modified["status"] == "verified"
    _assert_probe_effects(tmp_path, "new-probe-effects")
    new_package_request = {**package_request, "host_root": str(new_target),
        "implementation_bundle": str(new_bundle),
        "trusted_modified_receipt_sha256": new_modified["receipt_sha256"],
        "template_directory": str(new_template),
        "reviewed_package_source_sha256": digest(installer._tree(new_target)),
        "package_directory": str(tmp_path / "new-package")}
    new_package_plan = installer.plan_package(new_package_request)
    assert package_plan["project_version"] == "1.0.0"
    assert new_package_plan["project_version"] == "1.0.1"
    new_package_receipt = installer.build_package(
        new_package_plan, approved_plan_sha256=new_package_plan["plan_sha256"])
    new_install_plan = installer.plan_install(new_package_plan, new_package_receipt)
    new_installed = installer.install_package(
        new_install_plan, approved_plan_sha256=new_install_plan["plan_sha256"])
    assert new_installed["generation_id"] != installed["generation_id"]
    retained2, ready2 = effects / "retained-v2.json", effects / "ready-v2.txt"
    new_observation = {"schema_version": "1.0", "kind": "template-delivery-observation-v1",
        "checks": [{"role": "ready", "path": str(ready2),
                    "before_sha256": None, "expected_sha256": ready_sha}]
        + [{"role": role, "path": str(retained2), "before_sha256": None,
            "expected_sha256": effect_sha}
           for role in ("entrypoint_reached", "integration_reachable", "outcome_verified")]}
    new_delivery_plan = delivery.plan_delivery(
        new_install_plan, trusted_install_receipt_sha256=new_installed["receipt_sha256"],
        observation=new_observation,
        launch_environment={"H_RETAINED_PATH": str(retained2), "H_READY_PATH": str(ready2)})
    upgrade_scope = _scope(disabled, delivery_plan, "upgrade")
    upgrade_scope["upgrade_plan_sha256"] = new_delivery_plan["plan_sha256"]
    upgrade_scope["scope_sha256"] = digest({k: v for k, v in upgrade_scope.items()
                                             if k != "scope_sha256"})
    upgraded = delivery.upgrade_session(session, new_delivery_plan,
        scope=upgrade_scope, approved_scope_sha256=upgrade_scope["scope_sha256"])
    assert upgraded["stage"] == "upgrade_staged"
    assert upgraded["generation_id"] == new_installed["generation_id"]
    assert Path(installed["environment"]).is_dir()
    new_launch_scope = _scope(upgraded, new_delivery_plan, "launch")
    new_observed = delivery.launch_session(session, scope=new_launch_scope,
        approved_scope_sha256=new_launch_scope["scope_sha256"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        new_observed = delivery.observe_session(
            session, trusted_session_head=new_observed["session_head_sha256"])
        if (new_observed["recorded_observations"]["ready"]
                and new_observed["recorded_observations"]["outcome_verified"]):
            break
        time.sleep(0.01)
    assert new_observed["recorded_observations"]["outcome_verified"] is True
    assert retained2.read_bytes() == expected_raw
    new_disable_scope = _scope(new_observed, new_delivery_plan, "disable")
    new_disabled = delivery.stop_session(session, scope=new_disable_scope,
        approved_scope_sha256=new_disable_scope["scope_sha256"], disable=True)
    assert new_disabled["stage"] == "disabled"
    rollback_scope = _scope(new_disabled, new_delivery_plan, "rollback")
    rollback_scope["rollback_digest"] = new_disabled["previous_generation_rollback_digest"]
    rollback_scope["scope_sha256"] = digest({k: v for k, v in rollback_scope.items()
                                              if k != "scope_sha256"})
    rolled = delivery.rollback_session(session, scope=rollback_scope,
        approved_scope_sha256=rollback_scope["scope_sha256"])
    assert rolled["stage"] == "rolled_back"
    assert rolled["generation_id"] == installed["generation_id"]
    assert Path(installed["environment"]).is_dir()
    assert Path(new_installed["environment"]).is_dir()
    assert rollback_implementation(new_target, new_bundle,
        new_applied["rollback_digest"])["status"] == "rolled_back"
    assert rollback_implementation(target, bundle,
        applied["rollback_digest"])["status"] == "rolled_back"
