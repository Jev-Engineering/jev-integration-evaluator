"""Exact, effect-free native Windows package plan for an already applied host."""
from __future__ import annotations

import importlib.metadata
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

from . import capabilities as cap
from .contracts import validate_contract
from .integrations.lifecycle import implementation_status
from .io import InputError, digest, file_hash
from .template_installation import _template_binding
from .windows_template_package_inputs import inspect_windows_template_package_inputs
from .windows_template_owned import (
    create_private_directory, check_private_directory,
    read_private_json, write_private_bytes_exclusive, write_private_json_exclusive,
)


_REQUEST = frozenset({
    'host_root', 'reviewed_source_files', 'implementation_bundle',
    'trusted_modified_receipt_sha256', 'template_directory',
    'wheelhouse', 'reviewed_wheels', 'output_parent', 'environment_parent',
    'console_script', 'interpreter', 'configuration',
    'reviewed_configuration_sha256',
})
_HEX = re.compile(r'^[0-9a-f]{64}$')


def _static_build_guard(source: Path, files: dict[str, str]) -> None:
    """Permit only static setuptools metadata in the copied source stage."""
    if {'setup.py', 'setup.cfg', 'MANIFEST.in'} & set(files):
        raise InputError('windows_package_executable_setup_unsupported')
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib
    raw = cap._windows_secure_input(source / 'pyproject.toml', 1_000_000)
    if hashlib.sha256(raw).hexdigest() != files['pyproject.toml']:
        raise InputError('windows_package_build_metadata_changed')
    try:
        document = tomllib.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError):
        raise InputError('windows_package_build_metadata_invalid') from None
    build = document.get('build-system')
    if (type(build) is not dict or set(build) != {'requires', 'build-backend'}
            or build['build-backend'] != 'setuptools.build_meta'):
        raise InputError('windows_package_nonstatic_build_unsupported')
    tool = document.get('tool', {})
    setuptools = tool.get('setuptools', {}) if type(tool) is dict else None
    if (type(setuptools) is not dict or set(setuptools) - {
            'packages', 'package-data', 'package-dir', 'include-package-data'}
            or any(key in document.get('project', {}) for key in ('dynamic',))):
        raise InputError('windows_package_nonstatic_build_unsupported')
    project = document['project']
    for key in ('readme', 'license'):
        value = project.get(key)
        if type(value) is str and key == 'readme':
            referenced = value
        elif type(value) is dict and 'file' in value:
            referenced = value['file']
        else:
            continue
        if type(referenced) is not str or referenced not in files:
            raise InputError('windows_package_external_metadata_file_unsupported')
    licenses = project.get('license-files', [])
    if (type(licenses) is not list or any(
            type(pattern) is not str or not re.fullmatch(r'[A-Za-z0-9_*?.-]+', pattern)
            for pattern in licenses)):
        raise InputError('windows_package_external_metadata_file_unsupported')
    def safe_relative(value: str) -> bool:
        if type(value) is not str or '\\' in value or ':' in value:
            return False
        if value == '.':
            return True
        parts = value.split('/')
        return (all(cap._windows_safe_component(part) for part in parts)
                and any(name.startswith(value + '/') for name in files))
    packages = setuptools.get('packages', {})
    if type(packages) is dict:
        if set(packages) != {'find'} or type(packages['find']) is not dict:
            raise InputError('windows_package_nonstatic_build_unsupported')
        finder = packages['find']
        if set(finder) - {'where', 'include', 'exclude', 'namespaces'}:
            raise InputError('windows_package_nonstatic_build_unsupported')
        where = finder.get('where', ['.'])
        if type(where) is not list or not where or any(
                item not in ('.', 'src') for item in where):
            raise InputError('windows_package_nonstatic_build_unsupported')
    elif type(packages) is not list or any(type(item) is not str for item in packages):
        raise InputError('windows_package_nonstatic_build_unsupported')
    package_dir = setuptools.get('package-dir', {})
    if (type(package_dir) is not dict or any(
            type(key) is not str or not safe_relative(value)
            for key, value in package_dir.items())):
        raise InputError('windows_package_nonstatic_build_unsupported')
    data = setuptools.get('package-data', {})
    if (type(data) is not dict or any(
            type(key) is not str or type(patterns) is not list or any(
                type(pattern) is not str or not re.fullmatch(r'[A-Za-z0-9_*?.-]+', pattern)
                for pattern in patterns)
            for key, patterns in data.items())
            or type(setuptools.get('include-package-data', False)) is not bool):
        raise InputError('windows_package_nonstatic_build_unsupported')


