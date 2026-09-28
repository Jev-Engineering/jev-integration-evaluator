"""Independent, hand-authored synthetic Linux runner acceptance probes.

These do not use scripts/implementation_fixtures.py, generated binding oracles,
provider calls, private host source, production systems, or privileged changes
to the parent process. They qualify only the new standalone bounded backend.
"""
from __future__ import annotations
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

import pytest
import jsonschema

from jev_integration_evaluator.runners import isolated_python as runner
from jev_integration_evaluator.runners.observations import inspect_lifecycle_postconditions

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                                reason='requires explicitly qualified privileged Linux launcher')


def host(tmp_path, source='print("hello", flush=True)\n', *, cases=None, files=None, limits=None):
    root = tmp_path / 'host source'
    root.mkdir()
    (root / 'entry.py').write_text(source)
    os.chmod(root / 'entry.py', 0o644)
    names = ['entry.py']
    for name, content in (files or {}).items():
        p = root / name
        p.parent.mkdir(exist_ok=True, parents=True)
        p.write_text(content)
        os.chmod(p, 0o644)
        names.append(name)
    spec = runner.prepare_spec(root, names, cases or [{'case_id':'one', 'entry':'entry.py', 'argv':[]}], limits=limits)
    return root, spec


def run(root, spec):
    return runner.run_schedule(root, spec, runner.ExecutionGrant(runner.request_digest(spec), 'synthetic-independent-tests'))


def assert_zero(result, expected=None, case='one'):
    row = next(x for x in result.receipt['cases'] if x['case_id'] == case)
    assert row['outcome'] == 'exited_zero', (row, result.private_outputs)
    assert row['returncode'] == 0
    assert row['isolation_established'] is True
    assert row['cleanup_complete'] is True
    if expected is not None:
        assert result.private_outputs[case][0] == expected
    assert result.receipt['integration_verified'] is False
    assert result.receipt['activation_eligible'] is False


def test_real_entry_and_source_modes_remain_unchanged(tmp_path):
    root, spec = host(tmp_path)
    before = (root/'entry.py').read_bytes(), (root/'entry.py').stat().st_mode
    result = run(root, spec)
    assert_zero(result, b'hello\n')
    assert before == ((root/'entry.py').read_bytes(), (root/'entry.py').stat().st_mode)
    assert result.receipt['source_identity_valid'] is True
    assert len(list(root.iterdir())) == 1


def test_target_startup_customization_is_not_implicitly_executed(tmp_path):
    poison = 'raise AssertionError("unapproved startup customization ran")\n'
    root, spec = host(tmp_path, 'print("entry reached", flush=True)\n', files={
        'sitecustomize.py': poison,
        'usercustomize.py': poison,
        'conftest.py': poison,
    })
    result = run(root, spec)
    assert_zero(result, b'entry reached\n')


def installed_fixture(tmp_path):
    root = tmp_path / 'target'
    root.mkdir()
    (root / 'entry.py').write_text('import toy_package\nprint(toy_package.value(), flush=True)\n')
    deps = tmp_path / 'installed-site-packages'
    (deps / 'toy_package').mkdir(parents=True)
    (deps / 'toy_package' / '__init__.py').write_text('def value(): return "installed-dependency"\n')
    metadata = deps / 'toy_package-1.0.dist-info' / 'METADATA'
    metadata.parent.mkdir()
    metadata.write_text('Metadata-Version: 2.1\nName: toy_package\nVersion: 1.0\n')
    selected = {'interpreter_path': sys.executable, 'dependency_root': str(deps),
                'files': ['toy_package/__init__.py', 'toy_package-1.0.dist-info/METADATA'],
                'distributions': [{'name': 'toy_package', 'version': '1.0',
                                   'metadata_path': 'toy_package-1.0.dist-info/METADATA'}]}
    schedule = [{'case_id': 'installed', 'entry': 'entry.py', 'argv': []}]
    spec = runner.prepare_spec(root, ['entry.py'], schedule, target_environment=selected)
    return root, deps, spec, selected


def test_exact_installed_pure_python_dependency_runs_inside_jail(tmp_path):
    root, _, spec, _ = installed_fixture(tmp_path)
    assert spec['schema_version'] == '1.1'
    result = run(root, spec)
    assert_zero(result, b'installed-dependency\n', case='installed')
    assert spec['target_environment']['interpreter_sha256'] == spec['environment_identity']['python_sha256']
    assert result.receipt['schema_version'] == '1.1'
    runner.inspect_receipt(spec, result.receipt, trusted_receipt_sha256=result.receipt_sha256)
    altered = copy.deepcopy(result.receipt)
    altered['target_environment_sha256'] = '0' * 64
    with pytest.raises(runner.RunnerError, match='receipt_binding_mismatch'):
        runner.inspect_receipt(spec, altered)


