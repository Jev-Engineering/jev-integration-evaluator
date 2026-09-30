"""Source-bound H task loop through offline installed retention delivery."""
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
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.template_catalog import (
    materialize_template, prepare_template_binding, validate_template_request,
)
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, implementation_status, plan_implementation,
    rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from tests.test_reusable_templates import fixture_module
from tests.test_template_installation import _metadata
from tests.test_use_case_retention_bind import BINDING, PROFILE, _bound_host
from tests.test_use_case_retention_host import _probe_effect_path, _scope


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='H bound installed journey requires Linux x86-64 CPython 3.13')


def _expected() -> tuple[bytes, list[dict]]:
    values = (('pinned', 'region east', 'verified_source', 'reviewed-one'),
              ('work', 'task open', 'tool', 'run-one'),
              ('old', 'noise item', 'tool', 'run-old'))
    items = [{'id': name, 'text': value, 'source_kind': kind,
              'source_ref': reference, 'capture_revision': 1,
              'token_count': len(value.split()),
              'byte_sha256': hashlib.sha256(value.encode()).hexdigest()}
             for name, value, kind, reference in values]
    return (json.dumps(items, sort_keys=True, separators=(',', ':')) + '\n').encode(), items


def _applied(tmp_path: Path, name: str, version: str) -> dict:
    target = tmp_path / name
    inventory, _, request = _bound_host(target, version=version, installed=True)
    prepared = prepare_template_binding(target, request, BINDING)
    bound = prepared['request']
    spec = bound['implementation_spec']
    assert spec['entrypoint_binding']['kind'] == 'task-loop-v1'
    assert validate_template_request(target, bound)['status'] == 'validated'
    template = tmp_path / (name + '-template')
    materialize_template(target, bound, template)
    bundle = tmp_path / (name + '-bundle')
    planned = plan_implementation(target, inventory, spec['candidate_id'], spec, bundle)
    with pytest.MonkeyPatch.context() as env:
        env.setenv('H_RETAINED_PATH', _probe_effect_path(tmp_path, name + '-probe'))
        env.delenv('H_READY_PATH', raising=False)
        baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'baseline_passed'
        applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                       baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                         baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])['status'] == 'verified'
    assert b'start_jev_runtime' in (target / 'retention_host/console.py').read_bytes()
    return {'target': target, 'bundle': bundle, 'template': template,
            'applied': applied, 'modified': modified, 'version': version, 'spec': spec}


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
               'build_tools': {name: importlib.metadata.version(name)
                               for name in ('pip', 'setuptools', 'wheel')},
               'wheelhouse': str(wheelhouse), 'wheels': rows,
               'requirements': requirements, 'package_directory': str(tmp_path / name),
               'environment_parent': str(environments), 'console_script': 'retention-host',
               'configuration': configuration, 'secret_references': {}}
    package_plan = installer.plan_package(request)
    built = installer.build_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_install(package_plan, built)
    installed = installer.install_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'
    environment = Path(installed['environment'])
    python = Path(installed['installed']['python'])
    origin = Path(installed['installed']['entrypoint_origin'])
    assert python.is_relative_to(environment / 'venv') and python.is_symlink()
    assert python.resolve(strict=True) == Path(sys.executable).resolve(strict=True)
    assert origin == environment / 'venv/lib/python3.13/site-packages/retention_host/console.py'
    assert origin.is_file() and not origin.is_symlink()
    assert file_hash(origin) == file_hash(host['target'] / 'retention_host/console.py')
    assert b'start_jev_runtime' in origin.read_bytes()
    for member in ('retention_consumer.py', 'retention_oracle.py'):
        assert file_hash(environment / 'venv/lib/python3.13/site-packages/retention_host' / member) == \
            file_hash(host['target'] / 'retention_host' / member)
    assert installed['installed']['distributions']['jev-retention-host-fixture'] == host['version']
    return install_plan, installed


