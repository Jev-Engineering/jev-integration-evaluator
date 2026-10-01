"""Native NTFS source preparation only; no installed or supervised delivery."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.windows_template_preflight import (
    _checked_files, inspect_windows_template_source,
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path):
    root = tmp_path / 'host'
    (root / 'pkg').mkdir(parents=True)
    entry = root / 'pkg/console.py'
    entry.write_text('def main():\n    return 0\n', encoding='utf-8')
    project = root / 'pyproject.toml'
    project.write_text('[project]\nname="fixture"\nversion="1.0"\n', encoding='utf-8')
    output_parent = tmp_path / 'external'
    output_parent.mkdir()
    return root, output_parent, {'pkg/console.py': _hash(entry),
                                 'pyproject.toml': _hash(project)}


def test_manifest_rejects_ambiguous_windows_names_and_traversal():
    sha = '0' * 64
    for files in ({'pkg/console.py': sha, 'PKG/CONSOLE.py': sha},
                  {'../console.py': sha}, {'CON.py': sha},
                  {'pkg\\console.py': sha}, {'pkg/console.py:stream': sha}):
        with pytest.raises(InputError):
            _checked_files(files)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_read_only_snapshot_and_source_drift(tmp_path):
    root, external, files = _fixture(tmp_path)
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    report = inspect_windows_template_source(root, files, external)
    assert report['status'] == 'preparation_only'
    assert report['target_modified'] is False and report['target_executed'] is False
    assert report['apply_authorized'] is report['install_authorized'] is report['launch_authorized'] is False
    assert report['source_files'] == dict(sorted(files.items()))
    assert before == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(InputError, match='windows_output_overlaps_source'):
        inspect_windows_template_source(root, files, root)
    (root / 'pkg/console.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    with pytest.raises(InputError, match='reviewed_windows_source_changed'):
        inspect_windows_template_source(root, files, external)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_hardlink_readonly_and_long_path(tmp_path):
    root, external, files = _fixture(tmp_path)
    entry = root / 'pkg/console.py'
    hardlink = root / 'pkg/alias.py'
    os.link(entry, hardlink)
    with pytest.raises(InputError, match='windows_preflight_hardlink_excluded'):
        inspect_windows_template_source(root, files, external)
    hardlink.unlink()
    os.chmod(entry, 0o444)
    try:
        assert inspect_windows_template_source(root, files, external)['status'] == 'preparation_only'
    finally:
        os.chmod(entry, 0o666)
    # The selected file itself crosses the legacy MAX_PATH boundary.
    deep = root
    for number in range(9):
        deep = deep / ('long_' + str(number) + '_' + 'x' * 19)
        deep.mkdir()
    long_file = deep / 'source.py'
    long_file.write_text('value = 1\n', encoding='utf-8')
    files[long_file.relative_to(root).as_posix()] = _hash(long_file)
    assert len(str(long_file)) > 260
    assert inspect_windows_template_source(root, files, external)['file_count'] == 3


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_two_pass_edit(tmp_path, monkeypatch):
    from jev_integration_evaluator import capabilities as cap

    root, external, files = _fixture(tmp_path)
    original = cap._windows_secure_input
    calls = 0

    def edit_after_first(path, limit):
        nonlocal calls
        raw = original(path, limit)
        calls += 1
        if calls == len(files):
            (root / 'pkg/console.py').write_text('changed\n', encoding='utf-8')
        return raw

    monkeypatch.setattr(cap, '_windows_secure_input', edit_after_first)
    with pytest.raises(InputError, match='reviewed_windows_source_changed'):
        inspect_windows_template_source(root, files, external)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_identical_root_replacement_between_passes_is_refused(tmp_path, monkeypatch):
    from jev_integration_evaluator import capabilities as cap

    root, external, files = _fixture(tmp_path)
    moved = tmp_path / 'original-host'
    original = cap._windows_secure_input
    calls = 0

    def replace_after_first_pass(path, limit):
        nonlocal calls
        raw = original(path, limit)
        calls += 1
        if calls == len(files):
            root.rename(moved)
            shutil.copytree(moved, root)
        return raw

    monkeypatch.setattr(cap, '_windows_secure_input', replace_after_first_pass)
    with pytest.raises(InputError, match='windows_source_root_changed'):
        inspect_windows_template_source(root, files, external)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_acl_denial_blocks_selected_source(tmp_path):
    root, external, files = _fixture(tmp_path)
    source = root / 'pkg/console.py'
    principal = subprocess.run(['whoami'], capture_output=True, text=True, timeout=10)
    assert principal.returncode == 0
    identity = principal.stdout.strip()
    # Deny file data reads while preserving WRITE_DAC so cleanup can remove
    # this disposable ACE even without elevated privileges.
    denied = subprocess.run(['icacls', str(source), '/deny', identity + ':(RD)'],
                            capture_output=True, text=True, timeout=10)
    if denied.returncode != 0:
        pytest.skip('This account cannot set a disposable file deny ACE')
    try:
        with pytest.raises(InputError, match='windows_preflight_access_denied'):
            inspect_windows_template_source(root, files, external)
    finally:
        restored = subprocess.run(['icacls', str(source), '/remove:d', identity],
                                  capture_output=True, text=True, timeout=10)
        assert restored.returncode == 0, 'Disposable test ACL could not be restored'


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_reparse_output_ancestor(tmp_path):
    root, _, files = _fixture(tmp_path)
    outside = tmp_path / 'elsewhere'
    outside.mkdir()
    junction = tmp_path / 'junction'
    try:
        os.symlink(outside, junction, target_is_directory=True)
    except (OSError, NotImplementedError):
        created = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(outside)],
                                 capture_output=True, text=True, timeout=10)
        if created.returncode != 0:
            pytest.skip('This account cannot create a native directory symlink or junction')
    with pytest.raises(InputError, match='path_contains_reparse_point'):
        inspect_windows_template_source(root, files, junction)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_powershell_friendly_command_omits_source_names(tmp_path):
    root, external, files = _fixture(tmp_path)
    manifest = tmp_path / 'reviewed.json'
    manifest.write_text(json.dumps({'schema_version': '1.0', 'files': files}), encoding='utf-8')
    script = Path(__file__).resolve().parents[1] / 'scripts/windows_template_preflight.py'
    command = [sys.executable, str(script), '--repo', str(root), '--manifest', str(manifest),
               '--output-parent', str(external)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)['status'] == 'preparation_only'
    assert 'console.py' not in run.stdout and str(root) not in run.stdout
    inside = root / 'manifest.json'
    inside.write_text(manifest.read_text(encoding='utf-8'), encoding='utf-8')
    blocked = subprocess.run(command[:5] + [str(inside), *command[6:]],
                             capture_output=True, text=True, timeout=15)
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)['reason'] == 'windows_source_manifest_must_be_external'


def _administrative_share(path: Path) -> str:
    """Spell a local drive path as a UNC root; delivery must refuse it unopened."""
    drive, tail = os.path.splitdrive(str(path))
    return '\\\\localhost\\' + drive[0] + '$' + tail


class _VolumeAnswer:
    """The real kernel32 with only the drive-type and filesystem answers replaced."""

    def __init__(self, kernel, drive_type: int, filesystem: str):
        self._kernel = kernel
        self._drive_type = drive_type
        self._filesystem = filesystem

    def __getattr__(self, name):
        return getattr(self._kernel, name)

    def GetDriveTypeW(self, _root):
        return self._drive_type

    def GetVolumeInformationW(self, _root, _name, _name_len, _serial, _component,
                              _flags, filesystem, _filesystem_len):
        filesystem.value = self._filesystem
        return 1


def _tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() if p.is_file() else None
            for p in sorted(root.rglob('*'))}


_UNSUPPORTED_VOLUMES = (
    (4, 'NTFS', 'unsupported_unc_path'),             # mapped network drive
    (3, 'ReFS', 'unsupported_windows_filesystem'),
    (2, 'exFAT', 'unsupported_windows_filesystem'),
    (5, 'NTFS', 'unsupported_windows_filesystem'),   # optical drive type
)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_unc_mapped_and_non_ntfs_roots_are_refused_without_effect(tmp_path, monkeypatch):
    from jev_integration_evaluator import capabilities as cap

    root, external, files = _fixture(tmp_path)
    before = _tree(tmp_path)
    assert inspect_windows_template_source(root, files, external)['status'] == 'preparation_only'
    extended = '\\\\?\\UNC\\' + _administrative_share(root)[2:]
    for source, output in ((_administrative_share(root), external),
                           (extended, external),
                           (root, _administrative_share(external))):
        with pytest.raises(InputError, match='^windows_preflight_unsupported_unc_path$'):
            inspect_windows_template_source(source, files, output)
    ctypes_module, wintypes, kernel = cap._windows_api()
    for drive_type, filesystem, reason in _UNSUPPORTED_VOLUMES:
        answer = _VolumeAnswer(kernel, drive_type, filesystem)
        with monkeypatch.context() as patch:
            patch.setattr(cap, '_windows_api', lambda: (ctypes_module, wintypes, answer))
            with pytest.raises(InputError, match='^windows_preflight_' + reason + '$'):
                inspect_windows_template_source(root, files, external)
    assert _tree(tmp_path) == before
    assert not list(external.iterdir())
    # The same local NTFS inputs remain acceptable once the volume answer is real.
    assert inspect_windows_template_source(root, files, external)['file_count'] == len(files)

    manifest = tmp_path / 'reviewed.json'
    manifest.write_text(json.dumps({'schema_version': '1.0', 'files': files}), encoding='utf-8')
    script = Path(__file__).resolve().parents[1] / 'scripts/windows_template_preflight.py'
    blocked = subprocess.run(
        [sys.executable, str(script), '--repo', _administrative_share(root),
         '--manifest', str(manifest), '--output-parent', str(external)],
        capture_output=True, text=True, timeout=15)
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout) == {
        'status': 'blocked', 'reason': 'windows_preflight_unsupported_unc_path'}
    assert 'localhost' not in blocked.stdout and not list(external.iterdir())


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_real_case_alias_blocks_selected_source_preparation(tmp_path):
    """A reviewed file or directory component with an on-disk case-only sibling."""
    root, external, files = _fixture(tmp_path)
    tree = root / 'cased'
    tree.mkdir()
    enabled = subprocess.run(
        ['fsutil', 'file', 'setCaseSensitiveInfo', str(tree), 'enable'],
        capture_output=True, text=True, timeout=15)
    assert enabled.returncode == 0, 'Per-directory NTFS case sensitivity is unavailable'
    lower, upper = tree / 'module.py', tree / 'MODULE.py'
    low_dir, up_dir = tree / 'sub', tree / 'SUB'
    try:
        lower.write_bytes(b'value = 1\n')
        upper.write_bytes(b'value = 2\n')
        low_dir.mkdir()
        (low_dir / 'inner.py').write_bytes(b'value = 3\n')
        up_dir.mkdir()
        assert sorted(os.listdir(tree)) == ['MODULE.py', 'SUB', 'module.py', 'sub']
        before = _tree(tmp_path)
        for relative, path in (('cased/module.py', lower), ('cased/MODULE.py', upper),
                               ('cased/sub/inner.py', low_dir / 'inner.py')):
            with pytest.raises(InputError, match='^windows_preflight_case_alias_refused$'):
                inspect_windows_template_source(root, {**files, relative: _hash(path)}, external)
        with pytest.raises(InputError, match='^case_ambiguous_windows_source_manifest$'):
            inspect_windows_template_source(
                root, {**files, 'cased/module.py': _hash(lower),
                       'cased/MODULE.py': _hash(upper)}, external)
        assert _tree(tmp_path) == before and not list(external.iterdir())
        upper.unlink()
        up_dir.rmdir()
        # With both aliases gone the same reviewed spellings are prepared.
        reviewed = {**files, 'cased/module.py': _hash(lower),
                    'cased/sub/inner.py': _hash(low_dir / 'inner.py')}
        report = inspect_windows_template_source(root, reviewed, external)
        assert report['source_files'] == dict(sorted(reviewed.items()))
        assert not list(external.iterdir())
    finally:
        if os.path.lexists(upper):
            upper.unlink()
        if os.path.lexists(up_dir):
            up_dir.rmdir()
        for directory in (low_dir, tree):
            restored = subprocess.run(
                ['fsutil', 'file', 'setCaseSensitiveInfo', str(directory), 'disable'],
                capture_output=True, text=True, timeout=15)
            assert restored.returncode == 0, 'Disposable case-sensitive directory was not restored'


def test_non_windows_has_no_delivery_claim(tmp_path):
    if os.name == 'nt':
        pytest.skip('non-Windows rejection applies on POSIX')
    with pytest.raises(InputError, match='native_windows_preflight_required'):
        inspect_windows_template_source(tmp_path, {'a.py': '0' * 64}, tmp_path)
