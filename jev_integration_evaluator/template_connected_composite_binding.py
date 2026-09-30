"""Exact installed provenance for reviewed composite Python placements.

Off package/install receipts prove provenance only.  This module never grants
egress, activation, or host execution authority.
"""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path
import stat
import zipfile

from .contracts import validate_contract
from .io import InputError, digest, file_hash, read_json
from .template_connected_binding import _member
from .template_installation import (
    composite_installation_status, package_status, plan_composite_install,
)


class CompositeConnectedBindingError(InputError):
    """A bounded provenance failure with no source or credential bytes."""


def _rows(raw: bytes) -> dict[str, tuple[str, str]]:
    try:
        lines = list(csv.reader(io.StringIO(raw.decode('utf-8'))))
    except UnicodeError:
        raise CompositeConnectedBindingError('composite_installed_record_invalid') from None
    if any(len(row) != 3 for row in lines) or len({row[0] for row in lines}) != len(lines):
        raise CompositeConnectedBindingError('composite_installed_record_invalid')
    return {name: (hash_value, size) for name, hash_value, size in lines}


def _regular_origin(path: Path, site: Path) -> None:
    try:
        info = path.stat()
        if (path.is_symlink() or not path.is_relative_to(site)
                or not path.resolve(strict=True).is_relative_to(site)
                or any(parent.is_symlink() for parent in path.parents if parent != site
                       and parent.is_relative_to(site))
                or not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o022):
            raise CompositeConnectedBindingError('composite_installed_origin_changed')
    except OSError:
        raise CompositeConnectedBindingError('composite_installed_origin_changed') from None


