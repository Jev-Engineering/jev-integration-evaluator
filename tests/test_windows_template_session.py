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

from jev_integration_evaluator.io import digest
from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.windows_template_plan import _static_build_guard
from jev_integration_evaluator.windows_template_owned import (
    create_private_directory, write_private_json_exclusive,
)
from jev_integration_evaluator.windows_template_session import (
    _identity, _kernel, stop_windows_template_session, windows_session_status,
)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows Job Object only')
def test_owned_job_stop_does_not_touch_unrelated_process(tmp_path):
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
