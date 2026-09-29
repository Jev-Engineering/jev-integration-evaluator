"""Independent offline runtime observations for generated adaptation modules."""
from __future__ import annotations

import ast
import asyncio
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv
from types import SimpleNamespace

import pytest

from jev_integration_evaluator.integrations.adaptation_shapes import prepare_shape
from jev_integration_evaluator.integrations.adaptation_runtime import (
    inspect_runtime_package, render_adapter, invoke_sync, invoke_async)
from jev_integration_evaluator.integrations.adaptation_adapter_lifecycle import (
    plan_generated_adapter, apply_generated_adapter, rollback_generated_adapter,
    generated_adapter_status)
from jev_integration_evaluator.integrations.errors import UnsupportedShape
from jev_integration_evaluator.integrations.lifecycle import engine_identity
from jev_integration_evaluator.io import digest
from scripts.implementation_fixtures import fixture


def test_runtime_adaptation_schema_copies_match():
    root = Path(__file__).resolve().parents[1]
    for name in ('generated-adaptation-adapter-request-v1',
                 'generated-adaptation-adapter-plan-v1',
                 'adaptation-runtime-caller-review-v1',
                 'adaptation-runtime-review-receipt-v1'):
        mirror = json.loads((root / 'schemas' / (name + '.schema.json')).read_text())
        packaged = json.loads((root / 'jev_integration_evaluator/data' /
                               (name + '.schema.json')).read_text())
        assert mirror == packaged


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _edit(source: str, shape: str, symbol: str) -> dict:
    tree = ast.parse(source)
    if '.' in symbol:
        owner, name = symbol.split('.')
        selected = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner)
        selected = next(n for n in selected.body if isinstance(n, ast.FunctionDef) and n.name == name)
    else:
        selected = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and n.name == symbol)
    raw = source.encode()
    return prepare_shape(raw, shape=shape, symbol=symbol, source_sha256=_sha(raw),
                         anchor_sha256=digest(ast.dump(selected.body[-1], annotate_fields=True,
                                                       include_attributes=False)), adapter_name='adapter')


FIXED = '''from . import adapter
events = []
def baseline(request, left, right):
    events.append((request['task_id'], left, right))
    return left + right
def run(request, left, right):
    return baseline(request, left, right)
'''


def test_fixed_positional_grammar_preserves_binding_and_rejects_mutations():
    proposal = _edit(FIXED, 'module-fixed-positional-tail-call-v1', 'run')
    assert proposal['binding_map'] == [
        {'position': 0, 'seam_parameter': 'request', 'baseline_parameter': 'request'},
        {'position': 1, 'seam_parameter': 'left', 'baseline_parameter': 'left'},
        {'position': 2, 'seam_parameter': 'right', 'baseline_parameter': 'right'},
    ]
    assert 'adapter.invoke(baseline, (request, left, right))' in proposal['new_content']
    for source in (
        FIXED.replace('right):', 'right=0):'),
        FIXED.replace('right):', '*right):'),
        FIXED.replace('return baseline(request, left, right)', 'return baseline(request, right, left)'),
        FIXED.replace('return baseline(request, left, right)', 'return baseline(request, left, right) if left else 0'),
        FIXED.replace('return baseline(request, left, right)', 'left += 1\n    return baseline(request, left, right)'),
        FIXED.replace('return baseline(request, left, right)', 'return baseline(request, left, left)'),
    ):
        with pytest.raises(UnsupportedShape):
            _edit(source, 'module-fixed-positional-tail-call-v1', 'run')


def test_runtime_off_preserves_receiver_argument_order_and_exception_object():
    module = SimpleNamespace(SHAPE='instance-method-tail-call-v1', _RUNTIME=None)
    calls = []
    error = LookupError('host instance')
    class Receiver:
        def original(self, request):
            calls.append((self, request))
            if request == 'error':
                raise error
            return request
    receiver = Receiver()
    assert invoke_sync(module, receiver.original, ('ok',)) == 'ok'
    with pytest.raises(LookupError) as caught:
        invoke_sync(module, receiver.original, ('error',))
    assert caught.value is error
    assert calls == [(receiver, 'ok'), (receiver, 'error')]
    fixed = SimpleNamespace(SHAPE='module-fixed-positional-tail-call-v1',
                            POSITIONAL_COUNT=3, REQUEST_POSITION=0, _RUNTIME=None)
    values = ({'task_id': 'one'}, object(), object())
    assert invoke_sync(fixed, lambda *args: args, values) == values


