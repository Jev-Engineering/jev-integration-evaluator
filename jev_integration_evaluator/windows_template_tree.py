"""Bounded, read-only NTFS inventory of an owned installed environment."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

from . import capabilities as cap
from .io import InputError
from .windows_template_owned import acl_sha256


def installed_tree_snapshot(root: Path) -> dict[str, dict[str, str]]:
    """Include all files, including import hooks absent from wheel RECORDs."""
    files: dict[str, str] = {}
    acls: dict[str, str] = {}
    identities: dict[str, tuple[int, int]] = {}
    seen = 0
    total = 0

    def visit(directory: Path, prefix: str, depth: int) -> None:
        nonlocal seen, total
        if depth > 64:
            raise InputError('windows_install_tree_limit')
        try:
            cap._windows_check_directory_path(directory, purpose='input')
            before = os.lstat(directory)
            if cap._windows_reparse_reason(before) or not stat.S_ISDIR(before.st_mode):
                raise InputError('windows_install_tree_reparse_or_nonregular')
            acls[prefix or '.'] = acl_sha256(directory)
            identities[prefix or '.'] = cap._windows_file_identity(before)
            with os.scandir(directory) as stream:
                entries = sorted(stream, key=lambda e: e.name.casefold())
            folded = set()
            for entry in entries:
                seen += 1
                if seen > 12_000 or not cap._windows_safe_component(entry.name):
                    raise InputError('windows_install_tree_limit')
                if entry.name.casefold() in folded:
                    raise InputError('windows_install_tree_ambiguous')
                folded.add(entry.name.casefold())
                path = directory / entry.name
                rel = f'{prefix}/{entry.name}' if prefix else entry.name
                info = os.lstat(path)
                if cap._windows_reparse_reason(info):
                    raise InputError('windows_install_tree_reparse_or_nonregular')
                if stat.S_ISDIR(info.st_mode):
                    visit(path, rel, depth + 1)
                elif stat.S_ISREG(info.st_mode):
                    acls[rel] = acl_sha256(path)
                    identities[rel] = cap._windows_file_identity(info)
                    raw = cap._windows_secure_input(path, 64_000_000)
                    total += len(raw)
                    if total > 512_000_000:
                        raise InputError('windows_install_tree_limit')
                    files[rel] = hashlib.sha256(raw).hexdigest()
                else:
                    raise InputError('windows_install_tree_reparse_or_nonregular')
            if cap._windows_file_identity(os.lstat(directory)) != cap._windows_file_identity(before):
                raise InputError('windows_install_tree_changed')
        except cap.CapabilityError as exc:
            raise InputError('windows_install_tree_' + exc.code) from None

    visit(root, '', 0)
    if not files:
        raise InputError('windows_install_tree_empty')
    return {'files': files, 'acls': acls, 'identities': identities}
