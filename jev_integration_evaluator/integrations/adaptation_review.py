"""Additive offline agent review for bounded native Python adaptation.

Agent output only proposes a shape and existing source binding. A separate
caller-owned binding review and host policy are required before preparation.
"""
from __future__ import annotations

import ast
from pathlib import Path

from ..contracts import validate_contract
from ..io import InputError, digest, file_hash, safe_child
from .adaptation_shapes import SHAPES, prepare_reviewed_shape


def _anchor(root: Path, source: dict, shape: str) -> str:
    path = safe_child(root, source['file'])
    if file_hash(path) != source['file_sha256']:
        raise InputError('Adaptation source changed after review')
    try:
        tree = ast.parse(path.read_bytes().decode('utf-8'))
    except (UnicodeError, SyntaxError):
        raise InputError('Invalid reviewed Python source') from None
    symbol = source['symbol']
    if shape == 'instance-method-tail-call-v1':
        parts = symbol.split('.')
        if len(parts) != 2:
            raise InputError('Reviewed method symbol must be qualified')
        owner = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == parts[0]]
        selected = [n for n in owner[0].body if isinstance(n, ast.FunctionDef) and n.name == parts[1]] if len(owner) == 1 else []
    else:
        selected = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == symbol]
    if len(selected) != 1 or not selected[0].body:
        raise InputError('Missing or ambiguous reviewed adaptation seam')
    return digest(ast.dump(selected[0].body[-1], annotate_fields=True, include_attributes=False))


def draft_adaptation_request(root, inventory, context, adapter, *, saved_answers,
                             trusted_binding_review, related_files=(), capability_report=None,
                             discovery_excludes=None):
    """Return a source-bound request or a blocked status; never apply or run."""
    try:
        from ..agent_review import RecordedReviewAdapter, retrieve_context
    except ImportError:
        raise InputError('Agent review dependency is not merged') from None
    if type(adapter) is not RecordedReviewAdapter:
        raise InputError('Only the fixed offline review adapter is supported')
    if type(saved_answers) is not dict or type(trusted_binding_review) is not dict:
        raise InputError('Trusted policy and binding review are required')
    fresh = retrieve_context(Path(root), inventory, context['candidate_id'],
                             related_files=related_files, capability_report=capability_report,
                             discovery_excludes=discovery_excludes)
    if fresh != context or context.get('inventory_sha256') != digest(inventory):
        raise InputError('Agent review context changed')
    for row in context.get('sources', []):
        if file_hash(safe_child(Path(root), row['file'])) != row['sha256']:
            raise InputError('Agent review source changed')
    policy = saved_answers.get('host_policy')
    if type(policy) is not dict or not policy:
        return {'status':'unresolved', 'fields':['host_policy'], 'context_sha256':digest(context)}
    request = {'context':context, 'host_policy_sha256':digest(policy),
               'authority':{'mutation':False,'execution':False,'egress':False}}
    proposal = adapter.respond(request)
    validate_contract(proposal, 'offline-adaptation-proposal-v1')
    if proposal['request_sha256'] != digest(request):
        raise InputError('Agent adaptation proposal is stale')
    if proposal['unresolved']:
        return {'status':'blocked', 'reasons':proposal['unresolved'],
                'context_sha256':digest(context)}
    candidate = [c for c in inventory['candidates'] if c['candidate_id'] == context['candidate_id']]
    if len(candidate) != 1:
        raise InputError('Missing or ambiguous reviewed candidate')
    source = candidate[0]['source']
    if context.get('source_sha256') != source['source_sha256']:
        raise InputError('Selected source identity differs from agent review context')
    reviewed_source = [row for row in context['sources'] if row['file'] == source['file']]
    if len(reviewed_source) != 1 or reviewed_source[0]['sha256'] != source['file_sha256']:
        raise InputError('Selected source differs from agent review context')
    known = {(row['file'], row['sha256']):row for row in context['sources']}
    evidence = proposal['evidence']
    if not evidence or not any(row['file'] == source['file'] and row['sha256'] == source['file_sha256']
                               and row['symbol'] == source['symbol'] for row in evidence):
        raise InputError('Agent proposal omits exact selected seam evidence')
    for row in evidence:
        observed = known.get((row['file'], row['sha256']))
        if observed is None or (row['symbol'] not in observed['symbols']
                                and not (row['file'] == source['file'] and row['symbol'] == source['symbol'])):
            raise InputError('Agent proposal references unreviewed source evidence')
    adapter_sources = [row for row in context['sources']
                       if row['file'] == proposal['adapter_file']]
    if len(adapter_sources) != 1 or proposal['adapter_file'] != proposal['adapter_name']+'.py':
        raise InputError('Agent proposal names an absent or ambiguous existing adapter')
    if proposal['shape'] not in SHAPES:
        raise InputError('Unsupported adaptation shape')
    binding = trusted_binding_review
    expected = {'approved','proposal_sha256','context_sha256','reviewer','reason',
                'source_sha256','adapter_file','adapter_sha256','host_policy_sha256'}
    if (set(binding) != expected or binding['approved'] is not True
            or binding['proposal_sha256'] != digest(proposal)
            or binding['context_sha256'] != digest(context)
            or not binding['reviewer'] or not binding['reason']
            or binding['source_sha256'] != source['source_sha256']
            or binding['adapter_file'] != proposal['adapter_file']
            or binding['adapter_sha256'] != adapter_sources[0]['sha256']
            or binding['host_policy_sha256'] != digest(policy)):
        raise InputError('Independent source-matched binding review required')
    anchor = _anchor(Path(root), source, proposal['shape'])
    selected = {'strategy':{'shape':proposal['shape'],'version':'1.0'},
                'candidate_id':context['candidate_id'],
                'inventory_sha256':digest(inventory),
                'inventory_fingerprint':inventory['scan_fingerprint'],
                'source':{'file':source['file'],'symbol':source['symbol'],
                          'source_sha256':source['source_sha256'],
                          'file_sha256':source['file_sha256'],'anchor_sha256':anchor},
                'adapter_name':proposal['adapter_name'],
                'review_context_sha256':digest(context),
                'host_policy_sha256':digest(policy),
                'trusted_binding_review_sha256':digest(binding),
                'agent_proposal_sha256':digest(proposal),
                'binding_review':{'reviewer':binding['reviewer'],'reason':binding['reason'],
                                  'source_sha256':source['source_sha256'],
                                  'adapter_file':proposal['adapter_file'],
                                  'adapter_sha256':adapter_sources[0]['sha256']}}
    prepare_reviewed_shape(Path(root), inventory, selected)
    return {'status':'reviewed_adaptation_request', 'request':selected,
            'context_sha256':digest(context), 'proposal_sha256':digest(proposal),
            'trusted_binding_review_sha256':digest(binding),
            'host_policy_sha256':digest(policy), 'target_modified':False,
            'target_executed':False}