def test_runtime_async_off_await_cancellation_timeout_and_error_identity():
    module = SimpleNamespace(SHAPE='async-module-tail-call-v1', _RUNTIME=None)
    error = LookupError('same object')
    events = []
    started = asyncio.Event()
    async def original(request):
        events.append(('start', request))
        started.set()
        if request == 'error':
            raise error
        if request in ('cancel', 'timeout'):
            await asyncio.sleep(.1)
        events.append(('finish', request))
        return request
    async def exercise():
        before = invoke_async(module, original, 'before')
        before.close()
        assert events == []
        assert await invoke_async(module, original, 'ok') == 'ok'
        with pytest.raises(LookupError) as caught:
            await invoke_async(module, original, 'error')
        assert caught.value is error
        started.clear()
        during = asyncio.create_task(invoke_async(module, original, 'cancel'))
        await started.wait()
        during.cancel()
        with pytest.raises(asyncio.CancelledError):
            await during
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(invoke_async(module, original, 'timeout'), timeout=.01)
        after = asyncio.create_task(invoke_async(module, original, 'after'))
        assert await after == 'after'
        after.cancel()
        assert after.result() == 'after'
    asyncio.run(exercise())
    assert events.count(('start', 'cancel')) == 1
    assert events.count(('start', 'timeout')) == 1
    assert ('finish', 'cancel') not in events
    assert ('finish', 'timeout') not in events
    assert events.count(('finish', 'after')) == 1


METHOD = '''from . import adapter
events = []
class Worker:
    def baseline(self, request):
        events.append(('effect', request['task_id']))
        if request.get('error'):
            raise LookupError('same host failure')
        return len(events)
    def run(self, request):
        return self.baseline(request)
'''
ASYNC = '''from . import adapter
import asyncio
events = []
async def baseline(request):
    events.append(('start', request['task_id']))
    await asyncio.sleep(0)
    if request.get('error'):
        raise LookupError('same async failure')
    events.append(('finish', request['task_id']))
    return len(events)
async def run(request):
    return await baseline(request)
'''


