"""Disposable test-only process supervisor; no shared-process changes."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

module_root, host_root, spec_path, receipt_path, approved = sys.argv[1:]
sys.path.insert(0,module_root)
from jev_integration_evaluator.runners import isolated_python as runner
libc=ctypes.CDLL(None,use_errno=True)
if libc.prctl(36,1,0,0,0)!=0:  # PR_SET_CHILD_SUBREAPER; ONLY this disposable probe.
    raise RuntimeError('test subreaper unavailable')
worker_pid=None
parent=subprocess.Popen([sys.executable,'-c',
    'import sys;sys.path.insert(0,sys.argv.pop(1));'
    'from jev_integration_evaluator.runners.isolated_python import main;'
    'raise SystemExit(main())',module_root,
    '--repo',host_root,'--spec',spec_path,'--receipt',receipt_path,
    '--approve-execution-digest',approved,'--authority-reference','synthetic-parent-death'],
    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
    env={'PATH':'/nonexistent','LC_ALL':'C'})
try:
    deadline=time.monotonic()+8
    while time.monotonic()<deadline and parent.poll() is None:
        # /proc/PID/task/PID/children is optional (CONFIG_CHECKPOINT_RESTORE).
        # Inspect only status metadata until a process is our owned child.
        for status_path in Path('/proc').glob('[0-9]*/status'):
            try:
                status=status_path.read_text()
                if f'\nPPid:\t{parent.pid}\n' not in status:
                    continue
                candidate=status_path.parent.name
                cmd=(status_path.parent/'cmdline').read_bytes()
            except (FileNotFoundError,ProcessLookupError,PermissionError):
                continue
            if b'_linux_worker.py' in cmd and b'--describe' not in cmd and '\nUid:\t65534\t' in status:
                worker_pid=int(candidate)
                break
        if worker_pid:
            break
        time.sleep(0.02)
    if worker_pid is None:
        raise RuntimeError('worker was not observed after privilege drop')
    parent.kill();parent.wait(timeout=3)
    deadline=time.monotonic()+3
    status=None
    while time.monotonic()<deadline:
        child, wait_status=os.waitpid(worker_pid,os.WNOHANG)
        if child==worker_pid:
            status=wait_status
            break
        time.sleep(0.02)
    if status is None:
        raise RuntimeError('worker survived supervisor death')
    marker=json.loads(Path(receipt_path).read_text())
    print(json.dumps({'worker_terminated_by_sigkill':os.WIFSIGNALED(status) and os.WTERMSIG(status)==signal.SIGKILL,
                      'worker_reaped':True,'receipt_state':marker['state']}))
finally:
    if parent.poll() is None:
        parent.kill();parent.wait(timeout=3)
    if worker_pid:
        try:
            os.kill(worker_pid,signal.SIGKILL)
            os.waitpid(worker_pid,0)
        except (ProcessLookupError,ChildProcessError):
            pass
    # Also reap any adopted owned child if setup failed before identification.
    for status_path in Path('/proc').glob('[0-9]*/status'):
        try:
            status=status_path.read_text()
            if f'\nPPid:\t{os.getpid()}\n' in status:
                child=int(status_path.parent.name)
                os.kill(child,signal.SIGKILL)
                os.waitpid(child,0)
        except (FileNotFoundError,ProcessLookupError,PermissionError,ChildProcessError):
            pass
    parent.stdout.close();parent.stderr.close()
