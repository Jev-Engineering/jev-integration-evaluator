"""Installed off-mode L host: raw in-memory graph mutation readback."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

import pytest

from jev_integration_evaluator import template_delivery as delivery
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, implementation_status, plan_implementation,
    rollback_implementation)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.template_catalog import materialize_template, validate_template_request
from tests.test_template_installation import _metadata
from tests.test_use_case_graph_host import _graph_host


PROFILE = (sys.platform == "linux" and platform.machine().lower() == "x86_64"
           and sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 13))
pytestmark = pytest.mark.skipif(not PROFILE, reason="L installed fixture requires Linux x86-64 CPython 3.13")


def _applied(tmp_path: Path, name: str, version: str) -> dict:
    target = tmp_path / name
    inventory, spec = _graph_host(target, version)
    request = {"schema_version": "1.0", "template_id": "python.bounded-tail-call",
               "template_version": "1.0.0", "backend": "python",
               "profile": "module-tail-call-v1", "reviewed_inventory": inventory,
               "implementation_spec": spec}
    assert validate_template_request(target, request)["status"] == "validated"
    template = tmp_path / (name + "-template")
    materialize_template(target, request, template)
    bundle = tmp_path / (name + "-bundle")
    plan = plan_implementation(target, inventory, spec["candidate_id"], spec, bundle)
    probes = tmp_path / (name + "-probes")
    probes.mkdir(mode=0o700)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("GRAPH_EFFECT_PATH", str(probes / "graph-{pid}.json"))
        baseline = verify_implementation(target, bundle, "baseline", approve_execution=True)
        assert baseline["status"] == "baseline_passed"
        applied = apply_implementation(target, bundle, plan["bundle_digest"],
                                       baseline_sha256=baseline["receipt_sha256"])
        modified = verify_implementation(target, bundle, "modified", approve_execution=True,
                                         baseline_sha256=baseline["receipt_sha256"])
    assert modified["status"] == "verified"
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified["receipt_sha256"])["status"] == "verified"
    assert list(probes.glob("graph-*.json"))
    return {"target": target, "bundle": bundle, "template": template,
            "version": version, "modified": modified, "applied": applied}


def _scope(status: dict, plan: dict, action: str, **extra) -> dict:
    value = {"schema_version": "1.0", "kind": "template-delivery-scope-v1",
             "reference": "independent-graph-fixture-operator",
             "run_id": status["run_id"], "plan_sha256": plan["plan_sha256"],
             "trusted_session_head": status["session_head_sha256"],
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             "revoked": False,
             "grants": {name: name == action for name in
                        ("launch", "stop", "disable", "rollback", "upgrade")}, **extra}
    value["scope_sha256"] = digest(value)
    return value


def _expected() -> bytes:
    left = {"key": "left", "name": "Acme", "jurisdiction": "US",
            "registry_id": "one", "provenance": "registry-left"}
    right = {"key": "right", "name": "Acme", "jurisdiction": "US",
             "registry_id": "one", "provenance": "registry-right"}
    receipt = {"left_key": "left", "right_key": "right",
               "sources": ["registry-left", "registry-right"],
               "revision_before": 0, "revision_after": 1}
    graph = {"task_id": "graph-task", "entities": {"left": left, "right": right},
             "receipt": receipt, "merges": [receipt], "audits": [receipt], "revision": 1}
    return (json.dumps(graph, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _observation(directory: Path) -> tuple[dict, dict, bytes]:
    raw = _expected()
    effect, ready = directory / "graph.json", directory / "ready.txt"
    checks = [{"role": "ready", "path": str(ready), "before_sha256": None,
               "expected_sha256": hashlib.sha256(b"ready\n").hexdigest()}]
    checks += [{"role": role, "path": str(effect), "before_sha256": None,
                "expected_sha256": hashlib.sha256(raw).hexdigest()}
               for role in ("entrypoint_reached", "integration_reachable",
                            "outcome_verified")]
    return ({"schema_version": "1.0", "kind": "template-delivery-observation-v1",
             "checks": checks},
            {"GRAPH_EFFECT_PATH": str(effect), "GRAPH_READY_PATH": str(ready)}, raw)


def _observe(session: Path, status: dict) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = delivery.observe_session(session,
            trusted_session_head=status["session_head_sha256"])
        if (status["recorded_observations"]["ready"]
                and status["recorded_observations"]["outcome_verified"]):
            return status
        time.sleep(0.01)
    raise AssertionError("graph effect not observed")


def test_graph_installed_offline_upgrade_and_rollback(tmp_path):
    wheelhouse_name = os.environ.get("JEV_TEMPLATE_WHEELHOUSE")
    if not wheelhouse_name:
        pytest.skip("exact private offline wheelhouse required")
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    first = _applied(tmp_path, "graph-v1", "1.0.0")
    wheels = sorted(wheelhouse.glob("*.whl"))
    wheel_rows = [{"filename": path.name, "sha256": file_hash(path)} for path in wheels]
    requirements = [{"name": name, "version": version, "wheel": path.name,
                     "sha256": file_hash(path)}
                    for path in wheels for name, version in [_metadata(path)]]
    environments = tmp_path / "environments"
    environments.mkdir(mode=0o700)
    configuration = {"jev_runtime": {"mode": "off", "credential_ref": None}}

    def install(host: dict, package_name: str) -> tuple[dict, dict]:
        request = {"schema_version": "1.0", "host_root": str(host["target"]),
                   "implementation_bundle": str(host["bundle"]),
                   "trusted_modified_receipt_sha256": host["modified"]["receipt_sha256"],
                   "template_directory": str(host["template"]),
                   "reviewed_package_source_sha256": digest(installer._tree(host["target"])),
                   "reviewed_configuration_sha256": digest(configuration),
                   "interpreter": sys.executable,
                   "build_tools": {name: importlib.metadata.version(name)
                                   for name in ("pip", "setuptools", "wheel")},
                   "wheelhouse": str(wheelhouse), "wheels": wheel_rows,
                   "requirements": requirements,
                   "package_directory": str(tmp_path / package_name),
                   "environment_parent": str(environments),
                   "console_script": "graph-host", "configuration": configuration,
                   "secret_references": {}}
        runtime = host["target"] / "graph_host/graph_runtime.py"
        reviewed = runtime.read_bytes()
        runtime.write_bytes(reviewed + b"\n# drift\n")
        with pytest.raises(installer.InstallationError):
            installer.plan_package(request)
        runtime.write_bytes(reviewed)
        package_plan = installer.plan_package(request)
        with pytest.raises(installer.InstallationError):
            installer.build_package(package_plan, approved_plan_sha256="0" * 64)
        built = installer.build_package(package_plan,
            approved_plan_sha256=package_plan["plan_sha256"])
        install_plan = installer.plan_install(package_plan, built)
        with pytest.raises(installer.InstallationError):
            installer.install_package(install_plan, approved_plan_sha256="0" * 64)
        installed = installer.install_package(install_plan,
            approved_plan_sha256=install_plan["plan_sha256"])
        assert installer.installation_status(install_plan)["status"] == "installed_recorded"
        environment = Path(installed["environment"])
        python = Path(installed["installed"]["python"])
        assert python.is_relative_to(environment / "venv") and python.is_symlink()
        assert python.resolve(strict=True) == Path(sys.executable).resolve(strict=True)
        origin = Path(installed["installed"]["entrypoint_origin"])
        assert origin == environment / "venv/lib/python3.13/site-packages/graph_host/console.py"
        assert origin.is_file() and not origin.is_symlink()
        assert installed["installed"]["distributions"]["jev-graph-host-fixture"] == host["version"]
        return install_plan, installed

    original_plan, original_install = install(first, "package-v1")
    effects = tmp_path / "external-effects"
    effects.mkdir(mode=0o700)
    v1 = effects / "v1"
    v1.mkdir(mode=0o700)
    observation, launch_env, raw = _observation(v1)
    original_delivery = delivery.plan_delivery(original_plan,
        trusted_install_receipt_sha256=original_install["receipt_sha256"],
        observation=observation, launch_environment=launch_env)
    session = tmp_path / "delivery-session"
    created = delivery.create_session(session, original_delivery)
    start = _scope(created, original_delivery, "launch")
    with pytest.raises(delivery.DeliveryError):
        delivery.launch_session(session, scope=start, approved_scope_sha256="0" * 64)
    assert list(v1.iterdir()) == []
    observed = _observe(session, delivery.launch_session(session, scope=start,
        approved_scope_sha256=start["scope_sha256"]))
    assert (v1 / "graph.json").read_bytes() == raw
    assert (v1 / "ready.txt").read_bytes() == b"ready\n"
    actual = json.loads((v1 / "graph.json").read_text())
    assert actual["revision"] == 1
    assert actual["receipt"] == actual["merges"][0] == actual["audits"][0]
    assert observed["recorded_observations"]["provider_reachable"] is False
    disable = _scope(observed, original_delivery, "disable")
    disabled = delivery.stop_session(session, scope=disable,
        approved_scope_sha256=disable["scope_sha256"], disable=True)
    assert disabled["stage"] == "disabled"

    second = _applied(tmp_path, "graph-v2", "1.0.1")
    new_plan, new_install = install(second, "package-v2")
    assert new_install["generation_id"] != original_install["generation_id"]
    v2 = effects / "v2"
    v2.mkdir(mode=0o700)
    new_observation, new_env, new_raw = _observation(v2)
    new_delivery = delivery.plan_delivery(new_plan,
        trusted_install_receipt_sha256=new_install["receipt_sha256"],
        observation=new_observation, launch_environment=new_env)
    upgrade = _scope(disabled, original_delivery, "upgrade",
                     upgrade_plan_sha256=new_delivery["plan_sha256"])
    upgraded = delivery.upgrade_session(session, new_delivery, scope=upgrade,
        approved_scope_sha256=upgrade["scope_sha256"])
    assert upgraded["stage"] == "upgrade_staged"
    start_new = _scope(upgraded, new_delivery, "launch")
    observed_new = _observe(session, delivery.launch_session(session, scope=start_new,
        approved_scope_sha256=start_new["scope_sha256"]))
    assert (v2 / "graph.json").read_bytes() == new_raw
    disable_new = _scope(observed_new, new_delivery, "disable")
    disabled_new = delivery.stop_session(session, scope=disable_new,
        approved_scope_sha256=disable_new["scope_sha256"], disable=True)
    rollback = _scope(disabled_new, new_delivery, "rollback",
        rollback_digest=disabled_new["previous_generation_rollback_digest"])
    rolled = delivery.rollback_session(session, scope=rollback,
        approved_scope_sha256=rollback["scope_sha256"])
    assert rolled["stage"] == "rolled_back"
    assert rolled["generation_id"] == original_install["generation_id"]
    assert Path(original_install["environment"]).is_dir()
    assert Path(new_install["environment"]).is_dir()
    for host in (second, first):
        assert rollback_implementation(host["target"], host["bundle"],
            host["applied"]["rollback_digest"])["status"] == "rolled_back"