def test_installed_dependency_drift_retains_scheduled_failure(tmp_path):
    root, deps, spec, _ = installed_fixture(tmp_path)
    (deps / 'toy_package' / '__init__.py').write_text('def value(): return "changed"\n')
    result = run(root, spec)
    assert [row['outcome'] for row in result.receipt['cases']] == ['dependency_drift']
    assert result.private_outputs == {}
    runner.inspect_receipt(spec, result.receipt)


def test_missing_installed_dependency_retains_scheduled_failure(tmp_path):
    root, deps, spec, _ = installed_fixture(tmp_path)
    (deps / 'toy_package' / '__init__.py').unlink()
    result = run(root, spec)
    assert result.receipt['scheduled'] == result.receipt['recorded'] == 1
    assert result.receipt['cases'][0]['outcome'] == 'unsafe_or_missing_source'
    assert result.private_outputs == {}


def test_dependency_revalidation_charges_total_schedule_deadline(tmp_path, monkeypatch):
    root, _, spec, _ = installed_fixture(tmp_path)
    spec['limits']['schedule_seconds'] = 1
    original = runner._dependency_snapshot
    calls = 0
    def delayed(value):
        nonlocal calls
        calls += 1
        if calls == 2:
            time.sleep(1.05)
        return original(value)
    monkeypatch.setattr(runner, '_dependency_snapshot', delayed)
    result = run(root, spec)
    assert result.receipt['cases'][0]['outcome'] == 'schedule_deadline'
    assert result.private_outputs == {}


def test_installed_sitecustomize_cannot_run_before_approved_entry(tmp_path):
    root, deps, _, selected = installed_fixture(tmp_path)
    (deps / 'sitecustomize.py').write_text('raise AssertionError("site hook ran")\n')
    metadata = deps / 'sitecustomize-1.0.dist-info' / 'METADATA'
    metadata.parent.mkdir()
    metadata.write_text('Metadata-Version: 2.1\nName: sitecustomize\nVersion: 1.0\n')
    selected['files'] += ['sitecustomize.py', 'sitecustomize-1.0.dist-info/METADATA']
    selected['distributions'].append({'name': 'sitecustomize', 'version': '1.0',
                                      'metadata_path': 'sitecustomize-1.0.dist-info/METADATA'})
    spec = runner.prepare_spec(root, ['entry.py'],
                               [{'case_id': 'installed', 'entry': 'entry.py', 'argv': []}],
                               target_environment=selected)
    assert_zero(run(root, spec), b'installed-dependency\n', case='installed')


def test_dependency_preparation_and_denied_grant_never_import_target(tmp_path):
    root, deps, original, selected = installed_fixture(tmp_path)
    (deps / 'toy_package' / '__init__.py').write_text(
        'raise AssertionError("dependency imported before approval")\n')
    spec = runner.prepare_spec(root, ['entry.py'], original['schedule'],
                               target_environment=selected)
    with pytest.raises(runner.RunnerError, match='execution_authority'):
        runner.run_schedule(root, spec, None)


def test_missing_or_different_interpreter_is_rejected_before_target_launch(tmp_path):
    root, _, spec, selected = installed_fixture(tmp_path)
    selected['interpreter_path'] = str(tmp_path / 'missing-python')
    with pytest.raises(runner.RunnerError, match='unsupported_target_interpreter'):
        runner.prepare_spec(root, ['entry.py'], spec['schedule'], target_environment=selected)
    spec['target_environment']['interpreter_sha256'] = '0' * 64
    result = run(root, spec)
    assert result.receipt['cases'][0]['outcome'] == 'target_interpreter_drift'


