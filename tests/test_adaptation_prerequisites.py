"""Adversarial checks for scoped append-only prerequisite plans."""
import copy
import hashlib
import sys
from types import ModuleType

import pytest
import jev_integration_evaluator.integrations.adaptation_prerequisites as prerequisites

from jev_integration_evaluator.integrations.adaptation_prerequisites import (
    apply_prerequisites, draft_prerequisite_plan, draft_agent_prerequisites,
    prerequisite_status, rollback_prerequisites, prerequisite_rollback_digest)
from jev_integration_evaluator.io import InputError, digest


def _fixture(root, monkeypatch):
    originals = {'a.py':b'def existing(value):\n    return value\n',
                 'b.py':b'def baseline(value):\n    return value + 1\n'}
    for name, content in originals.items(): (root / name).write_bytes(content)
    inventory = {'files':[{'file':name,'sha256':hashlib.sha256(content).hexdigest()}
                          for name, content in originals.items()],
                 'candidates':[{'candidate_id':'c','tier':1,'pattern':'C',
                                'source':{'source_sha256':'a'*64,'file':'a.py',
                                          'file_sha256':hashlib.sha256(originals['a.py']).hexdigest()},
                                'semantic_review':{'approved':True,'reviewer':'source fixture',
                                                   'reason':'bounded fixture','source_sha256':'a'*64}}]}
    context = {'candidate_id':'c','inventory_sha256':digest(inventory),
               'source_sha256':'a'*64,
               'sources':[{'file':name,'sha256':hashlib.sha256(content).hexdigest()}
                          for name, content in originals.items()]}
    module = ModuleType('jev_integration_evaluator.agent_review')
    module.retrieve_context = lambda *args, **kwargs: copy.deepcopy(context)
    class RecordedReviewAdapter:
        def __init__(self, response): self.response = response
        def respond(self, request): return copy.deepcopy(self.response)
    module.RecordedReviewAdapter = RecordedReviewAdapter
    monkeypatch.setitem(sys.modules, module.__name__, module)
    policy = {'fixed_host_rule':'synthetic, caller-owned'}
    validation = {'expected':{'a.py':'helper returns transformed value',
                              'b.py':'helper leaves baseline intact'}}
    changes = [{'file':name,'old_sha256':hashlib.sha256(content).hexdigest(),
                'new_content':content.decode() + '\ndef helper_'+name[0]+'(value):\n    return value\n'}
               for name, content in originals.items()]
    scope = sorted(originals)
    request = {'context':context,'policy_sha256':digest(policy),'allowed_files':scope,
               'authority':{'mutation':False,'execution':False,'egress':False}}
    proposal = {'schema_version':'1.0','kind':'adaptation-prerequisites-v1',
                'request_sha256':digest(request),'context_sha256':digest(context),
                'policy_sha256':digest(policy), 'changes':changes}
    review = {'approved':True,'proposal_sha256':digest(proposal),
              'context_sha256':digest(context),'policy_sha256':digest(policy),
              'scope_sha256':digest(scope),'validation_sha256':digest(validation),
              'reviewer':'independent fixture','reason':'reviewed exact helpers and expected results'}
    return inventory, context, proposal, policy, validation, review, scope


def _draft(root, items):
    inventory, context, proposal, policy, validation, review, scope = items
    return draft_prerequisite_plan(root, inventory, context, proposal,
                                   host_policy=policy, trusted_review=review,
                                   allowed_files=scope, validation_spec=validation)


def test_scoped_prerequisites_require_external_approval_then_rescan(tmp_path, monkeypatch):
    items = _fixture(tmp_path, monkeypatch)
    recovery = tmp_path.parent / (tmp_path.name + '-recovery')
    plan = _draft(tmp_path, items)
    assert plan['status'] == 'planned_prerequisites'
    agent_adapter = sys.modules['jev_integration_evaluator.agent_review'].RecordedReviewAdapter(items[2])
    assert draft_agent_prerequisites(tmp_path, items[0], items[1], agent_adapter,
                                     host_policy=items[3], trusted_review=items[5],
                                     allowed_files=items[6], validation_spec=items[4]) == plan
    assert all(b'helper_' not in (tmp_path / name).read_bytes() for name in items[-1])
    with pytest.raises(InputError, match='approved'):
        apply_prerequisites(tmp_path, plan, '0'*64, inventory=items[0], context=items[1],
                            proposal=items[2], host_policy=items[3], validation_spec=items[4],
                            trusted_review=items[5], allowed_files=items[6],
                            recovery_bundle=recovery)
    outcome = apply_prerequisites(tmp_path, plan, plan['contract_digest'], inventory=items[0],
                                  context=items[1], proposal=items[2], host_policy=items[3],
                                  validation_spec=items[4], trusted_review=items[5],
                                  allowed_files=items[6], recovery_bundle=recovery)
    assert outcome['status'] == 'applied_requires_rescan'
    assert outcome['verified'] is False and outcome['recipe_applicable'] is False
    assert prerequisite_status(tmp_path, recovery, plan['contract_digest'])['status'] == 'applied_requires_rescan'
    with pytest.raises(InputError, match='changed'):
        _draft(tmp_path, items)


@pytest.mark.parametrize('attack', ['authority','old_body','scope','policy','review','new_validation',
                                    'import_time_default','global_shadow','source_review'])
