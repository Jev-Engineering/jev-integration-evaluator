"""Source-bound L console through offline installed graph delivery and recovery."""
from __future__ import annotations

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
from tests.test_template_installation import _metadata
from tests.test_use_case_graph_bind import BINDING, PROFILE, _bound_host
from tests.test_use_case_graph_installed import (
    _database_readback, _observation, _observe, _scope,
)
from tests.use_case_faults import interrupted_apply_recovery, missing_secret_package_refusals


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='L bound installed journey requires Linux x86-64 CPython 3.13')


def _applied(tmp_path: Path, name: str, version: str,
             connected_authority_source: Path | None = None,
             generation_task: str | None = None) -> dict:
    target = tmp_path / name
    inventory, request = _bound_host(target, version=version, installed=True,
                                    connected_authority_source=connected_authority_source,
                                    generation_task=generation_task)
    prepared = prepare_template_binding(target, request, BINDING)
    bound = prepared['request']
    spec = bound['implementation_spec']
    assert spec['entrypoint_binding']['kind'] == 'task-loop-v1'
    assert validate_template_request(target, bound)['status'] == 'validated'
    template = tmp_path / (name + '-template')
    materialize_template(target, bound, template)
    bundle = tmp_path / (name + '-bundle')
    planned = plan_implementation(target, inventory, spec['candidate_id'], spec, bundle)
    probe = tmp_path / (name + '-probe')
    probe.mkdir(mode=0o700)
    with pytest.MonkeyPatch.context() as env:
        env.setenv('GRAPH_EFFECT_PATH', str(probe / 'graph-{pid}.json'))
        env.setenv('GRAPH_DB_PATH', str(probe / 'graph-{pid}.sqlite'))
        env.delenv('GRAPH_READY_PATH', raising=False)
        baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'baseline_passed'
        applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                       baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                         baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])['status'] == 'verified'
    assert list(probe.glob('graph-*.json'))
    assert b'start_jev_runtime' in (target / 'graph_host/console.py').read_bytes()
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
               'environment_parent': str(environments), 'console_script': 'graph-host',
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
    assert origin == environment / 'venv/lib/python3.13/site-packages/graph_host/console.py'
    assert origin.is_file() and not origin.is_symlink()
    assert file_hash(origin) == file_hash(host['target'] / 'graph_host/console.py')
    assert b'start_jev_runtime' in origin.read_bytes()
    assert installed['installed']['distributions']['jev-graph-host-fixture'] == host['version']
    return install_plan, installed


def _await_natural_exit(session: Path, status: dict) -> dict:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        status = delivery.observe_session(session,
            trusted_session_head=status['session_head_sha256'])
        if not status['current_process_alive']:
            return status
        time.sleep(.05)
    raise AssertionError('bound graph console did not complete its task')


def test_l_bound_installed_graph_lifecycle_and_revision_conflict(tmp_path):
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
    first = _applied(tmp_path, 'bound-graph-v1', '1.0.0')
    first_plan, first_receipt = _installed(
        tmp_path, first, wheelhouse, rows, requirements, environments, 'package-v1')
    missing_secret_package_refusals(first_plan['package_plan']['request'],
                                    tmp_path / 'package-without-secret')
    effects = tmp_path / 'external-effects'
    effects.mkdir(mode=0o700)
    v1 = effects / 'v1'
    v1.mkdir(mode=0o700)
    observation, launch_env, raw = _observation(v1)
    first_delivery = delivery.plan_delivery(first_plan,
        trusted_install_receipt_sha256=first_receipt['receipt_sha256'],
        observation=observation, launch_environment=launch_env)
    session = tmp_path / 'delivery-session'
    created = delivery.create_session(session, first_delivery)
    launch = _scope(created, first_delivery, 'launch')
    observed = _observe(session, delivery.launch_session(session, scope=launch,
        approved_scope_sha256=launch['scope_sha256']))
    assert (v1 / 'graph.json').read_bytes() == raw
    assert (v1 / 'ready.txt').read_bytes() == b'ready\n'
    _database_readback(v1 / 'graph.sqlite', raw)
    actual = json.loads(raw)
    assert actual['receipt'] == actual['merges'][0] == actual['audits'][0]
    assert actual['revision'] == 1
    assert observed['recorded_observations']['provider_reachable'] is False
    observed = _await_natural_exit(session, observed)
    disable = _scope(observed, first_delivery, 'disable')
    disabled = delivery.stop_session(session, scope=disable,
        approved_scope_sha256=disable['scope_sha256'], disable=True)
    assert disabled['stage'] == 'disabled'

    # A second normal installed command sees the current SQLite revision and
    # withholds a new merge/effect when the reviewed request remains at zero.
    conflict = effects / 'conflict'
    conflict.mkdir(mode=0o700)
    existing_hash = file_hash(v1 / 'graph.sqlite')
    refused = subprocess.run([first_receipt['installed']['console_script']],
        cwd=tmp_path, env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path),
                           'LANG': 'C.UTF-8', 'JEV_RUNTIME_MODE': 'off',
                           'GRAPH_DB_PATH': str(v1 / 'graph.sqlite'),
                           'GRAPH_EFFECT_PATH': str(conflict / 'graph.json')},
        capture_output=True, text=True, timeout=30)
    assert refused.returncode != 0 and 'revision conflict' in refused.stderr
    assert file_hash(v1 / 'graph.sqlite') == existing_hash
    assert list(conflict.iterdir()) == []
    _database_readback(v1 / 'graph.sqlite', raw)

    second = _applied(tmp_path, 'bound-graph-v2', '1.0.1')
    second_plan, second_receipt = _installed(
        tmp_path, second, wheelhouse, rows, requirements, environments, 'package-v2')
    assert second_receipt['generation_id'] != first_receipt['generation_id']
    v2 = effects / 'v2'
    v2.mkdir(mode=0o700)
    next_observation, next_env, next_raw = _observation(v2)
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
    assert (v2 / 'graph.json').read_bytes() == next_raw
    _database_readback(v2 / 'graph.sqlite', next_raw)
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
        assert file_hash(host['target'] / 'graph_host/console.py') == \
            host['spec']['entrypoint_binding']['file_sha256']


def test_l_bound_interrupted_apply_requires_recovery_and_owned_rollback(tmp_path):
    result = interrupted_apply_recovery(
        tmp_path, sys.modules[__name__], 'interrupted-graph',
        lambda: _applied(tmp_path, 'interrupted-graph', '1.0.0'),
        letter='L', consumer='graph_host/graph_runtime.py')
    assert result['target'] == tmp_path / 'interrupted-graph'
