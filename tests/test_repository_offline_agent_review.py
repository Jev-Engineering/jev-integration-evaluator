"""Offline source-bound review flows through the real repository session gates."""
import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import repository_run as run
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.agent_review import retrieve_context
from jev_integration_evaluator.integrations import lifecycle as engine
from jev_integration_evaluator.nomination_inventory import (
    _settings, discover_repository_capabilities, prepare_nominated_inventory,
    review_nominated_inventory,
)

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Secure native POSIX discovery backend')
BASE = Path(__file__).resolve().parents[1] / 'examples' / 'implementation' / 'e'


def offline_input(root):
    binding = json.loads((BASE / 'binding.example.json').read_text())
    source = (BASE / 'target' / 'host_example_e.py').read_bytes().replace(b'_example_e', b'_q7')
    root.mkdir()
    (root / 'host_q7.py').write_bytes(source)
    policy = replace(_settings(DEFAULT, None)[1], exclude=('private_*',))
    report = discover_repository_capabilities(root, DEFAULT, policy=policy)
    seam = next(s for s in report['seams'] if s['source']['qualified_symbol'] == 'select_boundary_q7')
    anchor = seam['source']
    nomination = dict(schema_version='1.0', discovery_version=cap.VERSION,
                      report_sha256=report['report_sha256'], seam_id=seam['seam_id'],
                      source=anchor, pattern='E', proposer='offline-test',
                      rationale='Finite ambiguous outcome with an independent host observation.',
                      evidence=[{k: anchor[k] for k in ('file', 'file_sha256', 'start_line', 'end_line')}])
    prepared = prepare_nominated_inventory(root, report, [nomination], DEFAULT, policy=policy)
    candidate = prepared['inventory']['candidates'][0]
    review = dict(schema_version='1.0', prepared_sha256=prepared['prepared_sha256'],
                  reviews={candidate['candidate_id']: dict(
                      source_sha256=candidate['source']['source_sha256'], reviewer='independent-offline-fixture',
                      reason='Existing finite semantic decision with existing host callbacks.', approved=True)})
    inventory = review_nominated_inventory(root, report, prepared, review, DEFAULT, policy=policy)['inventory']
    answers = {'host_policy': binding['policy'], 'runtime_ownership': binding['runtime']}
    context = retrieve_context(root, inventory, candidate['candidate_id'], capability_report=report)
    request = dict(context=context, saved_answers=answers,
                   authority=dict(mutation=False, execution=False, egress=False,
                                  installation=False, activation=False))
    verification = copy.deepcopy(binding['verification'])
    verification['entry_point'] = verification['entry_point'].replace('_example_e', '_q7')
    verification['effect_symbols'] = [x.replace('_example_e', '_q7') for x in verification['effect_symbols']]
    for case in verification['cases']:
        for phase in ('baseline', 'active'):
            case[phase]['calls'] = {k.replace('_example_e', '_q7'): v
                                    for k, v in case[phase]['calls'].items()}
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
    envelope = dict(schema_version='1.0', kind='repository-offline-agent-review-v1',
                    candidate_id=candidate['candidate_id'], capabilities=report, inventory=inventory,
                    proposal=proposal, verification=verification, related_files=[])
    session_context = run.request_context(policy=policy, adapter=run.BOUND_ADAPTER,
                                          saved_answers=answers)
    return envelope, session_context


def preparation_scope(root, context, ready):
    inspected = run.inspect_repository(root, context=context)
    return dict(schema_version='1.0', kind='repository-run-scope-v1',
                reference='synthetic-operator-authorization',
                repository_identity=inspected['report']['repository_identity'],
                context_sha256=inspected['context_sha256'], bundle_digest=None,
                trusted_session_head=ready['session_head_sha256'], trusted_baseline_receipt=None,
                trusted_modified_receipt=None, rollback_digest=None,
                execution_environment='trusted_host', prepared_sha256=ready['prepared_sha256'],
                grants={**run.ZERO_GRANTS, 'prepare': True})


