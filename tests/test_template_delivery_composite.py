"""One stable delivery run through two installed source-bound console decisions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from contextlib import redirect_stdout
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
import zipfile

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash, read_json
from jev_integration_evaluator.cli import main as cli_main
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator import template_delivery as delivery
from jev_integration_evaluator import template_delivery_journey as journey
from jev_integration_evaluator.template_catalog import materialize_template
from jev_integration_evaluator.integrations.composite import (
    apply_composite, plan_composite, rollback_composite,
    status_composite, verify_composite)
from tests.test_composite_console_delivery import _prepared


pytestmark = pytest.mark.skipif(
    not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
         and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)),
    reason='Composite installed session requires Linux x86-64 CPython 3.13')


def _scope(result, plan, action, rollback_digest=None):
    value = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
             'reference': 'independent-composite-fixture-operator',
             'run_id': result['run_id'], 'plan_sha256': plan['plan_sha256'],
             'trusted_session_head': result['session_head_sha256'],
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             'revoked': False, 'grants': {
                 name: name == action for name in ('launch', 'stop', 'disable',
                                                   'upgrade', 'rollback')}}
    if rollback_digest is not None:
        value['rollback_digest'] = rollback_digest
    value['scope_sha256'] = digest(value)
    return value


def _metadata(path):
    with zipfile.ZipFile(path) as archive:
        name = next(row for row in archive.namelist() if row.endswith('.dist-info/METADATA'))
        record = BytesParser().parsebytes(archive.read(name))
        return record['Name'], record['Version']


def _sha(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def _record(session, status, stage, **kwargs):
    result = journey.record_journey(session,
        trusted_journey_head=status['journey_head_sha256'], stage=stage, **kwargs)
    assert result['run_id'] == status['run_id']
    return result


def test_journey_archive_partial_write_retries_only_exact_prefix(tmp_path):
    directory = tmp_path / 'journey'
    directory.mkdir(mode=0o700)
    plans = directory / 'plans'
    plans.mkdir(mode=0o700)
    value = {'plan_sha256': 'a' * 64, 'example': 'reviewed'}
    pending = plans / ('a' * 64 + '.json.pending')
    raw = journey.canonical(value) + b'\n'
    pending.write_bytes(raw[:9])
    pending.chmod(0o600)
    journey._archive(directory, value, 'a' * 64)
    assert (plans / ('a' * 64 + '.json')).read_bytes() == raw
    assert not pending.exists()
    linked_directory = tmp_path / 'linked-journey'
    linked_directory.mkdir(mode=0o700)
    linked_plans = linked_directory / 'plans'
    linked_plans.mkdir(mode=0o700)
    linked_pending = linked_plans / ('a' * 64 + '.json.pending')
    linked_final = linked_plans / ('a' * 64 + '.json')
    linked_pending.write_bytes(raw)
    linked_pending.chmod(0o600)
    os.link(linked_pending, linked_final)
    journey._archive(linked_directory, value, 'a' * 64)
    assert linked_final.read_bytes() == raw
    assert linked_final.stat().st_nlink == 1
    assert not linked_pending.exists()


def test_interrupted_composite_apply_blocks_replay_under_same_journey(tmp_path, monkeypatch):
    root, inventory, selection, specs = _prepared(tmp_path)
    bundle = tmp_path / 'bundle'
    planned = plan_composite(root, inventory, selection, specs, bundle)
    session = tmp_path / 'journey'
    created = journey.create_journey(session, source_root=str(root),
                                     bundle=str(bundle), source_kind='composite')
    baseline = verify_composite(root, bundle, 'baseline', approve_execution=True)
    recorded = _record(session, created, 'baseline_anchored',
                       trusted_receipt_sha256=baseline['receipt_sha256'])
    from jev_integration_evaluator.integrations import composite
    original_patch = composite.apply_patch_plan
    def interrupted_patch(*_args, **_kwargs):
        raise RuntimeError('injected_apply_interruption')
    monkeypatch.setattr(composite, 'apply_patch_plan', interrupted_patch)
    with pytest.raises(RuntimeError, match='injected_apply_interruption'):
        apply_composite(root, bundle, planned['bundle_digest'],
                        baseline_sha256=baseline['receipt_sha256'])
    stuck = journey.journey_status(session,
        trusted_journey_head=recorded['journey_head_sha256'])
    assert stuck['run_id'] == created['run_id']
    assert stuck['next_action'] == 'reconcile_exact_source_transaction'
    monkeypatch.setattr(composite, 'apply_patch_plan', original_patch)
    with pytest.raises(InputError):
        apply_composite(root, bundle, planned['bundle_digest'],
                        baseline_sha256=baseline['receipt_sha256'])
    approved = status_composite(root, bundle)['rollback_digest']
    rollback_composite(root, bundle, approved)
    assert journey.journey_status(session,
        trusted_journey_head=recorded['journey_head_sha256'])['run_id'] == created['run_id']


def test_composite_journey_to_supervised_installed_two_effects(tmp_path, monkeypatch):
    wheelhouse_name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not wheelhouse_name:
        pytest.skip('Explicit offline wheelhouse required')
    root, inventory, selection, specs = _prepared(tmp_path, delivery_effects=True)
    templates = {}
    for identifier, spec in specs.items():
        directory = tmp_path / ('template-' + identifier)
        materialize_template(root, {
            'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
            'template_version': '1.0.0', 'backend': 'python',
            'profile': 'module-tail-call-v1', 'reviewed_inventory': inventory,
            'implementation_spec': spec}, directory)
        templates[identifier] = str(directory)
    bundle = tmp_path / 'bundle'
    planned = plan_composite(root, inventory, selection, specs, bundle)
    session = tmp_path / 'journey'
    created = journey.create_journey(session, source_root=str(root),
                                     bundle=str(bundle), source_kind='composite')
    output = io.StringIO()
    with redirect_stdout(output):
        assert cli_main(['template', 'journey-status', '--session', str(session),
                         '--trusted-journey-head', created['journey_head_sha256']]) == 0
    assert json.loads(output.getvalue())['run_id'] == created['run_id']
    assert created['next_action'] == 'verify_and_anchor_source_baseline'
    baseline = verify_composite(root, bundle, 'baseline', approve_execution=True)
    recorded = _record(session, created, 'baseline_anchored',
                       trusted_receipt_sha256=baseline['receipt_sha256'])
    assert recorded['next_action'] == 'apply_exact_source_bundle'
    apply_composite(root, bundle, planned['bundle_digest'],
                    baseline_sha256=baseline['receipt_sha256'])
    assert journey.journey_status(session,
        trusted_journey_head=recorded['journey_head_sha256'])['next_action'] == 'verify_and_anchor_modified_source'
    modified = verify_composite(root, bundle, 'modified', approve_execution=True,
                                baseline_sha256=baseline['receipt_sha256'])
    recorded = _record(session, recorded, 'source_verified',
                       trusted_receipt_sha256=modified['receipt_sha256'])
    assert recorded['next_action'] == 'prepare_exact_package_plan'
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    wheels = sorted(wheelhouse.glob('*.whl'))
    parent = tmp_path / 'environments'
    parent.mkdir(mode=0o700)
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    request = {
        'schema_version': '1.0', 'host_root': str(root),
        'implementation_bundle': str(bundle),
        'trusted_modified_receipt_sha256': modified['receipt_sha256'],
        'template_directories': templates,
        'reviewed_package_source_sha256': digest(installer._tree(root)),
        'reviewed_configuration_sha256': digest(config),
        'interpreter': sys.executable, 'wheelhouse': str(wheelhouse),
        'package_directory': str(tmp_path / 'package'),
        'environment_parent': str(parent),
        'console_script': read_json(bundle / 'composite-console.json')['script'],
        'build_tools': {name: importlib.metadata.version(name)
                        for name in ('pip', 'setuptools', 'wheel')},
        'wheels': [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels],
        'requirements': [{'name': name, 'version': version,
                          'wheel': path.name, 'sha256': file_hash(path)}
                         for path in wheels for name, version in [_metadata(path)]],
        'configuration': config, 'secret_references': {},
    }
    package_plan = installer.plan_composite_package(request)
    recorded = _record(session, recorded, 'package_planned', plan=package_plan)
    assert recorded['next_action'] == 'build_exact_package_plan'
    package_receipt = installer.build_composite_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    recorded = _record(session, recorded, 'package_built',
                       receipt=package_receipt,
                       trusted_receipt_sha256=package_receipt['receipt_sha256'])
    install_plan = installer.plan_composite_install(package_plan, package_receipt)
    recorded = _record(session, recorded, 'install_planned', plan=install_plan)
    assert recorded['next_action'] == 'install_exact_generation'
    original_run = installer._run
    def interrupt_first_venv(argv, **kwargs):
        if argv[1:3] == ['-m', 'venv']:
            raise installer.InstallationError('injected_pre_venv_interruption')
        return original_run(argv, **kwargs)
    monkeypatch.setattr(installer, '_run', interrupt_first_venv)
    with pytest.raises(installer.InstallationError, match='injected_pre_venv_interruption'):
        installer.install_composite_package(
            install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    interrupted = journey.journey_status(session,
        trusted_journey_head=recorded['journey_head_sha256'])
    assert interrupted['run_id'] == created['run_id']
    assert interrupted['next_action'] == 'recover_exact_install_generation'
    with pytest.raises(installer.InstallationError, match='install_interrupted_recovery_required'):
        installer.install_composite_package(
            install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    status = installer.composite_installation_status(install_plan)
    assert status['generation_sha256'] is not None
    installer.recover_composite_installation(install_plan,
        approved_plan_sha256=install_plan['plan_sha256'],
        approved_generation_sha256=status['generation_sha256'])
    monkeypatch.setattr(installer, '_run', original_run)
    install_receipt = installer.install_composite_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    recorded = _record(session, recorded, 'installed',
                       trusted_receipt_sha256=install_receipt['receipt_sha256'])
    assert recorded['next_action'] == 'promote_verified_installation'
    ready = tmp_path / 'ready-one.bin'
    one = tmp_path / 'effect-one.bin'
    two = tmp_path / 'effect-two.bin'
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [
                       {'role': 'ready', 'path': str(ready), 'before_sha256': None,
                        'expected_sha256': _sha(b'ready\n')},
                       {'role': 'entrypoint_reached', 'path': str(one),
                        'before_sha256': None, 'expected_sha256': _sha(b'first\n')},
                       {'role': 'integration_reachable', 'path': str(two),
                        'before_sha256': None, 'expected_sha256': _sha(b'first\n')},
                       {'role': 'outcome_verified', 'path': str(two),
                        'before_sha256': None, 'expected_sha256': _sha(b'first\n')} ]}
    environment = {'DELIVERY_READY_PATH_ONE': str(ready),
                   'DELIVERY_EFFECT_PATH_ONE': str(one),
                   'DELIVERY_EFFECT_PATH_TWO': str(two),
                   'DELIVERY_EFFECT_HOLD_SECONDS': '0.7'}
    original_append = delivery._append
    def interrupted_created_row(path, rows, event, state):
        if event == 'created':
            raise RuntimeError('injected_before_first_runtime_row')
        return original_append(path, rows, event, state)
    monkeypatch.setattr(delivery, '_append', interrupted_created_row)
    with pytest.raises(RuntimeError, match='injected_before_first_runtime_row'):
        journey.promote_journey(session,
            trusted_journey_head=recorded['journey_head_sha256'],
            observation=observation, launch_environment=environment)
    pending = journey.journey_status(session)
    assert pending['run_id'] == created['run_id']
    assert pending['next_action'] == 'recover_exact_unlaunched_runtime'
    with pytest.raises(delivery.DeliveryError, match='externally_retained_journey_head_required'):
        journey.recover_journey_promotion(session,
            trusted_journey_head=recorded['journey_head_sha256'])
    monkeypatch.setattr(delivery, '_append', original_append)
    original_journey_append = journey._append
    def interrupted_outer_completion(path, rows, event, state):
        if event == 'runtime_session':
            raise RuntimeError('injected_after_child_created_row')
        return original_journey_append(path, rows, event, state)
    monkeypatch.setattr(journey, '_append', interrupted_outer_completion)
    with pytest.raises(RuntimeError, match='injected_after_child_created_row'):
        journey.recover_journey_promotion(session,
            trusted_journey_head=pending['journey_head_sha256'])
    pending_completion = journey.journey_status(session)
    assert pending_completion['run_id'] == created['run_id']
    assert pending_completion['next_action'] == 'complete_exact_promotion'
    monkeypatch.setattr(journey, '_append', original_journey_append)
    promoted = journey.promote_journey(session,
        trusted_journey_head=pending_completion['journey_head_sha256'],
        observation=observation, launch_environment=environment)
    assert promoted['run_id'] == created['run_id']
    assert promoted['runtime'] == 'installed'
    runtime = session / 'runtime'
    delivery_plan = read_json(runtime / 'delivery-plan.json')
    child = delivery.session_status(runtime)
    assert child['run_id'] == created['run_id']
    launch_scope = _scope(child, delivery_plan, 'launch')
    launched = delivery.launch_session(runtime, scope=launch_scope,
        approved_scope_sha256=launch_scope['scope_sha256'])
    observed = launched
    for _ in range(200):
        observed = delivery.observe_session(runtime,
            trusted_session_head=observed['session_head_sha256'])
        if observed['recorded_observations']['outcome_verified']:
            break
        time.sleep(0.01)
    assert observed['current_process_alive'] is True
    assert observed['current_ready'] is True
    assert observed['current_integration_reachable'] is True
    assert observed['recorded_observations']['provider_reachable'] is False
    assert observed['recorded_observations']['mode_authorized'] is True
    assert ready.read_bytes() == b'ready\n'
    assert one.read_bytes() == b'first\n'
    assert two.read_bytes() == b'first\n'
    stop_scope = _scope(observed, delivery_plan, 'disable')
    stopped = delivery.stop_session(runtime, scope=stop_scope,
        approved_scope_sha256=stop_scope['scope_sha256'], disable=True)
    assert stopped['stage'] == 'disabled'
    exact_source = status_composite(root, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])['rollback_digest']
    rollback_scope = _scope(stopped, delivery_plan, 'rollback', exact_source)
    rolled = delivery.rollback_session(runtime, scope=rollback_scope,
        approved_scope_sha256=rollback_scope['scope_sha256'])
    assert rolled['stage'] == 'rolled_back'
    assert status_composite(root, bundle)['status'] == 'rolled_back'
    assert Path(install_receipt['environment']).is_dir()
    assert journey.journey_status(session,
        trusted_journey_head=promoted['journey_head_sha256'])['run_id'] == created['run_id']
