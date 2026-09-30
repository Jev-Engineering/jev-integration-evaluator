"""Source-reviewed offline installed two-placement journey, never provider authority."""
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
from jev_integration_evaluator.integrations.composite import (
    apply_composite, plan_composite, status_composite, verify_composite)
from jev_integration_evaluator.template_catalog import materialize_template
from jev_integration_evaluator import template_installation as installer


_source = Path(__file__).resolve().with_name('qualification.py')
_spec = importlib.util.spec_from_file_location('registered_dual_qualification', _source)
if _spec is None or _spec.loader is None:
    raise RuntimeError('dual_qualification_loader_missing')
_qualification = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_qualification)
ROOT = _qualification.ROOT
FROZEN_REVIEW_SHA256 = '91eeee10b1f181142d2a983cf958a68092d5f75d6f8da5746fa45403966ee1d9'
FROZEN_ORACLE_SHA256 = '23570482720c6a32ac0480b678458d2ec96b6419f879b5304cca91696a52c77e'


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _review(root: Path) -> dict:
    path = root / 'review-v1.json'
    if path.is_symlink() or file_hash(path) != FROZEN_REVIEW_SHA256:
        raise RuntimeError('dual_frozen_review_changed')
    review = read_json(path)
    if review['status'] != 'source_reviewed_for_offline_composite':
        raise RuntimeError('dual_frozen_review_status_changed')
    expected = set(review['files'])
    actual = {path.relative_to(root).as_posix() for path in (root / 'src').rglob('*')
              if (path.is_file() or path.is_symlink()) and '__pycache__' not in path.parts
              and path.suffix != '.pyc'}
    if actual != {name for name in expected if name.startswith('src/')}:
        raise RuntimeError('dual_frozen_source_tree_changed')
    if {path.name for path in root.iterdir() if path.name != '__pycache__'} != {
            'pyproject.toml', 'src', 'review-v1.json', 'oracle-v1.json',
            'README.md', 'qualification.py', 'installed_journey.py'}:
        raise RuntimeError('dual_frozen_root_tree_changed')
    for name, expected_sha in review['files'].items():
        current = root
        for part in Path(name).parts:
            current = current / part
            if current.is_symlink():
                raise RuntimeError('dual_frozen_source_changed:' + name)
        if not current.is_file() or file_hash(current) != expected_sha:
            raise RuntimeError('dual_frozen_source_changed:' + name)
    return review


def _private(path: Path, *, create: bool) -> Path:
    if not path.is_absolute() or any(row.is_symlink() for row in (path, *path.parents)):
        raise ValueError('dual_private_path_required')
    if create:
        path.mkdir(mode=0o700)
    info = path.stat()
    if not path.is_dir() or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('dual_private_directory_required')
    return path


def _wheel_metadata(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist()
                 if name.count('/') == 1 and name.endswith('.dist-info/METADATA')]
        if len(names) != 1:
            raise ValueError('dual_wheel_metadata_ambiguous')
        record = BytesParser().parsebytes(archive.read(names[0]))
    return record['Name'], record['Version']


def _record(journey, directory: Path, previous: dict, stage: str, **kwargs) -> dict:
    result = journey.record_journey(directory,
        trusted_journey_head=previous['journey_head_sha256'], stage=stage, **kwargs)
    if result['run_id'] != previous['run_id']:
        raise RuntimeError('dual_journey_run_changed')
    return result


def _scope(status: dict, plan: dict, action: str, rollback_digest: str | None = None) -> dict:
    value = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
             'reference': 'registered-dual-offline-operator-v1',
             'run_id': status['run_id'], 'plan_sha256': plan['plan_sha256'],
             'trusted_session_head': status['session_head_sha256'],
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             'revoked': False, 'grants': {name: name == action for name in
                                         ('launch', 'stop', 'disable', 'upgrade', 'rollback')}}
    if rollback_digest is not None:
        value['rollback_digest'] = rollback_digest
    value['scope_sha256'] = digest(value)
    return value