def _host(tmp_path: Path, shape: str, layout: str = 'package') -> tuple[Path, str]:
    target = tmp_path / 'installed_host'
    package = target / ('src/sample_pkg' if layout == 'src' else 'sample_pkg')
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('', encoding='utf-8')
    source = (METHOD if shape.startswith('instance') else
              FIXED if shape.startswith('module-fixed') else ASYNC)
    symbol = 'Worker.run' if shape.startswith('instance') else 'run'
    edit = _edit(source, shape, symbol)
    (package / 'host.py').write_bytes(edit['new_content'].encode('utf-8'))
    pyproject = '''[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
[project]
name = "sample-adaptation-host"
version = "1.0.0"
requires-python = ">=3.10"
[project.scripts]
sample-adaptation = "sample_pkg.console:main"
[tool.setuptools.packages.find]
include = ["sample_pkg*"]
'''
    if layout == 'src':
        pyproject = pyproject.replace('include = ["sample_pkg*"]',
                                      'where = ["src"]\ninclude = ["sample_pkg*"]')
    (target / 'pyproject.toml').write_text(pyproject, encoding='utf-8')
    console = '''import asyncio
from concurrent.futures import wait
import json
import os
from pathlib import Path
from jev_integration_evaluator.integrations.probe import SyntheticClient, SyntheticAudit
from jev_integration_evaluator.runtime import HostGate
from . import adapter, host

def registry(request):
    return {'base': host.Worker().baseline} if hasattr(host, 'Worker') else {'base': host.baseline}
def baseline_action(request): return 'base'
def evidence(request): return {'task_id': request['task_id']}
def gate(request, action): return HostGate(('base',))
def validate(request, action): return action == 'base'
def blocked(request, reason): raise RuntimeError(reason)
def guard(request):
    from contextlib import nullcontext
    return nullcontext()

def main():
    receipt = json.loads(Path(os.environ['ADAPTATION_REVIEW_RECEIPT']).read_text())
    plan = json.loads(Path(os.environ['ADAPTATION_ADAPTER_PLAN']).read_text())
    audit = SyntheticAudit()
    mode = os.environ.get('ADAPTATION_MODE', 'off')
    client = SyntheticClient('primary') if mode == 'shadow' else None
    runtime = adapter.startup(budget_limits=dict(max_calls_per_task=3, max_cost_per_task=3,
        max_total_calls=3, max_total_cost=3, max_in_flight=2, max_tasks=3),
        audit_log=audit, policy_bindings=dict(registry=registry, baseline_action=baseline_action,
            evidence=evidence, gate=gate, validate=validate, blocked=blocked, guard=guard),
        adapter_plan=plan, review_receipt=receipt,
        verify_review=lambda kind, value: kind == 'adaptation_runtime_review'
            and value == os.environ['ADAPTATION_REVIEW_DIGEST'],
        client=client, startup_mode=mode)
    async def run_async(task_id):
        return await host.run({'task_id': task_id})
    try:
        if os.environ.get('ADAPTATION_MUTATE_HOST') == '1':
            path = Path(host.__file__)
            path.write_bytes(path.read_bytes() + b'\\n# post-start drift\\n')
        if hasattr(host, 'Worker'):
            value = host.Worker().run({'task_id': 'one'})
        else:
            value = asyncio.run(run_async())
        wait(tuple(router.futures))
        adapter.complete_task('one')
        adapter.complete_task('two')
        print(json.dumps({'value': value, 'events': host.events,
            'calls': client.calls if client is not None else 0,
            'assessments': [event['task_id_hash'] for event in audit.events
                if event.get('type') == 'assessment'],
            'audit_types': [event.get('type') for event in audit.events],
            'budget': runtime.coordinator.snapshot(),
            'mode': runtime.mode_status()['effective_mode'],
            'closed_tasks': runtime.coordinator.snapshot()['closed_tasks']}))
        return 0
    finally:
        adapter.shutdown()
'''
    if shape.startswith('instance'):
        console = console.replace(
            "return {'base': host.Worker().baseline} if hasattr(host, 'Worker') else {'base': host.baseline}",
            "return {'base': host.Worker().baseline}")
        console = console.replace(
            "    async def run_async(task_id):\n        return await host.run({'task_id': task_id})\n", '')
        console = console.replace(
            "        if hasattr(host, 'Worker'):\n            value = host.Worker().run({'task_id': 'one'})\n        else:\n            value = asyncio.run(run_async())",
            "        router = runtime.router(adapter.SPEC['candidate_id'], {'task_id': 'one'})\n"
            "        host.Worker().run({'task_id': 'one'})\n"
            "        assert runtime.router(adapter.SPEC['candidate_id'], {'task_id': 'two'}) is router\n"
            "        value = host.Worker().run({'task_id': 'two'})")
    elif shape.startswith('module-fixed'):
        console = console.replace(
            "return {'base': host.Worker().baseline} if hasattr(host, 'Worker') else {'base': host.baseline}",
            "return {'base': lambda request: host.baseline(request, 1, 2)}")
        console = console.replace(
            "    async def run_async(task_id):\n        return await host.run({'task_id': task_id})\n", '')
        console = console.replace(
            "        if hasattr(host, 'Worker'):\n            value = host.Worker().run({'task_id': 'one'})\n        else:\n            value = asyncio.run(run_async())",
            "        router = runtime.router(adapter.SPEC['candidate_id'], {'task_id': 'one'})\n"
            "        host.run({'task_id': 'one'}, 1, 2)\n"
            "        assert runtime.router(adapter.SPEC['candidate_id'], {'task_id': 'two'}) is router\n"
            "        value = host.run({'task_id': 'two'}, 1, 2)")
    else:
        console = console.replace(
            "return {'base': host.Worker().baseline} if hasattr(host, 'Worker') else {'base': host.baseline}",
            "return {'base': host.baseline}")
        console = console.replace(
            "        if hasattr(host, 'Worker'):\n            value = host.Worker().run({'task_id': 'one'})\n        else:\n            value = asyncio.run(run_async())",
            "        router = runtime.router(adapter.SPEC['candidate_id'], {'task_id': 'one'})\n"
            "        asyncio.run(run_async('one'))\n"
            "        assert runtime.router(adapter.SPEC['candidate_id'], {'task_id': 'two'}) is router\n"
            "        value = asyncio.run(run_async('two'))")
    (package / 'console.py').write_text(console, encoding='utf-8')
    _, full_spec = fixture(tmp_path / 'source_spec', 'C', tag=shape.replace('-', '_'))
    runtime_spec = {key: full_spec[key] for key in ('candidate_id', 'experiment_id', 'source', 'recipe',
        'questions', 'primary_question', 'evidence_question', 'label_actions', 'runtime', 'policy')}
    source_file = 'src/sample_pkg/host.py' if layout == 'src' else 'sample_pkg/host.py'
    runtime_spec['source'] = dict(runtime_spec['source'], file=source_file,
                                  symbol=symbol, file_sha256=edit['new_sha256'])
    runtime_spec['registered_action_ids'] = ['base']
    scope = inspect_runtime_package(target, source_file=source_file,
                                    adapted_source=edit['new_content'], symbol=symbol,
                                    shape=shape, script='sample-adaptation')
    files = scope['source_files']
    assert len(scope['calls']) == (1 if shape.startswith('async') else 2)
    adapter_source = render_adapter(spec=runtime_spec, shape=shape, source_files=files,
        pyproject_sha256=scope['pyproject_sha256'], script=scope['script'],
        script_target=scope['script_target'], distribution=scope['distribution'],
        caller_scope_sha256=digest(scope),
        positional_count=3 if shape.startswith('module-fixed') else 1,
        source_root_depth=2 if layout == 'src' else 1)
    (package / 'adapter.py').write_bytes(adapter_source.encode('utf-8'))
    adapter_sha256 = _sha(adapter_source.encode())
    root_stat = target.stat()
    plan_body = {'kind': 'generated-adaptation-adapter-plan-v1',
                 'schema_version': '1.0',
                 'root_identity': {'path_sha256': digest(str(target.resolve())),
                                   'device': root_stat.st_dev, 'inode': root_stat.st_ino},
                 'engine_identity': engine_identity(),
                 'request_sha256': digest({'fixture': shape, 'layout': layout}),
                 'spec_sha256': digest(runtime_spec),
                 'inventory_sha256': digest(files),
                 'caller_scope_sha256': digest(scope),
                 'patch_sha256': digest({'adapter_sha256': adapter_sha256}),
                 'owned_file': {'file': (Path(source_file).parent / 'adapter.py').as_posix(),
                                'old_sha256': '0' * 64, 'new_sha256': adapter_sha256,
                                'old_mode': 0o644, 'new_mode': 0o644},
                 'source_file': source_file,
                 'source_before_sha256': _sha(source.encode('utf-8')),
                 'source_after_sha256': edit['new_sha256'],
                 'adaptation_verification_sha256': 'd' * 64,
                 'stage': 'final'}
    plan = dict(plan_body, contract_digest=digest(plan_body))
    (tmp_path / 'adapter-plan.json').write_text(json.dumps(plan), encoding='utf-8')
    receipt = {'adapter_sha256': adapter_sha256,
               'adapter_plan_sha256': plan['contract_digest'],
               'adaptation_verification_sha256': plan['adaptation_verification_sha256'],
               'adapted_source_sha256': edit['new_sha256'],
               'adapted_symbol_sha256': runtime_spec['source']['source_sha256'],
               'caller_scope_sha256': digest(scope),
               'pyproject_sha256': scope['pyproject_sha256'],
               'script_target': scope['script_target'],
               'reviewer': 'independent-test-review',
               'approved': True}
    receipt_path = tmp_path / 'review.json'
    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    return target, digest(receipt)


