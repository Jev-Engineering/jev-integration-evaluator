# -*- coding: utf-8 -*-
"""Synthetic café host; no live model, service or database."""
from __future__ import annotations
from threading import RLock
from jev_integration_evaluator.runtime import HostGate
LOCK = RLock()
STATE = {'effects': [], 'kept': [], 'blocked': 0, 'step': 0, 'retries': 0, 'completed': False, 'idempotent': True, 'approval': True, 'remaining': 10, 'scope': True, 'ineffective': False, 'records': 0, 'checks': True, 'revision': 0, 'compactions': 0, 'owner_allowed': True, 'child_valid': True, 'hard_block': False, 'valid': True}
RECORDS = [{'id': 'hit', 'text': 'relevant claim', 'provenance': 'source:one'}, {'id': 'counter', 'text': 'contradictory evidence', 'provenance': 'source:two', 'contradictory': True}, {'id': 'maybe', 'text': 'uncertain evidence', 'provenance': 'source:three', 'uncertain': True}, {'id': 'noise', 'text': 'unrelated background', 'provenance': 'source:four'}]

def perform_primary_example_i(request):
    STATE['effects'].append('first')
    return 'first'


def perform_alternative_example_i(request):
    STATE['effects'].append('second')
    return 'second'

OPTIONS = {'base': perform_primary_example_i, 'alt': perform_alternative_example_i}

def bound_runtime_example_i(request):
    raise RuntimeError('Synthetic fixture runtime is supplied by the authorized probe')


def bound_evidence_example_i(request):
    return {'goal': 'resolve an ambiguous request', 'evidence': request.get('evidence', ['supplied evidence'])}


def bound_baseline_action_example_i(request):
    return 'base'


def bound_registry_example_i(request):
    return dict(OPTIONS)


def bound_gate_example_i(request, action):
    return HostGate(tuple(OPTIONS) + ('first','second'), hard_block=STATE['hard_block'], approval_required=action in ('alt','merge'), approval_granted=STATE['approval'])


def bound_validate_example_i(request, action):
    return request.get('valid', True) is True and STATE['valid'] is True


def bound_blocked_example_i(request, action):
    STATE['blocked'] += 1
    return 'blocked'


def bound_guard_example_i(request):
    return LOCK


def bound_attempt_example_i(request):
    return STATE['retries']


def bound_reserve_retry_example_i(request, action):
    STATE['retries'] += 1
    return True


def bound_effect_state_example_i(request):
    return {'state': 'completed' if STATE['completed'] else 'not_started', 'idempotent': STATE['idempotent']}


def bound_completed_example_i(request):
    return 'already_completed'


def legacy_dispatch_example_i(request):
    if STATE['completed']: return bound_completed_example_i(request)
    bound_reserve_retry_example_i(request, 'base')
    return perform_primary_example_i(request)


def select_boundary_example_i(payload):
    """Reviewed finite decision boundary, not generative replacement source."""
    # Retain this unrelated café comment.
    return legacy_dispatch_example_i(payload)


def public_entry_example_i(request):
    return select_boundary_example_i(request)