def test_edited_host_bootstrap_off_shadow_parity_uses_installed_package(tmp_path):
    _, deps, _, selected = installed_fixture(tmp_path)
    (deps / 'toy_package' / '__init__.py').write_text(
        'def judge(value): return "accepted:" + value\n')
    entry = '''import sys
from runtime import bootstrap
runtime = bootstrap()
answer = runtime.decide('x', sys.argv[1])
runtime.close()
print(answer, runtime.effects, runtime.assessments, runtime.closed, runtime.origin(), flush=True)
'''
    common = '''import toy_package
class Runtime:
    def __init__(self):
        self.effects = 0
        self.assessments = 0
        self.closed = False
    def origin(self): return toy_package.__file__
    def close(self): self.closed = True
def bootstrap(): return Runtime()
'''
    baseline_body = '''    def decide(self, value, mode):
        self.effects += 1
        return 'baseline:' + value
'''
    edited_body = '''    def decide(self, value, mode):
        self.effects += 1
        if mode == 'shadow':
            assert toy_package.judge(value) == 'accepted:' + value
            self.assessments += 1
        return 'baseline:' + value
'''
    schedule = [{'case_id': mode, 'entry': 'entry.py', 'argv': [mode]}
                for mode in ('off', 'shadow')]
    outputs = {}
    for phase, body in [('baseline', baseline_body), ('edited', edited_body)]:
        host_root = tmp_path / phase
        host_root.mkdir()
        (host_root / 'entry.py').write_text(entry)
        (host_root / 'runtime.py').write_text(common.replace('def bootstrap():', body + 'def bootstrap():'))
        spec = runner.prepare_spec(host_root, ['entry.py', 'runtime.py'], schedule,
                                   target_environment=selected)
        result = run(host_root, spec)
        assert result.receipt['scheduled'] == result.receipt['recorded'] == 2
        for mode in ('off', 'shadow'):
            assert_zero(result, case=mode)
            outputs[(phase, mode)] = result.private_outputs[mode][0]
    origin = b'/deps/toy_package/__init__.py\n'
    assert outputs[('baseline', 'off')] == b'baseline:x 1 0 True ' + origin
    assert outputs[('edited', 'off')] == outputs[('baseline', 'off')]
    assert outputs[('baseline', 'shadow')] == outputs[('baseline', 'off')]
    assert outputs[('edited', 'shadow')] == b'baseline:x 1 1 True ' + origin


def test_independent_json_state_oracle_binds_edited_entry_and_parity(tmp_path):
    _, _, _, selected = installed_fixture(tmp_path)
    entry = '''import json, sys
from runtime import bootstrap
runtime = bootstrap()
result = runtime.decide('x', sys.argv[1])
runtime.close()
print(json.dumps({'reached': True, 'result': result, 'effects': runtime.effects,
                  'state': {'closed': runtime.closed}, 'assessments': runtime.assessments,
                  'dependency_origin': runtime.origin()}, sort_keys=True), flush=True)
'''
    shared = '''import toy_package
class Runtime:
    def __init__(self):
        self.effects = []
        self.assessments = 0
        self.closed = False
    def origin(self): return toy_package.__file__
    def close(self): self.closed = True
def bootstrap(): return Runtime()
'''
    baseline_body = '''    def decide(self, value, mode):
        self.effects.append('charge:' + value)
        return 'baseline:' + value
'''
    edited_body = '''    def decide(self, value, mode):
        self.effects.append('charge:' + value)
        if mode == 'shadow': self.assessments += 1
        return 'baseline:' + value
'''
    specs, results = {}, {}
    for phase, body, modes in [('baseline', baseline_body, ['baseline']),
                               ('modified', edited_body, ['off', 'shadow'])]:
        source = tmp_path / phase
        source.mkdir()
        (source / 'entry.py').write_text(entry)
        (source / 'runtime.py').write_text(shared.replace('def bootstrap():', body + 'def bootstrap():'))
        schedule = [{'case_id': mode, 'entry': 'entry.py', 'argv': [mode]} for mode in modes]
        specs[phase] = runner.prepare_spec(source, ['entry.py', 'runtime.py'], schedule,
                                           target_environment=selected)
        results[phase] = run(source, specs[phase])
    origin = '/deps/toy_package/__init__.py'
    def expected(assessments):
        return {'reached': True, 'result': 'baseline:x', 'effects': ['charge:x'],
                'state': {'closed': True}, 'assessments': assessments,
                'dependency_origin': origin}
    oracle = {'schema_version': '1.0', 'kind': 'native-postconditions-v1',
              'repository_identity': '1' * 64, 'context_sha256': '2' * 64,
              'bundle_digest': '3' * 64, 'adapter': 'json-state-v1'}
    for phase, modes in [('baseline', ['baseline']), ('modified', ['off', 'shadow'])]:
        spec = specs[phase]
        oracle[phase] = {'request_sha256': runner.request_digest(spec),
                         'source_manifest_sha256': results[phase].receipt['source_manifest_sha256'],
                         'attempt': 1,
                         'cases': [{'case_id': mode, 'entry_sha256': spec['files'][0]['sha256'],
                                    'observation': expected(1 if mode == 'shadow' else 0)}
                                   for mode in modes]}
    oracle_hash = hashlib.sha256(runner.canonical(oracle)).hexdigest()
    jsonschema.validate(oracle, json.loads((Path(__file__).resolve().parents[1] /
        'schemas/native-postconditions-v1.schema.json').read_text()))
    arguments = dict(trusted_oracle_sha256=oracle_hash,
                     baseline_spec=specs['baseline'], baseline_receipt=results['baseline'].receipt,
                     baseline_outputs=results['baseline'].private_outputs,
                     trusted_baseline_receipt_sha256=results['baseline'].receipt_sha256,
                     modified_spec=specs['modified'], modified_receipt=results['modified'].receipt,
                     modified_outputs=results['modified'].private_outputs,
                     trusted_modified_receipt_sha256=results['modified'].receipt_sha256)
    report = inspect_lifecycle_postconditions(oracle, **arguments)
    assert report['scheduled'] == report['recorded'] == 3
    assert report['postconditions_satisfied'] is True
    assert report['integration_verified'] is False
    jsonschema.validate(report, json.loads((Path(__file__).resolve().parents[1] /
        'schemas/native-postcondition-report-v1.schema.json').read_text()))
    tampered = copy.deepcopy(arguments)
    tampered['modified_outputs'] = dict(tampered['modified_outputs'])
    tampered['modified_outputs']['shadow'] = (b'{}\n', b'')
    with pytest.raises(runner.RunnerError, match='native_output_receipt_mismatch'):
        inspect_lifecycle_postconditions(oracle, **tampered)
    forged_oracle = copy.deepcopy(oracle)
    forged_oracle['modified']['cases'][-1]['observation']['assessments'] = 0
    with pytest.raises(runner.RunnerError, match='external_oracle_anchor_mismatch'):
        inspect_lifecycle_postconditions(forged_oracle, **arguments)
    drifted = copy.deepcopy(arguments)
    drifted['modified_receipt'] = copy.deepcopy(drifted['modified_receipt'])
    drifted['modified_receipt']['source_identity_valid'] = False
    drifted['trusted_modified_receipt_sha256'] = hashlib.sha256(
        runner.canonical(drifted['modified_receipt'])).hexdigest()
    assert inspect_lifecycle_postconditions(oracle, **drifted)['postconditions_satisfied'] is False