@pytest.mark.parametrize('shape', ['instance-method-tail-call-v1', 'async-module-tail-call-v1',
                                   'module-fixed-positional-tail-call-v1'])
@pytest.mark.parametrize('mode', ['off', 'shadow'])
def test_generated_adapter_normal_package_entrypoint(tmp_path, shape, mode):
    target, review_digest = _host(tmp_path, shape)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(target), str(Path(__file__).resolve().parents[1]))),
               ADAPTATION_ADAPTER_PLAN=str(tmp_path / 'adapter-plan.json'),
               ADAPTATION_REVIEW_RECEIPT=str(tmp_path / 'review.json'),
               ADAPTATION_REVIEW_DIGEST=review_digest, ADAPTATION_MODE=mode)
    run = subprocess.run([sys.executable, '-c',
        'from sample_pkg.console import main; raise SystemExit(main())'],
        env=env, text=True, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report['value'] == (2 if shape.startswith('instance') else
                               3 if shape.startswith('module-fixed') else 4)
    assert report['closed_tasks'] == 2
    assert report['calls'] == (2 if mode == 'shadow' else 0), json.dumps(report, sort_keys=True)


@pytest.mark.parametrize('field', ['adapter_plan_sha256', 'adaptation_verification_sha256'])
def test_runtime_receipt_rejects_stale_plan_or_verification_chain(tmp_path, field):
    target, _ = _host(tmp_path, 'instance-method-tail-call-v1')
    receipt = json.loads((tmp_path / 'review.json').read_text(encoding='utf-8'))
    receipt[field] = 'f' * 64
    stale = tmp_path / 'stale-review.json'
    stale.write_text(json.dumps(receipt), encoding='utf-8')
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join((str(target), str(Path(__file__).resolve().parents[1]))),
               ADAPTATION_ADAPTER_PLAN=str(tmp_path / 'adapter-plan.json'),
               ADAPTATION_REVIEW_RECEIPT=str(stale),
               ADAPTATION_REVIEW_DIGEST=digest(receipt), ADAPTATION_MODE='off')
    run = subprocess.run([sys.executable, '-c',
        'from sample_pkg.console import main; raise SystemExit(main())'],
        env=env, text=True, capture_output=True, timeout=30)
    assert run.returncode != 0
    assert 'authenticated_post_adaptation_review_required' in run.stderr
    assert run.stdout == ''


