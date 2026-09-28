"""Frozen #6 review API seam; real dependency is exercised after its merge."""
import ast
import copy
import hashlib
import sys
from types import ModuleType

import pytest

from jev_integration_evaluator.integrations.adaptation_review import draft_adaptation_request
import jev_integration_evaluator.integrations.adaptation_review as reviewed
from jev_integration_evaluator.io import InputError, digest


def _fixture(tmp_path, monkeypatch):
    source = b'import adapter\nclass Worker:\n    def baseline(self, request):\n        return request\n    def run(self, request):\n        return self.baseline(request)\n'
    adapter = b'def invoke(original, request):\n    return original(request)\n'
    (tmp_path / 'worker.py').write_bytes(source)
    (tmp_path / 'adapter.py').write_bytes(adapter)
    source_hash = hashlib.sha256(source).hexdigest()
    adapter_hash = hashlib.sha256(adapter).hexdigest()
    analysis = {'synthetic': True}
    inventory = {'analysis_identity': analysis, 'scan_fingerprint': digest(analysis),
                 'files': [{'file':'worker.py','sha256':source_hash},
                           {'file':'adapter.py','sha256':adapter_hash}],
                 'configuration_evidence': [],
                 'candidates': [{'candidate_id':'c', 'source': {
                     'file':'worker.py','symbol':'Worker.run','source_sha256':'a'*64,
                     'file_sha256':source_hash}, 'tier':1,'pattern':'C',
                     'semantic_review':{'approved':True,'reviewer':'source reviewer',
                         'reason':'reviewed synthetic seam','source_sha256':'a'*64}}]}
    context = {'candidate_id':'c','inventory_sha256':digest(inventory),
               'source_sha256':'a'*64,
               'sources':[{'file':'worker.py','sha256':source_hash,'symbols':['Worker']},
                          {'file':'adapter.py','sha256':adapter_hash,'symbols':['invoke']}]}
    module = ModuleType('jev_integration_evaluator.agent_review')
    class RecordedReviewAdapter:
        def __init__(self, response): self.response = response
        def respond(self, request): return copy.deepcopy(self.response)
    module.RecordedReviewAdapter = RecordedReviewAdapter
    module.retrieve_context = lambda *args, **kwargs: copy.deepcopy(context)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(reviewed, '_caller_scope', lambda *args: {
        'kind':'bounded-python-caller-scope-v1','discovery_sha256':'b'*64,
        'source_files_sha256':'c'*64,'selected_symbol':'Worker.run',
        'calls':[{'file':'entry.py','line':2,'column':0}],
        'unknown_external_callers':True})
    policy = {'existing_host_policy':'reviewed fixture'}
    request = {'context':context,'host_policy_sha256':digest(policy),
               'authority':{'mutation':False,'execution':False,'egress':False}}
    proposal = {'schema_version':'1.0','kind':'offline-adaptation-proposal-v1',
                'request_sha256':digest(request),'reviewer':'offline fixture',
                'reason':'selected existing callback','shape':'instance-method-tail-call-v1',
                'adapter_file':'adapter.py','adapter_name':'adapter',
                'evidence':[{'file':'worker.py','sha256':source_hash,'symbol':'Worker.run'},
                            {'file':'adapter.py','sha256':adapter_hash,'symbol':'invoke'}],
                'unresolved':[]}
    binding = {'approved':True,'proposal_sha256':digest(proposal),
               'context_sha256':digest(context),'reviewer':'independent reviewer',
               'reason':'existing callback and policy checked','source_sha256':'a'*64,
               'adapter_file':'adapter.py','adapter_sha256':adapter_hash,
               'host_policy_sha256':digest(policy)}
    return inventory, context, RecordedReviewAdapter(proposal), policy, binding


