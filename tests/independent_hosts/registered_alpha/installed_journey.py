"""Explicit offline installed journey for the independently authored Alpha host.

Run only with a reviewed CPython 3.13 wheelhouse and an evaluator that includes
the issue #56 public journey/delivery APIs. Every effect uses disposable paths.
This driver does not request provider access or assert measured benefit.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import zipfile

from jev_integration_evaluator.io import digest, file_hash, read_json, write_json
from jev_integration_evaluator.template_catalog import prepare_template_binding, materialize_template
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, implementation_status, plan_implementation)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator import template_installation as installer
from tests.independent_hosts.registered_alpha.qualification import ROOT, source_matched_request


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _wheel_metadata(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
        if len(names) != 1:
            raise ValueError('wheel_metadata_missing_or_ambiguous')
        metadata = BytesParser().parsebytes(archive.read(names[0]))
    return metadata['Name'], metadata['Version']


def _private_directory(path: Path, *, create: bool) -> Path:
    if not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('private_directory_requires_absolute_nonlink_path')
    if create:
        path.mkdir(mode=0o700)
    if (not path.is_dir() or path.stat().st_uid != os.geteuid()
            or path.stat().st_mode & 0o077):
        raise ValueError('private_directory_not_owner_private')
    return path


def _anchor(directory: Path, stage: str, value: str) -> None:
    """Retain a digest outside the source bundle, installer and journey."""
    path = directory / (stage + '.json')
    if path.exists():
        raise ValueError('external_anchor_collision')
    write_json(path, {'stage': stage, 'sha256': value})


def _record(journey, directory: Path, previous: dict, stage: str, **kwargs) -> dict:
    result = journey.record_journey(directory,
        trusted_journey_head=previous['journey_head_sha256'], stage=stage, **kwargs)
    if result['run_id'] != previous['run_id']:
        raise RuntimeError('journey_run_identity_changed')
    return result


def _scope(result: dict, plan: dict, action: str, *, rollback_digest: str | None = None) -> dict:
    value = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
             'reference': 'registered-alpha-offline-operator-v1',
             'run_id': result['run_id'], 'plan_sha256': plan['plan_sha256'],
             'trusted_session_head': result['session_head_sha256'],
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             'revoked': False,
             'grants': {name: name == action for name in
                        ('launch', 'stop', 'disable', 'upgrade', 'rollback')}}
    if rollback_digest is not None:
        value['rollback_digest'] = rollback_digest
    value['scope_sha256'] = digest(value)
    return value


def _create_release(path: Path) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, b'release\n')
        os.fsync(fd)
    finally:
        os.close(fd)


def run_offline(workspace: Path, wheelhouse: Path, anchors: Path) -> dict:
    """Execute one separately authorized offline source/install/console run."""
    if not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
            and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)):
        raise RuntimeError('registered_alpha_requires_linux_x86_64_cpython_3_13')
    # Import only after the profile check, so this fixture remains parseable on
    # earlier evaluator branches. The #56 package supplies these public APIs.
    from jev_integration_evaluator import template_delivery as delivery
    from jev_integration_evaluator import template_delivery_journey as journey

    wheelhouse = _private_directory(wheelhouse.resolve(strict=True), create=False)
    workspace = _private_directory(workspace, create=True)
    anchors = _private_directory(anchors, create=True)
    if anchors == workspace or anchors.is_relative_to(workspace):
        raise ValueError('external_anchors_must_be_outside_run_workspace')
    host = workspace / 'host'
    shutil.copytree(ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    request, binding = source_matched_request(host)
    bound = prepare_template_binding(host, request, binding)['request']
    template = workspace / 'template'
    materialize_template(host, bound, template)
    spec = bound['implementation_spec']
    bundle = workspace / 'implementation'
    source_plan = plan_implementation(host, bound['reviewed_inventory'],
                                      spec['candidate_id'], spec, bundle)
    journey_dir = workspace / 'journey'
    progress = journey.create_journey(journey_dir, source_root=str(host), bundle=str(bundle))
    _anchor(anchors, 'journey_created', progress['journey_head_sha256'])
    probe = _private_directory(workspace / 'source-probe-effects', create=True)
    prior = os.environ.get('REGISTERED_ALPHA_PROBE_EFFECTS_DIR')
    os.environ['REGISTERED_ALPHA_PROBE_EFFECTS_DIR'] = str(probe)
    try:
        baseline = verify_implementation(host, bundle, 'baseline', approve_execution=True)
        if baseline['status'] != 'baseline_passed':
            raise RuntimeError('alpha_baseline_verification_failed')
        _anchor(anchors, 'source_baseline', baseline['receipt_sha256'])
        progress = _record(journey, journey_dir, progress, 'baseline_anchored',
                           trusted_receipt_sha256=baseline['receipt_sha256'])
        _anchor(anchors, 'journey_baseline', progress['journey_head_sha256'])
        apply_implementation(host, bundle, source_plan['bundle_digest'],
                             baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(host, bundle, 'modified', approve_execution=True,
                                         baseline_sha256=baseline['receipt_sha256'])
        if modified['status'] != 'verified':
            raise RuntimeError('alpha_modified_verification_failed')
        _anchor(anchors, 'source_modified', modified['receipt_sha256'])
        progress = _record(journey, journey_dir, progress, 'source_verified',
                           trusted_receipt_sha256=modified['receipt_sha256'])
        _anchor(anchors, 'journey_source_verified', progress['journey_head_sha256'])
    finally:
        if prior is None:
            os.environ.pop('REGISTERED_ALPHA_PROBE_EFFECTS_DIR', None)
        else:
            os.environ['REGISTERED_ALPHA_PROBE_EFFECTS_DIR'] = prior

    wheels = sorted(wheelhouse.glob('*.whl'))
    if not wheels:
        raise ValueError('reviewed_offline_wheelhouse_empty')
    wheel_rows = [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels]
    requirements = [{'name': name, 'version': version, 'wheel': path.name,
                     'sha256': file_hash(path)}
                    for path in wheels for name, version in [_wheel_metadata(path)]]
    environments = _private_directory(workspace / 'environments', create=True)
    configuration = {'jev_runtime': {'mode': 'off', 'credential_ref': 'env:TYPESAFE_API_KEY'}}
    package_request = {
        'schema_version': '1.0', 'host_root': str(host),
        'implementation_bundle': str(bundle),
        'trusted_modified_receipt_sha256': modified['receipt_sha256'],
        'template_directory': str(template),
        'reviewed_package_source_sha256': digest(installer._tree(host)),
        'reviewed_configuration_sha256': digest(configuration),
        'interpreter': sys.executable, 'wheelhouse': str(wheelhouse),
        'package_directory': str(workspace / 'package'),
        'environment_parent': str(environments), 'console_script': 'registered-alpha',
        'build_tools': {name: importlib.metadata.version(name)
                        for name in ('pip', 'setuptools', 'wheel')},
        'wheels': wheel_rows, 'requirements': requirements,
        'configuration': configuration,
        'secret_references': {'credential': 'env:TYPESAFE_API_KEY'},
    }
    package_plan = installer.plan_package(package_request)
    progress = _record(journey, journey_dir, progress, 'package_planned', plan=package_plan)
    _anchor(anchors, 'journey_package_planned', progress['journey_head_sha256'])
    package_receipt = installer.build_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    _anchor(anchors, 'package_built', package_receipt['receipt_sha256'])
    progress = _record(journey, journey_dir, progress, 'package_built',
                       receipt=package_receipt,
                       trusted_receipt_sha256=package_receipt['receipt_sha256'])
    _anchor(anchors, 'journey_package_built', progress['journey_head_sha256'])
    install_plan = installer.plan_install(package_plan, package_receipt)
    progress = _record(journey, journey_dir, progress, 'install_planned', plan=install_plan)
    _anchor(anchors, 'journey_install_planned', progress['journey_head_sha256'])
    installed = installer.install_package(install_plan,
        approved_plan_sha256=install_plan['plan_sha256'])
    _anchor(anchors, 'package_installed', installed['receipt_sha256'])
    progress = _record(journey, journey_dir, progress, 'installed',
                       trusted_receipt_sha256=installed['receipt_sha256'])
    _anchor(anchors, 'journey_installed', progress['journey_head_sha256'])

    evidence = _private_directory(workspace / 'external-effects', create=True)
    ready, release = evidence / 'ready.bin', evidence / 'release.bin'
    effects, audit = evidence / 'effects.jsonl', evidence / 'audit.jsonl'
    expected_effect = (json.dumps({'task_id': 'alpha-installed-1', 'action': 'inspect',
                                   'item': 'fixture-one'}, sort_keys=True,
                                  separators=(',', ':')) + '\n').encode()
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [
                       {'role': role, 'path': str(ready), 'before_sha256': None,
                        'expected_sha256': _sha(b'in-flight\n')}
                       for role in ('ready', 'entrypoint_reached')
                   ] + [
                       {'role': role, 'path': str(effects), 'before_sha256': None,
                        'expected_sha256': _sha(expected_effect)}
                       for role in ('integration_reachable', 'outcome_verified')
                   ]}
    launch_environment = {
        'REGISTERED_ALPHA_EFFECTS': str(effects), 'REGISTERED_ALPHA_AUDIT': str(audit),
        'REGISTERED_ALPHA_TASK_ID': 'alpha-installed-1', 'REGISTERED_ALPHA_ITEM': 'fixture-one',
        'REGISTERED_ALPHA_INTENT': 'summarize', 'REGISTERED_ALPHA_PERMIT': '1',
        'REGISTERED_ALPHA_APPROVED': '1', 'REGISTERED_ALPHA_HOLD': '1',
        'REGISTERED_ALPHA_READY': str(ready), 'REGISTERED_ALPHA_RELEASE': str(release),
    }
    progress = journey.promote_journey(journey_dir,
        trusted_journey_head=progress['journey_head_sha256'],
        observation=observation, launch_environment=launch_environment)
    _anchor(anchors, 'journey_promoted', progress['journey_head_sha256'])
    runtime = journey_dir / 'runtime'
    delivery_plan = read_json(runtime / 'delivery-plan.json')
    child = delivery.session_status(runtime)
    if child['run_id'] != progress['run_id']:
        raise RuntimeError('registered_alpha_run_identity_changed')
    launch_scope = _scope(child, delivery_plan, 'launch')
    launched = delivery.launch_session(runtime, scope=launch_scope,
        approved_scope_sha256=launch_scope['scope_sha256'])
    _anchor(anchors, 'delivery_launched', launched['session_head_sha256'])
    observed = launched
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        observed = delivery.observe_session(runtime,
            trusted_session_head=observed['session_head_sha256'])
        if observed['recorded_observations']['ready']:
            break
        time.sleep(0.02)
    if not observed['recorded_observations']['ready'] or not observed['current_process_alive']:
        raise RuntimeError('registered_alpha_live_ready_not_observed')
    _anchor(anchors, 'delivery_ready', observed['session_head_sha256'])
    _create_release(release)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        observed = delivery.observe_session(runtime,
            trusted_session_head=observed['session_head_sha256'])
        if observed['recorded_observations']['outcome_verified']:
            break
        time.sleep(0.02)
    if not observed['recorded_observations']['outcome_verified']:
        raise RuntimeError('registered_alpha_effect_not_observed')
    if effects.read_bytes() != expected_effect:
        raise RuntimeError('registered_alpha_raw_effect_changed')
    if observed['recorded_observations']['provider_reachable'] is not False:
        raise RuntimeError('unexpected_provider_qualification_claim')
    _anchor(anchors, 'delivery_effect_observed', observed['session_head_sha256'])
    disable_scope = _scope(observed, delivery_plan, 'disable')
    disabled = delivery.stop_session(runtime, scope=disable_scope,
        approved_scope_sha256=disable_scope['scope_sha256'], disable=True)
    if disabled['stage'] != 'disabled':
        raise RuntimeError('registered_alpha_disable_incomplete')
    _anchor(anchors, 'delivery_disabled', disabled['session_head_sha256'])
    source_status = implementation_status(host, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])
    rollback_scope = _scope(disabled, delivery_plan, 'rollback',
                            rollback_digest=source_status['rollback_digest'])
    rolled = delivery.rollback_session(runtime, scope=rollback_scope,
        approved_scope_sha256=rollback_scope['scope_sha256'])
    if rolled['stage'] != 'rolled_back':
        raise RuntimeError('registered_alpha_rollback_incomplete')
    _anchor(anchors, 'delivery_rolled_back', rolled['session_head_sha256'])
    return {'schema_version': '1.0', 'classification': 'offline_installed_host',
            'run_id': progress['run_id'], 'source_candidate_id': spec['candidate_id'],
            'source_sha256': spec['source']['source_sha256'],
            'modified_receipt_sha256': modified['receipt_sha256'],
            'install_receipt_sha256': installed['receipt_sha256'],
            'raw_effect_sha256': file_hash(effects),
            'observed_action': 'inspect', 'provider_qualification': 'not_run',
            'measured_benefit': False, 'final_stage': rolled['stage']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--anchors', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_offline(args.workspace, args.wheelhouse, args.anchors),
                     sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
