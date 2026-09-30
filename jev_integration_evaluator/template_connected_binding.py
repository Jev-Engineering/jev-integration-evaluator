"""Read-only source-to-installed mapping for a separately authorized connected launch.

The off-mode package and install receipts are provenance only.  This module
does not provision a key, construct a client, or grant exposure.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
from pathlib import Path
import zipfile

from .contracts import validate_contract
from .io import InputError, digest, file_hash, read_json
from .template_installation import (
    installation_status, package_status, plan_install,
)


class ConnectedBindingError(InputError):
    """Fixed diagnostic without source bytes or secret material."""


def _member(wheel: zipfile.ZipFile, name: str, record: dict[str, tuple[str, str]]) -> bytes:
    if name not in record or name not in wheel.namelist():
        raise ConnectedBindingError('installed_wheel_member_missing')
    raw = wheel.read(name)
    encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
    if record[name] != ('sha256=' + encoded, str(len(raw))):
        raise ConnectedBindingError('installed_wheel_record_mismatch')
    return raw


def derive_installed_binding(package_plan: dict, package_receipt: dict,
                             install_plan: dict, install_receipt: dict,
                             *, trusted_package_receipt_sha256: str,
                             trusted_install_receipt_sha256: str) -> dict:
    """Recompute an exact installed map from anchored off-mode generations.

    This is intentionally read-only.  External anchors must be retained by the
    caller; matching a self-reported receipt hash is never approval.
    """
    validate_contract(package_plan, 'template-package-plan-v1')
    validate_contract(package_receipt, 'template-package-receipt-v1')
    validate_contract(install_plan, 'template-install-plan-v1')
    validate_contract(install_receipt, 'template-install-receipt-v1')
    if (trusted_package_receipt_sha256 != package_receipt['receipt_sha256']
            or trusted_install_receipt_sha256 != install_receipt['receipt_sha256']
            or plan_install(package_plan, package_receipt) != install_plan
            or install_receipt['plan_sha256'] != install_plan['plan_sha256']
            or install_receipt['package_receipt_sha256'] != package_receipt['receipt_sha256']
            or package_status(package_plan)['status'] != 'built_recorded'
            or installation_status(install_plan)['status'] != 'installed_recorded'):
        raise ConnectedBindingError('installed_receipt_or_generation_unverified')
    root = Path(install_receipt['environment']).resolve(strict=True)
    if root.is_symlink() or root != Path(installation_status(install_plan)['environment']):
        raise ConnectedBindingError('installed_environment_origin_changed')
    source = package_plan['source_files']
    bundle = Path(package_plan['request']['implementation_bundle']).resolve(strict=True)
    spec = read_json(bundle / 'implementation-spec.json')
    if (spec.get('candidate_id') is None or spec.get('package_binding', {}).get('namespace') is not False
            or 'entrypoint_binding' not in spec or spec['source']['file'] not in source
            or 'pyproject.toml' not in source):
        raise ConnectedBindingError('installed_reviewed_binding_missing')
    source_module = spec['package_binding']['module']
    package_module = source_module.rpartition('.')[0]
    if not package_module:
        raise ConnectedBindingError('installed_regular_package_required')
    adapter_module = package_module + '.' + spec['output']['module']
    console_module = spec['entrypoint_binding']['module']
    members = {'host': source_module.replace('.', '/') + '.py',
               'adapter': adapter_module.replace('.', '/') + '.py',
               'console': console_module.replace('.', '/') + '.py'}
    loader_source = (Path(spec['source']['file']).parent / 'connected_authority.py').as_posix()
    if loader_source in source:
        members['loader'] = package_module.replace('.', '/') + '/connected_authority.py'
    if len(set(members.values())) != len(members):
        raise ConnectedBindingError('installed_module_mapping_ambiguous')
    wheel_path = (Path(package_plan['request']['package_directory']) /
                  package_receipt['wheel_filename']).resolve(strict=True)
    if wheel_path.is_symlink() or file_hash(wheel_path) != package_receipt['wheel_sha256']:
        raise ConnectedBindingError('installed_wheel_changed')
    origins = {}
    with zipfile.ZipFile(wheel_path) as wheel:
        records = [name for name in wheel.namelist() if name.endswith('.dist-info/RECORD')]
        if len(records) != 1:
            raise ConnectedBindingError('installed_wheel_record_missing')
        entries = list(csv.reader(io.StringIO(wheel.read(records[0]).decode('utf-8'))))
        if any(len(row) != 3 for row in entries) or len({row[0] for row in entries}) != len(entries):
            raise ConnectedBindingError('installed_wheel_record_invalid')
        record = {name: (hash_value, size) for name, hash_value, size in entries}
        site = Path(install_receipt['installed']['entrypoint_origin']).resolve(strict=True)
        relative_console = Path(members['console'])
        for _ in relative_console.parts:
            site = site.parent
        if (site.is_symlink() or not site.is_relative_to(root / 'venv')
                or site / relative_console != Path(install_receipt['installed']['entrypoint_origin'])):
            raise ConnectedBindingError('installed_entrypoint_origin_changed')
        installed_record = site / records[0]
        if installed_record.is_symlink() or not installed_record.is_file():
            raise ConnectedBindingError('installed_record_changed')
        installed_rows = list(csv.reader(io.StringIO(installed_record.read_text(encoding='utf-8'))))
        if (any(len(row) != 3 for row in installed_rows)
                or len({row[0] for row in installed_rows}) != len(installed_rows)):
            raise ConnectedBindingError('installed_record_changed')
        installed_entries = {name: (hash_value, size) for name, hash_value, size in installed_rows}
        for role, member in members.items():
            raw = _member(wheel, member, record)
            if installed_entries.get(member) != record[member]:
                raise ConnectedBindingError('installed_record_changed')
            path = site / member
            if (path.is_symlink() or not path.is_file() or path.read_bytes() != raw
                    or not path.resolve(strict=True).is_relative_to(site)):
                raise ConnectedBindingError('installed_module_bytes_changed')
            origins[role] = {'path': str(path.resolve(strict=True)),
                             'sha256': hashlib.sha256(raw).hexdigest(), 'wheel_member': member}
    if (origins['host']['sha256'] != source[spec['source']['file']]
            or origins['console']['sha256'] != source[spec['entrypoint_binding']['file']]
            or origins['adapter']['sha256'] != source[
                (Path(spec['source']['file']).parent / (spec['output']['module'] + '.py')).as_posix()]):
        raise ConnectedBindingError('installed_source_to_wheel_mismatch')
    if 'loader' in origins and origins['loader']['sha256'] != source[loader_source]:
        raise ConnectedBindingError('installed_source_to_wheel_mismatch')
    retained_project = Path(package_plan['request']['package_directory']) / 'source/pyproject.toml'
    if (retained_project.is_symlink() or file_hash(retained_project) != source['pyproject.toml']
            or spec['entrypoint_binding']['pyproject_sha256'] != source['pyproject.toml']):
        raise ConnectedBindingError('installed_project_provenance_changed')
    report = {'schema_version': '1.0', 'kind': 'connected-installed-binding-v1',
              'candidate_id': spec['candidate_id'], 'source_file': spec['source']['file'],
              'reviewed_file_sha256': spec['source']['file_sha256'],
              'applied_file_sha256': origins['host']['sha256'],
              'package_plan_sha256': package_plan['plan_sha256'],
              'package_receipt_sha256': package_receipt['receipt_sha256'],
              'install_plan_sha256': install_plan['plan_sha256'],
              'install_receipt_sha256': install_receipt['receipt_sha256'],
              'wheel_sha256': package_receipt['wheel_sha256'],
              'installed_files_sha256': install_receipt['installed']['installed_files_sha256'],
              'site': str(site), 'origins': origins,
              'reviewed_project_path': str(retained_project.resolve(strict=True)),
              'reviewed_project_sha256': source['pyproject.toml'],
              'source_plan': {'files': [
                  {'path': origins[role]['path'], 'sha256': origins[role]['sha256']}
                  for role in members
              ] + [{'path': str(retained_project.resolve(strict=True)),
                    'sha256': source['pyproject.toml']}]}}
    report['binding_sha256'] = digest(report)
    validate_contract(report, 'connected-installed-binding-v1')
    return report
