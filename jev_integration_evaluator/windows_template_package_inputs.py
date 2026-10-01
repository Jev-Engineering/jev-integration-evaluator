"""Read-only native Windows package input inventory; no build/install authority."""
from __future__ import annotations

from email.parser import BytesParser
import hashlib
from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

from packaging import tags
from packaging.tags import parse_tag
from packaging.utils import canonicalize_name, parse_wheel_filename

from . import capabilities as cap
from .contracts import validate_contract
from .io import InputError, digest
from .windows_template_preflight import _case_colliding_names, _profile


_HEX = re.compile(r'^[0-9a-f]{64}$')
_SKIP = frozenset({'.git', '.pytest_cache', '__pycache__', 'build', 'dist'})
_MAX_SOURCE_FILES = 4096
_MAX_SOURCE_BYTES = 64_000_000
_MAX_WHEELS = 64
_MAX_WHEEL_BYTES = 64_000_000
_MAX_TOTAL_WHEEL_BYTES = 256_000_000
_MAX_DIRECTORY_ENTRIES = 8192
_MAX_DEPTH = 64


def _manifest(files: dict, *, wheels: bool) -> dict[str, str]:
    maximum = _MAX_WHEELS if wheels else _MAX_SOURCE_FILES
    if type(files) is not dict or not 1 <= len(files) <= maximum:
        raise InputError('invalid_windows_package_input_manifest')
    result = {}
    folded = set()
    for relative, expected in files.items():
        if (type(relative) is not str or type(expected) is not str
                or not _HEX.fullmatch(expected) or '\\' in relative or ':' in relative):
            raise InputError('invalid_windows_package_input_manifest')
        parts = PurePosixPath(relative).parts
        if (not parts or relative != '/'.join(parts)
                or any(not cap._windows_safe_component(part) for part in parts)
                or (wheels and (len(parts) != 1 or not relative.endswith('.whl')))
                or (not wheels and any(part in _SKIP for part in parts[:-1]))):
            raise InputError('invalid_windows_package_input_manifest')
        folded_name = relative.casefold()
        if folded_name in folded:
            raise InputError('case_ambiguous_windows_package_input_manifest')
        folded.add(folded_name)
        result[relative] = expected
    return dict(sorted(result.items()))


def _source_pass(root: Path, reviewed: dict[str, str]) -> tuple[dict[str, str], dict[str, bytes], dict[str, tuple[int, int]]]:
    observed: dict[str, str] = {}
    selected_bytes: dict[str, bytes] = {}
    directories: dict[str, tuple[int, int]] = {}
    total = 0

    entries_seen = 0

    def visit(directory: Path, relative: str, depth: int) -> None:
        nonlocal total
        nonlocal entries_seen
        if depth > _MAX_DEPTH or len(directories) >= _MAX_DIRECTORY_ENTRIES:
            raise InputError('windows_package_source_size_limit')
        cap._windows_check_directory_path(directory, purpose='input')
        info = os.lstat(directory)
        if cap._windows_reparse_reason(info) or not stat.S_ISDIR(info.st_mode):
            raise InputError('windows_package_source_directory_invalid')
        directories[relative] = cap._windows_file_identity(info)
        with os.scandir(directory) as stream:
            entries = []
            for entry in stream:
                entries_seen += 1
                if entries_seen > _MAX_DIRECTORY_ENTRIES:
                    raise InputError('windows_package_source_size_limit')
                entries.append(entry)
        entries.sort(key=lambda entry: entry.name.casefold())
        colliding = _case_colliding_names(entry.name for entry in entries)
        for entry in entries:
            name = entry.name
            if not cap._windows_safe_component(name) or name.casefold() in colliding:
                raise InputError('windows_package_source_name_ambiguous')
            child = directory / name
            child_rel = name if not relative else relative + '/' + name
            child_info = os.lstat(child)
            if cap._windows_reparse_reason(child_info):
                raise InputError('windows_package_source_reparse_point')
            if stat.S_ISDIR(child_info.st_mode):
                if name not in _SKIP:
                    visit(child, child_rel, depth + 1)
                continue
            if not stat.S_ISREG(child_info.st_mode):
                raise InputError('windows_package_source_nonregular')
            if child_rel not in reviewed:
                raise InputError('windows_package_source_manifest_incomplete')
            raw = cap._windows_secure_input(child, _MAX_SOURCE_BYTES)
            total += len(raw)
            if len(observed) >= _MAX_SOURCE_FILES or total > _MAX_SOURCE_BYTES:
                raise InputError('windows_package_source_size_limit')
            actual = hashlib.sha256(raw).hexdigest()
            if actual != reviewed[child_rel]:
                raise InputError('reviewed_windows_package_source_changed')
            observed[child_rel] = actual
            if child_rel == 'pyproject.toml':
                selected_bytes[child_rel] = raw
        if cap._windows_file_identity(os.lstat(directory)) != directories[relative]:
            raise InputError('windows_package_source_directory_changed')

    visit(root, '', 0)
    if observed != reviewed:
        raise InputError('windows_package_source_manifest_incomplete')
    return observed, selected_bytes, directories


