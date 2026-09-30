"""Versioned native Windows connected shadow owner for an anchored install.

All grants are issued outside the installed child.  The off-mode install and
package receipts are provenance, never activation authority.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from . import capabilities as cap
from .contracts import parse_utc, validate_contract
from .io import InputError, digest
from .windows_connected_verify import cng_identity, verify_p256_sha256
from .windows_template_connected_binding import (
    current_origin, derive_windows_installed_binding,
)
from .windows_template_install import owned_windows_install_receipt
from .windows_template_owned import (
    acl_sha256, check_private_directory, create_private_directory,
    read_private_json, write_private_json_exclusive,
)
from .windows_template_plan import windows_package_status
from .windows_template_preflight import _profile
from . import windows_template_session as native_session


class WindowsConnectedDeliveryError(InputError):
    """Fixed diagnostic without key, source or credential bytes."""


_HEX = re.compile(r'^[a-f0-9]{64}$')
_ENV = frozenset({
    'REGISTERED_ALPHA_PERMIT', 'REGISTERED_ALPHA_AUDIT',
    'REGISTERED_ALPHA_EFFECTS', 'REGISTERED_ALPHA_TASK_ID',
    'REGISTERED_ALPHA_HOLD', 'REGISTERED_ALPHA_READY',
    'REGISTERED_ALPHA_RELEASE', 'REGISTERED_ALPHA_AUTH_PUBKEY_FILE',
    'REGISTERED_ALPHA_CONNECTED_REF', 'SSL_CERT_FILE',
    'REGISTERED_ALPHA_OBSERVATION_ACL_SHA256',
    'REGISTERED_ALPHA_REFERENCE_ACL_SHA256',
    'REGISTERED_ALPHA_ENTRYPOINT', 'REGISTERED_ALPHA_INTEGRATION',
})
_REFS = frozenset({'REGISTERED_ALPHA_AUTH_PUBKEY_FILE',
                   'REGISTERED_ALPHA_CONNECTED_REF'})
_ROLES = frozenset({'ready', 'entrypoint_reached',
                    'integration_reachable', 'outcome_verified'})


def _reference(path: Path, owned: dict, expected_sha256: str | None = None) -> str:
    """Read a current owner-private reference through no-link NTFS checks."""
    try:
        check_private_directory(owned)
        if (not path.is_absolute() or path.parent != Path(owned['path'])
                or path.stat().st_nlink != 1
                or acl_sha256(path) != owned['lock_acl_sha256']):
            raise WindowsConnectedDeliveryError('windows_connected_reference_invalid')
        raw = cap._windows_secure_input(path, 1_000_000)
        actual = hashlib.sha256(raw).hexdigest()
        if expected_sha256 is not None and actual != expected_sha256:
            raise WindowsConnectedDeliveryError('windows_connected_reference_changed')
        check_private_directory(owned)
        return actual
    except (OSError, cap.CapabilityError):
        raise WindowsConnectedDeliveryError('windows_connected_reference_invalid') from None


def plan_windows_connected_delivery(install_plan: dict, *,
                                    trusted_package_receipt_sha256: str,
                                    trusted_install_receipt_sha256: str,
                                    installed_binding: dict,
                                    trusted_binding_sha256: str,
                                    reference_owner: dict,
                                    observation_owner: dict,
                                    launch_environment: dict[str, str],
                                    observation: dict,
                                    requested_mode: str = 'shadow',
                                    _require_observation_baseline: bool = True) -> dict:
    """Recompute the native binding and bind exact private inputs and oracle schedule."""
    _profile()
    if requested_mode != 'shadow':
        raise WindowsConnectedDeliveryError('windows_connected_mode_requires_observed_gate')
    if (type(launch_environment) is not dict or not _REFS <= set(launch_environment)
            or not set(launch_environment) <= _ENV
            or any(type(value) is not str for value in launch_environment.values())
            or launch_environment.get('REGISTERED_ALPHA_PERMIT', '0') not in ('0', '1')
            or launch_environment.get('REGISTERED_ALPHA_HOLD', '0') not in ('0', '1')):
        raise WindowsConnectedDeliveryError('windows_connected_environment_invalid')
    mandatory = {'REGISTERED_ALPHA_READY', 'REGISTERED_ALPHA_ENTRYPOINT',
                 'REGISTERED_ALPHA_INTEGRATION', 'REGISTERED_ALPHA_EFFECTS',
                 'REGISTERED_ALPHA_AUDIT', 'REGISTERED_ALPHA_TASK_ID',
                 'REGISTERED_ALPHA_OBSERVATION_ACL_SHA256',
                 'REGISTERED_ALPHA_REFERENCE_ACL_SHA256'}
    task_id = launch_environment.get('REGISTERED_ALPHA_TASK_ID', '')
    if (not mandatory <= set(launch_environment)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', task_id)):
        raise WindowsConnectedDeliveryError('windows_connected_environment_invalid')
    check_private_directory(reference_owner)
    if launch_environment.get('REGISTERED_ALPHA_REFERENCE_ACL_SHA256') != reference_owner['acl_sha256']:
        raise WindowsConnectedDeliveryError('windows_connected_reference_owner_invalid')
    if (type(observation) is not dict or set(observation) != {'checks'}
            or type(observation['checks']) is not list
            or len(observation['checks']) != 4
            or {row.get('role') for row in observation['checks']} != _ROLES):
        raise WindowsConnectedDeliveryError('windows_connected_observation_invalid')
    expected_paths = {
        'ready': launch_environment['REGISTERED_ALPHA_READY'],
        'entrypoint_reached': launch_environment['REGISTERED_ALPHA_ENTRYPOINT'],
        'integration_reachable': launch_environment['REGISTERED_ALPHA_INTEGRATION'],
        'outcome_verified': str(Path(launch_environment['REGISTERED_ALPHA_EFFECTS']).parent /
                                ('effect-' + task_id + '.json')),
    }
    check_private_directory(observation_owner)
    if launch_environment.get('REGISTERED_ALPHA_OBSERVATION_ACL_SHA256') != observation_owner['acl_sha256']:
        raise WindowsConnectedDeliveryError('windows_connected_observation_owner_invalid')
    for row in observation['checks']:
        if (type(row) is not dict or set(row) != {'role', 'path', 'before_sha256',
                                                'after_sha256'}
                or type(row['path']) is not str or not Path(row['path']).is_absolute()
                or not _HEX.fullmatch(row['before_sha256'])
                or not _HEX.fullmatch(row['after_sha256'])
                or row['before_sha256'] != hashlib.sha256(b'').hexdigest()
                or row['path'] != expected_paths[row['role']]):
            raise WindowsConnectedDeliveryError('windows_connected_observation_invalid')
        path = Path(row['path'])
        if (path.parent != Path(observation_owner['path']) or
                cap._path_is_within(path, install_plan['package_plan']['request']['host_root'])):
            raise WindowsConnectedDeliveryError('windows_connected_observation_overlap')
        try:
            try:
                os.lstat(path)
            except FileNotFoundError:
                baseline = hashlib.sha256(b'').hexdigest()
            else:
                baseline = hashlib.sha256(cap._windows_secure_input(path, 1_000_000)).hexdigest()
        except (OSError, cap.CapabilityError):
            raise WindowsConnectedDeliveryError('windows_connected_observation_invalid') from None
        if _require_observation_baseline and baseline != row['before_sha256']:
            raise WindowsConnectedDeliveryError('windows_connected_observation_baseline_changed')
    package_plan = install_plan['package_plan']
    package_receipt = install_plan['package_receipt']
    if windows_package_status(package_plan,
            trusted_receipt_sha256=trusted_package_receipt_sha256).get('receipt_trust') != 'externally_anchored':
        raise WindowsConnectedDeliveryError('windows_connected_package_unverified')
    install_receipt = owned_windows_install_receipt(install_plan,
                                                   trusted_install_receipt_sha256)
    actual = derive_windows_installed_binding(
        package_plan, package_receipt, install_plan, install_receipt,
        trusted_package_receipt_sha256=trusted_package_receipt_sha256,
        trusted_install_receipt_sha256=trusted_install_receipt_sha256)
    if (actual != installed_binding or actual['binding_sha256'] != trusted_binding_sha256
            or 'loader' not in actual['origins']):
        raise WindowsConnectedDeliveryError('windows_connected_binding_unverified')
    reference_hashes = {}
    for name in sorted(_REFS | ({'SSL_CERT_FILE'} if 'SSL_CERT_FILE' in launch_environment else set())):
        reference_hashes[name] = _reference(Path(launch_environment[name]), reference_owner)
    report = {'schema_version': '1.0', 'kind': 'windows-connected-delivery-plan-v1',
              'install_plan_sha256': install_plan['plan_sha256'],
              'trusted_package_receipt_sha256': trusted_package_receipt_sha256,
              'trusted_install_receipt_sha256': trusted_install_receipt_sha256,
              'installed_binding_sha256': trusted_binding_sha256,
              'cng': cng_identity(),
              'reference_owner': reference_owner,
              'observation_owner': observation_owner,
              'reference_sha256': reference_hashes,
              'launch_environment': launch_environment,
              'observation': observation,
              'requested_mode': requested_mode,
              'runtime_activation_authorized': False,
              'provider_reachable': None}
    report['plan_sha256'] = digest(report)
    validate_contract(report, 'windows-connected-delivery-plan-v1')
    return report


def _check_plan(plan: dict, install_plan: dict, installed_binding: dict, *,
                require_observation_baseline: bool = True) -> dict:
    validate_contract(plan, 'windows-connected-delivery-plan-v1')
    if (plan['plan_sha256'] != digest({k: v for k, v in plan.items()
                                      if k != 'plan_sha256'})
            or installed_binding['binding_sha256'] != plan['installed_binding_sha256']):
        raise WindowsConnectedDeliveryError('windows_connected_plan_changed')
    exact = plan_windows_connected_delivery(
        install_plan,
        trusted_package_receipt_sha256=plan['trusted_package_receipt_sha256'],
        trusted_install_receipt_sha256=plan['trusted_install_receipt_sha256'],
        installed_binding=installed_binding,
        trusted_binding_sha256=plan['installed_binding_sha256'],
        reference_owner=plan['reference_owner'],
        observation_owner=plan['observation_owner'],
        launch_environment=plan['launch_environment'],
        observation=plan['observation'], requested_mode=plan['requested_mode'],
        _require_observation_baseline=require_observation_baseline)
    if exact != plan:
        raise WindowsConnectedDeliveryError('windows_connected_plan_drift')
    for role, origin in installed_binding['origins'].items():
        if not current_origin(origin):
            raise WindowsConnectedDeliveryError('windows_connected_installed_origin_changed')
    for name, expected in plan['reference_sha256'].items():
        _reference(Path(plan['launch_environment'][name]), plan['reference_owner'], expected)
    return exact


def _scope(scope: dict, approved_scope_sha256: str, public_key: bytes, *,
           run_id: str, plan_sha256: str, session_sha256: str,
           action: str) -> None:
    """Check an externally issued signature in addition to an approved exact digest."""
    from datetime import datetime, timezone

    validate_contract(scope, 'windows-connected-delivery-scope-v1')
    body = {key: value for key, value in scope.items()
            if key not in ('scope_sha256', 'issuer_signature')}
    if (scope['scope_sha256'] != digest(body)
            or scope['scope_sha256'] != approved_scope_sha256
            or scope['run_id'] != run_id
            or scope['plan_sha256'] != plan_sha256
            or scope['session_sha256'] != session_sha256
            or scope['action'] != action
            or parse_utc(scope['expires_at']) <= datetime.now(timezone.utc)
            or hashlib.sha256(public_key).hexdigest() != scope['public_key_sha256']):
        raise WindowsConnectedDeliveryError('windows_connected_exact_scope_required')
    try:
        signature = base64.b64decode(scope['issuer_signature'], validate=True)
    except (ValueError, base64.binascii.Error):
        raise WindowsConnectedDeliveryError('windows_connected_scope_signature_invalid') from None
    if not verify_p256_sha256(public_key,
            ('scope:' + scope['scope_sha256']).encode('ascii'), signature):
        raise WindowsConnectedDeliveryError('windows_connected_scope_signature_invalid')


def _checked_session(session: dict, plan: dict, *, executables: bool = True) -> tuple[Path, dict]:
    _profile()
    validate_contract(session, 'windows-connected-session-v1')
    if (session['session_sha256'] != digest({k: v for k, v in session.items()
                                            if k != 'session_sha256'})
            or session['plan_sha256'] != plan['plan_sha256']):
        raise WindowsConnectedDeliveryError('windows_connected_session_changed')
    owned = session['owned_directory']
    if (read_private_json(owned, 'session.json') != session
            or read_private_json(owned, 'plan.json') != plan):
        raise WindowsConnectedDeliveryError('windows_connected_session_changed')
    if executables:
        native_session._verified_guardian_python(session)
        for name, hash_name in (('python', 'python_sha256'),
                                ('console_script', 'console_script_sha256')):
            actual = hashlib.sha256(cap._windows_secure_input(
                Path(session[name]), 64_000_000)).hexdigest()
            if actual != session[hash_name]:
                raise WindowsConnectedDeliveryError('windows_connected_executable_changed')
    return Path(owned['path']), owned


def create_windows_connected_session(directory: str | Path, plan: dict,
                                     install_plan: dict, installed_binding: dict, *,
                                     run_id: str | None = None) -> dict:
    """Record one shadow intent owner; creation executes no target code."""
    _check_plan(plan, install_plan, installed_binding)
    install = owned_windows_install_receipt(
        install_plan, plan['trusted_install_receipt_sha256'])
    if run_id is None:
        run_id = str(uuid.uuid4())
    else:
        try:
            if type(run_id) is not str or str(uuid.UUID(run_id)) != run_id:
                raise ValueError('run_id')
        except ValueError:
            raise WindowsConnectedDeliveryError('windows_connected_run_id_invalid') from None
    guardian, guardian_sha = native_session._current_guardian_python()
    owned = create_private_directory(directory)
    session = {'schema_version': '1.0', 'kind': 'windows-connected-session-v1',
               'run_id': run_id, 'owned_directory': owned,
               'plan_sha256': plan['plan_sha256'],
               'installed_binding_sha256': plan['installed_binding_sha256'],
               'install_plan_sha256': install_plan['plan_sha256'],
               'install_receipt_sha256': plan['trusted_install_receipt_sha256'],
               'install_environment': install['environment'],
               'python': install['installed']['python'],
               'python_sha256': install['installed']['python_sha256'],
               'console_script': install['installed']['console_script'],
               'console_script_sha256': install['installed']['console_script_sha256'],
               'guardian_python': guardian, 'guardian_python_sha256': guardian_sha,
               'mode': 'shadow'}
    session['session_sha256'] = digest(session)
    validate_contract(session, 'windows-connected-session-v1')
    write_private_json_exclusive(owned, 'plan.json', plan)
    write_private_json_exclusive(owned, 'session.json', session)
    return session


def _environment(root: Path, session: dict, plan: dict) -> dict[str, str]:
    """Use a finite clean child environment, with no issuer signing capability."""
    credential = os.environ.get('TYPESAFE_API_KEY')
    if not credential:
        raise WindowsConnectedDeliveryError('windows_connected_credential_unavailable')
    env = native_session._environment(root, Path(session['python']), {})
    env['JEV_RUNTIME_MODE'] = 'shadow'
    for name in ('PROCESSOR_ARCHITECTURE', 'PROCESSOR_ARCHITEW6432'):
        if name in os.environ:
            env[name] = os.environ[name]
    env.update(plan['launch_environment'])
    env.update({'TYPESAFE_API_KEY': credential,
                'REGISTERED_ALPHA_AUTH_PUBKEY_SHA256': plan['reference_sha256'][
                    'REGISTERED_ALPHA_AUTH_PUBKEY_FILE'],
                'REGISTERED_ALPHA_CONNECTED_REF_SHA256': plan['reference_sha256'][
                    'REGISTERED_ALPHA_CONNECTED_REF']})
    return env


def launch_windows_connected_session(session: dict, plan: dict, install_plan: dict,
                                     installed_binding: dict, *, scope: dict,
                                     approved_scope_sha256: str) -> dict:
    """Durable one-shot launch into an exact Job after independent signed scope."""
    root, owned = _checked_session(session, plan)
    if (root / 'launch-intent.json').exists():
        raise WindowsConnectedDeliveryError('windows_connected_launch_already_attempted')
    _check_plan(plan, install_plan, installed_binding)
    public_path = Path(plan['launch_environment']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'])
    _scope(scope, approved_scope_sha256,
           cap._windows_secure_input(public_path, 4096), run_id=session['run_id'],
           plan_sha256=plan['plan_sha256'], session_sha256=session['session_sha256'],
           action='launch')
    child_env = _environment(root, session, plan)
    job_name = 'Local\\jev-template-' + session['run_id']
    write_private_json_exclusive(owned, 'launch-intent.json',
        {'session_sha256': session['session_sha256'], 'job': job_name,
         'status': 'launch_pending'})
    import msvcrt
    read_fd, write_fd = os.pipe()
    child = None
    kernel = native_session._kernel()
    job = None
    try:
        raw_handle = msvcrt.get_osfhandle(read_fd)
        os.set_handle_inheritable(raw_handle, True)
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {'handle_list': [raw_handle]}
        child = subprocess.Popen([session['python'], '-I', '-c', native_session._GATE,
                                  str(raw_handle), session['console_script']],
                                 cwd=root, env=child_env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 close_fds=True, startupinfo=startup,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        os.set_handle_inheritable(raw_handle, False)
        os.close(read_fd); read_fd = -1
        job = kernel.CreateJobObjectW(None, job_name)
        if not job or ctypes.get_last_error() == 183:
            raise WindowsConnectedDeliveryError('windows_connected_job_name_unavailable')
        native_session._kill_on_last_job_handle(job, kernel)
        if not kernel.AssignProcessToJobObject(job, int(child._handle)):
            raise WindowsConnectedDeliveryError('windows_connected_job_assignment_failed')
        guardian, (created_guardian, image_guardian) = native_session._start_guardian(
            job, child, root, kernel, native_session._verified_guardian_python(session))
        if image_guardian != session['guardian_python'].casefold():
            raise WindowsConnectedDeliveryError('windows_connected_guardian_changed')
        created, image = native_session._identity(int(child._handle), kernel)
        identity = {'schema_version': '1.0', 'kind': 'windows-template-process-v1',
                    'session_sha256': session['session_sha256'],
                    'pid': child.pid, 'created_filetime': created, 'image': image,
                    'job': job_name, 'guardian_pid': guardian.pid,
                    'guardian_created_filetime': created_guardian,
                    'guardian_image': image_guardian}
        identity['identity_sha256'] = digest(identity)
        validate_contract(identity, 'windows-template-process-v1')
        write_private_json_exclusive(owned, 'launch-identity.json', identity)
        _check_plan(plan, install_plan, installed_binding)
        _scope(scope, approved_scope_sha256,
               cap._windows_secure_input(public_path, 4096), run_id=session['run_id'],
               plan_sha256=plan['plan_sha256'], session_sha256=session['session_sha256'],
               action='launch')
        os.write(write_fd, b'G')
        write_private_json_exclusive(owned, 'launch-released.json',
                                     {'identity_sha256': identity['identity_sha256'],
                                      'status': 'released'})
        return identity
    finally:
        if read_fd != -1:
            os.close(read_fd)
        os.close(write_fd)
        if job:
            kernel.CloseHandle(job)


def windows_connected_session_status(session: dict, plan: dict, install_plan: dict,
                                     installed_binding: dict, *,
                                     trusted_identity_sha256: str | None = None) -> dict:
    """Read current source, references, Job identity and durable phase."""
    root, owned = _checked_session(session, plan, executables=False)
    _check_plan(plan, install_plan, installed_binding,
                require_observation_baseline=False)
    if not (root / 'launch-intent.json').exists():
        return {'status': 'created', 'process_alive': False, 'receipt_trust': 'absent'}
    intent = read_private_json(owned, 'launch-intent.json')
    if intent != {'session_sha256': session['session_sha256'],
                  'job': 'Local\\jev-template-' + session['run_id'],
                  'status': 'launch_pending'}:
        raise WindowsConnectedDeliveryError('windows_connected_intent_changed')
    if not (root / 'launch-identity.json').exists():
        return {'status': 'blocked_recovery', 'process_alive': False,
                'receipt_trust': 'absent'}
    identity = read_private_json(owned, 'launch-identity.json')
    validate_contract(identity, 'windows-template-process-v1')
    if (identity['identity_sha256'] != digest({k: v for k, v in identity.items()
                                              if k != 'identity_sha256'})
            or identity['session_sha256'] != session['session_sha256']
            or identity['job'] != intent['job']):
        raise WindowsConnectedDeliveryError('windows_connected_identity_changed')
    alive, _, _ = native_session._owned_process(identity)
    stopping = (root / 'stop-intent.json').exists()
    if stopping and read_private_json(owned, 'stop-intent.json') != {
            'identity_sha256': identity['identity_sha256'], 'status': 'stop_pending'}:
        raise WindowsConnectedDeliveryError('windows_connected_stop_intent_changed')
    if not (root / 'launch-released.json').exists():
        return {'status': 'blocked_recovery', 'process_alive': alive,
                'receipt_trust': 'absent'}
    if read_private_json(owned, 'launch-released.json') != {
            'identity_sha256': identity['identity_sha256'], 'status': 'released'}:
        raise WindowsConnectedDeliveryError('windows_connected_release_changed')
    stage = ('stop_pending' if alive else 'stopped') if stopping else (
        'running' if alive else 'exited_unverified')
    return {'status': stage, 'process_alive': alive,
            'receipt_trust': ('externally_anchored' if trusted_identity_sha256 ==
                              identity['identity_sha256'] else 'recorded_untrusted'),
            'identity_sha256': identity['identity_sha256']}


def observe_windows_connected_session(session: dict, plan: dict, install_plan: dict,
                                      installed_binding: dict, *,
                                      approved_identity_sha256: str,
                                      role: str) -> dict:
    """Read a predeclared independent host marker with current Job context."""
    if role not in _ROLES:
        raise WindowsConnectedDeliveryError('windows_connected_observation_role_invalid')
    root, owned = _checked_session(session, plan, executables=False)
    status = windows_connected_session_status(
        session, plan, install_plan, installed_binding,
        trusted_identity_sha256=approved_identity_sha256)
    if (status.get('identity_sha256') != approved_identity_sha256
            or status['receipt_trust'] != 'externally_anchored'):
        raise WindowsConnectedDeliveryError('windows_connected_observation_identity_required')
    if (role == 'ready' and status['status'] != 'running'
            or role != 'ready' and status['status'] not in ('stopped', 'exited_unverified')):
        raise WindowsConnectedDeliveryError('windows_connected_observation_phase_invalid')
    row = next(item for item in plan['observation']['checks'] if item['role'] == role)
    path = Path(row['path'])
    try:
        check_private_directory(plan['observation_owner'])
        if path.parent != Path(plan['observation_owner']['path']):
            raise WindowsConnectedDeliveryError('windows_connected_observation_owner_changed')
        if acl_sha256(path) != plan['observation_owner']['lock_acl_sha256']:
            raise WindowsConnectedDeliveryError('windows_connected_observation_acl_changed')
        observed = hashlib.sha256(cap._windows_secure_input(path, 1_000_000)).hexdigest()
        check_private_directory(plan['observation_owner'])
    except (OSError, cap.CapabilityError):
        raise WindowsConnectedDeliveryError('windows_connected_observation_unavailable') from None
    members = []
    assigned_count = None
    if role == 'ready':
        identity = read_private_json(owned, 'launch-identity.json')
        assigned_count, members = native_session._job_members(identity)
    report = {'schema_version': '1.0', 'kind': 'windows-connected-observation-v1',
              'run_id': session['run_id'], 'session_sha256': session['session_sha256'],
              'identity_sha256': approved_identity_sha256, 'role': role,
              'path': str(path), 'expected_sha256': row['after_sha256'],
              'observed_sha256': observed,
              'job_assigned_count': assigned_count, 'job_members': members,
              'status': 'matched' if observed == row['after_sha256'] else 'mismatched'}
    report['observation_sha256'] = digest(report)
    validate_contract(report, 'windows-connected-observation-v1')
    record_name = 'observation-' + role + '.json'
    if (root / record_name).exists():
        if read_private_json(owned, record_name) != report:
            raise WindowsConnectedDeliveryError('windows_connected_observation_changed')
    else:
        write_private_json_exclusive(owned, record_name, report)
    return report


def stop_windows_connected_session(session: dict, plan: dict, install_plan: dict,
                                   installed_binding: dict, *, scope: dict,
                                   approved_scope_sha256: str,
                                   approved_identity_sha256: str) -> dict:
    """Stop only the exact owned Job under a fresh signed stop scope."""
    root, owned = _checked_session(session, plan, executables=False)
    public_path = Path(plan['launch_environment']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'])
    _reference(public_path, plan['reference_owner'],
               plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'])
    _scope(scope, approved_scope_sha256, cap._windows_secure_input(public_path, 4096),
           run_id=session['run_id'], plan_sha256=plan['plan_sha256'],
           session_sha256=session['session_sha256'], action='stop')
    status = windows_connected_session_status(session, plan, install_plan,
                                              installed_binding,
                                              trusted_identity_sha256=approved_identity_sha256)
    if status.get('identity_sha256') != approved_identity_sha256:
        raise WindowsConnectedDeliveryError('windows_connected_exact_stop_identity_required')
    if not (root / 'stop-intent.json').exists():
        write_private_json_exclusive(owned, 'stop-intent.json',
            {'identity_sha256': approved_identity_sha256, 'status': 'stop_pending'})
    elif read_private_json(owned, 'stop-intent.json') != {
            'identity_sha256': approved_identity_sha256, 'status': 'stop_pending'}:
        raise WindowsConnectedDeliveryError('windows_connected_stop_intent_changed')
    identity = read_private_json(owned, 'launch-identity.json')
    alive, process, job = native_session._owned_process(identity, terminate=True)
    if alive:
        kernel = native_session._kernel()
        try:
            if not kernel.TerminateJobObject(job, 2):
                raise WindowsConnectedDeliveryError('windows_connected_owned_stop_failed')
            if kernel.WaitForSingleObject(process, 5000) != 0:
                raise WindowsConnectedDeliveryError('windows_connected_owned_stop_unconfirmed')
        finally:
            kernel.CloseHandle(job)
            kernel.CloseHandle(process)
    return windows_connected_session_status(session, plan, install_plan,
                                            installed_binding,
                                            trusted_identity_sha256=approved_identity_sha256)