def test_runtime_rejects_mutated_final_plan_before_host_effect(tmp_path):
    target, review_digest = _host(tmp_path, 'instance-method-tail-call-v1')
    plan = json.loads((tmp_path / 'adapter-plan.json').read_text(encoding='utf-8'))
    plan['owned_file']['new_sha256'] = 'f' * 64
    changed = tmp_path / 'changed-plan.json'
    changed.write_text(json.dumps(plan), encoding='utf-8')
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join((str(target), str(Path(__file__).resolve().parents[1]))),
               ADAPTATION_ADAPTER_PLAN=str(changed),
               ADAPTATION_REVIEW_RECEIPT=str(tmp_path / 'review.json'),
               ADAPTATION_REVIEW_DIGEST=review_digest, ADAPTATION_MODE='off')
    run = subprocess.run([sys.executable, '-c',
        'from sample_pkg.console import main; raise SystemExit(main())'],
        env=env, text=True, capture_output=True, timeout=30)
    assert run.returncode != 0
    assert 'final_adaptation_adapter_plan_mismatch' in run.stderr
    assert run.stdout == ''


def test_runtime_rejects_post_start_source_drift_before_effect(tmp_path):
    target, review_digest = _host(tmp_path, 'instance-method-tail-call-v1')
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(target), str(Path(__file__).resolve().parents[1]))),
               ADAPTATION_ADAPTER_PLAN=str(tmp_path / 'adapter-plan.json'),
               ADAPTATION_REVIEW_RECEIPT=str(tmp_path / 'review.json'),
               ADAPTATION_REVIEW_DIGEST=review_digest, ADAPTATION_MUTATE_HOST='1')
    run = subprocess.run([sys.executable, '-c',
        'from sample_pkg.console import main; raise SystemExit(main())'],
        env=env, text=True, capture_output=True, timeout=30)
    assert run.returncode != 0
    assert 'runtime_source_or_configuration_drift' in run.stderr
    assert run.stdout == ''