def _observation(directory: Path, expected_raw: bytes) -> tuple[dict, dict]:
    retained, ready = directory / 'retained.json', directory / 'ready.txt'
    checks = [{'role': 'ready', 'path': str(ready), 'before_sha256': None,
               'expected_sha256': hashlib.sha256(b'ready\n').hexdigest()}]
    checks += [{'role': role, 'path': str(retained), 'before_sha256': None,
                'expected_sha256': hashlib.sha256(expected_raw).hexdigest()}
               for role in ('entrypoint_reached', 'integration_reachable', 'outcome_verified')]
    return ({'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
             'checks': checks},
            {'H_RETAINED_PATH': str(retained), 'H_READY_PATH': str(ready),
             'H_COMMAND': '/prune'})


def _observe(session: Path, status: dict) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = delivery.observe_session(session,
            trusted_session_head=status['session_head_sha256'])
        if (status['recorded_observations']['ready']
                and status['recorded_observations']['outcome_verified']):
            return status
        time.sleep(.01)
    raise AssertionError('independent retention effect not observed')


def _await_natural_exit(session: Path, status: dict) -> dict:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        status = delivery.observe_session(session,
            trusted_session_head=status['session_head_sha256'])
        if not status['current_process_alive']:
            return status
        time.sleep(.05)
    raise AssertionError('bound retention console did not finish')


def _direct(installed: dict, directory: Path, *, command: str | None = '/prune',
            scenario: str | None = None, retained: Path | None = None) -> subprocess.CompletedProcess:
    directory.mkdir(mode=0o700)
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(directory), 'LANG': 'C.UTF-8',
           'JEV_RUNTIME_MODE': 'off',
           'H_RETAINED_PATH': str(retained or directory / 'retained.json')}
    if command is not None:
        env['H_COMMAND'] = command
    if scenario is not None:
        env['H_REQUEST_SCENARIO'] = scenario
    return subprocess.run([installed['installed']['console_script']], cwd=directory,
                          env=env, capture_output=True, text=True, timeout=30)


