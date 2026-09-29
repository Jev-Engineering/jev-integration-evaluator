"""Independent synthetic behavior checks for structural adaptation proposals."""
import ast
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jev_integration_evaluator.integrations.adaptation_shapes import (
    REVIEWED_REQUEST_SCHEMA, prepare_shape, prepare_reviewed_shape)
from jev_integration_evaluator.integrations.errors import UnsupportedShape
from jev_integration_evaluator.io import InputError, digest


def prepared(source, shape, symbol):
    raw = source.encode()
    tree = ast.parse(source)
    if '.' in symbol:
        owner, name = symbol.split('.')
        statement = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner)
        statement = next(n for n in statement.body if isinstance(n, ast.FunctionDef) and n.name == name).body[-1]
    else:
        statement = next(n for n in tree.body if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
                         and n.name == symbol).body[-1]
    return prepare_shape(raw, shape=shape, symbol=symbol, source_sha256=hashlib.sha256(raw).hexdigest(),
                         anchor_sha256=digest(ast.dump(statement, annotate_fields=True, include_attributes=False)),
                         adapter_name='adapter')


def test_review_request_schema_matches_code_and_packaged_mirror():
    root = Path(__file__).resolve().parents[1]
    packaged = json.loads((root / 'jev_integration_evaluator/data/adaptation-request-v1.schema.json').read_text())
    mirror = json.loads((root / 'schemas/adaptation-request-v1.schema.json').read_text())
    assert packaged == mirror == REVIEWED_REQUEST_SCHEMA


METHOD = '''
class Worker:
    def __init__(self, log):
        self.log = log
        self.state = 0

    def baseline(self, request):
        self.log.append(('effect', self.state, request))
        self.state += 1
        if request == 'error':
            raise LookupError('host error')
        return self.state

    def run(self, request):
        return self.baseline(request)
'''


def test_instance_method_receiver_effect_order_and_exception_identity():
    # The constructor and baseline are outside the selected method. The method
    # remains a normal descriptor and receives its exact original receiver.
    result = prepared(METHOD, 'instance-method-tail-call-v1', 'Worker.run')
    original = {}; modified = {}
    exec(METHOD, original)
    calls = []
    def invoke(baseline, request):
        calls.append(('adapter', baseline.__self__.state, request))
        return baseline(request)
    modified['adapter'] = SimpleNamespace(invoke=invoke)
    exec(result['new_content'], modified)
    for namespace in (original, modified):
        log = []
        worker = namespace['Worker'](log)
        assert worker.run('one') == 1
        with pytest.raises(LookupError) as exc:
            worker.run('error')
        assert str(exc.value) == 'host error'
        assert worker.state == 2
        assert log == [('effect', 0, 'one'), ('effect', 1, 'error')]
    assert calls == [('adapter', 0, 'one'), ('adapter', 1, 'error')]


ASYNC = '''
events = []
async def baseline(request):
    events.append(('start', request))
    await asyncio.sleep(0)
    if request == 'error':
        raise LookupError('async host error')
    events.append(('finish', request))
    return request

async def run(request):
    return await baseline(request)
'''


def test_async_tail_call_awaits_once_and_propagates_exception_and_cancellation():
    result = prepared(ASYNC, 'async-module-tail-call-v1', 'run')
    async def invoke_async(baseline, request):
        return await baseline(request)
    for source in (ASYNC, result['new_content']):
        namespace = {'asyncio': asyncio, 'adapter': SimpleNamespace(invoke_async=invoke_async)}
        exec(source, namespace)
        async def exercise():
            assert await namespace['run']('ok') == 'ok'
            with pytest.raises(LookupError, match='async host error'):
                await namespace['run']('error')
            task = asyncio.create_task(namespace['run']('cancel'))
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        asyncio.run(exercise())
        assert namespace['events'].count(('start', 'ok')) == 1
        assert namespace['events'].count(('finish', 'ok')) == 1
        assert namespace['events'].count(('start', 'error')) == 1
        assert namespace['events'].count(('start', 'cancel')) == 1
        assert ('finish', 'cancel') not in namespace['events']


@pytest.mark.parametrize('changed', [
    METHOD.replace('return self.baseline(request)', 'return self.baseline(request) if request else 0'),
    METHOD.replace('return self.baseline(request)', 'return self.baseline(request) + 1'),
    METHOD.replace('return self.baseline(request)', 'return self.baseline(request, 1)'),
    METHOD.replace('return self.baseline(request)', 'return self.baseline(self.state)'),
    METHOD.replace('def run(self, request):', '@property\n    def run(self, request):'),
    METHOD.replace('class Worker:', 'class Worker(object):'),
    METHOD.replace('return self.baseline(request)', 'return self.run(request)'),
])
def test_method_unsupported_shapes_fail_closed(changed):
    with pytest.raises(UnsupportedShape):
        prepared(changed, 'instance-method-tail-call-v1', 'Worker.run')


