"""Source-pinned, offline installed Alpha 1.0.0 -> 1.0.1 -> 1.0.0 journey."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time

from jev_integration_evaluator.io import InputError, digest, file_hash, write_json
from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.template_catalog import prepare_template_binding, materialize_template
from jev_integration_evaluator.integrations.lifecycle import apply_implementation, plan_implementation
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator import template_delivery as delivery

_journey_spec = importlib.util.spec_from_file_location(
    'registered_alpha_installed_journey', Path(__file__).with_name('installed_journey.py'))
if _journey_spec is None or _journey_spec.loader is None:
    raise RuntimeError('registered_alpha_journey_loader_missing')
_journey = importlib.util.module_from_spec(_journey_spec)
_journey_spec.loader.exec_module(_journey)
ROOT = _journey.ROOT
_anchor = _journey._anchor
_create_release = _journey._create_release
_installed_origins = _journey._installed_origins
_private_directory = _journey._private_directory
_refused = _journey._refused
_sha = _journey._sha
_wheel_metadata = _journey._wheel_metadata
source_matched_request = _journey.source_matched_request


REVIEW = ROOT / 'review-upgrade-v1.json'
V2 = ROOT / 'versions/1.0.1'


def _check_review(root: Path, version: str) -> None:
    """Compare copied bytes to separately frozen fixture review before scanning."""
    review = json.loads(REVIEW.read_text(encoding='utf-8'))
    if review['schema_version'] != '1.0' or version not in review['versions']:
        raise ValueError('registered_alpha_upgrade_review_missing')
    for relative, expected in review['versions'][version]['files'].items():
        if file_hash(root / relative) != expected:
            raise ValueError('registered_alpha_upgrade_pinned_source_drift:' + relative)


def _copy_host(workspace: Path, version: str) -> Path:
    host = workspace / ('host-' + version)
    shutil.copytree(ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    if version == '1.0.1':
        shutil.copyfile(V2 / 'host.py', host / 'src/registered_alpha/host.py')
        shutil.copyfile(V2 / 'pyproject.toml', host / 'pyproject.toml')
    _check_review(host, version)
    return host


def _prepare(workspace: Path, wheelhouse: Path, anchors: Path, version: str) -> dict:
    host = _copy_host(workspace, version)
    request, binding = source_matched_request(host)
    bound = prepare_template_binding(host, request, binding)['request']
    template = workspace / ('template-' + version)
    materialize_template(host, bound, template)
    spec = bound['implementation_spec']
    bundle = workspace / ('implementation-' + version)
    source_plan = plan_implementation(host, bound['reviewed_inventory'],
                                      spec['candidate_id'], spec, bundle)
    probe = _private_directory(workspace / ('probe-' + version), create=True)
    old_probe = os.environ.get('REGISTERED_ALPHA_PROBE_EFFECTS_DIR')
    os.environ['REGISTERED_ALPHA_PROBE_EFFECTS_DIR'] = str(probe)
    try:
        baseline = verify_implementation(host, bundle, 'baseline', approve_execution=True)
        if baseline['status'] != 'baseline_passed':
            raise RuntimeError('registered_alpha_upgrade_baseline_failed')
        _anchor(anchors, version + '-baseline', baseline['receipt_sha256'])
        apply_implementation(host, bundle, source_plan['bundle_digest'],
                             baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(host, bundle, 'modified', approve_execution=True,
                                         baseline_sha256=baseline['receipt_sha256'])
        if modified['status'] != 'verified':
            raise RuntimeError('registered_alpha_upgrade_modified_failed')
        _anchor(anchors, version + '-modified', modified['receipt_sha256'])
    finally:
        if old_probe is None:
            os.environ.pop('REGISTERED_ALPHA_PROBE_EFFECTS_DIR', None)
        else:
            os.environ['REGISTERED_ALPHA_PROBE_EFFECTS_DIR'] = old_probe
    wheels = sorted(wheelhouse.glob('*.whl'))
    if not wheels:
        raise ValueError('reviewed_offline_wheelhouse_empty')
    configuration = {'jev_runtime': {'mode': 'off', 'credential_ref': 'env:TYPESAFE_API_KEY'}}
    environments = workspace / 'environments'
    if not environments.exists():
        _private_directory(environments, create=True)
    package_request = {
        'schema_version': '1.0', 'host_root': str(host),
        'implementation_bundle': str(bundle),
        'trusted_modified_receipt_sha256': modified['receipt_sha256'],
        'template_directory': str(template),
        'reviewed_package_source_sha256': digest(installer._tree(host)),
        'reviewed_configuration_sha256': digest(configuration),
        'interpreter': sys.executable, 'wheelhouse': str(wheelhouse),
        'package_directory': str(workspace / ('package-' + version)),
        'environment_parent': str(environments), 'console_script': 'registered-alpha',
        'build_tools': {name: importlib.metadata.version(name)
                        for name in ('pip', 'setuptools', 'wheel')},
        'wheels': [{'filename': p.name, 'sha256': file_hash(p)} for p in wheels],
        'requirements': [{'name': name, 'version': wheel_version, 'wheel': p.name,
                          'sha256': file_hash(p)} for p in wheels
                         for name, wheel_version in [_wheel_metadata(p)]],
        'configuration': configuration,
        'secret_references': {'credential': 'env:TYPESAFE_API_KEY'},
    }
    package_plan = installer.plan_package(package_request)
    package_receipt = installer.build_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_install(package_plan, package_receipt)
    installed = installer.install_package(install_plan,
                                          approved_plan_sha256=install_plan['plan_sha256'])
    origins = _installed_origins(installed, install_plan, workspace)
    if installed['installed']['distributions']['jev-independent-registered-alpha'] != version:
        raise RuntimeError('registered_alpha_upgrade_installed_version_changed')
    _anchor(anchors, version + '-package', package_receipt['receipt_sha256'])
    _anchor(anchors, version + '-install', installed['receipt_sha256'])
    return {'host': host, 'bundle': bundle, 'modified': modified,
            'install_plan': install_plan, 'installed': installed,
            'origins': origins, 'source_sha256': spec['source']['source_sha256']}


def _scope(state: dict, plan: dict, action: str, **extra: str) -> dict:
    scope = {'schema_version': '1.0', 'kind': 'template-delivery-scope-v1',
             'reference': 'registered-alpha-upgrade-offline-v1',
             'run_id': state['run_id'], 'plan_sha256': plan['plan_sha256'],
             'trusted_session_head': state['session_head_sha256'],
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             'revoked': False,
             'grants': {name: name == action for name in
                        ('launch', 'stop', 'disable', 'upgrade', 'rollback')}}
    scope.update(extra)
    scope['scope_sha256'] = digest(scope)
    return scope


def _observation(evidence: Path, generation: str, before: bytes, expected: bytes) -> tuple[dict, dict, Path]:
    ready = evidence / ('ready-' + generation + '.bin')
    release = evidence / ('release-' + generation + '.bin')
    effects = evidence / 'effects.jsonl'
    observation = {'schema_version': '1.0', 'kind': 'template-delivery-observation-v1',
                   'checks': [
                       {'role': role, 'path': str(ready), 'before_sha256': None,
                        'expected_sha256': _sha(b'in-flight\n')}
                       for role in ('ready', 'entrypoint_reached')
                   ] + [
                       {'role': role, 'path': str(effects),
                        'before_sha256': _sha(before) if before else None,
                        'expected_sha256': _sha(expected)}
                       for role in ('integration_reachable', 'outcome_verified')
                   ]}
    environment = {
        'REGISTERED_ALPHA_EFFECTS': str(effects),
        'REGISTERED_ALPHA_AUDIT': str(evidence / ('audit-' + generation + '.jsonl')),
        'REGISTERED_ALPHA_TASK_ID': 'alpha-upgrade-' + generation.replace('.', '-'),
        'REGISTERED_ALPHA_ITEM': 'fixture-one', 'REGISTERED_ALPHA_INTENT': 'summarize',
        'REGISTERED_ALPHA_PERMIT': '1', 'REGISTERED_ALPHA_APPROVED': '1',
        'REGISTERED_ALPHA_HOLD': '1', 'REGISTERED_ALPHA_READY': str(ready),
        'REGISTERED_ALPHA_RELEASE': str(release),
    }
    return observation, environment, release


def _effect(generation: str, action: str) -> bytes:
    return (json.dumps({'task_id': 'alpha-upgrade-' + generation.replace('.', '-'),
                        'action': action, 'item': 'fixture-one'},
                       sort_keys=True, separators=(',', ':')) + '\n').encode()


def _run_generation(runtime: Path, plan: dict, state: dict, release: Path,
                    effects: Path, expected: bytes, anchors: Path, label: str) -> dict:
    scope = _scope(state, plan, 'launch')
    launched = delivery.launch_session(runtime, scope=scope,
                                       approved_scope_sha256=scope['scope_sha256'])
    _anchor(anchors, label + '-launched', launched['session_head_sha256'])
    observed = launched
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        observed = delivery.observe_session(runtime,
            trusted_session_head=observed['session_head_sha256'])
        if observed['recorded_observations']['ready']:
            break
        time.sleep(0.02)
    if not observed['recorded_observations']['ready'] or not observed['current_process_alive']:
        raise RuntimeError('registered_alpha_upgrade_ready_not_live')
    _anchor(anchors, label + '-ready', observed['session_head_sha256'])
    _create_release(release)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        observed = delivery.observe_session(runtime,
            trusted_session_head=observed['session_head_sha256'])
        if observed['recorded_observations']['outcome_verified']:
            break
        time.sleep(0.02)
    if not observed['recorded_observations']['outcome_verified'] or effects.read_bytes() != expected:
        raise RuntimeError('registered_alpha_upgrade_raw_effect_not_verified')
    if observed['recorded_observations']['provider_reachable'] is not False:
        raise RuntimeError('registered_alpha_upgrade_false_provider_claim')
    _anchor(anchors, label + '-effect', observed['session_head_sha256'])
    return observed


def run_offline(workspace: Path, wheelhouse: Path, anchors: Path) -> dict:
    if not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
            and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)):
        raise RuntimeError('registered_alpha_upgrade_requires_linux_x86_64_cpython_3_13')
    wheelhouse = _private_directory(wheelhouse.resolve(strict=True), create=False)
    workspace = _private_directory(workspace, create=True)
    anchors = _private_directory(anchors, create=True)
    if anchors == workspace or anchors.is_relative_to(workspace):
        raise ValueError('external_anchors_must_be_outside_run_workspace')
    old = _prepare(workspace, wheelhouse, anchors, '1.0.0')
    new = _prepare(workspace, wheelhouse, anchors, '1.0.1')
    evidence = _private_directory(workspace / 'external-effects', create=True)
    effects = evidence / 'effects.jsonl'
    first = _effect('1.0.0', 'inspect')
    second = _effect('1.0.1', 'inspect-v2')
    observation, environment, release = _observation(evidence, '1.0.0', b'', first)
    old_plan = delivery.plan_delivery(old['install_plan'],
        trusted_install_receipt_sha256=old['installed']['receipt_sha256'],
        observation=observation, launch_environment=environment)
    runtime = workspace / 'runtime'
    state = delivery.create_session(runtime, old_plan)
    run_id = state['run_id']
    _anchor(anchors, 'session-created', state['session_head_sha256'])
    state = _run_generation(runtime, old_plan, state, release, effects, first,
                            anchors, '1.0.0')
    scope = _scope(state, old_plan, 'stop')
    state = delivery.stop_session(runtime, scope=scope,
                                  approved_scope_sha256=scope['scope_sha256'])
    if state['stage'] != 'stopped':
        raise RuntimeError('registered_alpha_upgrade_old_not_stopped')
    _anchor(anchors, 'old-stopped', state['session_head_sha256'])
    observation, environment, release = _observation(evidence, '1.0.1', first, first + second)
    new_plan = delivery.plan_delivery(new['install_plan'],
        trusted_install_receipt_sha256=new['installed']['receipt_sha256'],
        observation=observation, launch_environment=environment)
    bad = _scope(state, old_plan, 'upgrade', upgrade_plan_sha256='0' * 64)
    _refused(lambda: delivery.upgrade_session(runtime, new_plan, scope=bad,
        approved_scope_sha256=bad['scope_sha256']), delivery.DeliveryError,
        'exact_upgrade_plan_authority_required')
    if delivery.session_status(runtime)['session_head_sha256'] != state['session_head_sha256']:
        raise RuntimeError('registered_alpha_upgrade_refusal_changed_session')
    scope = _scope(state, old_plan, 'upgrade', upgrade_plan_sha256=new_plan['plan_sha256'])
    source_file = new['host'] / 'pyproject.toml'
    source_bytes = source_file.read_bytes()
    source_file.write_bytes(source_bytes + b'\n# unreviewed upgrade source drift\n')
    try:
        _refused(lambda: delivery.upgrade_session(runtime, new_plan, scope=scope,
            approved_scope_sha256=scope['scope_sha256']), InputError,
            'verification_failed')
    finally:
        source_file.write_bytes(source_bytes)
    config_file = Path(new['installed']['environment']) / 'config.json'
    config_bytes = config_file.read_bytes()
    changed_config = json.loads(config_bytes)
    changed_config['jev_runtime']['credential_ref'] = 'env:REGISTERED_ALPHA_UNUSED_KEY'
    config_file.write_text(json.dumps(changed_config, sort_keys=True), encoding='utf-8')
    try:
        _refused(lambda: delivery.upgrade_session(runtime, new_plan, scope=scope,
            approved_scope_sha256=scope['scope_sha256']), InputError, 'drift')
    finally:
        config_file.write_bytes(config_bytes)
    if (delivery.session_status(runtime)['session_head_sha256'] != state['session_head_sha256']
            or effects.read_bytes() != first):
        raise RuntimeError('registered_alpha_upgrade_drift_changed_session_or_effect')
    state = delivery.upgrade_session(runtime, new_plan, scope=scope,
                                     approved_scope_sha256=scope['scope_sha256'])
    if state['run_id'] != run_id or state['stage'] != 'upgrade_staged':
        raise RuntimeError('registered_alpha_upgrade_same_run_not_staged')
    _anchor(anchors, 'upgrade-staged', state['session_head_sha256'])
    state = _run_generation(runtime, new_plan, state, release, effects, first + second,
                            anchors, '1.0.1')
    scope = _scope(state, new_plan, 'disable')
    state = delivery.stop_session(runtime, scope=scope,
                                  approved_scope_sha256=scope['scope_sha256'], disable=True)
    if state['stage'] != 'disabled':
        raise RuntimeError('registered_alpha_upgrade_new_not_disabled')
    _anchor(anchors, 'new-disabled', state['session_head_sha256'])
    previous_digest = digest({'operation': 'restore_previous_owned_generation',
                              'current_plan_sha256': new_plan['plan_sha256'],
                              'previous_plan_sha256': old_plan['plan_sha256'],
                              'run_id': run_id})
    bad = _scope(state, new_plan, 'rollback', rollback_digest='0' * 64)
    _refused(lambda: delivery.rollback_session(runtime, scope=bad,
        approved_scope_sha256=bad['scope_sha256']), delivery.DeliveryError,
        'exact_previous_generation_rollback_required')
    scope = _scope(state, new_plan, 'rollback', rollback_digest=previous_digest)
    state = delivery.rollback_session(runtime, scope=scope,
                                      approved_scope_sha256=scope['scope_sha256'])
    if (state['run_id'] != run_id or state['stage'] != 'rolled_back'
            or state['generation_id'] != old_plan['generation_id']
            or effects.read_bytes() != first + second):
        raise RuntimeError('registered_alpha_upgrade_rollback_wrong_generation_or_effect')
    _anchor(anchors, 'retained-generation-rolled-back', state['session_head_sha256'])
    # The original plan's observation was tied to the empty effect file. A
    # fresh, separately scoped session verifies the retained old installation
    # against the now two-row baseline; the rollback journal keeps its run ID.
    third = _effect('rollback', 'inspect')
    observation, environment, release = _observation(
        evidence, 'rollback', first + second, first + second + third)
    rollback_plan = delivery.plan_delivery(old['install_plan'],
        trusted_install_receipt_sha256=old['installed']['receipt_sha256'],
        observation=observation, launch_environment=environment)
    rollback_runtime = workspace / 'rollback-validation-runtime'
    rollback_state = delivery.create_session(rollback_runtime, rollback_plan)
    _anchor(anchors, 'rollback-validation-created', rollback_state['session_head_sha256'])
    rollback_state = _run_generation(rollback_runtime, rollback_plan, rollback_state,
        release, effects, first + second + third, anchors, 'rollback-validation')
    scope = _scope(rollback_state, rollback_plan, 'disable')
    rollback_state = delivery.stop_session(rollback_runtime, scope=scope,
        approved_scope_sha256=scope['scope_sha256'], disable=True)
    if rollback_state['stage'] != 'disabled':
        raise RuntimeError('registered_alpha_upgrade_rollback_validation_not_disabled')
    _anchor(anchors, 'rollback-validation-disabled', rollback_state['session_head_sha256'])
    report = {'schema_version': '1.0', 'kind': 'registered-alpha-upgrade-report-v1',
              'classification': 'offline_installed_versioned_host', 'run_id': run_id,
              'rollback_validation_run_id': rollback_state['run_id'],
              'versions': ['1.0.0', '1.0.1'],
              'source_sha256': [old['source_sha256'], new['source_sha256']],
              'reviewed_host_file_sha256': [
                  file_hash(ROOT / 'src/registered_alpha/host.py'),
                  file_hash(V2 / 'host.py')],
              'modified_receipt_sha256': [old['modified']['receipt_sha256'],
                                          new['modified']['receipt_sha256']],
              'install_receipt_sha256': [old['installed']['receipt_sha256'],
                                         new['installed']['receipt_sha256']],
              'installed_origins': [old['origins'], new['origins']],
              'raw_effect_sha256': file_hash(effects),
              'raw_actions': ['inspect', 'inspect-v2', 'inspect'],
              'offline_fault_checks': ['wrong_upgrade_plan_refused',
                                       'new_source_drift_refused',
                                       'new_install_config_drift_refused',
                                       'wrong_rollback_digest_refused'],
              'retained_environments': [old['installed']['environment'],
                                         new['installed']['environment']],
              'final_stage': state['stage'], 'final_generation_id': state['generation_id'],
              'provider_qualification': 'not_run', 'measured_benefit': False}
    validate_contract(report, 'registered-alpha-upgrade-report-v1')
    write_json(anchors / 'upgrade-report.json', report)
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
