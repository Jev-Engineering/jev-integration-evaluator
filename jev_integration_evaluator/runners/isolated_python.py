"""Experimental source-bound, fail-closed Linux Python runner contribution.

This standalone backend is not yet connected to repository sessions or the
existing integration-receipt contract. An execution receipt is NOT a verified
integration, an independent postcondition, or activation authority.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Mapping

BACKEND = 'linux-chroot-seccomp-python-ro-v1'
ISOLATION_CAPABILITIES = {
    'platform': 'linux-x86_64',
    'filesystem': 'read_only_copied_snapshot',
    'network': 'denied',
    'process_creation': 'denied',
    'threads': 'denied',
    'exec': 'denied',
    'target_interpreter': 'same_inode_trusted_worker',
    'dependencies': 'declared_pure_python_snapshot',
}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_CONTRACT_BYTES = 512 * 1024
_HEX = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z')
_READY = b'JEV-ISOLATED-V1\n'


class RunnerError(ValueError):
    """Stable, redacted failure classification. Never carries raw host text."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise RunnerError('invalid_json_value') from error


def request_digest(spec: Mapping[str, Any]) -> str:
    return _hash(canonical(spec))


def _keys(value: Any, expected: set[str], code: str) -> None:
    if type(value) is not dict or set(value) != expected:
        raise RunnerError(code)


def _integer(value: Any, lower: int, upper: int, code: str) -> None:
    if type(value) is not int or not lower <= value <= upper:
        raise RunnerError(code)


def _hex(value: Any, code: str) -> None:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise RunnerError(code)


