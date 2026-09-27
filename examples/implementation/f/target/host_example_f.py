# -*- coding: utf-8 -*-
"""Synthetic café host; no live model, service or database."""
from __future__ import annotations
from threading import RLock
from jev_integration_evaluator.runtime import HostGate
LOCK = RLock()
STATE = {'effects': [], 'kept': [], 'blocked': 0, 'step': 0, 'retries': 0, 'completed': False, 'idempotent': True, 'approval': True, 'remaining': 10, 'scope': True, 'ineffective': False, 'records': 0, 'checks': True, 'revision': 0, 'compactions': 0, 'owner_allowed': True, 'child_valid': True, 'hard_block': False, 'valid': True}
RECORDS = [{'id': 'hit', 'text': 'relevant claim', 'provenance': 'source:one'}, {'id': 'counter', 'text': 'contradictory evidence', 'provenance': 'source:two', 'contradictory': True}, {'id': 'maybe', 'text': 'uncertain evidence', 'provenance': 'source:three', 'uncertain': True}, {'id': 'noise', 'text': 'unrelated background', 'provenance': 'source:four'}]

def perform_primary_example_f(request):
    STATE['effects'].append('first')
    return 'first'


def perform_alternative_example_f(request):
    STATE['effects'].append('second')
    return 'second'

OPTIONS = {'continue': 'continue', 'stop': 'stop', 'inspect': 'inspect'}

def bound_runtime_example_f(request):
    raise RuntimeError('Synthetic fixture runtime is supplied by the authorized probe')


def bound_evidence_example_f(request):
    return {'goal': 'resolve an ambiguous request', 'evidence': request.get('evidence', ['supplied evidence'])}


def bound_baseline_action_example_f(request):
    return 'continue'


def bound_registry_example_f(request):
    return dict(OPTIONS)


def bound_gate_example_f(request, action):
    return HostGate(tuple(OPTIONS) + ('first','second'), hard_block=STATE['hard_block'], approval_required=action in ('alt','merge'), approval_granted=STATE['approval'])


def bound_validate_example_f(request, action):
    return request.get('valid', True) is True and STATE['valid'] is True


def bound_blocked_example_f(request, action):
    STATE['blocked'] += 1
    return 'blocked'


def bound_guard_example_f(request):
    return LOCK


def bound_attempt_example_f(request):
    return STATE['step']


def legacy_dispatch_example_f(request):
    return 'continue'


def select_boundary_example_f(payload):
    """Reviewed finite decision boundary, not generative replacement source."""
    # Retain this unrelated café comment.
    return legacy_dispatch_example_f(payload)


def public_entry_example_f(request):
    while STATE['step'] < 3:
        transition = select_boundary_example_f(request)
        if transition != 'continue': return transition
        perform_primary_example_f(request)
        STATE['step'] += 1
    return 'stop'

