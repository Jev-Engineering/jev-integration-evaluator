"""Synthetic native repository contract checks; no target launch or mutation."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import repository_run as session
from jev_integration_evaluator.runners import isolated_python as runner
from scripts.implementation_fixtures import fixture

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='secure repository session requires POSIX')


def planned(tmp_path):
    root, output = tmp_path / 'target', tmp_path / 'session'
    inventory, spec = fixture(root, 'C')
    context = session.request_context()
    scanned = session.inspect_repository(root, context=context)
    scope = dict(schema_version='1.0', kind='repository-run-scope-v1', reference='synthetic-plan',
                 repository_identity=scanned['report']['repository_identity'],
                 context_sha256=scanned['context_sha256'], bundle_digest=None,
                 trusted_session_head=None, trusted_baseline_receipt=None,
                 trusted_modified_receipt=None, rollback_digest=None,
                 execution_environment='none', grants={**session.ZERO_GRANTS, 'prepare': True})
    prepared = dict(schema_version='1.0', adapter=session.ADAPTER, inventory=inventory, spec=spec)
    result = session.run_repository(root, output, context=context, prepared=prepared,
                                    scope=scope, stop_after='plan')
    assert result['status'] == 'planned'
    state = json.loads((output / 'journal.jsonl').read_text().splitlines()[-1])['state']
    bundle = Path(state['bundle']['path'])
    plan = json.loads((bundle / 'implementation-plan.json').read_text())
    return root, output, state, plan, result


def contract_for(tmp_path, root, state, plan, result):
    dependency_root = tmp_path / 'selected-deps'
    module = dependency_root / 'toy_package'
    module.mkdir(parents=True)
    (module / '__init__.py').write_text('def marker(): return "approved"\n')
    metadata = dependency_root / 'toy_package-1.0.dist-info' / 'METADATA'
    metadata.parent.mkdir()
    metadata.write_text('Metadata-Version: 2.1\nName: toy_package\nVersion: 1.0\n')
    selected = dict(interpreter_path=sys.executable, dependency_root=str(dependency_root),
                    files=['toy_package/__init__.py', 'toy_package-1.0.dist-info/METADATA'],
                    distributions=[dict(name='toy_package', version='1.0',
                                        metadata_path='toy_package-1.0.dist-info/METADATA')])
    host = plan['owned_files'][0]['file']
    baseline = runner.prepare_spec(root, [host],
        [dict(case_id='baseline', entry=host, argv=['baseline'])], target_environment=selected)
    modified = copy.deepcopy(baseline)
    patch = json.loads((Path(state['bundle']['path']) / 'patch-plan.json').read_text())
    changed = {row['file']: row['new_content'].encode() for row in patch['changes']}
    modified['files'] = []
    for owned in plan['owned_files']:
        path = owned['file']
        modified['files'].append(dict(path=path, sha256=cap._hash(changed[path]),
                                      bytes=len(changed[path]), mode=owned['new_mode']))
    modified['schedule'] = [dict(case_id=mode, entry=host, argv=[mode]) for mode in ('off','shadow')]
    wanted = dict(reached=True, result='first', effects=['first'], state={'done': True},
                  assessments=0, dependency_origin='/deps/toy_package/__init__.py')
    oracle = dict(schema_version='1.0', kind='native-postconditions-v1',
                  repository_identity=state['repository_identity'], context_sha256=state['context_sha256'],
                  bundle_digest=plan['contract_digest'], adapter='json-state-v1')
    for phase, spec in (('baseline', baseline), ('modified', modified)):
        oracle[phase] = dict(request_sha256=runner.request_digest(spec),
                             source_manifest_sha256=cap._digest(spec['files']), attempt=1,
                             cases=[dict(case_id=case['case_id'],
                                         entry_sha256=next(row['sha256'] for row in spec['files'] if row['path']==case['entry']),
                                         observation={**wanted, 'assessments':1 if case['case_id']=='shadow' else 0})
                                    for case in spec['schedule']])
    contract = dict(schema_version='1.0', kind='repository-native-contract-v1',
                    baseline_spec=baseline, modified_spec=modified, oracle=oracle)
    scope = dict(schema_version='1.1', kind='repository-run-scope-v1', reference='synthetic-native',
                 repository_identity=state['repository_identity'], context_sha256=state['context_sha256'],
                 bundle_digest=plan['contract_digest'], trusted_session_head=result['session_head_sha256'],
                 trusted_baseline_receipt=None, trusted_modified_receipt=None,
                 trusted_baseline_private_output=None, trusted_modified_private_output=None,
                 trusted_oracle_sha256=cap._digest(oracle), native_contract_sha256=cap._digest(contract),
                 rollback_digest=None, execution_environment='isolated',
                 grants={**session.ZERO_GRANTS, 'baseline':True})
    return contract, scope


def test_native_contract_binds_created_owned_file_and_external_oracle(tmp_path):
    root, output, state, plan, result = planned(tmp_path)
    contract, scope = contract_for(tmp_path, root, state, plan, result)
    checked_scope = session._scope(scope, state, result['session_head_sha256'], True)
    assert session._native_contract(contract, state, plan, checked_scope, 'baseline') == contract
    assert {row['path'] for row in contract['modified_spec']['files']} == {row['file'] for row in plan['owned_files']}
    changed = copy.deepcopy(contract)
    changed['modified_spec']['files'].pop()
    scope['native_contract_sha256'] = cap._digest(changed)
    changed['oracle']['modified']['source_manifest_sha256'] = cap._digest(changed['modified_spec']['files'])
    scope['native_contract_sha256'] = cap._digest(changed)
    scope['trusted_oracle_sha256'] = cap._digest(changed['oracle'])
    with pytest.raises(session.SessionError, match='native_spec_omits_owned_source'):
        session._native_contract(changed, state, plan, scope, 'baseline')


def test_native_contract_rejects_unanchored_oracle_and_attempt(tmp_path):
    root, output, state, plan, result = planned(tmp_path)
    contract, scope = contract_for(tmp_path, root, state, plan, result)
    scope['trusted_oracle_sha256'] = '0' * 64
    with pytest.raises(session.SessionError, match='native_oracle_external_anchor_mismatch'):
        session._native_contract(contract, state, plan, scope, 'baseline')
    scope['trusted_oracle_sha256'] = cap._digest(contract['oracle'])
    contract['oracle']['baseline']['attempt'] = 2
    scope['native_contract_sha256'] = cap._digest(contract)
    scope['trusted_oracle_sha256'] = cap._digest(contract['oracle'])
    with pytest.raises(session.SessionError, match='native_oracle_attempt_mismatch'):
        session._native_contract(contract, state, plan, scope, 'baseline')