def _wheel_metadata(raw: bytes, filename: str) -> tuple[str, str]:
    try:
        parsed_name, parsed_version, _, filename_tags = parse_wheel_filename(filename)
        if not filename_tags.intersection(tags.sys_tags()):
            raise InputError('windows_package_wheel_tag_unsupported')
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (not entries or len(entries) > 8192
                    or len(names) != len({name.casefold() for name in names})
                    or sum(row.file_size for row in entries) > 256_000_000):
                raise InputError('windows_package_wheel_format_invalid')
            for row in entries:
                parts = PurePosixPath(row.filename.rstrip('/')).parts
                if (not parts or row.filename.startswith('/') or '\\' in row.filename
                        or any(not cap._windows_safe_component(part) for part in parts)
                        or row.file_size > 64_000_000
                        or stat.S_ISLNK(row.external_attr >> 16)):
                    raise InputError('windows_package_wheel_format_invalid')
            metadata_names = [name for name in names if name.count('/') == 1
                              and name.endswith('.dist-info/METADATA')]
            wheel_names = [name for name in names if name.count('/') == 1
                           and name.endswith('.dist-info/WHEEL')]
            record_names = [name for name in names if name.count('/') == 1
                            and name.endswith('.dist-info/RECORD')]
            if len(metadata_names) != 1 or len(wheel_names) != 1 or len(record_names) != 1:
                raise InputError('windows_package_wheel_format_invalid')
            with archive.open(metadata_names[0]) as stream:
                metadata_bytes = stream.read(1_000_001)
            with archive.open(wheel_names[0]) as stream:
                wheel_bytes = stream.read(65_537)
            if len(metadata_bytes) > 1_000_000 or len(wheel_bytes) > 65_536:
                raise InputError('windows_package_wheel_format_invalid')
            metadata = BytesParser().parsebytes(metadata_bytes)
            wheel = BytesParser().parsebytes(wheel_bytes)
            internal_tags = set()
            for value in wheel.get_all('Tag', []):
                internal_tags.update(parse_tag(value))
            if not internal_tags or not internal_tags.intersection(filename_tags & set(tags.sys_tags())):
                raise InputError('windows_package_wheel_tag_unsupported')
            name, version = metadata.get('Name'), metadata.get('Version')
            if (not name or not version or canonicalize_name(name) != str(parsed_name)
                    or version != str(parsed_version)):
                raise InputError('windows_package_wheel_metadata_mismatch')
            return name, version
    except InputError:
        raise
    except (zipfile.BadZipFile, UnicodeError, KeyError, ValueError, RuntimeError):
        raise InputError('windows_package_wheel_format_invalid') from None


