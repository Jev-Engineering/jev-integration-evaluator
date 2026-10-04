"""Read installed RECORD snapshots without launching an installed interpreter."""
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
from pathlib import Path
import stat

from packaging.utils import canonicalize_name

from .io import InputError, digest


def installed_records_snapshot(install_plan: dict, receipt: dict) -> dict:
    """Refuse drift or unrecorded code before any installed metadata process."""
    try:
        environment = Path(receipt['environment']) / 'venv'
        site = environment / 'lib/python3.13/site-packages'
        if site.is_symlink() or not site.is_dir():
            raise InputError('packages_installed_record_snapshot_changed')
        expected = dict(receipt['installed']['distributions'])
        actual, hashes, by_distribution = {}, {}, {}
        total_bytes = 0
        for distribution in importlib.metadata.distributions(path=[str(site)]):
            name = distribution.metadata['Name']
            canonical = canonicalize_name(name)
            selected = [key for key in expected if canonicalize_name(key) == canonical]
            if len(selected) != 1 or selected[0] in actual or distribution.files is None:
                raise InputError('packages_installed_record_snapshot_changed')
            name = selected[0]
            if distribution.version != expected[name]:
                raise InputError('packages_installed_record_snapshot_changed')
            actual[name] = distribution.version
            rows = {}
            for item in distribution.files:
                path = Path(distribution.locate_file(item))
                if (path.is_symlink() or any(parent.is_symlink() for parent in path.parents)
                        or not path.resolve(strict=True).is_relative_to(environment)):
                    raise InputError('packages_installed_record_snapshot_changed')
                path = path.resolve(strict=True)
                info = path.stat()
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) & 0o022):
                    raise InputError('packages_installed_record_snapshot_changed')
                total_bytes += info.st_size
                if info.st_size > 4_000_000 or total_bytes > 64_000_000 or len(hashes) >= 4096:
                    raise InputError('packages_installed_record_snapshot_changed')
                with path.open('rb') as source:
                    raw = source.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise InputError('packages_installed_record_snapshot_changed')
                sha = hashlib.sha256(raw).hexdigest()
                if item.size is not None and len(raw) != item.size:
                    raise InputError('packages_installed_record_snapshot_changed')
                if item.hash is not None:
                    encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
                    if item.hash.mode != 'sha256' or item.hash.value != encoded:
                        raise InputError('packages_installed_record_snapshot_changed')
                hashes[str(path.relative_to(environment))] = sha
                rows[str(path)] = sha
            by_distribution[name] = rows
        if actual != expected or digest(hashes) != receipt['installed']['installed_files_sha256']:
            raise InputError('packages_installed_record_snapshot_changed')
        recorded = {str(environment / path) for path in hashes}
        for path in site.rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.pyc', '.pth', '.so', '.pyd', '.dll') and str(path) not in recorded:
                raise InputError('packages_unrecorded_executable_origin')
        return {'site': str(site), 'files': hashes, 'distributions': by_distribution}
    except (OSError, ValueError, TypeError, KeyError):
        raise InputError('packages_installed_record_snapshot_unavailable') from None