def test_offline_review_requires_second_exact_scope_before_planning(tmp_path):
    root, session = tmp_path / 'host', tmp_path / 'session'
    envelope, context = offline_input(root)
    source_before = (root / 'host_q7.py').read_bytes()
    ready = run.run_repository(root, session, context=context, agent_review_input=envelope)
    assert ready['status'] == 'reviewed_specification_ready'
    assert all(count == 0 for count in ready['attempts'].values())
    assert ready['agent_review_record']['proposal_sha256'] == digest(envelope['proposal'])
    assert ready['agent_review_record']['candidate_sha256'] == digest(envelope['candidate_id'])
    assert 'evidence' not in ready['agent_review_record']
    scope = preparation_scope(root, context, ready)
    pending = run.run_repository(root, session, scope=scope, stop_after='plan')
    assert pending['status'] == 'insufficient_evidence'
    assert pending['next_action'] == 'resupply_exact_offline_agent_review'
    planned = run.run_repository(root, session, agent_review_input=envelope,
                                 scope=scope, stop_after='plan')
    assert planned['status'] == 'planned', planned
    assert planned['attempts']['plan'] == 1
    assert planned['attempts']['baseline'] == planned['attempts']['apply'] == 0
    assert (root / 'host_q7.py').read_bytes() == source_before
    state = json.loads((session / 'journal.jsonl').read_text().splitlines()[-1])['state']
    assert len(state['agent_review_history']) == 1
    assert state['agent_review_history'][0]['draft_sha256'] == ready['prepared_sha256']


def test_offline_review_rejects_changed_input_and_stale_source(tmp_path):
    root, session = tmp_path / 'host', tmp_path / 'session'
    envelope, context = offline_input(root)
    ready = run.run_repository(root, session, context=context, agent_review_input=envelope)
    changed = copy.deepcopy(envelope)
    changed['proposal']['reason'] = 'Changed after review journaled.'
    next_review = run.run_repository(root, session, agent_review_input=changed,
                                     scope=preparation_scope(root, context, ready), stop_after='plan')
    assert next_review['status'] == 'reviewed_specification_ready'
    assert next_review['attempts']['plan'] == 0
    (root / 'host_q7.py').write_bytes((root / 'host_q7.py').read_bytes() + b'\n# changed\n')
    with pytest.raises(run.SessionError, match='stale|drift|mismatch'):
        run.run_repository(root, session, agent_review_input=changed,
                           scope=preparation_scope(root, context, next_review),
                           stop_after='plan')
    state = json.loads((session / 'journal.jsonl').read_text().splitlines()[-1])['state']
    assert state['attempts']['plan'] == 0


def test_planned_offline_review_rejects_changed_proposal(tmp_path):
    root, session = tmp_path / 'host', tmp_path / 'session'
    envelope, context = offline_input(root)
    ready = run.run_repository(root, session, context=context, agent_review_input=envelope)
    planned = run.run_repository(root, session, agent_review_input=envelope,
                                 scope=preparation_scope(root, context, ready),
                                 stop_after='plan')
    assert planned['status'] == 'planned'
    changed = copy.deepcopy(envelope)
    changed['proposal']['reason'] = 'Different opinion after planning.'
    with pytest.raises(run.SessionError, match='changed_after_planning'):
        run.run_repository(root, session, agent_review_input=changed)
    state = json.loads((session / 'journal.jsonl').read_text().splitlines()[-1])['state']
    assert state['attempts']['baseline'] == state['attempts']['apply'] == 0


def test_review_text_is_externally_retained_and_only_digests_are_journaled(tmp_path):
    root, session = tmp_path / 'host', tmp_path / 'session'
    envelope, context = offline_input(root)
    sentinel = 'PRIVATE_REVIEW_SENTINEL_DO_NOT_ARCHIVE'
    envelope['proposal']['reason'] = sentinel
    ready = run.run_repository(root, session, context=context, agent_review_input=envelope)
    state = json.loads((session / 'journal.jsonl').read_text().splitlines()[-1])['state']
    assert sentinel not in (session / 'journal.jsonl').read_text()
    assert envelope['candidate_id'] not in (session / 'journal.jsonl').read_text()
    assert sorted(p.name for p in session.iterdir()) == ['journal.jsonl']
    assert state['agent_review_history'][-1]['reason_sha256'] == digest(sentinel)
    assert ready['agent_review_content_retention'] == 'caller_external_only'
    pending = run.run_repository(root, session, scope=preparation_scope(root, context, ready),
                                 stop_after='plan')
    assert pending['next_action'] == 'resupply_exact_offline_agent_review'
    assert state['attempts']['plan'] == 0