def test_reviewed_proposal_requires_fresh_source_and_independent_binding(tmp_path, monkeypatch):
    inventory, context, adapter, policy, binding = _fixture(tmp_path, monkeypatch)
    result = draft_adaptation_request(tmp_path, inventory, context, adapter,
                                      saved_answers={'host_policy':policy},
                                      trusted_binding_review=binding)
    assert result['status'] == 'reviewed_adaptation_request'
    assert result['request']['source']['symbol'] == 'Worker.run'
    assert result['request']['agent_proposal_sha256'] == digest(adapter.response)
    assert result['caller_scope']['unknown_external_callers'] is True
    assert result['target_modified'] is False and result['target_executed'] is False
    assert (tmp_path / 'worker.py').read_bytes().endswith(b'return self.baseline(request)\n')
    changed_policy = {'existing_host_policy':'changed'}
    with pytest.raises(InputError, match='stale'):
        draft_adaptation_request(tmp_path, inventory, context, adapter,
                                 saved_answers={'host_policy':changed_policy},
                                 trusted_binding_review=binding)
    changed_binding = {**binding, 'adapter_sha256':'0'*64}
    with pytest.raises(InputError, match='binding review'):
        draft_adaptation_request(tmp_path, inventory, context, adapter,
                                 saved_answers={'host_policy':policy},
                                 trusted_binding_review=changed_binding)


def test_reviewed_proposal_stale_or_unresolved_blocks(tmp_path, monkeypatch):
    inventory, context, adapter, policy, binding = _fixture(tmp_path, monkeypatch)
    adapter.response['request_sha256'] = '0'*64
    with pytest.raises(InputError, match='stale'):
        draft_adaptation_request(tmp_path, inventory, context, adapter,
                                 saved_answers={'host_policy':policy},
                                 trusted_binding_review=binding)
    adapter.response['request_sha256'] = digest({'context':context,
        'host_policy_sha256':digest(policy),
        'authority':{'mutation':False,'execution':False,'egress':False}})
    adapter.response['unresolved'] = ['missing_host_capability']
    blocked = draft_adaptation_request(tmp_path, inventory, context, adapter,
                                       saved_answers={'host_policy':policy},
                                       trusted_binding_review=binding)
    assert blocked['status'] == 'blocked'
    (tmp_path / 'worker.py').write_bytes(b'changed\n')
    with pytest.raises(InputError, match='changed'):
        draft_adaptation_request(tmp_path, inventory, context, adapter,
                                 saved_answers={'host_policy':policy},
                                 trusted_binding_review=binding)


def test_bounded_caller_audit_refuses_ambiguous_receiver_and_reflection(tmp_path, monkeypatch):
    source = {'file':'worker.py','symbol':'Worker.run'}
    files = {
        'worker.py':'class Worker:\n    def run(self, request):\n        return request\n',
        'entry.py':'import worker\nresult = worker.Worker().run(1)\n',
    }
    report = {'report_sha256':'f'*64,
              'files':[{'file':name,'sha256':hashlib.sha256(text.encode()).hexdigest()}
                       for name,text in files.items()]}
    monkeypatch.setattr(reviewed.cap, 'discover_repository', lambda *args: report)
    context = {'search_coverage':{'discovery_excludes':[],
                                  'capability_report_sha256':'f'*64},
               'sources':[{'file':name,'sha256':hashlib.sha256(text.encode()).hexdigest(),
                           'text':text} for name,text in files.items()]}
    accepted = reviewed._caller_scope(tmp_path, context, source,
                                      'instance-method-tail-call-v1')
    assert accepted['calls'] == [{'file':'entry.py','line':2,'column':9}]
    context['sources'][1]['text'] = 'import worker\nvalue = worker.Worker()\nresult = value.run(1)\n'
    context['sources'][1]['sha256'] = hashlib.sha256(context['sources'][1]['text'].encode()).hexdigest()
    report['files'][1]['sha256'] = context['sources'][1]['sha256']
    with pytest.raises(InputError, match='Ambiguous'):
        reviewed._caller_scope(tmp_path, context, source, 'instance-method-tail-call-v1')
    context['sources'][1]['text'] = 'import worker\nresult = getattr(worker.Worker(), "run")(1)\n'
    context['sources'][1]['sha256'] = hashlib.sha256(context['sources'][1]['text'].encode()).hexdigest()
    report['files'][1]['sha256'] = context['sources'][1]['sha256']
    with pytest.raises(InputError, match='Dynamic'):
        reviewed._caller_scope(tmp_path, context, source, 'instance-method-tail-call-v1')
