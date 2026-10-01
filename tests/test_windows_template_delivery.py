"""Native installed console journey with private offline wheelhouse."""
from __future__ import annotations

from email.parser import BytesParser
from contextlib import contextmanager
import copy
import hashlib
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

import pytest

from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.template_catalog import (
    materialize_template, prepare_template_binding,
)
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.windows_template_plan import (
    build_windows_template_package, plan_windows_template_package,
    windows_package_status, _generation as _package_generation,
)
from jev_integration_evaluator.windows_template_install import (
    install_windows_template_package, plan_windows_template_install,
    windows_install_status, _generation as _install_generation,
)
from jev_integration_evaluator.windows_template_session import (
    create_windows_template_session, launch_windows_template_session,
    stop_windows_template_session, windows_session_status,
)
from test_template_python_entrypoint import _prepared


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wheel_name(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        name = next(name for name in archive.namelist()
                    if name.endswith('.dist-info/METADATA'))
        return BytesParser().parsebytes(archive.read(name))['Name']


def _request(tmp_path, *, version='1.0.0', ready=False):
    wheelhouse = os.environ.get('JEV_WINDOWS_TEMPLATE_WHEELHOUSE')
    if not wheelhouse:
        pytest.skip('Explicit native Windows offline wheelhouse required')
    wheelhouse = Path(wheelhouse)
    assert wheelhouse.is_dir()
    tools = {name: __import__('importlib').metadata.version(name)
             for name in ('setuptools', 'wheel')}
    target, template_request, binding = _prepared(tmp_path, tag='windows_delivery')
    project = target / 'pyproject.toml'
    source = project.read_text(encoding='utf-8').replace(
        'requires = ["setuptools>=68"]',
        'requires = ["setuptools==' + tools['setuptools'] + '", "wheel==' +
        tools['wheel'] + '"]')
    if version != '1.0.0':
        source = source.replace('version = "1.0.0"', f'version = "{version}"')
    project.write_text(source, encoding='utf-8')
    if ready:
        entry = target / 'atlas_pkg' / 'console.py'
        entry_source = entry.read_text(encoding='utf-8').replace(
            'def options():\n    global CLIENT\n',
            'def options():\n    global CLIENT\n'
            '    Path(os.environ["JEV_FIXTURE_READY"]).write_bytes(b"entry-ready\\n")\n'
            '    import time\n'
            '    deadline = time.monotonic() + 180\n'
            '    while not Path(os.environ["JEV_FIXTURE_RELEASE"]).is_file() and time.monotonic() < deadline:\n'
            '        time.sleep(0.02)\n'
            '    if not Path(os.environ["JEV_FIXTURE_RELEASE"]).is_file():\n'
            '        raise RuntimeError("ready observation timeout")\n')
        entry.write_text(entry_source, encoding='utf-8')
    prepared = prepare_template_binding(target, template_request, binding)
    spec = prepared['request']['implementation_spec']
    template = tmp_path / 'template'
    materialize_template(target, prepared['request'], template)
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, template_request['reviewed_inventory'],
                                  spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                   baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    source_files = {p.relative_to(target).as_posix(): _hash(p) for p in target.rglob('*')
                    if p.is_file() and not any(part in
                    {'.git', '.pytest_cache', '__pycache__', 'build', 'dist'}
                    for part in p.relative_to(target).parts[:-1])}
    wheels = {p.name: _hash(p) for p in wheelhouse.glob('*.whl')}
    output = tmp_path / 'packages'; output.mkdir()
    environments = tmp_path / 'environments'; environments.mkdir()
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    request = {'host_root': str(target), 'reviewed_source_files': source_files,
               'implementation_bundle': str(bundle),
               'trusted_modified_receipt_sha256': modified['receipt_sha256'],
               'template_directory': str(template), 'wheelhouse': str(wheelhouse),
               'reviewed_wheels': wheels, 'output_parent': str(output),
               'environment_parent': str(environments),
               'console_script': binding['script'], 'interpreter': sys.executable,
               'configuration': config, 'reviewed_configuration_sha256': digest(config)}
    return request, applied, target, bundle, spec


def _make_dangling_junction(root: Path, tmp_path: Path, label: str) -> Path:
    unrelated = tmp_path / (label + '-unrelated')
    unrelated.mkdir()
    (unrelated / 'preserve.txt').write_text('unrelated\n', encoding='utf-8')
    created = subprocess.run(['cmd', '/c', 'mklink', '/J', str(root), str(unrelated)],
                             capture_output=True, text=True, timeout=10)
    assert created.returncode == 0, created.stderr
    retained = tmp_path / (label + '-retained')
    unrelated.rename(retained)
    assert os.path.lexists(root) and not root.exists()
    return retained


@contextmanager
def _deny_sharing(path: Path):
    """Hold a real Win32 file handle that denies all concurrent opens."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        assert kernel.CloseHandle(handle)


def test_native_locked_install_config_blocks_status_replay_and_session(tmp_path):
    request, _, _, _, _ = _request(tmp_path)
    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    root = _install_generation(install_plan)
    config = root / 'config.json'
    original = config.read_bytes()
    unrelated = tmp_path / 'unrelated.txt'
    unrelated.write_bytes(b'preserve unrelated bytes\n')
    assert windows_install_status(
        install_plan, trusted_receipt_sha256=installed['receipt_sha256'])['status'] == 'installed_recorded'

    session_dir = tmp_path / 'blocked-session'
    with _deny_sharing(config):
        with pytest.raises(InputError, match='windows_install_status_unavailable'):
            windows_install_status(
                install_plan, trusted_receipt_sha256=installed['receipt_sha256'])
        with pytest.raises(InputError, match='windows_install_existing_generation_requires_status_review'):
            install_windows_template_package(
                install_plan, approved_plan_sha256=install_plan['plan_sha256'])
        with pytest.raises(InputError, match='windows_install_status_unavailable'):
            create_windows_template_session(
                session_dir, install_plan, installed,
                trusted_install_receipt_sha256=installed['receipt_sha256'])
        assert not session_dir.exists()
        assert unrelated.read_bytes() == b'preserve unrelated bytes\n'

    assert config.read_bytes() == original
    assert windows_install_status(
        install_plan, trusted_receipt_sha256=installed['receipt_sha256']) == {
            'status': 'installed_recorded', 'receipt_trust': 'externally_anchored',
            'receipt_sha256': installed['receipt_sha256']}
    assert unrelated.read_bytes() == b'preserve unrelated bytes\n'


def test_native_installed_hardlink_blocks_status_and_session(tmp_path):
    request, _, _, _, _ = _request(tmp_path)
    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    source = _install_generation(install_plan) / 'venv' / 'Lib' / 'site-packages' / 'atlas_pkg' / 'console.py'
    assert source.is_file() and source.stat().st_nlink == 1
    outside = tmp_path / 'outside-hardlink.py'
    os.link(source, outside)
    assert source.stat().st_nlink == 2
    try:
        with pytest.raises(InputError, match='windows_install_status_unavailable'):
            windows_install_status(
                install_plan, trusted_receipt_sha256=installed['receipt_sha256'])
        with pytest.raises(InputError, match='windows_install_status_unavailable'):
            create_windows_template_session(
                tmp_path / 'blocked-hardlink-session', install_plan, installed,
                trusted_install_receipt_sha256=installed['receipt_sha256'])
        assert not (tmp_path / 'blocked-hardlink-session').exists()
    finally:
        outside.unlink()
    assert source.stat().st_nlink == 1
    assert windows_install_status(
        install_plan, trusted_receipt_sha256=installed['receipt_sha256'])['status'] == 'installed_recorded'


def test_native_dangling_generation_junction_blocks_status_and_replay(tmp_path):
    request, _, _, _, _ = _request(tmp_path)
    plan = plan_windows_template_package(request)
    package_root = _package_generation(plan)
    retained_package = _make_dangling_junction(package_root, tmp_path, 'package')
    try:
        with pytest.raises(InputError, match='windows_owned_generation_reparse'):
            windows_package_status(plan)
        with pytest.raises(InputError, match='windows_owned_generation_reparse'):
            build_windows_template_package(plan,
                                           approved_plan_sha256=plan['plan_sha256'])
        assert (retained_package / 'preserve.txt').read_text() == 'unrelated\n'
    finally:
        package_root.rmdir()

    package = build_windows_template_package(plan,
                                             approved_plan_sha256=plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    install_root = _install_generation(install_plan)
    retained_install = _make_dangling_junction(install_root, tmp_path, 'install')
    try:
        with pytest.raises(InputError, match='windows_owned_generation_reparse'):
            windows_install_status(install_plan)
        with pytest.raises(InputError, match='windows_owned_generation_reparse'):
            install_windows_template_package(
                install_plan, approved_plan_sha256=install_plan['plan_sha256'])
        assert (retained_install / 'preserve.txt').read_text() == 'unrelated\n'
    finally:
        install_root.rmdir()


def test_native_offline_package_install_and_normal_console(tmp_path):
    request, applied, target, bundle, spec = _request(tmp_path)
    plan = plan_windows_template_package(request)
    assert plan['inputs']['entry_point'] == 'atlas_pkg.console:main'
    assert windows_package_status(plan)['status'] == 'absent'
    package = build_windows_template_package(plan,
                                             approved_plan_sha256=plan['plan_sha256'])
    assert windows_package_status(plan, trusted_receipt_sha256=
                                  package['receipt_sha256'])['receipt_trust'] == 'externally_anchored'
    forged_root = tmp_path / 'forged-package'
    (forged_root / 'dist').mkdir(parents=True)
    original_wheel = Path(package['package_directory']) / 'dist' / package['wheel_filename']
    forged_wheel = forged_root / 'dist' / package['wheel_filename']
    forged_wheel.write_bytes(original_wheel.read_bytes() + b'\nsubstituted wheel bytes')
    assert _wheel_name(forged_wheel) == _wheel_name(original_wheel)
    forged_package = copy.deepcopy(package)
    forged_package['package_directory'] = str(forged_root)
    forged_package['wheel_sha256'] = _hash(forged_wheel)
    assert forged_package['receipt_sha256'] == package['receipt_sha256']
    with pytest.raises(InputError, match='windows_install_package_unverified'):
        plan_windows_template_install(
            plan, forged_package, trusted_package_receipt_sha256=package['receipt_sha256'])
    install_plan = plan_windows_template_install(
        plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    assert windows_install_status(install_plan)['status'] == 'absent'
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert windows_install_status(install_plan, trusted_receipt_sha256=
                                  installed['receipt_sha256'])['status'] == 'installed_recorded'
    forged_install = copy.deepcopy(installed)
    forged_install['installed']['python'] = sys.executable
    forged_install['installed']['python_sha256'] = _hash(Path(sys.executable))
    forged_install['installed']['console_script'] = sys.executable
    forged_install['installed']['console_script_sha256'] = _hash(Path(sys.executable))
    assert forged_install['receipt_sha256'] == installed['receipt_sha256']
    forged_session_dir = tmp_path / 'forged-session'
    with pytest.raises(InputError, match='windows_session_install_receipt_substituted'):
        create_windows_template_session(
            forged_session_dir, install_plan, forged_install,
            trusted_install_receipt_sha256=installed['receipt_sha256'])
    assert not forged_session_dir.exists()
    marker = __import__('jev_integration_evaluator.integrations.recipes',
                        fromlist=['host_lifecycle_marker']).host_lifecycle_marker(
                            spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    record = tmp_path / 'record.json'
    session = create_windows_template_session(
        tmp_path / 'session', install_plan, installed,
        trusted_install_receipt_sha256=installed['receipt_sha256'],
        launch_environment={'JEV_FIXTURE_RECORD': str(record),
                            'JEV_FIXTURE_MARKER': marker})
    assert windows_session_status(session)['status'] == 'created'
    identity = launch_windows_template_session(
        session, install_plan, approved_session_sha256=session['session_sha256'])
    assert identity['pid'] > 0
    with pytest.raises(InputError, match='launch_already_attempted'):
        launch_windows_template_session(
            session, install_plan, approved_session_sha256=session['session_sha256'])
    import time
    deadline = time.monotonic() + 30
    while not record.is_file() and time.monotonic() < deadline:
        time.sleep(.05)
    assert record.is_file()
    status = windows_session_status(session,
                                    trusted_identity_sha256=identity['identity_sha256'])
    assert status['receipt_trust'] == 'externally_anchored'
    stopped = stop_windows_template_session(session,
                                             approved_identity_sha256=identity['identity_sha256'])
    assert not stopped['process_alive']
    added = Path(installed['installed']['python']).parents[1] / 'Lib' / 'site-packages' / 'sitecustomize.py'
    added.write_text('raise RuntimeError("unreviewed")\n', encoding='utf-8')
    with pytest.raises(InputError, match='tree_drift'):
        windows_install_status(install_plan,
                               trusted_receipt_sha256=installed['receipt_sha256'])


def test_native_interrupted_launch_retains_identity_and_refuses_replay(tmp_path, monkeypatch):
    """Exercise actual gated children across three durable launch boundaries."""
    import time
    from jev_integration_evaluator import windows_template_session as native
    from jev_integration_evaluator.windows_template_owned import read_private_json
    from jev_integration_evaluator.integrations.recipes import host_lifecycle_marker

    request, _, _, _, spec = _request(tmp_path, ready=True)
    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    marker = host_lifecycle_marker(
        spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    unrelated_file = tmp_path / 'unrelated.txt'
    unrelated_file.write_bytes(b'preserve unrelated work\n')
    unrelated = subprocess.Popen(
        [sys.executable, '-I', '-c', 'import time; time.sleep(600)'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW)
    original_write = native.write_private_json_exclusive
    try:
        for boundary in ('launch-intent.json', 'launch-identity.json',
                         'launch-released.json'):
            label = boundary.removesuffix('.json')
            ready = tmp_path / (label + '-ready.txt')
            effect = tmp_path / (label + '-effect.json')
            release = tmp_path / (label + '-host-release.txt')
            session = create_windows_template_session(
                tmp_path / label, install_plan, installed,
                trusted_install_receipt_sha256=installed['receipt_sha256'],
                launch_environment={'JEV_FIXTURE_RECORD': str(effect),
                                    'JEV_FIXTURE_MARKER': marker,
                                    'JEV_FIXTURE_READY': str(ready),
                                    'JEV_FIXTURE_RELEASE': str(release)})
            identity = None
            try:
                def interrupt(owned, name, value):
                    if name == boundary:
                        # Intent and identity have reached durable storage. The
                        # release token precedes its receipt, so interrupt before
                        # that write to retain the real uncertain-launch state.
                        if name != 'launch-released.json':
                            original_write(owned, name, value)
                        raise RuntimeError('injected durable launch interruption')
                    return original_write(owned, name, value)

                with monkeypatch.context() as patch:
                    patch.setattr(native, 'write_private_json_exclusive', interrupt)
                    with pytest.raises(RuntimeError, match='durable launch interruption'):
                        launch_windows_template_session(
                            session, install_plan,
                            approved_session_sha256=session['session_sha256'])
                owned = session['owned_directory']
                root = Path(owned['path'])
                intent_before = (root / 'launch-intent.json').read_bytes()
                assert not (root / 'launch-released.json').exists()
                if (root / 'launch-identity.json').exists():
                    identity = read_private_json(owned, 'launch-identity.json')
                    deadline = time.monotonic() + 30
                    if boundary == 'launch-released.json':
                        while not ready.exists() and time.monotonic() < deadline:
                            time.sleep(.05)
                        assert ready.read_bytes() == b'entry-ready\n'
                        assert windows_session_status(session)['process_alive']
                    else:
                        while windows_session_status(session)['process_alive'] and time.monotonic() < deadline:
                            time.sleep(.05)
                        assert not windows_session_status(session)['process_alive']
                        assert not ready.exists()
                else:
                    assert boundary == 'launch-intent.json'
                    assert not ready.exists()
                assert windows_session_status(session)['status'] == 'blocked_recovery'
                assert not effect.exists() and not release.exists()
                with pytest.raises(InputError, match='launch_already_attempted'):
                    launch_windows_template_session(
                        session, install_plan,
                        approved_session_sha256=session['session_sha256'])
                assert (root / 'launch-intent.json').read_bytes() == intent_before
                assert not effect.exists() and not release.exists()
            finally:
                if identity is None:
                    owned = session['owned_directory']
                    if (Path(owned['path']) / 'launch-identity.json').exists():
                        identity = read_private_json(owned, 'launch-identity.json')
                if identity is not None:
                    stopped = stop_windows_template_session(
                        session, approved_identity_sha256=identity['identity_sha256'])
                    assert not stopped['process_alive']
                    assert stopped['status'] == 'blocked_recovery'
            assert unrelated.poll() is None
            assert unrelated_file.read_bytes() == b'preserve unrelated work\n'
        assert windows_install_status(
            install_plan, trusted_receipt_sha256=installed['receipt_sha256'])['status'] == 'installed_recorded'
    finally:
        if unrelated.poll() is None:
            unrelated.terminate()
        unrelated.wait(timeout=10)


def _wait_until(condition, seconds: float) -> bool:
    """Bounded poll; the caller asserts the returned final observation."""
    import time
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(.05)
    return bool(condition())


def _installed_ready_session(tmp_path):
    """Install the entry-gated fixture and record one off-mode session."""
    from jev_integration_evaluator.integrations.recipes import host_lifecycle_marker

    request, _, _, _, spec = _request(tmp_path, ready=True)
    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    marker = host_lifecycle_marker(
        spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    ready = tmp_path / 'entry-ready.txt'
    effect = tmp_path / 'effect.json'
    release = tmp_path / 'host-release.txt'
    session = create_windows_template_session(
        tmp_path / 'session', install_plan, installed,
        trusted_install_receipt_sha256=installed['receipt_sha256'],
        launch_environment={'JEV_FIXTURE_RECORD': str(effect),
                            'JEV_FIXTURE_MARKER': marker,
                            'JEV_FIXTURE_READY': str(ready),
                            'JEV_FIXTURE_RELEASE': str(release)})
    return install_plan, installed, session, ready, effect, release


def _process_present(row: dict) -> bool:
    """True while the exact recorded process (PID and creation time) still runs."""
    import ctypes
    from jev_integration_evaluator import windows_template_session as native

    kernel = native._kernel()
    handle = kernel.OpenProcess(0x101000, False, row['pid'])
    if not handle:
        # Only "no such process" proves absence; any other failure is uncertain.
        return ctypes.get_last_error() not in (87, 1168)
    try:
        if kernel.WaitForSingleObject(handle, 0) == 0:
            return False
        try:
            return native._identity(handle, kernel)[0] == row['created_filetime']
        except InputError:
            return True
    finally:
        kernel.CloseHandle(handle)


def test_native_refused_replay_leaves_owned_job_members_unchanged(tmp_path):
    from jev_integration_evaluator.windows_template_session import _job_members

    install_plan, _, session, ready, effect, release = _installed_ready_session(tmp_path)
    root = Path(session['owned_directory']['path'])
    identity = launch_windows_template_session(
        session, install_plan, approved_session_sha256=session['session_sha256'])
    try:
        assert _wait_until(ready.is_file, 30)
        count, members = _job_members(identity)
        assert count == len(members) >= 2
        assert any(row['pid'] == identity['pid'] for row in members)
        assert any(row['pid'] != identity['pid'] for row in members)
        records = {name: (root / name).read_bytes() for name in (
            'session.json', 'launch-intent.json', 'launch-identity.json',
            'launch-released.json')}
        running = {'status': 'running', 'process_alive': True,
                   'receipt_trust': 'externally_anchored',
                   'identity_sha256': identity['identity_sha256']}
        assert windows_session_status(
            session, trusted_identity_sha256=identity['identity_sha256']) == running
        for _ in range(3):
            with pytest.raises(InputError, match='^windows_session_launch_already_attempted$'):
                launch_windows_template_session(
                    session, install_plan, approved_session_sha256=session['session_sha256'])
            # The exact named Job holds the same processes: no duplicate gate,
            # guardian-assigned member or console was started by the refusal.
            assert _job_members(identity) == (count, members)
            assert all(_process_present(row) for row in members)
        assert {name: (root / name).read_bytes() for name in records} == records
        assert not (root / 'stop-intent.json').exists()
        assert windows_session_status(
            session, trusted_identity_sha256=identity['identity_sha256']) == running
        assert ready.read_bytes() == b'entry-ready\n'
        assert not effect.exists() and not release.exists()
    finally:
        stopped = stop_windows_template_session(
            session, approved_identity_sha256=identity['identity_sha256'])
        assert not stopped['process_alive']
    assert stopped['status'] == 'stopped'
    assert _wait_until(lambda: not any(_process_present(row) for row in members), 15)
    with pytest.raises(InputError, match='^windows_session_launch_already_attempted$'):
        launch_windows_template_session(
            session, install_plan, approved_session_sha256=session['session_sha256'])
    assert not any(_process_present(row) for row in members)


def test_native_install_config_content_drift_blocks_status_session_and_launch(tmp_path):
    import json
    from jev_integration_evaluator.windows_template_owned import acl_sha256

    request, _, _, _, _ = _request(tmp_path)
    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    recorded = {'status': 'installed_recorded', 'receipt_trust': 'externally_anchored',
                'receipt_sha256': installed['receipt_sha256']}
    assert windows_install_status(
        install_plan, trusted_receipt_sha256=installed['receipt_sha256']) == recorded
    config = _install_generation(install_plan) / 'config.json'
    original = config.read_bytes()
    config_acl = acl_sha256(config)
    config_identity = (config.stat().st_dev, config.stat().st_ino)
    unrelated = tmp_path / 'unrelated.txt'
    unrelated.write_bytes(b'preserve unrelated bytes\n')
    # This session is recorded while the installed configuration is exact.
    session = create_windows_template_session(
        tmp_path / 'created-before-drift', install_plan, installed,
        trusted_install_receipt_sha256=installed['receipt_sha256'])
    session_root = Path(session['owned_directory']['path'])
    created = {'status': 'created', 'process_alive': False, 'receipt_trust': 'absent'}
    assert windows_session_status(session) == created
    drifted = (json.dumps({'jev_runtime': {'mode': 'shadow', 'credential_ref': None}},
                          sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    assert json.loads(original) == request['configuration'] != json.loads(drifted)
    blocked = tmp_path / 'blocked-after-drift'
    try:
        # Rewrite the content in place: same file identity, owner and DACL.
        with open(config, 'r+b') as stream:
            stream.write(drifted)
            stream.truncate()
        assert config.read_bytes() == drifted
        assert acl_sha256(config) == config_acl
        assert (config.stat().st_dev, config.stat().st_ino) == config_identity
        for trusted in (installed['receipt_sha256'], None):
            with pytest.raises(InputError, match='^windows_install_configuration_drift$'):
                windows_install_status(install_plan, trusted_receipt_sha256=trusted)
        with pytest.raises(InputError, match='windows_install_existing_generation_requires_status_review'):
            install_windows_template_package(
                install_plan, approved_plan_sha256=install_plan['plan_sha256'])
        with pytest.raises(InputError, match='^windows_install_configuration_drift$'):
            create_windows_template_session(
                blocked, install_plan, installed,
                trusted_install_receipt_sha256=installed['receipt_sha256'])
        assert not blocked.exists()
        with pytest.raises(InputError, match='^windows_install_configuration_drift$'):
            launch_windows_template_session(
                session, install_plan, approved_session_sha256=session['session_sha256'])
        assert not (session_root / 'launch-intent.json').exists()
        assert sorted(entry.name for entry in session_root.iterdir()) == [
            'delivery.lock', 'session.json']
        assert windows_session_status(session) == created
        # Refusal is read-only: the drifted bytes are neither repaired nor replaced.
        assert config.read_bytes() == drifted
        assert unrelated.read_bytes() == b'preserve unrelated bytes\n'
    finally:
        with open(config, 'r+b') as stream:
            stream.write(original)
            stream.truncate()
    assert config.read_bytes() == original and acl_sha256(config) == config_acl
    assert windows_install_status(
        install_plan, trusted_receipt_sha256=installed['receipt_sha256']) == recorded
    assert windows_session_status(session) == created
    assert unrelated.read_bytes() == b'preserve unrelated bytes\n'


def test_native_unsupported_roots_block_package_and_install_planning_without_effect(
        tmp_path, monkeypatch):
    from jev_integration_evaluator import capabilities as cap
    from test_windows_template_preflight import (
        _UNSUPPORTED_VOLUMES, _VolumeAnswer, _administrative_share,
    )

    request, _, _, _, _ = _request(tmp_path)
    output = Path(request['output_parent'])
    environments = Path(request['environment_parent'])
    for key in ('host_root', 'wheelhouse', 'output_parent', 'environment_parent',
                'implementation_bundle', 'template_directory'):
        changed = dict(request)
        changed[key] = _administrative_share(Path(request[key]))
        with pytest.raises(InputError, match='^windows_package_unsupported_unc_path$'):
            plan_windows_template_package(changed)
    assert not list(output.iterdir()) and not list(environments.iterdir())

    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    built = {'status': 'built_recorded', 'receipt_trust': 'externally_anchored',
             'receipt_sha256': package['receipt_sha256']}
    assert windows_package_status(
        package_plan, trusted_receipt_sha256=package['receipt_sha256']) == built
    package_root = _package_generation(package_plan)
    package_entries = sorted(entry.name for entry in package_root.iterdir())
    receipt_bytes = (package_root / 'package-receipt.json').read_bytes()
    ctypes_module, wintypes, kernel = cap._windows_api()
    for drive_type, filesystem, reason in _UNSUPPORTED_VOLUMES:
        answer = _VolumeAnswer(kernel, drive_type, filesystem)
        with monkeypatch.context() as patch:
            # Every drive now reports as mapped or non-NTFS for each stage.
            patch.setattr(cap, '_windows_api', lambda: (ctypes_module, wintypes, answer))
            with pytest.raises(InputError, match='^windows_package_' + reason + '$'):
                plan_windows_template_package(request)
            with pytest.raises(InputError, match='^windows_package_' + reason + '$'):
                build_windows_template_package(
                    package_plan, approved_plan_sha256=package_plan['plan_sha256'])
            with pytest.raises(InputError, match='^windows_owned_generation_parent_unavailable$'):
                windows_package_status(
                    package_plan, trusted_receipt_sha256=package['receipt_sha256'])
            with pytest.raises(InputError, match='^windows_owned_generation_parent_unavailable$'):
                plan_windows_template_install(
                    package_plan, package,
                    trusted_package_receipt_sha256=package['receipt_sha256'])
            with pytest.raises(InputError, match='^windows_owned_generation_parent_unavailable$'):
                install_windows_template_package(
                    install_plan, approved_plan_sha256=install_plan['plan_sha256'])
            with pytest.raises(InputError, match='^windows_owned_generation_parent_unavailable$'):
                windows_install_status(install_plan)
        assert not list(environments.iterdir())
        assert sorted(entry.name for entry in package_root.iterdir()) == package_entries
        assert (package_root / 'package-receipt.json').read_bytes() == receipt_bytes
    assert windows_install_status(install_plan) == {'status': 'absent',
                                                    'receipt_trust': 'absent'}
    assert windows_package_status(
        package_plan, trusted_receipt_sha256=package['receipt_sha256']) == built


def test_native_generation_acl_denial_blocks_build_and_install_fail_closed(
        tmp_path, monkeypatch):
    from jev_integration_evaluator import windows_template_install as install
    from test_windows_source_mutation import _allow, _deny

    request, _, _, _, _ = _request(tmp_path)
    output = Path(request['output_parent'])
    environments = Path(request['environment_parent'])
    package_plan = plan_windows_template_package(request)
    absent = {'status': 'absent', 'receipt_trust': 'absent'}

    # 1. The package output parent denies new subdirectories to this account.
    account = _deny(output, '(AD)')
    try:
        with pytest.raises(InputError, match='^windows_owned_directory_create_failed$'):
            build_windows_template_package(
                package_plan, approved_plan_sha256=package_plan['plan_sha256'])
        assert not list(output.iterdir())
    finally:
        _allow(output, account)
    assert windows_package_status(package_plan) == absent
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])

    # 2. The environment parent denies the owned generation directory itself.
    account = _deny(environments, '(AD)')
    try:
        with pytest.raises(InputError, match='^windows_owned_directory_create_failed$'):
            install_windows_template_package(
                install_plan, approved_plan_sha256=install_plan['plan_sha256'])
        assert not list(environments.iterdir())
    finally:
        _allow(environments, account)
    assert windows_install_status(install_plan) == absent

    # 3. The exclusively created generation gains a deny-write ACE before its
    #    first owner record. The owner DACL no longer matches, so nothing is
    #    written and the retained directory blocks status and replay.
    root = _install_generation(install_plan)
    real_write = install.write_private_json_exclusive
    denied = []

    def deny_before_first_record(owned, name, value):
        if not denied:
            assert name == 'owner.json' and Path(owned['path']) == root
            denied.append(_deny(root, '(WD,AD)'))
        return real_write(owned, name, value)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(install, 'write_private_json_exclusive', deny_before_first_record)
            with pytest.raises(InputError, match='^windows_owned_directory_changed$'):
                install_windows_template_package(
                    install_plan, approved_plan_sha256=install_plan['plan_sha256'])
        assert len(denied) == 1
        assert [entry.name for entry in root.iterdir()] == ['delivery.lock']
        with pytest.raises(InputError, match='^windows_install_status_unavailable$'):
            windows_install_status(install_plan)
        with pytest.raises(InputError, match='windows_install_existing_generation_requires_status_review'):
            install_windows_template_package(
                install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    finally:
        for account in denied:
            _allow(root, account)
    # Removing the ACE does not turn the incomplete generation into a replay.
    assert [entry.name for entry in root.iterdir()] == ['delivery.lock']
    assert [entry.name for entry in environments.iterdir()] == [root.name]
    with pytest.raises(InputError, match='windows_install_existing_generation_requires_status_review'):
        install_windows_template_package(
            install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert windows_package_status(
        package_plan, trusted_receipt_sha256=package['receipt_sha256'])['status'] == 'built_recorded'


_CONSOLE_BREAK = """import ctypes,sys,time
from ctypes import wintypes
k=ctypes.WinDLL('kernel32',use_last_error=True)
H=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.DWORD)
keep=H(lambda kind: True)
k.SetConsoleCtrlHandler.argtypes=(H,wintypes.BOOL)
k.FreeConsole()
if not k.AttachConsole(int(sys.argv[1])): sys.exit(41)
if not k.SetConsoleCtrlHandler(keep,True): sys.exit(43)
if not k.GenerateConsoleCtrlEvent(1,0): sys.exit(42)
time.sleep(.2)
sys.exit(0)"""


def test_native_console_break_cancellation_leaves_no_owned_process(tmp_path):
    """CTRL_BREAK_EVENT reaches only the owned console's own process group."""
    from jev_integration_evaluator.windows_template_session import _job_members

    install_plan, installed, session, ready, effect, release = _installed_ready_session(tmp_path)
    unrelated_file = tmp_path / 'unrelated.txt'
    unrelated_file.write_bytes(b'preserve unrelated work\n')
    unrelated = subprocess.Popen(
        [sys.executable, '-I', '-c', 'import time; time.sleep(600)'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW)
    identity = None
    try:
        identity = launch_windows_template_session(
            session, install_plan, approved_session_sha256=session['session_sha256'])
        assert _wait_until(ready.is_file, 30)
        count, members = _job_members(identity)
        assert count == len(members) >= 2
        assert any(row['pid'] != identity['pid'] for row in members)
        guardian = {'pid': identity['guardian_pid'],
                    'created_filetime': identity['guardian_created_filetime']}
        assert _process_present(guardian)
        # The gate was started without a window on a private console that this
        # test does not share. A helper joins that console, ignores the event
        # itself and raises CTRL_BREAK_EVENT (1) for the console's process group.
        sent = subprocess.run(
            [sys._base_executable, '-I', '-S', '-c', _CONSOLE_BREAK, str(identity['pid'])],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW)
        assert sent.returncode == 0
        assert _wait_until(
            lambda: not windows_session_status(session)['process_alive'], 15)
        assert _wait_until(
            lambda: not any(_process_present(row) for row in members), 15)
        assert _wait_until(lambda: not _process_present(guardian), 15)
        # With no member and no guardian handle the exact named Job is gone.
        with pytest.raises(InputError, match='^windows_session_observation_job_unavailable$'):
            _job_members(identity)
        # Exit by cancellation is never reported as a verified or stopped run.
        assert windows_session_status(
            session, trusted_identity_sha256=identity['identity_sha256']) == {
                'status': 'exited_unverified', 'process_alive': False,
                'receipt_trust': 'externally_anchored',
                'identity_sha256': identity['identity_sha256']}
        assert ready.read_bytes() == b'entry-ready\n'
        assert not effect.exists() and not release.exists()
        root = Path(session['owned_directory']['path'])
        assert not (root / 'stop-intent.json').exists()
        with pytest.raises(InputError, match='^windows_session_launch_already_attempted$'):
            launch_windows_template_session(
                session, install_plan, approved_session_sha256=session['session_sha256'])
        stopped = stop_windows_template_session(
            session, approved_identity_sha256=identity['identity_sha256'])
        assert stopped == {'status': 'stopped', 'process_alive': False,
                           'receipt_trust': 'externally_anchored',
                           'identity_sha256': identity['identity_sha256']}
        assert not any(_process_present(row) for row in members)
        assert not effect.exists() and not release.exists()
        assert unrelated.poll() is None
        assert unrelated_file.read_bytes() == b'preserve unrelated work\n'
        assert windows_install_status(
            install_plan, trusted_receipt_sha256=installed['receipt_sha256'])['status'] == 'installed_recorded'
    finally:
        try:
            if identity is not None:
                stopped = stop_windows_template_session(
                    session, approved_identity_sha256=identity['identity_sha256'])
                assert not stopped['process_alive']
        finally:
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=10)


