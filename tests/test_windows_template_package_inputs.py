"""Native read-only package-input checks, without installer or launch claims."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.windows_template_package_inputs import (
    inspect_windows_template_package_inputs,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path):
    host = tmp_path / 'host'
    host.mkdir()
    (host / 'host_cli.py').write_text('def main():\n    return 0\n', encoding='utf-8')
    (host / 'pyproject.toml').write_text(
        '[build-system]\nrequires=["setuptools==80.0.0", "wheel==0.45.1"]\n'
        'build-backend="setuptools.build_meta"\n'
        '[project]\nname="synthetic-host"\nversion="0.1.0"\n'
        '[project.scripts]\nsynthetic-host="host_cli:main"\n', encoding='utf-8')
    files = {p.name: _sha(p) for p in host.iterdir()}
    wheelhouse = tmp_path / 'wheelhouse'
    wheelhouse.mkdir()
    wheel = wheelhouse / 'synthetic_dep-1.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('synthetic_dep/__init__.py', 'value = 1\n')
        archive.writestr('synthetic_dep-1.0.dist-info/METADATA',
                         'Metadata-Version: 2.1\nName: synthetic-dep\nVersion: 1.0\n')
        archive.writestr('synthetic_dep-1.0.dist-info/WHEEL',
                         'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
        archive.writestr('synthetic_dep-1.0.dist-info/RECORD', '')
    output = tmp_path / 'package-output-parent'; output.mkdir()
    environments = tmp_path / 'environment-parent'; environments.mkdir()
    return host, files, wheelhouse, {wheel.name: _sha(wheel)}, output, environments


def _inspect(values):
    host, files, wheelhouse, wheels, output, environments = values
    return inspect_windows_template_package_inputs(
        host, files, wheelhouse, wheels, output, environments, 'synthetic-host')


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_exact_package_inputs_are_read_only(tmp_path):
    values = _fixture(tmp_path)
    report = _inspect(values)
    assert report['status'] == 'package_inputs_reviewed_only'
    assert report['source_traversal_exclusions'] == [
        '.git', '.pytest_cache', '__pycache__', 'build', 'dist']
    assert report['source_sha256'] == digest(values[1])
    assert report['wheels_sha256'] == digest(values[3])
    assert report['entry_point'] == 'host_cli:main'
    assert report['project_name'] == 'synthetic-host'
    assert report['project_version'] == '0.1.0'
    assert report['build_requirements'] == ['setuptools==80.0.0', 'wheel==0.45.1']
    assert report['interpreter'] == str(Path(sys.executable).absolute())
    assert report['target_modified'] is report['target_executed'] is False
    assert report['build_authorized'] is report['install_authorized'] is report['launch_authorized'] is False
    assert not list(values[4].iterdir()) and not list(values[5].iterdir())


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_traversed_source_completeness_and_drift(tmp_path):
    values = _fixture(tmp_path)
    host = values[0]
    (host / 'unreviewed.py').write_text('x = 1\n', encoding='utf-8')
    with pytest.raises(InputError, match='windows_package_source_manifest_incomplete'):
        _inspect(values)
    (host / 'unreviewed.py').unlink()
    (host / 'host_cli.py').write_text('x = 2\n', encoding='utf-8')
    with pytest.raises(InputError, match='reviewed_windows_package_source_changed'):
        _inspect(values)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_skipped_directory_is_explicitly_outside_inventory(tmp_path):
    values = _fixture(tmp_path)
    skipped = values[0] / 'build'
    skipped.mkdir()
    (skipped / 'unreviewed.py').write_text('value = 1\n', encoding='utf-8')
    report = _inspect(values)
    assert report['source_files'] == values[1]
    assert 'build' in report['source_traversal_exclusions']
    assert report['build_authorized'] is False


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_wheel_drift_and_hardlink_refusal(tmp_path):
    values = _fixture(tmp_path)
    wheel = next(values[2].iterdir())
    alias = values[2] / 'alias.bin'
    os.link(wheel, alias)
    with pytest.raises(InputError, match='windows_package_hardlink_excluded'):
        _inspect(values)
    alias.unlink()
    wheel.write_bytes(wheel.read_bytes() + b'changed')
    with pytest.raises(InputError, match='reviewed_windows_package_wheel_changed'):
        _inspect(values)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_wheel_change_between_passes_is_refused(tmp_path, monkeypatch):
    from jev_integration_evaluator import windows_template_package_inputs as package_inputs

    values = _fixture(tmp_path)
    wheel = next(values[2].iterdir())
    original = package_inputs._wheel_metadata
    count = 0

    def change_after_first_pass(raw, filename):
        nonlocal count
        result = original(raw, filename)
        count += 1
        if count == 1:
            wheel.write_bytes(wheel.read_bytes() + b'changed')
        return result

    monkeypatch.setattr(package_inputs, '_wheel_metadata', change_after_first_pass)
    with pytest.raises(InputError, match='reviewed_windows_package_wheel_changed'):
        _inspect(values)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_wheel_internal_tag_must_match_current_interpreter(tmp_path):
    values = _fixture(tmp_path)
    wheel = next(values[2].iterdir())
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('synthetic_dep-1.0.dist-info/METADATA',
                         'Metadata-Version: 2.1\nName: synthetic-dep\nVersion: 1.0\n')
        archive.writestr('synthetic_dep-1.0.dist-info/WHEEL',
                         'Wheel-Version: 1.0\nTag: cp39-cp39-manylinux_x86_64\n')
        archive.writestr('synthetic_dep-1.0.dist-info/RECORD', '')
    values[3][wheel.name] = _sha(wheel)
    with pytest.raises(InputError, match='windows_package_wheel_tag_unsupported'):
        _inspect(values)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_regular_file_named_build_is_in_traversed_source_map(tmp_path):
    values = _fixture(tmp_path)
    regular = values[0] / 'build'
    regular.write_text('reviewed file\n', encoding='utf-8')
    values[1]['build'] = _sha(regular)
    assert _inspect(values)['source_files']['build'] == values[1]['build']


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_directory_entry_budget(tmp_path, monkeypatch):
    from jev_integration_evaluator import windows_template_package_inputs as package_inputs

    values = _fixture(tmp_path)
    for index in range(3):
        (values[0] / f'empty{index}').mkdir()
    monkeypatch.setattr(package_inputs, '_MAX_DIRECTORY_ENTRIES', 4)
    with pytest.raises(InputError, match='windows_package_source_size_limit'):
        _inspect(values)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_source_acl_denial_has_private_reason(tmp_path):
    values = _fixture(tmp_path)
    source = values[0] / 'host_cli.py'
    principal = subprocess.run(['whoami'], capture_output=True, text=True, timeout=10)
    assert principal.returncode == 0
    identity = principal.stdout.strip()
    denied = subprocess.run(['icacls', str(source), '/deny', identity + ':(RD)'],
                            capture_output=True, text=True, timeout=10)
    if denied.returncode != 0:
        pytest.skip('This account cannot set a disposable file deny ACE')
    try:
        with pytest.raises(InputError, match='windows_package_access_denied'):
            _inspect(values)
    finally:
        restored = subprocess.run(['icacls', str(source), '/remove:d', identity],
                                  capture_output=True, text=True, timeout=10)
        assert restored.returncode == 0, 'Disposable test ACL could not be restored'


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_identical_source_root_replacement_is_refused(tmp_path, monkeypatch):
    from jev_integration_evaluator import windows_template_package_inputs as package_inputs

    values = _fixture(tmp_path)
    root = values[0]
    moved = tmp_path / 'old-host'
    original = package_inputs._source_pass
    count = 0

    def replace_after_pass(*args):
        nonlocal count
        result = original(*args)
        count += 1
        if count == 1:
            root.rename(moved)
            shutil.copytree(moved, root)
        return result

    monkeypatch.setattr(package_inputs, '_source_pass', replace_after_pass)
    with pytest.raises(InputError, match='windows_package_input_root_changed'):
        _inspect(values)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_identical_nested_directory_replacement_is_refused(tmp_path, monkeypatch):
    from jev_integration_evaluator import windows_template_package_inputs as package_inputs

    values = _fixture(tmp_path)
    nested = values[0] / 'pkg'
    nested.mkdir()
    source = nested / 'extra.py'
    source.write_text('value = 1\n', encoding='utf-8')
    values[1]['pkg/extra.py'] = _sha(source)
    moved = tmp_path / 'old-pkg'
    original = package_inputs._source_pass
    count = 0

    def replace_after_pass(*args):
        nonlocal count
        result = original(*args)
        count += 1
        if count == 1:
            nested.rename(moved)
            shutil.copytree(moved, nested)
        return result

    monkeypatch.setattr(package_inputs, '_source_pass', replace_after_pass)
    with pytest.raises(InputError, match='windows_package_source_directory_changed'):
        _inspect(values)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_output_overlap_and_reparse_refusal(tmp_path):
    values = _fixture(tmp_path)
    with pytest.raises(InputError, match='windows_package_input_output_overlap'):
        inspect_windows_template_package_inputs(*values[:4], values[0], values[5], 'synthetic-host')
    junction = tmp_path / 'junction'
    try:
        os.symlink(values[2], junction, target_is_directory=True)
    except (OSError, NotImplementedError):
        created = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(values[2])],
                                 capture_output=True, text=True, timeout=10)
        if created.returncode != 0:
            pytest.skip('Native symlink or junction creation unavailable')
    with pytest.raises(InputError, match='windows_package_repository_path_contains_(symlink|junction)'):
        inspect_windows_template_package_inputs(values[0], values[1], junction,
                                                values[3], values[4], values[5],
                                                'synthetic-host')


def test_non_windows_package_inputs_rejected(tmp_path):
    if os.name == 'nt':
        pytest.skip('non-Windows rejection applies on POSIX')
    with pytest.raises(InputError, match='native_windows_preflight_required'):
        inspect_windows_template_package_inputs(tmp_path, {}, tmp_path, {}, tmp_path,
                                                tmp_path, 'host')
