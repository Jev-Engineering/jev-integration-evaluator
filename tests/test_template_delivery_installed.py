"""Actual installed console invocation under the bounded offline delivery profile."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from copy import deepcopy
import importlib.metadata
import os
from pathlib import Path
import platform
import sys
import time

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.template_catalog import prepare_template_binding, materialize_template
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation, implementation_status)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator import template_delivery as delivery
from tests.test_template_python_entrypoint import _prepared
from tests.test_template_installation import _prepared as _package_prepared
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
    blocked_scope = _scope(disabled, delivery_plan, 'launch')
    with pytest.raises(delivery.DeliveryError, match='delivery_launch_already_attempted_or_blocked'):
        delivery.launch_session(session, scope=blocked_scope,
            approved_scope_sha256=blocked_scope['scope_sha256'])
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


def _installed_version(tmp_path, version):
    tmp_path.mkdir(mode=0o700, exist_ok=True)
    tmp_path.chmod(0o700)
    request = _package_prepared(tmp_path)
    project = Path(request['host_root']) / 'pyproject.toml'
    source = project.read_text(encoding='utf-8')
    assert 'version = "0.1.0"' in source
    project.write_text(source.replace('version = "0.1.0"',
                                      'version = "' + version + '"'), encoding='utf-8')
    request['reviewed_package_source_sha256'] = digest(installer._tree(Path(request['host_root'])))
    package_plan = installer.plan_package(request)
    package_receipt = installer.build_package(package_plan,
        approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_install(package_plan, package_receipt)
    receipt = installer.install_package(install_plan,
        approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'
    assert receipt['installed']['distributions'][package_plan['project_name']] == version
    ready = tmp_path / 'ready.bin'
    effect = tmp_path / 'effect.bin'
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [{'role': 'ready', 'path': str(ready), 'before_sha256': None,
                               'expected_sha256': digest_bytes(b'ready\n')},
                              {'role': 'entrypoint_reached', 'path': str(effect),
                               'before_sha256': None, 'expected_sha256': digest_bytes(b'first\n')},
                              {'role': 'integration_reachable', 'path': str(effect),
                               'before_sha256': None, 'expected_sha256': digest_bytes(b'first\n')}]}
    plan = delivery.plan_delivery(install_plan,
        trusted_install_receipt_sha256=receipt['receipt_sha256'],
        observation=observation)
    return request, install_plan, receipt, plan


def test_actual_installed_source_configuration_and_secret_drift_refuse_launch(tmp_path):
    if not os.environ.get('JEV_TEMPLATE_WHEELHOUSE'):
        pytest.skip('Explicit offline wheelhouse required')
    request, install_plan, receipt, plan = _installed_version(tmp_path / 'old', '0.1.0')
    session = tmp_path / 'session'
    created = delivery.create_session(session, plan)
    scope = _scope(created, plan, 'launch')
    source_path = Path(request['host_root']) / 'host_cli.py'
    original_source = source_path.read_bytes()
    environment_config = Path(receipt['environment']) / 'config.json'
    original_config = environment_config.read_bytes()
    for target, changed in (
        (source_path, original_source + b'\n# changed after source review\n'),
        (environment_config, b'{"jev_runtime":{"mode":"shadow","credential_ref":"env:TYPESAFE_API_KEY"}}\n'),
        (environment_config, b'{"jev_runtime":{"mode":"off","credential_ref":"env:OTHER"}}\n'),
    ):
        target.write_bytes(changed)
        with pytest.raises((InputError, installer.InstallationError, delivery.DeliveryError)):
            delivery.launch_session(session, scope=scope,
                approved_scope_sha256=scope['scope_sha256'])
        assert delivery.session_status(session)['stage'] == 'installed'
        target.write_bytes(original_source if target == source_path else original_config)
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'
    assert delivery.session_status(session,
        trusted_session_head=created['session_head_sha256'])['current_installation'] == 'current_verified'


def test_actual_changed_version_upgrade_and_incompatible_schema_refusal(tmp_path):
    if not os.environ.get('JEV_TEMPLATE_WHEELHOUSE'):
        pytest.skip('Explicit offline wheelhouse required')
    old_request, old_install, old_receipt, old = _installed_version(tmp_path / 'old', '0.1.0')
    new_request, new_install, new_receipt, new = _installed_version(tmp_path / 'new', '0.2.0')
    assert old_install['package_plan']['project_version'] == '0.1.0'
    assert new_install['package_plan']['project_version'] == '0.2.0'
    assert old['environment'] != new['environment']
    session = tmp_path / 'session'
    created = delivery.create_session(session, old)
    launch_scope = _scope(created, old, 'launch')
    launched = delivery.launch_session(session, scope=launch_scope,
        approved_scope_sha256=launch_scope['scope_sha256'])
    stop_scope = _scope(launched, old, 'stop')
    stopped = delivery.stop_session(session, scope=stop_scope,
        approved_scope_sha256=stop_scope['scope_sha256'])
    assert stopped['stage'] == 'stopped'
    upgrade_scope = _scope(stopped, old, 'upgrade')
    upgrade_scope['upgrade_plan_sha256'] = new['plan_sha256']
    upgrade_scope['scope_sha256'] = digest({k: v for k, v in upgrade_scope.items()
                                              if k != 'scope_sha256'})
    incompatible = deepcopy(new)
    incompatible['schema_version'] = '2.0'
    incompatible['plan_sha256'] = digest({k: v for k, v in incompatible.items()
                                          if k != 'plan_sha256'})
    incompatible_scope = deepcopy(upgrade_scope)
    incompatible_scope['upgrade_plan_sha256'] = incompatible['plan_sha256']
    incompatible_scope['scope_sha256'] = digest({k: v for k, v in incompatible_scope.items()
                                                   if k != 'scope_sha256'})
    with pytest.raises((InputError, delivery.DeliveryError)):
        delivery.upgrade_session(session, incompatible, scope=incompatible_scope,
            approved_scope_sha256=incompatible_scope['scope_sha256'])
    source_path = Path(old_request['host_root']) / 'host_cli.py'
    original_source = source_path.read_bytes()
    config_path = Path(old_receipt['environment']) / 'config.json'
    original_config = config_path.read_bytes()
    for target, changed in (
        (source_path, original_source + b'\n# changed before cutover\n'),
        (config_path, b'{"jev_runtime":{"mode":"shadow","credential_ref":"env:TYPESAFE_API_KEY"}}\n'),
        (config_path, b'{"jev_runtime":{"mode":"off","credential_ref":"env:OTHER"}}\n'),
    ):
        target.write_bytes(changed)
        with pytest.raises((InputError, installer.InstallationError, delivery.DeliveryError)):
            delivery.upgrade_session(session, new, scope=upgrade_scope,
                approved_scope_sha256=upgrade_scope['scope_sha256'])
        target.write_bytes(original_source if target == source_path else original_config)
    assert delivery.session_status(session)['generation_id'] == old['generation_id']
    upgraded = delivery.upgrade_session(session, new, scope=upgrade_scope,
        approved_scope_sha256=upgrade_scope['scope_sha256'])
    assert upgraded['stage'] == 'upgrade_staged'
    assert upgraded['generation_id'] == new['generation_id']
    assert upgraded['run_id'] == created['run_id']
    assert upgraded['recorded_observations']['launched'] is False
    assert Path(old_receipt['environment']).is_dir()
    assert Path(new_receipt['environment']).is_dir()
    with pytest.raises(delivery.DeliveryError, match='exact_delivery_scope'):
        delivery.launch_session(session, scope=launch_scope,
            approved_scope_sha256=launch_scope['scope_sha256'])
