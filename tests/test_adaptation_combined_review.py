"""Real #6 source context through prerequisites, rescan and method preparation."""
import ast
import copy
import hashlib
import os
import sys

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.agent_review import RecordedReviewAdapter, retrieve_context
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.integrations.adaptation_prerequisites import (
    apply_prerequisites, draft_agent_prerequisites,
    inspect_prerequisite_postconditions)
from jev_integration_evaluator.integrations.adaptation_review import draft_adaptation_request
from jev_integration_evaluator.integrations import adaptation_lifecycle as life
from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.runners import isolated_python as runner

pytestmark = pytest.mark.skipif(sys.platform != 'linux',
                                reason='requires secure native Linux discovery')

HOST = b'''import adapter
class Worker:
    def baseline(self, request):
        return request + 1
    def run(self, request):
        return self.baseline(request)
'''
ADAPTER = b'''MODE = 'off'
calls = 0
def invoke(original, request):
    global calls
    if MODE == 'shadow': calls += 1
    return original(request)
'''
ENTRY = b'''import json, helper_a, helper_b
first = helper_a.add_one(3)
second = helper_b.double(3)
print(json.dumps({'reached':True,'result':f'{first}-{second}',
    'effects':[f'a{first}',f'b{second}'],'state':{'count':2},
    'assessments':0,'dependency_origin':'none'},sort_keys=True))
'''
ADAPT_ENTRY = b'''import adapter, host, json, sys
adapter.MODE = sys.argv[1]
result = host.Worker().run(3)
print(json.dumps({'reached':True,'result':str(result),'effects':[],
    'state':{'count':1},'assessments':adapter.calls,
    'dependency_origin':'none'},sort_keys=True))
'''
ORIGINALS = {'host.py':HOST, 'adapter.py':ADAPTER, 'helper_a.py':b'X = 1\n',
             'helper_b.py':b'X = 2\n', 'entry.py':ENTRY, 'adapt_entry.py':ADAPT_ENTRY}


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _inventory(root, revision):
    report = cap.discover_repository(root, cap.DiscoveryPolicy(
        exclude=tuple(DEFAULT['repository']['exclude'])))
    files = [{'file':row['file'],'sha256':row['sha256']} for row in report['files']]
    host_hash = _sha((root / 'host.py').read_bytes())
    source_hash = _sha(b'    def run(self, request):\n        return self.baseline(request)\n')
    analysis = {'synthetic':True,'review_revision':revision}
    inventory = {'analysis_identity':analysis,'scan_fingerprint':digest(analysis),
                 'files':files,'configuration_evidence':[],
                 'candidates':[{'candidate_id':'method-c','tier':1,'pattern':'C',
                                'source':{'file':'host.py','symbol':'Worker.run',
                                          'source_sha256':source_hash,'file_sha256':host_hash},
                                'semantic_review':{'approved':True,
                                    'reviewer':f'independent-source-{revision}',
                                    'reason':'bounded ordinary method with existing baseline',
                                    'source_sha256':source_hash}}]}
    return inventory, report