def _installed_origins(receipt: dict, plan: dict) -> dict:
    root = Path(receipt['environment'])
    python = Path(receipt['installed']['python'])
    expected = Path(plan['profile']['executable_path']).resolve(strict=True)
    if (not python.is_relative_to(root / 'venv') or not python.is_symlink()
            or python.resolve(strict=True) != expected):
        raise RuntimeError('dual_interpreter_origin_drift')
    site = root / 'venv/lib/python3.13/site-packages'
    if not site.is_dir() or site.is_symlink():
        raise RuntimeError('dual_site_origin_drift')
    paths = {'host': site / 'registered_dual/__init__.py',
             'evaluator': site / 'jev_integration_evaluator/__init__.py'}
    for name, path in paths.items():
        if (path.is_symlink() or not path.is_file() or
                not path.resolve(strict=True).is_relative_to(site.resolve(strict=True))):
            raise RuntimeError('dual_' + name + '_origin_drift')
    for name in ('jev-independent-registered-dual', 'jev-integration-evaluator'):
        found = [row for row in importlib.metadata.distributions(path=[str(site)])
                 if row.metadata['Name'].lower().replace('_', '-') == name]
        if len(found) != 1 or found[0].version != receipt['installed']['distributions'][name]:
            raise RuntimeError('dual_distribution_origin_drift')
    entry = Path(receipt['installed']['entrypoint_origin'])
    console = site / 'registered_dual/console.py'
    if (entry.is_symlink() or not entry.is_file() or
            entry.resolve(strict=True) != console.resolve(strict=True)):
        raise RuntimeError('dual_entrypoint_origin_drift')
    return {name: str(path.resolve(strict=True)) for name, path in paths.items()}


