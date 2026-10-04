"""Read-only provenance of two independently installed package generations.

A report binds bytes only. It cannot authenticate its own selected set, grant
provider access, authorize an effect, or establish measured application benefit.
"""
from __future__ import annotations

import os
import base64
import hashlib
import importlib.metadata
from pathlib import Path
import stat

from .contracts import validate_contract
from .io import InputError, digest
from .template_connected_binding import derive_installed_binding


class PackagesConnectedBindingError(InputError):
    """Content-free composite provenance failure."""


def _member_import_plan(package: dict, binding: dict) -> list[dict]:
    """Cover the full selected application distribution before package imports."""
    from packaging.utils import canonicalize_name
    wanted = canonicalize_name(package['package_plan']['project_name'])
    distributions = [distribution for distribution in importlib.metadata.distributions(path=[binding['site']])
                     if canonicalize_name(distribution.metadata['Name']) == wanted]
    if len(distributions) != 1 or distributions[0].files is None:
        raise PackagesConnectedBindingError('packages_connected_member_record_missing')
    distribution = distributions[0]
    if distribution.version != package['package_plan']['project_version']:
        raise PackagesConnectedBindingError('packages_connected_member_record_changed')
    environment = Path(package['install_receipt']['environment']) / 'venv'
    files = {}
    for item in distribution.files:
        path = Path(distribution.locate_file(item))
        if (path.is_symlink() or any(parent.is_symlink() for parent in path.parents)
                or not path.resolve(strict=True).is_relative_to(environment)
                or not path.is_file()):
            raise PackagesConnectedBindingError('packages_connected_member_record_changed')
        path = path.resolve(strict=True)
        raw = path.read_bytes()
        if item.size is not None and len(raw) != item.size:
            raise PackagesConnectedBindingError('packages_connected_member_record_changed')
        if item.hash is not None:
            actual = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
            if item.hash.mode != 'sha256' or item.hash.value != actual:
                raise PackagesConnectedBindingError('packages_connected_member_record_changed')
        if path.suffix != '.pyc':
            files[str(path)] = hashlib.sha256(raw).hexdigest()
    if len(files) > 128:
        raise PackagesConnectedBindingError('packages_connected_member_profile_too_large')
    return [{'path': path, 'sha256': sha} for path, sha in sorted(files.items())]


def derive_installed_packages_binding(packages: list[dict], *, source_root: str) -> dict:
    """Return exact provenance or a bounded refusal without filesystem paths."""
    try:
        return _derive_installed_packages_binding(packages, source_root=source_root)
    except (OSError, ValueError, TypeError, KeyError):
        raise PackagesConnectedBindingError('packages_connected_provenance_unavailable') from None


def _derive_installed_packages_binding(packages: list[dict], *, source_root: str) -> dict:
    """Recompute both independent install receipts and merge their exact origins.

    The caller supplies the private common owner root explicitly; a parent
    directory is never inferred from target paths. No target module is imported.
    Both package and install anchors must come from outside the host bundles.
    """
    root = Path(source_root)
    if (type(packages) is not list or len(packages) != 2 or not root.is_absolute()
            or not root.is_dir() or root.is_symlink()
            or any(parent.is_symlink() for parent in root.parents)):
        raise PackagesConnectedBindingError('packages_connected_scope_invalid')
    root = root.resolve(strict=True)
    info = root.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise PackagesConnectedBindingError('packages_connected_owner_root_private_required')
    members, distributions, files = {}, {}, {}
    expected = {'package_plan', 'package_receipt', 'install_plan', 'install_receipt',
                'trusted_package_receipt_sha256', 'trusted_install_receipt_sha256'}
    for package in packages:
        if type(package) is not dict or set(package) != expected:
            raise PackagesConnectedBindingError('packages_connected_scope_invalid')
        from .template_packages_records import installed_records_snapshot
        installed_records_snapshot(package['install_plan'], package['install_receipt'])
        binding = derive_installed_binding(**package)
        name = binding['candidate_id']
        if name in members:
            raise PackagesConnectedBindingError('packages_connected_placement_collision')
        declared = package['install_receipt']['installed']['distributions']
        distribution = package['package_plan']['project_name']
        version = package['package_plan']['project_version']
        if (distribution == 'jev-integration-evaluator'
                or declared.get(distribution) != version):
            raise PackagesConnectedBindingError('packages_connected_distribution_ambiguous')
        if distribution in distributions:
            raise PackagesConnectedBindingError('packages_connected_distinct_distributions_required')
        # An independently installed generation must have its own environment.
        if any(binding['site'] == other['site'] for other in members.values()):
            raise PackagesConnectedBindingError('packages_connected_distinct_installs_required')
        for row in binding['source_plan']['files']:
            path = Path(row['path'])
            if (not path.is_relative_to(root) or not path.resolve(strict=True).is_relative_to(root)
                    or any(parent.is_symlink() for parent in path.parents)):
                raise PackagesConnectedBindingError('packages_connected_origin_outside_owner')
            if str(path) in files:
                raise PackagesConnectedBindingError('packages_connected_origin_collision')
            files[str(path)] = row['sha256']
        for row in _member_import_plan(package, binding):
            path = Path(row['path'])
            if not path.is_relative_to(root) or (row['path'] in files and files[row['path']] != row['sha256']):
                raise PackagesConnectedBindingError('packages_connected_origin_collision')
            files[row['path']] = row['sha256']
        if 'loader' not in binding['origins']:
            raise PackagesConnectedBindingError('packages_connected_loader_required')
        members[name] = binding
        distributions[distribution] = {'candidate_id': name, 'version': declared[distribution]}
    report = {'schema_version': '1.0', 'kind': 'connected-installed-packages-binding-v1',
              'candidate_ids': sorted(members), 'site': str(root),
              'members': dict(sorted(members.items())),
              'distributions': dict(sorted(distributions.items())),
              'source_plan': {'files': [{'path': path, 'sha256': files[path]}
                                        for path in sorted(files)]}}
    report['binding_sha256'] = digest(report)
    validate_contract(report, 'connected-installed-packages-binding-v1')
    return report
