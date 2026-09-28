"""Offline source-bound drafting; fixtures are synthetic, not host measurements."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from jev_integration_evaluator.agent_review import (
    RecordedReviewAdapter, draft_reviewed_spec, retrieve_context,
)
from jev_integration_evaluator.io import InputError, digest


BASE = Path(__file__).resolve().parents[1] / 'examples' / 'implementation' / 'e'


def prepared():
    inventory = json.loads((BASE / 'reviewed-inventory.example.json').read_text())
    binding = json.loads((BASE / 'binding.example.json').read_text())
    context = retrieve_context(BASE / 'target', inventory, binding['candidate_id'])
    answers = {'host_policy': binding['policy'], 'runtime_ownership': binding['runtime']}
    request = dict(context=context, saved_answers=answers,
                   authority=dict(mutation=False, execution=False, egress=False,
                                  installation=False, activation=False))
    proposal = dict(schema_version='1.0', kind='offline-agent-review-proposal-v1',
                    request_sha256=digest(request), reviewer='offline-fixture-reviewer',
                    reason='Source matched finite decision with existing callbacks.',
                    evidence=[dict(file='host_example_e.py',
                                   sha256=context['sources'][0]['sha256'],
                                   symbol=binding['source']['symbol'])],
                    recipe_id=binding['recipe']['id'], bindings=binding['bindings'],
                    questions=binding['questions'], primary_question=binding['primary_question'],
                    evidence_question=binding['evidence_question'],
                    label_actions=binding['label_actions'], unresolved=[])
    return inventory, binding, context, answers, proposal


def test_offline_draft_from_existing_callbacks():
    inventory, binding, context, answers, proposal = prepared()
    result = draft_reviewed_spec(BASE / 'target', inventory, context,
                                 RecordedReviewAdapter(proposal), saved_answers=answers,
                                 trusted_verification=binding['verification'])
    assert result['status'] == 'reviewed_specification'
    assert result['spec']['bindings'] == binding['bindings']
    assert result['spec']['runtime']['configuration']['mode'] == 'off'
    assert result['spec']['authorization_context']['not_authority'] is True


def test_missing_policy_is_unresolved():
    inventory, binding, context, answers, proposal = prepared()
    answers.pop('host_policy')
    proposal['request_sha256'] = digest(dict(context=context, saved_answers=answers,
                                             authority=dict(mutation=False, execution=False,
                                                            egress=False, installation=False,
                                                            activation=False)))
    result = draft_reviewed_spec(BASE / 'target', inventory, context,
                                 RecordedReviewAdapter(proposal), saved_answers=answers,
                                 trusted_verification=binding['verification'])
    assert result['fields'] == ['host_policy']


def test_agent_cannot_issue_authority_or_measurements():
    inventory, binding, context, answers, proposal = prepared()
    for extra in ({'authorization': {'execution': True}},
                  {'verification': binding['verification']},
                  {'shell': 'echo unsafe'}):
        altered = {**proposal, **extra}
        with pytest.raises(InputError):
            draft_reviewed_spec(BASE / 'target', inventory, context,
                                RecordedReviewAdapter(altered), saved_answers=answers,
                                trusted_verification=binding['verification'])


def test_invalid_mapping_rejected_by_deterministic_validator():
    inventory, binding, context, answers, proposal = prepared()
    proposal['label_actions'] = {**proposal['label_actions'], 'succeeded': 'invented'}
    with pytest.raises(InputError, match='Deterministic'):
        draft_reviewed_spec(BASE / 'target', inventory, context,
                            RecordedReviewAdapter(proposal), saved_answers=answers,
                            trusted_verification=binding['verification'])


def test_missing_independent_observations_remain_unresolved():
    inventory, _, context, answers, proposal = prepared()
    result = draft_reviewed_spec(BASE / 'target', inventory, context,
                                 RecordedReviewAdapter(proposal), saved_answers=answers,
                                 trusted_verification={})
    assert result['status'] == 'unresolved'
    assert result['fields'] == ['independent_verification']


def test_ambiguous_callback_is_rejected():
    inventory, binding, context, answers, proposal = prepared()
    proposal['bindings']['observe'] = proposal['bindings']['finish']
    with pytest.raises(InputError, match='Deterministic'):
        draft_reviewed_spec(BASE / 'target', inventory, context,
                            RecordedReviewAdapter(proposal), saved_answers=answers,
                            trusted_verification=binding['verification'])


def test_source_drift_rejected(tmp_path):
    inventory, binding, context, answers, proposal = prepared()
    (tmp_path / 'host_example_e.py').write_bytes((BASE / 'target' / 'host_example_e.py').read_bytes() + b'\n# drift\n')
    with pytest.raises(InputError, match='drift'):
        draft_reviewed_spec(tmp_path, inventory, context,
                            RecordedReviewAdapter(proposal), saved_answers=answers,
                            trusted_verification=binding['verification'])


def test_opaque_name_host_offline_review(tmp_path):
    inventory, binding, _, answers, _ = prepared()
    original = (BASE / 'target' / 'host_example_e.py').read_text(encoding='utf-8')
    source = original.replace('_example_e', '_q7')
    (tmp_path / 'host_q7.py').write_bytes(source.encode('utf-8'))
    source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    selected = next(c for c in inventory['candidates'] if c['candidate_id'] == binding['candidate_id'])
    lines = source.splitlines(keepends=True)
    snippet = ''.join(lines[selected['source']['start_line'] - 1:selected['source']['end_line']])
    selected['source'].update(file='host_q7.py', symbol='select_boundary_q7',
                              file_sha256=source_hash,
                              source_sha256=hashlib.sha256(snippet.encode('utf-8')).hexdigest())
    selected['semantic_review']['source_sha256'] = selected['source']['source_sha256']
    for row in inventory['files']:
        row.update(file='host_q7.py', sha256=source_hash)
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    context = retrieve_context(tmp_path, inventory, binding['candidate_id'])
    answers['runtime_ownership'] = copy.deepcopy(answers['runtime_ownership'])
    verification = copy.deepcopy(binding['verification'])
    verification['entry_point'] = verification['entry_point'].replace('_example_e', '_q7')
    verification['effect_symbols'] = [x.replace('_example_e', '_q7') for x in verification['effect_symbols']]
    for case in verification['cases']:
        for phase in ('baseline', 'active'):
            case[phase]['calls'] = {k.replace('_example_e', '_q7'): v for k, v in case[phase]['calls'].items()}
    request = dict(context=context, saved_answers=answers,
                   authority=dict(mutation=False, execution=False, egress=False,
                                  installation=False, activation=False))
    proposal = dict(schema_version='1.0', kind='offline-agent-review-proposal-v1',
                    request_sha256=digest(request), reviewer='offline-fixture-reviewer',
                    reason='Finite ambiguity and observed host callbacks match recipe E.',
                    evidence=[dict(file='host_q7.py', sha256=source_hash, symbol='select_boundary_q7')],
                    recipe_id='python.E',
                    bindings={k: v.replace('_example_e', '_q7') for k, v in binding['bindings'].items()},
                    questions=binding['questions'], primary_question=binding['primary_question'],
                    evidence_question=binding['evidence_question'],
                    label_actions=binding['label_actions'], unresolved=[])
    result = draft_reviewed_spec(tmp_path, inventory, context, RecordedReviewAdapter(proposal),
                                 saved_answers=answers, trusted_verification=verification)
    assert result['status'] == 'reviewed_specification'
    assert result['spec']['source']['symbol'] == 'select_boundary_q7'
