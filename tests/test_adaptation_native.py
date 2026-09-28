"""Privileged ephemeral Linux qualification of actual edited method/async hosts."""
from __future__ import annotations

import ast
import copy
import hashlib
import os
import sys

import pytest

from jev_integration_evaluator.integrations import adaptation_lifecycle as life
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.runners import isolated_python as runner

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                                reason='requires disposable privileged Linux runner')

ADAPTER = '''MODE = 'off'
calls = 0
def invoke(original, request):
    global calls
    if MODE == 'shadow': calls += 1
    return original(request)
async def invoke_async(original, request):
    global calls
    if MODE == 'shadow': calls += 1
    return await original(request)
'''
METHOD = '''import adapter
effects = []
class Worker:
    def baseline(self, request):
        effects.append('once')
        return 'ok'
    def run(self, request):
        return self.baseline(request)
'''
ASYNC = '''import adapter
import asyncio
effects = []
async def baseline(request):
    await asyncio.sleep(0)
    if request.get('scenario') == 'error':
        raise LookupError('host error')
    if request.get('scenario') == 'cancel':
        await asyncio.sleep(60)
    effects.append('once')
    return 'ok'
async def run(request):
    return await baseline(request)
'''
ENTRY = '''import adapter, host, json, sys, asyncio
adapter.MODE = sys.argv[1]
if sys.argv[2] == 'async':
    if sys.argv[1] == 'exception':
        try:
            asyncio.run(host.run({'task_id': 'one', 'scenario': 'error'}))
            raise AssertionError('expected host exception')
        except LookupError as error:
            result = type(error).__name__
    elif sys.argv[1] == 'cancel':
        async def cancellation():
            task = asyncio.create_task(host.run({'task_id': 'one', 'scenario': 'cancel'}))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            task.cancel()
            try:
                await task
                raise AssertionError('expected cancellation')
            except asyncio.CancelledError:
                return 'CancelledError'
        result = asyncio.run(cancellation())
    else:
        result = asyncio.run(host.run({'task_id': 'one'}))
else:
    result = host.Worker().run({'task_id': 'one'})
print(json.dumps({'reached': True, 'result': result, 'effects': host.effects,
    'state': {'count': len(host.effects)}, 'assessments': adapter.calls,
    'dependency_origin': 'none'}, sort_keys=True))
'''


