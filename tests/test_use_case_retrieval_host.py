"""Source-bound D host, pinned corpus, and installed off-mode retrieval effect."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib
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
pytestmark = pytest.mark.skipif(not PROFILE, reason="D installed fixture requires Linux x86-64 CPython 3.13")


def _corpus(parent: Path, name: str) -> Path:
    directory = parent / name
    directory.mkdir(mode=0o700)
    source = ROOT / "examples/use-case-host/retrieval_corpus_v1.json"
    path = directory / "corpus.json"
    shutil.copyfile(source, path)
    path.chmod(0o600)
    return path


def _host(target: Path, version: str) -> tuple[dict, dict, dict]:
    assert version in ("1.0.0", "1.0.1")
    inventory, spec = fixture(target, "D", tag="retrieval_handoff", layout="package",
                              package_name="retrieval_host")
    row = next(item for item in use_case_matrix()["rows"] if item["id"] == "D")
    package = target / "retrieval_host"
    for source, destination, expected in (
        (ROOT / row["source"], package / "retrieval_oracle.py", row["source_sha256"]),
        (ROOT / row["consumer_adapter"], package / "retrieval_consumer.py",
         row["consumer_adapter_sha256"]),
    ):
        assert file_hash(source) == expected
        shutil.copyfile(source, destination)
        assert file_hash(destination) == expected
    corpus_source = ROOT / row["consumer_corpus"]
    assert file_hash(corpus_source) == row["consumer_corpus_sha256"]
    passages = json.loads(corpus_source.read_text())["passages"]
    host_source = target / spec["source"]["file"]
    text = host_source.read_text(encoding="utf-8")
    lines = text.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("RECORDS = "))
    lines[index] = "RECORDS = " + repr(passages)
    text = "\n".join(lines) + "\n"
    old = ("STATE['kept'] = [item['id'] for item in action]\n"
           "    STATE['effects'].append('generate')\n"
           "    return STATE['kept'][:]")
    new = ("from . import retrieval_consumer\n"
           "    STATE['kept'] = retrieval_consumer.commit(request, action, "
           "host_approved=STATE['approval'])\n"
           "    STATE['effects'].append('generate')\n"
           "    return STATE['kept'][:]")
    assert text.count(old) == 1
    host_source.write_text(text.replace(old, new), encoding="utf-8")
    for case in spec["verification"]["cases"]:
        case["request"].update({"query": "approved", "expected_revision": 7})
    entry = spec["verification"]["entry_point"]
    (package / "console.py").write_text(
        f"from .{host_source.stem} import {entry}\n"
        "from pathlib import Path\nimport os\nimport time\n"
        "def main():\n"
        "    request = {'task_id':'retrieval-task','query':'approved','expected_revision':7}\n"
        f"    {entry}(request)\n"
        "    ready = os.environ.get('D_READY_PATH')\n"
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
        '[project]\nname = "jev-retrieval-host-fixture"\nversion = "' + version + '"\n'
        'requires-python = ">=3.13"\n'
        'dependencies = ["jev-integration-evaluator==1.3.0.dev12"]\n'
        '[project.scripts]\nretrieval-host = "retrieval_host.console:main"\n'
        '[tool.setuptools.packages.find]\ninclude = ["retrieval_host*"]\n', encoding="utf-8")
    cfg = load_config()
    cfg["repository"]["typescript_ast"] = False
    inventory = scan_repo(target, cfg)
    candidate = next(item for item in inventory["candidates"]
                     if item["source"]["symbol"] == "select_boundary_retrieval_handoff")
    reason = ("Reviewed D tail-call seam: pinned corpus provenance and material "
              "conflicts are required before the deterministic generation handoff")
    apply_reviews(inventory, {candidate["candidate_id"]: {
        "source_sha256": candidate["source"]["source_sha256"], "approved": True,
        "reviewer": "offline-retrieval-host-author", "reason": reason}}, cfg)
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
    inventory, spec, request = _host(target, version)
    assert validate_template_request(target, request)["status"] == "validated"
    template = tmp_path / (name + "-template")
    materialize_template(target, request, template)
    bundle = tmp_path / (name + "-bundle")
    plan = plan_implementation(target, inventory, spec["candidate_id"], spec, bundle)
    corpus = _corpus(tmp_path, name + "-corpus")
    probe = tmp_path / (name + "-probe")
    probe.mkdir(mode=0o700)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("D_CORPUS_PATH", str(corpus))
        env.setenv("D_EFFECT_PATH", str(probe / "effect-{pid}.json"))
        baseline = verify_implementation(target, bundle, "baseline", approve_execution=True)
        assert baseline["status"] == "baseline_passed"
        applied = apply_implementation(target, bundle, plan["bundle_digest"],
                                       baseline_sha256=baseline["receipt_sha256"])
        modified = verify_implementation(target, bundle, "modified", approve_execution=True,
                                         baseline_sha256=baseline["receipt_sha256"])
    assert modified["status"] == "verified"
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified["receipt_sha256"])["status"] == "verified"
    assert len(list(probe.glob("effect-*.json"))) >= 2
    return {"target": target, "bundle": bundle, "template": template,
            "version": version, "applied": applied, "modified": modified,
            "corpus": corpus}


def _scope(status: dict, plan: dict, action: str, **extra) -> dict:
    value = {"schema_version": "1.0", "kind": "template-delivery-scope-v1",
             "reference": "independent-retrieval-fixture-operator",
             "run_id": status["run_id"], "plan_sha256": plan["plan_sha256"],
             "trusted_session_head": status["session_head_sha256"],
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             "revoked": False,
             "grants": {name: name == action for name in
                        ("launch", "stop", "disable", "rollback", "upgrade")}, **extra}
    value["scope_sha256"] = digest(value)
    return value


def _expected_effect(corpus: Path) -> bytes:
    rows = json.loads(corpus.read_text())["passages"]
    assert [row["id"] for row in rows] == ["hit", "counter", "maybe", "noise"]
    assert [row["source_id"] for row in rows[:3]] == [
        "registry-one", "registry-two", "registry-three"]
    assert [row["stance"] for row in rows[:3]] == [
        "supports", "contradicts", "uncertain"]
    citations = [{"passage_id": row["id"], "source_id": row["source_id"],
                  "span": row["span"], "quote": row["text"],
                  "claim_id": row["claim_id"], "stance": row["stance"]}
                 for row in rows[:3]]
    expected = {"corpus_revision": 7, "corpus_sha256": file_hash(corpus),
                "status": "ready", "selected_ids": ["hit", "counter", "maybe"],
                "decisions": [["hit", "relevant"], ["counter", "irrelevant"],
                              ["maybe", "irrelevant"], ["noise", "irrelevant"]],
                "answer": {"query": "approved",
                           "summary": "conflicting and uncertain status evidence",
                           "citations": citations}}
    return (json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _observation(directory: Path, corpus: Path) -> tuple[dict, dict, bytes]:
    raw = _expected_effect(corpus)
    effect, ready = directory / "effect.json", directory / "ready.txt"
    checks = [{"role": "ready", "path": str(ready), "before_sha256": None,
               "expected_sha256": hashlib.sha256(b"ready\n").hexdigest()}]
    checks += [{"role": role, "path": str(effect), "before_sha256": None,
                "expected_sha256": hashlib.sha256(raw).hexdigest()}
               for role in ("entrypoint_reached", "integration_reachable",
                            "outcome_verified")]
    return ({"schema_version": "1.0", "kind": "template-delivery-observation-v1",
             "checks": checks},
            {"D_CORPUS_PATH": str(corpus), "D_EFFECT_PATH": str(effect),
             "D_READY_PATH": str(ready)}, raw)


def _observe(session: Path, status: dict) -> dict:
    for _ in range(300):
        status = delivery.observe_session(session,
            trusted_session_head=status["session_head_sha256"])
        if status["recorded_observations"]["outcome_verified"]:
            return status
        time.sleep(0.01)
    raise AssertionError("retrieval effect not observed")


def test_retrieval_consumer_refuses_missing_stale_and_unauthorized(tmp_path, monkeypatch):
    target = tmp_path / "retrieval-target"
    _host(target, "1.0.0")
    monkeypatch.syspath_prepend(str(target))
    consumer = importlib.import_module("retrieval_host.retrieval_consumer")
    rows = json.loads((ROOT / "examples/use-case-host/retrieval_corpus_v1.json").read_text())["passages"]
    corpus = _corpus(tmp_path, "corpus")
    effects = tmp_path / "effects"
    effects.mkdir(mode=0o700)
    output = effects / "effect.json"
    monkeypatch.setenv("D_CORPUS_PATH", str(corpus))
    monkeypatch.setenv("D_EFFECT_PATH", str(output))
    request = {"query": "approved", "expected_revision": 7}
    for changed, selected, approved in (
        (request, rows, False),
        ({**request, "expected_revision": 6}, rows, True),
        ({**request, "query": "unknown"}, rows, True),
        (request, [rows[0], rows[3]], True),
        (request, [rows[0], rows[0]], True),
        (request, [], True),
    ):
        with pytest.raises(ValueError):
            consumer.commit(changed, selected, host_approved=approved)
        assert not output.exists()
    monkeypatch.delenv("D_CORPUS_PATH")
    with pytest.raises(ValueError, match="D_CORPUS_PATH is required"):
        consumer.commit(request, rows, host_approved=True)
    monkeypatch.setenv("D_CORPUS_PATH", str(corpus))
    original = corpus.read_bytes()
    corpus.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="reviewed corpus bytes changed"):
        consumer.commit(request, rows, host_approved=True)
    assert not output.exists()
    corpus.write_bytes(original)
    monkeypatch.delenv("D_EFFECT_PATH")
    with pytest.raises(ValueError, match="D_EFFECT_PATH is required"):
        consumer.commit(request, rows, host_approved=True)
    assert not output.exists()
    monkeypatch.setenv("D_EFFECT_PATH", str(output))
    assert consumer.commit(request, rows, host_approved=True) == [
        "hit", "counter", "maybe", "noise"]
    assert output.read_bytes() == _expected_effect(corpus)
    with pytest.raises(ValueError, match="fresh"):
        consumer.commit(request, rows, host_approved=True)


def test_retrieval_installed_offline_upgrade_and_rollback(tmp_path):
    wheelhouse_name = os.environ.get("JEV_TEMPLATE_WHEELHOUSE")
    if not wheelhouse_name:
        pytest.skip("exact private offline wheelhouse required")
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    first = _applied(tmp_path, "retrieval-v1", "1.0.0")
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
                   "console_script": "retrieval-host", "configuration": configuration,
                   "secret_references": {}}
        adapter = host["target"] / "retrieval_host/retrieval_consumer.py"
        reviewed = adapter.read_bytes()
        adapter.write_bytes(reviewed + b"\n# drift\n")
        with pytest.raises(installer.InstallationError):
            installer.plan_package(request)
        adapter.write_bytes(reviewed)
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
        assert origin == environment / "venv/lib/python3.13/site-packages/retrieval_host/console.py"
        assert origin.is_file() and not origin.is_symlink()
        assert installed["installed"]["distributions"]["jev-retrieval-host-fixture"] == host["version"]
        return install_plan, installed

    original_plan, original_install = install(first, "package-v1")
    effects = tmp_path / "external-effects"
    effects.mkdir(mode=0o700)
    v1 = effects / "v1"
    v1.mkdir(mode=0o700)
    observation, launch_env, raw = _observation(v1, first["corpus"])
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
    assert (v1 / "effect.json").read_bytes() == raw
    assert (v1 / "ready.txt").read_bytes() == b"ready\n"
    effect = json.loads((v1 / "effect.json").read_text())
    assert effect["selected_ids"] == ["hit", "counter", "maybe"]
    assert [row["source_id"] for row in effect["answer"]["citations"]] == [
        "registry-one", "registry-two", "registry-three"]
    assert observed["recorded_observations"]["provider_reachable"] is False
    disable = _scope(observed, original_delivery, "disable")
    disabled = delivery.stop_session(session, scope=disable,
        approved_scope_sha256=disable["scope_sha256"], disable=True)
    assert disabled["stage"] == "disabled"

    second = _applied(tmp_path, "retrieval-v2", "1.0.1")
    new_plan, new_install = install(second, "package-v2")
    assert new_install["generation_id"] != original_install["generation_id"]
    v2 = effects / "v2"
    v2.mkdir(mode=0o700)
    new_observation, new_env, new_raw = _observation(v2, second["corpus"])
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
    assert (v2 / "effect.json").read_bytes() == new_raw
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
