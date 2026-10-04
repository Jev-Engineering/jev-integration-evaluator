"""Offline, source-bound packaging and owned Linux CPython 3.13 installation.

Planning reads bytes. Build hooks and pip run only in explicit effect methods.
No operation activates the runtime or supplies a provider credential.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.metadata
from email.parser import BytesParser
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from packaging import tags
from packaging.utils import canonicalize_name, parse_wheel_filename

from .contracts import validate_contract, seal, verify
from .io import InputError, digest, file_hash, read_json, write_json
from .integrations.lifecycle import implementation_status


class InstallationError(InputError):
    """A fixed diagnostic without source, command output or secret values."""


_SKIP = {'.git', '.pytest_cache', '__pycache__', 'build', 'dist'}
_MAX_FILES = 4096
_MAX_BYTES = 64_000_000


def _package_contract(plan: dict) -> str:
    kind = plan.get('kind')
    if kind not in ('template-package-plan-v1', 'template-composite-package-plan-v1',
                    'packages-owner-package-plan-v1'):
        raise InstallationError('package_plan_kind_unsupported')
    return kind


def _install_contract(plan: dict) -> str:
    kind = plan.get('kind')
    if kind not in ('template-install-plan-v1', 'template-composite-install-plan-v1',
                    'packages-owner-install-plan-v1'):
        raise InstallationError('install_plan_kind_unsupported')
    return kind


def _installation_planner(plan: dict):
    if plan.get('kind') == 'packages-owner-install-plan-v1':
        from .template_packages_installation import plan_owner_install
        return plan_owner_install
    return plan_composite_install if plan.get('kind') == 'template-composite-install-plan-v1' else plan_install


@contextlib.contextmanager
def _effect_lock(parent: Path, key: str):
    import fcntl
    if any(part.is_symlink() for part in (parent, *parent.parents)):
        raise InstallationError('symlink_path_unsupported')
    info = parent.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise InstallationError('owned_parent_must_be_private')
    path = parent / ('.jev-' + key + '.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        lock = os.fstat(fd)
        if lock.st_uid != os.getuid() or lock.st_nlink != 1 or stat.S_IMODE(lock.st_mode) != 0o600:
            raise InstallationError('unsafe_install_lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise InstallationError('installation_busy') from None
        yield
    finally:
        os.close(fd)


def _journal(root: Path) -> list[dict]:
    path = root / 'journal.jsonl'
    if not path.exists():
        return []
    if path.is_symlink() or path.stat().st_size > 1_000_000:
        raise InstallationError('install_journal_invalid')
    raw = path.read_bytes()
    if raw and not raw.endswith(b'\n'):
        raise InstallationError('install_journal_torn')
    previous = None
    events = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
            saved = row.pop('record_sha256')
            if row['previous'] != previous or row['sequence'] != len(events) or digest(row) != saved:
                raise ValueError()
            row['record_sha256'] = saved
        except (ValueError, KeyError, TypeError):
            raise InstallationError('install_journal_invalid') from None
        events.append(row)
        previous = saved
    if len(events) > 64:
        raise InstallationError('install_journal_limit')
    return events


def _record(root: Path, plan_sha256: str, event: str) -> str:
    events = _journal(root)
    if events and any(row['plan_sha256'] != plan_sha256 for row in events):
        raise InstallationError('install_journal_plan_drift')
    row = {'sequence': len(events), 'previous': events[-1]['record_sha256'] if events else None,
           'plan_sha256': plan_sha256, 'event': event}
    row['record_sha256'] = digest(row)
    path = root / 'journal.jsonl'
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise InstallationError('install_journal_invalid')
        os.write(fd, (json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n').encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    return row['record_sha256']


def _owned_tree(root: Path, *, python: Path) -> str:
    """Snapshot bytes and reject links, mounts, hardlinks and unowned top-level files."""
    if root.is_symlink() or not root.is_dir() or os.path.ismount(root):
        raise InstallationError('unsafe_owned_generation')
    base_device = root.stat().st_dev
    records = []
    count = 0
    for base, dirs, names in os.walk(root, followlinks=False):
        for name in sorted(dirs + names):
            path = Path(base) / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            if info.st_dev != base_device or os.path.ismount(path):
                raise InstallationError('owned_generation_mount_detected')
            if stat.S_ISLNK(info.st_mode):
                dirs[:] = [d for d in dirs if d != name]
                expected_python_link = (rel.startswith('venv/bin/python') and
                                        path.resolve() == python.resolve())
                expected_lib_link = (rel == 'venv/lib64' and
                                     path.resolve() == (root / 'venv/lib').resolve())
                if not (expected_python_link or expected_lib_link):
                    raise InstallationError('unsafe_owned_generation_symlink')
                records.append((rel, 'link', os.readlink(path)))
            elif stat.S_ISDIR(info.st_mode):
                records.append((rel, 'directory', stat.S_IMODE(info.st_mode)))
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                records.append((rel, 'file', file_hash(path)))
            else:
                raise InstallationError('unsafe_owned_generation_entry')
            count += 1
            if count > 50000:
                raise InstallationError('owned_generation_size_limit')
    return digest(records)


def _absolute(value: str, *, exists: bool = True) -> Path:
    if type(value) is not str or not Path(value).is_absolute():
        raise InstallationError('absolute_path_required')
    path = Path(value).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise InstallationError('symlink_path_unsupported')
    if exists and not path.exists():
        raise InstallationError('required_path_missing')
    return path


def write_plan_exclusive(path: str | Path, plan: dict, *, host_root: str | Path) -> None:
    """Write a private plan once outside the reviewed host and all symlink paths."""
    output = _absolute(str(path), exists=False)
    host = _absolute(str(host_root))
    if output.exists() or output == host or output.is_relative_to(host):
        raise InstallationError('plan_output_collision_or_overlap')
    parent = output.parent
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise InstallationError('plan_parent_must_be_private')
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        raw = (json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def _tree(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise InstallationError('source_directory_required')
    result: dict[str, str] = {}
    total = 0
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP)
        for name in sorted(dirs + names):
            p = Path(base) / name
            if p.is_symlink():
                raise InstallationError('source_symlink_unsupported')
        for name in sorted(names):
            p = Path(base) / name
            if not p.is_file() or not stat.S_ISREG(p.stat().st_mode):
                raise InstallationError('source_nonregular_file')
            total += p.stat().st_size
            if len(result) >= _MAX_FILES or total > _MAX_BYTES:
                raise InstallationError('source_size_limit')
            result[p.relative_to(root).as_posix()] = file_hash(p)
    return result


def _profile() -> dict:
    if (sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'amd64')
            or sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 13)):
        raise InstallationError('linux_x86_64_cpython313_required')
    import sysconfig
    return {'python': '.'.join(map(str, sys.version_info[:3])),
            'soabi': sysconfig.get_config_var('SOABI'),
            'platform': sysconfig.get_platform(),
            'interpreter_sha256': file_hash(Path(sys.executable).resolve()),
            'executable_path': str(Path(sys.executable).absolute()),
            'sys_prefix': str(Path(sys.prefix).absolute())}


def _wheel_identity(path: Path) -> tuple[str, str]:
    try:
        parsed_name, parsed_version, _, wheel_tags = parse_wheel_filename(path.name)
        if not wheel_tags.intersection(tags.sys_tags()):
            raise InstallationError('wheel_abi_or_platform_unsupported')
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or any(
                    name.startswith('/') or '..' in Path(name).parts or '\\' in name for name in names):
                raise InstallationError('wheel_format_invalid')
            if (sum(entry.file_size for entry in entries) > 256_000_000 or
                    any(entry.file_size > 64_000_000 or stat.S_ISLNK(entry.external_attr >> 16)
                        for entry in entries)):
                raise InstallationError('wheel_size_or_link_unsupported')
            meta_names = [name for name in names if name.count('/') == 1 and name.endswith('.dist-info/METADATA')]
            wheel_names = [name for name in names if name.count('/') == 1 and name.endswith('.dist-info/WHEEL')]
            if len(meta_names) != 1 or len(wheel_names) != 1 or not any(
                    name.count('/') == 1 and name.endswith('.dist-info/RECORD') for name in names):
                raise InstallationError('wheel_format_invalid')
            meta = BytesParser().parsebytes(archive.read(meta_names[0]))
            name, version = meta['Name'], meta['Version']
            if not name or not version or canonicalize_name(name) != str(parsed_name) or str(parsed_version) != version:
                raise InstallationError('wheel_metadata_mismatch')
            return name, version
    except (zipfile.BadZipFile, UnicodeError, KeyError, ValueError) as exc:
        if isinstance(exc, InstallationError):
            raise
        raise InstallationError('wheel_format_invalid') from None


def _wheel_rows(wheelhouse: Path, rows: list) -> dict[str, Path]:
    if type(rows) is not list or not rows or len(rows) > 256:
        raise InstallationError('wheel_manifest_invalid')
    found = {}
    for row in rows:
        if (type(row) is not dict or set(row) != {'filename', 'sha256'}
                or type(row['filename']) is not str or Path(row['filename']).name != row['filename']
                or not row['filename'].endswith('.whl') or row['filename'] in found
                or type(row['sha256']) is not str or len(row['sha256']) != 64):
            raise InstallationError('wheel_manifest_invalid')
        p = wheelhouse / row['filename']
        if p.is_symlink() or not p.is_file() or file_hash(p) != row['sha256']:
            raise InstallationError('wheel_hash_drift')
        _wheel_identity(p)
        found[row['filename']] = p
    return found


def _pure_wheel(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            wheel_records = [name for name in names if name.count('/') == 1 and name.endswith('.dist-info/WHEEL')]
            if len(wheel_records) != 1 or any(name.endswith(('.so', '.pyd', '.dll', '.dylib')) for name in names):
                raise InstallationError('native_wheel_unsupported')
            metadata = archive.read(wheel_records[0]).decode('utf-8')
            if 'Root-Is-Purelib: true' not in metadata or not any(
                    line in metadata for line in ('Tag: py3-none-any', 'Tag: py313-none-any')):
                raise InstallationError('native_wheel_unsupported')
    except (zipfile.BadZipFile, UnicodeError, KeyError):
        raise InstallationError('wheel_format_invalid') from None


def _template_binding(directory: Path) -> dict:
    lock = read_json(directory / 'template-lock.json')
    validate_contract(lock, 'template-lock-v1')
    verify(lock, 'lock_sha256')
    marker = read_json(directory / 'render-status.json')
    if (marker.get('status') != 'complete' or marker.get('lock_sha256') != lock['lock_sha256']
            or marker.get('resources') != lock['owned_resources']):
        raise InstallationError('template_materialization_incomplete')
    for name, expected in lock['owned_resources'].items():
        p = directory / name
        if p.is_symlink() or not p.is_file() or file_hash(p) != expected:
            raise InstallationError('template_resource_drift')
    return lock


def plan_package(request: dict, *, _allow_existing_output: bool = False) -> dict:
    """Read-only plan for a pre-applied, independently verified host source."""
    validate_contract(request, 'template-package-request-v1')
    return _plan_package(request, composite=False, _allow_existing_output=_allow_existing_output)


def plan_composite_package(request: dict, *, _allow_existing_output: bool = False) -> dict:
    """Read-only package plan bound to an anchored verified composite bundle."""
    validate_contract(request, 'template-composite-package-request-v1')
    return _plan_package(request, composite=True, _allow_existing_output=_allow_existing_output)


def _plan_package(request: dict, *, composite: bool, _allow_existing_output: bool) -> dict:
    source = _absolute(request['host_root'])
    bundle = _absolute(request['implementation_bundle'])
    templates = ({candidate: _absolute(path) for candidate, path in request['template_directories'].items()}
                 if composite else {'single': _absolute(request['template_directory'])})
    wheelhouse = _absolute(request['wheelhouse'])
    output = _absolute(request['package_directory'], exists=False)
    if (output.exists() and not _allow_existing_output) or any(
            output == p or output.is_relative_to(p) or p.is_relative_to(output)
            for p in (source, bundle, wheelhouse, *templates.values())):
        raise InstallationError('package_output_collision_or_overlap')
    try:
        locks = {candidate: _template_binding(path) for candidate, path in templates.items()}
        if composite:
            from .integrations.composite import status_composite
            status = status_composite(source, bundle,
                                      trusted_receipt_sha256=request['trusted_modified_receipt_sha256'])
        else:
            status = implementation_status(source, bundle,
                                           trusted_receipt_sha256=request['trusted_modified_receipt_sha256'])
    except (OSError, ValueError, KeyError, TypeError):
        raise InstallationError('template_or_applied_source_verification_failed') from None
    if status['status'] != 'verified' or status['receipt_trust'] != 'externally_anchored_execution':
        raise InstallationError('applied_source_unverified')
    if composite:
        composite_plan = read_json(bundle / 'composite-plan.json')
        specs = read_json(bundle / 'specifications.json')
        report = read_json(bundle / 'composite-console.json')
        if (set(locks) != set(composite_plan['candidate_ids']) or
                set(specs) != set(locks) or len(locks) != 2 or
                status['bundle_digest'] != composite_plan['contract_digest'] or
                status['selected_set_digest'] != composite_plan['selected_set_digest'] or
                report['candidate_ids'] != composite_plan['candidate_ids'] or
                report['selected_set_digest'] != composite_plan['selected_set_digest'] or
                report['script'] != request['console_script'] or
                any(locks[candidate]['spec_sha256'] != digest(specs[candidate]) or
                    locks[candidate]['candidate_id'] != candidate
                    for candidate in locks)):
            raise InstallationError('composite_template_bundle_binding_mismatch')
        lock_identity = digest({candidate: locks[candidate]['lock_sha256'] for candidate in sorted(locks)})
    else:
        spec = read_json(bundle / 'implementation-spec.json')
        lock = locks['single']
        if lock['spec_sha256'] != digest(spec) or lock['candidate_id'] != spec['candidate_id']:
            raise InstallationError('template_bundle_binding_mismatch')
        lock_identity = lock['lock_sha256']
    files = _tree(source)
    if digest(files) != request['reviewed_package_source_sha256']:
        raise InstallationError('reviewed_package_source_drift')
    if 'pyproject.toml' not in files:
        raise InstallationError('pyproject_missing')
    if composite and file_hash(source / 'pyproject.toml') != report['pyproject_sha256']:
        raise InstallationError('composite_console_project_drift')
    _profile()
    import tomllib
    try:
        project = tomllib.loads((source / 'pyproject.toml').read_text(encoding='utf-8'))
    except (tomllib.TOMLDecodeError, UnicodeError):
        raise InstallationError('invalid_pyproject_toml') from None
    build = project.get('build-system', {})
    metadata = project.get('project', {})
    scripts = metadata.get('scripts', {})
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', request['console_script'])
            or request['console_script'] in ('.', '..')):
        raise InstallationError('console_script_name_invalid')
    if (build.get('build-backend') != 'setuptools.build_meta'
            or metadata.get('dynamic') or type(metadata.get('name')) is not str
            or type(metadata.get('version')) is not str
            or type(scripts) is not dict or request['console_script'] not in scripts
            or type(scripts[request['console_script']]) is not str
            or ':' not in scripts[request['console_script']]):
        raise InstallationError('unsupported_pyproject_profile')
    if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',
                        scripts[request['console_script']], flags=re.ASCII):
        raise InstallationError('console_entry_target_invalid')
    if sorted(build.get('requires', [])) != sorted(
            f'{name}=={request["build_tools"][name]}' for name in ('setuptools', 'wheel')):
        raise InstallationError('unpinned_build_backend')
    profile = _profile()
    if Path(request['interpreter']).absolute() != Path(sys.executable).absolute():
        raise InstallationError('interpreter_must_match_planner')
    wheels = _wheel_rows(wheelhouse, request['wheels'])
    if not {'pip', 'setuptools', 'wheel'} <= set(request['build_tools']):
        raise InstallationError('build_tool_pins_missing')
    for name, version in request['build_tools'].items():
        try:
            if type(version) is not str or importlib.metadata.version(name) != version:
                raise InstallationError('build_tool_version_drift')
        except importlib.metadata.PackageNotFoundError:
            raise InstallationError('build_tool_missing') from None
    seen_requirements = set()
    for row in request['requirements']:
        if not (re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', row['name'])
                and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+!-]*', row['version'])):
            raise InstallationError('requirements_lock_invalid')
        if row['wheel'] not in wheels or row['sha256'] != file_hash(wheels[row['wheel']]):
            raise InstallationError('requirements_wheel_mismatch')
        actual_name, actual_version = _wheel_identity(wheels[row['wheel']])
        normalized = canonicalize_name(row['name'])
        if (normalized != canonicalize_name(actual_name) or row['version'] != actual_version
                or normalized in seen_requirements):
            raise InstallationError('requirements_metadata_mismatch')
        seen_requirements.add(normalized)
    if {row['wheel'] for row in request['requirements']} != set(wheels):
        raise InstallationError('wheel_manifest_lock_mismatch')
    if 'jev-integration-evaluator' not in {row['name'].lower().replace('_', '-') for row in request['requirements']}:
        raise InstallationError('evaluator_wheel_missing')
    config = request['configuration']
    if digest(config) != request['reviewed_configuration_sha256']:
        raise InstallationError('reviewed_configuration_drift')
    if config.get('jev_runtime', {}).get('mode') != 'off':
        raise InstallationError('connected_mode_requires_separate_validation')
    credential = config['jev_runtime'].get('credential_ref')
    if credential is not None and (type(credential) is not str or not re.fullmatch(
            r'env:[A-Za-z_][A-Za-z0-9_]*', credential)):
        raise InstallationError('inline_credential_unsupported')
    expected_references = {'credential': credential} if credential is not None else {}
    if request['secret_references'] != expected_references:
        raise InstallationError('configuration_secret_reference_mismatch')
    if any(not value.startswith('env:') or not value[4:].isidentifier()
           for value in request['secret_references'].values()):
        raise InstallationError('secret_reference_invalid')
    plan = {'schema_version': '1.0', 'kind': ('template-composite-package-plan-v1' if composite
                                            else 'template-package-plan-v1'),
            'request': request,
            'implementation_bundle_digest': status['bundle_digest'],
            'source_files': files, 'source_sha256': digest(files),
            'project_name': metadata['name'], 'project_version': metadata['version'],
            'entry_point': scripts[request['console_script']], 'profile': profile,
            'operations': ['copy_verified_source', 'build_offline_wheel', 'hash_and_record_wheel'],
            'target_executed': False, 'runtime_activation_authorized': False}
    if composite:
        plan.update(template_locks_sha256=lock_identity,
                    candidate_ids=composite_plan['candidate_ids'],
                    selected_set_digest=composite_plan['selected_set_digest'],
                    composite_console_sha256=report['file_sha256'])
    else:
        plan['template_lock_sha256'] = lock_identity
    plan = seal(plan, 'plan_sha256')
    validate_contract(plan, _package_contract(plan))
    return plan


def _check_package_plan(plan: dict) -> None:
    composite = plan.get('kind') == 'template-composite-package-plan-v1'
    validate_contract(plan, _package_contract(plan))
    verify(plan, 'plan_sha256')
    if plan.get('kind') == 'packages-owner-package-plan-v1':
        from .template_packages_installation import plan_owner_package
        planner = plan_owner_package
    else:
        planner = plan_composite_package if composite else plan_package
    current = planner(plan['request'], _allow_existing_output=True)
    if current != plan:
        raise InstallationError('package_plan_drift')


def _run(args: list[str], *, cwd: Path, timeout: int = 180) -> None:
    try:
        result = subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=_effect_env(cwd),
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise InstallationError('offline_command_failed') from None
    if result.returncode:
        raise InstallationError('offline_command_failed')


def _effect_env(directory: Path) -> dict[str, str]:
    """Use an isolated environment; ambient pip/Python/user config is excluded."""
    return {'HOME': str(directory), 'TMPDIR': str(directory), 'PATH':
            str(Path(sys.executable).parent) + ':/usr/bin:/bin',
            'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
            'PIP_NO_INDEX': '1', 'PIP_CONFIG_FILE': os.devnull,
            'PIP_NO_INPUT': '1', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
            'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}


def build_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    """Explicit build effect; a pending intent blocks automatic hook replay."""
    validate_contract(plan, 'template-package-plan-v1')
    return _build_package(plan, approved_plan_sha256=approved_plan_sha256)


def build_composite_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    """Build an anchored two-placement source without weakening single plans."""
    validate_contract(plan, 'template-composite-package-plan-v1')
    return _build_package(plan, approved_plan_sha256=approved_plan_sha256)


def _build_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    verify(plan, 'plan_sha256')
    parent = Path(plan['request']['package_directory']).parent
    with _effect_lock(parent, 'build-' + plan['plan_sha256'][:24]):
        return _build_package_locked(plan, approved_plan_sha256=approved_plan_sha256)


def _build_package_locked(plan: dict, *, approved_plan_sha256: str) -> dict:
    _check_package_plan(plan)
    if approved_plan_sha256 != plan['plan_sha256']:
        raise InstallationError('exact_build_authority_required')
    out = _absolute(plan['request']['package_directory'], exists=False)
    receipt_file = out / 'package-receipt.json'
    if out.exists():
        if (out.is_symlink() or not out.is_dir() or (out / 'build-intent.json').is_symlink()
                or not (out / 'build-intent.json').is_file() or
                read_json(out / 'build-intent.json') != {
                    'plan_sha256': plan['plan_sha256'], 'status': 'started'}):
            raise InstallationError('package_ownership_mismatch')
        events = _journal(out)
        if (not events or events[0]['event'] != 'build_started' or
                any(row['plan_sha256'] != plan['plan_sha256'] for row in events)):
            raise InstallationError('build_journal_plan_drift')
        if receipt_file.is_symlink() or not receipt_file.is_file():
            raise InstallationError('build_interrupted_review_required')
        receipt = read_json(receipt_file)
        _check_package_receipt(plan, receipt)
        return receipt
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(out, 0o700)
    write_json(out / 'build-intent.json', {'plan_sha256': plan['plan_sha256'], 'status': 'started'})
    _record(out, plan['plan_sha256'], 'build_started')
    source = Path(plan['request']['host_root'])
    staged = out / 'source'
    shutil.copytree(source, staged, ignore=shutil.ignore_patterns(*_SKIP), symlinks=False)
    if _tree(staged) != plan['source_files']:
        raise InstallationError('staged_source_drift')
    dist = out / 'dist'; dist.mkdir()
    _run([sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-deps',
          '--no-build-isolation', '--wheel-dir', str(dist), str(staged)], cwd=out)
    produced = list(dist.glob('*.whl'))
    if len(produced) != 1:
        raise InstallationError('expected_one_host_wheel')
    wheel = out / produced[0].name
    produced[0].replace(wheel)
    _pure_wheel(wheel)
    composite = plan['kind'] == 'template-composite-package-plan-v1'
    receipt_body = {'schema_version': '1.0',
                    'kind': _package_contract(plan).replace('-plan-', '-receipt-'),
                    'plan_sha256': plan['plan_sha256'], 'source_sha256': plan['source_sha256'],
                    'wheel_filename': wheel.name, 'wheel_sha256': file_hash(wheel),
                    'project_name': plan['project_name'], 'project_version': plan['project_version'],
                    'entry_point': plan['entry_point'], 'profile': plan['profile'],
                    'runtime_activation_authorized': False}
    if composite:
        receipt_body.update(candidate_ids=plan['candidate_ids'],
                            selected_set_digest=plan['selected_set_digest'],
                            composite_console_sha256=plan['composite_console_sha256'])
    receipt = seal(receipt_body, 'receipt_sha256')
    validate_contract(receipt, _package_contract(plan).replace('-plan-', '-receipt-'))
    write_json(receipt_file, receipt)
    _record(out, plan['plan_sha256'], 'build_completed')
    return receipt


def recover_package(plan: dict, *, approved_plan_sha256: str,
                    approved_generation_sha256: str | None = None) -> dict:
    """Adopt a verified wheel or remove an independently inspected owned partial build."""
    validate_contract(plan, _package_contract(plan))
    verify(plan, 'plan_sha256')
    parent = Path(plan['request']['package_directory']).parent
    with _effect_lock(parent, 'build-' + plan['plan_sha256'][:24]):
        _check_package_plan(plan)
        if approved_plan_sha256 != plan['plan_sha256']:
            raise InstallationError('exact_recovery_authority_required')
        root = Path(plan['request']['package_directory'])
        if not root.exists():
            return {'schema_version': '1.0', 'status': 'absent'}
        if root.is_symlink() or (root / 'build-intent.json').is_symlink() or read_json(root / 'build-intent.json') != {
                'plan_sha256': plan['plan_sha256'], 'status': 'started'}:
            raise InstallationError('package_ownership_mismatch')
        if (root / 'package-receipt.json').is_file():
            receipt = _build_package_locked(plan, approved_plan_sha256=approved_plan_sha256)
            return {'schema_version': '1.0', 'status': 'already_built',
                    'receipt_sha256': receipt['receipt_sha256']}
        built_wheels = list(root.glob('*.whl'))
        if len(built_wheels) > 1:
            raise InstallationError('unknown_package_generation_contents')
        if built_wheels:
            wheel = built_wheels[0]
            if wheel.is_symlink() or not wheel.is_file():
                raise InstallationError('unknown_package_generation_contents')
            name, version = _wheel_identity(wheel)
            if (canonicalize_name(name) != canonicalize_name(plan['project_name'])
                    or version != plan['project_version']):
                raise InstallationError('unknown_package_generation_contents')
            _pure_wheel(wheel)
        allowed = {'build-intent.json', 'journal.jsonl', 'source', 'dist'}
        allowed.update(p.name for p in built_wheels)
        if {p.name for p in root.iterdir()} - allowed:
            raise InstallationError('unknown_package_generation_contents')
        actual = _owned_tree(root, python=Path(sys.executable))
        if approved_generation_sha256 != actual:
            raise InstallationError('exact_generation_review_required')
        shutil.rmtree(root)
        return {'schema_version': '1.0', 'status': 'owned_incomplete_package_removed'}


def _check_package_receipt(plan: dict, receipt: dict) -> Path:
    composite = plan['kind'] == 'template-composite-package-plan-v1'
    validate_contract(receipt, _package_contract(plan).replace('-plan-', '-receipt-'))
    verify(receipt, 'receipt_sha256')
    if composite and (receipt['candidate_ids'] != plan['candidate_ids'] or
                      receipt['selected_set_digest'] != plan['selected_set_digest'] or
                      receipt['composite_console_sha256'] != plan['composite_console_sha256']):
        raise InstallationError('composite_package_receipt_binding_drift')
    name = receipt['wheel_filename']
    if Path(name).name != name or not name.endswith('.whl') or '/' in name or '\\' in name:
        raise InstallationError('package_wheel_filename_invalid')
    for key, expected in (('plan_sha256', plan['plan_sha256']),
                          ('source_sha256', plan['source_sha256']),
                          ('project_name', plan['project_name']),
                          ('project_version', plan['project_version']),
                          ('entry_point', plan['entry_point']), ('profile', plan['profile'])):
        if receipt[key] != expected:
            raise InstallationError('package_receipt_drift')
    wheel = Path(plan['request']['package_directory']) / name
    if wheel.is_symlink() or not wheel.is_file() or file_hash(wheel) != receipt['wheel_sha256']:
        raise InstallationError('package_artifact_drift')
    actual_name, actual_version = _wheel_identity(wheel)
    if canonicalize_name(actual_name) != canonicalize_name(plan['project_name']) or actual_version != plan['project_version']:
        raise InstallationError('package_wheel_metadata_mismatch')
    _pure_wheel(wheel)
    return wheel


def package_status(plan: dict) -> dict:
    """Read-only package status and exact owned-tree review digest."""
    validate_contract(plan, _package_contract(plan))
    verify(plan, 'plan_sha256')
    root = Path(plan['request']['package_directory'])
    if not root.exists():
        return {'schema_version': '1.0', 'status': 'absent',
                'generation_sha256': None, 'journal_head_sha256': None}
    try:
        if root.is_symlink() or (root / 'build-intent.json').is_symlink() or read_json(root / 'build-intent.json') != {
                'plan_sha256': plan['plan_sha256'], 'status': 'started'}:
            raise InstallationError('package_ownership_mismatch')
        generation = _owned_tree(root, python=Path(sys.executable))
        events = _journal(root)
        if not events or events[0]['event'] != 'build_started' or any(
                row['plan_sha256'] != plan['plan_sha256'] for row in events):
            raise InstallationError('build_journal_plan_drift')
        head = events[-1]['record_sha256'] if events else None
        if (root / 'package-receipt.json').is_file():
            _check_package_receipt(plan, read_json(root / 'package-receipt.json'))
            status = 'built_recorded'
        else:
            status = 'interrupted_recovery_required'
        return {'schema_version': '1.0', 'status': status,
                'generation_sha256': generation, 'journal_head_sha256': head}
    except (InputError, OSError, ValueError):
        return {'schema_version': '1.0', 'status': 'ownership_or_artifact_drift',
                'generation_sha256': None, 'journal_head_sha256': None}


def plan_install(package_plan: dict, package_receipt: dict) -> dict:
    """Read-only installation plan; no environment is created."""
    if package_plan.get('kind') != 'template-package-plan-v1':
        raise InstallationError('single_package_plan_required')
    return _plan_install(package_plan, package_receipt, composite=False)


def plan_composite_install(package_plan: dict, package_receipt: dict) -> dict:
    """Read-only install plan retaining both source placements and one generation."""
    if package_plan.get('kind') != 'template-composite-package-plan-v1':
        raise InstallationError('composite_package_plan_required')
    return _plan_install(package_plan, package_receipt, composite=True)


def _plan_install(package_plan: dict, package_receipt: dict, *, composite: bool) -> dict:
    _check_package_plan(package_plan)
    req = package_plan['request']
    _check_package_receipt(package_plan, package_receipt)
    if package_status(package_plan)['status'] != 'built_recorded':
        raise InstallationError('package_generation_unverified')
    parent = _environment_parent(req)
    body = {'schema_version': '1.0',
                 'kind': _package_contract(package_plan).replace('-package-', '-install-'),
                 'package_plan': package_plan, 'package_receipt': package_receipt,
                 'environment_parent': str(parent), 'wheelhouse': req['wheelhouse'],
                 'wheels': req['wheels'], 'requirements': req['requirements'],
                 'configuration': req['configuration'],
                 'secret_references': req['secret_references'],
                 'console_script': req['console_script'], 'profile': package_plan['profile'],
                 'operations': ['create_owned_venv', 'install_hash_checked_wheels',
                                'verify_metadata_and_import_origin', 'write_off_configuration'],
                 'runtime_activation_authorized': False}
    if composite:
        body.update(candidate_ids=package_plan['candidate_ids'],
                    selected_set_digest=package_plan['selected_set_digest'],
                    composite_bundle_digest=package_plan['implementation_bundle_digest'])
    plan = seal(body, 'plan_sha256')
    _check_environment_disjoint(plan)
    validate_contract(plan, _install_contract(plan))
    return plan


def _environment_parent(req: dict) -> Path:
    parent = _absolute(req['environment_parent'])
    info = parent.stat()
    if (not parent.is_dir() or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) != 0o700):
        raise InstallationError('environment_parent_invalid')
    return parent


def _check_environment_disjoint(plan: dict) -> None:
    req = plan['package_plan']['request']
    root = _environment(plan)
    if plan['kind'] == 'packages-owner-install-plan-v1':
        inputs = [Path(req[name]) for name in ('host_root', 'wheelhouse', 'package_directory')]
        inputs.append(Path(req['owner_source_receipt']['transaction_directory']))
        for member in req['owner_source_plan']['packages']:
            member_request = member['package_plan']['request']
            inputs.extend(Path(member_request[name]) for name in (
                'host_root', 'implementation_bundle', 'template_directory', 'package_directory'))
            inputs.append(Path(member['install_receipt']['environment']))
    else:
        inputs = [Path(req[name]) for name in ('host_root', 'implementation_bundle',
                                              'wheelhouse', 'package_directory')]
        if plan['kind'] == 'template-composite-install-plan-v1':
            inputs.extend(Path(path) for path in req['template_directories'].values())
        else:
            inputs.append(Path(req['template_directory']))
    if any(root == item or root.is_relative_to(item) or item.is_relative_to(root)
           for item in inputs):
        raise InstallationError('environment_generation_overlap')


def _environment(plan: dict) -> Path:
    return Path(plan['environment_parent']) / ('jev-env-' + plan['plan_sha256'][:24])


def _validate_venv(plan: dict, root: Path, *, execute_entrypoint_import: bool = True) -> dict:
    python = root / 'venv/bin/python'
    script = root / 'venv/bin' / plan['console_script']
    if (root.is_symlink() or (root / 'venv').is_symlink() or
            (root / 'venv/bin').is_symlink() or
            not python.is_symlink() or
            python.resolve() != Path(plan['profile']['executable_path']).resolve() or
            script.is_symlink() or not script.is_file() or
            not stat.S_ISREG(script.stat().st_mode) or script.stat().st_nlink != 1):
        raise InstallationError('installed_executable_origin_drift')
    if not python.is_file() or not script.is_file() or not (root / 'config.json').is_file():
        raise InstallationError('installed_environment_incomplete')
    if read_json(root / 'config.json') != plan['configuration']:
        raise InstallationError('installed_configuration_drift')
    code = '''import base64,hashlib,importlib,importlib.metadata as m,json,sys
from pathlib import Path
names=json.loads(sys.argv[1]); entry=json.loads(sys.argv[2]); base=Path(sys.argv[4]).resolve()
sys.path.insert(0,str(base/'lib/python3.13/site-packages'))
out={}; hashes={}
for name in names:
    dist=m.distribution(name); origin=Path(dist.locate_file('')).resolve()
    if not origin.is_relative_to(base): raise RuntimeError('distribution origin outside venv')
    if dist.files is None: raise RuntimeError('distribution RECORD absent')
    for item in dist.files:
        path=Path(dist.locate_file(item)).resolve()
        if not path.is_relative_to(base) or not path.is_file(): raise RuntimeError('distribution path outside venv')
        raw=path.read_bytes()
        if item.size is not None and len(raw)!=item.size: raise RuntimeError('RECORD size mismatch')
        if item.hash is not None:
            if item.hash.mode!='sha256': raise RuntimeError('unsupported RECORD hash')
            actual=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
            if actual!=item.hash.value: raise RuntimeError('RECORD hash mismatch')
        hashes[str(path.relative_to(base))]=hashlib.sha256(raw).hexdigest()
    out[name]={'version':dist.version,'origin':str(origin)}
host=m.distribution(entry['distribution'])
matches=[e for e in host.entry_points if e.group=='console_scripts' and e.name==entry['script']]
if len(matches)!=1 or matches[0].value!=entry['value']: raise RuntimeError('entry point metadata mismatch')
module_name,qualifier=entry['value'].split(':',1)
relative=module_name.replace('.','/')
candidates=[Path(host.locate_file(item)).resolve() for item in host.files
            if str(item).endswith(relative+'.py') or str(item).endswith(relative+'/__init__.py')]
if len(candidates)!=1: raise RuntimeError('entry module RECORD absent')
module_path=candidates[0]
if not module_path.is_relative_to(base): raise RuntimeError('entry module outside venv')
if sys.argv[3]=='1':
    module=importlib.import_module(module_name)
    if Path(module.__file__).resolve()!=module_path: raise RuntimeError('entry module origin mismatch')
    target=module
    for component in qualifier.split('.'):
        target=getattr(target,component)
    if not callable(target): raise RuntimeError('entry target not callable')
print(json.dumps({'distributions':out,'files_sha256':hashes,'entrypoint_origin':str(module_path)}))'''
    names = [row['name'] for row in plan['requirements']] + [plan['package_plan']['project_name']]
    try:
        entry = {'distribution': plan['package_plan']['project_name'],
                 'script': plan['console_script'], 'value': plan['package_plan']['entry_point']}
        result = subprocess.run([str(python), '-I', '-S', '-c', code, json.dumps(names), json.dumps(entry),
                                 '1' if execute_entrypoint_import else '0', str(root / 'venv')],
                                cwd=root, capture_output=True, text=True, timeout=60,
                                env=_effect_env(root))
        if result.returncode:
            raise InstallationError('installed_metadata_unavailable')
        metadata = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise InstallationError('installed_metadata_unavailable') from None
    expected = {row['name']: row['version'] for row in plan['requirements']}
    expected[plan['package_plan']['project_name']] = plan['package_plan']['project_version']
    for name, version in expected.items():
        row = metadata['distributions'].get(name)
        if row is None or row['version'] != version or not Path(row['origin']).resolve().is_relative_to((root / 'venv').resolve()):
            raise InstallationError('installed_distribution_drift')
    return {'python': str(python), 'console_script': str(script),
            'console_script_sha256': file_hash(script),
            'entrypoint_origin': metadata['entrypoint_origin'],
            'installed_files_sha256': digest(metadata['files_sha256']),
            'distributions': expected}


def install_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    """Explicit offline install; an incomplete generation is preserved for recovery."""
    validate_contract(plan, 'template-install-plan-v1')
    return _install_package(plan, approved_plan_sha256=approved_plan_sha256)


def install_composite_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    """Install a verified two-placement wheel into one owned offline environment."""
    validate_contract(plan, 'template-composite-install-plan-v1')
    return _install_package(plan, approved_plan_sha256=approved_plan_sha256)


def _install_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    verify(plan, 'plan_sha256')
    parent = Path(plan['environment_parent'])
    with _effect_lock(parent, 'install-' + plan['plan_sha256'][:24]):
        return _install_package_locked(plan, approved_plan_sha256=approved_plan_sha256)


def _install_package_locked(plan: dict, *, approved_plan_sha256: str) -> dict:
    composite = plan.get('kind') == 'template-composite-install-plan-v1'
    validate_contract(plan, _install_contract(plan))
    verify(plan, 'plan_sha256')
    if approved_plan_sha256 != plan['plan_sha256']:
        raise InstallationError('exact_install_authority_required')
    replanned = _installation_planner(plan)(plan['package_plan'], plan['package_receipt'])
    if replanned != plan:
        raise InstallationError('install_plan_drift')
    root = _environment(plan)
    if root.exists():
        if (root.is_symlink() or not root.is_dir() or (root / 'owner.json').is_symlink()
                or (root / 'install-receipt.json').is_symlink()
                or (root / 'config.json').is_symlink()
                or (root / 'venv').is_symlink()):
            raise InstallationError('environment_ownership_mismatch')
        marker = read_json(root / 'owner.json')
        if marker != {'schema_version': '1.0', 'plan_sha256': plan['plan_sha256']}:
            raise InstallationError('environment_ownership_mismatch')
        events = _journal(root)
        if (not events or events[0]['event'] != 'environment_created' or
                any(row['plan_sha256'] != plan['plan_sha256'] for row in events)):
            raise InstallationError('install_journal_plan_drift')
        receipt_file = root / 'install-receipt.json'
        if not receipt_file.is_file():
            raise InstallationError('install_interrupted_recovery_required')
        receipt = read_json(receipt_file)
        validate_contract(receipt, _install_contract(plan).replace('-plan-', '-receipt-'))
        verify(receipt, 'receipt_sha256')
        installed = _validate_venv(plan, root, execute_entrypoint_import=False)
        if receipt != _install_receipt(plan, root, installed):
            raise InstallationError('install_receipt_drift')
        _owned_tree(root, python=Path(sys.executable))
        return receipt
    root.mkdir(mode=0o700, exist_ok=False)
    os.chmod(root, 0o700)
    write_json(root / 'owner.json', {'schema_version': '1.0', 'plan_sha256': plan['plan_sha256']})
    _record(root, plan['plan_sha256'], 'environment_created')
    write_json(root / 'install-intent.json', {'schema_version': '1.0', 'phase': 'venv',
                                             'plan_sha256': plan['plan_sha256']})
    _record(root, plan['plan_sha256'], 'venv_started')
    _run([sys.executable, '-m', 'venv', str(root / 'venv')], cwd=root)
    _record(root, plan['plan_sha256'], 'venv_completed')
    python = root / 'venv/bin/python'
    wheelhouse = Path(plan['wheelhouse'])
    wheels = _wheel_rows(wheelhouse, plan['wheels'])
    lock = root / 'requirements.lock'
    lines = [f"{row['name']}=={row['version']} --hash=sha256:{row['sha256']}"
             for row in plan['requirements']]
    lock.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    write_json(root / 'install-intent.json', {'schema_version': '1.0', 'phase': 'dependencies',
                                             'plan_sha256': plan['plan_sha256']})
    _record(root, plan['plan_sha256'], 'dependencies_started')
    _run([str(python), '-m', 'pip', 'install', '--no-index', '--only-binary=:all:',
          '--require-hashes', '--find-links', str(wheelhouse), '-r', str(lock)], cwd=root)
    _record(root, plan['plan_sha256'], 'dependencies_completed')
    _wheel_rows(wheelhouse, plan['wheels'])
    host_wheel = Path(plan['package_plan']['request']['package_directory']) / plan['package_receipt']['wheel_filename']
    if file_hash(host_wheel) != plan['package_receipt']['wheel_sha256']:
        raise InstallationError('package_artifact_drift')
    write_json(root / 'install-intent.json', {'schema_version': '1.0', 'phase': 'host',
                                             'plan_sha256': plan['plan_sha256']})
    _record(root, plan['plan_sha256'], 'host_install_started')
    _run([str(python), '-m', 'pip', 'install', '--no-index', '--no-deps', str(host_wheel)], cwd=root)
    _record(root, plan['plan_sha256'], 'host_install_completed')
    _wheel_rows(wheelhouse, plan['wheels'])
    _check_package_receipt(plan['package_plan'], plan['package_receipt'])
    _run([str(python), '-m', 'pip', 'check'], cwd=root)
    write_json(root / 'config.json', plan['configuration'])
    installed = _validate_venv(plan, root)
    receipt = _install_receipt(plan, root, installed)
    validate_contract(receipt, _install_contract(plan).replace('-plan-', '-receipt-'))
    write_json(root / 'install-receipt.json', receipt)
    write_json(root / 'install-intent.json', {'schema_version': '1.0', 'phase': 'complete',
                                             'plan_sha256': plan['plan_sha256']})
    _record(root, plan['plan_sha256'], 'install_completed')
    return receipt


def _install_receipt(plan: dict, root: Path, installed: dict) -> dict:
    composite = plan['kind'] == 'template-composite-install-plan-v1'
    body = {'schema_version': '1.0',
                 'kind': _install_contract(plan).replace('-plan-', '-receipt-'),
                 'plan_sha256': plan['plan_sha256'],
                 'package_receipt_sha256': plan['package_receipt']['receipt_sha256'],
                 'environment': str(root), 'generation_id': root.name,
                 'configuration_sha256': digest(plan['configuration']),
                 'secret_references_sha256': digest(plan['secret_references']),
                 'installed': installed, 'mode': 'off', 'launched': False,
                 'provider_reachable': False, 'runtime_activation_authorized': False}
    if composite:
        body.update(candidate_ids=plan['candidate_ids'],
                    selected_set_digest=plan['selected_set_digest'],
                    composite_bundle_digest=plan['composite_bundle_digest'])
    return seal(body, 'receipt_sha256')


def recover_installation(plan: dict, *, approved_plan_sha256: str,
                         approved_generation_sha256: str | None = None) -> dict:
    """Adopt verified bytes or remove a separately inspected exact owned snapshot."""
    validate_contract(plan, 'template-install-plan-v1')
    return _recover_installation(plan, approved_plan_sha256=approved_plan_sha256,
                                 approved_generation_sha256=approved_generation_sha256)


def recover_composite_installation(plan: dict, *, approved_plan_sha256: str,
                                   approved_generation_sha256: str | None = None) -> dict:
    validate_contract(plan, 'template-composite-install-plan-v1')
    return _recover_installation(plan, approved_plan_sha256=approved_plan_sha256,
                                 approved_generation_sha256=approved_generation_sha256)


def _recover_installation(plan: dict, *, approved_plan_sha256: str,
                          approved_generation_sha256: str | None) -> dict:
    verify(plan, 'plan_sha256')
    parent = Path(plan['environment_parent'])
    with _effect_lock(parent, 'install-' + plan['plan_sha256'][:24]):
        return _recover_installation_locked(plan, approved_plan_sha256=approved_plan_sha256,
                                            approved_generation_sha256=approved_generation_sha256)


def _recover_installation_locked(plan: dict, *, approved_plan_sha256: str,
                                 approved_generation_sha256: str | None) -> dict:
    composite = plan.get('kind') == 'template-composite-install-plan-v1'
    validate_contract(plan, _install_contract(plan))
    verify(plan, 'plan_sha256')
    replanned = _installation_planner(plan)(plan['package_plan'], plan['package_receipt'])
    if approved_plan_sha256 != plan['plan_sha256'] or replanned != plan:
        raise InstallationError('exact_recovery_authority_required')
    root = _environment(plan)
    if not root.exists():
        return {'schema_version': '1.0', 'status': 'absent'}
    if (root.is_symlink() or (root / 'owner.json').is_symlink() or
            read_json(root / 'owner.json') != {'schema_version': '1.0', 'plan_sha256': plan['plan_sha256']}):
        raise InstallationError('environment_ownership_mismatch')
    if (root / 'install-receipt.json').exists():
        receipt = _install_package_locked(plan, approved_plan_sha256=approved_plan_sha256)
        return {'schema_version': '1.0', 'status': 'already_installed', 'receipt_sha256': receipt['receipt_sha256']}
    if {p.name for p in root.iterdir()} - {'owner.json', 'install-intent.json', 'journal.jsonl',
                                          'requirements.lock', 'venv', 'config.json'}:
        raise InstallationError('unknown_generation_contents')
    events = _journal(root)
    if not events or events[0]['event'] != 'environment_created':
        raise InstallationError('install_journal_missing_or_invalid')
    actual = _owned_tree(root, python=Path(sys.executable))
    if approved_generation_sha256 != actual:
        raise InstallationError('exact_generation_review_required')
    shutil.rmtree(root)
    return {'schema_version': '1.0', 'status': 'owned_incomplete_generation_removed'}


def installation_status(plan: dict) -> dict:
    """Read current owned bytes; a receipt alone does not establish health."""
    composite = plan.get('kind') == 'template-composite-install-plan-v1'
    validate_contract(plan, _install_contract(plan))
    verify(plan, 'plan_sha256')
    root = _environment(plan)
    if not root.exists():
        status = 'absent'
    elif root.is_symlink() or not (root / 'owner.json').is_file():
        status = 'ownership_unknown'
    elif read_json(root / 'owner.json').get('plan_sha256') != plan['plan_sha256']:
        status = 'ownership_mismatch'
    elif not (root / 'install-receipt.json').is_file():
        status = 'interrupted_recovery_required'
    else:
        try:
            receipt = read_json(root / 'install-receipt.json')
            validate_contract(receipt, _install_contract(plan).replace('-plan-', '-receipt-'))
            verify(receipt, 'receipt_sha256')
            if receipt != _install_receipt(plan, root, _validate_venv(plan, root,
                                                                       execute_entrypoint_import=False)):
                raise InstallationError('install_receipt_drift')
            status = 'installed_recorded'
        except (InputError, OSError, ValueError):
            status = 'installed_drift'
    generation_sha256 = None
    journal_head_sha256 = None
    if root.is_dir() and not root.is_symlink() and (root / 'owner.json').is_file():
        try:
            generation_sha256 = _owned_tree(root, python=Path(sys.executable))
            events = _journal(root)
            journal_head_sha256 = events[-1]['record_sha256'] if events else None
        except (InputError, OSError, ValueError):
            if status != 'installed_drift':
                status = 'ownership_or_journal_drift'
    return {'schema_version': '1.0', 'status': status, 'environment': str(root),
            'generation_sha256': generation_sha256,
            'journal_head_sha256': journal_head_sha256,
            'launched': False, 'provider_reachable': False, 'runtime_activation_authorized': False}


def composite_installation_status(plan: dict) -> dict:
    """Read-only status for one exact composite generation."""
    validate_contract(plan, 'template-composite-install-plan-v1')
    return installation_status(plan)