def test_real_bootstrap_off_shadow_no_replacement_callback(tmp_path):
    source = '''import sys
from runtime import bootstrap
runtime = bootstrap()
before = id(runtime)
first = runtime.decide('a', sys.argv[1])
second = runtime.decide('b', sys.argv[1])
assert id(runtime) == before
runtime.close()
print(first, second, runtime.effects, runtime.assessments, runtime.closed, flush=True)
'''
    dependency = '''class Runtime:
    def __init__(self):
        self.effects = 0
        self.assessments = 0
        self.closed = False
    def decide(self, value, mode):
        self.effects += 1
        if mode == 'shadow': self.assessments += 1
        return 'baseline:' + value
    def close(self): self.closed = True

def bootstrap():
    return Runtime()
'''
    cases=[{'case_id':'off','entry':'entry.py','argv':['off']},
           {'case_id':'shadow','entry':'entry.py','argv':['shadow']}]
    root,spec=host(tmp_path,source,cases=cases,files={'runtime.py':dependency})
    result=run(root,spec)
    assert_zero(result,b'baseline:a baseline:b 2 0 True\n',case='off')
    assert_zero(result,b'baseline:a baseline:b 2 2 True\n',case='shadow')
    # A hand-authored host exercises true startup; it is NOT TypeSafe bootstrap
    # or a qualification of the repository's existing callback/recipe contract.
    assert result.receipt['scheduled']==result.receipt['recorded']==2


@pytest.mark.parametrize('attempt', [
    "open('/etc/passwd','rb').read()",
    "open('../../../../etc/passwd','rb').read()",
    "open('/proc/self/root/etc/passwd','rb').read()",
    "open('/proc/self/environ','rb').read()",
    "open('/dev/mem','rb').read()",
    "open('/host/entry.py','w').write('changed')",
    "open('/host/new-file','w').write('changed')",
    "open('/new-file','w').write('changed')",
    "__import__('os').mkdir('/host/new-dir')",
    "__import__('os').symlink('/etc/passwd','/host/leak')",
    "__import__('os').chmod('/host/entry.py',0o777)",
    "__import__('os').chroot('/')",
    "__import__('os').setuid(0)",
    "__import__('os').setgid(0)",
    "__import__('os').setsid()",
    "__import__('os').setpgid(0,0)",
    "__import__('os').kill(__import__('os').getpid(),0)",
])
def test_filesystem_privilege_and_process_escape_attempts(tmp_path,attempt):
    source=f'''try:
    {attempt}
except OSError:
    print('denied',flush=True)
else:
    print('ESCAPED',flush=True)
'''
    root,spec=host(tmp_path,source)
    assert_zero(run(root,spec),b'denied\n')