def derive_installed_composite_binding(package_plan: dict, package_receipt: dict,
                                       install_plan: dict, install_receipt: dict,
                                       *, trusted_package_receipt_sha256: str,
                                       trusted_install_receipt_sha256: str) -> dict:
    """Independently reread each selected host, adapter, and shared wheel origin."""
    for value, contract in ((package_plan, 'template-composite-package-plan-v1'),
                            (package_receipt, 'template-composite-package-receipt-v1'),
                            (install_plan, 'template-composite-install-plan-v1'),
                            (install_receipt, 'template-composite-install-receipt-v1')):
        validate_contract(value, contract)
    candidates = package_plan['candidate_ids']
    if (not 2 <= len(candidates) <= 4 or len(set(candidates)) != len(candidates)
            or candidates != sorted(candidates)
            or trusted_package_receipt_sha256 != package_receipt['receipt_sha256']
            or trusted_install_receipt_sha256 != install_receipt['receipt_sha256']
            or plan_composite_install(package_plan, package_receipt) != install_plan
            or package_status(package_plan)['status'] != 'built_recorded'
            or composite_installation_status(install_plan)['status'] != 'installed_recorded'
            or any(value['candidate_ids'] != candidates for value in
                   (package_receipt, install_plan, install_receipt))
            or any(value['selected_set_digest'] != package_plan['selected_set_digest']
                   for value in (package_receipt, install_plan, install_receipt))
            or install_plan['composite_bundle_digest'] != package_plan['implementation_bundle_digest']
            or install_receipt['composite_bundle_digest'] != install_plan['composite_bundle_digest']
            or install_receipt['plan_sha256'] != install_plan['plan_sha256']
            or install_receipt['package_receipt_sha256'] != package_receipt['receipt_sha256']):
        raise CompositeConnectedBindingError('composite_receipt_or_generation_unverified')
    source = package_plan['source_files']
    bundle = Path(package_plan['request']['implementation_bundle']).resolve(strict=True)
    specs = read_json(bundle / 'specifications.json')
    composite = read_json(bundle / 'composite-plan.json')
    console = read_json(bundle / 'composite-console.json')
    if (set(specs) != set(candidates) or composite['candidate_ids'] != candidates
            or console['candidate_ids'] != candidates
            or composite['contract_digest'] != package_plan['implementation_bundle_digest']
            or composite['selected_set_digest'] != package_plan['selected_set_digest']
            or console['selected_set_digest'] != package_plan['selected_set_digest']
            or package_receipt['composite_console_sha256'] != console['file_sha256']
            or console['file'] not in source or 'pyproject.toml' not in source):
        raise CompositeConnectedBindingError('composite_reviewed_binding_missing')
    modules = {specs[name]['package_binding']['module'].rpartition('.')[0]
               for name in candidates}
    if (len(modules) != 1 or not next(iter(modules))
            or any(specs[name]['package_binding']['namespace'] is not False
                   for name in candidates)):
        raise CompositeConnectedBindingError('composite_regular_package_required')
    package_module = next(iter(modules))
    package_prefix = 'src/' + package_module.replace('.', '/') + '/'
    shared = {'console': console['file'],
              'loader': package_prefix + 'connected_authority.py'}
    if (any(name not in source or not name.startswith(package_prefix)
            or '..' in Path(name).parts for name in shared.values())
            or shared['console'] != package_prefix + 'console.py'):
        raise CompositeConnectedBindingError('composite_connected_loader_missing')
    members = {role: relative.removeprefix('src/') for role, relative in shared.items()}
    placements = {}
    for name in candidates:
        spec = specs[name]
        host_source = spec['source']['file']
        adapter_source = (Path(host_source).parent / (spec['output']['module'] + '.py')).as_posix()
        if (spec['candidate_id'] != name or host_source not in source
                or adapter_source not in source
                or not host_source.startswith(package_prefix)
                or not adapter_source.startswith(package_prefix)
                or '..' in Path(host_source).parts or '..' in Path(adapter_source).parts
                or spec['entrypoint_binding']['file'] !=
                console['file'] or spec['entrypoint_binding']['pyproject_sha256'] !=
                source['pyproject.toml']):
            raise CompositeConnectedBindingError('composite_reviewed_binding_missing')
        placements[name] = {'source_file': host_source,
                            'reviewed_file_sha256': spec['source']['file_sha256'],
                            'applied_file_sha256': source[host_source],
                            'host_source': host_source, 'adapter_source': adapter_source}
        members['host:' + name] = host_source.removeprefix('src/')
        members['adapter:' + name] = adapter_source.removeprefix('src/')
    if len(set(members.values())) != len(members):
        raise CompositeConnectedBindingError('composite_module_mapping_ambiguous')
    wheel_path = (Path(package_plan['request']['package_directory']) /
                  package_receipt['wheel_filename']).resolve(strict=True)
    if wheel_path.is_symlink() or file_hash(wheel_path) != package_receipt['wheel_sha256']:
        raise CompositeConnectedBindingError('composite_installed_wheel_changed')
    root = Path(install_receipt['environment']).resolve(strict=True)
    if root.is_symlink() or root != Path(composite_installation_status(install_plan)['environment']):
        raise CompositeConnectedBindingError('composite_installed_environment_changed')
    site = Path(install_receipt['installed']['entrypoint_origin']).resolve(strict=True)
    console_member = Path(members['console'])
    for _ in console_member.parts:
        site = site.parent
    if (site.is_symlink() or not site.is_relative_to(root / 'venv')
            or site / console_member != Path(install_receipt['installed']['entrypoint_origin'])):
        raise CompositeConnectedBindingError('composite_entrypoint_origin_changed')
    origins = {}
    with zipfile.ZipFile(wheel_path) as wheel:
        record_names = [name for name in wheel.namelist() if name.endswith('.dist-info/RECORD')]
        if len(record_names) != 1:
            raise CompositeConnectedBindingError('composite_wheel_record_missing')
        record = _rows(wheel.read(record_names[0]))
        installed_record = site / record_names[0]
        _regular_origin(installed_record, site)
        installed = _rows(installed_record.read_bytes())
        for role, member in members.items():
            raw = _member(wheel, member, record)
            if installed.get(member) != record[member]:
                raise CompositeConnectedBindingError('composite_installed_record_changed')
            path = site / member
            _regular_origin(path, site)
            if path.read_bytes() != raw:
                raise CompositeConnectedBindingError('composite_installed_module_bytes_changed')
            sha = file_hash(path)
            source_name = ('host_source' if role.startswith('host:') else 'adapter_source')
            expected_source = (placements[role.split(':', 1)[1]][source_name]
                               if ':' in role else shared[role])
            if sha != source[expected_source]:
                raise CompositeConnectedBindingError('composite_source_to_wheel_mismatch')
            origins[role] = {'path': str(path.resolve(strict=True)), 'sha256': sha,
                             'wheel_member': member}
    project = Path(package_plan['request']['package_directory']) / 'source/pyproject.toml'
    if (project.is_symlink() or file_hash(project) != source['pyproject.toml']
            or console['pyproject_sha256'] != source['pyproject.toml']):
        raise CompositeConnectedBindingError('composite_project_provenance_changed')
    for name in candidates:
        placements[name] = {'source_file': placements[name]['source_file'],
                            'reviewed_file_sha256': placements[name]['reviewed_file_sha256'],
                            'applied_file_sha256': placements[name]['applied_file_sha256'],
                            'origins': {'host': origins['host:' + name],
                                        'adapter': origins['adapter:' + name]}}
    origin_rows = {row['path']: row['sha256'] for row in origins.values()}
    if len(origin_rows) != len(origins):
        raise CompositeConnectedBindingError('composite_installed_origin_ambiguous')
    origin_rows[str(project.resolve(strict=True))] = source['pyproject.toml']
    report = {'schema_version': '1.0', 'kind': 'connected-installed-composite-binding-v1',
              'candidate_ids': candidates, 'selected_set_digest': package_plan['selected_set_digest'],
              'composite_bundle_digest': composite['contract_digest'],
              'package_plan_sha256': package_plan['plan_sha256'],
              'package_receipt_sha256': package_receipt['receipt_sha256'],
              'install_plan_sha256': install_plan['plan_sha256'],
              'install_receipt_sha256': install_receipt['receipt_sha256'],
              'wheel_sha256': package_receipt['wheel_sha256'],
              'installed_files_sha256': install_receipt['installed']['installed_files_sha256'],
              'site': str(site), 'placements': placements,
              'shared_origins': {'console': origins['console'], 'loader': origins['loader']},
              'reviewed_project_path': str(project.resolve(strict=True)),
              'reviewed_project_sha256': source['pyproject.toml'],
              'source_plan': {'files': [{'path': path, 'sha256': sha}
                                        for path, sha in sorted(origin_rows.items())]}}
    report['binding_sha256'] = digest(report)
    validate_contract(report, 'connected-installed-composite-binding-v1')
    return report
