"""Offline D binder through the real installed, supervised console lifecycle."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from jev_integration_evaluator import template_delivery as delivery
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.template_catalog import (
    materialize_template, prepare_template_binding, validate_template_request,
)
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, implementation_status, plan_implementation,
    rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from tests.test_template_installation import _metadata
from tests.test_use_case_retrieval_bind import BINDING, _bound_host
from tests.test_use_case_retrieval_host import (
    PROFILE, _corpus, _expected_effect, _scope, _observe,
)


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='D bound installed journey requires Linux x86-64 CPython 3.13')


def _applied(tmp_path: Path, name: str, version: str,
             connected_authority_source: Path | None = None) -> dict:
    target = tmp_path / name
    inventory, request = _bound_host(target, version=version, installed=True,
                                    connected_authority_source=connected_authority_source)
    prepared = prepare_template_binding(target, request, BINDING)
    bound = prepared['request']
    spec = bound['implementation_spec']
    assert spec['entrypoint_binding']['kind'] == 'task-loop-v1'
    assert validate_template_request(target, bound)['status'] == 'validated'
    template = tmp_path / (name + '-template')
    materialize_template(target, bound, template)
    bundle = tmp_path / (name + '-bundle')
    planned = plan_implementation(target, inventory, spec['candidate_id'], spec, bundle)
    corpus = _corpus(tmp_path, name + '-corpus')
    probe = tmp_path / (name + '-probe')
    probe.mkdir(mode=0o700)
    with pytest.MonkeyPatch.context() as env:
        env.setenv('D_CORPUS_PATH', str(corpus))
        env.setenv('D_EFFECT_PATH', str(probe / 'effect-{pid}.json'))
        baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'baseline_passed'
        applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                       baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                         baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])['status'] == 'verified'
    assert b'start_jev_runtime' in (target / 'retrieval_host/console.py').read_bytes()
    assert len(list(probe.glob('effect-*.json'))) >= 2
    return {'target': target, 'bundle': bundle, 'template': template,
            'applied': applied, 'modified': modified, 'corpus': corpus,
            'version': version, 'spec': spec}


def _installed(tmp_path: Path, host: dict, wheelhouse: Path, rows: list[dict],
               requirements: list[dict], environments: Path, name: str) -> tuple[dict, dict]:
    configuration = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    request = {'schema_version': '1.0', 'host_root': str(host['target']),
               'implementation_bundle': str(host['bundle']),
               'trusted_modified_receipt_sha256': host['modified']['receipt_sha256'],
               'template_directory': str(host['template']),
               'reviewed_package_source_sha256': digest(installer._tree(host['target'])),
               'reviewed_configuration_sha256': digest(configuration),
               'interpreter': sys.executable,
               'build_tools': {tool: importlib.metadata.version(tool)
                               for tool in ('pip', 'setuptools', 'wheel')},
               'wheelhouse': str(wheelhouse), 'wheels': rows,
               'requirements': requirements, 'package_directory': str(tmp_path / name),
               'environment_parent': str(environments),
               'console_script': 'retrieval-host', 'configuration': configuration,
               'secret_references': {}}
    package_plan = installer.plan_package(request)
    package_receipt = installer.build_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_install(package_plan, package_receipt)
    installed = installer.install_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'
    root = Path(installed['environment'])
    origin = Path(installed['installed']['entrypoint_origin'])
    assert origin == root / 'venv/lib/python3.13/site-packages/retrieval_host/console.py'
    assert origin.is_file() and not origin.is_symlink()
    assert file_hash(origin) == file_hash(host['target'] / 'retrieval_host/console.py')
    assert b'start_jev_runtime' in origin.read_bytes()
    assert installed['installed']['distributions']['jev-retrieval-host-fixture'] == host['version']
    return install_plan, installed


def _observation(folder: Path, corpus: Path) -> tuple[dict, dict, bytes]:
    raw = _expected_effect(corpus)
    first = folder / 'retrieval-one.json'
    second = folder / 'retrieval-two.json'
    ready = folder / 'ready.txt'
    checks = [
        {'role': 'ready', 'path': str(ready), 'before_sha256': None,
         'expected_sha256': hashlib.sha256(b'ready\n').hexdigest()},
        {'role': 'entrypoint_reached', 'path': str(first), 'before_sha256': None,
         'expected_sha256': hashlib.sha256(raw).hexdigest()},
        {'role': 'integration_reachable', 'path': str(second), 'before_sha256': None,
         'expected_sha256': hashlib.sha256(raw).hexdigest()},
        {'role': 'outcome_verified', 'path': str(second), 'before_sha256': None,
         'expected_sha256': hashlib.sha256(raw).hexdigest()},
    ]
    return ({'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
             'checks': checks},
            {'D_CORPUS_PATH': str(corpus), 'D_EFFECT_DIRECTORY': str(folder)}, raw)


def _await_natural_exit(session: Path, status: dict) -> dict:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        status = delivery.observe_session(session,
            trusted_session_head=status['session_head_sha256'])
        if not status['current_process_alive']:
            return status
        time.sleep(.05)
    raise AssertionError('bound retrieval console did not finish both tasks')


def test_d_bound_installed_two_task_lifecycle_upgrade_and_rollback(tmp_path):
    wheelhouse_name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not wheelhouse_name:
        pytest.skip('exact private offline wheelhouse required')
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    wheels = sorted(wheelhouse.glob('*.whl'))
    assert wheels
    rows = [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels]
    requirements = [{'name': name, 'version': version, 'wheel': path.name,
                     'sha256': file_hash(path)}
                    for path in wheels for name, version in [_metadata(path)]]
    environments = tmp_path / 'environments'
    environments.mkdir(mode=0o700)
    first = _applied(tmp_path, 'bound-v1', '1.0.0')
    first_plan, first_receipt = _installed(
        tmp_path, first, wheelhouse, rows, requirements, environments, 'package-v1')
    effects = tmp_path / 'external-effects'
    effects.mkdir(mode=0o700)
    v1 = effects / 'v1'
    v1.mkdir(mode=0o700)
    observation, launch_env, raw = _observation(v1, first['corpus'])
    first_delivery = delivery.plan_delivery(first_plan,
        trusted_install_receipt_sha256=first_receipt['receipt_sha256'],
        observation=observation, launch_environment=launch_env)
    session = tmp_path / 'delivery-session'
    created = delivery.create_session(session, first_delivery)
    launch = _scope(created, first_delivery, 'launch')
    observed = _observe(session, delivery.launch_session(session, scope=launch,
        approved_scope_sha256=launch['scope_sha256']))
    for task in ('retrieval-one', 'retrieval-two'):
        effect = json.loads((v1 / (task + '.json')).read_bytes())
        assert (v1 / (task + '.json')).read_bytes() == raw
        assert effect['answer']['disposition'] == 'withheld_conflict'
        assert effect['answer']['answer'] is None
        assert [item['source_id'] for item in effect['answer']['passages']] == [
            'registry-one', 'registry-two', 'registry-three']
        validate_contract(effect['answer'], 'retrieval-answer-handoff-v1')
    assert (v1 / 'ready.txt').read_bytes() == b'ready\n'
    assert (v1 / 'owner.txt').read_bytes() == b'one-runtime-startup\n'
    assert observed['recorded_observations']['provider_reachable'] is False
    observed = _await_natural_exit(session, observed)
    disable = _scope(observed, first_delivery, 'disable')
    disabled = delivery.stop_session(session, scope=disable,
        approved_scope_sha256=disable['scope_sha256'], disable=True)
    assert disabled['stage'] == 'disabled'

    # The installed generated loop refuses repeated task identity before startup.
    duplicate = effects / 'duplicate'
    duplicate.mkdir(mode=0o700)
    script = Path(first_receipt['installed']['console_script'])
    clean = {'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path), 'LANG': 'C.UTF-8',
             'JEV_RUNTIME_MODE': 'off', 'D_TASKS': 'duplicate',
             'D_CORPUS_PATH': str(first['corpus']),
             'D_EFFECT_DIRECTORY': str(duplicate)}
    refused = subprocess.run([str(script)], cwd=tmp_path, env=clean,
                             capture_output=True, text=True, timeout=30)
    assert refused.returncode != 0 and 'duplicate_task_identity' in refused.stderr
    assert list(duplicate.iterdir()) == []
    invalid_budget = effects / 'invalid-budget'
    invalid_budget.mkdir(mode=0o700)
    refused_budget = subprocess.run([str(script)], cwd=tmp_path,
        env={**clean, 'D_TASKS': 'two', 'D_BUDGET': 'invalid',
             'D_EFFECT_DIRECTORY': str(invalid_budget)},
        capture_output=True, text=True, timeout=30)
    assert refused_budget.returncode != 0
    assert (invalid_budget / 'owner.txt').read_bytes() == b'one-runtime-startup\n'
    assert sorted(path.name for path in invalid_budget.iterdir()) == ['owner.txt']

    second = _applied(tmp_path, 'bound-v2', '1.0.1')
    second_plan, second_receipt = _installed(
        tmp_path, second, wheelhouse, rows, requirements, environments, 'package-v2')
    assert second_receipt['generation_id'] != first_receipt['generation_id']
    v2 = effects / 'v2'
    v2.mkdir(mode=0o700)
    next_observation, next_env, next_raw = _observation(v2, second['corpus'])
    next_delivery = delivery.plan_delivery(second_plan,
        trusted_install_receipt_sha256=second_receipt['receipt_sha256'],
        observation=next_observation, launch_environment=next_env)
    upgrade = _scope(disabled, first_delivery, 'upgrade',
                     upgrade_plan_sha256=next_delivery['plan_sha256'])
    upgraded = delivery.upgrade_session(session, next_delivery, scope=upgrade,
        approved_scope_sha256=upgrade['scope_sha256'])
    assert upgraded['stage'] == 'upgrade_staged'
    launch_new = _scope(upgraded, next_delivery, 'launch')
    observed_new = _observe(session, delivery.launch_session(session, scope=launch_new,
        approved_scope_sha256=launch_new['scope_sha256']))
    assert (v2 / 'retrieval-one.json').read_bytes() == next_raw
    assert (v2 / 'retrieval-two.json').read_bytes() == next_raw
    assert (v2 / 'owner.txt').read_bytes() == b'one-runtime-startup\n'
    observed_new = _await_natural_exit(session, observed_new)
    disable_new = _scope(observed_new, next_delivery, 'disable')
    disabled_new = delivery.stop_session(session, scope=disable_new,
        approved_scope_sha256=disable_new['scope_sha256'], disable=True)
    rollback = _scope(disabled_new, next_delivery, 'rollback',
        rollback_digest=disabled_new['previous_generation_rollback_digest'])
    rolled = delivery.rollback_session(session, scope=rollback,
        approved_scope_sha256=rollback['scope_sha256'])
    assert rolled['stage'] == 'rolled_back'
    assert rolled['generation_id'] == first_receipt['generation_id']
    assert Path(first_receipt['environment']).is_dir()
    assert Path(second_receipt['environment']).is_dir()
    for host in (second, first):
        assert rollback_implementation(host['target'], host['bundle'],
            host['applied']['rollback_digest'])['status'] == 'rolled_back'
        assert file_hash(host['target'] / 'retrieval_host/console.py') == \
            host['spec']['entrypoint_binding']['file_sha256']