# Native x86-64 syscalls. Invalid arguments are intentionally harmless if a
# policy regression occurs; the independent assertion demands seccomp EPERM.
@pytest.mark.parametrize('number,args', [
    (41, '2, 1, 0'),       # socket(AF_INET, SOCK_STREAM)
    (41, '10, 1, 0'),      # socket(AF_INET6, SOCK_STREAM)
    (41, '1, 1, 0'),       # socket(AF_UNIX, SOCK_STREAM)
    (53, '1, 1, 0, 0'),    # socketpair, invalid destination
    (101, '-1, 0, 0, 0'), # ptrace, invalid request
    (310, '0, 0, 0, 0, 0, 0'), # process_vm_readv
    (311, '0, 0, 0, 0, 0, 0'), # process_vm_writev
    (425, '0, 0'),         # io_uring_setup
    (426, '-1, 0, 0, 0, 0, 0'), # io_uring_enter
    (427, '-1, 0, 0, 0'), # io_uring_register
    (272, '0'),           # unshare; no namespace creation
    (308, '-1, 0'),       # setns; invalid descriptor
    (321, '-1, 0, 0'),    # bpf; invalid command
    (298, '0, 0, 0, -1, 0'), # perf_event_open
    (319, '0, 0'),        # memfd_create; invalid name
    (435, '0, 0'),        # clone3; no process can be created
    (59, '0, 0, 0'),      # execve; invalid program pointer
    (322, '-1, 0, 0, 0, 0'), # execveat
    (161, '0'),           # chroot; invalid pathname
    (157, '38, 0, 0, 0, 0'), # prctl: cannot clear no_new_privs
    (160, '0, 0'),        # setrlimit
    (302, '0, 0, 0, 0'), # prlimit64
])
def test_native_syscall_filter_not_python_audit_hook(tmp_path,number,args):
    source=f'''import ctypes
libc=ctypes.CDLL(None,use_errno=True)
ctypes.set_errno(0)
result=libc.syscall({number},{args})
print(result,ctypes.get_errno(),flush=True)
'''
    root,spec=host(tmp_path,source)
    assert_zero(run(root,spec),b'-1 1\n')


def test_fork_is_denied_without_leaking_child(tmp_path):
    root,spec=host(tmp_path,'''import os
try:
    child=os.fork()
except OSError as error:
    print(error.errno,flush=True)
else:
    if child==0: os._exit(0)
    print('fork-allowed',flush=True)
''')
    assert_zero(run(root,spec),b'1\n')


def test_credentials_irreversibly_dropped(tmp_path):
    root,spec=host(tmp_path,'''import os
print(os.getresuid(),os.getresgid(),os.getgroups(),flush=True)
''')
    assert_zero(run(root,spec),b'(65534, 65534, 65534) (65534, 65534, 65534) []\n')


def test_no_extra_inherited_descriptors(tmp_path):
    root,spec=host(tmp_path,'''import os
opened=[]
for fd in range(3,64):
    try: os.fstat(fd)
    except OSError: pass
    else: opened.append(fd)
print(opened,flush=True)
''')
    assert_zero(run(root,spec),b'[]\n')


def test_timeout_and_later_success_preserve_schedule(tmp_path):
    root,spec=host(tmp_path,'''import sys,time
if sys.argv[1]=='slow': time.sleep(20)
print('done',flush=True)
''',cases=[{'case_id':'slow','entry':'entry.py','argv':['slow']},
            {'case_id':'fast','entry':'entry.py','argv':['fast']}])
    spec['limits']['wall_seconds']=1
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='timeout'
    assert result.receipt['cases'][0]['returncode']==-signal.SIGKILL
    assert result.receipt['cases'][0]['cleanup_complete'] is True
    assert_zero(result,b'done\n',case='fast')
    assert result.receipt['scheduled']==result.receipt['recorded']==2
    assert result.receipt['exited_zero']==1


def test_total_schedule_deadline_preserves_not_run_cases(tmp_path):
    root,spec=host(tmp_path,'import time;time.sleep(20)\n',cases=[
        {'case_id':str(i),'entry':'entry.py','argv':[]} for i in range(4)])
    spec['limits']['schedule_seconds']=1
    result=run(root,spec)
    assert result.receipt['scheduled']==result.receipt['recorded']==4
    assert result.receipt['cases'][0]['outcome']=='timeout'
    assert all(r['outcome']=='schedule_deadline' for r in result.receipt['cases'][1:])


def test_cpu_limit_reaps_worker(tmp_path):
    root,spec=host(tmp_path,'while True: pass\n')
    spec['limits']['cpu_seconds']=1
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='execution_failed'
    assert result.receipt['cases'][0]['returncode']==-signal.SIGKILL
    assert result.receipt['cases'][0]['cleanup_complete'] is True


def test_memory_limit(tmp_path):
    root,spec=host(tmp_path,'''try:
    excessive=bytearray(1024*1024*1024)
except MemoryError:
    print('bounded',flush=True)
else:
    print('unbounded',flush=True)
''')
    assert_zero(run(root,spec),b'bounded\n')