def _relative(value: Any) -> str:
    try:
        encoded = value.encode('utf-8') if isinstance(value, str) else b''
    except UnicodeEncodeError as error:
        raise RunnerError('invalid_relative_path') from error
    if (not isinstance(value, str) or len(encoded) > 240
            or not value or value.startswith('/') or '\\' in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise RunnerError('invalid_relative_path')
    path = PurePosixPath(value)
    if str(path) != value or any(p in ('', '.', '..') for p in value.split('/')):
        raise RunnerError('invalid_relative_path')
    return value


def _identity(st: os.stat_result) -> dict[str, int]:
    return {'device': st.st_dev, 'inode': st.st_ino}


def _root_fd(path: str | Path) -> int:
    # Traverse every component with O_NOFOLLOW; never resolve then reopen.
    absolute = os.path.abspath(os.fspath(path))
    if os.fspath(path) != absolute:
        raise RunnerError('absolute_root_required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in Path(absolute).parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except OSError as error:
        os.close(fd)
        raise RunnerError('unsafe_or_missing_root') from error


def _read_at(root_fd: int, relative: str) -> tuple[bytes, os.stat_result]:
    parts = _relative(relative).split('/')
    parent = os.dup(root_fd)
    fd = None
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            os.close(parent)
            parent = next_fd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size > MAX_FILE_BYTES):
            raise RunnerError('unsupported_source_file')
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise RunnerError('source_byte_limit')
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise RunnerError('source_changed_during_read')
        return b''.join(chunks), after
    except OSError as error:
        raise RunnerError('unsafe_or_missing_source') from error
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def _plain_hash(path: Path) -> str:
    with path.open('rb') as handle:
        h = hashlib.sha256()
        for chunk in iter(lambda: handle.read(65536), b''):
            h.update(chunk)
        return h.hexdigest()


def environment_identity() -> dict[str, Any]:
    """Identify the trusted launcher and its loaded dependency closure.

    Runs only this code-owned worker in describe mode, never a target program.
    No dependency is installed and no target is imported.
    """
    if sys.platform != 'linux' or platform.machine() != 'x86_64':
        raise RunnerError('unsupported_platform')
    if not hasattr(os, 'geteuid') or os.geteuid() != 0 or os.getuid() != 0:
        raise RunnerError('privileged_launcher_required')
    # Explicit native locations, never a target LD_LIBRARY_PATH, ldconfig, hook,
    # compiler, or package installation. The selected bytes are part of approval.
    options = [Path('/lib/x86_64-linux-gnu/libseccomp.so.2'),
               Path('/usr/lib/x86_64-linux-gnu/libseccomp.so.2')]
    library = next((p.resolve() for p in options if p.is_file()), None)
    if library is None:
        raise RunnerError('libseccomp_missing')
    executable = Path(sys.executable).resolve()
    worker = Path(__file__).with_name('_linux_worker.py')
    try:
        described = subprocess.run(
            [str(executable), '-I', '-B', '-S', str(worker), '--describe', str(library)],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=5, check=True,
            env={'LC_ALL': 'C', 'PATH': '/nonexistent'}, cwd='/', close_fds=True)
        dependency_digest = json.loads(described.stdout)['runtime_dependencies_sha256']
        _hex(dependency_digest, 'runtime_probe_failed')
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        raise RunnerError('runtime_probe_failed') from error
    return {
        'runtime_dependencies_sha256': dependency_digest,
        'python_executable': str(executable), 'python_sha256': _plain_hash(executable),
        'python_version': platform.python_version(), 'machine': platform.machine(),
        'kernel': platform.release(), 'worker_sha256': _plain_hash(worker),
        'supervisor_sha256': _plain_hash(Path(__file__)),
        'library_path': str(library), 'library_sha256': _plain_hash(library),
    }


def validate_spec(spec: Any) -> None:
    if type(spec) is not dict:
        raise RunnerError('invalid_spec_fields')
    version = spec.get('schema_version')
    expected = {'schema_version', 'backend', 'source_identity', 'files', 'environment_identity',
                'environment', 'schedule', 'limits'}
    if version == '1.1':
        expected.add('target_environment')
        expected.add('isolation_capabilities')
    _keys(spec, expected, 'invalid_spec_fields')
    if version not in ('1.0', '1.1') or spec['backend'] != BACKEND:
        raise RunnerError('unsupported_contract_or_backend')
    if len(canonical(spec)) > MAX_CONTRACT_BYTES:
        raise RunnerError('contract_byte_limit')
    _keys(spec['source_identity'], {'device', 'inode'}, 'invalid_source_identity')
    for value in spec['source_identity'].values():
        _integer(value, 0, 2**64 - 1, 'invalid_source_identity')
    env_keys = {'python_executable', 'python_sha256', 'python_version', 'machine', 'kernel',
                'worker_sha256', 'supervisor_sha256', 'library_path', 'library_sha256',
                'runtime_dependencies_sha256'}
    _keys(spec['environment_identity'], env_keys, 'invalid_environment_identity')
    for key, value in spec['environment_identity'].items():
        if key.endswith('_sha256'):
            _hex(value, 'invalid_environment_identity')
        elif not isinstance(value, str) or not value or len(value) > 4096 or '\0' in value:
            raise RunnerError('invalid_environment_identity')
    if type(spec['files']) is not list or not 1 <= len(spec['files']) <= 256:
        raise RunnerError('invalid_files')
    paths: set[str] = set()
    total = 0
    for row in spec['files']:
        _keys(row, {'path', 'sha256', 'bytes', 'mode'}, 'invalid_file_record')
        name = _relative(row['path'])
        if version == '1.1' and (re.search(r'\.so(?:\.|$)', PurePosixPath(name).name)
                                 or name.endswith(('.pyd', '.dll', '.pth'))):
            raise RunnerError('unsupported_native_artifact')
        if name in paths:
            raise RunnerError('duplicate_source_path')
        paths.add(name)
        _hex(row['sha256'], 'invalid_source_hash')
        _integer(row['bytes'], 0, MAX_FILE_BYTES, 'invalid_source_size')
        # Retain phase modes exactly. Unsupported private/mutable/exotic modes
        # fail, rather than changing mode and claiming byte/mode fidelity.
        if type(row['mode']) is not int or row['mode'] not in (0o444, 0o644, 0o555, 0o755):
            raise RunnerError('unsupported_source_mode')
        total += row['bytes']
    if total > MAX_SOURCE_BYTES:
        raise RunnerError('source_byte_limit')
    if version == '1.1':
        if spec['isolation_capabilities'] != ISOLATION_CAPABILITIES:
            raise RunnerError('unsupported_isolation_capabilities')
        target = spec['target_environment']
        _keys(target, {'interpreter_path', 'interpreter_sha256', 'dependency_root',
                       'dependency_identity', 'files', 'distributions'}, 'invalid_target_environment')
        for key in ('interpreter_path', 'dependency_root'):
            value = target[key]
            if (not isinstance(value, str) or not value.startswith('/')
                    or len(value) > 4096 or '\0' in value):
                raise RunnerError('invalid_target_environment')
        _hex(target['interpreter_sha256'], 'invalid_target_environment')
        _keys(target['dependency_identity'], {'device', 'inode'}, 'invalid_target_environment')
        for value in target['dependency_identity'].values():
            _integer(value, 0, 2**64 - 1, 'invalid_target_environment')
        if type(target['files']) is not list or not 1 <= len(target['files']) <= 256:
            raise RunnerError('invalid_dependency_files')
        dep_paths: set[str] = set()
        for row in target['files']:
            _keys(row, {'path', 'sha256', 'bytes', 'mode'}, 'invalid_dependency_file')
            path = _relative(row['path'])
            if (path in dep_paths or not (path.endswith('.py')
                                          or path.endswith('.dist-info/METADATA'))):
                raise RunnerError('unsupported_or_duplicate_dependency')
            dep_paths.add(path)
            _hex(row['sha256'], 'invalid_dependency_file')
            _integer(row['bytes'], 0, MAX_FILE_BYTES, 'invalid_dependency_file')
            if row['mode'] not in (0o444, 0o644, 0o555, 0o755):
                raise RunnerError('unsupported_dependency_mode')
            total += row['bytes']
        if total > MAX_SOURCE_BYTES:
            raise RunnerError('source_byte_limit')
        if (type(target['distributions']) is not list or not target['distributions']
                or len(target['distributions']) > 32):
            raise RunnerError('invalid_dependency_provenance')
        for distribution in target['distributions']:
            _keys(distribution, {'name', 'version', 'metadata_path'}, 'invalid_dependency_provenance')
            if (not isinstance(distribution['name'], str) or not _ID.fullmatch(distribution['name'])
                    or not isinstance(distribution['version'], str)
                    or not _ID.fullmatch(distribution['version'])
                    or distribution['metadata_path'] not in dep_paths
                    or not distribution['metadata_path'].endswith('.dist-info/METADATA')):
                raise RunnerError('invalid_dependency_provenance')
        module_roots = {d['name'].replace('-', '_') for d in target['distributions']}
        for path in dep_paths:
            if path.endswith('.py') and not any(
                    path == name + '.py' or path.startswith(name + '/')
                    for name in module_roots):
                raise RunnerError('unproven_dependency_module')
    if any(any(parent.as_posix() in paths for parent in PurePosixPath(name).parents if str(parent) != '.')
           for name in paths):
        raise RunnerError('source_path_collision')
    if type(spec['environment']) is not dict or len(spec['environment']) > 16:
        raise RunnerError('invalid_environment')
    for key, value in spec['environment'].items():
        if (not isinstance(key, str) or not re.fullmatch(r'JEV_[A-Z0-9_]{1,40}', key)
                or not isinstance(value, str) or len(value) > 256 or '\0' in value):
            raise RunnerError('invalid_environment')
    if type(spec['schedule']) is not list or not 1 <= len(spec['schedule']) <= 64:
        raise RunnerError('invalid_schedule')
    seen: set[str] = set()
    for row in spec['schedule']:
        _keys(row, {'case_id', 'entry', 'argv'}, 'invalid_case')
        case_id = row['case_id']
        if not isinstance(case_id, str) or not _ID.fullmatch(case_id) or case_id in seen:
            raise RunnerError('invalid_or_duplicate_case_id')
        seen.add(case_id)
        if not isinstance(row['entry'], str) or row['entry'] not in paths or not row['entry'].endswith('.py'):
            raise RunnerError('undeclared_or_unsupported_entry')
        if (type(row['argv']) is not list or len(row['argv']) > 32
                or any(not isinstance(v, str) or len(v) > 1024 or '\0' in v for v in row['argv'])):
            raise RunnerError('invalid_argv')
    _keys(spec['limits'], {'wall_seconds', 'cpu_seconds', 'address_space_bytes', 'open_files',
                          'output_bytes', 'schedule_seconds'}, 'invalid_limits')
    bounds = {
        'wall_seconds': (1, 30), 'cpu_seconds': (1, 20),
        'address_space_bytes': (64 * 1024**2, 512 * 1024**2),
        'open_files': (16, 64), 'output_bytes': (64, 1024 * 1024),
        'schedule_seconds': (1, 120),
    }
    for key, (low, high) in bounds.items():
        _integer(spec['limits'][key], low, high, 'invalid_' + key)


def prepare_spec(root: str | Path, paths: list[str], schedule: list[dict[str, Any]], *,
                 environment: dict[str, str] | None = None,
                 limits: dict[str, int] | None = None,
                 target_environment: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read only explicitly named files; no target execution and no approval."""
    if type(paths) is not list or not 1 <= len(paths) <= 256:
        raise RunnerError('invalid_files')
    safe_paths = [_relative(path) for path in paths]
    if len(set(safe_paths)) != len(safe_paths):
        raise RunnerError('duplicate_source_path')
    fd = _root_fd(root)
    try:
        rows = []
        for relative in paths:
            data, st = _read_at(fd, relative)
            rows.append({'path': relative, 'sha256': _hash(data), 'bytes': len(data),
                         'mode': stat.S_IMODE(st.st_mode)})
        identity = _identity(os.fstat(fd))
    finally:
        os.close(fd)
    spec = {'schema_version': '1.0', 'backend': BACKEND,
            'source_identity': identity, 'files': rows,
            'environment_identity': environment_identity(), 'environment': environment or {},
            'schedule': schedule, 'limits': limits or {
                'wall_seconds': 3, 'cpu_seconds': 2, 'address_space_bytes': 128 * 1024**2,
                'open_files': 32, 'output_bytes': 4096, 'schedule_seconds': 30}}
    if target_environment is not None:
        _keys(target_environment, {'interpreter_path', 'dependency_root', 'files',
                                   'distributions'}, 'invalid_target_environment')
        if (not isinstance(target_environment['interpreter_path'], str)
                or not isinstance(target_environment['dependency_root'], str)
                or type(target_environment['files']) is not list
                or not target_environment['files']
                or len(target_environment['files']) > 256):
            raise RunnerError('invalid_target_environment')
        selected = Path(target_environment['interpreter_path'])
        if (not selected.is_absolute() or not selected.is_file()
                or not os.path.samefile(selected, sys.executable)):
            raise RunnerError('unsupported_target_interpreter')
        dep_root = target_environment['dependency_root']
        dep_fd = _root_fd(dep_root)
        try:
            dep_rows = []
            dep_contents = {}
            for relative in target_environment['files']:
                data, st = _read_at(dep_fd, relative)
                dep_contents[relative] = data
                dep_rows.append({'path': relative, 'sha256': _hash(data), 'bytes': len(data),
                                 'mode': stat.S_IMODE(st.st_mode)})
            dep_identity = _identity(os.fstat(dep_fd))
        finally:
            os.close(dep_fd)
        for distribution in target_environment['distributions']:
            metadata = dep_contents.get(distribution['metadata_path'], b'')
            try:
                headers = metadata.decode('utf-8').splitlines()
            except UnicodeDecodeError as error:
                raise RunnerError('invalid_dependency_provenance') from error
            if (f"Name: {distribution['name']}" not in headers
                    or f"Version: {distribution['version']}" not in headers):
                raise RunnerError('invalid_dependency_provenance')
        spec['schema_version'] = '1.1'
        spec['isolation_capabilities'] = dict(ISOLATION_CAPABILITIES)
        spec['target_environment'] = {'interpreter_path': str(selected),
            'interpreter_sha256': _plain_hash(selected), 'dependency_root': str(dep_root),
            'dependency_identity': dep_identity, 'files': dep_rows,
            'distributions': target_environment['distributions']}
    validate_spec(spec)
    return spec


@dataclasses.dataclass(frozen=True)
class ExecutionGrant:
    """Trusted caller input, NOT something inferred from repository/agent text.

    A digest is a binding, not an authentication scheme. The embedding caller
    must authenticate who supplied this grant and enforce its own scope policy.
    """
    approved_request_sha256: str
    authority_reference: str
    backend: str = BACKEND


@dataclasses.dataclass(frozen=True)
class RunResult:
    receipt: dict[str, Any]
    # Never serialize these into a public report. They may contain host secrets.
    private_outputs: dict[str, tuple[bytes, bytes]]

    @property
    def receipt_sha256(self) -> str:
        return _hash(canonical(self.receipt))


def _row(case: Mapping[str, Any], outcome: str, **details: Any) -> dict[str, Any]:
    value = {'case_id': case['case_id'], 'command_sha256': _hash(canonical(case)),
             'outcome': outcome, 'target_launch_released': False, 'isolation_established': False,
             'returncode': None, 'stdout_bytes': 0, 'stderr_bytes': 0,
             'stdout_sha256': _hash(b''), 'stderr_sha256': _hash(b''),
             'elapsed_ms': 0, 'cleanup_complete': True}
    value.update(details)
    return value


def _snapshot(root_fd: int, spec: Mapping[str, Any]) -> dict[str, bytes]:
    if _identity(os.fstat(root_fd)) != spec['source_identity']:
        raise RunnerError('source_root_changed')
    result = {}
    for row in spec['files']:
        data, st = _read_at(root_fd, row['path'])
        if (len(data), _hash(data), stat.S_IMODE(st.st_mode)) != (row['bytes'], row['sha256'], row['mode']):
            raise RunnerError('source_drift')
        result[row['path']] = data
    return result


def _dependency_snapshot(spec: Mapping[str, Any]) -> dict[str, bytes]:
    target = spec['target_environment']
    selected = Path(target['interpreter_path'])
    if (not selected.is_file() or not os.path.samefile(selected, sys.executable)
            or _plain_hash(selected) != target['interpreter_sha256']):
        raise RunnerError('target_interpreter_drift')
    fd = _root_fd(target['dependency_root'])
    try:
        if _identity(os.fstat(fd)) != target['dependency_identity']:
            raise RunnerError('dependency_root_changed')
        result = {}
        for row in target['files']:
            data, st = _read_at(fd, row['path'])
            if (len(data), _hash(data), stat.S_IMODE(st.st_mode)) != (
                    row['bytes'], row['sha256'], row['mode']):
                raise RunnerError('dependency_drift')
            result[row['path']] = data
        return result
    finally:
        os.close(fd)


def _kill_and_reap(process: subprocess.Popen[bytes]) -> bool:
    # The v1 kernel policy denies all creation/escape of descendants. killpg is
    # still used defensively, and the direct worker is always reaped.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        return False
    try:
        process.wait(timeout=3)
        return True
    except subprocess.TimeoutExpired:
        return False


def _execute_case(spec: dict[str, Any], case: dict[str, Any], snapshot: dict[str, bytes],
                  dependencies: dict[str, bytes],
                  remaining: float) -> tuple[dict[str, Any], tuple[bytes, bytes]]:
    start = time.monotonic()
    process = None
    read_fd = write_fd = None
    try:
        with tempfile.TemporaryDirectory(prefix='jev-ro-runner-') as temporary:
            base = Path(temporary)
            os.chmod(base, 0o700)
            jail = base / 'jail'
            jail.mkdir(mode=0o755)
            host = jail / 'host'
            host.mkdir(mode=0o755)
            for row in spec['files']:
                target = host / row['path']
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                with target.open('xb') as handle:
                    handle.write(snapshot[row['path']])
                os.chmod(target, row['mode'])
            if spec['schema_version'] == '1.1':
                dep_dir = jail / 'deps'
                dep_dir.mkdir(mode=0o755)
                for row in spec['target_environment']['files']:
                    target = dep_dir / row['path']
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                    with target.open('xb') as handle:
                        handle.write(dependencies[row['path']])
                    os.chmod(target, row['mode'])
            # No writable jail directory, /proc, device, runtime socket, mount,
            # external directory descriptor, or target-created symlink exists.
            for item in [jail, host, *jail.rglob('*')]:
                st = item.lstat()
                if st.st_uid != 0 or st.st_mode & 0o022 or item.is_symlink():
                    raise RunnerError('jail_ownership_failure')
            environment = spec['environment_identity']
            worker = Path(__file__).with_name('_linux_worker.py').resolve()
            request = {'jail': str(jail), 'entry': case['entry'], 'argv': case['argv'],
                       'environment': spec['environment'], 'limits': spec['limits'],
                       'dependency_path': '/deps' if spec['schema_version'] == '1.1' else None,
                       'library_path': environment['library_path'],
                       'library_sha256': environment['library_sha256'],
                       'runtime_dependencies_sha256': environment['runtime_dependencies_sha256']}
            request_path = base / 'request.json'
            request_path.write_bytes(canonical(request))
            os.chmod(request_path, 0o600)
            read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
            process = subprocess.Popen(
                [environment['python_executable'], '-I', '-B', '-S', str(worker), str(request_path),
                 str(write_fd), str(os.getpid())],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={'LC_ALL': 'C', 'PATH': '/nonexistent'}, cwd='/',
                close_fds=True, pass_fds=(write_fd,), start_new_session=True,
            )
            os.close(write_fd)
            write_fd = None
            buffers = {'stdout': bytearray(), 'stderr': bytearray(), 'ready': bytearray()}
            limit = spec['limits']['output_bytes']
            deadline = min(start + spec['limits']['wall_seconds'], start + remaining)
            outcome = None
            with selectors.DefaultSelector() as selector:
                for stream, label in ((process.stdout, 'stdout'), (process.stderr, 'stderr'), (read_fd, 'ready')):
                    os.set_blocking(stream if type(stream) is int else stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, label)
                while selector.get_map():
                    if time.monotonic() >= deadline:
                        outcome = 'timeout'
                        break
                    for key, _ in selector.select(min(0.05, max(0, deadline - time.monotonic()))):
                        data = os.read(key.fd, 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        label = key.data
                        allowance = ((128 - len(buffers['ready'])) if label == 'ready' else
                                     limit - len(buffers['stdout']) - len(buffers['stderr']))
                        buffers[label].extend(data[:max(0, allowance)])
                        if len(data) > allowance:
                            outcome = 'setup_failed' if label == 'ready' else 'output_limit'
                            break
                        if len(buffers['stdout']) + len(buffers['stderr']) > limit:
                            outcome = 'output_limit'
                            break
                    if outcome:
                        break
                    # Process exit alone does not replace draining bounded pipes.
                if outcome is None:
                    try:
                        process.wait(timeout=max(0.001, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        outcome = 'timeout'
            cleanup = _kill_and_reap(process)
            rc = process.returncode
            ready = bytes(buffers['ready']) == _READY
            if not ready:
                outcome = 'setup_failed'
            elif outcome is None:
                outcome = 'exited_zero' if rc == 0 else 'execution_failed'
            if not cleanup:
                outcome = 'cleanup_failed'
            # Recheck the copies after the process has stopped. Do not certify a
            # changed artifact even if the command returned zero.
            for row in spec['files']:
                target = host / row['path']
                if (_plain_hash(target), stat.S_IMODE(target.stat().st_mode)) != (row['sha256'], row['mode']):
                    outcome = 'copied_source_drift'
            if spec['schema_version'] == '1.1':
                for row in spec['target_environment']['files']:
                    target = jail / 'deps' / row['path']
                    if (_plain_hash(target), stat.S_IMODE(target.stat().st_mode)) != (
                            row['sha256'], row['mode']):
                        outcome = 'copied_source_drift'
            stdout, stderr = bytes(buffers['stdout']), bytes(buffers['stderr'])
            return _row(case, outcome, target_launch_released=ready, isolation_established=ready,
                        returncode=rc, stdout_bytes=len(stdout), stderr_bytes=len(stderr),
                        stdout_sha256=_hash(stdout), stderr_sha256=_hash(stderr),
                        elapsed_ms=round((time.monotonic() - start) * 1000), cleanup_complete=cleanup), (stdout, stderr)
    except (OSError, RunnerError, ValueError):
        cleanup = _kill_and_reap(process) if process is not None else True
        return _row(case, 'setup_failed', cleanup_complete=cleanup), (b'', b'')
    finally:
        if process is not None:
            if process.poll() is None:
                _kill_and_reap(process)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        for fd in (read_fd, write_fd):
            if fd is not None:
                os.close(fd)


def _check_grant(digest: str, grant: ExecutionGrant | None) -> None:
    if (type(grant) is not ExecutionGrant or grant.backend != BACKEND
            or grant.approved_request_sha256 != digest
            or not isinstance(grant.authority_reference, str)
            or not _ID.fullmatch(grant.authority_reference)):
        raise RunnerError('missing_or_mismatched_execution_authority')


def run_schedule(root: str | Path, spec: dict[str, Any], grant: ExecutionGrant | None) -> RunResult:
    """Execute each scheduled case at most once, with no automatic fallback/retry.

    Invalid contracts/authority fail before launch. Valid schedules retain a row
    for EVERY case, including missing prerequisites, source drift and deadlines.
    """
    # Copy first: callback/caller mutation cannot silently alter checked policy.
    spec = json.loads(canonical(spec))
    validate_spec(spec)
    digest = request_digest(spec)
    _check_grant(digest, grant)
    rows = []
    outputs = {}
    root_fd = None
    start = time.monotonic()
    try:
        if environment_identity() != spec['environment_identity']:
            raise RunnerError('environment_drift')
        root_fd = _root_fd(root)
        snapshot = _snapshot(root_fd, spec)
        dependencies = _dependency_snapshot(spec) if spec['schema_version'] == '1.1' else {}
    except (RunnerError, OSError) as error:
        block = error.code if isinstance(error, RunnerError) else 'prerequisite_io_error'
    else:
        block = None
    try:
        for case in spec['schedule']:
            remaining = spec['limits']['schedule_seconds'] - (time.monotonic() - start)
            if block:
                rows.append(_row(case, block))
                continue
            if remaining <= 0:
                rows.append(_row(case, 'schedule_deadline'))
                continue
            try:
                check_fd = _root_fd(root)
                try:
                    if _snapshot(check_fd, spec) != snapshot:
                        raise RunnerError('source_drift')
                finally:
                    os.close(check_fd)
            except RunnerError as error:
                block = error.code
                rows.append(_row(case, block))
                continue
            if spec['schema_version'] == '1.1':
                try:
                    if _dependency_snapshot(spec) != dependencies:
                        raise RunnerError('dependency_drift')
                except RunnerError as error:
                    block = error.code
                    rows.append(_row(case, block))
                    continue
            row, output = _execute_case(spec, case, snapshot, dependencies, remaining)
            rows.append(row)
            outputs[case['case_id']] = output
            # Failed setup is a hard stop, not a silent unsandboxed fallback.
            if row['outcome'] in ('setup_failed', 'cleanup_failed', 'copied_source_drift'):
                block = row['outcome']
        # Re-open by caller root path, not just a stale held directory descriptor.
        final_identity_valid = False
        if block is None:
            try:
                check_fd = _root_fd(root)
                try:
                    final_identity_valid = _snapshot(check_fd, spec) == snapshot
                    if spec['schema_version'] == '1.1':
                        final_identity_valid = final_identity_valid and _dependency_snapshot(spec) == dependencies
                finally:
                    os.close(check_fd)
            except RunnerError:
                pass
        else:
            final_identity_valid = False
    finally:
        if root_fd is not None:
            os.close(root_fd)
    receipt = {
        'schema_version': spec['schema_version'], 'backend': BACKEND, 'run_id': str(uuid.uuid4()),
        'request_sha256': digest, 'authority_reference_sha256': _hash(grant.authority_reference.encode()),
        'source_manifest_sha256': _hash(canonical(spec['files'])),
        'environment_identity_sha256': _hash(canonical(spec['environment_identity'])),
        'schedule_sha256': _hash(canonical(spec['schedule'])),
        'evidence_kind': 'runner_execution_only', 'integration_verified': False,
        'activation_eligible': False, 'source_identity_valid': final_identity_valid,
        'scheduled': len(spec['schedule']), 'recorded': len(rows),
        'exited_zero': sum(row['outcome'] == 'exited_zero' for row in rows),
        'cases': rows,
    }
    if spec['schema_version'] == '1.1':
        receipt['target_environment_sha256'] = _hash(canonical(spec['target_environment']))
    return RunResult(receipt, outputs)


def inspect_receipt(spec: dict[str, Any], receipt: dict[str, Any], *,
                    trusted_receipt_sha256: str | None = None) -> dict[str, Any]:
    """Validate full denominators and optional external anchoring, without running.

    A self-consistent local hash is not authentication. Even an anchored record
    describes runner execution only, never host correctness or activation.
    """
    validate_spec(spec)
    top = {'schema_version', 'backend', 'run_id', 'request_sha256',
           'authority_reference_sha256', 'source_manifest_sha256',
           'environment_identity_sha256', 'schedule_sha256', 'evidence_kind',
           'integration_verified', 'activation_eligible', 'source_identity_valid',
           'scheduled', 'recorded', 'exited_zero', 'cases'}
    if spec['schema_version'] == '1.1':
        top.add('target_environment_sha256')
    _keys(receipt, top, 'invalid_receipt_fields')
    if len(canonical(receipt)) > MAX_CONTRACT_BYTES:
        raise RunnerError('receipt_byte_limit')
    if (receipt['schema_version'] != spec['schema_version'] or receipt['backend'] != BACKEND
            or receipt['evidence_kind'] != 'runner_execution_only'
            or receipt['integration_verified'] is not False
            or receipt['activation_eligible'] is not False
            or type(receipt['source_identity_valid']) is not bool):
        raise RunnerError('invalid_receipt_claim')
    try:
        if str(uuid.UUID(receipt['run_id'])) != receipt['run_id']:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as error:
        raise RunnerError('invalid_run_identity') from error
    bindings = {'request_sha256': request_digest(spec),
                'source_manifest_sha256': _hash(canonical(spec['files'])),
                'environment_identity_sha256': _hash(canonical(spec['environment_identity'])),
                'schedule_sha256': _hash(canonical(spec['schedule']))}
    if spec['schema_version'] == '1.1':
        bindings['target_environment_sha256'] = _hash(canonical(spec['target_environment']))
    if any(receipt[key] != expected for key, expected in bindings.items()):
        raise RunnerError('receipt_binding_mismatch')
    _hex(receipt['authority_reference_sha256'], 'invalid_authority_reference_hash')
    if type(receipt['cases']) is not list or len(receipt['cases']) != len(spec['schedule']):
        raise RunnerError('incomplete_receipt_schedule')
    for key in ('scheduled', 'recorded', 'exited_zero'):
        _integer(receipt[key], 0, 64, 'invalid_receipt_count')
    if receipt['recorded'] != receipt['scheduled'] or receipt['scheduled'] != len(spec['schedule']):
        raise RunnerError('incomplete_receipt_schedule')
    row_fields = set(_row(spec['schedule'][0], 'not_run'))
    known_outcomes = {'exited_zero', 'execution_failed', 'timeout', 'output_limit',
                     'setup_failed', 'cleanup_failed', 'copied_source_drift',
                     'schedule_deadline', 'environment_drift', 'source_root_changed',
                     'source_drift', 'source_changed_during_read', 'unsafe_or_missing_root',
                     'unsafe_or_missing_source', 'unsupported_source_file', 'source_byte_limit',
                     'unsupported_platform', 'privileged_launcher_required',
                     'libseccomp_missing', 'runtime_probe_failed', 'absolute_root_required',
                     'unsupported_target_interpreter', 'target_interpreter_drift',
                     'dependency_root_changed', 'dependency_drift',
                     'prerequisite_io_error'}
    for case, row in zip(spec['schedule'], receipt['cases']):
        _keys(row, row_fields, 'invalid_case_receipt')
        if row['case_id'] != case['case_id'] or row['command_sha256'] != _hash(canonical(case)):
            raise RunnerError('receipt_command_mismatch')
        if not isinstance(row['outcome'], str) or row['outcome'] not in known_outcomes:
            raise RunnerError('invalid_execution_outcome')
        for key in ('target_launch_released', 'isolation_established', 'cleanup_complete'):
            if type(row[key]) is not bool:
                raise RunnerError('invalid_case_flag')
        if row['target_launch_released'] != row['isolation_established']:
            raise RunnerError('invalid_launch_claim')
        for key in ('stdout_bytes', 'stderr_bytes'):
            _integer(row[key], 0, spec['limits']['output_bytes'], 'invalid_output_size')
        for key in ('stdout_sha256', 'stderr_sha256'):
            _hex(row[key], 'invalid_output_hash')
        _integer(row['elapsed_ms'], 0, 180_000, 'invalid_elapsed_time')
        if row['returncode'] is not None:
            _integer(row['returncode'], -128, 255, 'invalid_exit_code')
        if row['outcome'] == 'exited_zero' and (row['returncode'] != 0
                or not row['isolation_established'] or not row['cleanup_complete']):
            raise RunnerError('false_success_claim')
        if row['outcome'] == 'execution_failed' and (row['returncode'] is None
                or row['returncode'] == 0 or not row['isolation_established']):
            raise RunnerError('invalid_failure_exit_code')
        if row['outcome'] in ('timeout', 'output_limit') and not row['isolation_established']:
            raise RunnerError('invalid_execution_outcome')
    if receipt['exited_zero'] != sum(row['outcome'] == 'exited_zero' for row in receipt['cases']):
        raise RunnerError('receipt_count_mismatch')
    actual = _hash(canonical(receipt))
    if trusted_receipt_sha256 is not None:
        _hex(trusted_receipt_sha256, 'invalid_trusted_receipt_hash')
        if actual != trusted_receipt_sha256:
            raise RunnerError('trusted_receipt_mismatch')
    return {'record_status': ('externally_anchored_runner_record' if trusted_receipt_sha256
                              else 'integrity_consistent_but_unverified'),
            'receipt_sha256': actual,
            'all_commands_exited_zero': receipt['exited_zero'] == receipt['scheduled'],
            'source_identity_valid': receipt['source_identity_valid'],
            'integration_verified': False, 'activation_eligible': False}


def read_contract(path: str | Path) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value = {}
        for key, item in pairs:
            if key in value:
                raise RunnerError('duplicate_json_key')
            value[key] = item
        return value
    with Path(path).open('rb') as handle:
        data = handle.read(MAX_CONTRACT_BYTES + 1)
    if len(data) > MAX_CONTRACT_BYTES:
        raise RunnerError('contract_byte_limit')
    try:
        result = json.loads(data, object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(RunnerError('nonfinite_json')))
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, RunnerError):
            raise
        raise RunnerError('invalid_json') from error
    validate_spec(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--approve-execution-digest', required=True)
    parser.add_argument('--authority-reference', required=True)
    parser.add_argument('--receipt', required=True, help='New external private receipt; raw host output is never written')
    args = parser.parse_args(argv)
    try:
        spec = read_contract(args.spec)
        grant = ExecutionGrant(args.approve_execution_digest, args.authority_reference)
        _check_grant(request_digest(spec), grant)
        # Fail output checks BEFORE execution. No overwrite or path traversal.
        output = Path(args.receipt)
        if not output.is_absolute() or output.exists() or output.is_symlink():
            raise RunnerError('new_absolute_receipt_path_required')
        parent_fd = _root_fd(output.parent)
        try:
            if output.resolve().is_relative_to(Path(args.repo).resolve()):
                raise RunnerError('receipt_must_be_external')
            fd = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
            try:
                # Persist an explicit started marker, not a success-shaped empty
                # file. Interrupted standalone runs must not be auto-reexecuted.
                marker = canonical({'state': 'started_uncompleted', 'request_sha256': request_digest(spec)}) + b'\n'
                os.write(fd, marker)
                os.fsync(fd)
                os.fsync(parent_fd)
                result = run_schedule(args.repo, spec, grant)
                payload = canonical({'state': 'completed', 'receipt': result.receipt,
                                     'receipt_sha256': result.receipt_sha256}) + b'\n'
                os.lseek(fd, 0, os.SEEK_SET)
                os.ftruncate(fd, 0)
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
                os.fsync(parent_fd)
            finally:
                os.close(fd)
        finally:
            os.close(parent_fd)
        print(json.dumps({'receipt_sha256': result.receipt_sha256,
                          'scheduled': result.receipt['scheduled'],
                          'exited_zero': result.receipt['exited_zero'],
                          'integration_verified': False, 'activation_eligible': False}))
        return 0 if (result.receipt['exited_zero'] == result.receipt['scheduled']
                     and result.receipt['source_identity_valid']) else 3
    except (RunnerError, OSError) as error:
        code = error.code if isinstance(error, RunnerError) else 'io_error'
        print(json.dumps({'error': code, 'integration_verified': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