def inspect_windows_template_package_inputs(host_root: str | Path,
                                            reviewed_source_files: dict[str, str],
                                            wheelhouse: str | Path,
                                            reviewed_wheels: dict[str, str],
                                            output_parent: str | Path,
                                            environment_parent: str | Path,
                                            console_script: str) -> dict:
    """Inspect reviewed files in the declared traversal and selected wheels on NTFS."""
    profile = _profile()
    source_files = _manifest(reviewed_source_files, wheels=False)
    wheels = _manifest(reviewed_wheels, wheels=True)
    if ('pyproject.toml' not in source_files or type(console_script) is not str
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', console_script)):
        raise InputError('windows_package_console_manifest_invalid')
    opened = []
    try:
        source, source_handle, source_info = cap._secure_windows_root(host_root)
        opened.append((source, source_handle, source_info))
        wheel_root, wheel_handle, wheel_info = cap._secure_windows_root(wheelhouse)
        opened.append((wheel_root, wheel_handle, wheel_info))
        output, _, _ = cap._windows_check_directory_path(output_parent, purpose='output')
        environment, _, _ = cap._windows_check_directory_path(environment_parent, purpose='output')
        paths = (source, wheel_root, Path(output), Path(environment))
        if any(cap._path_is_within(left, right) or cap._path_is_within(right, left)
               for index, left in enumerate(paths) for right in paths[index + 1:]):
            raise InputError('windows_package_input_output_overlap')
        source_directories = None
        metadata = None
        for _ in (1, 2):
            observed, selected, current_directories = _source_pass(source, source_files)
            if source_directories is not None and current_directories != source_directories:
                raise InputError('windows_package_source_directory_changed')
            source_directories = current_directories
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib
            try:
                document = tomllib.loads(selected['pyproject.toml'].decode('utf-8'))
                project = document['project']
                build = document['build-system']
                if type(project) is not dict or type(build) is not dict:
                    raise ValueError('metadata tables')
                scripts = project['scripts']
                if type(scripts) is not dict:
                    raise ValueError('scripts table')
                entry_point = scripts[console_script]
                project_name, project_version = project['name'], project['version']
                requirements = build['requires']
                if (type(project_name) is not str or not project_name
                        or type(project_version) is not str or not project_version
                        or project.get('dynamic') or build.get('build-backend') != 'setuptools.build_meta'
                        or type(requirements) is not list or len(requirements) != 2
                        or any(type(item) is not str or not re.fullmatch(
                            r'(setuptools|wheel)==[A-Za-z0-9][A-Za-z0-9._+!-]*', item)
                            for item in requirements)
                        or {item.split('==', 1)[0] for item in requirements} != {'setuptools', 'wheel'}
                        or type(entry_point) is not str or not re.fullmatch(
                        r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',
                        entry_point, flags=re.ASCII)):
                    raise ValueError('entry point')
            except (KeyError, TypeError, ValueError, UnicodeError, tomllib.TOMLDecodeError):
                raise InputError('windows_package_console_metadata_invalid') from None
            current_metadata = (project_name, project_version, tuple(sorted(requirements)),
                                entry_point)
            if metadata is not None and metadata != current_metadata:
                raise InputError('windows_package_console_metadata_changed')
            metadata = current_metadata
            wheel_total = 0
            wheel_rows = []
            for filename, expected in wheels.items():
                raw = cap._windows_secure_input(wheel_root / filename, _MAX_WHEEL_BYTES)
                wheel_total += len(raw)
                if wheel_total > _MAX_TOTAL_WHEEL_BYTES:
                    raise InputError('windows_package_wheel_size_limit')
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise InputError('reviewed_windows_package_wheel_changed')
                name, version = _wheel_metadata(raw, filename)
                wheel_rows.append({'filename': filename, 'sha256': expected,
                                   'name': name, 'version': version})
            for root, handle, initial in opened:
                try:
                    cap._verify_root(root, handle, initial)
                except (cap.CapabilityError, OSError):
                    raise InputError('windows_package_input_root_changed') from None
        for root, handle, initial in opened:
            try:
                cap._verify_root(root, handle, initial)
            except (cap.CapabilityError, OSError):
                raise InputError('windows_package_input_root_changed') from None
        report = {'schema_version': '1.0', 'status': 'package_inputs_reviewed_only',
                  'profile': profile, 'source_files': observed,
                  'source_traversal_exclusions': sorted(_SKIP),
                  'source_sha256': digest(observed), 'wheel_files': wheel_rows,
                  'wheels_sha256': digest(wheels), 'console_script': console_script,
                  'project_name': metadata[0], 'project_version': metadata[1],
                  'build_requirements': list(metadata[2]), 'entry_point': metadata[3],
                  'interpreter': str(Path(sys.executable).absolute()),
                  'interpreter_sha256': hashlib.sha256(
                      cap._windows_secure_input(Path(sys.executable), 64_000_000)).hexdigest(),
                  'target_modified': False, 'target_executed': False,
                  'build_authorized': False, 'install_authorized': False,
                  'launch_authorized': False, 'output_private_creation': 'pending',
                  'execution_boundary': 'trusted_local_host_no_isolation'}
        validate_contract(report, 'windows-template-package-inputs-v1')
        return report
    except cap.CapabilityError as exc:
        raise InputError('windows_package_' + exc.code) from None
    except OSError as exc:
        raise InputError('windows_package_' + cap._windows_oserror_reason(exc)) from None
    finally:
        for _, handle, _ in reversed(opened):
            os.close(handle.fd)