def _hash(raw): return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('shape', ['instance-method-tail-call-v1', 'async-module-tail-call-v1'])
def test_native_edited_host_reachability_parity_and_anchored_lifecycle(tmp_path, shape):
    is_async = shape.startswith('async')
    source = ASYNC if is_async else METHOD
    symbol = 'run' if is_async else 'Worker.run'
    root, bundle = tmp_path / 'host', tmp_path / 'private'
    root.mkdir()
    for name, content in [('host.py', source), ('adapter.py', ADAPTER), ('entry.py', ENTRY)]:
        (root / name).write_bytes(content.encode())
        os.chmod(root / name, 0o644)
    tree = ast.parse(source)
    function = tree.body[-1] if is_async else tree.body[-1].body[-1]
    source_sha, adapter_sha = _hash(source.encode()), _hash(ADAPTER.encode())
    source_record = {'file':'host.py', 'symbol':symbol, 'source_sha256':'a'*64,
                     'file_sha256':source_sha,
                     'anchor_sha256':digest(ast.dump(function.body[-1], annotate_fields=True,
                                                     include_attributes=False))}
    analysis = {'synthetic': True, 'shape': shape}
    inventory = {'analysis_identity': analysis, 'scan_fingerprint': digest(analysis),
                 'files':[{'file':name, 'sha256':_hash(content.encode())}
                          for name,content in [('host.py',source),('adapter.py',ADAPTER),('entry.py',ENTRY)]],
                 'configuration_evidence': [],
                 'candidates':[{'candidate_id':'synthetic', 'tier':1, 'pattern':'C',
                                'source':{k:source_record[k] for k in
                                          ('file','symbol','source_sha256','file_sha256')},
                                'semantic_review':{'approved':True,'reviewer':'synthetic-test',
                                    'reason':'synthetic source review','source_sha256':'a'*64}}]}
    request = {'strategy':{'shape':shape,'version':'1.0'}, 'candidate_id':'synthetic',
               'inventory_sha256':digest(inventory), 'inventory_fingerprint':digest(analysis),
               'source':source_record, 'adapter_name':'adapter',
               'binding_review':{'reviewer':'synthetic-test', 'reason':'synthetic adapter review',
                                 'source_sha256':'a'*64,'adapter_file':'adapter.py',
                                 'adapter_sha256':adapter_sha}}
    plan = life.plan_adaptation(root, inventory, request, bundle)
    files = ['host.py','adapter.py','entry.py']
    kind = 'async' if is_async else 'method'
    baseline = runner.prepare_spec(root, files,
        [{'case_id':'baseline','entry':'entry.py','argv':['baseline',kind]}])
    modified = copy.deepcopy(baseline)
    for row in modified['files']:
        if row['path']=='host.py':
            row.update(sha256=plan['new_sha256'], bytes=len(
                __import__('json').loads((bundle/'patch-plan.json').read_text())['changes'][0]['new_content'].encode()))
    modified['schedule'] = [{'case_id':mode,'entry':'entry.py','argv':[mode,kind]}
                            for mode in ('off','shadow')]
    expected = {'reached':True,'result':'ok','effects':['once'],
                'state':{'count':1},'assessments':0,'dependency_origin':'none'}
    oracle = {'schema_version':'1.0','kind':'native-postconditions-v1',
              'repository_identity':digest(str(root.resolve())),
              'context_sha256':digest({'inventory_sha256':digest(inventory),
                                       'request_sha256':digest(request)}),
              'bundle_digest':plan['contract_digest'],'adapter':'json-state-v1'}
    for phase,spec in [('baseline',baseline),('modified',modified)]:
        oracle[phase] = {'request_sha256':runner.request_digest(spec),
                         'source_manifest_sha256':digest(spec['files']), 'attempt':1,
                         'cases':[{'case_id':case['case_id'],
                                   'entry_sha256':next(row['sha256'] for row in spec['files'] if row['path']=='entry.py'),
                                   'observation':{**expected,'assessments':1 if case['case_id']=='shadow' else 0}}
                                  for case in spec['schedule']]}
    oracle_sha = _hash(runner.canonical(oracle))
    grant = lambda spec: runner.ExecutionGrant(runner.request_digest(spec), 'synthetic-adaptation-test')
    original = runner.run_schedule(root, baseline, grant(baseline))
    assert original.receipt['exited_zero'] == 1
    assert life.apply_adaptation(root,bundle,plan['contract_digest'],baseline_spec=baseline,
        baseline_receipt=original.receipt,baseline_outputs=original.private_outputs,oracle=oracle,
        trusted_oracle_sha256=oracle_sha,
        trusted_baseline_receipt_sha256=original.receipt_sha256)['status']=='applied_unverified'
    edited = runner.run_schedule(root, modified, grant(modified))
    assert edited.receipt['exited_zero']==2
    result = life.verify_adaptation(root,bundle,baseline_spec=baseline,
        baseline_receipt=original.receipt,baseline_outputs=original.private_outputs,
        modified_spec=modified,modified_receipt=edited.receipt,
        modified_outputs=edited.private_outputs,oracle=oracle,trusted_oracle_sha256=oracle_sha,
        trusted_baseline_receipt_sha256=original.receipt_sha256,
        trusted_modified_receipt_sha256=edited.receipt_sha256)
    assert result['status']=='verified_fresh' and result['report']['scheduled']==3
    if is_async:
        adversity = copy.deepcopy(modified)
        adversity['schedule'] = [{'case_id':mode,'entry':'entry.py','argv':[mode,'async']}
                                 for mode in ('exception','cancel')]
        adverse_result = runner.run_schedule(root, adversity, grant(adversity))
        assert adverse_result.receipt['exited_zero'] == 2
        for case_id, wanted in [('exception','LookupError'),('cancel','CancelledError')]:
            output = adverse_result.private_outputs[case_id][0]
            observed = __import__('json').loads(output)
            assert observed['result'] == wanted
            assert observed['effects'] == [] and observed['state']['count'] == 0
            assert observed['assessments'] == 0
    assert life.adaptation_status(root,bundle)['status']=='applied_unverified'
    assert life.rollback_adaptation(root,bundle,plan['contract_digest'])['status']=='rolled_back'
    assert (root/'host.py').read_bytes()==source.encode()