def test_prerequisite_authority_and_drift_fail_without_mutation(tmp_path, monkeypatch, attack):
    items = list(_fixture(tmp_path, monkeypatch))
    original = {name:(tmp_path / name).read_bytes() for name in items[-1]}
    if attack == 'authority':
        items[2] = copy.deepcopy(items[2]); items[2]['changes'][0]['new_content'] += '\ndef approve_request(value):\n    return True\n'
        items[5] = {**items[5], 'proposal_sha256':digest(items[2])}
    elif attack == 'old_body':
        items[2] = copy.deepcopy(items[2]); items[2]['changes'][0]['new_content'] = items[2]['changes'][0]['new_content'].replace('return value\n','return True\n',1)
        items[5] = {**items[5], 'proposal_sha256':digest(items[2])}
    elif attack == 'scope': items[6] = ['a.py','c.py']
    elif attack == 'policy': items[3] = {'fixed_host_rule':'changed'}
    elif attack == 'review': items[5] = {**items[5], 'approved':False}
    elif attack == 'import_time_default':
        items[2] = copy.deepcopy(items[2])
        items[2]['changes'][0]['new_content'] = items[2]['changes'][0]['new_content'].replace(
            'def helper_a(value):', 'def helper_a(value=side_effect()):')
        items[5] = {**items[5], 'proposal_sha256':digest(items[2])}
    elif attack == 'global_shadow':
        items[2] = copy.deepcopy(items[2])
        items[2]['changes'][0]['new_content'] += '\ndef value(other):\n    return other\n'
        items[5] = {**items[5], 'proposal_sha256':digest(items[2])}
    elif attack == 'source_review':
        items[0] = copy.deepcopy(items[0])
        items[0]['candidates'][0]['semantic_review']['approved'] = False
    else: items[4] = {'expected':'weaker'}
    with pytest.raises(InputError): _draft(tmp_path, items)
    assert all((tmp_path / name).read_bytes() == content for name, content in original.items())


def test_self_consistent_local_plan_substitution_has_no_apply_authority(tmp_path, monkeypatch):
    items = _fixture(tmp_path, monkeypatch)
    original = _draft(tmp_path, items)
    altered = copy.deepcopy(original)
    altered['patch']['changes'][0]['new_content'] += '\ndef extra(value):\n    return value\n'
    altered['patch']['changes'][0]['new_sha256'] = hashlib.sha256(
        altered['patch']['changes'][0]['new_content'].encode()).hexdigest()
    altered['patch']['plan_digest'] = digest({k:v for k,v in altered['patch'].items()
                                            if k != 'plan_digest'})
    altered['binding']['patch_sha256'] = digest(altered['patch'])
    altered['contract_digest'] = digest(altered['binding'])
    with pytest.raises(InputError, match='approved'):
        apply_prerequisites(tmp_path, altered, altered['contract_digest'], inventory=items[0],
                            context=items[1], proposal=items[2], host_policy=items[3],
                            validation_spec=items[4], trusted_review=items[5],
                            allowed_files=items[6],
                            recovery_bundle=tmp_path.parent / (tmp_path.name + '-forged-recovery'))
    assert b'extra' not in (tmp_path / 'a.py').read_bytes()


def test_interrupted_multifile_apply_blocks_replay_and_keeps_preimages(tmp_path, monkeypatch):
    items = _fixture(tmp_path, monkeypatch)
    plan = _draft(tmp_path, items)
    recovery = tmp_path.parent / (tmp_path.name + '-interrupted')
    original_apply = prerequisites.apply_patch_plan
    def interrupted(root, patch, approval, *, progress):
        row = patch['changes'][0]
        progress('write_started', row)
        (tmp_path / row['file']).write_bytes(row['new_content'].encode())
        progress('write_completed', row)
        raise RuntimeError('synthetic process interruption')
    monkeypatch.setattr(prerequisites, 'apply_patch_plan', interrupted)
    with pytest.raises(RuntimeError, match='interruption'):
        apply_prerequisites(tmp_path, plan, plan['contract_digest'], inventory=items[0],
                            context=items[1], proposal=items[2], host_policy=items[3],
                            validation_spec=items[4], trusted_review=items[5],
                            allowed_files=items[6], recovery_bundle=recovery)
    assert prerequisite_status(tmp_path, recovery, plan['contract_digest'])['status'] == 'blocked_recovery'
    assert (recovery / 'preimages/0.utf8').read_bytes().startswith(b'def existing')
    with pytest.raises(InputError):
        apply_prerequisites(tmp_path, plan, plan['contract_digest'], inventory=items[0],
                            context=items[1], proposal=items[2], host_policy=items[3],
                            validation_spec=items[4], trusted_review=items[5],
                            allowed_files=items[6], recovery_bundle=recovery)
    monkeypatch.setattr(prerequisites, 'apply_patch_plan', original_apply)
    with pytest.raises(InputError, match='rollback approval'):
        rollback_prerequisites(tmp_path, recovery, plan['contract_digest'],
                               plan['patch']['plan_digest'])
    approval = prerequisite_rollback_digest(plan['contract_digest'],
                                             plan['binding']['owned_sha256'])
    assert rollback_prerequisites(tmp_path, recovery, plan['contract_digest'], approval)['status'] == 'rolled_back'
    assert prerequisite_status(tmp_path, recovery, plan['contract_digest'])['status'] == 'rolled_back'
    assert (tmp_path / 'a.py').read_bytes().startswith(b'def existing')
    (recovery / 'preimages/0.utf8').write_bytes(b'tampered')
    with pytest.raises(InputError, match='preimage'):
        prerequisite_status(tmp_path, recovery, plan['contract_digest'])