def test_package_caller_audit_rejects_dynamic_and_unknown_calls(tmp_path):
    target, _ = _host(tmp_path, 'instance-method-tail-call-v1')
    host = target / 'sample_pkg' / 'host.py'
    console = target / 'sample_pkg' / 'console.py'
    original = console.read_bytes()
    for suffix in (b'\ngetattr(host.Worker(), "run")\n',
                   b'\nhasattr(host.Worker(), "run")\n',
                   b'\nhost.Worker().run\n',
                   b'\nworker = host.Worker()\nworker.run({"task_id":"extra"})\n',
                   b'\nimport importlib\nimportlib.import_module("sample_pkg.host")\n',
                   b'\nfrom sample_pkg.host import Worker\nWorker().run({"task_id":"extra"})\n',
                   b'\nfrom sample_pkg.host import *\n'):
        console.write_bytes(original + suffix)
        with pytest.raises(UnsupportedShape):
            inspect_runtime_package(target, source_file='sample_pkg/host.py',
                adapted_source=host.read_text(encoding='utf-8'), symbol='Worker.run',
                shape='instance-method-tail-call-v1', script='sample-adaptation')
    console.write_bytes(original)


def test_async_caller_audit_rejects_unawaited_coroutine(tmp_path):
    target, _ = _host(tmp_path, 'async-module-tail-call-v1')
    host = target / 'sample_pkg' / 'host.py'
    console = target / 'sample_pkg' / 'console.py'
    console.write_bytes(console.read_bytes() + b'\nhost.run({"task_id": "unawaited"})\n')
    with pytest.raises(UnsupportedShape, match='directly await'):
        inspect_runtime_package(target, source_file='sample_pkg/host.py',
            adapted_source=host.read_text(encoding='utf-8'), symbol='run',
            shape='async-module-tail-call-v1', script='sample-adaptation')


