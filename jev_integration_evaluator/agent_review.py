"""Offline, source-bound agent drafting. Agent output is data, never authority."""
from __future__ import annotations

import ast
import copy
import hashlib
import os
from pathlib import Path
from typing import Protocol

from . import capabilities as cap
from .config import DEFAULT
from .integrations.contracts import validate_inventory, validate_spec
from .integrations.recipes import RECIPES, anchor_hash, transform
from .integrations.errors import AmbiguousBinding, MissingBinding, UnsupportedShape
from .io import InputError, digest, safe_child


class ReviewAdapter(Protocol):
    def respond(self, request: dict) -> dict: ...


class RecordedReviewAdapter:
    """A fixed response used for offline tests; no import, network or execution."""

    def __init__(self, response: dict):
        self.response = copy.deepcopy(response)

    def respond(self, request: dict) -> dict:
        return copy.deepcopy(self.response)


def retrieve_context(root: Path, inventory: dict, candidate_id: str, *,
                     related_files: tuple[dict, ...] = (),
                     capability_report: dict | None = None,
                     discovery_excludes: tuple[str, ...] | None = None,
                     max_files: int = 24, max_bytes: int = 120_000) -> dict:
    """Read only source already named by the inventory, bounded by count/bytes."""
    root = Path(root)
    candidates = [c for c in inventory.get('candidates', []) if c.get('candidate_id') == candidate_id]
    if len(candidates) != 1:
        raise InputError('Missing or ambiguous candidate')
    candidate = candidates[0]
    rows = inventory.get('files', []) + inventory.get('configuration_evidence', [])
    bridge = inventory.get('coverage', {}).get('nomination_bridge')
    if capability_report is None:
        if related_files or discovery_excludes is not None or bridge is not None:
            raise InputError('Source review requires the bound capability report')
        excludes = tuple(DEFAULT['repository']['exclude'])
        policy_binding = 'legacy_inventory_default_scope'
    else:
        if type(capability_report) is not dict or type(bridge) is not dict:
            raise InputError('Invalid capability report binding')
        try:
            cap._schema('repository-capabilities', capability_report)
            expected = capability_report['report_sha256']
            if (expected != cap._digest({k: v for k, v in capability_report.items()
                                         if k != 'report_sha256'})
                    or expected != bridge['report_sha256']):
                raise InputError('Capability report differs from reviewed inventory')
            policy = cap.DiscoveryPolicy.from_json(capability_report['policy'])
        except (cap.CapabilityError, KeyError, TypeError):
            raise InputError('Invalid capability report binding') from None
        excludes = policy.exclude
        if discovery_excludes is not None and discovery_excludes != excludes:
            raise InputError('Discovery exclusion policy mismatch')
        policy_binding = expected
    if type(excludes) is not tuple or any(type(x) is not str for x in excludes):
        raise InputError('Invalid discovery exclusion policy')
    if type(related_files) not in (tuple, list):
        raise InputError('Invalid related source allowlist')
    excluded = {'.git', '.venv', 'venv', '__pycache__', 'node_modules',
                'dist', 'build', '.next', '.tox', 'vendor', 'target'}
    extra = []
    for item in related_files:
        if (type(item) is not dict or set(item) != {'file', 'sha256', 'role'}
                or type(item['file']) is not str or type(item['sha256']) is not str
                or type(item['role']) is not str or not cap._safe_rel(item['file'])
                or item['role'] not in {'caller', 'callbacks', 'registries', 'tests', 'host_policy'}
                or any(part in excluded or part.startswith('.') for part in Path(item['file']).parts)
                or any(cap.SENSITIVE.search(part) for part in Path(item['file']).parts)
                or any(cap._matches('/'.join(Path(item['file']).parts[:i]), excludes)
                       for i in range(1, len(Path(item['file']).parts) + 1))
                or not cap.HEX.fullmatch(item['sha256'])):
            raise InputError('Invalid related source allowlist')
        extra.append(dict(file=item['file'], sha256=item['sha256'], role=item['role']))
    if len({r['file'] for r in rows + extra}) != len(rows + extra):
        raise InputError('Duplicate review context file')
    rows = rows + extra
    if len(rows) > max_files or not 1 <= max_files <= 64 or not 1 <= max_bytes <= 500_000:
        raise InputError('Review context file/byte bound exceeded')
    sources = []
    total = 0
    for row in rows:
        rel = row['file']
        if (type(rel) is not str or not cap._safe_rel(rel)
                or any(cap.SENSITIVE.search(part) for part in Path(rel).parts)
                or any(cap._matches('/'.join(Path(rel).parts[:i]), excludes)
                       for i in range(1, len(Path(rel).parts) + 1))
                or any(part in excluded or part.startswith('.') for part in Path(rel).parts)):
            raise InputError('Excluded or sensitive review context file')
        path = safe_child(root, rel)
        if not path.is_file():
            raise InputError('Source drift from reviewed inventory')
        if path.stat().st_size > max_bytes - total:
            raise InputError('Review context byte bound exceeded')
        if os.name == 'posix':
            try:
                _, parent_fd = cap._open_directory(path.parent)
                try:
                    raw, _ = cap._read_at(parent_fd, path.name, max_bytes - total)
                finally:
                    os.close(parent_fd)
            except cap.CapabilityError:
                raise InputError('Secure review source read failed') from None
        else:
            raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise InputError('Source drift from reviewed inventory')
        total += len(raw)
        if total > max_bytes:
            raise InputError('Review context byte bound exceeded')
        try:
            source = raw.decode('utf-8')
        except UnicodeDecodeError:
            raise InputError('Unsupported review source encoding') from None
        roles = [row['role']] if 'role' in row else []
        if rel == candidate['source']['file']:
            roles.append('seam')
        if rel.endswith('.py'):
            try:
                tree = ast.parse(source)
            except SyntaxError:
                raise InputError('Unsupported Python review source') from None
            symbols = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            if 'role' not in row:
                roles.append('python_source')
            if 'role' not in row and ('test' in Path(rel).parts or Path(rel).name.startswith('test_')):
                roles.append('tests')
        else:
            symbols = []
            if 'role' not in row:
                roles.append('policy_or_configuration')
        sources.append(dict(file=rel, sha256=row['sha256'], roles=roles,
                            symbols=symbols, text=source))
    if not any(x['file'] == candidate['source']['file'] for x in sources):
        raise InputError('Selected source absent from bounded review context')
    return dict(schema_version='1.0', kind='source-hashed-review-context-v1',
                inventory_sha256=digest(inventory), candidate_id=candidate_id,
                source_sha256=candidate['source']['source_sha256'],
                search_coverage=dict(included_related=len(extra),
                                     related_scope='exact_caller_owned_allowlist',
                                     discovery_excludes=list(excludes),
                                     capability_report_sha256=policy_binding),
                sources=sources)