def plan_windows_template_package(request: dict) -> dict:
    """Bind native package inputs to an external modified receipt; grant no effects."""
    if type(request) is not dict or set(request) != _REQUEST:
        raise InputError('windows_package_request_invalid')
    if (type(request['trusted_modified_receipt_sha256']) is not str
            or not _HEX.fullmatch(request['trusted_modified_receipt_sha256'])
            or type(request['reviewed_configuration_sha256']) is not str
            or not _HEX.fullmatch(request['reviewed_configuration_sha256'])
            or type(request['configuration']) is not dict):
        raise InputError('windows_package_request_invalid')
    config = request['configuration']
    runtime = config.get('jev_runtime')
    if (digest(config) != request['reviewed_configuration_sha256']
            or set(config) != {'jev_runtime'} or type(runtime) is not dict
            or set(runtime) != {'mode', 'credential_ref'}
            or runtime['mode'] != 'off'
            or (runtime['credential_ref'] is not None and
                (type(runtime['credential_ref']) is not str or not re.fullmatch(
                    r'env:[A-Za-z_][A-Za-z0-9_]*', runtime['credential_ref'])))):
        raise InputError('windows_package_off_configuration_required')
    if (type(request['interpreter']) is not str
            or Path(request['interpreter']).absolute() != Path(sys.executable).absolute()):
        raise InputError('windows_package_interpreter_must_match_planner')
    inputs = inspect_windows_template_package_inputs(
        request['host_root'], request['reviewed_source_files'],
        request['wheelhouse'], request['reviewed_wheels'],
        request['output_parent'], request['environment_parent'],
        request['console_script'])
    _static_build_guard(Path(request['host_root']), inputs['source_files'])
    try:
        bundle, _, _ = cap._windows_check_directory_path(
            request['implementation_bundle'], purpose='input')
        template, _, _ = cap._windows_check_directory_path(
            request['template_directory'], purpose='input')
        roots = (request['host_root'], request['wheelhouse'], request['output_parent'],
                 request['environment_parent'], bundle, template)
        if any(cap._path_is_within(a, b) or cap._path_is_within(b, a)
               for index, a in enumerate(roots) for b in roots[index + 1:]):
            raise InputError('windows_package_input_output_overlap')
        status = implementation_status(
            request['host_root'], bundle,
            trusted_receipt_sha256=request['trusted_modified_receipt_sha256'])
        if (status['status'] != 'verified'
                or status['receipt_trust'] != 'externally_anchored_execution'):
            raise InputError('windows_package_applied_source_unverified')
        lock = _template_binding(Path(template))
        from .io import read_json
        spec = read_json(Path(bundle) / 'implementation-spec.json')
        if (lock['spec_sha256'] != digest(spec)
                or lock['candidate_id'] != spec['candidate_id']):
            raise InputError('windows_package_template_bundle_mismatch')
        build_pins = {}
        for row in inputs['build_requirements']:
            name, version = row.split('==', 1)
            build_pins[name] = version
            if importlib.metadata.version(name) != version:
                raise InputError('windows_package_build_tool_drift')
        wheel_names = {row['name'].lower().replace('_', '-') for row in inputs['wheel_files']}
        if len(wheel_names) != len(inputs['wheel_files']):
            raise InputError('windows_package_duplicate_wheel_distribution')
        if 'jev-integration-evaluator' not in wheel_names:
            raise InputError('windows_package_evaluator_wheel_missing')
        if not {'pip', 'setuptools', 'wheel'} <= wheel_names:
            raise InputError('windows_package_build_wheels_missing')
        for row in inputs['wheel_files']:
            name = row['name'].lower().replace('_', '-')
            if name in build_pins and row['version'] != build_pins[name]:
                raise InputError('windows_package_build_wheel_version_mismatch')
        evaluator = next(row for row in inputs['wheel_files']
                         if row['name'].lower().replace('_', '-') ==
                         'jev-integration-evaluator')
        evaluator_raw = cap._windows_secure_input(
            Path(request['wheelhouse']) / evaluator['filename'], 64_000_000)
        package_root = Path(__file__).resolve().parent
        expected_runtime = {p.relative_to(package_root.parent).as_posix(): file_hash(p)
                            for p in package_root.rglob('*')
                            if p.is_file() and (p.suffix == '.py' or
                                                p.parent == package_root / 'data' and
                                                p.suffix in ('.json', '.cjs'))}
        with zipfile.ZipFile(BytesIO(evaluator_raw)) as archive:
            names = [name for name in archive.namelist() if not name.endswith('/')]
            metadata_prefix = (f'jev_integration_evaluator-{evaluator["version"]}'
                               '.dist-info/')
            if any(not name.startswith(('jev_integration_evaluator/', metadata_prefix))
                   for name in names):
                raise InputError('windows_package_evaluator_wheel_extra_payload')
            actual_runtime = {name: hashlib.sha256(archive.read(name)).hexdigest()
                              for name in names if name.startswith('jev_integration_evaluator/')}
        if actual_runtime != expected_runtime:
            raise InputError('windows_package_evaluator_wheel_source_mismatch')
        body = {'schema_version': '1.0', 'kind': 'windows-template-package-plan-v1',
                'request': request, 'inputs': inputs,
                'implementation_bundle_digest': status['bundle_digest'],
                'template_lock_sha256': lock['lock_sha256'],
                'build_tool_versions': build_pins,
                'operations': ['copy_selected_reviewed_source', 'build_offline_wheel',
                               'hash_and_record_wheel'],
                'target_executed': False, 'runtime_activation_authorized': False}
        body['plan_sha256'] = digest(body)
        validate_contract(body, 'windows-template-package-plan-v1')
        return body
    except cap.CapabilityError as exc:
        raise InputError('windows_package_' + exc.code) from None
    except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile,
            importlib.metadata.PackageNotFoundError):
        raise InputError('windows_package_binding_unavailable') from None


