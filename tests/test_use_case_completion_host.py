"""Source-bound E fixture and independently read raw installed completion effects."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

import pytest

from jev_integration_evaluator import template_delivery as delivery
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, implementation_status, plan_implementation,
    rollback_implementation)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.template_catalog import materialize_template, validate_template_request
from jev_integration_evaluator.use_case_templates import use_case_matrix
from scripts.implementation_fixtures import fixture
from tests.test_template_installation import _metadata
from tests.test_reusable_templates import fixture_module


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (sys.platform == "linux" and platform.machine().lower() == "x86_64"
           and sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 13))
pytestmark = pytest.mark.skipif(not PROFILE, reason="E installed fixture requires Linux x86-64 CPython 3.13")


def _source_host(target: Path, version: str = "1.0.0") -> tuple[dict, dict, dict]:
    assert version in ("1.0.0", "1.0.1")
    inventory, spec = fixture(target, "E", tag="raw_completion", layout="package",
                              package_name="completion_host")
    package = target / "completion_host"
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "E")
    for source, destination, expected in (
        (ROOT / row["source"], package / "completion_oracle.py", row["source_sha256"]),
        (ROOT / row["consumer_adapter"], package / "completion_consumer.py",
         row["consumer_adapter_sha256"]),
    ):
        assert file_hash(source) == expected
        shutil.copyfile(source, destination)
        assert file_hash(destination) == expected
    host_source = target / spec["source"]["file"]
    text = host_source.read_text(encoding="utf-8")
    old = ("STATE['effects'].append('first')\n"
           "    if not STATE['ineffective']: STATE['records'] += 1\n"
           "    return {'reported': 'ok'}")
    new = ("STATE['effects'].append('first')\n"
           "    if not STATE['ineffective']:\n"
           "        from . import completion_consumer\n"
           "        completion_consumer.commit(request, host_approved=STATE['approval'])\n"
           "        STATE['records'] += 1\n"
           "    return {'reported': 'ok'}")
    assert text.count(old) == 1
    host_source.write_text(text.replace(old, new), encoding="utf-8")
    for case in spec["verification"]["cases"]:
        case["request"].update({"operation": "close_and_label"})
    entry = spec["verification"]["entry_point"]
    (package / "console.py").write_text(
        f"from .{host_source.stem} import {entry}\n"
        "from pathlib import Path\nimport os\nimport time\n"
        "def main():\n"
        "    request = {'task_id':'completion-task','operation':'close_and_label'}\n"
        f"    {entry}(request)\n"
        "    ready = os.environ.get('E_READY_PATH')\n"
        "    if ready:\n"
        "        with Path(ready).open('x', encoding='utf-8') as stream:\n"
        "            stream.write('ready\\n')\n"
        "    time.sleep(0.5)\n"
        "    return 0\n"
        "if __name__ == '__main__':\n    raise SystemExit(main())\n",
        encoding="utf-8")
    tools = {name: importlib.metadata.version(name) for name in ("pip", "setuptools", "wheel")}
    (target / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools==' + tools["setuptools"] +
        '", "wheel==' + tools["wheel"] + '"]\nbuild-backend = "setuptools.build_meta"\n'
        '[project]\nname = "jev-completion-host-fixture"\nversion = "' + version + '"\n'
        'requires-python = ">=3.13"\n'
        'dependencies = ["jev-integration-evaluator==1.3.0.dev12"]\n'
        '[project.scripts]\ncompletion-host = "completion_host.console:main"\n'
        '[tool.setuptools.packages.find]\ninclude = ["completion_host*"]\n', encoding="utf-8")
    cfg = load_config()
    cfg["repository"]["typescript_ast"] = False
    inventory = scan_repo(target, cfg)
    candidate = next(row for row in inventory["candidates"]
                     if row["source"]["symbol"] == "select_boundary_raw_completion")
    reason = ("Reviewed E tail-call seam: an executor report cannot certify raw completion; "
              "the finite host action and independent effect receipt remain authoritative")
    apply_reviews(inventory, {candidate["candidate_id"]: {
        "source_sha256": candidate["source"]["source_sha256"], "approved": True,
        "reviewer": "offline-completion-host-author", "reason": reason}}, cfg)
    spec["candidate_id"] = candidate["candidate_id"]
    spec["experiment_id"] = candidate["recommended_experiment"]["id"]
    spec["inventory_sha256"] = digest(inventory)
    spec["inventory_fingerprint"] = inventory["scan_fingerprint"]
    spec["source"].update({"file_sha256": candidate["source"]["file_sha256"],
                           "source_sha256": candidate["source"]["source_sha256"]})
    spec["binding_review"].update({"source_sha256": candidate["source"]["source_sha256"],
                                    "reason": reason})
    request = {"schema_version": "1.0", "template_id": "python.bounded-tail-call",
               "template_version": "1.0.0", "backend": "python",
               "profile": "module-tail-call-v1", "reviewed_inventory": inventory,
               "implementation_spec": spec}
    return inventory, spec, request


def _probe(tmp_path: Path, name: str) -> dict[str, str]:
    parent = tmp_path / name
    parent.mkdir(mode=0o700)
    return {"E_RAW_STATE_PATH": str(parent / "state-{pid}.json"),
            "E_EFFECT_RECEIPT_PATH": str(parent / "receipt-{pid}.json")}


def _applied(tmp_path: Path, name: str, version: str) -> dict:
    target = tmp_path / name
    inventory, spec, request = _source_host(target, version)
    assert validate_template_request(target, request)["status"] == "validated"
    template = tmp_path / (name + "-template")
    materialize_template(target, request, template)
    bundle = tmp_path / (name + "-bundle")
    plan = plan_implementation(target, inventory, spec["candidate_id"], spec, bundle)
    with pytest.MonkeyPatch.context() as env:
        for key, value in _probe(tmp_path, name + "-probe").items():
            env.setenv(key, value)
        baseline = verify_implementation(target, bundle, "baseline", approve_execution=True)
        assert baseline["status"] == "baseline_passed"
        applied = apply_implementation(target, bundle, plan["bundle_digest"],
                                       baseline_sha256=baseline["receipt_sha256"])
        modified = verify_implementation(target, bundle, "modified", approve_execution=True,
                                         baseline_sha256=baseline["receipt_sha256"])
    assert modified["status"] == "verified"
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified["receipt_sha256"])["status"] == "verified"
    assert len(list((tmp_path / (name + "-probe")).glob("state-*.json"))) >= 2
    return {"target": target, "bundle": bundle, "template": template,
            "version": version,
            "applied": applied, "modified": modified, "spec": spec}


def _scope(status: dict, plan: dict, action: str, **additional) -> dict:
    value = {"schema_version": "1.0", "kind": "template-delivery-scope-v1",
             "reference": "independent-completion-fixture-operator", "run_id": status["run_id"],
             "plan_sha256": plan["plan_sha256"],
             "trusted_session_head": status["session_head_sha256"],
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             "revoked": False, "grants": {name: name == action for name in
                                           ("launch", "stop", "disable", "rollback", "upgrade")},
             **additional}
    value["scope_sha256"] = digest(value)
    return value


def _expected(task_id: str) -> tuple[bytes, bytes]:
    initial = {"task_id": task_id, "status": "open", "revision": 0,
               "labels": [], "unrequested": []}
    final = {"task_id": task_id, "status": "closed", "revision": 2,
             "labels": ["verified"], "unrequested": []}
    raw = lambda value: (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    receipt = {"task_id": task_id, "operation": "close_and_label",
               "before_sha256": hashlib.sha256(raw(initial)).hexdigest(),
               "after_sha256": hashlib.sha256(raw(final)).hexdigest()}
    return raw(final), raw(receipt)


def _observation(directory: Path) -> tuple[dict, dict, bytes, bytes]:
    raw_state, raw_receipt = _expected("completion-task")
    state, receipt, ready = (directory / name for name in ("state.json", "receipt.json", "ready.txt"))
    checks = [{"role": "ready", "path": str(ready), "before_sha256": None,
               "expected_sha256": hashlib.sha256(b"ready\n").hexdigest()}]
    checks += [{"role": role, "path": str(state), "before_sha256": None,
                "expected_sha256": hashlib.sha256(raw_state).hexdigest()}
               for role in ("entrypoint_reached", "integration_reachable")]
    checks += [{"role": "outcome_verified", "path": str(receipt), "before_sha256": None,
                "expected_sha256": hashlib.sha256(raw_receipt).hexdigest()}]
    return ({"schema_version": "1.0", "kind": "template-delivery-observation-v1",
             "checks": checks},
            {"E_RAW_STATE_PATH": str(state), "E_EFFECT_RECEIPT_PATH": str(receipt),
             "E_READY_PATH": str(ready)}, raw_state, raw_receipt)


def _observe(session: Path, status: dict) -> dict:
    for _ in range(300):
        status = delivery.observe_session(session,
            trusted_session_head=status["session_head_sha256"])
        if status["recorded_observations"]["outcome_verified"]:
            return status
        time.sleep(0.01)
    raise AssertionError("independent completion receipt not observed")


def test_completion_consumer_refuses_permission_and_success_shaped_false_completion(tmp_path, monkeypatch):
    import importlib.util
    source = ROOT / "examples/use-case-host/completion_consumer.py"
    spec = importlib.util.spec_from_file_location("completion_consumer_test", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evidence = tmp_path / "effects"
    evidence.mkdir(mode=0o700)
    monkeypatch.setenv("E_RAW_STATE_PATH", str(evidence / "state.json"))
    monkeypatch.setenv("E_EFFECT_RECEIPT_PATH", str(evidence / "receipt.json"))
    request = {"task_id": "completion-task", "operation": "close_and_label"}
    for unsafe, approved in ((request, False),
                             ({**request, "operation": "arbitrary"}, True)):
        with pytest.raises(ValueError, match="permission or operation refused"):
            module.commit(unsafe, host_approved=approved)
    assert list(evidence.iterdir()) == []
    oracle = fixture_module("examples/coding-agent/completion_oracle.py", "completion_e_oracle")
    initial = {"task_id": "completion-task", "status": "open", "revision": 0,
               "labels": [], "unrequested": []}
    objective = {"task_id": "completion-task", "allowed_fields": list(initial),
                 "required_status": "closed", "required_labels": ["verified"],
                 "required_unrequested": []}
    assert not oracle.exact_goal({**initial, "executor_success": True}, objective)
    assert module.commit(request, host_approved=True) == {"reported": "ok"}
    raw_state, raw_receipt = _expected("completion-task")
    assert (evidence / "state.json").read_bytes() == raw_state
    assert (evidence / "receipt.json").read_bytes() == raw_receipt
    assert oracle.exact_goal(json.loads(raw_state), objective)
    with pytest.raises(ValueError, match="fresh and unlinked"):
        module.commit(request, host_approved=True)


def test_completion_installed_offline_upgrade_and_rollback(tmp_path):
    wheelhouse_name = os.environ.get("JEV_TEMPLATE_WHEELHOUSE")
    if not wheelhouse_name:
        pytest.skip("exact private offline wheelhouse required")
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    first = _applied(tmp_path, "completion-v1", "1.0.0")
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
                   "console_script": "completion-host", "configuration": configuration,
                   "secret_references": {}}
        adapter = host["target"] / "completion_host/completion_consumer.py"
        reviewed_bytes = adapter.read_bytes()
        adapter.write_bytes(reviewed_bytes + b"\n# unreviewed drift\n")
        with pytest.raises(installer.InstallationError):
            installer.plan_package(request)
        adapter.write_bytes(reviewed_bytes)
        package_plan = installer.plan_package(request)
        with pytest.raises(installer.InstallationError):
            installer.build_package(package_plan,
                approved_plan_sha256="0" * 64)
        built = installer.build_package(package_plan,
            approved_plan_sha256=package_plan["plan_sha256"])
        install_plan = installer.plan_install(package_plan, built)
        with pytest.raises(installer.InstallationError):
            installer.install_package(install_plan,
                approved_plan_sha256="0" * 64)
        installed = installer.install_package(install_plan,
            approved_plan_sha256=install_plan["plan_sha256"])
        assert installer.installation_status(install_plan)["status"] == "installed_recorded"
        environment = Path(installed["environment"])
        python = Path(installed["installed"]["python"])
        assert python.is_relative_to(environment / "venv") and python.is_symlink()
        assert python.resolve(strict=True) == Path(sys.executable).resolve(strict=True)
        origin = Path(installed["installed"]["entrypoint_origin"])
        assert origin == environment / "venv/lib/python3.13/site-packages/completion_host/console.py"
        assert origin.is_file() and not origin.is_symlink()
        assert (environment / "venv/lib/python3.13/site-packages/jev_integration_evaluator/__init__.py").is_file()
        assert installed["installed"]["distributions"]["jev-completion-host-fixture"] == host["version"]
        return install_plan, installed

    original_plan, original_install = install(first, "package-v1")
    effects = tmp_path / "external-effects"
    effects.mkdir(mode=0o700)
    original_effects = effects / "v1"
    original_effects.mkdir(mode=0o700)
    observation, launch_env, raw_state, raw_receipt = _observation(original_effects)
    original_delivery = delivery.plan_delivery(original_plan,
        trusted_install_receipt_sha256=original_install["receipt_sha256"],
        observation=observation, launch_environment=launch_env)
    session = tmp_path / "delivery-session"
    created = delivery.create_session(session, original_delivery)
    start = _scope(created, original_delivery, "launch")
    with pytest.raises(delivery.DeliveryError):
        delivery.launch_session(session, scope=start,
            approved_scope_sha256="0" * 64)
    assert list(original_effects.iterdir()) == []
    observed = _observe(session, delivery.launch_session(session, scope=start,
        approved_scope_sha256=start["scope_sha256"]))
    assert (original_effects / "state.json").read_bytes() == raw_state
    assert (original_effects / "receipt.json").read_bytes() == raw_receipt
    oracle = fixture_module("examples/coding-agent/completion_oracle.py", "installed_e_oracle")
    objective = {"task_id": "completion-task", "allowed_fields": ["task_id", "status",
                  "revision", "labels", "unrequested"], "required_status": "closed",
                 "required_labels": ["verified"], "required_unrequested": []}
    assert oracle.exact_goal(json.loads(raw_state), objective)
    assert observed["recorded_observations"]["provider_reachable"] is False
    disable = _scope(observed, original_delivery, "disable")
    disabled = delivery.stop_session(session, scope=disable,
        approved_scope_sha256=disable["scope_sha256"], disable=True)
    assert disabled["stage"] == "disabled"

    second = _applied(tmp_path, "completion-v2", "1.0.1")
    new_plan, new_install = install(second, "package-v2")
    assert new_plan["package_plan"]["project_version"] == "1.0.1"
    assert new_install["generation_id"] != original_install["generation_id"]
    new_effects = effects / "v2"
    new_effects.mkdir(mode=0o700)
    new_observation, new_env, _, _ = _observation(new_effects)
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
    assert (new_effects / "state.json").read_bytes() == raw_state
    assert (new_effects / "receipt.json").read_bytes() == raw_receipt
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
