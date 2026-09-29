"""Source-bound Python console binding and actual independent host entrypoint."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest

from scripts.implementation_fixtures import fixture
from jev_integration_evaluator.io import digest, read_json, write_json
from jev_integration_evaluator.template_catalog import prepare_template_binding
from jev_integration_evaluator.integrations.lifecycle import plan_implementation
from jev_integration_evaluator.integrations.lifecycle import apply_implementation, rollback_implementation, implementation_status
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.integrations.recipes import host_lifecycle_marker
from jev_integration_evaluator.integrations.python_entrypoint import inspect_entrypoint


def _prepared(tmp_path: Path, layout: str = 'package', tag: str = 'console', loop: bool = False):
    target = tmp_path / 'target'
    package_name = 'birch_pkg' if layout == 'src' else 'atlas_pkg'
    inventory, spec = fixture(target, 'C', tag=tag, layout=layout, console_exit=True,
                              package_name=package_name)
    package = target / ('src/' + package_name if layout == 'src' else package_name)
    host = Path(spec['source']['file']).stem
    entry = spec['verification']['entry_point']
    script = f'fixture-{tag}'
    pyproject = f'''[build-system]\nrequires = ["setuptools>=68"]\nbuild-backend = "setuptools.build_meta"\n[project]\nname = "fixture-{tag}"\nversion = "1.0.0"\nrequires-python = ">=3.10"\n[project.scripts]\n{script} = "{package_name}.console:main"\n[tool.setuptools.packages.find]\nwhere = ["src"]\ninclude = ["{package_name}*"]\n[tool.setuptools.package-data]\n{package_name} = ["*.lock", "*.json"]\n''' if layout == 'src' else f'''[build-system]\nrequires = ["setuptools>=68"]\nbuild-backend = "setuptools.build_meta"\n[project]\nname = "fixture-{tag}"\nversion = "1.0.0"\nrequires-python = ">=3.10"\n[project.scripts]\n{script} = "{package_name}.console:main"\n[tool.setuptools.packages.find]\ninclude = ["{package_name}*"]\n[tool.setuptools.package-data]\n{package_name} = ["*.lock", "*.json"]\n'''
    (target / 'pyproject.toml').write_text(pyproject, encoding='utf-8')
    request_body = ('    return [{"task_id": "fixture-one", "objective": "bounded offline task", "command": "/prune"}, '
                    '{"task_id": "fixture-two", "objective": "bounded offline task", "command": "/prune"}]'
                    if loop else '    return {"task_id": "fixture-task", "objective": "bounded offline task", "command": "/prune"}')
    main_body = (f'    requests = make_request()\n    for request in requests:\n        {entry}(request)\n    return 0'
                 if loop else f'    request = make_request()\n    return {entry}(request)')
    source = f'''from .{host} import {entry}
from . import {host} as observed_host
from pathlib import Path
import atexit
import hashlib
import json
import os

CLIENT = None

def record_state():
    path = os.environ.get("JEV_FIXTURE_RECORD")
    if path:
        marker = os.environ["JEV_FIXTURE_MARKER"]
        Path(path).write_text(json.dumps({{"effects": observed_host.STATE["effects"], "started": getattr(observed_host, marker + "_started"), "closed": getattr(observed_host, marker) is None, "model_calls": CLIENT.calls if CLIENT is not None else 0}}), encoding="utf-8")

atexit.register(record_state)

class Audit:
    def append(self, record):
        pass

def limits():
    return dict(max_calls_per_task=2, max_cost_per_task=2, max_total_calls=2, max_total_cost=2, max_in_flight=1, max_tasks=2)

def audit():
    return Audit()

def dependencies():
    base = Path(__file__).resolve().parent
    return {{"files": [{{"path": str(base / name), "sha256": hashlib.sha256((base / name).read_bytes()).hexdigest()}} for name in ("requirements.lock", "runtime.json")]}}

def options():
    global CLIENT
    if os.environ.get("JEV_FIXTURE_MODE") == "shadow":
        from jev_integration_evaluator.integrations.probe import SyntheticClient
        CLIENT = SyntheticClient("alternative")
        return {{"startup_mode": "shadow", "client": CLIENT, "enable_experiment": True}}
    return {{}}

def make_request():
{request_body}

def main():
{main_body}
'''
    (package / 'console.py').write_text(source, encoding='utf-8')
    runtime_files = {'requirements.lock': ('dependency_lock',
        'jev-integration-evaluator==1.3.0.dev1\n', 'jev-integration-evaluator==1.3.0.dev12\n'),
        'runtime.json': ('configuration',
        '{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
        '{"jev_runtime":{"mode":"off","credential_ref":"env:TYPESAFE_API_KEY"}}\n')}
    for name, (kind, old, new) in runtime_files.items():
        path = package / name
        path.write_bytes(old.encode('utf-8'))
        rel = path.relative_to(target).as_posix()
        inventory['configuration_evidence'].append({'file': rel, 'sha256': hashlib.sha256(old.encode()).hexdigest()})
        spec.setdefault('runtime_files', []).append({'file': rel, 'kind': kind,
            'old_sha256': hashlib.sha256(old.encode()).hexdigest(), 'new_content': new})
        spec['output']['permitted_edits'].append(rel)
    inventory['analysis_identity']['configuration_digest'] = digest(inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    spec['inventory_sha256'] = digest(inventory)
    spec['inventory_fingerprint'] = inventory['scan_fingerprint']
    spec['host_lifecycle'] = {'kind': 'module-startup-v1', 'startup': 'start_jev_runtime',
                              'shutdown': 'stop_jev_runtime', 'complete_task': 'finish_jev_task'}
    request = {'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
               'template_version': '1.0.0', 'backend': 'python', 'profile': 'module-tail-call-v1',
               'reviewed_inventory': inventory, 'implementation_spec': spec}
    binding = {'version': '1.0', 'script': script,
               'startup_inputs': {'budget_limits': 'limits', 'audit_log': 'audit',
                                  'dependency_plan': 'dependencies', 'startup_options': 'options'}}
    return target, request, binding


@pytest.mark.parametrize('layout', ['package', 'src'])
def test_bind_two_package_layouts_and_exact_owned_plan(tmp_path, layout):
    target, request, binding = _prepared(tmp_path, layout, layout)
    prepared = prepare_template_binding(target, request, binding)
    assert prepared['binding_report']['status'] == 'planned_not_applied'
    spec = prepared['request']['implementation_spec']
    assert spec['entrypoint_binding']['module'] in ('atlas_pkg.console', 'birch_pkg.console')
    assert spec['entrypoint_binding']['file'] in spec['output']['permitted_edits']
    result = plan_implementation(target, prepared['request']['reviewed_inventory'],
                                 spec['candidate_id'], spec, tmp_path / 'bundle')
    assert result['status'] == 'planned'
    assert 'return ' + spec['entrypoint_binding']['task_symbol'] in (target / spec['entrypoint_binding']['file']).read_text()


def test_template_bind_cli_writes_same_source_bound_request(tmp_path):
    target, request, binding = _prepared(tmp_path)
    expected = prepare_template_binding(target, request, binding)
    write_json(tmp_path / 'request.json', request)
    write_json(tmp_path / 'binding.json', binding)
    command = [sys.executable, '-m', 'jev_integration_evaluator', 'template', 'bind',
               '--repo', str(target), '--request', str(tmp_path / 'request.json'),
               '--binding', str(tmp_path / 'binding.json'), '--out', str(tmp_path / 'bound')]
    run = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert read_json(tmp_path / 'bound/template-request.json') == expected['request']
    assert read_json(tmp_path / 'bound/binding-report.json') == expected['binding_report']
    assert read_json(tmp_path / 'bound/bind-status.json')['status'] == 'complete'


def test_bind_rejects_stale_script_and_ambiguous_startup(tmp_path):
    target, request, binding = _prepared(tmp_path)
    stale = copy.deepcopy(binding)
    stale['script'] = 'missing'
    with pytest.raises(Exception, match='console script'):
        prepare_template_binding(target, request, stale)
    path = target / 'atlas_pkg' / 'console.py'
    path.write_text(path.read_text() + '\nlimits = None\n', encoding='utf-8')
    with pytest.raises(Exception, match='entrypoint function'):
        prepare_template_binding(target, request, binding)


def test_nested_package_caller_and_malformed_source_fail_closed(tmp_path):
    root = tmp_path / 'nested'
    for rel in ('pkg', 'pkg/core', 'pkg/cli'):
        path = root / rel
        path.mkdir(parents=True, exist_ok=True)
        (path / '__init__.py').write_text('"""Reviewed package."""\n', encoding='utf-8')
    host = root / 'pkg/core/host.py'
    host.write_text('def seam(request):\n    return 0\n\ndef task(request):\n    return seam(request)\n', encoding='utf-8')
    entry = root / 'pkg/cli/console.py'
    entry.write_text('from ..core.host import task\n\ndef make_request():\n    return {"task_id":"one"}\n\ndef limits():\n    return {}\n\ndef audit():\n    return None\n\ndef dependencies():\n    return {}\n\ndef options():\n    return {}\n\ndef main():\n    request = make_request()\n    return task(request)\n', encoding='utf-8')
    pyproject = root / 'pyproject.toml'
    pyproject.write_text('[project]\nname="nested"\nversion="1"\n[project.scripts]\nnested="pkg.cli.console:main"\n', encoding='utf-8')
    spec = {'recipe': {'id': 'python.C'}, 'source': {'file': 'pkg/core/host.py', 'symbol': 'seam'},
            'package_binding': {'version': '1.0', 'module': 'pkg.core.host', 'namespace': False},
            'host_lifecycle': {'kind': 'module-startup-v1', 'startup': 'start',
                               'shutdown': 'stop', 'complete_task': 'complete'},
            'runtime_files': [{'file': 'pkg/core/requirements.lock'}, {'file': 'pkg/core/runtime.json'}]}
    binding = {'version': '1.0', 'script': 'nested', 'startup_inputs': {
        'budget_limits': 'limits', 'audit_log': 'audit',
        'dependency_plan': 'dependencies', 'startup_options': 'options'}}
    result = inspect_entrypoint(root, spec, binding)
    assert result['module'] == 'pkg.cli.console'
    assert result['contributing_sources']['pkg/core/host.py'] == hashlib.sha256(host.read_bytes()).hexdigest()
    host.write_text('def seam(request):\n    return 0\n\ndef task():\n    return seam({})\n', encoding='utf-8')
    with pytest.raises(Exception, match='task caller'):
        inspect_entrypoint(root, spec, binding)
    pyproject.write_text('[[project]]\nname="bad"\n', encoding='utf-8')
    with pytest.raises(Exception, match='project'):
        inspect_entrypoint(root, spec, binding)


def test_bind_drift_and_exact_owned_rollback(tmp_path):
    target, request, binding = _prepared(tmp_path)
    bound = prepare_template_binding(target, request, binding)['request']
    spec = bound['implementation_spec']
    entry = target / spec['entrypoint_binding']['file']
    pyproject = target / 'pyproject.toml'
    original_pyproject = pyproject.read_bytes()
    pyproject.write_bytes(original_pyproject + b'\n# changed\n')
    with pytest.raises(Exception, match='drift'):
        plan_implementation(target, request['reviewed_inventory'], spec['candidate_id'], spec,
                            tmp_path / 'stale-bundle')
    pyproject.write_bytes(original_pyproject)
    plan = plan_implementation(target, request['reviewed_inventory'], spec['candidate_id'], spec,
                               tmp_path / 'bundle')
    baseline = verify_implementation(target, tmp_path / 'bundle', 'baseline', approve_execution=True)
    applied = apply_implementation(target, tmp_path / 'bundle', plan['bundle_digest'],
                                   baseline_sha256=baseline['receipt_sha256'])
    neighbor = target / 'unrelated.txt'
    neighbor.write_text('keep', encoding='utf-8')
    edited = entry.read_bytes()
    entry.write_bytes(edited + b'\n# outside edit\n')
    with pytest.raises(Exception):
        rollback_implementation(target, tmp_path / 'bundle', applied['rollback_digest'])
    entry.write_bytes(edited)
    assert rollback_implementation(target, tmp_path / 'bundle', applied['rollback_digest'])['status'] == 'rolled_back'
    assert neighbor.read_text(encoding='utf-8') == 'keep'


@pytest.mark.parametrize('role', ['registry', 'gate'])
def test_bind_refuses_registry_or_policy_source_drift(tmp_path, role):
    target, request, binding = _prepared(tmp_path)
    original = prepare_template_binding(target, request, binding)
    assert original['binding_report']['status'] == 'planned_not_applied'
    host = target / request['implementation_spec']['source']['file']
    raw = host.read_bytes()
    old, new = ((b'return dict(OPTIONS)', b'return dict(OPTIONS)  # registry changed')
                if role == 'registry' else
                (b"hard_block=STATE['hard_block']", b"hard_block=not STATE['hard_block']"))
    assert old in raw
    host.write_bytes(raw.replace(old, new, 1))
    with pytest.raises(Exception, match='Source drift|changed'):
        prepare_template_binding(target, request, binding)


@pytest.mark.parametrize('missing', ['audit_factory', 'dependency_lock'])
def test_bind_refuses_missing_host_prerequisites(tmp_path, missing):
    target, request, binding = _prepared(tmp_path)
    if missing == 'audit_factory':
        source = target / 'atlas_pkg/console.py'
        source.write_text(source.read_text(encoding='utf-8').replace('def audit():', 'def removed_audit():'),
                          encoding='utf-8')
        with pytest.raises(Exception, match='entrypoint function'):
            prepare_template_binding(target, request, binding)
    else:
        lock = target / 'atlas_pkg/requirements.lock'
        lock.unlink()
        with pytest.raises(Exception, match='Source drift|Runtime file'):
            prepare_template_binding(target, request, binding)


@pytest.mark.parametrize('coverage', ['missing_entry', 'missing_pyproject', 'entry_drift'])
def test_connected_startup_requires_exact_console_and_pyproject_source_plan(tmp_path, coverage):
    target, request, binding = _prepared(tmp_path)
    spec = prepare_template_binding(target, request, binding)['request']['implementation_spec']
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, request['reviewed_inventory'], spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    apply_implementation(target, bundle, planned['bundle_digest'],
                         baseline_sha256=baseline['receipt_sha256'])
    entry = target / spec['entrypoint_binding']['file']
    pyproject = target / 'pyproject.toml'
    rows = [{'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in (entry, pyproject)]
    if coverage == 'missing_entry':
        rows = rows[1:]
    elif coverage == 'missing_pyproject':
        rows = rows[:1]
    else:
        rows[0]['sha256'] = '0' * 64
    marker = host_lifecycle_marker(spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    code = '''import importlib,json,sys
sys.path.insert(0,sys.argv[1]);sys.path.append(sys.argv[2])
host=importlib.import_module(sys.argv[3]);console=importlib.import_module(sys.argv[4])
try:
    host.start_jev_runtime(budget_limits=console.limits(),audit_log=console.audit(),
        dependency_plan=console.dependencies(),startup_mode='shadow',
        connected_config={'source_plan':{'files':json.loads(sys.argv[5])}})
except Exception as exc:
    result=[type(exc).__name__,str(exc)]
else:
    result=['unexpected_success']
print(json.dumps({'result':result,'started':getattr(host,sys.argv[6]+'_started')}))
'''
    run = subprocess.run([sys.executable, '-I', '-c', code,
                          str(Path(__file__).resolve().parents[1]), str(target),
                          spec['package_binding']['module'], spec['entrypoint_binding']['module'],
                          json.dumps(rows), marker], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {'result': ['LifecycleError', 'connected_entrypoint_source_plan_missing'],
                                      'started': False}


@pytest.mark.parametrize('mode', ['duplicate', 'unbounded', 'mutate'])
def test_loop_preflight_and_task_id_snapshot(tmp_path, mode):
    target, request, binding = _prepared(tmp_path, tag='identity_' + mode, loop=True)
    bound = prepare_template_binding(target, request, binding)['request']
    spec = bound['implementation_spec']
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, request['reviewed_inventory'], spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    apply_implementation(target, bundle, planned['bundle_digest'],
                         baseline_sha256=baseline['receipt_sha256'])
    marker = host_lifecycle_marker(spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    code = '''import importlib,json,sys
sys.path.insert(0,sys.argv[1]);sys.path.append(sys.argv[2])
host=importlib.import_module(sys.argv[3]+'.'+sys.argv[4]);console=importlib.import_module(sys.argv[3]+'.console')
mode=sys.argv[5]
if mode=='duplicate':
    console.make_request=lambda:[{'task_id':'same'},{'task_id':'same'}]
elif mode=='unbounded':
    console.make_request=lambda:iter([{'task_id':'one'}])
else:
    def mutate(request):
        host.STATE['effects'].append('first');request['task_id']='changed';return 0
    setattr(host,sys.argv[6],mutate)
try:
    result=console.main();outcome=['return',result]
except BaseException as exc:
    outcome=['exception',type(exc).__name__,str(exc)]
print(json.dumps({'outcome':outcome,'effects':host.STATE['effects'],
 'started':getattr(host,sys.argv[7]+'_started'),'closed':getattr(host,sys.argv[7]) is None}))
'''
    env = os.environ.copy()
    env['JEV_FIXTURE_MODE'] = 'shadow'
    env.pop('PYTHONPATH', None)
    run = subprocess.run([sys.executable, '-I', '-c', code,
                          str(Path(__file__).resolve().parents[1]), str(target),
                          'atlas_pkg', Path(spec['source']['file']).stem, mode,
                          'perform_primary_identity_' + mode, marker], cwd=tmp_path,
                         env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    observed = json.loads(run.stdout)
    assert observed['closed'] is True
    if mode == 'duplicate':
        assert observed['outcome'] == ['exception', 'ValueError', 'duplicate_task_identity']
        assert observed['started'] is False and observed['effects'] == []
    elif mode == 'unbounded':
        assert observed['outcome'] == ['exception', 'ValueError', 'invalid_bounded_task_schedule']
        assert observed['started'] is False and observed['effects'] == []
    else:
        assert observed['outcome'] == ['exception', 'RuntimeError', 'task_identity_changed']
        assert observed['started'] is True and observed['effects'] == ['first']


@pytest.mark.parametrize('failure,loop', [('none', False), ('executor', False),
    ('finisher', False), ('cancel', False), ('repeat', False), ('none', True), ('cancel', True)])
def test_console_lifecycle_order_identity_and_failure_propagation(tmp_path, failure, loop):
    target, request, binding = _prepared(tmp_path, tag='fault_' + failure, loop=loop)
    bound = prepare_template_binding(target, request, binding)['request']
    spec = bound['implementation_spec']
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, request['reviewed_inventory'], spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    apply_implementation(target, bundle, planned['bundle_digest'],
                         baseline_sha256=baseline['receipt_sha256'])
    marker = host_lifecycle_marker(spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    effect = 'perform_primary_' + 'fault_' + failure
    code = '''import importlib,json,os,sys
sys.path.insert(0,sys.argv[1]);sys.path.append(sys.argv[2])
from jev_integration_evaluator.integrations.runtime_lifecycle import HostRuntimeLifecycle as L
host=importlib.import_module(sys.argv[3]+'.'+sys.argv[4]); console=importlib.import_module(sys.argv[3]+'.console')
events=[]
original_init,original_router,original_complete,original_close=L.__init__,L.router,L.complete_task,L.close
def init(self,*args,**kwargs):
    original_init(self,*args,**kwargs);events.append(['start',id(self.coordinator)])
def router(self,*args,**kwargs):
    result=original_router(self,*args,**kwargs)
    events.append(['route',id(result),id(result.budget_coordinator)])
    return result
def complete(self,task_id):
    events.append(['complete',task_id,len(host.STATE['effects'])]);return original_complete(self,task_id)
def close(self):
    events.append(['close',len(host.STATE['effects'])]);return original_close(self)
L.__init__,L.router,L.complete_task,L.close=init,router,complete,close
failure=sys.argv[5]
if failure in ('executor','cancel'):
    def fail(request):
        host.STATE['effects'].append('first')
        raise KeyboardInterrupt('cancelled') if failure=='cancel' else RuntimeError('executor_failed')
    setattr(host,sys.argv[6],fail)
elif failure=='finisher':
    original_task=getattr(console,sys.argv[7])
    def fail(request):
        original_task(request)
        raise RuntimeError('finisher_failed')
    setattr(console,sys.argv[7],fail)
try:
    result=console.main()
    outcome=['return',result]
    if failure=='repeat':
        console.main()
except BaseException as exc:
    outcome=['exception',type(exc).__name__,str(exc)]
print(json.dumps({'events':events,'effects':host.STATE['effects'],
                  'outcome':outcome,'started':getattr(host,sys.argv[8]+'_started'),
                  'closed':getattr(host,sys.argv[8]) is None}))
'''
    env = os.environ.copy()
    env['JEV_FIXTURE_MODE'] = 'shadow'
    env.pop('PYTHONPATH', None)
    run = subprocess.run([sys.executable, '-I', '-c', code,
                          str(Path(__file__).resolve().parents[1]), str(target),
                          'atlas_pkg', Path(spec['source']['file']).stem,
                          failure, effect, spec['verification']['entry_point'], marker],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    observed = json.loads(run.stdout)
    assert observed['effects'] == ['first'] * (2 if loop and failure == 'none' else 1)
    assert observed['started'] is True and observed['closed'] is True
    kinds = [row[0] for row in observed['events']]
    if loop and failure == 'none':
        assert kinds == ['start', 'route', 'complete', 'route', 'complete', 'close']
        assert observed['events'][0][1] == observed['events'][1][2] == observed['events'][3][2]
        assert observed['events'][1][1] == observed['events'][3][1]
        assert observed['events'][2][1:] == ['fixture-one', 1]
        assert observed['events'][4][1:] == ['fixture-two', 2]
        assert observed['events'][5][1] == 2
    else:
        assert kinds == ['start', 'route', 'complete', 'close']
        assert observed['events'][0][1] == observed['events'][1][2]
        assert observed['events'][2][1:] == ['fixture-one' if loop else 'fixture-task', 1]
        assert observed['events'][3][1] == 1
    if failure == 'none':
        assert observed['outcome'] == ['return', 0]
    elif failure == 'repeat':
        assert observed['outcome'] == ['exception', 'RuntimeError', 'host_runtime_already_started']
    elif failure == 'cancel':
        assert observed['outcome'] == ['exception', 'KeyboardInterrupt', 'cancelled']
    else:
        assert observed['outcome'] == ['exception', 'RuntimeError', failure + '_failed']


@pytest.mark.parametrize('layout', ['package', 'src'])
def test_installed_console_reaches_owned_integration_and_rolls_back(tmp_path, layout):
    loop = layout == 'package'
    target, request, binding = _prepared(tmp_path, layout, 'launch_' + layout, loop=loop)
    prepared = prepare_template_binding(target, request, binding)
    spec = prepared['request']['implementation_spec']
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, request['reviewed_inventory'], spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                   baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified', modified
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])['status'] == 'verified'
    buildsrc = tmp_path / 'buildsrc'
    shutil.copytree(target, buildsrc)
    dist = tmp_path / 'dist'
    dist.mkdir()
    evaluator = Path(__file__).resolve().parents[1]
    for source in (buildsrc, evaluator):
        build = subprocess.run([sys.executable, '-c',
            'import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))',
            str(dist)], cwd=source, capture_output=True, text=True, timeout=90)
        assert build.returncode == 0, build.stderr
    environment = tmp_path / 'venv'
    venv.EnvBuilder(with_pip=False, system_site_packages=True).create(environment)
    binary = 'Scripts' if os.name == 'nt' else 'bin'
    python = environment / binary / ('python.exe' if os.name == 'nt' else 'python')
    wheels = sorted(dist.glob('*.whl'))
    assert len(wheels) == 2
    install = subprocess.run([sys.executable, '-m', 'pip', '--python', str(python),
                              'install', '--no-index', '--no-deps',
                              *(str(w) for w in wheels)], capture_output=True, text=True, timeout=90)
    assert install.returncode == 0, install.stderr
    script = environment / binary / (binding['script'] + ('.exe' if os.name == 'nt' else ''))
    record = tmp_path / 'record.json'
    marker = host_lifecycle_marker(spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    env = os.environ.copy()
    env['JEV_FIXTURE_RECORD'] = str(record)
    env['JEV_FIXTURE_MARKER'] = marker
    env.pop('PYTHONPATH', None)
    run = subprocess.run([str(script)], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    observed = json.loads(record.read_text(encoding='utf-8'))
    count = 2 if loop else 1
    assert observed == {'effects': ['first'] * count, 'started': True, 'closed': True, 'model_calls': 0}
    env['JEV_FIXTURE_MODE'] = 'shadow'
    shadow = subprocess.run([str(script)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=30)
    assert shadow.returncode == 0, shadow.stderr
    shadow_observed = json.loads(record.read_text(encoding='utf-8'))
    assert shadow_observed['effects'] == ['first'] * count
    assert shadow_observed['started'] is True and shadow_observed['closed'] is True
    assert 1 <= shadow_observed['model_calls'] <= count
    assert rollback_implementation(target, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