def _generation(plan: dict) -> Path:
    return Path(plan['request']['output_parent']) / ('jev-package-' + plan['plan_sha256'][:24])


def _effect_environment(root: Path, scripts: Path) -> dict[str, str]:
    return {'SystemRoot': os.environ['SystemRoot'], 'WINDIR': os.environ['WINDIR'],
            'PATH': str(scripts), 'TEMP': str(root), 'TMP': str(root),
            'PIP_NO_INDEX': '1', 'PIP_CONFIG_FILE': os.devnull, 'PIP_NO_INPUT': '1',
            'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PYTHONNOUSERSITE': '1',
            'PYTHONDONTWRITEBYTECODE': '1'}


def _run(args: list[str], *, root: Path, scripts: Path, timeout: int = 180) -> None:
    try:
        completed = subprocess.run(args, cwd=root, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=_effect_environment(root, scripts), timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise InputError('windows_package_offline_command_failed') from None
    if completed.returncode != 0:
        raise InputError('windows_package_offline_command_failed')


def _copy_selected_source(plan: dict, staged: Path) -> None:
    """Copy only files the inventory hashed; excluded trees never reach hooks."""
    from .windows_template_package_inputs import _MAX_SOURCE_BYTES

    source = Path(plan['request']['host_root'])
    for relative, expected in plan['inputs']['source_files'].items():
        parts = relative.split('/')
        dest = staged.joinpath(*parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = cap._windows_secure_input(source.joinpath(*parts), _MAX_SOURCE_BYTES)
        if __import__('hashlib').sha256(raw).hexdigest() != expected:
            raise InputError('reviewed_windows_package_source_changed')
        _, io_path = cap._windows_absolute_path(dest)
        try:
            fd = cap._windows_create_private_file(io_path)
        except OSError:
            raise InputError('windows_package_staging_collision') from None
        try:
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise InputError('windows_package_staging_write_failed')
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        if file_hash(dest) != expected:
            raise InputError('windows_package_staged_source_drift')
    # Empty excluded directories and ambient files have no channel into the
    # isolated build source. A later source recheck catches target edits.


def _requirements_lock(rows: list[dict]) -> bytes:
    lines = []
    for row in sorted(rows, key=lambda item: item['name'].casefold()):
        name, version, sha = row['name'], row['version'], row['sha256']
        if any(ch in name + version for ch in '\r\n\\\"\' '):
            raise InputError('windows_package_requirement_invalid')
        lines.append(f'{name}=={version} --hash=sha256:{sha}\n')
    return ''.join(lines).encode('ascii')


def build_windows_template_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    """Run one offline wheel build; preserve an interrupted intent for review."""
    validate_contract(plan, 'windows-template-package-plan-v1')
    if (plan['plan_sha256'] != digest({k: v for k, v in plan.items() if k != 'plan_sha256'})
            or approved_plan_sha256 != plan['plan_sha256']):
        raise InputError('windows_package_exact_build_authority_required')
    current = plan_windows_template_package(plan['request'])
    if current != plan:
        raise InputError('windows_package_plan_drift')
    root = _generation(plan)
    if root.exists():
        raise InputError('windows_package_existing_generation_requires_status_review')
    owned = create_private_directory(root)
    write_private_json_exclusive(owned, 'owner.json', {'plan_sha256': plan['plan_sha256'],
                                                       'owned_directory': owned})
    write_private_json_exclusive(owned, 'build-intent.json',
                                 {'plan_sha256': plan['plan_sha256'], 'status': 'started'})
    staged = root / 'source'
    create_private_directory(staged)
    _copy_selected_source(plan, staged)
    # Repeat exact source and wheel checks after the copy, before effects.
    if inspect_windows_template_package_inputs(
            plan['request']['host_root'], plan['request']['reviewed_source_files'],
            plan['request']['wheelhouse'], plan['request']['reviewed_wheels'],
            plan['request']['output_parent'], plan['request']['environment_parent'],
            plan['request']['console_script']) != plan['inputs']:
        raise InputError('windows_package_inputs_changed_before_build')
    venv = root / 'build-venv'
    _run([sys.executable, '-I', '-m', 'venv', str(venv)], root=root,
         scripts=Path(sys.executable).parent)
    python = venv / 'Scripts/python.exe'
    if not python.is_file():
        raise InputError('windows_package_build_venv_incomplete')
    wheels = Path(plan['request']['wheelhouse'])
    tool_rows = [row for row in plan['inputs']['wheel_files']
                 if row['name'].lower().replace('_', '-') in {'pip', 'setuptools', 'wheel'}]
    if len(tool_rows) != 3:
        raise InputError('windows_package_build_wheels_missing')
    write_private_bytes_exclusive(owned, 'build-tools.lock', _requirements_lock(tool_rows))
    _run([str(python), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps',
          '--require-hashes', '--force-reinstall', '--find-links', str(wheels),
          '-r', str(root / 'build-tools.lock')],
         root=root, scripts=venv / 'Scripts')
    dist = root / 'dist'
    create_private_directory(dist)
    _run([str(python), '-I', '-m', 'pip', 'wheel', '--no-index', '--no-deps',
          '--no-build-isolation', '--wheel-dir', str(dist), str(staged)],
         root=root, scripts=venv / 'Scripts')
    produced = list(dist.glob('*.whl'))
    if len(produced) != 1:
        raise InputError('windows_package_expected_one_host_wheel')
    from .windows_template_package_inputs import _wheel_metadata
    wheel_bytes = cap._windows_secure_input(produced[0], 64_000_000)
    name, version = _wheel_metadata(wheel_bytes, produced[0].name)
    if (name.lower().replace('_', '-') != plan['inputs']['project_name'].lower().replace('_', '-')
            or version != plan['inputs']['project_version']):
        raise InputError('windows_package_host_wheel_metadata_changed')
    wheel_sha = __import__('hashlib').sha256(wheel_bytes).hexdigest()
    receipt = {'schema_version': '1.0', 'kind': 'windows-template-package-receipt-v1',
               'plan_sha256': plan['plan_sha256'], 'source_sha256': plan['inputs']['source_sha256'],
               'wheel_filename': produced[0].name, 'wheel_sha256': wheel_sha,
               'package_directory': str(root), 'owned_directory': owned,
               'runtime_activation_authorized': False}
    receipt['receipt_sha256'] = digest(receipt)
    write_private_json_exclusive(owned, 'package-receipt.json', receipt)
    return receipt


def windows_package_status(plan: dict, *, trusted_receipt_sha256: str | None = None) -> dict:
    """Read-only state; a pending intent never implies permission to replay hooks."""
    validate_contract(plan, 'windows-template-package-plan-v1')
    if plan['plan_sha256'] != digest({k: v for k, v in plan.items() if k != 'plan_sha256'}):
        raise InputError('windows_package_plan_digest_changed')
    root = _generation(plan)
    if not root.exists():
        return {'status': 'absent', 'receipt_trust': 'absent'}
    try:
        from .io import loads
        owner = loads(cap._windows_secure_input(root / 'owner.json', 1_000_000))
        owned = owner['owned_directory']
        check_private_directory(owned)
        if owner['plan_sha256'] != plan['plan_sha256'] or owned['path'] != str(root):
            raise InputError('windows_package_ownership_changed')
        intent = read_private_json(owned, 'build-intent.json')
        if intent != {'plan_sha256': plan['plan_sha256'], 'status': 'started'}:
            raise InputError('windows_package_intent_changed')
        receipt_path = root / 'package-receipt.json'
        if not receipt_path.exists():
            return {'status': 'blocked_recovery', 'receipt_trust': 'absent'}
        receipt = read_private_json(owned, 'package-receipt.json')
        validate_contract(receipt, 'windows-template-package-receipt-v1')
        if (receipt['receipt_sha256'] != digest({k: v for k, v in receipt.items()
                                                 if k != 'receipt_sha256'})
                or receipt['plan_sha256'] != plan['plan_sha256']
                or receipt['owned_directory'] != owned
                or receipt['package_directory'] != str(root)
                or receipt['source_sha256'] != plan['inputs']['source_sha256']):
            raise InputError('windows_package_receipt_changed')
        wheel = root / 'dist' / receipt['wheel_filename']
        if (not wheel.is_file() or wheel.is_symlink() or wheel.stat().st_nlink != 1
                or file_hash(wheel) != receipt['wheel_sha256']):
            raise InputError('windows_package_wheel_drift')
        return {'status': 'built_recorded',
                'receipt_trust': ('externally_anchored' if trusted_receipt_sha256 ==
                                  receipt['receipt_sha256'] else 'recorded_untrusted'),
                'receipt_sha256': receipt['receipt_sha256']}
    except (OSError, KeyError, TypeError, ValueError):
        raise InputError('windows_package_status_unavailable') from None