def test_h_bound_installed_retention_lifecycle_and_refusals(tmp_path):
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
    expected_raw, items = _expected()
    first = _applied(tmp_path, 'bound-retention-v1', '1.0.0')
    first_plan, first_receipt = _installed(
        tmp_path, first, wheelhouse, rows, requirements, environments, 'package-v1')
    effects = tmp_path / 'external-effects'
    effects.mkdir(mode=0o700)
    v1 = effects / 'v1'
    v1.mkdir(mode=0o700)
    observation, launch_env = _observation(v1, expected_raw)
    first_delivery = delivery.plan_delivery(first_plan,
        trusted_install_receipt_sha256=first_receipt['receipt_sha256'],
        observation=observation, launch_environment=launch_env)
    session = tmp_path / 'delivery-session'
    created = delivery.create_session(session, first_delivery)
    launch = _scope(created, first_delivery, 'launch')
    observed = _observe(session, delivery.launch_session(session, scope=launch,
        approved_scope_sha256=launch['scope_sha256']))
    assert (v1 / 'retained.json').read_bytes() == expected_raw
    assert (v1 / 'ready.txt').read_bytes() == b'ready\n'
    assert json.loads(expected_raw) == items
    assert [item['id'] for item in items] == ['pinned', 'work', 'old']
    assert items[0]['source_ref'] == 'reviewed-one'
    assert items[0]['byte_sha256'] == hashlib.sha256(b'region east').hexdigest()
    oracle = fixture_module('examples/coding-agent/retention_oracle.py',
                            'issue59_h_bound_installed_recall')
    recall = oracle.score_recall('authoritative region sources', {
        'applicable': True, 'expected_answer': 'east', 'required_source_ids': ['pinned'],
        'required_source_sha256': {'pinned': items[0]['byte_sha256']}},
        json.loads((v1 / 'retained.json').read_text()), [])
    assert recall['success'] is True and recall['citation_ids'] == ['pinned']
    assert observed['recorded_observations']['provider_reachable'] is False
    assert delivery.session_status(session,
        trusted_session_head=observed['session_head_sha256'])['current_installation'] == 'current_verified'
    observed = _await_natural_exit(session, observed)
    disable = _scope(observed, first_delivery, 'disable')
    disabled = delivery.stop_session(session, scope=disable,
        approved_scope_sha256=disable['scope_sha256'], disable=True)
    assert disabled['stage'] == 'disabled'

    for name, command, scenario, error in (
        ('duplicate', '/prune', 'duplicate', 'duplicate_task_identity'),
        ('budget', '/prune', 'budget', 'retention task budget refused'),
        ('compact', '/compact', None, 'explicit /prune choice required'),
        ('missing', None, None, 'H_COMMAND')):
        directory = effects / name
        refused = _direct(first_receipt, directory, command=command, scenario=scenario)
        assert refused.returncode != 0 and error in refused.stderr
        assert list(directory.iterdir()) == []
    occupied_dir = effects / 'occupied'
    existing_hash = file_hash(v1 / 'retained.json')
    occupied = _direct(first_receipt, occupied_dir, retained=v1 / 'retained.json')
    assert occupied.returncode != 0 and 'fresh, absolute and unlinked' in occupied.stderr
    assert file_hash(v1 / 'retained.json') == existing_hash
    assert list(occupied_dir.iterdir()) == []

    second = _applied(tmp_path, 'bound-retention-v2', '1.0.1')
    second_plan, second_receipt = _installed(
        tmp_path, second, wheelhouse, rows, requirements, environments, 'package-v2')
    assert second_receipt['generation_id'] != first_receipt['generation_id']
    v2 = effects / 'v2'
    v2.mkdir(mode=0o700)
    next_observation, next_env = _observation(v2, expected_raw)
    next_delivery = delivery.plan_delivery(second_plan,
        trusted_install_receipt_sha256=second_receipt['receipt_sha256'],
        observation=next_observation, launch_environment=next_env)
    upgrade = _scope(disabled, first_delivery, 'upgrade')
    upgrade['upgrade_plan_sha256'] = next_delivery['plan_sha256']
    upgrade['scope_sha256'] = digest({k: v for k, v in upgrade.items()
                                     if k != 'scope_sha256'})
    upgraded = delivery.upgrade_session(session, next_delivery, scope=upgrade,
        approved_scope_sha256=upgrade['scope_sha256'])
    assert upgraded['stage'] == 'upgrade_staged'
    launch_new = _scope(upgraded, next_delivery, 'launch')
    observed_new = _observe(session, delivery.launch_session(session, scope=launch_new,
        approved_scope_sha256=launch_new['scope_sha256']))
    assert (v2 / 'retained.json').read_bytes() == expected_raw
    observed_new = _await_natural_exit(session, observed_new)
    disable_new = _scope(observed_new, next_delivery, 'disable')
    disabled_new = delivery.stop_session(session, scope=disable_new,
        approved_scope_sha256=disable_new['scope_sha256'], disable=True)
    rollback = _scope(disabled_new, next_delivery, 'rollback')
    rollback['rollback_digest'] = disabled_new['previous_generation_rollback_digest']
    rollback['scope_sha256'] = digest({k: v for k, v in rollback.items()
                                      if k != 'scope_sha256'})
    rolled = delivery.rollback_session(session, scope=rollback,
        approved_scope_sha256=rollback['scope_sha256'])
    assert rolled['stage'] == 'rolled_back'
    assert rolled['generation_id'] == first_receipt['generation_id']
    assert Path(first_receipt['environment']).is_dir()
    assert Path(second_receipt['environment']).is_dir()
    for host in (second, first):
        assert rollback_implementation(host['target'], host['bundle'],
            host['applied']['rollback_digest'])['status'] == 'rolled_back'
        assert file_hash(host['target'] / 'retention_host/console.py') == \
            host['spec']['entrypoint_binding']['file_sha256']
