"""Trusted, disposable Linux launcher. Not a Python-language sandbox.

Only this child changes root, credentials, limits or seccomp. Host source is
compiled/executed only after kernel enforcement and after the setup pipe closes.
The parent never treats target-generated JSON as an enforcement receipt.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import resource
import signal
import stat
import sys
import time

# Native x86-64 ABI only. libseccomp supplies architecture dispatch and rejects
# non-native ABI calls. Every unlisted syscall is denied, including new syscalls.
# No exec, fork, clone, threads, signals to peers, ptrace, sockets, io_uring,
# namespaces, mount, credentials, chmod/chown, filesystem mutations, or prctl.
READ_ONLY_SYSCALLS = (
    'read', 'write', 'readv', 'writev', 'close', 'lseek', 'pread64',
    'open', 'openat', 'newfstatat', 'fstat', 'stat', 'lstat', 'statx',
    'access', 'faccessat', 'faccessat2', 'readlink', 'readlinkat',
    'getdents', 'getdents64', 'getcwd', 'chdir',
    'mmap', 'mprotect', 'munmap', 'mremap', 'brk', 'madvise',
    'rt_sigaction', 'rt_sigprocmask', 'rt_sigreturn', 'sigaltstack',
    'futex', 'restart_syscall', 'getpid', 'getppid', 'gettid',
    'getuid', 'geteuid', 'getgid', 'getegid', 'getresuid', 'getresgid',
    'getgroups', 'getpgrp', 'getpgid', 'getsid', 'getrusage', 'times',
    'clock_gettime', 'clock_getres', 'clock_nanosleep', 'nanosleep',
    'gettimeofday', 'time', 'sched_yield', 'sched_getaffinity',
    'getrandom', 'uname', 'poll', 'ppoll', 'select', 'pselect6',
    'exit', 'exit_group',
)


def _digest_file(path: str) -> str:
    with open(path, 'rb') as handle:
        h = hashlib.sha256()
        for chunk in iter(lambda: handle.read(65536), b''):
            h.update(chunk)
        return h.hexdigest()


def runtime_dependencies() -> str:
    """Hash the trusted preloaded module/DSO closure, never target modules."""
    paths = set()
    for name, module in tuple(sys.modules.items()):
        path = getattr(module, '__file__', None)
        if path and name != '__main__' and os.path.isfile(path):
            paths.add(os.path.realpath(path))
    with open('/proc/self/maps', 'r', encoding='utf-8') as handle:
        for line in handle:
            columns = line.rstrip('\n').split(maxsplit=5)
            if len(columns) == 6 and columns[5].startswith('/'):
                path = columns[5]
                if path.endswith(' (deleted)') or not os.path.isfile(path):
                    raise RuntimeError('unhashable_runtime_mapping')
                paths.add(os.path.realpath(path))
    records = [{'path': path, 'sha256': _digest_file(path)} for path in sorted(paths)]
    encoded = json.dumps(records, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return hashlib.sha256(encoded).hexdigest()


def _seccomp(library: ctypes.CDLL) -> int:
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    library.seccomp_attr_set.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32]
    library.seccomp_arch_native.restype = ctypes.c_uint32
    library.seccomp_arch_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_arch_resolve_name.restype = ctypes.c_uint32
    library.seccomp_arch_exist.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    # Default EPERM. Architecture mismatch defaults to libseccomp KILL action.
    context = library.seccomp_init(0x00050000 | errno.EPERM)
    if not context:
        raise RuntimeError('seccomp_init')
    try:
        if library.seccomp_arch_native() != library.seccomp_arch_resolve_name(b'x86_64'):
            raise RuntimeError('unsupported_native_abi')
        for other in (b'x86', b'x32'):
            if library.seccomp_arch_exist(context, library.seccomp_arch_resolve_name(other)) == 0:
                raise RuntimeError('unexpected_secondary_abi')
        # SCMP_FLTATR_ACT_BADARCH=2, SCMP_ACT_KILL_PROCESS=0x80000000.
        if library.seccomp_attr_set(context, 2, 0x80000000) != 0:
            raise RuntimeError('unsupported_bad_arch_action')
        for name in READ_ONLY_SYSCALLS:
            number = library.seccomp_syscall_resolve_name(name.encode('ascii'))
            if number < 0:
                raise RuntimeError('unsupported_syscall_table')
            if library.seccomp_rule_add(context, 0x7fff0000, number, 0) != 0:
                raise RuntimeError('seccomp_rule')
        code = library.seccomp_load(context)
    finally:
        library.seccomp_release(context)
    if code != 0:
        raise RuntimeError('seccomp_load')
    return code


def _clear_and_check_capabilities(libc: ctypes.CDLL) -> None:
    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]
    class Capabilities(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]
    header = Header(0x20080522, 0)
    data = (Capabilities * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise RuntimeError('capset')
    if libc.capget(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise RuntimeError('capget')
    if any(part.effective or part.permitted or part.inheritable for part in data):
        raise RuntimeError('capabilities_remaining')


def main() -> int:
    # These arguments are produced by the trusted supervisor, not the host.
    request_path, ready_text, expected_parent_text = sys.argv[1:]
    ready_fd = int(ready_text)
    try:
        with open(request_path, 'r', encoding='utf-8') as handle:
            request = json.load(handle)
        library_path = request['library_path']
        if _digest_file(library_path) != request['library_sha256']:
            raise RuntimeError('library_drift')
        library = ctypes.CDLL(library_path, use_errno=True)
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.restype = ctypes.c_int
        if runtime_dependencies() != request['runtime_dependencies_sha256']:
            raise RuntimeError('runtime_dependency_drift')
        # Load code-owned machinery before restriction. No host import or parse.
        limits = request['limits']
        jail = request['jail']
        entry = request['entry']
        args = list(request['argv'])
        environment = dict(request['environment'])
        expected_parent = int(expected_parent_text)
        # The worker starts with close_fds=True; retain no external descriptor.
        # Validate what the loader actually left open before loading host code.
        inherited = [int(n) for n in os.listdir('/proc/self/fd') if n.isdecimal()]
        for fd in inherited:
            if fd > 2 and fd != ready_fd:
                try:
                    os.close(fd)
                except OSError as error:
                    if error.errno != errno.EBADF:
                        raise
        if os.geteuid() != 0 or os.getuid() != 0:
            raise RuntimeError('privileged_launcher_required')
        os.chroot(jail)
        os.chdir('/host')
        os.setgroups([])
        os.setresgid(65534, 65534, 65534)
        os.setresuid(65534, 65534, 65534)
        if os.getresuid() != (65534,) * 3 or os.getresgid() != (65534,) * 3 or os.getgroups():
            raise RuntimeError('credential_drop')
        _clear_and_check_capabilities(libc)
        # setuid can clear dumpability/PDEATHSIG; set them AFTER the drop.
        if libc.prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE
            raise RuntimeError('dumpability')
        if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
            raise RuntimeError('parent_death_signal')
        if os.getppid() != expected_parent:
            raise RuntimeError('parent_changed')
        if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(39, 0, 0, 0, 0) != 1:
            raise RuntimeError('no_new_privs')
        for kind, bound in (
            (resource.RLIMIT_CORE, 0), (resource.RLIMIT_FSIZE, 0),
            (resource.RLIMIT_NPROC, 0), (resource.RLIMIT_NOFILE, limits['open_files']),
            (resource.RLIMIT_AS, limits['address_space_bytes']),
            (resource.RLIMIT_CPU, limits['cpu_seconds']),
        ):
            resource.setrlimit(kind, (bound, bound))
        os.environ.clear()
        os.environ.update(environment)
        sys.path[:] = ['/host']
        sys.argv[:] = ['/host/' + entry] + args
        sys.dont_write_bytecode = True
        _seccomp(library)
        # These checks are real syscalls after enforcement, not an audit hook.
        ctypes.set_errno(0)
        if libc.socket(2, 1, 0) != -1 or ctypes.get_errno() != errno.EPERM:
            raise RuntimeError('network_filter_not_enforced')
        # This channel has no target-produced content and is closed permanently
        # before any target byte is compiled. It is not exposed via /proc.
        os.write(ready_fd, b'JEV-ISOLATED-V1\n')
        os.close(ready_fd)
    except BaseException:
        try:
            os.write(ready_fd, b'JEV-SETUP-FAILED-V1\n')
            os.close(ready_fd)
        except OSError:
            pass
        # Do not expose exception text, environment, paths, or target content.
        return 125

    try:
        # The exact approved script is loaded from the read-only copied host.
        # This is real __main__ execution: no callback, router or assertion is
        # substituted by the runner. Undeclared imports fail normally.
        filename = '/host/' + entry
        with open(filename, 'rb') as handle:
            source = handle.read()
        program = compile(source, filename, 'exec', dont_inherit=True)
        namespace = {'__name__': '__main__', '__file__': filename,
                     '__package__': None, '__cached__': None, '__builtins__': __builtins__}
        exec(program, namespace, namespace)
        sys.stdout.flush()
        sys.stderr.flush()
        return 0
    except SystemExit as error:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            return 120
        if error.code is None:
            return 0
        if type(error.code) is int:
            return error.code % 256
        return 1
    except BaseException:
        # Target output remains separately bounded/private. No automatic
        # traceback can leak local source or credential-bearing arguments.
        return 1


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--describe':
        _described_library = ctypes.CDLL(sys.argv[2], use_errno=True)
        _described_libc = ctypes.CDLL(None, use_errno=True)
        print(json.dumps({'runtime_dependencies_sha256': runtime_dependencies()}))
    else:
        os._exit(main())
