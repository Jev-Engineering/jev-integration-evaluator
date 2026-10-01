"""Separate, durable installed connected-shadow supervisor for an owned Linux console.

Package/install provenance remains off. No model output grants launch authority.
This supervisor records intent before releasing a child and never replays a
possibly executed console command after an uncertain outcome.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import copy
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import uuid

from .contracts import parse_utc, validate_contract
from .io import InputError, canonical, digest, file_hash, read_json
from .template_connected_binding import derive_installed_binding
from . import template_delivery as offline


class ConnectedDeliveryError(InputError):
    """Fixed diagnostic; no reference or credential content is included."""


# These are reviewed host shapes, not grants.  The absent selector retains the
# original Alpha plan representation and its exact canonical digest.
_PROFILES = {
    'retention-h-v1': {
        'source': 'retention_host/host_retention_consumer.py',
        'members': {'host': 'retention_host/host_retention_consumer.py',
                    'console': 'retention_host/console.py',
                    'loader': 'retention_host/connected_authority.py'},
        'references': ('H_CONNECTED_REF', 'H_AUTH_PUBKEY_FILE'),
        'allowed': frozenset({'H_COMMAND', 'H_EFFECT_DIRECTORY', 'H_READY_PATH',
                              'H_RELEASE_PATH', 'H_HOLD', 'H_TASKS'}),
        'binary': ('H_HOLD',),
        'injected': ('H_CONNECTED_REF_SHA256', 'H_AUTH_PUBKEY_SHA256'),
    },
    None: {
        'source': 'src/registered_alpha/host.py',
        'members': {'host': 'registered_alpha/host.py',
                    'console': 'registered_alpha/console.py',
                    'loader': 'registered_alpha/connected_authority.py'},
        'references': ('REGISTERED_ALPHA_CONNECTED_REF',
                       'REGISTERED_ALPHA_AUTH_PUBKEY_FILE'),
        'allowed': frozenset({'REGISTERED_ALPHA_PERMIT', 'REGISTERED_ALPHA_AUDIT',
                              'REGISTERED_ALPHA_EFFECTS', 'REGISTERED_ALPHA_TASK_ID',
                              'REGISTERED_ALPHA_HOLD', 'REGISTERED_ALPHA_READY',
                              'REGISTERED_ALPHA_RELEASE'}),
        'binary': ('REGISTERED_ALPHA_PERMIT', 'REGISTERED_ALPHA_HOLD'),
        'injected': ('REGISTERED_ALPHA_CONNECTED_REF_SHA256',
                     'REGISTERED_ALPHA_AUTH_PUBKEY_SHA256'),
    },
    'retrieval-d-v1': {
        'source': 'retrieval_host/host_retrieval_handoff.py',
        'members': {'host': 'retrieval_host/host_retrieval_handoff.py',
                    'console': 'retrieval_host/console.py',
                    'loader': 'retrieval_host/connected_authority.py'},
        'references': ('D_CONNECTED_REF', 'D_AUTH_PUBKEY_FILE', 'D_CORPUS_PATH'),
        'allowed': frozenset({'D_EFFECT_DIRECTORY', 'D_AUDIT_PATH', 'D_TASKS',
                              'D_READY_PATH', 'D_RELEASE_PATH', 'D_HOLD'}),
        'binary': ('D_HOLD',),
        'injected': ('D_CONNECTED_REF_SHA256', 'D_AUTH_PUBKEY_SHA256'),
    },
    'graph-l-v1': {
        'source': 'graph_host/host_graph_consumer.py',
        'members': {'host': 'graph_host/host_graph_consumer.py',
                    'console': 'graph_host/console.py',
                    'loader': 'graph_host/connected_authority.py'},
        'references': ('L_CONNECTED_REF', 'L_AUTH_PUBKEY_FILE'),
        'allowed': frozenset({'GRAPH_DB_PATH', 'GRAPH_EFFECT_PATH',
                              'GRAPH_SECOND_EFFECT_PATH', 'GRAPH_READY_PATH',
                              'L_TASKS', 'L_HOLD', 'L_RELEASE_PATH',
                              'L_APPROVAL', 'L_EXPECTED_REVISION'}),
        'binary': ('L_HOLD', 'L_APPROVAL'),
        'injected': ('L_CONNECTED_REF_SHA256', 'L_AUTH_PUBKEY_SHA256'),
    },
    'registered-dual-connected-v1': {
        'source': {'JEV-DA938C3C7965': 'src/registered_dual/work_queue.py',
                   'JEV-EDF19BDB65F0': 'src/registered_dual/alpha.py'},
        'members': {'console': 'registered_dual/console.py',
                    'loader': 'registered_dual/connected_authority.py'},
        'references': ('REGISTERED_DUAL_CONNECTED_REF',
                       'REGISTERED_DUAL_AUTH_PUBKEY_FILE'),
        'allowed': frozenset({'DUAL_TASK_ID', 'DUAL_PERMIT', 'DUAL_AUDIT_PATH',
                              'REGISTERED_ALPHA_EFFECTS', 'WORK_QUEUE_EFFECTS',
                              'DUAL_HOLD', 'DUAL_READY_PATH', 'DUAL_RELEASE_PATH',
                              'DUAL_REPEAT'}),
        'binary': ('DUAL_PERMIT', 'DUAL_HOLD', 'DUAL_REPEAT'),
        'injected': ('REGISTERED_DUAL_CONNECTED_REF_SHA256',
                     'REGISTERED_DUAL_AUTH_PUBKEY_SHA256'),
    },
}


def _profile(name: str | None) -> dict:
    if name not in _PROFILES:
        raise ConnectedDeliveryError('connected_host_profile_unregistered')
    return _PROFILES[name]


def _check_profile_binding(binding: dict, profile: dict) -> None:
    if type(profile['source']) is dict:
        sources = profile['source']
        if (binding['kind'] != 'connected-installed-composite-binding-v1'
                or set(binding['candidate_ids']) != set(sources)
                or set(binding['placements']) != set(sources)
                or any(binding['placements'][name]['source_file'] != source
                       or binding['placements'][name]['origins']['host']['wheel_member'] !=
                          source.removeprefix('src/')
                       for name, source in sources.items())
                or any(binding['shared_origins'].get(role, {}).get('wheel_member') != member
                       for role, member in profile['members'].items())):
            raise ConnectedDeliveryError('connected_host_profile_binding_mismatch')
        return
    if (binding['kind'] != 'connected-installed-binding-v1'
            or binding['source_file'] != profile['source']
            or any(binding['origins'].get(role, {}).get('wheel_member') != member
                   for role, member in profile['members'].items())):
        raise ConnectedDeliveryError('connected_host_profile_binding_mismatch')


def _private_file(path: Path, maximum: int) -> None:
    offline._owned_file(path, maximum=maximum)


def _check_reference(path: str) -> None:
    target = Path(path)
    if (not target.is_absolute() or any(part.is_symlink() for part in (target, *target.parents))
            or not target.is_file()):
        raise ConnectedDeliveryError('connected_private_reference_invalid')
    _private_file(target, 256_000)
    offline._private(target.parent)


def plan_connected_delivery(install_plan: dict, *, trusted_install_receipt_sha256: str,
                            trusted_package_receipt_sha256: str,
                            installed_binding: dict, trusted_binding_sha256: str,
                            observation: dict, launch_environment: dict[str, str],
                            requested_mode: str = 'shadow',
                            host_profile: str | None = None) -> dict:
    """Bind exact installed bytes and externally authored shadow observations."""
    offline._linux_profile()
    if requested_mode != 'shadow':
        raise ConnectedDeliveryError('connected_mode_requires_observed_gate')
    profile = _profile(host_profile)
    if host_profile == 'retention-h-v1':
        if type(launch_environment) is not dict:
            raise ConnectedDeliveryError('connected_host_references_required')
        if launch_environment.get('H_COMMAND') != '/prune':
            raise ConnectedDeliveryError('connected_retention_requires_explicit_prune')
        if (not {'H_EFFECT_DIRECTORY', 'H_READY_PATH'} <= set(launch_environment)
                or launch_environment.get('H_TASKS', 'two') not in ('two', 'duplicate')
                or (launch_environment.get('H_HOLD', '0') == '1'
                    and 'H_RELEASE_PATH' not in launch_environment)):
            raise ConnectedDeliveryError('connected_host_references_required')
    references = set(profile['references'])
    allowed = references | profile['allowed'] | {'SSL_CERT_FILE'}
    if (type(launch_environment) is not dict or not references <= set(launch_environment)
            or not set(launch_environment) <= allowed
            or any(launch_environment.get(name, '0') not in ('0', '1')
                   for name in profile['binary'])
            or (host_profile == 'retrieval-d-v1'
                and launch_environment.get('D_TASKS', 'two') not in ('two', 'duplicate'))
            or (host_profile == 'graph-l-v1' and (
                launch_environment.get('L_TASKS', 'two') not in ('two', 'duplicate')
                or launch_environment.get('L_EXPECTED_REVISION', '0') not in ('0', '1')))):
        raise ConnectedDeliveryError('connected_host_references_required')
    if 'SSL_CERT_FILE' in launch_environment:
        _check_reference(launch_environment['SSL_CERT_FILE'])
    for name in references:
        _check_reference(launch_environment[name])
    base = offline.plan_delivery(install_plan,
        trusted_install_receipt_sha256=trusted_install_receipt_sha256,
        observation=observation, launch_environment=launch_environment)
    if {row['role'] for row in observation['checks']} != {
            'ready', 'entrypoint_reached', 'integration_reachable', 'outcome_verified'}:
        raise ConnectedDeliveryError('connected_independent_outcome_schedule_required')
    receipt = offline._receipt(install_plan, trusted_install_receipt_sha256)
    if host_profile == 'registered-dual-connected-v1':
        from .template_connected_composite_binding import derive_installed_composite_binding
        derive = derive_installed_composite_binding
    else:
        derive = derive_installed_binding
    actual = derive(install_plan['package_plan'],
        install_plan['package_receipt'], install_plan, receipt,
        trusted_package_receipt_sha256=trusted_package_receipt_sha256,
        trusted_install_receipt_sha256=trusted_install_receipt_sha256)
    has_loader = ('loader' in actual['shared_origins'] if host_profile ==
                  'registered-dual-connected-v1' else 'loader' in actual['origins'])
    if (actual != installed_binding or actual['binding_sha256'] != trusted_binding_sha256
            or not has_loader):
        raise ConnectedDeliveryError('connected_installed_binding_unverified')
    _check_profile_binding(actual, profile)
    plan = {'schema_version': '1.0', 'kind': 'connected-delivery-plan-v1',
            'off_provenance': base, 'installed_binding': actual,
            'trusted_binding_sha256': trusted_binding_sha256,
            'trusted_package_receipt_sha256': trusted_package_receipt_sha256,
            'reference_sha256': {name: file_hash(Path(launch_environment[name]))
                                 for name in sorted(references | ({'SSL_CERT_FILE'}
                                 if 'SSL_CERT_FILE' in launch_environment else set()))},
            'requested_mode': requested_mode,
            'provider_reachable': None, 'runtime_activation_authorized': False}
    if host_profile is not None:
        plan['host_profile'] = host_profile
    plan['plan_sha256'] = digest(plan)
    validate_contract(plan, 'connected-delivery-plan-v1')
    return plan


def _check_plan(plan: dict) -> None:
    validate_contract(plan, 'connected-delivery-plan-v1')
    if digest({k: v for k, v in plan.items() if k != 'plan_sha256'}) != plan['plan_sha256']:
        raise ConnectedDeliveryError('connected_plan_digest_changed')
    base = plan['off_provenance']
    actual = plan_connected_delivery(base['install_plan'],
        trusted_install_receipt_sha256=base['trusted_install_receipt_sha256'],
        trusted_package_receipt_sha256=plan['trusted_package_receipt_sha256'],
        installed_binding=plan['installed_binding'],
        trusted_binding_sha256=plan['trusted_binding_sha256'],
        observation=base['observation'], launch_environment=base['launch_environment'],
        requested_mode=plan['requested_mode'], host_profile=plan.get('host_profile'))
    if actual != plan:
        raise ConnectedDeliveryError('connected_plan_or_reference_drift')
    for name in plan['reference_sha256']:
        if file_hash(Path(base['launch_environment'][name])) != plan['reference_sha256'][name]:
            raise ConnectedDeliveryError('connected_reference_changed')


def _write_exclusive(path: Path, value: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, value)
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _locked(target: Path):
    import fcntl
    lock = target / 'session.lock'
    _private_file(lock, 64)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ConnectedDeliveryError('connected_session_owned_by_another_controller') from None
        yield
    finally:
        os.close(fd)


def _event(target: Path, previous: list[dict], event: str, state: dict) -> str:
    validate_contract(state, 'connected-delivery-session-v1')
    body = {'sequence': len(previous), 'event': event,
            'previous_sha256': previous[-1]['record_sha256'] if previous else None,
            'state': copy.deepcopy(state)}
    body['record_sha256'] = digest(body)
    stream = target / 'events.jsonl'
    fd = os.open(stream, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    try:
        os.write(fd, canonical(body) + b'\n')
        os.fsync(fd)
    finally:
        os.close(fd)
    previous.append(body)
    return body['record_sha256']


def _open(directory: str | Path) -> tuple[Path, list[dict], dict, dict]:
    target = offline._safe_directory(directory, exists=True)
    offline._private(target)
    _private_file(target / 'plan.json', 4_000_000)
    _private_file(target / 'events.jsonl', 4_000_000)
    plan = read_json(target / 'plan.json')
    validate_contract(plan, 'connected-delivery-plan-v1')
    if digest({k: v for k, v in plan.items() if k != 'plan_sha256'}) != plan['plan_sha256']:
        raise ConnectedDeliveryError('connected_session_plan_changed')
    rows = []
    with (target / 'events.jsonl').open('rb') as stream:
        for raw in stream:
            if len(rows) >= 128 or len(raw) > 1_000_000:
                raise ConnectedDeliveryError('connected_journal_bound_exceeded')
            row = json.loads(raw)
            if (type(row) is not dict or set(row) !=
                    {'sequence', 'event', 'previous_sha256', 'state', 'record_sha256'}
                    or row['sequence'] != len(rows)
                    or row['previous_sha256'] != (rows[-1]['record_sha256'] if rows else None)
                    or row['record_sha256'] != digest({k: v for k, v in row.items()
                                                        if k != 'record_sha256'})):
                raise ConnectedDeliveryError('connected_journal_changed')
            validate_contract(row['state'], 'connected-delivery-session-v1')
            rows.append(row)
    if not rows or rows[-1]['state']['plan_sha256'] != plan['plan_sha256']:
        raise ConnectedDeliveryError('connected_session_plan_changed')
    return target, rows, copy.deepcopy(rows[-1]['state']), plan


def create_connected_session(directory: str | Path, plan: dict,
                             *, approved_plan_sha256: str,
                             generation_parent: dict | None = None) -> dict:
    offline._linux_profile()
    _check_plan(plan)
    if plan['plan_sha256'] != approved_plan_sha256:
        raise ConnectedDeliveryError('exact_connected_plan_approval_required')
    target = offline._safe_directory(directory, exists=False)
    offline._private(target.parent)
    target.mkdir(mode=0o700)
    _write_exclusive(target / 'session.lock', b'')
    _write_exclusive(target / 'plan.json', canonical(plan) + b'\n')
    _write_exclusive(target / 'events.jsonl', b'')
    state = {'schema_version': '1.0', 'kind': 'connected-delivery-session-v1',
             'run_id': (generation_parent['run_id'] if generation_parent else str(uuid.uuid4())),
             'plan_sha256': plan['plan_sha256'],
             'stage': ('generation_pending' if generation_parent else 'installed'),
             'pending': None, 'launch_attempts': 0,
             'process': None, 'failures': (list(generation_parent['failure_history'])
                                          if generation_parent else [])}
    if generation_parent is not None:
        state['generation_parent'] = copy.deepcopy(generation_parent)
    rows = []
    head = _event(target, rows, 'created', state)
    return _result(state, head, plan)


def _authority(scope: dict, approved_scope_sha256: str, head: str,
               state: dict, plan: dict, action: str) -> None:
    validate_contract(scope, 'connected-delivery-scope-v1')
    parent = state.get('generation_parent')
    if (action == 'launch' and parent is not None and
            (datetime.now(timezone.utc) >= parse_utc(parent['original_expires_at'])
             or parse_utc(scope['expires_at']) > parse_utc(parent['original_expires_at']))):
        raise ConnectedDeliveryError('connected_original_cutoff_expired')
    if (scope['scope_sha256'] != approved_scope_sha256
            or scope['scope_sha256'] != digest({k: v for k, v in scope.items()
                                                if k != 'scope_sha256'})
            or scope['run_id'] != state['run_id']
            or scope['plan_sha256'] != state['plan_sha256']
            or scope['public_key_sha256'] != plan['reference_sha256'][
                _profile(plan.get('host_profile'))['references'][1]]
            or scope['trusted_session_head'] != head
            or scope['action'] != action
            or parse_utc(scope['expires_at']) <= datetime.now(timezone.utc)):
        raise ConnectedDeliveryError('exact_expiring_connected_scope_required')


def launch_connected_session(directory: str | Path, *, scope: dict,
                             approved_scope_sha256: str) -> dict:
    offline._linux_profile()
    target = offline._safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, plan = _open(target)
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state, plan, 'launch')
        if state['pending'] or state['launch_attempts'] or state['stage'] != 'installed':
            raise ConnectedDeliveryError('connected_launch_already_attempted')
        _check_plan(plan)
        if not os.environ.get('TYPESAFE_API_KEY'):
            raise ConnectedDeliveryError('connected_credential_unavailable')
        base = plan['off_provenance']
        for row in base['observation']['checks']:
            if offline._probe_hash(Path(row['path'])) != row['before_sha256']:
                raise ConnectedDeliveryError('connected_observation_baseline_changed')
        state['launch_attempts'] = 1
        state['stage'], state['pending'] = 'launch_pending', 'launch'
        _event(target, rows, 'launch_pending', state)
        read_fd, write_fd = os.pipe()
        try:
            env = dict(base['launch_environment'])
            profile = _profile(plan.get('host_profile'))
            env.update({'PATH': str(Path(base['environment']) / 'venv/bin'),
                        'PYTHONNOUSERSITE': '1',
                        'TYPESAFE_API_KEY': os.environ['TYPESAFE_API_KEY'],
                        profile['injected'][0]:
                            plan['reference_sha256'][profile['references'][0]],
                        profile['injected'][1]:
                            plan['reference_sha256'][profile['references'][1]]})
            child = subprocess.Popen([sys.executable, '-I', '-c', offline._HELPER,
                                      str(read_fd), base['console_script'], base['environment']],
                                     pass_fds=(read_fd,), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     close_fds=True, start_new_session=True, env=env,
                                     cwd=base['environment'])
            os.close(read_fd); read_fd = -1
            start = None
            for _ in range(100):
                info = offline._process_info(child.pid)
                if info is not None:
                    start = info[0]
                    break
                time.sleep(0.001)
            if start is None:
                raise ConnectedDeliveryError('connected_child_identity_unavailable')
            state['process'] = {'pid': child.pid, 'boot_id': offline._boot_id(),
                                'start_ticks': start}
            state['stage'] = 'launched'
            _event(target, rows, 'launched', state)
            os.write(write_fd, b'G')
        finally:
            if read_fd != -1:
                os.close(read_fd)
            os.close(write_fd)
        state['stage'], state['pending'] = 'running', None
        head = _event(target, rows, 'running', state)
        return _result(state, head, plan)


def resume_connected_session(directory: str | Path, *, trusted_session_head: str) -> dict:
    target = offline._safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, plan = _open(target)
        if trusted_session_head != rows[-1]['record_sha256']:
            raise ConnectedDeliveryError('externally_retained_connected_head_required')
        if state['pending'] == 'launch':
            if state['process'] is not None and offline._execed_console(
                    state['process'], plan['off_provenance']['console_script']):
                state['stage'], state['pending'] = 'running', None
                head = _event(target, rows, 'running', state)
                return _result(state, head, plan)
            state['stage'], state['pending'] = 'blocked_recovery', None
            state['failures'].append('launch_effect_unknown')
            head = _event(target, rows, 'blocked_recovery', state)
            return _result(state, head, plan)
        if state['pending'] == 'stop' and not offline._process_alive(state['process']):
            state['stage'], state['pending'] = 'stopped', None
            head = _event(target, rows, 'stopped', state)
            return _result(state, head, plan)
        return _result(state, rows[-1]['record_sha256'], plan)


def stop_connected_session(directory: str | Path, *, scope: dict,
                           approved_scope_sha256: str) -> dict:
    offline._linux_profile()
    target = offline._safe_directory(directory, exists=True)
    with _locked(target):
        _, rows, state, plan = _open(target)
        _authority(scope, approved_scope_sha256, rows[-1]['record_sha256'], state, plan, 'stop')
        if state['process'] is None or state['pending'] not in (None, 'stop'):
            raise ConnectedDeliveryError('connected_stop_requires_known_process')
        if state['pending'] is None:
            state['stage'], state['pending'] = 'stop_pending', 'stop'
            _event(target, rows, 'stop_pending', state)
        if offline._process_alive(state['process']):
            offline._signal_owned(state['process'], signal.SIGTERM)
            deadline = time.monotonic() + 1.0
            while offline._process_alive(state['process']) and time.monotonic() < deadline:
                time.sleep(0.02)
        if offline._process_alive(state['process']):
            return _result(state, rows[-1]['record_sha256'], plan)
        state['stage'], state['pending'] = 'stopped', None
        head = _event(target, rows, 'stopped', state)
        return _result(state, head, plan)


def connected_session_status(directory: str | Path, *, trusted_session_head: str | None = None) -> dict:
    target, rows, state, plan = _open(directory)
    if trusted_session_head is not None and trusted_session_head != rows[-1]['record_sha256']:
        raise ConnectedDeliveryError('externally_retained_connected_head_required')
    return _result(state, rows[-1]['record_sha256'], plan)


def _result(state: dict, head: str, plan: dict) -> dict:
    base = plan['off_provenance']
    checks = {row['role']: offline._probe_hash(Path(row['path'])) == row['expected_sha256']
              for row in base['observation']['checks']}
    def current(path: str, expected: str, *, private: bool = False,
                origin: bool = False) -> bool:
        try:
            target = Path(path)
            if private:
                _check_reference(path)
            if origin:
                info = target.stat()
                if (info.st_uid != os.geteuid() or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) & 0o022):
                    return False
            return target.is_file() and not target.is_symlink() and file_hash(target) == expected
        except (OSError, InputError):
            return False
    binding = plan['installed_binding']
    if binding['kind'] == 'connected-installed-composite-binding-v1':
        origin_paths = {row['path'] for row in (
            *binding['shared_origins'].values(),
            *(origin for placement in binding['placements'].values()
              for origin in placement['origins'].values()))}
    else:
        origin_paths = {row['path'] for row in binding['origins'].values()}
    sources_current = all(current(row['path'], row['sha256'],
                                  origin=row['path'] in origin_paths)
                          for row in plan['installed_binding']['source_plan']['files'])
    references_current = all(current(base['launch_environment'][name], expected, private=True)
                             for name, expected in plan['reference_sha256'].items())
    result = {'schema_version': '1.0', 'kind': 'connected-delivery-result-v1',
            'run_id': state['run_id'], 'plan_sha256': state['plan_sha256'],
            'session_head_sha256': head, 'stage': state['stage'],
            'pending': state['pending'], 'launch_attempts': state['launch_attempts'],
            'process_alive': offline._process_alive(state['process']),
            'independent_checks': checks, 'failure_history': list(state['failures']),
            'installed_sources_current': sources_current,
            'private_references_current': references_current,
            'evidence_type': 'offline_protocol',
            'requested_mode': 'shadow', 'provider_reachable': None,
            'observed_benefit': None}
    validate_contract(result, 'connected-delivery-result-v1')
    return result