def _external_anchor(directory: Path, stage: str, sha256: str) -> None:
    path = directory / (stage + '.json')
    if path.exists():
        raise RuntimeError('dual_anchor_collision')
    write_json(path, {'stage': stage, 'sha256': sha256})


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
        raise RuntimeError('dual_requires_linux_x86_64_cpython_3_13')
    from jev_integration_evaluator import template_delivery as delivery
    from jev_integration_evaluator import template_delivery_journey as journey

    wheelhouse = _private(wheelhouse.resolve(strict=True), create=False)
    workspace = _private(workspace, create=True)
    anchors = _private(anchors, create=True)
    if anchors == workspace or anchors.is_relative_to(workspace):
        raise ValueError('dual_external_anchors_required')
    review = _review(ROOT)
    host = workspace / 'host'
    shutil.copytree(ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    _review(host)
    if file_hash(host / 'oracle-v1.json') != FROZEN_ORACLE_SHA256:
        raise RuntimeError('dual_frozen_oracle_changed')
    inventory, selection, specs = _qualification.source_matched_composite(host)
    if set(specs) != set(review['candidates']) or any(
            {**{key: spec['source'][key] for key in
                 ('file', 'symbol', 'source_sha256', 'file_sha256')},
             'pattern': spec['binding_review']['pattern']}
            != review['candidates'][identifier] for identifier, spec in specs.items()):
        raise RuntimeError('dual_frozen_candidate_changed')
    oracle = read_json(host / 'oracle-v1.json')
    templates = {}
    for identifier, spec in specs.items():
        output = workspace / ('template-' + identifier)
        materialize_template(host, {
            'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
            'template_version': '1.0.0', 'backend': 'python',
            'profile': 'module-tail-call-v1', 'reviewed_inventory': inventory,
            'implementation_spec': spec}, output)
        templates[identifier] = str(output)
    bundle = workspace / 'bundle'
    planned = plan_composite(host, inventory, selection, specs, bundle)
    journey_dir = workspace / 'journey'
    progress = journey.create_journey(journey_dir, source_root=str(host),
                                      bundle=str(bundle), source_kind='composite')
    _external_anchor(anchors, 'journey_created', progress['journey_head_sha256'])
    probe = _private(workspace / 'probe', create=True)
    names = ('REGISTERED_ALPHA_PROBE_EFFECTS_DIR', 'WORK_QUEUE_PROBE_EFFECTS_DIR',
             'DUAL_SHADOW')
    previous = {name: os.environ.get(name) for name in names}
    os.environ.update({names[0]: str(probe), names[1]: str(probe), names[2]: '1'})
    try:
        baseline = verify_composite(host, bundle, 'baseline', approve_execution=True)
        if baseline['status'] != 'baseline_passed':
            raise RuntimeError('dual_baseline_failed')
        _external_anchor(anchors, 'source_baseline', baseline['receipt_sha256'])
        progress = _record(journey, journey_dir, progress, 'baseline_anchored',
                           trusted_receipt_sha256=baseline['receipt_sha256'])
        apply_composite(host, bundle, planned['bundle_digest'],
                        baseline_sha256=baseline['receipt_sha256'])
        modified = verify_composite(host, bundle, 'modified', approve_execution=True,
                                    baseline_sha256=baseline['receipt_sha256'])
        if modified['status'] != 'verified':
            raise RuntimeError('dual_modified_verification_failed')
        combined = read_json(bundle / 'verification-receipt.json')['combined_check']
        if not combined['shared_budget_valid']:
            raise RuntimeError('dual_shared_budget_verification_failed')
        _external_anchor(anchors, 'source_modified', modified['receipt_sha256'])
        progress = _record(journey, journey_dir, progress, 'source_verified',
                           trusted_receipt_sha256=modified['receipt_sha256'])
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    wheels = sorted(wheelhouse.glob('*.whl'))
    if not wheels:
        raise RuntimeError('dual_wheelhouse_empty')
    requirements = [{'name': name, 'version': version, 'wheel': path.name,
                     'sha256': file_hash(path)} for path in wheels
                    for name, version in [_wheel_metadata(path)]]
    wheel_rows = [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels]
    environments = _private(workspace / 'environments', create=True)
    configuration = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    package_request = {
        'schema_version': '1.0', 'host_root': str(host), 'implementation_bundle': str(bundle),
        'trusted_modified_receipt_sha256': modified['receipt_sha256'],
        'template_directories': templates,
        'reviewed_package_source_sha256': digest(installer._tree(host)),
        'reviewed_configuration_sha256': digest(configuration),
        'interpreter': sys.executable, 'wheelhouse': str(wheelhouse),
        'package_directory': str(workspace / 'package'),
        'environment_parent': str(environments),
        'console_script': read_json(bundle / 'composite-console.json')['script'],
        'build_tools': {name: importlib.metadata.version(name)
                        for name in ('pip', 'setuptools', 'wheel')},
        'wheels': wheel_rows, 'requirements': requirements,
        'configuration': configuration, 'secret_references': {},
    }
    package_plan = installer.plan_composite_package(package_request)
    progress = _record(journey, journey_dir, progress, 'package_planned', plan=package_plan)
    built = installer.build_composite_package(package_plan,
                                              approved_plan_sha256=package_plan['plan_sha256'])
    _external_anchor(anchors, 'package_built', built['receipt_sha256'])
    progress = _record(journey, journey_dir, progress, 'package_built',
                       receipt=built, trusted_receipt_sha256=built['receipt_sha256'])
    install_plan = installer.plan_composite_install(package_plan, built)
    progress = _record(journey, journey_dir, progress, 'install_planned', plan=install_plan)
    installed = installer.install_composite_package(install_plan,
                                                   approved_plan_sha256=install_plan['plan_sha256'])
    _external_anchor(anchors, 'package_installed', installed['receipt_sha256'])
    progress = _record(journey, journey_dir, progress, 'installed',
                       trusted_receipt_sha256=installed['receipt_sha256'])
    origins = _installed_origins(installed, install_plan)

    evidence = _private(workspace / 'external-effects', create=True)
    alpha, queue = evidence / 'alpha.jsonl', evidence / 'queue.jsonl'
    audit, ready, release = evidence / 'audit.json', evidence / 'ready.bin', evidence / 'release.bin'
    alpha_raw = (json.dumps(oracle['alpha_effect'], sort_keys=True, separators=(',', ':')) + '\n').encode()
    queue_raw = (json.dumps(oracle['queue_effect'], sort_keys=True, separators=(',', ':')) + '\n').encode()
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [
                       {'role': role, 'path': str(path), 'before_sha256': None,
                        'expected_sha256': _sha(raw)}
                       for role, path, raw in (
                           ('ready', ready, b'dual-ready\n'),
                           ('entrypoint_reached', alpha, alpha_raw),
                           ('integration_reachable', queue, queue_raw),
                           ('outcome_verified', queue, queue_raw))]}
    launch_environment = {'REGISTERED_ALPHA_EFFECTS': str(alpha),
                          'WORK_QUEUE_EFFECTS': str(queue),
                          'DUAL_AUDIT_PATH': str(audit), 'DUAL_TASK_ID': oracle['task_id'],
                          'DUAL_SHADOW': '1', 'DUAL_REPEAT': '1', 'DUAL_HOLD': '1',
                          'DUAL_READY_PATH': str(ready), 'DUAL_RELEASE_PATH': str(release)}
    progress = journey.promote_journey(journey_dir,
        trusted_journey_head=progress['journey_head_sha256'],
        observation=observation, launch_environment=launch_environment)
    _external_anchor(anchors, 'journey_promoted', progress['journey_head_sha256'])
    runtime = journey_dir / 'runtime'
    delivery_plan = read_json(runtime / 'delivery-plan.json')
    child = delivery.session_status(runtime)
    if child['run_id'] != progress['run_id']:
        raise RuntimeError('dual_run_identity_changed')
    launch_scope = _scope(child, delivery_plan, 'launch')
    original_append = delivery._append
    def interrupt_before_release(directory, rows, event, state):
        if event == 'launched':
            raise RuntimeError('dual_injected_before_release')
        return original_append(directory, rows, event, state)
    delivery._append = interrupt_before_release
    try:
        try:
            delivery.launch_session(runtime, scope=launch_scope,
                                    approved_scope_sha256=launch_scope['scope_sha256'])
        except RuntimeError as error:
            if str(error) != 'dual_injected_before_release':
                raise
        else:
            raise RuntimeError('dual_start_interruption_missing')
    finally:
        delivery._append = original_append
    pending = delivery.session_status(runtime)
    if (pending['pending'] != 'launch' or pending['run_id'] != progress['run_id']
            or alpha.exists() or queue.exists() or ready.exists()):
        raise RuntimeError('dual_unreleased_start_changed_effect')
    _external_anchor(anchors, 'delivery_start_pending', pending['session_head_sha256'])
    recovered = delivery.resume_session(runtime,
        trusted_session_head=pending['session_head_sha256'])
    if recovered['stage'] != 'installed' or recovered['run_id'] != progress['run_id']:
        raise RuntimeError('dual_start_recovery_changed_run')
    _external_anchor(anchors, 'delivery_start_recovered', recovered['session_head_sha256'])
    launch_scope = _scope(recovered, delivery_plan, 'launch')
    launched = delivery.launch_session(runtime, scope=launch_scope,
        approved_scope_sha256=launch_scope['scope_sha256'])
    _external_anchor(anchors, 'delivery_launched', launched['session_head_sha256'])
    observed = launched
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        observed = delivery.observe_session(runtime,
            trusted_session_head=observed['session_head_sha256'])
        if observed['recorded_observations']['outcome_verified'] and observed['current_ready']:
            break
        time.sleep(.02)
    if (not observed['current_process_alive'] or not observed['current_ready']
            or alpha.read_bytes() != alpha_raw or queue.read_bytes() != queue_raw
            or observed['recorded_observations']['provider_reachable'] is not False):
        raise RuntimeError('dual_raw_offline_effect_missing')
    _release(release)
    deadline = time.monotonic() + 12
    while not audit.exists() and time.monotonic() < deadline:
        time.sleep(.02)
    host_audit = read_json(audit)
    if (sorted(host_audit['assessed']) != selection['candidate_ids']
            or len(set(host_audit['task_hashes'])) != 1
            or len(set(host_audit['tokens'])) != 1
            or host_audit['calls'] != oracle['shared_budget']['expected_assessments']
            or len(host_audit['repeat_results']) != 2
            or set(host_audit['repeat_results']) != {'duplicate_queue_job',
                                                      'duplicate_task_effect'}
            or host_audit['audit_types'].count('assessment') != 2
            or host_audit['audit_types'].count('shadow_comparison') != 4
            or len(host_audit['audit_types']) != 6
            # Completion order of original and repeat shadow comparisons varies.
            or host_audit['audit_reasons'].count('shared_total_call_budget') < 1
            or any(reason not in {
                'shared_total_call_budget',
                'runtime_suspended_or_closed_during_assessment',
                'bounded_proposal_not_execution_authorization'}
                   for reason in host_audit['audit_reasons'][-4:])
            or host_audit['modes'] != ['shadow', 'shadow']):
        raise RuntimeError('dual_shared_budget_or_duplicate_missing')
    installed_root = Path(installed['environment']) / 'venv'
    if (Path(host_audit['python_prefix']).resolve() != installed_root.resolve()
            or not all(Path(path).is_relative_to(installed_root)
                       for path in host_audit['module_origins'].values())):
        raise RuntimeError('dual_installed_module_origin_drift')
    repeat_environment = {key: value for key, value in launch_environment.items()
                          if key not in ('DUAL_AUDIT_PATH', 'DUAL_HOLD',
                                         'DUAL_READY_PATH', 'DUAL_RELEASE_PATH', 'DUAL_REPEAT')}
    repeat_environment.update({'PATH': str(installed_root / 'bin'),
                               'PYTHONNOUSERSITE': '1', 'JEV_RUNTIME_MODE': 'off'})
    duplicate = subprocess.run([installed['installed']['console_script']],
        cwd=installed['environment'], env=repeat_environment,
        capture_output=True, timeout=15)
    if (duplicate.returncode == 0 or
            b'duplicate_' not in duplicate.stderr or
            alpha.read_bytes() != alpha_raw or queue.read_bytes() != queue_raw):
        raise RuntimeError('dual_duplicate_effect_not_refused')
    disable_scope = _scope(observed, delivery_plan, 'disable')
    disabled = delivery.stop_session(runtime, scope=disable_scope,
        approved_scope_sha256=disable_scope['scope_sha256'], disable=True)
    if disabled['stage'] != 'disabled':
        raise RuntimeError('dual_disable_incomplete')
    _external_anchor(anchors, 'delivery_disabled', disabled['session_head_sha256'])
    source_status = status_composite(host, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])
    rollback_scope = _scope(disabled, delivery_plan, 'rollback',
                            source_status['rollback_digest'])
    rolled = delivery.rollback_session(runtime, scope=rollback_scope,
        approved_scope_sha256=rollback_scope['scope_sha256'])
    if (rolled['stage'] != 'rolled_back' or
            status_composite(host, bundle)['status'] != 'rolled_back' or
            any(file_hash(host / name) != sha256
                for name, sha256 in review['files'].items())):
        raise RuntimeError('dual_owned_rollback_incomplete')
    _external_anchor(anchors, 'delivery_rolled_back', rolled['session_head_sha256'])
    report = {'schema_version': '1.0', 'kind': 'registered-dual-offline-report-v1',
              'classification': 'independent_installed_composite_fixture',
              'run_id': progress['run_id'], 'candidate_ids': selection['candidate_ids'],
              'source_sha256': {key: value['source']['source_sha256'] for key, value in specs.items()},
              'modified_receipt_sha256': modified['receipt_sha256'],
              'install_receipt_sha256': installed['receipt_sha256'],
              'raw_effect_sha256': {'alpha': file_hash(alpha), 'queue': file_hash(queue)},
              'installed_origins': origins, 'assessment_count': 2,
              'common_task_identity': True, 'shared_budget_exhausted': True,
              'duplicate_refused': True, 'start_recovered_same_run': True,
              'provider_qualification': 'not_run', 'measured_benefit': False,
              'final_stage': rolled['stage']}
    validate_contract(report, 'registered-dual-offline-report-v1')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--anchors', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_offline(args.workspace, args.wheelhouse, args.anchors), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