def draft_reviewed_spec(root: Path, inventory: dict, context: dict, adapter: ReviewAdapter,
                        *, saved_answers: dict, trusted_verification: dict,
                        related_files: tuple[dict, ...] = (),
                        capability_report: dict | None = None,
                        discovery_excludes: tuple[str, ...] | None = None,
                        source_egress_grant: bool = False) -> dict:
    """Draft a spec using caller-owned policy and independent verification.

    The adapter has no authority channel. A remote adapter requires a separate
    explicit source-egress grant; callers must enforce that at their boundary.
    This function only accepts the fixed offline adapter until that boundary
    exists. No proposal may provide verification cases or an authorization.
    """
    if type(adapter) is not RecordedReviewAdapter:
        raise InputError('Unsupported review adapter: source egress boundary absent')
    if source_egress_grant:
        raise InputError('Offline review does not consume source-egress authority')
    if type(saved_answers) is not dict or type(trusted_verification) is not dict:
        raise InputError('Invalid saved answers or independent verification')
    fresh = retrieve_context(root, inventory, context['candidate_id'],
                             related_files=related_files, capability_report=capability_report,
                             discovery_excludes=discovery_excludes)
    if fresh != context:
        raise InputError('Source drift from agent review context')
    request = dict(context=copy.deepcopy(context), saved_answers=copy.deepcopy(saved_answers),
                   authority=dict(mutation=False, execution=False, egress=False,
                                  installation=False, activation=False))
    if len(cap._json(request)) > 500_000:
        raise InputError('Agent review request byte bound exceeded')
    proposal = adapter.respond(request)
    try:
        if len(cap._json(proposal)) > 500_000:
            raise InputError('Agent review response byte bound exceeded')
    except (TypeError, ValueError, RecursionError):
        raise InputError('Invalid agent review response') from None
    try:
        cap._schema('offline-agent-review-proposal-v1', proposal)
    except cap.CapabilityError:
        raise InputError('Invalid agent review proposal schema') from None
    required = {'schema_version', 'kind', 'request_sha256', 'reviewer', 'reason',
                'evidence', 'recipe_id', 'bindings', 'questions', 'primary_question',
                'evidence_question', 'label_actions', 'unresolved'}
    if type(proposal) is not dict or set(proposal) != required or proposal['schema_version'] != '1.0' \
            or proposal['kind'] != 'offline-agent-review-proposal-v1' \
            or proposal['request_sha256'] != digest(request):
        raise InputError('Invalid or stale agent review proposal')
    for key in ('reviewer', 'reason'):
        if type(proposal[key]) is not str or not 1 <= len(proposal[key]) <= 2000:
            raise InputError('Missing reviewer identity or reason')
    if type(proposal['evidence']) is not list or not proposal['evidence']:
        raise InputError('Missing source evidence references')
    allowed = {(s['file'], s['sha256']): set(s['symbols']) for s in context['sources']}
    for item in proposal['evidence']:
        if type(item) is not dict or set(item) != {'file', 'sha256', 'symbol'} \
                or type(item['file']) is not str or type(item['sha256']) is not str \
                or (item['file'], item['sha256']) not in allowed \
                or type(item['symbol']) is not str or len(item['symbol']) > 256 \
                or (item['symbol'] and item['symbol'] not in allowed[item['file'], item['sha256']]):
            raise InputError('Invalid source evidence reference')
    if type(proposal['unresolved']) is not list or any(type(x) is not str or len(x) > 128 for x in proposal['unresolved']):
        raise InputError('Invalid unresolved facts')
    candidate = next(c for c in inventory['candidates'] if c['candidate_id'] == context['candidate_id'])
    blocked_facts = set(proposal['unresolved'])
    if blocked_facts - {'ambiguous_callback', 'missing_independent_observation',
                        'unsupported_binding', 'missing_host_capability'}:
        raise InputError('Unsupported unresolved agent field')
    if blocked_facts:
        return dict(status='blocked', reasons=sorted(blocked_facts),
                    reviewer=proposal['reviewer'], context_sha256=digest(context))
    pending = []
    indispensable = {'host_policy', 'independent_verification', 'runtime_ownership'}
    pending.extend(sorted(k for k in indispensable if k not in saved_answers and
                          (k != 'independent_verification' or not trusted_verification)))
    if pending:
        return dict(status='unresolved', fields=sorted(set(pending)),
                    reviewer=proposal['reviewer'], context_sha256=digest(context))
    if type(proposal['recipe_id']) is not str:
        raise InputError('Invalid recipe ID')
    recipe = RECIPES.get(proposal['recipe_id'])
    if recipe is None:
        raise InputError('Unsupported recipe')
    if type(proposal['bindings']) is not dict or set(proposal['bindings']) != set(recipe.bindings):
        raise InputError('Missing or extra binding roles')
    host_policy = saved_answers['host_policy']
    ownership = saved_answers['runtime_ownership']
    if type(host_policy) is not dict or type(ownership) is not dict:
        raise InputError('Invalid host policy or runtime ownership')
    source = candidate['source']
    tree = ast.parse(safe_child(Path(root), source['file']).read_text(encoding='utf-8'))
    seams = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == source['symbol']]
    if len(seams) != 1 or not seams[0].body:
        raise InputError('Missing or ambiguous seam anchor')
    anchor = anchor_hash(seams[0].body[-1])
    output_module = '_jev_' + source['symbol']
    spec = dict(schema_version='1.0', candidate_id=candidate['candidate_id'],
                experiment_id=candidate['recommended_experiment']['id'],
                inventory_sha256=digest(inventory), inventory_fingerprint=inventory['scan_fingerprint'],
                source=dict(file=source['file'], symbol=source['symbol'],
                            anchor_sha256=anchor,
                            file_sha256=source['file_sha256'], source_sha256=source['source_sha256']),
                recipe=dict(id=recipe.id, version=recipe.version, shape=recipe.shape),
                bindings=copy.deepcopy(proposal['bindings']),
                binding_review=dict(approved=True, source_sha256=source['source_sha256'],
                                    pattern=recipe.id.split('.')[-1], reviewer=proposal['reviewer'],
                                    reason=proposal['reason']),
                questions=copy.deepcopy(proposal['questions']),
                primary_question=proposal['primary_question'],
                evidence_question=proposal['evidence_question'],
                label_actions=copy.deepcopy(proposal['label_actions']),
                policy=copy.deepcopy(host_policy), runtime=copy.deepcopy(ownership),
                output=dict(module=output_module,
                            permitted_edits=[source['file'], output_module + '.py'],
                            feature_flag_default=False,
                            dependencies=['jev-integration-evaluator>=1.3.0.dev1']),
                verification=copy.deepcopy(trusted_verification),
                authorization_context=dict(reference='offline reviewed specification', scopes=[],
                                           not_authority=True))
    try:
        validate_spec(spec)
        validate_inventory(Path(root), inventory, spec)
        transform(Path(root), spec)
    except AmbiguousBinding:
        raise InputError('Deterministic specification validation failed: ambiguous existing binding') from None
    except MissingBinding:
        raise InputError('Deterministic specification validation failed: missing existing binding') from None
    except UnsupportedShape:
        raise InputError('Deterministic specification validation failed: unsupported source or binding shape') from None
    except (InputError, KeyError, TypeError):
        raise InputError('Deterministic specification validation failed: invalid policy, mapping or observation') from None
    return dict(status='reviewed_specification', spec=spec,
                reviewer=proposal['reviewer'], evidence=copy.deepcopy(proposal['evidence']),
                context_sha256=digest(context), proposal_sha256=digest(proposal))