def test_native_install_config_byte_drift_blocks_status_session_and_launch(tmp_path):
    """Bytes that parse to the reviewed configuration are still not the installed file."""
    import json
    from jev_integration_evaluator.windows_template_owned import acl_sha256

    request, _, _, _, _ = _request(tmp_path)
    package_plan = plan_windows_template_package(request)
    package = build_windows_template_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = plan_windows_template_install(
        package_plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    recorded = {'status': 'installed_recorded', 'receipt_trust': 'externally_anchored',
                'receipt_sha256': installed['receipt_sha256']}
    assert windows_install_status(
        install_plan, trusted_receipt_sha256=installed['receipt_sha256']) == recorded
    config = _install_generation(install_plan) / 'config.json'
    original = config.read_bytes()
    reviewed = request['configuration']
    assert original == b'{"jev_runtime":{"credential_ref":null,"mode":"off"}}\n'
    config_acl = acl_sha256(config)
    config_identity = (config.stat().st_dev, config.stat().st_ino)
    session = create_windows_template_session(
        tmp_path / 'created-before-drift', install_plan, installed,
        trusted_install_receipt_sha256=installed['receipt_sha256'])
    session_root = Path(session['owned_directory']['path'])
    created = {'status': 'created', 'process_alive': False, 'receipt_trust': 'absent'}
    assert windows_session_status(session) == created
    variants = {
        'no-trailing-newline': original[:-1],
        'extra-trailing-newline': original + b'\n',
        'crlf-line-ending': original[:-1] + b'\r\n',
        'whitespace': (json.dumps(reviewed, sort_keys=True) + '\n').encode('utf-8'),
        'key-order': b'{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
        'duplicate-key': b'{"jev_runtime":{"credential_ref":null,"mode":"shadow","mode":"off"}}\n',
    }
    complete = ('no-trailing-newline', 'whitespace')
    assert set(complete) <= set(variants)
    try:
        for label, drifted in variants.items():
            # Every variant is a different file that a JSON parser reads as
            # the same reviewed configuration.
            assert drifted != original and json.loads(drifted) == reviewed, label
            with open(config, 'r+b') as stream:
                stream.write(drifted)
                stream.truncate()
            assert config.read_bytes() == drifted
            assert acl_sha256(config) == config_acl
            assert (config.stat().st_dev, config.stat().st_ino) == config_identity
            with pytest.raises(InputError, match='^windows_install_configuration_drift$'):
                windows_install_status(
                    install_plan, trusted_receipt_sha256=installed['receipt_sha256'])
            if label in complete:
                # Each further entry repeats the full installed-byte review,
                # so two representative variants bound this case's duration.
                with pytest.raises(InputError, match='^windows_install_configuration_drift$'):
                    windows_install_status(install_plan)
                blocked = tmp_path / ('blocked-' + label)
                with pytest.raises(InputError, match='^windows_install_configuration_drift$'):
                    create_windows_template_session(
                        blocked, install_plan, installed,
                        trusted_install_receipt_sha256=installed['receipt_sha256'])
                assert not blocked.exists()
                with pytest.raises(InputError, match='^windows_install_configuration_drift$'):
                    launch_windows_template_session(
                        session, install_plan,
                        approved_session_sha256=session['session_sha256'])
                assert sorted(entry.name for entry in session_root.iterdir()) == [
                    'delivery.lock', 'session.json']
                assert windows_session_status(session) == created
            # Refusal is read-only: the drifted bytes are not repaired.
            assert config.read_bytes() == drifted
    finally:
        with open(config, 'r+b') as stream:
            stream.write(original)
            stream.truncate()
    assert config.read_bytes() == original and acl_sha256(config) == config_acl
    assert windows_install_status(
        install_plan, trusted_receipt_sha256=installed['receipt_sha256']) == recorded
    assert windows_session_status(session) == created


def _supervised_off_console_run(directory: Path, install_plan: dict, installed: dict,
                                marker: str) -> None:
    """Launch one recorded off-mode console, observe its effect and stop it."""
    record = directory.with_name(directory.name + '-effect.json')
    session = create_windows_template_session(
        directory, install_plan, installed,
        trusted_install_receipt_sha256=installed['receipt_sha256'],
        launch_environment={'JEV_FIXTURE_RECORD': str(record),
                            'JEV_FIXTURE_MARKER': marker})
    identity = launch_windows_template_session(
        session, install_plan, approved_session_sha256=session['session_sha256'])
    try:
        assert _wait_until(record.is_file, 60)
    finally:
        stopped = stop_windows_template_session(
            session, approved_identity_sha256=identity['identity_sha256'])
    assert stopped['status'] == 'stopped' and not stopped['process_alive']


def test_native_locked_package_inputs_block_build_and_install_fail_closed(
        tmp_path, monkeypatch):
    """A handle that shares nothing on a wheel, source file or built wheel."""
    from contextlib import ExitStack
    import shutil
    from jev_integration_evaluator import windows_template_plan as planning

    request, _, target, _, spec = _request(tmp_path)
    # A private copy of the reviewed wheels: the held handles never touch the
    # wheelhouse other tests read.
    wheelhouse = tmp_path / 'private-wheelhouse'
    wheelhouse.mkdir()
    for name in request['reviewed_wheels']:
        shutil.copyfile(Path(request['wheelhouse']) / name, wheelhouse / name)
    request = {**request, 'wheelhouse': str(wheelhouse)}
    output, environments = Path(request['output_parent']), Path(request['environment_parent'])
    names = sorted(request['reviewed_wheels'])
    evaluator = wheelhouse / next(n for n in names if n.startswith('jev_integration_evaluator-'))
    build_tool = wheelhouse / next(n for n in names if n.startswith('setuptools-'))
    dependency = wheelhouse / next(
        n for n in names if not n.startswith(('jev_integration_evaluator-', 'pip-',
                                              'setuptools-', 'wheel-')))
    source_hashes = dict(request['reviewed_source_files'])
    wheel_hashes = dict(request['reviewed_wheels'])
    unrelated = tmp_path / 'unrelated.txt'
    unrelated.write_bytes(b'preserve unrelated bytes\n')

    def unchanged() -> None:
        assert {name: _hash(target.joinpath(*name.split('/')))
                for name in source_hashes} == source_hashes
        assert {name: _hash(wheelhouse / name) for name in wheel_hashes} == wheel_hashes
        assert unrelated.read_bytes() == b'preserve unrelated bytes\n'

    # 1. Package planning: a locked wheel or a locked reviewed source file.
    for locked in (evaluator, dependency, target / 'pyproject.toml',
                   target / 'atlas_pkg' / 'console.py'):
        with _deny_sharing(locked):
            with pytest.raises(PermissionError):
                locked.read_bytes()
            with pytest.raises(InputError, match='^windows_package_access_denied$'):
                plan_windows_template_package(request)
        assert not list(output.iterdir()) and not list(environments.iterdir())
    plan = plan_windows_template_package(request)
    assert windows_package_status(plan) == {'status': 'absent', 'receipt_trust': 'absent'}

    # 2. Build with the wheel already locked: refused before any generation.
    with _deny_sharing(dependency):
        with pytest.raises(InputError, match='^windows_package_access_denied$'):
            build_windows_template_package(plan, approved_plan_sha256=plan['plan_sha256'])
        assert windows_package_status(plan) == {'status': 'absent', 'receipt_trust': 'absent'}
    assert not list(output.iterdir())

    # 3. The lock arrives after the build intent, before the offline tool
    #    install reads the wheel. The partial generation is retained and no
    #    later status or replay accepts it, also after the handle is closed.
    package_root = _package_generation(plan)
    original_write = planning.write_private_bytes_exclusive
    with ExitStack() as held:
        def lock_then_write(owned, name, raw):
            if name == 'build-tools.lock':
                held.enter_context(_deny_sharing(build_tool))
            return original_write(owned, name, raw)

        monkeypatch.setattr(planning, 'write_private_bytes_exclusive', lock_then_write)
        try:
            with pytest.raises(InputError, match='^windows_package_offline_command_failed$'):
                build_windows_template_package(plan, approved_plan_sha256=plan['plan_sha256'])
        finally:
            monkeypatch.setattr(planning, 'write_private_bytes_exclusive', original_write)
        with pytest.raises(PermissionError):
            build_tool.read_bytes()
        assert (package_root / 'build-tools.lock').is_file()
        assert not (package_root / 'package-receipt.json').exists()
        assert not (package_root / 'dist').exists()
        assert windows_package_status(plan) == {
            'status': 'blocked_recovery', 'receipt_trust': 'absent'}
    partial = sorted(entry.name for entry in package_root.iterdir())
    for _ in (1, 2):
        assert windows_package_status(plan) == {
            'status': 'blocked_recovery', 'receipt_trust': 'absent'}
        with pytest.raises(InputError,
                           match='^windows_package_existing_generation_requires_status_review$'):
            build_windows_template_package(plan, approved_plan_sha256=plan['plan_sha256'])
    assert sorted(entry.name for entry in package_root.iterdir()) == partial
    assert [entry.name for entry in output.iterdir()] == [package_root.name]
    assert not list(environments.iterdir())
    unchanged()

    # 4. A separately reviewed output parent builds once nothing is locked.
    retry_output = tmp_path / 'packages-after-lock'
    retry_output.mkdir()
    request = {**request, 'output_parent': str(retry_output)}
    plan = plan_windows_template_package(request)
    package = build_windows_template_package(plan, approved_plan_sha256=plan['plan_sha256'])
    built = {'status': 'built_recorded', 'receipt_trust': 'externally_anchored',
             'receipt_sha256': package['receipt_sha256']}
    assert windows_package_status(
        plan, trusted_receipt_sha256=package['receipt_sha256']) == built

    # 5. Install planning: a locked wheelhouse wheel, then the locked built wheel.
    host_wheel = Path(package['package_directory']) / 'dist' / package['wheel_filename']
    for locked, reason in ((dependency, 'windows_package_access_denied'),
                           (host_wheel, 'windows_package_status_unavailable')):
        with _deny_sharing(locked):
            with pytest.raises(InputError, match='^' + reason + '$'):
                plan_windows_template_install(
                    plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
        assert not list(environments.iterdir())
    install_plan = plan_windows_template_install(
        plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])

    # 6. Install with either input locked: refused before any generation.
    for locked, reason in ((evaluator, 'windows_package_access_denied'),
                           (host_wheel, 'windows_package_status_unavailable')):
        with _deny_sharing(locked):
            with pytest.raises(InputError, match='^' + reason + '$'):
                install_windows_template_package(
                    install_plan, approved_plan_sha256=install_plan['plan_sha256'])
            assert windows_install_status(install_plan) == {
                'status': 'absent', 'receipt_trust': 'absent'}
        assert not list(environments.iterdir())
    assert windows_package_status(
        plan, trusted_receipt_sha256=package['receipt_sha256']) == built
    unchanged()

    # 7. With every handle closed the same plan installs, and the installed
    #    console runs once under the off-mode supervisor.
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert windows_install_status(
        install_plan, trusted_receipt_sha256=installed['receipt_sha256']) == {
            'status': 'installed_recorded', 'receipt_trust': 'externally_anchored',
            'receipt_sha256': installed['receipt_sha256']}
    assert [entry.name for entry in environments.iterdir()] == [
        _install_generation(install_plan).name]
    from jev_integration_evaluator.integrations.recipes import host_lifecycle_marker
    _supervised_off_console_run(
        tmp_path / 'session-after-lock', install_plan, installed,
        host_lifecycle_marker(spec['host_lifecycle'], spec['bindings']['runtime'],
                              spec['candidate_id']))
    # The earlier partial generation is still not accepted.
    assert sorted(entry.name for entry in package_root.iterdir()) == partial
    unchanged()
