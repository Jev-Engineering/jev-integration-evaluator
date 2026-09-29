"""Native job ownership: an exact stopped member leaves unrelated processes alive."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from jev_integration_evaluator import windows_template_session as native_session
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.windows_template_plan import _static_build_guard
from jev_integration_evaluator.windows_template_owned import (
    create_private_directory, write_private_json_exclusive,
)
from jev_integration_evaluator.windows_template_session import (
    _identity, _job_members, _kernel, _kill_on_last_job_handle, _owned_process,
    _start_guardian, _current_guardian_python, _verified_guardian_python,
    observe_windows_template_session, stop_windows_template_session,
    windows_session_status,
)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows Job Object only')
def test_owned_job_stop_does_not_touch_unrelated_process(tmp_path, monkeypatch):
    owned = create_private_directory(tmp_path / 'session')
    zero = '0' * 64
    session = {'schema_version': '1.0', 'kind': 'windows-template-session-v1',
               'owned_directory': owned, 'run_id': str(uuid.uuid4()),
               'install_plan_sha256': zero, 'install_receipt_sha256': zero,
               'install_environment': str(tmp_path), 'python': sys.executable,
               'python_sha256': zero, 'console_script': sys.executable,
               'console_script_sha256': zero, 'launch_environment': {}, 'mode': 'off'}
    session['session_sha256'] = digest(session)
    write_private_json_exclusive(owned, 'session.json', session)
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    target = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    kernel = _kernel()
    job_name = 'Local\\jev-template-' + session['run_id']
    job = kernel.CreateJobObjectW(None, job_name)
    try:
        assert job and ctypes.get_last_error() != 183
        assert kernel.AssignProcessToJobObject(job, int(target._handle))
        created, image = _identity(int(target._handle), kernel)
        intent = {'session_sha256': session['session_sha256'], 'job': job_name,
                  'status': 'launch_pending'}
        write_private_json_exclusive(owned, 'launch-intent.json', intent)
        assert windows_session_status(session)['status'] == 'blocked_recovery'
        identity = {'schema_version': '1.0', 'kind': 'windows-template-process-v1',
                    'session_sha256': session['session_sha256'], 'pid': target.pid,
                    'created_filetime': created, 'image': image, 'job': job_name}
        identity['identity_sha256'] = digest(identity)
        write_private_json_exclusive(owned, 'launch-identity.json', identity)
        write_private_json_exclusive(owned, 'launch-released.json',
                                     {'identity_sha256': identity['identity_sha256'],
                                      'status': 'released'})
        assert windows_session_status(session)['process_alive']
        class UncertainKernel:
            def __init__(self, mode):
                self.mode = mode

            def __getattr__(self, name):
                return getattr(kernel, name)

            def OpenProcess(self, *args):
                if self.mode == 'process_denied':
                    ctypes.set_last_error(5)
                    return 0
                return kernel.OpenProcess(*args)

            def OpenJobObjectW(self, *args):
                if self.mode in ('job_denied', 'job_missing'):
                    ctypes.set_last_error(5 if self.mode == 'job_denied' else 2)
                    return 0
                return kernel.OpenJobObjectW(*args)

            def IsProcessInJob(self, process, job, member):
                if self.mode == 'membership_denied':
                    ctypes.set_last_error(5)
                    return 0
                if self.mode == 'membership_changed':
                    member._obj.value = 0
                    return 1
                return kernel.IsProcessInJob(process, job, member)

        for mode, reason in (
                ('process_denied', 'process_open_unavailable'),
                ('job_denied', 'job_open_unavailable'),
                ('job_missing', 'job_open_unavailable'),
                ('membership_denied', 'job_membership_unavailable'),
                ('membership_changed', 'job_membership_changed')):
            with monkeypatch.context() as patch:
                patch.setattr(native_session, '_kernel', lambda: UncertainKernel(mode))
                with pytest.raises(InputError, match=reason):
                    windows_session_status(session)
                with pytest.raises(InputError, match=reason):
                    observe_windows_template_session(
                        session, approved_identity_sha256=identity['identity_sha256'],
                        phase='effect', path=tmp_path.parent / 'effect.json',
                        expected_sha256=zero)
                with pytest.raises(InputError, match=reason):
                    stop_windows_template_session(
                        session, approved_identity_sha256=identity['identity_sha256'])
            assert target.poll() is None
        stopped = stop_windows_template_session(session,
                                                 approved_identity_sha256=identity['identity_sha256'])
        target.wait(timeout=5)
        assert not stopped['process_alive']
        assert unrelated.poll() is None
        assert windows_session_status(session)['status'] == 'stopped'
    finally:
        kernel.CloseHandle(job)
        if target.poll() is None:
            target.terminate(); target.wait(timeout=5)
        unrelated.terminate(); unrelated.wait(timeout=5)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_package_plan_rejects_executable_setup_and_custom_build_hooks(tmp_path):
    import hashlib
    project = tmp_path / 'pyproject.toml'
    project.write_text('[build-system]\nrequires=["setuptools==80.0.0", "wheel==0.45.1"]\n'
                       'build-backend="setuptools.build_meta"\n'
                       '[project]\nname="host"\nversion="1.0"\n'
                       '[tool.setuptools]\npackages=["host"]\n', encoding='utf-8')
    files = {'pyproject.toml': hashlib.sha256(project.read_bytes()).hexdigest()}
    _static_build_guard(tmp_path, files)
    with pytest.raises(InputError, match='executable_setup'):
        _static_build_guard(tmp_path, files | {'setup.py': '0' * 64})
    project.write_text(project.read_text(encoding='utf-8') +
                       '[tool.setuptools.cmdclass]\nbuild="host:Custom"\n',
                       encoding='utf-8')
    files['pyproject.toml'] = hashlib.sha256(project.read_bytes()).hexdigest()
    with pytest.raises(InputError, match='nonstatic_build'):
        _static_build_guard(tmp_path, files)
    project.write_text('[build-system]\nrequires=["setuptools==80.0.0", "wheel==0.45.1"]\n'
                       'build-backend="setuptools.build_meta"\nbackend-path=[".."]\n'
                       '[project]\nname="host"\nversion="1.0"\n', encoding='utf-8')
    files['pyproject.toml'] = hashlib.sha256(project.read_bytes()).hexdigest()
    with pytest.raises(InputError, match='nonstatic_build'):
        _static_build_guard(tmp_path, files)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows Job Object only')
def test_guardian_retains_named_job_and_kills_owned_gate_on_exit(tmp_path):
    gate = subprocess.Popen([sys._base_executable, '-I', '-c', 'import time;time.sleep(30)'],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    kernel = _kernel()
    job_name = 'Local\\jev-template-' + str(uuid.uuid4())
    job = kernel.CreateJobObjectW(None, job_name)
    keeper = None
    try:
        assert job and ctypes.get_last_error() != 183
        _kill_on_last_job_handle(job, kernel)
        assert kernel.AssignProcessToJobObject(job, int(gate._handle))
        keeper, (keeper_created, keeper_image) = _start_guardian(
            job, gate, tmp_path, kernel, Path(sys._base_executable))
        gate_created, gate_image = _identity(int(gate._handle), kernel)
        identity = {'pid': gate.pid, 'created_filetime': gate_created,
                    'image': gate_image, 'job': job_name}
        assert keeper_created > 0 and keeper_image.endswith('python.exe')
        kernel.CloseHandle(job); job = None
        assert _owned_process(identity)[0]
        count, members = _job_members(identity)
        assert count >= 1 and any(row['pid'] == gate.pid for row in members)
        begun = time.monotonic()
        keeper.terminate(); keeper.wait(timeout=5)
        gate.wait(timeout=5)
        assert time.monotonic() - begun < 5
        assert not _owned_process(identity)[0]
    finally:
        if job:
            kernel.CloseHandle(job)
        if keeper is not None and keeper.poll() is None:
            keeper.terminate(); keeper.wait(timeout=5)
        if gate.poll() is None:
            gate.terminate(); gate.wait(timeout=5)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows toolchain only')
def test_guardian_interpreter_path_and_hash_are_exact():
    path, sha = _current_guardian_python()
    assert _verified_guardian_python({'guardian_python': path,
                                      'guardian_python_sha256': sha}) == Path(path)
    with pytest.raises(InputError, match='guardian_toolchain_drift'):
        _verified_guardian_python({'guardian_python': path,
                                   'guardian_python_sha256': '0' * 64})
