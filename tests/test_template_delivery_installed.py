"""Actual installed console invocation under the bounded offline delivery profile."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.metadata
import os
from pathlib import Path
import platform
import sys
import time

import pytest

from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.template_catalog import prepare_template_binding, materialize_template
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation, implementation_status)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator import template_delivery as delivery
from tests.test_template_python_entrypoint import _prepared
from tests.test_template_installation import _metadata


pytestmark = pytest.mark.skipif(
    not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
         and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)),
    reason='Installed delivery profile is Linux x86-64 CPython 3.13 only')


def _scope(result, plan, action):
    value = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
             'reference': 'independent-installed-fixture-operator',
             'run_id': result['run_id'], 'plan_sha256': plan['plan_sha256'],
             'trusted_session_head': result['session_head_sha256'],
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             'revoked': False,
             'grants': {'launch': action == 'launch', 'stop': action == 'stop',
                        'disable': action == 'disable', 'rollback': action == 'rollback',
                        'upgrade': action == 'upgrade'}}
    value['scope_sha256'] = digest(value)
    return value


def test_bound_template_installed_console_is_supervised_with_direct_effect(tmp_path):
    wheelhouse_name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not wheelhouse_name:
        pytest.skip('Explicitly prepared offline template wheelhouse required')
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    target, request, binding = _prepared(tmp_path, 'package', 'delivery_actual',
                                         effect_sink=True)
    tools = {name: importlib.metadata.version(name) for name in ('pip', 'setuptools', 'wheel')}
    project = target / 'pyproject.toml'
    source = project.read_text(encoding='utf-8')
    source = source.replace('requires = ["setuptools>=68"]',
                            'requires = ["setuptools==' + tools['setuptools'] +
                            '", "wheel==' + tools['wheel'] + '"]')
    source = source.replace('requires-python = ">=3.10"',
                            'requires-python = ">=3.13"\n'
                            'dependencies = ["jev-integration-evaluator==1.3.0.dev12"]')
    project.write_text(source, encoding='utf-8')
    prepared = prepare_template_binding(target, request, binding)
    bound = prepared['request']
    template = tmp_path / 'materialized'
    materialize_template(target, bound, template)
    spec = bound['implementation_spec']
    bundle = tmp_path / 'implementation-bundle'
    planned = plan_implementation(target, bound['reviewed_inventory'],
                                  spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    apply_implementation(target, bundle, planned['bundle_digest'],
                         baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    wheels = sorted(wheelhouse.glob('*.whl'))
    rows = [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels]
    requirements = [{'name': name, 'version': version,
                     'wheel': path.name, 'sha256': file_hash(path)}
                    for path in wheels for name, version in [_metadata(path)]]
    environments = tmp_path / 'environments'
    environments.mkdir(mode=0o700)
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': 'env:TYPESAFE_API_KEY'}}
    package_request = {
        'schema_version': '1.0', 'host_root': str(target),
        'implementation_bundle': str(bundle),
        'trusted_modified_receipt_sha256': modified['receipt_sha256'],
        'template_directory': str(template),
        'reviewed_package_source_sha256': digest(installer._tree(target)),
        'reviewed_configuration_sha256': digest(config),
        'interpreter': sys.executable, 'build_tools': tools,
        'wheelhouse': str(wheelhouse), 'wheels': rows, 'requirements': requirements,
        'package_directory': str(tmp_path / 'package'),
        'environment_parent': str(environments), 'console_script': binding['script'],
        'configuration': config, 'secret_references': {'credential': 'env:TYPESAFE_API_KEY'}}
    package_plan = installer.plan_package(package_request)
    package_receipt = installer.build_package(package_plan,
                                              approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_install(package_plan, package_receipt)
    installed = installer.install_package(install_plan,
                                          approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'
    sink = tmp_path / 'actual-effect.bin'
    ready_marker = tmp_path / 'actual-ready.bin'
    expected = digest_bytes(b'first\n')
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [
                       {'role': 'ready', 'path': str(ready_marker), 'before_sha256': None,
                        'expected_sha256': digest_bytes(b'ready\n')}]
                   + [
                       {'role': role, 'path': str(sink), 'before_sha256': None,
                        'expected_sha256': expected}
                       for role in ('entrypoint_reached',
                                    'integration_reachable', 'outcome_verified')]}
    delivery_plan = delivery.plan_delivery(install_plan,
        trusted_install_receipt_sha256=installed['receipt_sha256'], observation=observation,
        launch_environment={'DELIVERY_EFFECT_PATH': str(sink),
                            'DELIVERY_READY_PATH': str(ready_marker),
                            'DELIVERY_EFFECT_HOLD_SECONDS': '0.5'})
    session = tmp_path / 'delivery-session'
    created = delivery.create_session(session, delivery_plan)
    launch_scope = _scope(created, delivery_plan, 'launch')
    launched = delivery.launch_session(session, scope=launch_scope,
        approved_scope_sha256=launch_scope['scope_sha256'])
    observed = launched
    for _ in range(200):
        observed = delivery.observe_session(session,
            trusted_session_head=observed['session_head_sha256'])
        if observed['recorded_observations']['outcome_verified']:
            break
        time.sleep(0.01)
    assert observed['recorded_observations']['ready'] is True
    assert observed['recorded_observations']['entrypoint_reached'] is True
    assert observed['recorded_observations']['integration_reachable'] is True
    assert observed['recorded_observations']['outcome_verified'] is True
    assert observed['current_process_alive'] is True
    assert observed['current_ready'] is True
    assert observed['current_integration_reachable'] is True
    assert observed['recorded_observations']['provider_reachable'] is False
    assert observed['recorded_observations']['mode_authorized'] is True
    disable_scope = _scope(observed, delivery_plan, 'disable')
    disabled = delivery.stop_session(session, scope=disable_scope,
        approved_scope_sha256=disable_scope['scope_sha256'], disable=True,
        grace_seconds=5)
    assert disabled['stage'] == 'disabled'
    assert disabled['current_process_alive'] is False
    assert delivery.session_status(session,
        trusted_session_head=disabled['session_head_sha256'])['current_ready'] is False
    assert sink.read_bytes() == b'first\n'
    assert ready_marker.read_bytes() == b'ready\n'
    rollback_scope = _scope(disabled, delivery_plan, 'rollback')
    rollback_scope['rollback_digest'] = implementation_status(target, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])['rollback_digest']
    rollback_scope['scope_sha256'] = digest({k: v for k, v in rollback_scope.items()
                                              if k != 'scope_sha256'})
    rolled = delivery.rollback_session(session, scope=rollback_scope,
        approved_scope_sha256=rollback_scope['scope_sha256'])
    assert rolled['stage'] == 'rolled_back'
    assert Path(installed['environment']).is_dir()
    assert delivery.session_status(session,
        trusted_session_head=rolled['session_head_sha256'])['current_installation'] == 'drift_or_unavailable'


def digest_bytes(raw: bytes) -> str:
    import hashlib
    return hashlib.sha256(raw).hexdigest()
