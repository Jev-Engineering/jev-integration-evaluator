"""One owned, finite native Windows console launch from an anchored install.

An immutable intent is durable before the gated child exists. The child cannot
invoke the console until its exact process and job identity have been recorded.
Uncertain outcomes never grant another launch.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from . import capabilities as cap
from .contracts import validate_contract
from .io import InputError, digest
from .windows_template_install import (
    owned_windows_install_receipt, plan_windows_template_install,
)
from .windows_template_owned import (create_private_directory, read_private_json,
                                     write_private_json_exclusive)
from .windows_template_preflight import _profile


_GATE = '''import msvcrt,os,subprocess,sys
fd=msvcrt.open_osfhandle(int(sys.argv[1]),os.O_RDONLY)
try: token=os.read(fd,1)
finally: os.close(fd)
if token!=b'G': sys.exit(91)
sys.exit(subprocess.call([sys.argv[2]],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))'''

_GUARDIAN = '''import ctypes,msvcrt,os,sys
from ctypes import wintypes
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.WaitForSingleObject.argtypes=(wintypes.HANDLE,wintypes.DWORD)
k.WaitForSingleObject.restype=wintypes.DWORD
k.IsProcessInJob.argtypes=(wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.BOOL))
k.IsProcessInJob.restype=wintypes.BOOL
k.CloseHandle.argtypes=(wintypes.HANDLE,)
k.CloseHandle.restype=wintypes.BOOL
job,gate,ack=map(int,sys.argv[1:4])
try:
    member=wintypes.BOOL()
    if k.WaitForSingleObject(gate,0)!=258 or not k.IsProcessInJob(gate,job,ctypes.byref(member)) or not member.value: sys.exit(92)
    fd=msvcrt.open_osfhandle(ack,os.O_WRONLY)
    try: os.write(fd,b'K')
    finally: os.close(fd)
    sys.exit(0 if k.WaitForSingleObject(gate,0xffffffff)==0 else 93)
finally:
    k.CloseHandle(gate)
    k.CloseHandle(job)'''


class _JobBasicLimits(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD)]


class _JobIoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class _JobExtendedLimits(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', _JobBasicLimits),
                ('IoInfo', _JobIoCounters),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t)]


class _JobProcessIds(ctypes.Structure):
    _fields_ = [('NumberOfAssignedProcesses', wintypes.DWORD),
                ('NumberOfProcessIdsInList', wintypes.DWORD),
                ('ProcessIdList', ctypes.c_size_t * 64)]


def _kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.OpenJobObjectW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.OpenJobObjectW.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.IsProcessInJob.argtypes = (wintypes.HANDLE, wintypes.HANDLE,
                                     ctypes.POINTER(wintypes.BOOL))
    kernel.IsProcessInJob.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                                      ctypes.POINTER(wintypes.FILETIME),
                                      ctypes.POINTER(wintypes.FILETIME),
                                      ctypes.POINTER(wintypes.FILETIME))
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, wintypes.INT,
                                                ctypes.c_void_p, wintypes.DWORD)
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.PeekNamedPipe.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                                     ctypes.c_void_p)
    kernel.PeekNamedPipe.restype = wintypes.BOOL
    kernel.QueryInformationJobObject.argtypes = (wintypes.HANDLE, wintypes.INT,
                                                  ctypes.c_void_p, wintypes.DWORD,
                                                  ctypes.POINTER(wintypes.DWORD))
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _kill_on_last_job_handle(job, kernel) -> None:
    limits = _JobExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits),
                                          ctypes.sizeof(limits)):
        raise InputError('windows_session_job_close_limit_unavailable')


def _start_guardian(job, gate, root: Path, kernel,
                    interpreter: Path) -> tuple[subprocess.Popen, tuple[int, str]]:
    """Keep the named Job open until the exact gate exits, with a bounded ack."""
    import msvcrt
    ack_read, ack_write = os.pipe()
    keeper = None
    handles = [int(job), int(gate._handle), msvcrt.get_osfhandle(ack_write)]
    try:
        for handle in handles:
            os.set_handle_inheritable(handle, True)
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {'handle_list': handles}
        keeper = subprocess.Popen(
            [str(interpreter), '-I', '-S', '-c', _GUARDIAN,
             *(str(handle) for handle in handles)],
            cwd=root, env=_environment(root, interpreter, {}),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True, startupinfo=startup,
            creationflags=subprocess.CREATE_NO_WINDOW)
        os.set_handle_inheritable(handles[2], False)
        os.close(ack_write); ack_write = -1
        deadline = time.monotonic() + 10
        raw_read = msvcrt.get_osfhandle(ack_read)
        while time.monotonic() < deadline:
            available = wintypes.DWORD()
            if kernel.PeekNamedPipe(raw_read, None, 0, None,
                                    ctypes.byref(available), None) and available.value:
                if os.read(ack_read, 1) != b'K':
                    break
                if keeper.poll() is not None:
                    break
                return keeper, _identity(int(keeper._handle), kernel)
            if keeper.poll() is not None:
                break
            time.sleep(.02)
        raise InputError('windows_session_guardian_unavailable')
    finally:
        for handle in handles[:2]:
            os.set_handle_inheritable(handle, False)
        os.close(ack_read)
        if ack_write != -1:
            os.set_handle_inheritable(handles[2], False)
            os.close(ack_write)


def _identity(handle, kernel) -> tuple[int, str]:
    created = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel_time = wintypes.FILETIME()
    user_time = wintypes.FILETIME()
    if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exit_time),
                                  ctypes.byref(kernel_time), ctypes.byref(user_time)):
        raise InputError('windows_session_process_identity_unavailable')
    buffer = ctypes.create_unicode_buffer(32768)
    length = wintypes.DWORD(len(buffer))
    if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
        raise InputError('windows_session_process_identity_unavailable')
    return ((created.dwHighDateTime << 32) | created.dwLowDateTime,
            buffer.value.casefold())


def _owned_process(identity: dict, *, terminate: bool = False) -> tuple[bool, object, object]:
    kernel = _kernel()
    process = kernel.OpenProcess(0x101000, False, identity['pid'])
    if not process:
        if ctypes.get_last_error() in (87, 1168):  # no process with this PID
            return False, None, None
        raise InputError('windows_session_process_open_unavailable')
    job = None
    retained = False
    try:
        wait = kernel.WaitForSingleObject(process, 0)
        if wait == 0:
            return False, None, None
        if wait != 0x102:
            raise InputError('windows_session_process_state_unavailable')
        if _identity(process, kernel) != (identity['created_filetime'],
                                          identity['image'].casefold()):
            return False, None, None
        job = kernel.OpenJobObjectW(0x000c if terminate else 0x0004,
                                    False, identity['job'])
        if not job:
            raise InputError('windows_session_job_open_unavailable')
        member = wintypes.BOOL()
        if not kernel.IsProcessInJob(process, job, ctypes.byref(member)):
            raise InputError('windows_session_job_membership_unavailable')
        if not member.value:
            raise InputError('windows_session_job_membership_changed')
        if terminate:
            retained = True
            return True, process, job
        return True, None, None
    finally:
        if not terminate:
            if job:
                kernel.CloseHandle(job)
            kernel.CloseHandle(process)
        elif not retained:
            if job:
                kernel.CloseHandle(job)
            kernel.CloseHandle(process)


def _job_members(identity: dict) -> tuple[int, list[dict]]:
    """Snapshot at most 64 live members of the exact named Job, without effects."""
    kernel = _kernel()
    job = kernel.OpenJobObjectW(0x0004, False, identity['job'])
    if not job:
        raise InputError('windows_session_observation_job_unavailable')
    try:
        info = _JobProcessIds()
        returned = wintypes.DWORD()
        if not kernel.QueryInformationJobObject(job, 3, ctypes.byref(info),
                                                 ctypes.sizeof(info),
                                                 ctypes.byref(returned)):
            raise InputError('windows_session_observation_job_list_unavailable')
        count = info.NumberOfAssignedProcesses
        listed = info.NumberOfProcessIdsInList
        if count > 64 or listed > 64 or listed < count:
            raise InputError('windows_session_observation_job_member_limit')
        members = []
        for index in range(listed):
            pid = int(info.ProcessIdList[index])
            if pid <= 0:
                raise InputError('windows_session_observation_job_list_invalid')
            process = kernel.OpenProcess(0x101000, False, pid)
            if not process:
                if ctypes.get_last_error() in (87, 1168):  # exited during snapshot
                    continue
                raise InputError('windows_session_observation_member_unavailable')
            try:
                state = kernel.WaitForSingleObject(process, 0)
                if state == 0:
                    continue
                if state != 0x102:
                    raise InputError('windows_session_observation_member_unavailable')
                member = wintypes.BOOL()
                if not kernel.IsProcessInJob(process, job, ctypes.byref(member)) or not member.value:
                    raise InputError('windows_session_observation_member_changed')
                created, image = _identity(process, kernel)
                members.append({'pid': pid, 'created_filetime': created,
                                'image': image})
            finally:
                kernel.CloseHandle(process)
        if not any(row == {'pid': identity['pid'],
                           'created_filetime': identity['created_filetime'],
                           'image': identity['image']} for row in members):
            raise InputError('windows_session_observation_gate_missing')
        return count, sorted(members, key=lambda row: row['pid'])
    finally:
        kernel.CloseHandle(job)


def _environment(root: Path, python: Path, extra: dict) -> dict[str, str]:
    if type(extra) is not dict or len(extra) > 16:
        raise InputError('windows_session_environment_invalid')
    env = {'SystemRoot': os.environ['SystemRoot'], 'WINDIR': os.environ['WINDIR'],
           'PATH': str(python.parent), 'TEMP': str(root), 'TMP': str(root),
           'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'JEV_RUNTIME_MODE': 'off'}
    folded = {name.casefold() for name in env}
    for name, value in extra.items():
        if (type(name) is not str or type(value) is not str or len(value) > 4096
                or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', name)
                or name.casefold() in folded or name.startswith(('PYTHON', 'PIP_'))
                or any(term in name for term in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL'))):
            raise InputError('windows_session_environment_invalid')
        folded.add(name.casefold())
        env[name] = value
    return env


def _current_guardian_python() -> tuple[str, str]:
    path = Path(getattr(sys, '_base_executable', sys.executable)).absolute()
    try:
        return str(path), hashlib.sha256(
            cap._windows_secure_input(path, 64_000_000)).hexdigest()
    except (OSError, cap.CapabilityError):
        raise InputError('windows_session_guardian_toolchain_unavailable') from None


def _verified_guardian_python(session: dict) -> Path:
    path, sha = _current_guardian_python()
    if (session.get('guardian_python') != path
            or session.get('guardian_python_sha256') != sha):
        raise InputError('windows_session_guardian_toolchain_drift')
    return Path(path)


def create_windows_template_session(directory: str | Path, install_plan: dict,
                                    install_receipt: dict, *,
                                    trusted_install_receipt_sha256: str,
                                    launch_environment: dict | None = None,
                                    run_id: str | None = None) -> dict:
    """Record an exact off-mode session; creation does not launch the host."""
    _profile()
    if install_plan != plan_windows_template_install(
            install_plan['package_plan'], install_plan['package_receipt'],
            trusted_package_receipt_sha256=install_plan['trusted_package_receipt_sha256']):
        raise InputError('windows_session_install_plan_drift')
    canonical = owned_windows_install_receipt(install_plan,
                                              trusted_install_receipt_sha256)
    if install_receipt != canonical:
        raise InputError('windows_session_install_receipt_substituted')
    if run_id is None:
        run_id = str(uuid.uuid4())
    else:
        try:
            if type(run_id) is not str or str(uuid.UUID(run_id)) != run_id:
                raise ValueError('run_id')
        except ValueError:
            raise InputError('windows_session_run_id_invalid') from None
    python = Path(canonical['installed']['python'])
    guardian_python, guardian_sha = _current_guardian_python()
    if launch_environment is None:
        launch_environment = {}
    _environment(Path(directory), python, launch_environment)
    owned = create_private_directory(directory)
    body = {'schema_version': '1.0', 'kind': 'windows-template-session-v1',
            'run_id': run_id, 'owned_directory': owned,
            'install_plan_sha256': install_plan['plan_sha256'],
            'install_receipt_sha256': trusted_install_receipt_sha256,
            'install_environment': canonical['environment'],
            'python': str(python), 'python_sha256': canonical['installed']['python_sha256'],
            'console_script': canonical['installed']['console_script'],
            'console_script_sha256': canonical['installed']['console_script_sha256'],
            'guardian_python': guardian_python,
            'guardian_python_sha256': guardian_sha,
            'launch_environment': launch_environment, 'mode': 'off'}
    body['session_sha256'] = digest(body)
    validate_contract(body, 'windows-template-session-v1')
    write_private_json_exclusive(owned, 'session.json', body)
    return body


def _checked_session(session: dict, *, check_executables: bool = True) -> tuple[Path, dict]:
    _profile()
    if (type(session) is not dict or session.get('kind') != 'windows-template-session-v1'
            or session.get('session_sha256') != digest({k: v for k, v in session.items()
                                                      if k != 'session_sha256'})):
        raise InputError('windows_session_record_invalid')
    validate_contract(session, 'windows-template-session-v1')
    owned = session['owned_directory']
    if read_private_json(owned, 'session.json') != session:
        raise InputError('windows_session_record_changed')
    root = Path(owned['path'])
    if check_executables:
        _verified_guardian_python(session)
        for path_key, hash_key in (('python', 'python_sha256'),
                                   ('console_script', 'console_script_sha256')):
            if hashlib.sha256(cap._windows_secure_input(Path(session[path_key]),
                                                        64_000_000)).hexdigest() != session[hash_key]:
                raise InputError('windows_session_installed_executable_drift')
    return root, owned


def launch_windows_template_session(session: dict, install_plan: dict, *,
                                    approved_session_sha256: str) -> dict:
    """Launch once, with a gated helper and an exact named Job Object."""
    root, owned = _checked_session(session, check_executables=False)
    canonical = owned_windows_install_receipt(
        install_plan, session['install_receipt_sha256'])
    if (install_plan != plan_windows_template_install(
            install_plan['package_plan'], install_plan['package_receipt'],
            trusted_package_receipt_sha256=install_plan['trusted_package_receipt_sha256'])
            or install_plan['plan_sha256'] != session['install_plan_sha256']
            or session['install_environment'] != canonical['environment']
            or session['python'] != canonical['installed']['python']
            or session['python_sha256'] != canonical['installed']['python_sha256']
            or session['console_script'] != canonical['installed']['console_script']
            or session['console_script_sha256'] != canonical['installed']['console_script_sha256']):
        raise InputError('windows_session_install_drift')
    _checked_session(session)
    if approved_session_sha256 != session['session_sha256']:
        raise InputError('windows_session_exact_launch_authority_required')
    if (root / 'launch-intent.json').exists():
        raise InputError('windows_session_launch_already_attempted')
    # The immutable intent makes any subsequent attempt a review-only case.
    job_name = 'Local\\jev-template-' + session['run_id']
    intent = {'session_sha256': session['session_sha256'], 'job': job_name,
              'status': 'launch_pending'}
    write_private_json_exclusive(owned, 'launch-intent.json', intent)
    import msvcrt
    read_fd, write_fd = os.pipe()
    child = None
    kernel = _kernel()
    job = None
    try:
        raw_handle = msvcrt.get_osfhandle(read_fd)
        os.set_handle_inheritable(raw_handle, True)
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {'handle_list': [raw_handle]}
        child = subprocess.Popen([session['python'], '-I', '-c', _GATE,
                                  str(raw_handle), session['console_script']],
                                 cwd=root, env=_environment(root, Path(session['python']),
                                                             session['launch_environment']),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, close_fds=True,
                                 startupinfo=startup,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        os.set_handle_inheritable(raw_handle, False)
        os.close(read_fd); read_fd = -1
        job = kernel.CreateJobObjectW(None, job_name)
        if not job or ctypes.get_last_error() == 183:
            raise InputError('windows_session_job_name_unavailable')
        _kill_on_last_job_handle(job, kernel)
        if not kernel.AssignProcessToJobObject(job, int(child._handle)):
            raise InputError('windows_session_job_assignment_failed')
        keeper, (keeper_created, keeper_image) = _start_guardian(
            job, child, root, kernel, _verified_guardian_python(session))
        if keeper_image != session['guardian_python'].casefold():
            raise InputError('windows_session_guardian_image_changed')
        created, image = _identity(int(child._handle), kernel)
        identity = {'schema_version': '1.0', 'kind': 'windows-template-process-v1',
                    'session_sha256': session['session_sha256'],
                    'pid': child.pid, 'created_filetime': created, 'image': image,
                    'job': job_name, 'guardian_pid': keeper.pid,
                    'guardian_created_filetime': keeper_created,
                    'guardian_image': keeper_image}
        identity['identity_sha256'] = digest(identity)
        validate_contract(identity, 'windows-template-process-v1')
        write_private_json_exclusive(owned, 'launch-identity.json', identity)
        if owned_windows_install_receipt(
                install_plan, session['install_receipt_sha256']) != canonical:
            raise InputError('windows_session_install_changed_before_release')
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


def windows_session_status(session: dict, *, trusted_identity_sha256: str | None = None) -> dict:
    """Read-only: report process liveness; never infer task success from exit."""
    root, owned = _checked_session(session, check_executables=False)
    if not (root / 'launch-intent.json').exists():
        return {'status': 'created', 'process_alive': False, 'receipt_trust': 'absent'}
    intent = read_private_json(owned, 'launch-intent.json')
    if intent['session_sha256'] != session['session_sha256']:
        raise InputError('windows_session_intent_changed')
    if not (root / 'launch-identity.json').exists():
        return {'status': 'blocked_recovery', 'process_alive': False,
                'receipt_trust': 'absent'}
    identity = read_private_json(owned, 'launch-identity.json')
    validate_contract(identity, 'windows-template-process-v1')
    if (identity['identity_sha256'] != digest({k: v for k, v in identity.items()
                                              if k != 'identity_sha256'})
            or identity['session_sha256'] != session['session_sha256']
            or identity['job'] != intent['job']):
        raise InputError('windows_session_identity_changed')
    released = root / 'launch-released.json'
    alive, _, _ = _owned_process(identity)
    stopping = (root / 'stop-intent.json').exists()
    if stopping and read_private_json(owned, 'stop-intent.json') != {
            'identity_sha256': identity['identity_sha256'], 'status': 'stop_pending'}:
        raise InputError('windows_session_stop_intent_changed')
    if not released.exists():
        return {'status': 'blocked_recovery', 'process_alive': alive,
                'receipt_trust': 'absent'}
    if read_private_json(owned, 'launch-released.json') != {
            'identity_sha256': identity['identity_sha256'], 'status': 'released'}:
        raise InputError('windows_session_release_changed')
    stage = ('stop_pending' if alive else 'stopped') if stopping else (
        'running' if alive else 'exited_unverified')
    return {'status': stage,
            'process_alive': alive, 'receipt_trust':
            'externally_anchored' if trusted_identity_sha256 == identity['identity_sha256']
            else 'recorded_untrusted', 'identity_sha256': identity['identity_sha256']}


def observe_windows_template_session(session: dict, *,
                                     approved_identity_sha256: str,
                                     phase: str, path: str | Path,
                                     expected_sha256: str) -> dict:
    """Read a separately supplied host marker with exact Job identity context.

    This is an external observation, never launch or provider authority. The
    caller must retain the expected path and bytes independently of the host.
    """
    if phase not in ('ready', 'effect') or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise InputError('windows_session_observation_invalid')
    root, owned = _checked_session(session, check_executables=False)
    status = windows_session_status(
        session, trusted_identity_sha256=approved_identity_sha256)
    if (status.get('identity_sha256') != approved_identity_sha256
            or status['receipt_trust'] != 'externally_anchored'):
        raise InputError('windows_session_observation_identity_required')
    if (phase == 'ready' and status['status'] != 'running') or (
            phase == 'effect' and status['status'] not in ('stopped', 'exited_unverified')):
        raise InputError('windows_session_observation_phase_unavailable')
    observed = Path(path)
    if (not observed.is_absolute() or cap._path_is_within(observed, root)
            or cap._path_is_within(observed, Path(session['install_environment']))):
        raise InputError('windows_session_observation_path_invalid')
    try:
        actual = hashlib.sha256(cap._windows_secure_input(observed, 1_000_000)).hexdigest()
    except (OSError, cap.CapabilityError):
        raise InputError('windows_session_observation_unavailable') from None
    assigned_count = None
    members = []
    if phase == 'ready':
        identity = read_private_json(owned, 'launch-identity.json')
        if identity['identity_sha256'] != approved_identity_sha256:
            raise InputError('windows_session_observation_identity_changed')
        assigned_count, members = _job_members(identity)
    report = {'schema_version': '1.0', 'kind': 'windows-template-observation-v1',
              'run_id': session['run_id'], 'session_sha256': session['session_sha256'],
              'identity_sha256': approved_identity_sha256, 'phase': phase,
              'path': str(observed), 'expected_sha256': expected_sha256,
              'observed_sha256': actual,
              'job_assigned_count': assigned_count,
              'job_members': members,
              'status': 'matched' if actual == expected_sha256 else 'mismatched'}
    report['observation_sha256'] = digest(report)
    validate_contract(report, 'windows-template-observation-v1')
    return report


def stop_windows_template_session(session: dict, *, approved_identity_sha256: str) -> dict:
    """Terminate only members of the exact recorded job; no PID-only fallback."""
    root, owned = _checked_session(session, check_executables=False)
    if not (root / 'launch-identity.json').exists():
        raise InputError('windows_session_known_process_required')
    identity = read_private_json(owned, 'launch-identity.json')
    validate_contract(identity, 'windows-template-process-v1')
    if (identity['identity_sha256'] != approved_identity_sha256
            or identity['identity_sha256'] != digest({k: v for k, v in identity.items()
                                                     if k != 'identity_sha256'})
            or identity['session_sha256'] != session['session_sha256']):
        raise InputError('windows_session_exact_stop_authority_required')
    intent = read_private_json(owned, 'launch-intent.json')
    if intent != {'session_sha256': session['session_sha256'],
                  'job': identity['job'], 'status': 'launch_pending'}:
        raise InputError('windows_session_intent_changed')
    if not (root / 'stop-intent.json').exists():
        write_private_json_exclusive(owned, 'stop-intent.json',
                                     {'identity_sha256': approved_identity_sha256,
                                      'status': 'stop_pending'})
    elif read_private_json(owned, 'stop-intent.json')['identity_sha256'] != approved_identity_sha256:
        raise InputError('windows_session_stop_intent_changed')
    alive, process, job = _owned_process(identity, terminate=True)
    if alive:
        kernel = _kernel()
        try:
            if not kernel.TerminateJobObject(job, 2):
                raise InputError('windows_session_owned_stop_failed')
            if kernel.WaitForSingleObject(process, 5000) != 0:
                raise InputError('windows_session_owned_stop_unconfirmed')
        finally:
            kernel.CloseHandle(job)
            kernel.CloseHandle(process)
    return windows_session_status(session, trusted_identity_sha256=approved_identity_sha256)