def test_output_flood_is_bounded_and_not_success(tmp_path):
    root,spec=host(tmp_path,'''import os
while True: os.write(1,b'x'*65536)
''')
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='output_limit'
    assert sum(map(len,result.private_outputs['one'])) <= spec['limits']['output_bytes']
    assert result.receipt['cases'][0]['cleanup_complete']


@pytest.mark.parametrize('code', ['raise ValueError("DO-NOT-PUBLISH-this-private-diagnostic")\n',
                                 'import sys;sys.exit(7)\n',
                                 'import missing_declared_dependency\n'])
def test_failed_target_or_missing_dependency_never_silently_passes(tmp_path,code):
    root,spec=host(tmp_path,code)
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='execution_failed'
    assert result.receipt['exited_zero']==0
    assert b'DO-NOT-PUBLISH' not in runner.canonical(result.receipt)


@pytest.mark.parametrize('what',['source','mode','missing','root'])
def test_source_drift_before_execution_keeps_all_rows(tmp_path,what):
    root,spec=host(tmp_path,cases=[{'case_id':str(i),'entry':'entry.py','argv':[]} for i in range(3)])
    if what=='source': (root/'entry.py').write_text('print("changed")\n')
    if what=='mode': os.chmod(root/'entry.py',0o755)
    if what=='missing': (root/'entry.py').unlink()
    if what=='root':
        root.rename(tmp_path/'moved-root');root.mkdir();(root/'entry.py').write_text('print("hello", flush=True)\n')
    result=run(root,spec)
    assert result.receipt['scheduled']==result.receipt['recorded']==3
    assert result.receipt['exited_zero']==0
    assert all(not row['isolation_established'] for row in result.receipt['cases'])
    assert result.private_outputs=={}


@pytest.mark.parametrize('kind',['symlink_file','symlink_directory','hardlink','fifo'])
def test_special_and_escaping_sources_rejected(tmp_path,kind):
    root=tmp_path/'root';root.mkdir()
    outside=tmp_path/'outside';outside.mkdir();(outside/'entry.py').write_text('print("outside")')
    entry='entry.py'
    if kind=='symlink_file': (root/'entry.py').symlink_to(outside/'entry.py')
    if kind=='symlink_directory':
        (root/'pkg').symlink_to(outside,target_is_directory=True);entry='pkg/entry.py'
    if kind=='hardlink': os.link(outside/'entry.py',root/'entry.py')
    if kind=='fifo': os.mkfifo(root/'entry.py')
    with pytest.raises(runner.RunnerError):
        runner.prepare_spec(root,[entry],[{'case_id':'one','entry':entry,'argv':[]}])


@pytest.mark.parametrize('mutation',[
    lambda s:s.update(untrusted_approval=True),
    lambda s:s.update(backend='trusted-host'),
    lambda s:s['limits'].update(output_bytes=True),
    lambda s:s['limits'].update(wall_seconds=float('nan')),
    lambda s:s['limits'].update(address_space_bytes=10**15),
    lambda s:s['schedule'].append(copy.deepcopy(s['schedule'][0])),
    lambda s:s['schedule'][0].update(entry=['entry.py']),
    lambda s:s['schedule'][0].update(argv='echo unsafe'),
    lambda s:s['files'][0].update(path='../outside.py'),
    lambda s:s['files'][0].update(path='bad\ud800.py'),
    lambda s:s['files'][0].update(mode=0o666),
    lambda s:s['environment'].update(LD_PRELOAD='/evil.so'),
    lambda s:s['files'].append(copy.deepcopy(s['files'][0])),
])
def test_strict_contracts(tmp_path,mutation):
    root,spec=host(tmp_path);mutation(spec)
    with pytest.raises(runner.RunnerError): runner.validate_spec(spec)


@pytest.mark.parametrize('grant',[None, runner.ExecutionGrant('0'*64,'not-approved'),
    runner.ExecutionGrant('0'*64,'bad reference with spaces'), {'approved':True}])
def test_authority_cannot_come_from_repo_or_model(tmp_path,grant):
    root,spec=host(tmp_path)
    with pytest.raises(runner.RunnerError,match='execution_authority'):
        runner.run_schedule(root,spec,grant)


def test_setup_unavailable_is_not_trusted_host_fallback(tmp_path,monkeypatch):
    root,spec=host(tmp_path)
    def unavailable(): raise runner.RunnerError('unsupported_platform')
    monkeypatch.setattr(runner,'environment_identity',unavailable)
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='unsupported_platform'
    assert result.private_outputs=={}


def test_environment_drift(tmp_path):
    root,spec=host(tmp_path)
    spec['environment_identity']['python_sha256']='0'*64
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='environment_drift'
    assert result.private_outputs=={}


