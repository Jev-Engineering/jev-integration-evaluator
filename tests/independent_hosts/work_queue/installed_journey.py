"""Offline installed work-queue journey through public template delivery APIs."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import time
import zipfile

from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import digest, file_hash, read_json, write_json
from jev_integration_evaluator.template_catalog import prepare_template_binding, materialize_template
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, implementation_status, plan_implementation)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator import template_installation as installer


_qualification_file = Path(__file__).resolve().with_name('qualification.py')
_qualification_spec = importlib.util.spec_from_file_location('work_queue_qualification',
                                                            _qualification_file)
if _qualification_spec is None or _qualification_spec.loader is None:
    raise RuntimeError('work_queue_qualification_loader_missing')
_qualification = importlib.util.module_from_spec(_qualification_spec)
_qualification_spec.loader.exec_module(_qualification)
ROOT = _qualification.ROOT


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _private(path: Path, *, create: bool) -> Path:
    if not path.is_absolute() or any(row.is_symlink() for row in (path, *path.parents)):
        raise ValueError('work_queue_private_path_required')
    if create:
        path.mkdir(mode=0o700)
    info = path.stat()
    if not path.is_dir() or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('work_queue_private_directory_required')
    return path


def _anchor(directory: Path, stage: str, value: str) -> None:
    path = directory / (stage + '.json')
    if path.exists():
        raise ValueError('work_queue_anchor_collision')
    write_json(path, {'stage': stage, 'sha256': value})


def _record(journey, directory: Path, previous: dict, stage: str, **kwargs) -> dict:
    value = journey.record_journey(directory, trusted_journey_head=previous['journey_head_sha256'],
                                   stage=stage, **kwargs)
    if value['run_id'] != previous['run_id']:
        raise RuntimeError('work_queue_journey_run_changed')
    return value


def _wheel_metadata(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist()
                 if name.count('/') == 1 and name.endswith('.dist-info/METADATA')]
        if len(names) != 1:
            raise ValueError('work_queue_wheel_metadata_ambiguous')
        metadata = BytesParser().parsebytes(archive.read(names[0]))
    return metadata['Name'], metadata['Version']


def _scope(status: dict, plan: dict, action: str, *, rollback_digest: str | None = None) -> dict:
    value = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
             'reference': 'work-queue-offline-operator-v1', 'run_id': status['run_id'],
             'plan_sha256': plan['plan_sha256'],
             'trusted_session_head': status['session_head_sha256'],
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             'revoked': False,
             'grants': {name: name == action for name in
                        ('launch', 'stop', 'disable', 'upgrade', 'rollback')}}
    if rollback_digest is not None:
        value['rollback_digest'] = rollback_digest
    value['scope_sha256'] = digest(value)
    return value


def _installed_origins(receipt: dict, plan: dict) -> dict:
    """Inspect validated installed paths and metadata without starting a probe."""
    root = Path(receipt['environment'])
    python = Path(receipt['installed']['python'])
    expected = Path(plan['profile']['executable_path']).resolve(strict=True)
    if (not python.is_relative_to(root / 'venv') or not python.is_symlink()
            or python.resolve(strict=True) != expected):
        raise RuntimeError('work_queue_interpreter_origin_drift')
    site = root / 'venv/lib/python3.13/site-packages'
    if not site.is_dir() or site.is_symlink():
        raise RuntimeError('work_queue_site_origin_drift')
    paths = {'host': site / 'work_queue/__init__.py',
             'evaluator': site / 'jev_integration_evaluator/__init__.py'}
    for name, path in paths.items():
        if (path.is_symlink() or not path.is_file() or
                not path.resolve(strict=True).is_relative_to(site.resolve(strict=True))):
            raise RuntimeError('work_queue_' + name + '_origin_drift')
    for name in ('jev-independent-work-queue', 'jev-integration-evaluator'):
        found = [row for row in importlib.metadata.distributions(path=[str(site)])
                 if row.metadata['Name'].lower().replace('_', '-') == name]
        if len(found) != 1 or found[0].version != receipt['installed']['distributions'][name]:
            raise RuntimeError('work_queue_distribution_origin_drift')
    entry = Path(receipt['installed']['entrypoint_origin'])
    if (entry.is_symlink() or not entry.is_file() or
            entry.resolve(strict=True) != paths['host'].with_name('cli.py').resolve(strict=True)):
        raise RuntimeError('work_queue_entrypoint_origin_drift')
    return {name: str(path.resolve(strict=True)) for name, path in paths.items()}


def _release(path: Path) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, b'release\n')
        os.fsync(fd)
    finally:
        os.close(fd)


def run_offline(workspace: Path, wheelhouse: Path, anchors: Path) -> dict:
    if not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
            and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)):
        raise RuntimeError('work_queue_requires_linux_x86_64_cpython_3_13')
    from jev_integration_evaluator import template_delivery as delivery
    from jev_integration_evaluator import template_delivery_journey as journey

    wheelhouse = _private(wheelhouse.resolve(strict=True), create=False)
    workspace = _private(workspace, create=True)
    anchors = _private(anchors, create=True)
    if anchors == workspace or anchors.is_relative_to(workspace):
        raise ValueError('work_queue_external_anchors_required')
    host = workspace / 'host'
    shutil.copytree(ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    request, binding = _qualification.source_matched_request(host)
    bound = prepare_template_binding(host, request, binding)['request']
    template = workspace / 'template'
    materialize_template(host, bound, template)
    spec = bound['implementation_spec']
    bundle = workspace / 'implementation'
    source_plan = plan_implementation(host, bound['reviewed_inventory'],
                                      spec['candidate_id'], spec, bundle)
    original_owned = {row['file']: row['old_sha256'] for row in
                      read_json(bundle / 'implementation-plan.json')['owned_files']
                      if row['old_sha256'] is not None}
    journey_dir = workspace / 'journey'
    progress = journey.create_journey(journey_dir, source_root=str(host), bundle=str(bundle))
    _anchor(anchors, 'journey_created', progress['journey_head_sha256'])
    probe = _private(workspace / 'probe-effects', create=True)
    previous_probe = os.environ.get('WORK_QUEUE_PROBE_EFFECTS_DIR')
    os.environ['WORK_QUEUE_PROBE_EFFECTS_DIR'] = str(probe)
    try:
        baseline = verify_implementation(host, bundle, 'baseline', approve_execution=True)
        if baseline['status'] != 'baseline_passed':
            raise RuntimeError('work_queue_baseline_failed')
        _anchor(anchors, 'source_baseline', baseline['receipt_sha256'])
        progress = _record(journey, journey_dir, progress, 'baseline_anchored',
                           trusted_receipt_sha256=baseline['receipt_sha256'])
        apply_implementation(host, bundle, source_plan['bundle_digest'],
                             baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(host, bundle, 'modified', approve_execution=True,
                                         baseline_sha256=baseline['receipt_sha256'])
        if modified['status'] != 'verified':
            raise RuntimeError('work_queue_modified_verification_failed')
        _anchor(anchors, 'source_modified', modified['receipt_sha256'])
        progress = _record(journey, journey_dir, progress, 'source_verified',
                           trusted_receipt_sha256=modified['receipt_sha256'])
    finally:
        if previous_probe is None:
            os.environ.pop('WORK_QUEUE_PROBE_EFFECTS_DIR', None)
        else:
            os.environ['WORK_QUEUE_PROBE_EFFECTS_DIR'] = previous_probe

    wheels = sorted(wheelhouse.glob('*.whl'))
    if not wheels:
        raise ValueError('work_queue_wheelhouse_empty')
    requirements = [{'name': name, 'version': version, 'wheel': path.name,
                     'sha256': file_hash(path)}
                    for path in wheels for name, version in [_wheel_metadata(path)]]
    wheel_rows = [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels]
    environments = _private(workspace / 'environments', create=True)
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
        'environment_parent': str(environments), 'console_script': 'work-queue',
        'build_tools': {name: importlib.metadata.version(name)
                        for name in ('pip', 'setuptools', 'wheel')},
        'wheels': wheel_rows, 'requirements': requirements,
        'configuration': configuration,
        'secret_references': {'credential': 'env:TYPESAFE_API_KEY'},
    }
    package_plan = installer.plan_package(package_request)
    progress = _record(journey, journey_dir, progress, 'package_planned', plan=package_plan)
    built = installer.build_package(package_plan,
                                    approved_plan_sha256=package_plan['plan_sha256'])
    _anchor(anchors, 'package_built', built['receipt_sha256'])
    progress = _record(journey, journey_dir, progress, 'package_built',
                       receipt=built, trusted_receipt_sha256=built['receipt_sha256'])
    install_plan = installer.plan_install(package_plan, built)
    progress = _record(journey, journey_dir, progress, 'install_planned', plan=install_plan)
    installed = installer.install_package(install_plan,
                                           approved_plan_sha256=install_plan['plan_sha256'])
    _anchor(anchors, 'package_installed', installed['receipt_sha256'])
    progress = _record(journey, journey_dir, progress, 'installed',
                       trusted_receipt_sha256=installed['receipt_sha256'])
    origins = _installed_origins(installed, install_plan)

    evidence = _private(workspace / 'external-effects', create=True)
    ready, release = evidence / 'ready.bin', evidence / 'release.bin'
    effects, audit = evidence / 'effects.jsonl', evidence / 'audit.jsonl'
    expected_effect = (json.dumps({'job_id': 'queue-installed-1', 'operation': 'enqueue',
                                   'item': 'batch-b'}, sort_keys=True,
                                  separators=(',', ':')) + '\n').encode()
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [
                       {'role': role, 'path': str(ready), 'before_sha256': None,
                        'expected_sha256': _sha(b'queue-running\n')}
                       for role in ('ready', 'entrypoint_reached')
                   ] + [
                       {'role': role, 'path': str(effects), 'before_sha256': None,
                        'expected_sha256': _sha(expected_effect)}
                       for role in ('integration_reachable', 'outcome_verified')
                   ]}
    launch_environment = {
        'WORK_QUEUE_EFFECTS': str(effects), 'WORK_QUEUE_AUDIT': str(audit),
        'WORK_QUEUE_JOB_ID': 'queue-installed-1', 'WORK_QUEUE_ITEM': 'batch-b',
        'WORK_QUEUE_INTENT': 'complete', 'WORK_QUEUE_ALLOWED': '1',
        'WORK_QUEUE_COMPLETE_ALLOWED': '1', 'WORK_QUEUE_HOLD': '1',
        'WORK_QUEUE_READY': str(ready), 'WORK_QUEUE_RELEASE': str(release),
    }
    progress = journey.promote_journey(journey_dir,
        trusted_journey_head=progress['journey_head_sha256'],
        observation=observation, launch_environment=launch_environment)
    _anchor(anchors, 'journey_promoted', progress['journey_head_sha256'])
    runtime = journey_dir / 'runtime'
    delivery_plan = read_json(runtime / 'delivery-plan.json')
    child = delivery.session_status(runtime)
    if child['run_id'] != progress['run_id']:
        raise RuntimeError('work_queue_run_identity_changed')
    launch_scope = _scope(child, delivery_plan, 'launch')
    original_append = delivery._append

    def interrupt_before_release(directory, rows, event, state):
        if event == 'launched':
            raise RuntimeError('work_queue_injected_before_release')
        return original_append(directory, rows, event, state)

    delivery._append = interrupt_before_release
    try:
        try:
            delivery.launch_session(runtime, scope=launch_scope,
                                    approved_scope_sha256=launch_scope['scope_sha256'])
        except RuntimeError as error:
            if str(error) != 'work_queue_injected_before_release':
                raise
        else:
            raise RuntimeError('work_queue_start_interruption_missing')
    finally:
        delivery._append = original_append
    pending = delivery.session_status(runtime)
    if pending['pending'] != 'launch' or effects.exists() or ready.exists():
        raise RuntimeError('work_queue_unreleased_start_changed_effect')
    _anchor(anchors, 'delivery_start_pending', pending['session_head_sha256'])
    child = delivery.resume_session(runtime,
        trusted_session_head=pending['session_head_sha256'])
    if child['stage'] != 'installed' or child['run_id'] != progress['run_id']:
        raise RuntimeError('work_queue_start_recovery_changed_run')
    _anchor(anchors, 'delivery_start_recovered', child['session_head_sha256'])
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
        time.sleep(.02)
    if not observed['recorded_observations']['ready'] or not observed['current_process_alive']:
        raise RuntimeError('work_queue_live_ready_missing')
    _anchor(anchors, 'delivery_ready', observed['session_head_sha256'])
    _release(release)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        observed = delivery.observe_session(runtime,
            trusted_session_head=observed['session_head_sha256'])
        if observed['recorded_observations']['outcome_verified']:
            break
        time.sleep(.02)
    if (not observed['recorded_observations']['outcome_verified'] or
            effects.read_bytes() != expected_effect or
            observed['recorded_observations']['provider_reachable'] is not False):
        raise RuntimeError('work_queue_raw_offline_effect_missing')
    _anchor(anchors, 'delivery_effect_observed', observed['session_head_sha256'])
    repeat_environment = {key: value for key, value in launch_environment.items()
                          if key not in ('WORK_QUEUE_HOLD', 'WORK_QUEUE_READY', 'WORK_QUEUE_RELEASE')}
    repeat_environment.update({'PATH': str(Path(installed['environment']) / 'venv/bin'),
                               'PYTHONNOUSERSITE': '1', 'JEV_RUNTIME_MODE': 'off'})
    duplicate = subprocess.run([installed['installed']['console_script']],
        cwd=installed['environment'], env=repeat_environment,
        capture_output=True, timeout=15)
    if (duplicate.returncode == 0 or b'duplicate_queue_job' not in duplicate.stderr
            or effects.read_bytes() != expected_effect):
        raise RuntimeError('work_queue_duplicate_effect_not_refused')
    disable_scope = _scope(observed, delivery_plan, 'disable')
    disabled = delivery.stop_session(runtime, scope=disable_scope,
        approved_scope_sha256=disable_scope['scope_sha256'], disable=True)
    if disabled['stage'] != 'disabled':
        raise RuntimeError('work_queue_disable_incomplete')
    _anchor(anchors, 'delivery_disabled', disabled['session_head_sha256'])
    source_status = implementation_status(host, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])
    rollback_scope = _scope(disabled, delivery_plan, 'rollback',
                            rollback_digest=source_status['rollback_digest'])
    rolled = delivery.rollback_session(runtime, scope=rollback_scope,
        approved_scope_sha256=rollback_scope['scope_sha256'])
    if rolled['stage'] != 'rolled_back':
        raise RuntimeError('work_queue_owned_rollback_incomplete')
    for relative, expected in original_owned.items():
        if file_hash(host / relative) != expected:
            raise RuntimeError('work_queue_owned_source_not_restored')
    _anchor(anchors, 'delivery_rolled_back', rolled['session_head_sha256'])
    report = {'schema_version': '1.0', 'kind': 'work-queue-offline-report-v1',
              'classification': 'second_independent_installed_host',
              'run_id': progress['run_id'], 'source_candidate_id': spec['candidate_id'],
              'source_sha256': spec['source']['source_sha256'],
              'modified_receipt_sha256': modified['receipt_sha256'],
              'install_receipt_sha256': installed['receipt_sha256'],
              'raw_effect_sha256': file_hash(effects), 'installed_origins': origins,
              'observed_operation': 'enqueue', 'effect_count': 1,
              'start_recovered_same_run': True, 'duplicate_refused': True,
              'provider_qualification': 'not_run', 'measured_benefit': False,
              'final_stage': rolled['stage']}
    validate_contract(report, 'work-queue-offline-report-v1')
    return report


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
