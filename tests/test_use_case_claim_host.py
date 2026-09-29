"""Source-bound M fixture and independently read raw installed claim effects."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
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


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (sys.platform == "linux" and platform.machine().lower() == "x86_64"
           and sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 13))
pytestmark = pytest.mark.skipif(not PROFILE, reason="M installed fixture requires Linux x86-64 CPython 3.13")


def _source_host(target: Path, version: str = "1.0.0") -> tuple[dict, dict, dict]:
    assert version in ("1.0.0", "1.0.1")
    inventory, spec = fixture(target, "M", tag="claim_support", layout="package",
                              package_name="claim_host")
    package = target / "claim_host"
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "M")
    for source, destination, expected in (
        (ROOT / row["source"], package / "claim_oracle.py", row["source_sha256"]),
        (ROOT / row["consumer_adapter"], package / "claim_consumer.py",
         row["consumer_adapter_sha256"]),
    ):
        assert file_hash(source) == expected
        shutil.copyfile(source, destination)
        assert file_hash(destination) == expected
    host_source = target / spec["source"]["file"]
    entry = spec["verification"]["entry_point"]
    (package / "console.py").write_text(
        f"from .{host_source.stem} import {entry}\n"
        "from . import claim_consumer\n"
        "from pathlib import Path\nimport os\nimport time\n"
        "def main():\n"
        "    request = {'task_id':'claim-task','claim':'Permit is active',\n"
        "               'quote':'Permit is active','start':0,'end':16}\n"
        f"    action = {entry}(request)\n"
        "    if action != 'inspect':\n"
        "        raise ValueError('off-mode claim disposition changed')\n"
        "    claim_consumer.commit(request, host_approved=True)\n"
        "    ready = os.environ.get('M_READY_PATH')\n"
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
        '[project]\nname = "jev-claim-host-fixture"\nversion = "' + version + '"\n'
        'requires-python = ">=3.13"\n'
        'dependencies = ["jev-integration-evaluator==1.3.0.dev12"]\n'
        '[project.scripts]\nclaim-host = "claim_host.console:main"\n'
        '[tool.setuptools.packages.find]\ninclude = ["claim_host*"]\n', encoding="utf-8")
    cfg = load_config()
    cfg["repository"]["typescript_ast"] = False
    inventory = scan_repo(target, cfg)
    candidate = next(row for row in inventory["candidates"]
                     if row["source"]["symbol"] == "select_boundary_claim_support")
    reason = ("Reviewed M finite tail-call seam; code-owned citation and exact support "
              "checks, audit and independent raw claim effects remain authoritative")
    apply_reviews(inventory, {candidate["candidate_id"]: {
        "source_sha256": candidate["source"]["source_sha256"], "approved": True,
        "reviewer": "offline-claim-host-author", "reason": reason}}, cfg)
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


def _applied(tmp_path: Path, name: str, version: str) -> dict:
    target = tmp_path / name
    inventory, spec, request = _source_host(target, version)
    assert validate_template_request(target, request)["status"] == "validated"
    template = tmp_path / (name + "-template")
    materialize_template(target, request, template)
    bundle = tmp_path / (name + "-bundle")
    plan = plan_implementation(target, inventory, spec["candidate_id"], spec, bundle)
    baseline = verify_implementation(target, bundle, "baseline", approve_execution=True)
    assert baseline["status"] == "baseline_passed"
    applied = apply_implementation(target, bundle, plan["bundle_digest"],
                                   baseline_sha256=baseline["receipt_sha256"])
    modified = verify_implementation(target, bundle, "modified", approve_execution=True,
                                     baseline_sha256=baseline["receipt_sha256"])
    assert modified["status"] == "verified"
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified["receipt_sha256"])["status"] == "verified"
    return {"target": target, "bundle": bundle, "template": template,
            "version": version,
            "applied": applied, "modified": modified, "spec": spec}


def _scope(status: dict, plan: dict, action: str, **additional) -> dict:
    value = {"schema_version": "1.0", "kind": "template-delivery-scope-v1",
             "reference": "independent-claim-fixture-operator", "run_id": status["run_id"],
             "plan_sha256": plan["plan_sha256"],
             "trusted_session_head": status["session_head_sha256"],
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             "revoked": False, "grants": {name: name == action for name in
                                           ("launch", "stop", "disable", "rollback", "upgrade")},
             **additional}
    value["scope_sha256"] = digest(value)
    return value


def _raw(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _expected(task_id: str) -> tuple[bytes, bytes, bytes]:
    support = {"claim_id": "permit-status", "passage_id": "permit-record-1",
               "source_id": "fixture-permit-register-v1", "span": "0:16",
               "quote": "Permit is active", "decision": "supported"}
    audit = {"task_id": task_id, "claim_id": "permit-status",
             "support_sha256": hashlib.sha256(_raw(support)).hexdigest(),
             "policy": "exact-fixture-support-v1"}
    effect = {"task_id": task_id, "claim_id": "permit-status", "claim": "Permit is active",
              "status": "released", "audit_sha256": hashlib.sha256(_raw(audit)).hexdigest(),
              "support_sha256": hashlib.sha256(_raw(support)).hexdigest()}
    return _raw(support), _raw(audit), _raw(effect)


def _observation(directory: Path) -> tuple[dict, dict, bytes, bytes, bytes]:
    raw_support, raw_audit, raw_claim = _expected("claim-task")
    support, audit, claim, ready = (directory / name for name in
                                    ("support.json", "audit.json", "claim.json", "ready.txt"))
    checks = [{"role": "ready", "path": str(ready), "before_sha256": None,
               "expected_sha256": hashlib.sha256(b"ready\n").hexdigest()}]
    checks += [{"role": "entrypoint_reached", "path": str(support), "before_sha256": None,
                "expected_sha256": hashlib.sha256(raw_support).hexdigest()},
               {"role": "integration_reachable", "path": str(audit), "before_sha256": None,
                "expected_sha256": hashlib.sha256(raw_audit).hexdigest()},
               {"role": "outcome_verified", "path": str(claim), "before_sha256": None,
                "expected_sha256": hashlib.sha256(raw_claim).hexdigest()}]
    return ({"schema_version": "1.0", "kind": "template-delivery-observation-v1",
             "checks": checks},
            {"M_SUPPORT_PATH": str(support), "M_AUDIT_PATH": str(audit),
             "M_CLAIM_PATH": str(claim), "M_READY_PATH": str(ready)},
            raw_support, raw_audit, raw_claim)


def _observe(session: Path, status: dict) -> dict:
    for _ in range(300):
        status = delivery.observe_session(session,
            trusted_session_head=status["session_head_sha256"])
        if status["recorded_observations"]["outcome_verified"]:
            return status
        time.sleep(0.01)
    raise AssertionError("independent claim receipt not observed")


def test_claim_consumer_refuses_unsupported_and_duplicate_effects(tmp_path, monkeypatch):
    import importlib
    package = tmp_path / "claim_test_package"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "M")
    for source, destination, expected in (
        (ROOT / row["source"], package / "claim_oracle.py", row["source_sha256"]),
        (ROOT / row["consumer_adapter"], package / "claim_consumer.py",
         row["consumer_adapter_sha256"]),
    ):
        assert file_hash(source) == expected
        shutil.copyfile(source, destination)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module("claim_test_package.claim_consumer")
    evidence = tmp_path / "effects"
    evidence.mkdir(mode=0o700)
    monkeypatch.setenv("M_SUPPORT_PATH", str(evidence / "support.json"))
    monkeypatch.setenv("M_AUDIT_PATH", str(evidence / "audit.json"))
    monkeypatch.setenv("M_CLAIM_PATH", str(evidence / "claim.json"))
    request = {"task_id": "claim-task", "claim": "Permit is active",
               "quote": "Permit is active", "start": 0, "end": 16}
    for unsafe, approved in ((request, False),
                             ({**request, "claim": "Permit is inactive"}, True),
                             ({**request, "quote": "Permit is inactive"}, True),
                             ({**request, "end": 6}, True),
                             ({**request, "task_id": "other-task"}, True)):
        with pytest.raises(ValueError, match="refused|unsupported|invalid"):
            module.commit(unsafe, host_approved=approved)
    assert list(evidence.iterdir()) == []
    assert module.commit(request, host_approved=True) == {"reported": "ok"}
    raw_support, raw_audit, raw_claim = _expected("claim-task")
    assert (evidence / "support.json").read_bytes() == raw_support
    assert (evidence / "audit.json").read_bytes() == raw_audit
    assert (evidence / "claim.json").read_bytes() == raw_claim
    with pytest.raises(ValueError, match="fresh and unlinked"):
        module.commit(request, host_approved=True)


def test_claim_consumer_refuses_symlink_output_before_any_effect(tmp_path, monkeypatch):
    import importlib
    package = tmp_path / "claim_symlink_package"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "M")
    shutil.copyfile(ROOT / row["source"], package / "claim_oracle.py")
    shutil.copyfile(ROOT / row["consumer_adapter"], package / "claim_consumer.py")
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module("claim_symlink_package.claim_consumer")
    evidence = tmp_path / "effects"
    evidence.mkdir(mode=0o700)
    (evidence / "support.json").symlink_to(evidence / "outside.json")
    monkeypatch.setenv("M_SUPPORT_PATH", str(evidence / "support.json"))
    monkeypatch.setenv("M_AUDIT_PATH", str(evidence / "audit.json"))
    monkeypatch.setenv("M_CLAIM_PATH", str(evidence / "claim.json"))
    with pytest.raises(ValueError, match="fresh and unlinked"):
        module.commit({"task_id": "claim-task", "claim": "Permit is active",
                       "quote": "Permit is active", "start": 0, "end": 16},
                      host_approved=True)
    assert not (evidence / "outside.json").exists()
    assert not (evidence / "audit.json").exists()
    assert not (evidence / "claim.json").exists()


def test_claim_installed_offline_upgrade_and_rollback(tmp_path):
    wheelhouse_name = os.environ.get("JEV_TEMPLATE_WHEELHOUSE")
    if not wheelhouse_name:
        pytest.skip("exact private offline wheelhouse required")
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    first = _applied(tmp_path, "claim-v1", "1.0.0")
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
                   "console_script": "claim-host", "configuration": configuration,
                   "secret_references": {}}
        for member in ("claim_consumer.py", "claim_oracle.py"):
            source = host["target"] / "claim_host" / member
            reviewed_bytes = source.read_bytes()
            source.write_bytes(reviewed_bytes + b"\n# unreviewed drift\n")
            with pytest.raises(installer.InstallationError):
                installer.plan_package(request)
            source.write_bytes(reviewed_bytes)
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
        assert origin == environment / "venv/lib/python3.13/site-packages/claim_host/console.py"
        assert origin.is_file() and not origin.is_symlink()
        assert (environment / "venv/lib/python3.13/site-packages/jev_integration_evaluator/__init__.py").is_file()
        assert installed["installed"]["distributions"]["jev-claim-host-fixture"] == host["version"]
        return install_plan, installed

    original_plan, original_install = install(first, "package-v1")
    effects = tmp_path / "external-effects"
    effects.mkdir(mode=0o700)
    original_effects = effects / "v1"
    original_effects.mkdir(mode=0o700)
    observation, launch_env, raw_support, raw_audit, raw_claim = _observation(original_effects)
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
    assert (original_effects / "support.json").read_bytes() == raw_support
    assert (original_effects / "audit.json").read_bytes() == raw_audit
    assert (original_effects / "claim.json").read_bytes() == raw_claim
    assert json.loads(raw_claim)["audit_sha256"] == file_hash(original_effects / "audit.json")
    assert json.loads(raw_claim)["support_sha256"] == file_hash(original_effects / "support.json")
    with pytest.raises(delivery.DeliveryError):
        delivery.launch_session(session, scope=start,
            approved_scope_sha256=start["scope_sha256"])
    assert len(list(original_effects.iterdir())) == 4
    assert observed["recorded_observations"]["provider_reachable"] is False
    disable = _scope(observed, original_delivery, "disable")
    disabled = delivery.stop_session(session, scope=disable,
        approved_scope_sha256=disable["scope_sha256"], disable=True)
    assert disabled["stage"] == "disabled"

    second = _applied(tmp_path, "claim-v2", "1.0.1")
    new_plan, new_install = install(second, "package-v2")
    assert new_plan["package_plan"]["project_version"] == "1.0.1"
    assert new_install["generation_id"] != original_install["generation_id"]
    new_effects = effects / "v2"
    new_effects.mkdir(mode=0o700)
    new_observation, new_env, _, _, _ = _observation(new_effects)
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
    assert (new_effects / "support.json").read_bytes() == raw_support
    assert (new_effects / "audit.json").read_bytes() == raw_audit
    assert (new_effects / "claim.json").read_bytes() == raw_claim
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
