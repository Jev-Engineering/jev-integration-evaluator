"""Read-only installed metadata fixtures, not a built-package qualification."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
from pathlib import Path

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.template_packages_records import installed_records_snapshot


def fixture(root):
    site = root / 'venv/lib/python3.13/site-packages'
    package = site / 'bounded_snapshot'
    package.mkdir(parents=True)
    initializer = package / '__init__.py'
    initializer.write_text('VALUE = 1\n')
    metadata = site / 'bounded_snapshot-1.0.0.dist-info'
    metadata.mkdir()
    (metadata / 'METADATA').write_text('Metadata-Version: 2.1\nName: bounded-snapshot\nVersion: 1.0.0\n')
    rows = []
    for path in (initializer, metadata / 'METADATA'):
        raw = path.read_bytes()
        rows.append([str(path.relative_to(site)), 'sha256=' + base64.urlsafe_b64encode(
            hashlib.sha256(raw).digest()).rstrip(b'=').decode(), str(len(raw))])
    rows.append([str((metadata / 'RECORD').relative_to(site)), '', ''])
    content = io.StringIO()
    csv.writer(content).writerows(rows)
    (metadata / 'RECORD').write_text(content.getvalue())
    files = {str(path.relative_to(root / 'venv')): file_hash(path)
             for path in (initializer, metadata / 'METADATA', metadata / 'RECORD')}
    receipt = {'environment': str(root), 'installed': {
        'distributions': {'bounded-snapshot': '1.0.0'}, 'installed_files_sha256': digest(files)}}
    return site, initializer, receipt


def test_read_only_record_snapshot_covers_initializer_and_metadata(tmp_path):
    site, initializer, receipt = fixture(tmp_path)
    result = installed_records_snapshot({}, receipt)
    assert result['site'] == str(site)
    assert str(initializer) in result['distributions']['bounded-snapshot']


@pytest.mark.parametrize('changed', ['initializer', 'unrecorded_source', 'unrecorded_startup', 'unrecorded_pyc'])
def test_record_snapshot_refuses_before_any_import(tmp_path, changed):
    site, initializer, receipt = fixture(tmp_path)
    marker = tmp_path / 'must-not-run'
    if changed == 'initializer':
        initializer.write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    else:
        suffix = {'unrecorded_source': '.py', 'unrecorded_startup': '.pth', 'unrecorded_pyc': '.pyc'}[changed]
        (site / ('surprise' + suffix)).write_text(f'import pathlib; pathlib.Path({str(marker)!r}).touch()\n')
    with pytest.raises(InputError) as refused:
        installed_records_snapshot({}, receipt)
    assert 'packages_' in str(refused.value)
    assert str(tmp_path) not in str(refused.value)
    assert not marker.exists()
