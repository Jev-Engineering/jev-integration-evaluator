"""Real abrupt death at native install boundaries blocks reuse of partial installs."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from jev_integration_evaluator.io import InputError, file_hash
from jev_integration_evaluator import windows_template_install as install
from jev_integration_evaluator import windows_template_session as session
from jev_integration_evaluator.windows_template_plan import (
    build_windows_template_package, plan_windows_template_package,
)
from test_windows_template_delivery import _request


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')


@pytest.mark.parametrize('phase', ['durable_intent', 'host_installed', 'before_receipt'])
def test_native_installer_process_death_preserves_intent_and_blocks_replay(
        tmp_path, monkeypatch, phase):
    request, _, target, _, _ = _request(tmp_path)
    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    plan = install.plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    root = install._generation(plan)
    unrelated_file = tmp_path / 'unrelated.txt'
    unrelated_file.write_bytes(b'preserve independent work\n')
    unrelated_hash = file_hash(unrelated_file)
    source_hashes = {name: file_hash(target / name)
                     for name in request['reviewed_source_files']}
    plan_file, marker = tmp_path / 'install-plan.json', tmp_path / 'checkpoint.json'
    plan_file.write_text(json.dumps(plan, sort_keys=True), encoding='utf-8')
    from ctypes import wintypes
    kernel = session._kernel()
    kernel.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel.TerminateProcess.restype = wintypes.BOOL
    job = kernel.CreateJobObjectW(None, None)
    assert job, 'Owned fixture Job creation failed'
    child_handle = thread_handle = installer_handle = None
    unrelated = None
    try:
        session._kill_on_last_job_handle(job, kernel)
        clean = {name: os.environ[name] for name in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP')
                 if name in os.environ}
        clean['PATH'] = str(Path(sys.executable).parent)
        unrelated = subprocess.Popen(
            [session._current_guardian_python(), '-c', 'import time; time.sleep(600)'],
            cwd=tmp_path, env=clean, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import _winapi
        import msvcrt
        startup = subprocess.STARTUPINFO()
        startup.dwFlags = subprocess.STARTF_USESTDHANDLES
        with open(os.devnull, 'rb') as null_input, open(os.devnull, 'wb') as null_output:
            input_handle = msvcrt.get_osfhandle(null_input.fileno())
            output_handle = msvcrt.get_osfhandle(null_output.fileno())
            startup.hStdInput = input_handle
            startup.hStdOutput = startup.hStdError = output_handle
            startup.lpAttributeList = {'handle_list': [input_handle, output_handle]}
            os.set_handle_inheritable(input_handle, True)
            os.set_handle_inheritable(output_handle, True)
            try:
                command = [sys.executable,
                           str(Path(__file__).with_name('windows_install_death_child.py')),
                           str(plan_file), str(marker), phase]
                child_handle, thread_handle, child_pid, _ = _winapi.CreateProcess(
                    str(Path(sys.executable)), subprocess.list2cmdline(command), None, None,
                    True, subprocess.CREATE_NO_WINDOW | 0x00000004,  # CREATE_SUSPENDED
                    clean, str(tmp_path), startup)
            finally:
                os.set_handle_inheritable(input_handle, False)
                os.set_handle_inheritable(output_handle, False)
        assert kernel.AssignProcessToJobObject(job, child_handle)
        created, image = session._identity(child_handle, kernel)
        kernel.ResumeThread.argtypes = (wintypes.HANDLE,)
        kernel.ResumeThread.restype = wintypes.DWORD
        assert kernel.ResumeThread(thread_handle) == 1
        kernel.CloseHandle(thread_handle)
        thread_handle = None
        deadline = time.monotonic() + 300
        while (not marker.is_file() and kernel.WaitForSingleObject(child_handle, 0) == 0x102
               and time.monotonic() < deadline):
            time.sleep(.05)
        assert marker.is_file(), 'Installer checkpoint missing; bounded child diagnosis retained'
        checkpoint = json.loads(marker.read_text(encoding='utf-8'))
        assert checkpoint['phase'] == phase and checkpoint['plan_sha256'] == plan['plan_sha256']
        assert type(checkpoint['pid']) is int and checkpoint['pid'] > 0
        assert kernel.WaitForSingleObject(child_handle, 0) == 0x102
        assert session._identity(child_handle, kernel) == (created, image)
        # Windows venv redirectors may launch a second interpreter. Both inherit the Job,
        # because it was assigned while the launcher was suspended before its first instruction.
        installer_handle = kernel.OpenProcess(0x101000, False, checkpoint['pid'])
        assert installer_handle
        member = wintypes.BOOL()
        assert kernel.IsProcessInJob(installer_handle, job, ctypes.byref(member)) and member.value
        installer_created, _ = session._identity(installer_handle, kernel)
        assert kernel.WaitForSingleObject(installer_handle, 0) == 0x102
        assert kernel.TerminateJobObject(job, 2)
        assert kernel.WaitForSingleObject(child_handle, 15000) == 0
        assert kernel.WaitForSingleObject(installer_handle, 15000) == 0
        assert _winapi.GetExitCodeProcess(child_handle) != 0
        assert unrelated.poll() is None
        info = session._JobProcessIds()
        deadline = time.monotonic() + 10
        while True:
            assert kernel.QueryInformationJobObject(
                job, 3, ctypes.byref(info), ctypes.sizeof(info), None)
            if info.NumberOfAssignedProcesses == 0 or time.monotonic() >= deadline:
                break
            time.sleep(.05)
        assert info.NumberOfAssignedProcesses == 0
        assert not (root / 'install-receipt.json').exists()
        preserved = {name: file_hash(root / name)
                     for name in ('owner.json', 'install-intent.json')}
        assert (root / 'venv').exists() is (phase != 'durable_intent')
        assert (root / 'config.json').exists() is (phase == 'before_receipt')
        if phase != 'durable_intent':
            module = root / 'venv/Lib/site-packages/atlas_pkg/console.py'
            assert file_hash(module) == file_hash(target / 'atlas_pkg/console.py')
            assert (root / 'venv/Scripts' /
                    (package_plan['inputs']['console_script'] + '.exe')).is_file()
        assert install.windows_install_status(plan) == {
            'status': 'blocked_recovery', 'receipt_trust': 'absent'}
        with pytest.raises(InputError, match='windows_session_install_unverified'):
            install.owned_windows_install_receipt(plan, 'a' * 64)
        replay_commands = []
        def replay_run(command, **kwargs):
            replay_commands.append(command)
            raise AssertionError('Partial generation replay ran an effect command')
        monkeypatch.setattr(install, '_run', replay_run)
        with pytest.raises(InputError, match='existing_generation_requires_status_review'):
            install.install_windows_template_package(
                plan, approved_plan_sha256=plan['plan_sha256'])
        assert replay_commands == []
        assert preserved == {name: file_hash(root / name) for name in preserved}
        assert source_hashes == {name: file_hash(target / name) for name in source_hashes}
        assert file_hash(unrelated_file) == unrelated_hash and unrelated.poll() is None
        (tmp_path / 'death-observation.json').write_text(json.dumps({
            'phase': phase, 'child_pid': child_pid, 'created_filetime': created,
            'installer_pid': checkpoint['pid'], 'installer_created_filetime': installer_created,
            'plan_sha256': plan['plan_sha256'], 'child_reaped': True,
            'job_assigned_count': 0, 'unrelated_alive': True,
            'receipt_absent': True, 'preserved_hashes': preserved}, sort_keys=True),
            encoding='utf-8')
    finally:
        # Every worker/descendant belongs only to our suspended-launch unnamed Job.
        kernel.TerminateJobObject(job, 2)
        if child_handle is not None:
            # Also handles a failure before assignment: this retained HANDLE is ours.
            kernel.TerminateProcess(child_handle, 2)
            kernel.WaitForSingleObject(child_handle, 15000)
        for handle in (installer_handle, thread_handle, child_handle, job):
            if handle is not None:
                kernel.CloseHandle(handle)
        if unrelated is not None:
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=15)