def _prepared(root, recovery):
    root.mkdir()
    for name, raw in ORIGINALS.items():
        (root / name).write_bytes(raw)
        os.chmod(root / name, 0o644)
    inventory, report = _inventory(root, 'before')
    context = retrieve_context(root, inventory, 'method-c')
    scope = ['helper_a.py','helper_b.py']
    policy = {'helper_policy':'deterministic arithmetic on integer 3'}
    observation = {'reached':True,'result':'4-6','effects':['a4','b6'],
                   'state':{'count':2},'assessments':0,'dependency_origin':'none'}
    validation = {'schema_version':'1.0','kind':'prerequisite-validation-v1',
                  'cases':[{'case_id':'helpers','entry':'entry.py',
                            'entry_sha256':_sha(ENTRY),'observation':observation}]}
    request = {'context':context,'policy_sha256':digest(policy),
               'allowed_files':scope,
               'authority':{'mutation':False,'execution':False,'egress':False}}
    proposal = {'schema_version':'1.0','kind':'adaptation-prerequisites-v1',
                'request_sha256':digest(request),'context_sha256':digest(context),
                'policy_sha256':digest(policy),
                'changes':[{'file':'helper_a.py','old_sha256':_sha(ORIGINALS['helper_a.py']),
                            'new_content':'X = 1\n\ndef add_one(value):\n    return value + 1\n'},
                           {'file':'helper_b.py','old_sha256':_sha(ORIGINALS['helper_b.py']),
                            'new_content':'X = 2\n\ndef double(value):\n    return value * 2\n'}]}
    review = {'approved':True,'proposal_sha256':digest(proposal),
              'context_sha256':digest(context),'policy_sha256':digest(policy),
              'scope_sha256':digest(scope),'validation_sha256':digest(validation),
              'reviewer':'independent-prerequisite-review',
              'reason':'exact append-only helpers and expected observations reviewed'}
    plan = draft_agent_prerequisites(root, inventory, context,
        RecordedReviewAdapter(proposal), host_policy=policy, trusted_review=review,
        allowed_files=scope, validation_spec=validation)
    applied = apply_prerequisites(root, plan, plan['contract_digest'], inventory=inventory,
        context=context, proposal=proposal, host_policy=policy, trusted_review=review,
        allowed_files=scope, validation_spec=validation, recovery_bundle=recovery)
    assert applied['status'] == 'applied_requires_rescan'
    with pytest.raises(InputError):
        retrieve_context(root, inventory, 'method-c')
    fresh_inventory, fresh_report = _inventory(root, 'after')
    fresh_context = retrieve_context(root, fresh_inventory, 'method-c')
    assert fresh_context['inventory_sha256'] != context['inventory_sha256']
    assert fresh_context['sources'] != context['sources']
    request = {'context':fresh_context,'host_policy_sha256':digest(policy),
               'authority':{'mutation':False,'execution':False,'egress':False}}
    adaptation_proposal = {'schema_version':'1.0','kind':'offline-adaptation-proposal-v1',
        'request_sha256':digest(request),'reviewer':'offline-fixture',
        'reason':'existing source and adapter callback selected',
        'shape':'instance-method-tail-call-v1','adapter_file':'adapter.py',
        'adapter_name':'adapter',
        'evidence':[{'file':'host.py','sha256':_sha(HOST),'symbol':'Worker.run'},
                    {'file':'adapter.py','sha256':_sha(ADAPTER),'symbol':'invoke'}],
        'unresolved':[]}
    binding = {'approved':True,'proposal_sha256':digest(adaptation_proposal),
               'context_sha256':digest(fresh_context),
               'reviewer':'fresh-independent-binding-review',
               'reason':'adapter callback and selected method reviewed after rescan',
               'source_sha256':fresh_context['source_sha256'],
               'adapter_file':'adapter.py','adapter_sha256':_sha(ADAPTER),
               'host_policy_sha256':digest(policy)}
    adapted = draft_adaptation_request(root, fresh_inventory, fresh_context,
        RecordedReviewAdapter(adaptation_proposal), saved_answers={'host_policy':policy},
        trusted_binding_review=binding)
    assert adapted['status'] == 'reviewed_adaptation_request'
    return fresh_inventory, adapted['request'], plan, validation


def test_real_agent_review_rescan_and_fresh_method_plan(tmp_path):
    root = tmp_path / 'host'
    inventory, request, prerequisite, validation = _prepared(root, tmp_path / 'recovery')
    planned = life.plan_adaptation(root, inventory, request, tmp_path / 'adaptation')
    assert planned['status'] == 'planned'
    assert planned['source_sha256'] == _sha(HOST)
    assert prerequisite['binding']['validation_sha256'] == digest(validation)


@pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                    reason='requires disposable privileged Linux runner')
def test_combined_review_prerequisite_native_and_method_lifecycle(tmp_path):
    root, recovery = tmp_path / 'host', tmp_path / 'recovery'
    inventory, request, prerequisite, validation = _prepared(root, recovery)
    files = list(ORIGINALS)
    helper_spec = runner.prepare_spec(root, files,
        [{'case_id':'helpers','entry':'entry.py','argv':[]}])
    grant = lambda spec: runner.ExecutionGrant(runner.request_digest(spec),
                                                'synthetic-combined-review-test')
    helper_result = runner.run_schedule(root, helper_spec, grant(helper_spec))
    helper_oracle = {'schema_version':'1.0','kind':'native-prerequisite-postconditions-v1',
        'repository_identity':digest(str(root.resolve())),
        'context_sha256':prerequisite['binding']['context_sha256'],
        'bundle_digest':prerequisite['contract_digest'],
        'validation_sha256':digest(validation),
        'request_sha256':runner.request_digest(helper_spec),
        'source_manifest_sha256':digest(helper_spec['files']), 'attempt':1,
        'cases':[{'case_id':'helpers','entry_sha256':_sha(ENTRY),
                  'observation':validation['cases'][0]['observation']}]}
    checked = inspect_prerequisite_postconditions(root,recovery,
        prerequisite['contract_digest'], spec=helper_spec, receipt=helper_result.receipt,
        outputs=helper_result.private_outputs, oracle=helper_oracle,
        validation_spec=validation,
        trusted_oracle_sha256=_sha(runner.canonical(helper_oracle)),
        trusted_receipt_sha256=helper_result.receipt_sha256)
    assert checked['status'] == 'validated_requires_rescan'
    bundle = tmp_path / 'adaptation'
    plan = life.plan_adaptation(root, inventory, request, bundle)
    baseline = runner.prepare_spec(root, files,
        [{'case_id':'baseline','entry':'adapt_entry.py','argv':['baseline']}])
    modified = copy.deepcopy(baseline)
    patch = __import__('json').loads((bundle/'patch-plan.json').read_text())
    for row in modified['files']:
        if row['path'] == 'host.py':
            row.update(sha256=plan['new_sha256'],
                       bytes=len(patch['changes'][0]['new_content'].encode()))
    modified['schedule'] = [{'case_id':mode,'entry':'adapt_entry.py','argv':[mode]}
                            for mode in ('off','shadow')]
    baseline_expected = {'reached':True,'result':'4','effects':[],
                         'state':{'count':1},'assessments':0,'dependency_origin':'none'}
    oracle = {'schema_version':'1.0','kind':'native-postconditions-v1',
        'repository_identity':digest(str(root.resolve())),
        'context_sha256':digest({'inventory_sha256':digest(inventory),
                                 'request_sha256':digest(request)}),
        'bundle_digest':plan['contract_digest'],'adapter':'json-state-v1'}
    for phase, spec in [('baseline',baseline),('modified',modified)]:
        oracle[phase] = {'request_sha256':runner.request_digest(spec),
            'source_manifest_sha256':digest(spec['files']), 'attempt':1,
            'cases':[{'case_id':case['case_id'], 'entry_sha256':_sha(ADAPT_ENTRY),
                      'observation':{**baseline_expected,
                          'assessments':1 if case['case_id']=='shadow' else 0}}
                     for case in spec['schedule']]}
    oracle_sha = _sha(runner.canonical(oracle))
    original = runner.run_schedule(root,baseline,grant(baseline))
    assert original.receipt['exited_zero'] == 1
    applied = life.apply_adaptation(root,bundle,plan['contract_digest'],
        baseline_spec=baseline,baseline_receipt=original.receipt,
        baseline_outputs=original.private_outputs,oracle=oracle,
        trusted_oracle_sha256=oracle_sha,
        trusted_baseline_receipt_sha256=original.receipt_sha256)
    assert applied['status'] == 'applied_unverified'
    edited = runner.run_schedule(root,modified,grant(modified))
    assert edited.receipt['exited_zero'] == 2
    proof = life.verify_adaptation(root,bundle,baseline_spec=baseline,
        baseline_receipt=original.receipt,baseline_outputs=original.private_outputs,
        modified_spec=modified,modified_receipt=edited.receipt,
        modified_outputs=edited.private_outputs,oracle=oracle,
        trusted_oracle_sha256=oracle_sha,
        trusted_baseline_receipt_sha256=original.receipt_sha256,
        trusted_modified_receipt_sha256=edited.receipt_sha256)
    assert proof['status']=='verified_fresh' and proof['report']['scheduled']==3
