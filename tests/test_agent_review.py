"""Offline source-bound drafting; fixtures are synthetic, not host measurements."""
import copy
import hashlib
import sys
from dataclasses import replace
import json
from pathlib import Path

import pytest

from jev_integration_evaluator.agent_review import (
    RecordedReviewAdapter, draft_reviewed_spec, retrieve_context,
)
from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.nomination_inventory import (
    _settings, discover_repository_capabilities, prepare_nominated_inventory, review_nominated_inventory,
)


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


def test_agent_only_reports_supported_blocked_facts():
    inventory, binding, context, answers, proposal = prepared()
    proposal['unresolved'] = ['ambiguous_callback']
    result = draft_reviewed_spec(BASE / 'target', inventory, context,
                                 RecordedReviewAdapter(proposal), saved_answers=answers,
                                 trusted_verification=binding['verification'])
    assert result['status'] == 'blocked' and result['reasons'] == ['ambiguous_callback']
    proposal['unresolved'] = ['grant_execution']
    with pytest.raises(InputError, match='Unsupported unresolved'):
        draft_reviewed_spec(BASE / 'target', inventory, context,
                            RecordedReviewAdapter(proposal), saved_answers=answers,
                            trusted_verification=binding['verification'])


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


def test_unbound_related_context_is_rejected(tmp_path):
    inventory, binding, _, _, _ = prepared()
    raw = (BASE / 'target' / 'host_example_e.py').read_bytes()
    (tmp_path / 'host_example_e.py').write_bytes(raw)
    (tmp_path / 'test_host.py').write_text(
        'def test_boundary():\n    assert select_boundary_example_e\n', encoding='utf-8')
    (tmp_path / 'caller.py').write_text(
        'def call(request):\n    return select_boundary_example_e(request)\n', encoding='utf-8')
    (tmp_path / 'policy.json').write_text('{"runtime_default":"off"}', encoding='utf-8')
    related_allowlist = tuple(dict(file=name, sha256=hashlib.sha256((tmp_path / name).read_bytes()).hexdigest(), role=role)
                              for name, role in [('test_host.py', 'tests'), ('caller.py', 'caller'),
                                                 ('policy.json', 'host_policy')])
    with pytest.raises(InputError, match='bound capability report'):
        retrieve_context(tmp_path, inventory, binding['candidate_id'], related_files=related_allowlist)


def test_unreviewed_secret_and_ignored_directories_never_enter_context(tmp_path):
    inventory, binding, _, _, _ = prepared()
    (tmp_path / 'host_example_e.py').write_bytes((BASE / 'target' / 'host_example_e.py').read_bytes())
    (tmp_path / 'secret.py').write_text('PRIVATE_SENTINEL = "secret"\n', encoding='utf-8')
    for directory in ('vendor', '.tox', '.next', 'target'):
        p = tmp_path / directory
        p.mkdir()
        (p / 'test_private.py').write_text('PRIVATE_SENTINEL = "secret"\n', encoding='utf-8')
    context = retrieve_context(tmp_path, inventory, binding['candidate_id'])
    assert 'PRIVATE_SENTINEL' not in str(context)
    assert [row['file'] for row in context['sources']] == ['host_example_e.py']
    with pytest.raises(InputError, match='bound capability report'):
        retrieve_context(tmp_path, inventory, binding['candidate_id'], related_files=(
            dict(file='secret.py', sha256=hashlib.sha256((tmp_path / 'secret.py').read_bytes()).hexdigest(),
                 role='caller'),))
    for path in ('vendor/test_private.py', '.tox/test_private.py', '.next/test_private.py',
                 'target/test_private.py'):
        with pytest.raises(InputError, match='bound capability report'):
            retrieve_context(tmp_path, inventory, binding['candidate_id'], related_files=(
                dict(file=path, sha256=hashlib.sha256((tmp_path / path).read_bytes()).hexdigest(), role='tests'),))
    (tmp_path / 'private_policy.py').write_text('PRIVATE_SENTINEL = "secret"\n', encoding='utf-8')
    with pytest.raises(InputError, match='bound capability report'):
        retrieve_context(tmp_path, inventory, binding['candidate_id'], related_files=(
            dict(file='private_policy.py',
                 sha256=hashlib.sha256((tmp_path / 'private_policy.py').read_bytes()).hexdigest(),
                 role='host_policy'),), discovery_excludes=('private_*',))
    malicious_inventory = copy.deepcopy(inventory)
    malicious_inventory['files'].append(dict(file='secret.py',
                                             sha256=hashlib.sha256((tmp_path / 'secret.py').read_bytes()).hexdigest(),
                                             mode=0o644))
    with pytest.raises(InputError, match='Excluded or sensitive'):
        retrieve_context(tmp_path, malicious_inventory, binding['candidate_id'])


