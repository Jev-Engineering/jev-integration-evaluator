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


def test_non_windows_has_no_delivery_claim(tmp_path):
    if os.name == 'nt':
        pytest.skip('non-Windows rejection applies on POSIX')
    with pytest.raises(InputError, match='native_windows_preflight_required'):
        inspect_windows_template_source(tmp_path, {'a.py': '0' * 64}, tmp_path)
