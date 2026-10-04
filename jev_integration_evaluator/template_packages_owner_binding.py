"""Read-only exact installed common-owner provenance; no target imports."""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.metadata
import io
from pathlib import Path
import zipfile

from .contracts import seal, validate_contract, verify
from .io import InputError, digest, file_hash
from .template_connected_binding import _member
from .template_connected_packages_binding import derive_installed_packages_binding
from .template_packages_installation import plan_owner_install, owner_installation_status
from . import template_installation as installer


class PackagesOwnerBindingError(InputError):
    """Path-free refusal of changed selected owner or member provenance."""


def derive_installed_owner_binding(package_plan: dict, package_receipt: dict,
                                   install_plan: dict, install_receipt: dict, *,
                                   trusted_package_receipt_sha256: str,
                                   trusted_install_receipt_sha256: str) -> dict:
    try:
        return _derive_owner(package_plan, package_receipt, install_plan, install_receipt,
            trusted_package_receipt_sha256=trusted_package_receipt_sha256,
            trusted_install_receipt_sha256=trusted_install_receipt_sha256)
    except PackagesOwnerBindingError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise PackagesOwnerBindingError('packages_owner_installed_provenance_unavailable') from None


def _derive_owner(package_plan, package_receipt, install_plan, install_receipt, *,
                  trusted_package_receipt_sha256, trusted_install_receipt_sha256):
    for value, kind in ((package_plan, 'packages-owner-package-plan-v1'),
                        (package_receipt, 'packages-owner-package-receipt-v1'),
                        (install_plan, 'packages-owner-install-plan-v1'),
                        (install_receipt, 'packages-owner-install-receipt-v1')):
        validate_contract(value, kind)
    verify(package_receipt, 'receipt_sha256', trusted_package_receipt_sha256)
    verify(install_receipt, 'receipt_sha256', trusted_install_receipt_sha256)
    from .template_packages_records import installed_records_snapshot
    installed_records_snapshot(install_plan, install_receipt)
    if (plan_owner_install(package_plan, package_receipt) != install_plan
            or installer.package_status(package_plan)['status'] != 'built_recorded'
            or owner_installation_status(install_plan)['status'] != 'installed_recorded'
            or install_receipt['plan_sha256'] != install_plan['plan_sha256']
            or install_receipt['package_receipt_sha256'] != package_receipt['receipt_sha256']):
        raise PackagesOwnerBindingError('packages_owner_install_receipts_changed')
    root = Path(install_receipt['environment']).resolve(strict=True)
    console = Path(install_receipt['installed']['entrypoint_origin']).resolve(strict=True)
    site = console.parent.parent
    if console != site / 'registered_packages/console.py' or not site.is_relative_to(root / 'venv'):
        raise PackagesOwnerBindingError('packages_owner_installed_module_changed')
    wheel_path = installer._check_package_receipt(package_plan, package_receipt)
    with zipfile.ZipFile(wheel_path) as wheel:
        records = [name for name in wheel.namelist() if name.endswith('.dist-info/RECORD')]
        if len(records) != 1:
            raise PackagesOwnerBindingError('packages_owner_wheel_record_changed')
        record = {name: (hashed, size) for name, hashed, size in
                  csv.reader(io.StringIO(wheel.read(records[0]).decode('utf-8')))}
        raw = _member(wheel, 'registered_packages/console.py', record)
        if console.read_bytes() != raw or file_hash(console) != package_plan['source_files']['src/registered_packages/console.py']:
            raise PackagesOwnerBindingError('packages_owner_source_to_wheel_changed')
    files = {}
    wanted = dict(install_receipt['installed']['distributions'])
    found = {}
    for distribution in importlib.metadata.distributions(path=[str(site)]):
        name = distribution.metadata['Name']
        if name not in wanted:
            raise PackagesOwnerBindingError('packages_owner_unselected_distribution')
        if name in found or distribution.version != wanted[name] or distribution.files is None:
            raise PackagesOwnerBindingError('packages_owner_distribution_metadata_changed')
        found[name] = distribution.version
        for item in distribution.files:
            path = Path(distribution.locate_file(item))
            if (path.is_symlink() or any(parent.is_symlink() for parent in path.parents)
                    or not path.resolve(strict=True).is_relative_to(root / 'venv') or not path.is_file()):
                raise PackagesOwnerBindingError('packages_owner_record_origin_changed')
            path = path.resolve(strict=True)
            raw = path.read_bytes()
            if item.size is not None and len(raw) != item.size:
                raise PackagesOwnerBindingError('packages_owner_record_size_changed')
            if item.hash is not None:
                actual = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
                if item.hash.mode != 'sha256' or actual != item.hash.value:
                    raise PackagesOwnerBindingError('packages_owner_record_hash_changed')
            files[str(path)] = hashlib.sha256(raw).hexdigest()
    if found != wanted or len(files) > 4096:
        raise PackagesOwnerBindingError('packages_owner_distribution_set_changed')
    project = Path(package_plan['request']['package_directory']) / 'source/pyproject.toml'
    if file_hash(project) != package_plan['source_files']['pyproject.toml']:
        raise PackagesOwnerBindingError('packages_owner_retained_project_changed')
    files[str(project.resolve(strict=True))] = file_hash(project)
    origins = {'console': {'path': str(console), 'sha256': file_hash(console)},
               'command': {'path': install_receipt['installed']['console_script'],
                           'sha256': install_receipt['installed']['console_script_sha256']},
               'evaluator': {'path': str(site / 'jev_integration_evaluator/__init__.py'),
                             'sha256': file_hash(site / 'jev_integration_evaluator/__init__.py')},
               'project': {'path': str(project.resolve(strict=True)), 'sha256': file_hash(project)}}
    if any(files.get(row['path']) != row['sha256'] for row in origins.values()):
        raise PackagesOwnerBindingError('packages_owner_command_scope_changed')
    report = seal({'schema_version': '1.0', 'kind': 'connected-installed-owner-binding-v1',
                   'package_plan_sha256': package_plan['plan_sha256'],
                   'package_receipt_sha256': package_receipt['receipt_sha256'],
                   'install_plan_sha256': install_plan['plan_sha256'],
                   'install_receipt_sha256': install_receipt['receipt_sha256'],
                   'owner_source_plan_sha256': package_plan['owner_source_plan_sha256'],
                   'wheel_sha256': package_receipt['wheel_sha256'],
                   'installed_files_sha256': install_receipt['installed']['installed_files_sha256'],
                   'environment': str(root), 'site': str(site), 'origins': origins,
                   'source_plan': {'files': [{'path': path, 'sha256': sha} for path, sha in sorted(files.items())]}},
                  'binding_sha256')
    validate_contract(report, report['kind'])
    return report


def derive_owned_packages_binding(packages: list[dict], owner: dict, *, source_root: str) -> dict:
    """Bind selected member generations and a genuinely installed normal owner."""
    try:
        group = derive_installed_packages_binding(packages, source_root=source_root)
        bound_owner = derive_installed_owner_binding(**owner)
        if owner['package_plan']['request']['owner_source_plan']['binding'] != group:
            raise PackagesOwnerBindingError('packages_owner_selected_group_changed')
        files = {row['path']: row['sha256'] for row in group['source_plan']['files']}
        for row in bound_owner['source_plan']['files']:
            path = Path(row['path'])
            if (not path.resolve(strict=True).is_relative_to(Path(group['site']))
                    or row['path'] in files):
                raise PackagesOwnerBindingError('packages_owner_common_scope_changed')
            files[row['path']] = row['sha256']
        group['owner'] = bound_owner
        group['source_plan']['files'] = [{'path': path, 'sha256': sha} for path, sha in sorted(files.items())]
        group = seal(group, 'binding_sha256')
        validate_contract(group, group['kind'])
        return group
    except PackagesOwnerBindingError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise PackagesOwnerBindingError('packages_owner_installed_provenance_unavailable') from None
