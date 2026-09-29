"""Native NTFS ownership primitives used by the offline mutating adapter."""
from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import sys

import pytest

from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.windows_template_owned import (
    check_private_directory, create_private_directory, locked_private_directory,
    read_private_json, write_private_json_exclusive,
)


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_private_directory_exclusive_identity_and_acl(tmp_path):
    path = tmp_path / 'owned'
    receipt = create_private_directory(path)
    assert receipt['path'] == str(path)
    assert path.is_dir()
    check_private_directory(receipt)
    with pytest.raises(InputError, match='windows_owned_directory_already_exists'):
        create_private_directory(path)
    with locked_private_directory(receipt) as root:
        assert root == path
        with pytest.raises(InputError, match='windows_owned_lock_busy'):
            with locked_private_directory(receipt):
                pass
        check = subprocess.run([sys.executable, '-c',
            'import json,sys\n'
            'from jev_integration_evaluator.windows_template_owned import locked_private_directory\n'
            'from jev_integration_evaluator.io import InputError\n'
            'try:\n'
            '  with locked_private_directory(json.loads(sys.argv[1])): pass\n'
            'except InputError as exc: print(str(exc))\n', json.dumps(receipt)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
        assert check.returncode == 0
        assert check.stdout.strip() == 'windows_owned_lock_busy'
    digest = write_private_json_exclusive(receipt, 'event-000.json', {'phase': 'pending'})
    assert len(digest) == 64
    with pytest.raises(InputError, match='windows_owned_record_exists_or_unavailable'):
        write_private_json_exclusive(receipt, 'event-000.json', {'phase': 'complete'})
    assert (path / 'event-000.json').read_text(encoding='utf-8') == '{"phase":"pending"}\n'
    moved = tmp_path / 'moved'
    path.rename(moved)
    path.mkdir()
    with pytest.raises(InputError, match='windows_owned_directory_changed'):
        check_private_directory(receipt)


def test_non_windows_owner_primitives_rejected(tmp_path):
    if os.name == 'nt':
        pytest.skip('non-Windows rejection applies on POSIX')
    with pytest.raises(InputError, match='native_windows_preflight_required'):
        create_private_directory(tmp_path / 'owned')


@pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')
def test_native_lock_alias_and_record_acl_drift_refused(tmp_path):
    owned = create_private_directory(tmp_path / 'owned')
    root = Path(owned['path'])
    lock_alias = root / 'lock-alias.bin'
    os.link(root / 'delivery.lock', lock_alias)
    try:
        with pytest.raises(InputError, match='windows_owned_lock_invalid'):
            with locked_private_directory(owned):
                pass
    finally:
        lock_alias.unlink()
    write_private_json_exclusive(owned, 'event.json', {'phase': 'reviewed'})
    assert read_private_json(owned, 'event.json') == {'phase': 'reviewed'}
    identity = subprocess.run(['whoami'], capture_output=True, text=True, timeout=10)
    assert identity.returncode == 0
    changed = subprocess.run(['icacls', str(root / 'event.json'), '/grant',
                              identity.stdout.strip() + ':(R)'],
                             capture_output=True, text=True, timeout=10)
    if changed.returncode != 0:
        pytest.skip('This account cannot change a disposable record ACL')
    with pytest.raises(InputError, match='windows_owned_record_acl_changed'):
        read_private_json(owned, 'event.json')
