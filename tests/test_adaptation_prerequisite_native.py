"""Ephemeral privileged Linux proof of actual post-edit prerequisite helpers."""
import copy
import hashlib
import os
import sys
from types import ModuleType

import pytest

from jev_integration_evaluator.integrations.adaptation_prerequisites import (
    apply_prerequisites, draft_agent_prerequisites, inspect_prerequisite_postconditions)
from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.runners import isolated_python as runner

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                                reason='requires disposable privileged Linux runner')


def _sha(data): return hashlib.sha256(data).hexdigest()


def test_native_modified_host_reaches_both_reviewed_helpers(tmp_path, monkeypatch):
    root, bundle = tmp_path / 'host', tmp_path / 'recovery'
    root.mkdir()
    originals = {'a.py':b'def baseline(value):\n    return value + 1\n',
                 'b.py':b'def baseline(value):\n    return value * 2\n'}
    entry = b'''import a, b, json
first = a.helper_a(3)
second = b.helper_b(3)
print(json.dumps({'reached':True,'result':f'{first}-{second}',
    'effects':[f'a{first}',f'b{second}'],'state':{'count':2},
    'assessments':0,'dependency_origin':'none'},sort_keys=True))
'''
    for name, raw in {**originals,'entry.py':entry}.items():
        (root / name).write_bytes(raw)
        os.chmod(root / name, 0o644)
    inventory = {'files':[{'file':name,'sha256':_sha(raw)}
                          for name,raw in {**originals,'entry.py':entry}.items()],
                 'candidates':[{'candidate_id':'c','tier':1,'pattern':'C',
                                'source':{'source_sha256':'a'*64,'file':'a.py',
                                          'file_sha256':_sha(originals['a.py'])},
                                'semantic_review':{'approved':True,'reviewer':'source fixture',
                                                   'reason':'bounded fixture','source_sha256':'a'*64}}]}
    context = {'candidate_id':'c','inventory_sha256':digest(inventory),
               'source_sha256':'a'*64,
               'sources':[{'file':name,'sha256':_sha(raw)}
                          for name,raw in originals.items()]}
    module = ModuleType('jev_integration_evaluator.agent_review')
    module.retrieve_context = lambda *args, **kwargs: copy.deepcopy(context)
    class RecordedReviewAdapter:
        def __init__(self, response): self.response = response
        def respond(self, request): return copy.deepcopy(self.response)
    module.RecordedReviewAdapter = RecordedReviewAdapter
    monkeypatch.setitem(sys.modules, module.__name__, module)
    policy = {'synthetic_existing_host_rule':'non-authority arithmetic only'}
    scope = ['a.py','b.py']
    observation = {'reached':True,'result':'4-6','effects':['a4','b6'],
                   'state':{'count':2},'assessments':0,'dependency_origin':'none'}
    validation = {'schema_version':'1.0','kind':'prerequisite-validation-v1',
                  'cases':[{'case_id':'helper-check','entry':'entry.py',
                            'entry_sha256':_sha(entry),'observation':observation}]}
    request = {'context':context,'policy_sha256':digest(policy),'allowed_files':scope,
               'authority':{'mutation':False,'execution':False,'egress':False}}
    changes = [{'file':name,'old_sha256':_sha(raw),
                'new_content':raw.decode() + f'\ndef helper_{name[0]}(value):\n    return baseline(value)\n'}
               for name,raw in originals.items()]
    proposal = {'schema_version':'1.0','kind':'adaptation-prerequisites-v1',
                'request_sha256':digest(request),'context_sha256':digest(context),
                'policy_sha256':digest(policy),'changes':changes}
    review = {'approved':True,'proposal_sha256':digest(proposal),
              'context_sha256':digest(context),'policy_sha256':digest(policy),
              'scope_sha256':digest(scope),'validation_sha256':digest(validation),
              'reviewer':'independent fixture','reason':'exact arithmetic helpers reviewed'}
    plan = draft_agent_prerequisites(root, inventory, context, RecordedReviewAdapter(proposal),
                                     host_policy=policy, trusted_review=review,
                                     allowed_files=scope, validation_spec=validation)
    applied = apply_prerequisites(root, plan, plan['contract_digest'], inventory=inventory,
                                  context=context, proposal=proposal, host_policy=policy,
                                  trusted_review=review, allowed_files=scope,
                                  validation_spec=validation, recovery_bundle=bundle)
    assert applied['status'] == 'applied_requires_rescan'
    spec = runner.prepare_spec(root, ['a.py','b.py','entry.py'],
                               [{'case_id':'helper-check','entry':'entry.py','argv':[]}])
    result = runner.run_schedule(root, spec, runner.ExecutionGrant(
        runner.request_digest(spec), 'synthetic-prerequisite-test'))
    assert result.receipt['scheduled'] == result.receipt['recorded'] == result.receipt['exited_zero'] == 1
    oracle = {'schema_version':'1.0','kind':'native-prerequisite-postconditions-v1',
              'repository_identity':digest(str(root.resolve())),
              'context_sha256':digest(context),'bundle_digest':plan['contract_digest'],
              'validation_sha256':digest(validation),
              'request_sha256':runner.request_digest(spec),
              'source_manifest_sha256':digest(spec['files']),'attempt':1,
              'cases':[{'case_id':'helper-check','entry_sha256':_sha(entry),
                        'observation':observation}]}
    oracle_sha = _sha(runner.canonical(oracle))
    checked = inspect_prerequisite_postconditions(root,bundle,plan['contract_digest'],
        spec=spec,receipt=result.receipt,outputs=result.private_outputs,oracle=oracle,
        validation_spec=validation,
        trusted_oracle_sha256=oracle_sha,trusted_receipt_sha256=result.receipt_sha256)
    assert checked['status'] == 'validated_requires_rescan'
    assert checked['recipe_applicable'] is False and checked['integration_verified'] is False
    forged = copy.deepcopy(oracle)
    forged['cases'][0]['observation']['result'] = '5-6'
    with pytest.raises(InputError, match='oracle'):
        inspect_prerequisite_postconditions(root,bundle,plan['contract_digest'],
            spec=spec,receipt=result.receipt,outputs=result.private_outputs,oracle=forged,
            validation_spec=validation,
            trusted_oracle_sha256=oracle_sha,trusted_receipt_sha256=result.receipt_sha256)
    with pytest.raises(InputError, match='case binding'):
        inspect_prerequisite_postconditions(root,bundle,plan['contract_digest'],
            spec=spec,receipt=result.receipt,outputs=result.private_outputs,oracle=forged,
            validation_spec=validation,
            trusted_oracle_sha256=_sha(runner.canonical(forged)),
            trusted_receipt_sha256=result.receipt_sha256)