def test_generated_adapter_bootstrap_owns_only_its_exact_bytes(tmp_path):
    target, _ = _host(tmp_path, 'instance-method-tail-call-v1')
    adapter_path = target / 'sample_pkg' / 'adapter.py'
    adapter_text = adapter_path.read_text(encoding='utf-8')
    spec_assignment = next(node for node in ast.parse(adapter_text).body
                           if isinstance(node, ast.Assign) and any(
                               isinstance(name, ast.Name) and name.id == 'SPEC'
                               for name in node.targets))
    spec = ast.literal_eval(spec_assignment.value)
    adapter_path.unlink()
    source_path = target / 'sample_pkg' / 'host.py'
    source_path.write_bytes(METHOD.encode('utf-8'))
    edit = _edit(METHOD, 'instance-method-tail-call-v1', 'Worker.run')
    selected = next(node for node in ast.parse(METHOD).body if isinstance(node, ast.ClassDef))
    statement = next(node for node in selected.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'run').body[-1]
    pre_sha = _sha(METHOD.encode())
    source_id = {'file': 'sample_pkg/host.py', 'symbol': 'Worker.run',
                 'file_sha256': pre_sha, 'source_sha256': 'a' * 64}
    inventory = {'files': [{'file': path.relative_to(target).as_posix(),
                            'sha256': _sha(path.read_bytes())}
                           for path in sorted(target.rglob('*')) if path.is_file()],
                 'configuration_evidence': [],
                 'candidates': [{'candidate_id': spec['candidate_id'], 'source': source_id,
                                 'semantic_review': {'approved': True, 'source_sha256': 'a' * 64,
                                                     'reviewer': 'independent-test-review',
                                                     'reason': 'reviewed synthetic seam'}}]}
    scope = inspect_runtime_package(target, source_file='sample_pkg/host.py',
                                    adapted_source=edit['new_content'], symbol='Worker.run',
                                    shape='instance-method-tail-call-v1', script='sample-adaptation')
    caller_review = {'reviewer': 'independent-test-review', 'reason': 'closed fixture package',
                     'closed_scope': True, 'external_callers': False,
                     'caller_scope_sha256': digest(scope)}
    request = {'kind': 'generated-adaptation-adapter-v1', 'stage': 'bootstrap',
               'candidate_id': spec['candidate_id'], 'shape': 'instance-method-tail-call-v1',
               'source_file': 'sample_pkg/host.py', 'symbol': 'Worker.run',
               'source_before_sha256': pre_sha, 'source_after_sha256': edit['new_sha256'],
               'anchor_sha256': digest(ast.dump(statement, annotate_fields=True,
                                                include_attributes=False)),
               'adapter_name': 'adapter', 'script': 'sample-adaptation',
               'request_position': 0, 'positional_count': 1,
               'adaptation_verification_sha256': None,
               'reviewed_inventory_sha256': digest(inventory),
               'external_caller_review_sha256': digest(caller_review)}
    bundle = tmp_path / 'bootstrap_plan'
    plan = plan_generated_adapter(target, request, spec, inventory, caller_review, bundle)
    assert not adapter_path.exists()
    source_path.write_bytes(edit['new_content'].encode('utf-8'))
    with pytest.raises(Exception, match='Bootstrap must be applied before source adaptation'):
        apply_generated_adapter(target, bundle, plan['contract_digest'],
            verify_review=lambda kind, value: kind == 'adaptation_caller_review'
            and value == digest(caller_review))
    assert not adapter_path.exists()
    source_path.write_bytes(METHOD.encode('utf-8'))
    applied = apply_generated_adapter(target, bundle, plan['contract_digest'],
                                      verify_review=lambda kind, value: kind == 'adaptation_caller_review'
                                      and value == digest(caller_review))
    assert applied['status'] == 'applied_unverified'
    assert _sha(adapter_path.read_bytes()) == plan['adapter_sha256']
    adapter_path.write_bytes(b'drift\n')
    with pytest.raises(Exception, match='drift'):
        rollback_generated_adapter(target, bundle, plan['rollback_digest'])
    adapter_path.write_bytes((json.loads((bundle / 'patch-plan.json').read_text())['changes'][0]
                              ['new_content']).encode('utf-8'))
    source_path.write_bytes(edit['new_content'].encode('utf-8'))
    with pytest.raises(Exception, match='Rollback adapted source'):
        rollback_generated_adapter(target, bundle, plan['rollback_digest'])
    final_spec = copy.deepcopy(spec)
    final_spec['source']['source_sha256'] = 'c' * 64
    fresh_inventory = copy.deepcopy(inventory)
    for row in fresh_inventory['files']:
        if row['file'] == 'sample_pkg/host.py':
            row['sha256'] = edit['new_sha256']
    fresh_inventory['files'].append({'file': 'sample_pkg/adapter.py',
                                     'sha256': plan['adapter_sha256']})
    fresh_inventory['candidates'][0]['source']['file_sha256'] = edit['new_sha256']
    fresh_inventory['candidates'][0]['source']['source_sha256'] = 'c' * 64
    fresh_inventory['candidates'][0]['semantic_review']['source_sha256'] = 'c' * 64
    final_request = dict(request, stage='final',
                         reviewed_inventory_sha256=digest(fresh_inventory),
                         adaptation_verification_sha256='d' * 64)
    with pytest.raises(Exception, match='anchored verified adaptation'):
        plan_generated_adapter(target, final_request, final_spec, fresh_inventory,
                               caller_review, tmp_path / 'rejected_final')
    final_bundle = tmp_path / 'final_plan'
    final = plan_generated_adapter(target, final_request, final_spec, fresh_inventory,
        caller_review, final_bundle,
        verify_adaptation=lambda kind, value: kind == 'verified_adaptation' and value == 'd' * 64)
    apply_generated_adapter(target, final_bundle, final['contract_digest'],
        verify_review=lambda kind, value: kind == 'adaptation_caller_review'
        and value == digest(caller_review))
    assert generated_adapter_status(target, final_bundle)['status'] == 'applied_unverified'
    assert _sha(adapter_path.read_bytes()) == final['adapter_sha256']
    assert rollback_generated_adapter(target, final_bundle, final['rollback_digest'])['status'] == 'rolled_back'
    assert _sha(adapter_path.read_bytes()) == plan['adapter_sha256']
    source_path.write_bytes(METHOD.encode('utf-8'))
    assert rollback_generated_adapter(target, bundle, plan['rollback_digest'])['status'] == 'rolled_back'
    assert not adapter_path.exists()


