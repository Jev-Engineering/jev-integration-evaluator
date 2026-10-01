"""Read-only native Windows preparation for a reviewed Python console host.

This is a source/path inspection receipt, not apply, installation, isolation,
or launch authority. Full Windows delivery requires a separate owned adapter.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys

from . import capabilities as cap
from .contracts import validate_contract
from .io import InputError, digest

_HEX = re.compile(r'^[0-9a-f]{64}$')
_MAX_FILES = 32
_MAX_FILE_BYTES = 2_000_000
_MAX_TOTAL_BYTES = 16_000_000


def _profile() -> dict:
    if os.name != 'nt' or sys.implementation.name != 'cpython':
        raise InputError('native_windows_preflight_required')
    version = sys.getwindowsversion()
    build = version.build
    product_type = version.product_type
    if (platform.machine().lower() not in ('amd64', 'x86_64')
            or ((product_type == 1 and build < 22000)
                or (product_type != 1 and build != 20348))
            or sys.version_info[:2] not in ((3, 10), (3, 13), (3, 14))):
        raise InputError('unsupported_native_windows_preflight_profile')
    return {'os': 'windows_11' if product_type == 1 else 'windows_server_2022',
            'build': build, 'architecture': 'x86_64',
            'python': '.'.join(map(str, sys.version_info[:3])), 'filesystem': 'local_ntfs'}


def _checked_files(files: dict[str, str]) -> dict[str, str]:
    if type(files) is not dict or not 1 <= len(files) <= _MAX_FILES:
        raise InputError('invalid_windows_source_manifest')
    result = {}
    folded = set()
    for relative, expected in files.items():
        if (type(relative) is not str or type(expected) is not str
                or not _HEX.fullmatch(expected) or '\\' in relative or ':' in relative):
            raise InputError('invalid_windows_source_manifest')
        parts = PurePosixPath(relative).parts
        if (not parts or relative != '/'.join(parts)
                or any(part in ('', '.', '..') or not cap._windows_safe_component(part)
                       for part in parts)):
            raise InputError('invalid_windows_source_manifest')
        key = relative.casefold()
        if key in folded:
            raise InputError('case_ambiguous_windows_source_manifest')
        folded.add(key)
        result[relative] = expected
    return dict(sorted(result.items()))


def _case_colliding_names(names) -> frozenset:
    """Case-folded names carried by more than one entry of one directory."""
    seen: set = set()
    colliding = set()
    for name in names:
        key = name.casefold()
        if key in seen:
            colliding.add(key)
        seen.add(key)
    return frozenset(colliding)


def refuse_case_alias(root: str | Path, relative: str, prefix: str) -> None:
    """Refuse a selected target whose path component has an on-disk case alias.

    Read-only. A per-directory case-sensitive NTFS directory can hold two
    entries that differ only by case; a selected spelling is then ambiguous
    for every case-insensitive consumer. A new name beside a differently
    cased entry in such a directory is refused for the same reason.
    """
    directory = Path(root)
    for part in PurePosixPath(relative).parts:
        key = part.casefold()
        try:
            _, io_path = cap._windows_absolute_path(directory)
            with os.scandir(io_path) as stream:
                names = [entry.name for entry in stream if entry.name.casefold() == key]
            absent = (bool(names) and part not in names
                      and not os.path.lexists(os.path.join(io_path, part)))
        except (FileNotFoundError, NotADirectoryError):
            # Nothing is listed below a missing parent; later exact checks decide.
            return
        except cap.CapabilityError as exc:
            raise InputError(prefix + exc.code) from None
        except OSError as exc:
            raise InputError(prefix + cap._windows_oserror_reason(
                exc, directory=True)) from None
        if _case_colliding_names(names) or absent:
            raise InputError(prefix + 'case_alias_refused')
        directory = directory / part


def inspect_windows_template_source(root: str | Path, files: dict[str, str],
                                    output_parent: str | Path) -> dict:
    """Check selected exact source bytes and external NTFS path without writing.

    ``files`` is an independently retained map of normalized relative paths to
    SHA-256 digests. This function does not authenticate who approved that map.
    """
    profile = _profile()
    checked = _checked_files(files)
    directory = None
    try:
        root_path, directory, initial = cap._secure_windows_root(root)
        output, _, _ = cap._windows_check_directory_path(output_parent, purpose='output')
        if (cap._path_is_within(output, root_path)
                or cap._path_is_within(root_path, output)):
            raise InputError('windows_output_overlaps_source')
        root_identity = cap._windows_file_identity(initial)
        observed = {}
        for pass_number in (1, 2):
            total = 0
            for relative, expected in checked.items():
                path = root_path.joinpath(*PurePosixPath(relative).parts)
                refuse_case_alias(root_path, relative, 'windows_preflight_')
                raw = cap._windows_secure_input(path, _MAX_FILE_BYTES)
                total += len(raw)
                if total > _MAX_TOTAL_BYTES:
                    raise InputError('windows_source_byte_budget')
                actual = hashlib.sha256(raw).hexdigest()
                if actual != expected:
                    raise InputError('reviewed_windows_source_changed')
                if pass_number == 1:
                    observed[relative] = actual
            if cap._windows_file_identity(os.fstat(directory.fd)) != root_identity:
                raise InputError('windows_source_root_changed')
            # The held handle can still refer to the old directory after a
            # lexical rename/replacement. Reopen the original path and compare
            # its final handle path and file ID before trusting this pass.
            try:
                cap._verify_root(root_path, directory, initial)
            except (cap.CapabilityError, OSError):
                raise InputError('windows_source_root_changed') from None
        try:
            cap._verify_root(root_path, directory, initial)
        except (cap.CapabilityError, OSError):
            raise InputError('windows_source_root_changed') from None
        report = {'schema_version': '1.0', 'status': 'preparation_only',
                'profile': profile, 'source_manifest_sha256': digest(checked),
                'source_files': observed, 'file_count': len(observed),
                'target_modified': False, 'target_executed': False,
                'apply_authorized': False, 'install_authorized': False,
                'launch_authorized': False, 'output_private_creation': 'pending',
                'execution_boundary': 'trusted_local_host_no_isolation'}
        validate_contract(report, 'windows-template-preflight-v1')
        return report
    except cap.CapabilityError as exc:
        raise InputError('windows_preflight_' + exc.code) from None
    finally:
        if directory is not None:
            os.close(directory.fd)