@pytest.mark.skipif(sys.platform != 'linux', reason='Native POSIX discovery backend')
def test_discovery_to_reviewed_spec_on_opaque_host(tmp_path):
    _, binding, _, answers, _ = prepared()
    source = (BASE / 'target' / 'host_example_e.py').read_bytes().replace(b'_example_e', b'_q7')
    (tmp_path / 'host_q7.py').write_bytes(source)
    (tmp_path / 'private_dir').mkdir()
    (tmp_path / 'private_dir' / 'host.py').write_text('PRIVATE_SENTINEL = 1\n')
    (tmp_path / 'credentials').mkdir()
    (tmp_path / 'credentials' / 'host.py').write_text('PRIVATE_SENTINEL = 2\n')
    policy = replace(_settings(DEFAULT, None)[1], exclude=('private_dir', 'private_*'))
    report = discover_repository_capabilities(tmp_path, DEFAULT, policy=policy)
    seam = next(s for s in report['seams'] if s['source']['qualified_symbol'] == 'select_boundary_q7')
    anchor = seam['source']
    nomination = dict(schema_version='1.0', discovery_version=cap.VERSION,
                      report_sha256=report['report_sha256'], seam_id=seam['seam_id'],
                      source=anchor, pattern='E', proposer='offline-test',
                      rationale='Finite ambiguous outcome with an independent host observation.',
                      evidence=[{k: anchor[k] for k in ('file', 'file_sha256', 'start_line', 'end_line')}])
    prepared_inventory = prepare_nominated_inventory(tmp_path, report, [nomination], DEFAULT, policy=policy)
    candidate = prepared_inventory['inventory']['candidates'][0]
    review = dict(schema_version='1.0', prepared_sha256=prepared_inventory['prepared_sha256'],
                  reviews={candidate['candidate_id']: dict(
                      source_sha256=candidate['source']['source_sha256'], reviewer='independent-offline-fixture',
                      reason='Existing finite semantic decision with existing host callbacks.', approved=True)})
    reviewed = review_nominated_inventory(tmp_path, report, prepared_inventory, review, DEFAULT, policy=policy)
    inventory = reviewed['inventory']
    related = ()
    with pytest.raises(InputError, match='bound capability report'):
        retrieve_context(tmp_path, inventory, candidate['candidate_id'])
    with pytest.raises(InputError, match='mismatch'):
        retrieve_context(tmp_path, inventory, candidate['candidate_id'], related_files=related,
                         capability_report=report, discovery_excludes=())
    for forbidden in ('private_dir/host.py', 'credentials/host.py'):
        row = dict(file=forbidden, sha256=hashlib.sha256((tmp_path / forbidden).read_bytes()).hexdigest(),
                   role='caller')
        with pytest.raises(InputError, match='allowlist'):
            retrieve_context(tmp_path, inventory, candidate['candidate_id'],
                             capability_report=report, related_files=(row,))
        malicious = copy.deepcopy(inventory)
        malicious['files'].append({k: row[k] for k in ('file', 'sha256')})
        with pytest.raises(InputError, match='absent from bound capability report'):
            retrieve_context(tmp_path, malicious, candidate['candidate_id'], capability_report=report)
    forged = copy.deepcopy(inventory)
    forged['files'].append(dict(file='extra.py', sha256='0' * 64))
    with pytest.raises(InputError, match='absent from bound capability report'):
        retrieve_context(tmp_path, forged, candidate['candidate_id'], capability_report=report)
    (tmp_path / 'extra.py').write_text('PRIVATE_SENTINEL = 3\n')
    with pytest.raises(InputError, match='changed since reviewed discovery'):
        retrieve_context(tmp_path, inventory, candidate['candidate_id'], capability_report=report)
    (tmp_path / 'extra.py').unlink()
    context = retrieve_context(tmp_path, inventory, candidate['candidate_id'],
                               capability_report=report, related_files=related)
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
                    request_sha256=digest(request), reviewer='offline-reviewer',
                    reason='Existing callback roles matched to recipe E.',
                    evidence=[dict(file='host_q7.py', sha256=hashlib.sha256(source).hexdigest(),
                                   symbol='select_boundary_q7')],
                    recipe_id='python.E',
                    bindings={k: v.replace('_example_e', '_q7') for k, v in binding['bindings'].items()},
                    questions=binding['questions'], primary_question=binding['primary_question'],
                    evidence_question=binding['evidence_question'],
                    label_actions=binding['label_actions'], unresolved=[])
    result = draft_reviewed_spec(tmp_path, inventory, context, RecordedReviewAdapter(proposal),
                                 saved_answers=answers, trusted_verification=verification,
                                 capability_report=report, related_files=related)
    assert result['status'] == 'reviewed_specification'