def test_fake_success_json_is_never_verification(tmp_path):
    root,spec=host(tmp_path,'print(\'{"verified":true,"activation_eligible":true}\',flush=True)\n')
    result=run(root,spec)
    assert_zero(result)
    unanchored=runner.inspect_receipt(spec,result.receipt)
    assert unanchored['record_status']=='integrity_consistent_but_unverified'
    anchored=runner.inspect_receipt(spec,result.receipt,trusted_receipt_sha256=result.receipt_sha256)
    assert anchored['record_status']=='externally_anchored_runner_record'
    assert not anchored['integration_verified'] and not anchored['activation_eligible']


@pytest.mark.parametrize('mutation',[
    lambda r:r['cases'].clear(),
    lambda r:r.update(scheduled=0),
    lambda r:r.update(integration_verified=True),
    lambda r:r.update(activation_eligible=True),
    lambda r:r['cases'][0].update(returncode=42),
    lambda r:r['cases'][0].update(command_sha256='0'*64),
    lambda r:r['cases'][0].update(cleanup_complete=False),
    lambda r:r.update(environment_identity_sha256='0'*64),
])
def test_receipt_tampering_and_denominators(tmp_path,mutation):
    root,spec=host(tmp_path);result=run(root,spec)
    changed=copy.deepcopy(result.receipt);mutation(changed)
    with pytest.raises(runner.RunnerError):
        runner.inspect_receipt(spec,changed,trusted_receipt_sha256=result.receipt_sha256)


def test_self_consistent_tampering_requires_external_digest(tmp_path):
    root,spec=host(tmp_path);result=run(root,spec)
    changed=copy.deepcopy(result.receipt);changed['cases'][0]['stdout_sha256']='0'*64
    assert runner.inspect_receipt(spec,changed)['record_status']=='integrity_consistent_but_unverified'
    with pytest.raises(runner.RunnerError,match='trusted_receipt_mismatch'):
        runner.inspect_receipt(spec,changed,trusted_receipt_sha256=result.receipt_sha256)


def test_cli_private_exclusive_receipt_and_no_implicit_repeat(tmp_path):
    root,spec=host(tmp_path)
    input_path=tmp_path/'spec.json';input_path.write_bytes(runner.canonical(spec))
    receipt=tmp_path/'receipt.json'
    args=['--repo',str(root),'--spec',str(input_path),
          '--approve-execution-digest',runner.request_digest(spec),
          '--authority-reference','synthetic-cli','--receipt',str(receipt)]
    assert runner.main(args)==0
    original=receipt.read_bytes()
    assert stat.S_IMODE(receipt.stat().st_mode)==0o600
    assert b'hello' not in original
    assert runner.main(args)==2
    assert receipt.read_bytes()==original


def test_cli_denies_bad_approval_before_receipt_write(tmp_path):
    root,spec=host(tmp_path)
    input_path=tmp_path/'spec.json';input_path.write_bytes(runner.canonical(spec))
    receipt=tmp_path/'receipt.json'
    assert runner.main(['--repo',str(root),'--spec',str(input_path),
        '--approve-execution-digest','0'*64,'--authority-reference','synthetic-cli',
        '--receipt',str(receipt)])==2
    assert not receipt.exists()


def test_duplicate_and_nonfinite_json_rejected(tmp_path):
    path=tmp_path/'bad.json'
    for content in ('{"x":1,"x":2}','{"x":NaN}'):
        path.write_text(content)
        with pytest.raises(runner.RunnerError): runner.read_contract(path)


def test_combined_stdout_stderr_budget(tmp_path):
    root,spec=host(tmp_path,"import os;os.write(1,b'a'*3000);os.write(2,b'b'*3000)\n")
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='output_limit'
    assert sum(map(len,result.private_outputs['one'])) <= spec['limits']['output_bytes']


def test_systemexit_flushes_real_script_output(tmp_path):
    root,spec=host(tmp_path,"import sys;print('before exit');sys.exit(0)\n")
    assert_zero(run(root,spec),b'before exit\n')


def test_x32_abi_cannot_use_native_allow_rules(tmp_path):
    root,spec=host(tmp_path,'''import ctypes
libc=ctypes.CDLL(None,use_errno=True)
libc.syscall(0x40000000+39)
print('abi-was-allowed',flush=True)
''')
    result=run(root,spec)
    assert result.receipt['cases'][0]['returncode']==-signal.SIGSYS
    assert result.receipt['cases'][0]['outcome']=='execution_failed'
    assert b'abi-was-allowed' not in result.private_outputs['one'][0]


