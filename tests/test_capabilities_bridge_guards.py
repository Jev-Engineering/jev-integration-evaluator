"""Synthetic guards for the shared discovery reader used by the inventory bridge."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from jev_integration_evaluator import capabilities as cap

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Secure descriptor reads require POSIX')

SOURCE = b'def baseline(value):\n    return value.dispatch()\ndef seam(value):\n    return baseline(value)\n'


@pytest.mark.parametrize('replacement', [SOURCE, SOURCE + b'# replacement\n'])
def test_source_read_rejects_path_replacement_after_descriptor_open(tmp_path, monkeypatch, replacement):
    root = tmp_path/'host'
    root.mkdir()
    source = root/'opaque.py'
    source.write_bytes(SOURCE)
    original = os.read
    replaced = False

    def read_then_replace(fd, amount):
        nonlocal replaced
        raw = original(fd, amount)
        if raw and not replaced:
            replaced = True
            source.rename(root/'old.txt')
            source.write_bytes(replacement)
        return raw

    _, directory, _ = cap._secure_root(root)
    monkeypatch.setattr(os, 'read', read_then_replace)
    try:
        with pytest.raises(cap.CapabilityError, match='^source_changed_during_read$'):
            cap._read_at(directory, 'opaque.py', 4096)
    finally:
        os.close(directory)
    assert source.read_bytes() == replacement


@pytest.mark.parametrize('change', ['new_file', 'deleted_file', 'mode'])
def test_full_snapshot_recheck_covers_changes_after_ast_analysis(tmp_path, monkeypatch, change):
    root = tmp_path/'host'
    root.mkdir()
    source = root/'opaque.py'
    source.write_bytes(SOURCE)
    original = cap._analyze_python
    changed = False

    def analyze_then_change(path, raw, policy):
        nonlocal changed
        result = original(path, raw, policy)
        if not changed:
            changed = True
            if change == 'new_file':
                (root/'added.py').write_bytes(SOURCE)
            elif change == 'deleted_file':
                source.unlink()
            else:
                source.chmod(0o600)
        return result

    monkeypatch.setattr(cap, '_analyze_python', analyze_then_change)
    with pytest.raises(cap.CapabilityError, match='^source_changed_during_discovery$'):
        cap.discover_repository(root)