def test_legacy_raw_archive_session_record_fails_closed(tmp_path):
    root, session = tmp_path / 'host', tmp_path / 'session'
    envelope, context = offline_input(root)
    run.run_repository(root, session, context=context, agent_review_input=envelope)
    state = json.loads((session / 'journal.jsonl').read_text().splitlines()[-1])['state']
    state['agent_review_history'][-1]['input_file'] = 'agent-review-' + '0' * 64 + '.json'
    state['agent_review_history'][-1]['reviewer'] = 'raw reviewer text'
    with pytest.raises(cap.CapabilityError, match='invalid_repository_session_v1'):
        run._validate_state(state)


def test_post_plan_review_content_need_not_be_resupplied_for_owned_rollback(tmp_path):
    root, session = tmp_path / 'host', tmp_path / 'session'
    envelope, context = offline_input(root)
    ready = run.run_repository(root, session, context=context, agent_review_input=envelope)
    planned = run.run_repository(root, session, agent_review_input=envelope,
                                 scope=preparation_scope(root, context, ready),
                                 stop_after='plan')
    assert planned['status'] == 'planned'
    state = json.loads((session / 'journal.jsonl').read_text().splitlines()[-1])['state']
    assert state['agent_review_history'][-1]['draft_sha256'] == ready['prepared_sha256']
    scope = preparation_scope(root, context, ready)
    scope['trusted_session_head'] = planned['session_head_sha256']
    scope['bundle_digest'] = planned['bundle_digest']
    plan = json.loads((Path(state['bundle']['path']) / 'implementation-plan.json').read_text())
    scope['grants'] = {**run.ZERO_GRANTS, 'rollback': True}
    scope['rollback_digest'] = engine.rollback_digest(plan)
    rolled = run.run_repository(root, session, scope=scope, recover=True)
    assert rolled['status'] == 'rolled_back'


def test_unresolved_host_policy_has_no_plan_or_effect(tmp_path):
    root, session = tmp_path / 'host', tmp_path / 'session'
    envelope, context = offline_input(root)
    answers = {'runtime_ownership': context['saved_answers']['runtime_ownership']}
    context['saved_answers'] = answers
    review_context = retrieve_context(root, envelope['inventory'], envelope['candidate_id'],
                                      capability_report=envelope['capabilities'])
    envelope['proposal']['request_sha256'] = digest(dict(
        context=review_context, saved_answers=answers,
        authority=dict(mutation=False, execution=False, egress=False,
                       installation=False, activation=False)))
    result = run.run_repository(root, session, context=context, agent_review_input=envelope)
    assert result['status'] == 'insufficient_evidence'
    assert result['next_action'] == 'supply_indispensable_host_policy_or_verification'
    assert all(count == 0 for count in result['attempts'].values())
    assert result['bundle_digest'] is None


def test_cli_loads_external_offline_review_without_effects(tmp_path):
    root, session = tmp_path / 'host', tmp_path / 'session'
    envelope, context = offline_input(root)
    context_path, review_path = tmp_path / 'context.json', tmp_path / 'review.json'
    context_path.write_text(json.dumps(context))
    review_path.write_text(json.dumps(envelope))
    completed = subprocess.run([
        sys.executable, '-m', 'jev_integration_evaluator.repository_run', str(root),
        '--session', str(session), '--context', str(context_path),
        '--agent-review', str(review_path)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result['status'] == 'reviewed_specification_ready'
    assert all(count == 0 for count in result['attempts'].values())
    assert result['provider_connectivity'] == 'not_tested'
