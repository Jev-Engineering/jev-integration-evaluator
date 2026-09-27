# -*- coding: utf-8 -*-
"""Synthetic café host; no live model, service or database."""
from __future__ import annotations
from threading import RLock
from jev_integration_evaluator.runtime import HostGate
LOCK = RLock()
STATE = {'effects': [], 'kept': [], 'blocked': 0, 'step': 0, 'retries': 0, 'completed': False, 'idempotent': True, 'approval': True, 'remaining': 10, 'scope': True, 'ineffective': False, 'records': 0, 'checks': True, 'revision': 0, 'compactions': 0, 'owner_allowed': True, 'child_valid': True, 'hard_block': False, 'valid': True}
RECORDS = [{'id': 'hit', 'text': 'relevant claim', 'provenance': 'source:one'}, {'id': 'counter', 'text': 'contradictory evidence', 'provenance': 'source:two', 'contradictory': True}, {'id': 'maybe', 'text': 'uncertain evidence', 'provenance': 'source:three', 'uncertain': True}, {'id': 'noise', 'text': 'unrelated background', 'provenance': 'source:four'}]

def perform_primary_example_d(request):
    STATE['effects'].append('first')
    return 'first'


def perform_alternative_example_d(request):
    STATE['effects'].append('second')
    return 'second'

OPTIONS = {'all': ['hit', 'counter', 'maybe', 'noise'], 'focused': ['hit']}

def bound_runtime_example_d(request):
    raise RuntimeError('Synthetic fixture runtime is supplied by the authorized probe')


def bound_evidence_example_d(request):
    return {'goal': 'resolve an ambiguous request', 'evidence': request.get('evidence', ['supplied evidence'])}


def bound_baseline_action_example_d(request):
    return 'all'


def bound_registry_example_d(request):
    return dict(OPTIONS)


def bound_gate_example_d(request, action):
    return HostGate(tuple(OPTIONS) + ('first','second'), hard_block=STATE['hard_block'], approval_required=action in ('alt','merge'), approval_granted=STATE['approval'])


def bound_validate_example_d(request, action):
    return request.get('valid', True) is True and STATE['valid'] is True


def bound_blocked_example_d(request, action):
    STATE['blocked'] += 1
    return 'blocked'


def bound_guard_example_d(request):
    return LOCK


def bound_items_example_d(request):
    return RECORDS


def bound_generate_example_d(request, action):
    STATE['kept'] = [item['id'] for item in action]
    STATE['effects'].append('generate')
    return STATE['kept'][:]


def legacy_dispatch_example_d(request):
    return bound_generate_example_d(request, RECORDS)


def select_boundary_example_d(payload):
    """Reviewed finite decision boundary, not generative replacement source."""
    # Retain this unrelated café comment.
    return legacy_dispatch_example_d(payload)


def public_entry_example_d(request):
    return select_boundary_example_d(request)

