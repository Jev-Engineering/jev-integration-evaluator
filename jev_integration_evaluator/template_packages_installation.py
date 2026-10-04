"""Genuine finite owner-package provenance using the trusted offline mechanics.

This package is a normal application console, separate from both installed
members. Its receipts prove bytes and metadata, never provider qualification.
"""
from __future__ import annotations

import importlib.metadata
from pathlib import Path
import re
import sys
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from packaging.utils import canonicalize_name

from . import template_installation as installer
from .contracts import seal, validate_contract, verify
from .io import InputError, digest, file_hash
from .template_packages_owner import OWNER_FILE, packages_owner_source_status


class PackagesOwnerInstallationError(InputError):
    """Bounded finite-owner packaging refusal."""


def plan_owner_package(request: dict, *, _allow_existing_output: bool = False) -> dict:
    """Read and bind a declarative owner package, without imports or execution."""
    try:
        return _plan_owner_package(request, _allow_existing_output=_allow_existing_output)
    except PackagesOwnerInstallationError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise PackagesOwnerInstallationError('packages_owner_package_inputs_unavailable') from None


def _plan_owner_package(request: dict, *, _allow_existing_output: bool) -> dict:
    validate_contract(request, 'packages-owner-package-request-v1')
    source = installer._absolute(request['host_root'])
    wheelhouse = installer._absolute(request['wheelhouse'])
    output = installer._absolute(request['package_directory'], exists=False)
    source_plan = request['owner_source_plan']
    source_receipt = request['owner_source_receipt']
    if (source != Path(source_plan['owner_root']) or (output.exists() and not _allow_existing_output)
            or any(output == root or output.is_relative_to(root) or root.is_relative_to(output)
                   for root in (source, wheelhouse))):
        raise PackagesOwnerInstallationError('packages_owner_package_output_collision')
    packages_owner_source_status(source_plan, source_receipt,
        trusted_receipt_sha256=request['trusted_owner_source_receipt_sha256'])
    files = installer._tree(source)
    if (set(files) != {'pyproject.toml', 'src/registered_packages/__init__.py', OWNER_FILE}
            or (source / 'src/registered_packages/__init__.py').read_bytes() != b''
            or digest(files) != request['reviewed_package_source_sha256']):
        raise PackagesOwnerInstallationError('packages_owner_declarative_source_required')
    project = tomllib.loads((source / 'pyproject.toml').read_text(encoding='utf-8'))
    if set(project) != {'build-system', 'project', 'tool'}:
        raise PackagesOwnerInstallationError('packages_owner_declarative_project_required')
    build = project['build-system']
    metadata = project['project']
    version = importlib.metadata.version('jev-integration-evaluator')
    if (build != {'requires': [f'setuptools=={request["build_tools"]["setuptools"]}',
                               f'wheel=={request["build_tools"]["wheel"]}'],
                  'build-backend': 'setuptools.build_meta'}
            or set(metadata) != {'name', 'version', 'requires-python', 'dependencies', 'scripts'}
            or metadata['name'] != 'jev-independent-registered-packages-owner'
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', metadata['version'])
            or metadata['requires-python'] != '>=3.13'
            or metadata['dependencies'] != [f'jev-integration-evaluator=={version}']
            or metadata['scripts'] != {'registered-packages': 'registered_packages.console:main'}
            or request['console_script'] != 'registered-packages'
            or project['tool'] != {'setuptools': {'packages': {'find': {'where': ['src']}}}}):
        raise PackagesOwnerInstallationError('packages_owner_project_profile_unsupported')
    profile = installer._profile()
    if Path(request['interpreter']).absolute() != Path(sys.executable).absolute():
        raise PackagesOwnerInstallationError('packages_owner_interpreter_mismatch')
    if set(request['build_tools']) != {'pip', 'setuptools', 'wheel'} or any(
            importlib.metadata.version(name) != pinned for name, pinned in request['build_tools'].items()):
        raise PackagesOwnerInstallationError('packages_owner_build_tool_drift')
    wheels = installer._wheel_rows(wheelhouse, request['wheels'])
    seen = set()
    for row in request['requirements']:
        if (row['wheel'] not in wheels or file_hash(wheels[row['wheel']]) != row['sha256']
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', row['name'])
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+!-]*', row['version'])):
            raise PackagesOwnerInstallationError('packages_owner_dependency_lock_mismatch')
        name, wheel_version = installer._wheel_identity(wheels[row['wheel']])
        normalized = canonicalize_name(name)
        if normalized != canonicalize_name(row['name']) or wheel_version != row['version'] or normalized in seen:
            raise PackagesOwnerInstallationError('packages_owner_dependency_metadata_mismatch')
        seen.add(normalized)
    if (set(wheels) != {row['wheel'] for row in request['requirements']}
            or 'jev-integration-evaluator' not in seen
            or request['configuration'] != {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
            or digest(request['configuration']) != request['reviewed_configuration_sha256']
            or request['secret_references']):
        raise PackagesOwnerInstallationError('packages_owner_off_configuration_required')
    plan = seal({'schema_version': '1.0', 'kind': 'packages-owner-package-plan-v1',
                 'request': request, 'source_files': files, 'source_sha256': digest(files),
                 'owner_source_plan_sha256': source_plan['plan_sha256'],
                 'owner_source_receipt_sha256': source_receipt['receipt_sha256'],
                 'project_name': metadata['name'], 'project_version': metadata['version'],
                 'entry_point': metadata['scripts']['registered-packages'], 'profile': profile,
                 'operations': ['copy_verified_source', 'build_offline_wheel', 'hash_and_record_wheel'],
                 'target_executed': False, 'runtime_activation_authorized': False}, 'plan_sha256')
    validate_contract(plan, plan['kind'])
    return plan


def build_owner_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    """Build only the exact declared finite owner; no member code is imported."""
    validate_contract(plan, 'packages-owner-package-plan-v1')
    return installer._build_package(plan, approved_plan_sha256=approved_plan_sha256)


def plan_owner_install(package_plan: dict, package_receipt: dict) -> dict:
    validate_contract(package_plan, 'packages-owner-package-plan-v1')
    return installer._plan_install(package_plan, package_receipt, composite=False)


def install_owner_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    validate_contract(plan, 'packages-owner-install-plan-v1')
    return installer._install_package(plan, approved_plan_sha256=approved_plan_sha256)


def owner_installation_status(plan: dict) -> dict:
    validate_contract(plan, 'packages-owner-install-plan-v1')
    verify(plan, 'plan_sha256')
    return installer.installation_status(plan)