@pytest.mark.parametrize('shape', ['instance-method-tail-call-v1', 'async-module-tail-call-v1',
                                   'module-fixed-positional-tail-call-v1'])
@pytest.mark.parametrize('layout', ['package', 'src'])
def test_generated_runtime_in_independent_installed_console(tmp_path, shape, layout):
    target, review_digest = _host(tmp_path, shape, layout)
    distribution_dir = tmp_path / 'dist'
    distribution_dir.mkdir()
    evaluator = Path(__file__).resolve().parents[1]
    for source in (target, evaluator):
        build = subprocess.run([sys.executable, '-c',
            'import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))',
            str(distribution_dir)], cwd=source, capture_output=True, text=True, timeout=90)
        assert build.returncode == 0, build.stderr
    environment = tmp_path / 'venv'
    venv.EnvBuilder(with_pip=False, system_site_packages=True).create(environment)
    binary = 'Scripts' if os.name == 'nt' else 'bin'
    python = environment / binary / ('python.exe' if os.name == 'nt' else 'python')
    wheels = sorted(distribution_dir.glob('*.whl'))
    assert len(wheels) == 2
    if importlib.util.find_spec('pip'):
        installer = [sys.executable, '-m', 'pip', '--python', str(python), 'install']
    else:
        uv = shutil.which('uv')
        assert uv is not None, 'independent wheel check requires pip or uv'
        installer = [uv, 'pip', 'install', '--python', str(python)]
    install = subprocess.run([*installer, '--no-index', '--no-deps',
                              *(str(wheel) for wheel in wheels)],
                             capture_output=True, text=True, timeout=90)
    assert install.returncode == 0, install.stderr
    script = environment / binary / ('sample-adaptation' + ('.exe' if os.name == 'nt' else ''))
    for mode in ('off', 'shadow'):
        env = dict(os.environ, ADAPTATION_ADAPTER_PLAN=str(tmp_path / 'adapter-plan.json'),
                   ADAPTATION_REVIEW_RECEIPT=str(tmp_path / 'review.json'),
                   ADAPTATION_REVIEW_DIGEST=review_digest, ADAPTATION_MODE=mode)
        env.pop('PYTHONPATH', None)
        run = subprocess.run([str(script)], cwd=tmp_path, env=env,
                             capture_output=True, text=True, timeout=30)
        assert run.returncode == 0, run.stderr
        observed = json.loads(run.stdout)
        assert observed['events'] == ([['effect', 'one'], ['effect', 'two']]
                                      if shape.startswith('instance') else
                                      [['one', 1, 2], ['two', 1, 2]]
                                      if shape.startswith('module-fixed') else
                                      [['start', 'one'], ['finish', 'one'],
                                       ['start', 'two'], ['finish', 'two']])
        assert observed['calls'] == (2 if mode == 'shadow' else 0)
        assert observed['closed_tasks'] == 2
