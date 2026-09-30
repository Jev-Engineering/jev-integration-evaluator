"""Read-only native Windows source-to-installed binding for connected review.

The off-mode receipts establish provenance.  This report grants no exposure.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
from pathlib import Path
import stat
import zipfile

from . import capabilities as cap
from .contracts import validate_contract
from .io import InputError, digest, loads
from .windows_template_install import owned_windows_install_receipt, windows_install_status
from .windows_template_owned import acl_sha256
from .windows_template_plan import windows_package_status


class WindowsConnectedBindingError(InputError):
    """Fixed diagnostic without source bytes or credential material."""


def _regular(path: Path, expected_sha256: str, limit: int = 64_000_000) -> dict:
    """Recheck bytes, NTFS identity, ACL and hardlink exclusion at use time."""
    try:
        before = os.lstat(path)
        if (cap._windows_reparse_reason(before) or not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1):
            raise WindowsConnectedBindingError('windows_connected_origin_linked')
        raw = cap._windows_secure_input(path, limit)
        after = os.lstat(path)
        identity = cap._windows_file_identity(before)
        if (cap._windows_file_identity(after) != identity or after.st_nlink != 1
                or hashlib.sha256(raw).hexdigest() != expected_sha256):
            raise WindowsConnectedBindingError('windows_connected_origin_changed')
        return {'path': str(path), 'sha256': expected_sha256,
                'volume_id': identity[0], 'file_id': identity[1],
                'acl_sha256': acl_sha256(path)}
    except cap.CapabilityError:
        raise WindowsConnectedBindingError('windows_connected_origin_unavailable') from None
    except OSError:
        raise WindowsConnectedBindingError('windows_connected_origin_unavailable') from None


def current_origin(row: dict) -> bool:
    """Check the exact installed identity before each route or status claim."""
    try:
        actual = _regular(Path(row['path']), row['sha256'])
        return all(actual[key] == row[key] for key in
                   ('path', 'sha256', 'volume_id', 'file_id', 'acl_sha256'))
    except (KeyError, TypeError, WindowsConnectedBindingError):
        return False


def derive_windows_installed_binding(package_plan: dict, package_receipt: dict,
                                     install_plan: dict, install_receipt: dict, *,
                                     trusted_package_receipt_sha256: str,
                                     trusted_install_receipt_sha256: str) -> dict:
    """Recompute wheel RECORD and exact native installed origins from anchored receipts."""
    validate_contract(package_plan, 'windows-template-package-plan-v1')
    validate_contract(package_receipt, 'windows-template-package-receipt-v1')
    validate_contract(install_plan, 'windows-template-install-plan-v1')
    validate_contract(install_receipt, 'windows-template-install-receipt-v1')
    package_status = windows_package_status(
        package_plan, trusted_receipt_sha256=trusted_package_receipt_sha256)
    install_status = windows_install_status(
        install_plan, trusted_receipt_sha256=trusted_install_receipt_sha256)
    owned = owned_windows_install_receipt(install_plan, trusted_install_receipt_sha256)
    if (package_status != {'status': 'built_recorded', 'receipt_trust':
                           'externally_anchored', 'receipt_sha256':
                           trusted_package_receipt_sha256}
            or install_status != {'status': 'installed_recorded', 'receipt_trust':
                                  'externally_anchored', 'receipt_sha256':
                                  trusted_install_receipt_sha256}
            or owned != install_receipt or install_plan['package_plan'] != package_plan
            or install_plan['package_receipt'] != package_receipt):
        raise WindowsConnectedBindingError('windows_connected_receipts_unverified')
    source = package_plan['inputs']['source_files']
    spec_path = Path(package_plan['request']['implementation_bundle']) / 'implementation-spec.json'
    try:
        spec = loads(cap._windows_secure_input(spec_path, 1_000_000))
        host_source = spec['source']['file']
        package_module = spec['package_binding']['module'].rpartition('.')[0]
        if (not package_module or spec['package_binding']['namespace'] is not False
                or host_source not in source or 'pyproject.toml' not in source):
            raise WindowsConnectedBindingError('windows_connected_reviewed_binding_missing')
        members = {'host': spec['package_binding']['module'].replace('.', '/') + '.py',
                   'adapter': (package_module + '.' + spec['output']['module']).replace('.', '/') + '.py',
                   'console': spec['entrypoint_binding']['module'].replace('.', '/') + '.py'}
        loader_source = (Path(host_source).parent / 'connected_authority.py').as_posix()
        if loader_source in source:
            members['loader'] = package_module.replace('.', '/') + '/connected_authority.py'
        if len(set(members.values())) != len(members):
            raise WindowsConnectedBindingError('windows_connected_mapping_ambiguous')
        root = Path(install_receipt['environment'])
        venv = root / 'venv'
        console = Path(install_receipt['installed']['entrypoint_origin'])
        site = console
        for _ in Path(members['console']).parts:
            site = site.parent
        if (not cap._path_is_within(site, venv)
                or not cap._windows_same_path(str(site / members['console']), str(console))):
            raise WindowsConnectedBindingError('windows_connected_site_changed')
        wheel = Path(package_receipt['package_directory']) / 'dist' / package_receipt['wheel_filename']
        _regular(wheel, package_receipt['wheel_sha256'])
        origins = {}
        with zipfile.ZipFile(wheel) as archive:
            records = [name for name in archive.namelist() if name.endswith('.dist-info/RECORD')]
            if len(records) != 1:
                raise WindowsConnectedBindingError('windows_connected_wheel_record_missing')
            wheel_record = list(csv.reader(io.StringIO(archive.read(records[0]).decode('utf-8'))))
            installed_record_path = site / records[0].replace('/', os.sep)
            installed_record_raw = cap._windows_secure_input(installed_record_path, 4_000_000)
            _regular(installed_record_path, hashlib.sha256(installed_record_raw).hexdigest(), 4_000_000)
            installed_record = list(csv.reader(io.StringIO(installed_record_raw.decode('utf-8'))))
            if (any(len(row) != 3 for row in wheel_record + installed_record)
                    or len({row[0] for row in wheel_record}) != len(wheel_record)
                    or len({row[0] for row in installed_record}) != len(installed_record)):
                raise WindowsConnectedBindingError('windows_connected_record_invalid')
            wheel_entries = {name: (sha, size) for name, sha, size in wheel_record}
            installed_entries = {name: (sha, size) for name, sha, size in installed_record}
            for role, member in members.items():
                raw = archive.read(member)
                encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
                if (wheel_entries.get(member) != ('sha256=' + encoded, str(len(raw)))
                        or installed_entries.get(member) != wheel_entries[member]):
                    raise WindowsConnectedBindingError('windows_connected_record_mismatch')
                row = _regular(site / member.replace('/', os.sep), hashlib.sha256(raw).hexdigest())
                if row['sha256'] != hashlib.sha256(raw).hexdigest():
                    raise WindowsConnectedBindingError('windows_connected_installed_changed')
                origins[role] = {**row, 'wheel_member': member}
        adapter_source = (Path(host_source).parent / (spec['output']['module'] + '.py')).as_posix()
        if (origins['host']['sha256'] != source[host_source]
                or origins['adapter']['sha256'] != source[adapter_source]
                or origins['console']['sha256'] != source[spec['entrypoint_binding']['file']]
                or ('loader' in origins and origins['loader']['sha256'] != source[loader_source])):
            raise WindowsConnectedBindingError('windows_connected_source_wheel_mismatch')
        project = Path(package_receipt['package_directory']) / 'source' / 'pyproject.toml'
        project_row = _regular(project, source['pyproject.toml'], 1_000_000)
        if spec['entrypoint_binding']['pyproject_sha256'] != project_row['sha256']:
            raise WindowsConnectedBindingError('windows_connected_project_changed')
        report = {'schema_version': '1.0', 'kind': 'windows-connected-installed-binding-v1',
                  'candidate_id': spec['candidate_id'], 'source_file': host_source,
                  'reviewed_file_sha256': spec['source']['file_sha256'],
                  'applied_file_sha256': origins['host']['sha256'],
                  'package_plan_sha256': package_plan['plan_sha256'],
                  'package_receipt_sha256': package_receipt['receipt_sha256'],
                  'install_plan_sha256': install_plan['plan_sha256'],
                  'install_receipt_sha256': install_receipt['receipt_sha256'],
                  'wheel_sha256': package_receipt['wheel_sha256'],
                  'installed_files_sha256': install_receipt['installed']['installed_files_sha256'],
                  'site': str(site), 'origins': origins,
                  'reviewed_project': project_row,
                  'reviewed_project_path': project_row['path'],
                  'reviewed_project_sha256': project_row['sha256'],
                  'installed_record': _regular(installed_record_path,
                                               hashlib.sha256(installed_record_raw).hexdigest(),
                                               4_000_000),
                  'source_plan': {'files': [{'path': row['path'], 'sha256': row['sha256']}
                                            for row in origins.values()] +
                                           [{'path': project_row['path'], 'sha256': project_row['sha256']}]}}
        report['binding_sha256'] = digest(report)
        validate_contract(report, 'windows-connected-installed-binding-v1')
        return report
    except (KeyError, TypeError, ValueError, UnicodeError, zipfile.BadZipFile, cap.CapabilityError):
        raise WindowsConnectedBindingError('windows_connected_binding_unavailable') from None