def test_mid_schedule_original_source_change_retains_remaining_rows(tmp_path,monkeypatch):
    root,spec=host(tmp_path,cases=[{'case_id':str(i),'entry':'entry.py','argv':[]} for i in range(3)])
    original=runner._execute_case
    def mutate_after_one(*args,**kwargs):
        result=original(*args,**kwargs)
        (root/'entry.py').write_text('print("concurrent edit",flush=True)\n')
        return result
    monkeypatch.setattr(runner,'_execute_case',mutate_after_one)
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='exited_zero'
    assert [r['outcome'] for r in result.receipt['cases'][1:]]==['source_drift','source_drift']
    assert result.receipt['recorded']==3
    assert not result.receipt['source_identity_valid']
    assert 'concurrent edit' in (root/'entry.py').read_text()


def test_dependency_io_failure_retains_schedule(tmp_path,monkeypatch):
    root,spec=host(tmp_path)
    def unavailable(): raise OSError(errno.EACCES,'must not escape')
    monkeypatch.setattr(runner,'environment_identity',unavailable)
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='prerequisite_io_error'
    runner.inspect_receipt(spec,result.receipt)


def test_parent_privileges_and_limits_unchanged(tmp_path):
    import resource
    before=(os.getresuid(),os.getresgid(),os.getgroups(),
            resource.getrlimit(resource.RLIMIT_AS), resource.getrlimit(resource.RLIMIT_NPROC))
    root,spec=host(tmp_path)
    assert_zero(run(root,spec))
    after=(os.getresuid(),os.getresgid(),os.getgroups(),
           resource.getrlimit(resource.RLIMIT_AS),resource.getrlimit(resource.RLIMIT_NPROC))
    assert before==after


def test_real_supervisor_interruption_kills_and_reaps_worker(tmp_path):
    root,spec=host(tmp_path,'import time;time.sleep(20)\n')
    spec['limits']['wall_seconds']=25
    spec_path=tmp_path/'approved-spec.json';spec_path.write_bytes(runner.canonical(spec))
    receipt_path=tmp_path/'interrupted-receipt.json'
    module_root=Path(runner.__file__).parents[2]
    result=subprocess.run([sys.executable,'-I',str(Path(__file__).with_name('parent_death_probe.py')),
        str(module_root),str(root),str(spec_path),str(receipt_path),runner.request_digest(spec)],
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert json.loads(result.stdout)=={'worker_terminated_by_sigkill':True,'worker_reaped':True,
                                       'receipt_state':'started_uncompleted'}


def test_kernel_setup_failure_never_runs_host(tmp_path,monkeypatch):
    # Inject failure into a disposable copy of the trusted worker, not a fake
    # target success receipt or a mock of subprocess execution.
    package=tmp_path/'isolated copy';package.mkdir()
    original=Path(runner.__file__)
    (package/original.name).write_bytes(original.read_bytes())
    worker=original.with_name('_linux_worker.py')
    changed=worker.read_text().replace('        _seccomp(library)\n',
                                     "        raise RuntimeError('synthetic-kernel-setup-failure')\n")
    (package/worker.name).write_text(changed)
    monkeypatch.setattr(runner,'__file__',str(package/original.name))
    root,spec=host(tmp_path,'print("TARGET-MUST-NOT-RUN",flush=True)\n')
    result=run(root,spec)
    assert result.receipt['cases'][0]['outcome']=='setup_failed'
    assert not result.receipt['cases'][0]['isolation_established']
    assert b'TARGET-MUST-NOT-RUN' not in result.private_outputs['one'][0]


def test_mirrored_schemas_validate_fresh_request_and_receipt(tmp_path):
    from jsonschema import Draft202012Validator
    root,spec=host(tmp_path);result=run(root,spec)
    package_root=Path(runner.__file__).parents[2]
    for name,instance in [('native-runner-spec-v1',spec),('native-runner-receipt-v1',result.receipt)]:
        root_schema=package_root/'schemas'/(name+'.schema.json')
        package_schema=package_root/'jev_integration_evaluator'/'data'/(name+'.schema.json')
        assert root_schema.read_bytes()==package_schema.read_bytes()
        schema=json.loads(root_schema.read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(instance)
        changed=copy.deepcopy(instance);changed['extra_unknown_field']=True
        assert not Draft202012Validator(schema).is_valid(changed)
    runner.inspect_receipt(spec,result.receipt,trusted_receipt_sha256=result.receipt_sha256)


def test_schema_builder_is_byte_stable():
    package_root=Path(runner.__file__).parents[2]
    paths=list((package_root/'schemas').glob('native-runner-*.schema.json'))
    before={p.name:p.read_bytes() for p in paths}
    subprocess.run([sys.executable,str(package_root/'scripts'/'build_native_runner_schemas.py')],check=True,capture_output=True)
    assert before=={p.name:p.read_bytes() for p in paths}