@pytest.mark.parametrize('changed', [
    ASYNC.replace('return await baseline(request)', 'return baseline(request)'),
    ASYNC.replace('return await baseline(request)', 'return await baseline(request, extra=1)'),
    ASYNC.replace('return await baseline(request)', 'return await baseline(request) if request else 0'),
    ASYNC.replace('async def run(request):', '@staticmethod\nasync def run(request):'),
])
def test_async_unsupported_shapes_fail_closed(changed):
    with pytest.raises(UnsupportedShape):
        prepared(changed, 'async-module-tail-call-v1', 'run')


def test_source_and_anchor_drift_rejected():
    raw = METHOD.encode()
    with pytest.raises(InputError, match='reviewed bytes'):
        prepare_shape(raw + b'\n', shape='instance-method-tail-call-v1', symbol='Worker.run',
                      source_sha256=hashlib.sha256(raw).hexdigest(), anchor_sha256='0'*64,
                      adapter_name='adapter')
    with pytest.raises(InputError, match='reviewed anchor'):
        prepare_shape(raw, shape='instance-method-tail-call-v1', symbol='Worker.run',
                      source_sha256=hashlib.sha256(raw).hexdigest(), anchor_sha256='0'*64,
                      adapter_name='adapter')


def test_reviewed_preparation_rechecks_complete_snapshot_and_review(tmp_path):
    source = 'import adapter\n' + METHOD
    path = tmp_path / 'worker.py'
    path.write_bytes(source.encode())
    adapter_path = tmp_path / 'adapter.py'
    adapter_path.write_bytes(b'def invoke(original, request):\n    return original(request)\n')
    adapter_sha = hashlib.sha256(adapter_path.read_bytes()).hexdigest()
    file_sha = hashlib.sha256(source.encode()).hexdigest()
    statement = ast.parse(source).body[1].body[-1].body[-1]
    anchor = digest(ast.dump(statement, annotate_fields=True, include_attributes=False))
    analysis = {'synthetic': True}
    source_record = {'file': 'worker.py', 'symbol': 'Worker.run', 'source_sha256': 'a'*64,
                     'file_sha256': file_sha, 'anchor_sha256': anchor}
    inventory = {'analysis_identity': analysis, 'scan_fingerprint': digest(analysis),
                 'files': [{'file': 'worker.py', 'sha256': file_sha},
                           {'file': 'adapter.py', 'sha256': adapter_sha}], 'configuration_evidence': [],
                 'candidates': [{'candidate_id': 'synthetic-c', 'source': {k: source_record[k] for k in
                                ('file', 'symbol', 'source_sha256', 'file_sha256')}, 'tier': 1,
                                'pattern': 'C', 'semantic_review': {'approved': True, 'reviewer': 'test',
                                'reason': 'synthetic source review', 'source_sha256': 'a'*64}}]}
    request = {'strategy': {'shape': 'instance-method-tail-call-v1', 'version': '1.0'},
               'candidate_id': 'synthetic-c', 'inventory_sha256': digest(inventory),
               'inventory_fingerprint': digest(analysis), 'source': source_record,
               'binding_review': {'reviewer': 'test', 'reason': 'synthetic binding review',
                                  'source_sha256': 'a'*64, 'adapter_file': 'adapter.py',
                                  'adapter_sha256': adapter_sha},
               'adapter_name': 'adapter'}
    result = prepare_reviewed_shape(tmp_path, inventory, request)
    assert result['candidate_id'] == 'synthetic-c'
    assert result['new_sha256'] != file_sha
    assert path.read_bytes() == source.encode()
    adapter_path.write_bytes(b'changed\n')
    with pytest.raises(InputError, match='snapshot'):
        prepare_reviewed_shape(tmp_path, inventory, request)
    adapter_path.write_bytes(b'def invoke(original, request):\n    return original(request)\n')
    path.write_bytes((source + '\n').encode())
    with pytest.raises(InputError, match='snapshot'):
        prepare_reviewed_shape(tmp_path, inventory, request)
    path.write_bytes(source.encode())
    inventory['candidates'][0]['semantic_review']['approved'] = False
    request['inventory_sha256'] = digest(inventory)
    with pytest.raises(InputError, match='review'):
        prepare_reviewed_shape(tmp_path, inventory, request)
    inventory['candidates'][0]['semantic_review']['approved'] = True
    adapter_path.write_bytes(b'def unrelated(original, request):\n    return original(request)\n')
    changed_adapter_sha = hashlib.sha256(adapter_path.read_bytes()).hexdigest()
    inventory['files'][1]['sha256'] = changed_adapter_sha
    request['binding_review']['adapter_sha256'] = changed_adapter_sha
    request['inventory_sha256'] = digest(inventory)
    with pytest.raises(UnsupportedShape, match='callback'):
        prepare_reviewed_shape(tmp_path, inventory, request)
