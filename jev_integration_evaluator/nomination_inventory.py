"""Source-anchored nominations using the existing candidate/review constructors.

No target import, Git hook, TypeScript plugin, implementation, or provider runs.
This bridge does not accept caller-authored inventories. It re-reads the bounded
snapshot and rebuilds the legacy inventory from actual Python AST facts. The
separate capability report remains authoritative about parser/shape coverage.
"""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import replace
import hashlib
import os
from pathlib import Path
from typing import Any

from . import capabilities as cap
from .config import DEFAULT, validate_config
from .contracts import validate_contract
from .io import InputError, canonical, digest
from .lifecycle import analysis_identity
from .scanner import _python, _patterns, build_architecture, discover, detect_interactions
from .scoring import apply_reviews, score_candidate

CONTRACT = 'repository-nominated-inventory-v1'
VERSION = '1.0'
MAX_NOMINATIONS = 32
# Legacy architecture traversal is quadratic in symbols. Bound its whole input,
# not merely each source file. This does not alter the existing scanner limits.
MAX_INVENTORY_SYMBOLS = 512
MAX_INVENTORY_CALLS = 4096
MAX_RECORD_BYTES = 16_000_000
REVIEW_KEYS = {'source_sha256', 'reviewer', 'reason', 'approved',
               'deterministic_alternative', 'hard_real_time'}


def _bounded_json(value: Any) -> None:
    try:
        encoded = canonical(value)
    except (TypeError, ValueError, RecursionError):
        raise cap.CapabilityError('invalid_inventory_bridge_json') from None
    if len(encoded) > MAX_RECORD_BYTES:
        raise cap.CapabilityError('inventory_bridge_byte_bound')


def _engine_identity() -> str:
    """Bind the bridge and the unchanged constructors it actually delegates to."""
    package = Path(__file__).parent
    modules = ('nomination_inventory', 'scanner', 'scoring', 'lifecycle',
               'config', 'patterns', 'contracts', 'io', '__init__')
    schemas = (CONTRACT, 'repository-semantic-review-v1', 'repository-reviewed-inventory-v1')
    return digest({
        'modules': {name: hashlib.sha256((package / (name + '.py')).read_bytes()).hexdigest()
                    for name in modules},
        'schemas': {name: hashlib.sha256((package / 'data' / (name + '.schema.json')).read_bytes()).hexdigest()
                    for name in schemas},
    })


def _settings(cfg: dict, policy: cap.DiscoveryPolicy | None) -> tuple[dict, cap.DiscoveryPolicy]:
    _bounded_json(cfg)
    settings = copy.deepcopy(cfg)
    try:
        if not isinstance(settings, dict) or set(settings) != set(DEFAULT):
            raise InputError('Unknown or missing configuration keys')
        for section, default in DEFAULT.items():
            if isinstance(default, dict) and (not isinstance(settings[section], dict)
                    or set(settings[section]) != set(default)):
                raise InputError('Unknown or missing configuration keys')
        validate_config(settings)
    except (InputError, KeyError, TypeError, ValueError):
        raise cap.CapabilityError('invalid_evaluator_configuration') from None
    ceiling = min(settings['repository']['max_files'],
                  500 if settings['depth'] == 'QUICK' else settings['repository']['max_files'])
    if policy is None:
        defaults = cap.DiscoveryPolicy()
        policy = replace(defaults, max_files=min(defaults.max_files, ceiling),
                         max_file_bytes=min(defaults.max_file_bytes, settings['repository']['max_file_bytes']))
    if not isinstance(policy, cap.DiscoveryPolicy):
        raise cap.CapabilityError('invalid_discovery_policy')
    # Do not silently change an explicitly supplied bound. Computed defaults
    # are recorded by discovery; a changed bound requires a new report.
    if policy.max_files > ceiling or policy.max_file_bytes > settings['repository']['max_file_bytes']:
        raise cap.CapabilityError('capability_bounds_exceed_evaluator_configuration')
    combined = [*settings['repository']['exclude'], *policy.exclude]
    return settings, replace(policy, exclude=tuple(sorted(set(combined))))



def discover_repository_capabilities(repo: str | Path, cfg: dict, *,
                                     policy: cap.DiscoveryPolicy | None = None) -> dict:
    """Read-only discovery with the evaluator's restrictive configuration applied."""
    _, policy = _settings(cfg, policy)
    return cap.discover_repository(repo, policy)


def _facts(repo: str | Path, report: dict, policy: cap.DiscoveryPolicy) -> tuple[list[dict], list[dict], list[dict]]:
    """Read exact hashes through the no-follow backend; reuse actual AST parsing."""
    root, fd, root_stat = cap._secure_discovery_root(repo)
    functions, files, configs = [], [], []
    calls = 0
    try:
        if cap._repository_identity(root, root_stat) != report['repository_identity']:
            raise cap.CapabilityError('repository_replaced')
        records = {r['file']: r for r in report['files']}
        observed = []
        notes: list[dict] = []
        for path, raw, mode in cap._walk(fd, policy, notes, Counter()):
            record = records.get(path)
            if record is None or hashlib.sha256(raw).hexdigest() != record['sha256'] or mode != record['mode']:
                raise cap.CapabilityError('source_changed_during_inventory_preparation')
            observed.append(path)
            if record['configuration_sighting']:
                configs.append({'file': path, 'sha256': record['sha256'], 'markers': []})
            if record['language'] == 'configuration':
                continue
            parsed, imports = [], []
            if record['parser'] == 'python_ast':
                text = raw.decode('utf-8')
                try:
                    parsed, imports, _ = _python(text, path)
                except (SyntaxError, ValueError, RecursionError, MemoryError):
                    raise cap.CapabilityError('python_parser_unavailable_for_inventory') from None
                counts = Counter(f['symbol'] for f in parsed)
                ordinals: Counter = Counter()
                for f in parsed:
                    original = f['symbol']
                    if counts[original] > 1:
                        ordinals[original] += 1
                        f['symbol'] = original + '#definition-' + str(ordinals[original])
                    snippet = '\n'.join(text.splitlines()[f['start_line'] - 1:f['end_line']])
                    f.update({'file': path, 'language': 'python', 'file_sha256': record['sha256'],
                              'source_sha256': hashlib.sha256(snippet.encode('utf-8')).hexdigest(),
                              'node_id': path + '::' + f['symbol'], 'imports': imports,
                              'is_test': any((p.casefold().startswith('test') if os.name == 'nt' else p.startswith('test'))
                                             or (p.casefold() in ('tests', '__tests__') if os.name == 'nt' else p in ('tests', '__tests__'))
                                             for p in Path(path).parts) or '.test.' in path or '.spec.' in path})
                    f['patterns'], f['roles'], f['discovery_note'] = _patterns(f)
                    calls += len(f['calls'])
                if len(functions) + len(parsed) > MAX_INVENTORY_SYMBOLS or calls > MAX_INVENTORY_CALLS:
                    raise cap.CapabilityError('inventory_architecture_bound')
                functions.extend(parsed)
            # Non-Python/failed-parser files retain their complete file hashes.
            # They are not promoted to AST coverage or useful-placement absence.
            files.append({'file': path, 'sha256': record['sha256'],
                          'language': record['language'],
                          'parser': record['parser'],
                          'symbols': len(parsed), 'imports': imports})
        if observed != list(records) or any(n['reason'] == 'source_changed_during_read' for n in notes):
            raise cap.CapabilityError('source_changed_during_inventory_preparation')
        _, check_fd, current = cap._secure_discovery_root(root)
        cap._close_directory(check_fd)
        if cap._repository_identity(root, current) != cap._repository_identity(root, root_stat):
            raise cap.CapabilityError('repository_replaced')
        return functions, files, configs
    finally:
        cap._close_directory(fd)


def prepare_nominated_inventory(repo: str | Path, report: dict, nominations: list[dict],
                                cfg: dict, *, policy: cap.DiscoveryPolicy | None = None) -> dict:
    """Prepare a real legacy inventory without approving, mutating, or executing.

    The report and nominations are data. Separately supplied constraints are
    re-applied; a caller cannot replace them by editing a report or proposal.
    This API deliberately does not run Git metadata or trusted TypeScript tools.
    """
    _bounded_json(report)
    _bounded_json(nominations)
    if not isinstance(nominations, list) or len(nominations) > MAX_NOMINATIONS:
        raise cap.CapabilityError('invalid_nomination_schedule')
    settings, policy = _settings(cfg, policy)
    engine = _engine_identity()
    fresh = cap.discover_repository(repo, policy)
    if cap._json(fresh) != cap._json(report):
        raise cap.CapabilityError('stale_or_tampered_capability_report')
    admissions, seen = [], set()
    for nomination in nominations:
        admission = cap.admit_nomination(repo, nomination,
                                         expected_report_sha256=fresh['report_sha256'], policy=policy)
        key = (nomination['seam_id'], admission['pattern'])
        if key in seen:
            raise cap.CapabilityError('duplicate_nominated_placement')
        seen.add(key)
        admissions.append(copy.deepcopy(admission))
    functions, files, configs = _facts(repo, fresh, policy)
    architecture = build_architecture(functions)
    candidates = []
    withheld = []
    for candidate in discover(functions, architecture, settings):
        source = candidate['source']
        matches = [s for s in fresh['seams'] if
                   (s['source']['file'], s['source']['start_line'], s['source']['end_line']) ==
                   (source['file'], source['start_line'], source['end_line'])]
        # The older scanner can manufacture module pseudo-symbols or recover
        # symbols outside the capability budget. They are not admitted seams.
        if len(matches) != 1 or 'ambiguous_symbol' in matches[0]['reasons']:
            withheld.append({'candidate_id': candidate['candidate_id'],
                             'reason': 'missing_or_ambiguous_capability_seam'})
            continue
        seam = matches[0]
        if seam['eligibility'] == 'ineligible':
            if 'hard_real_time_exclusion' in seam['reasons']:
                candidate['hard_real_time'] = True
            elif 'deterministic_operation_shape' in seam['reasons']:
                candidate['deterministic_alternative'] = 'mandatory'
            else:
                raise cap.CapabilityError('unrecognized_capability_exclusion')
            score_candidate(candidate, settings)
        candidate['evidence'].append({
            'id': candidate['candidate_id'] + ':capability', 'kind': 'source_capability_v1',
            'report_sha256': fresh['report_sha256'], 'source': copy.deepcopy(seam['source']),
            'eligibility': seam['eligibility'], 'reasons': list(seam['reasons']),
            'shape': seam['shape'], 'execution_qualified': False,
        })
        candidates.append(candidate)
    by_id = {c['candidate_id']: c for c in candidates}
    if len(by_id) != len(candidates):
        raise cap.CapabilityError('ambiguous_candidate_identity')
    for nomination, admission in zip(nominations, admissions):
        anchor = nomination['source']
        matches = [f for f in functions if f['file'] == anchor['file'] and f['symbol'] == anchor['qualified_symbol']]
        if len(matches) != 1:
            raise cap.CapabilityError('unknown_or_ambiguous_inventory_anchor')
        source = matches[0]
        if source['is_test']:
            raise cap.CapabilityError('test_source_not_an_implementation_candidate')
        previous = [c for c in candidates if c['source']['file'] == anchor['file']
                    and c['source']['symbol'] == anchor['qualified_symbol']]
        if 'NONE' in source['patterns'] or any(c['tier'] == 0 or c.get('hard_real_time') is True
                or c['deterministic_alternative'] in ('mandatory', 'preferred') for c in previous):
            raise cap.CapabilityError('legacy_deterministic_or_real_time_exclusion')
        hypothesis = copy.deepcopy(source)
        hypothesis['patterns'] = [nomination['pattern']]
        hypothesis['discovery_note'] = 'Source-anchored nomination: semantic suitability requires source-matched review.'
        candidate = discover([hypothesis, *[f for f in functions if f['is_test']]], architecture, settings)[0]
        candidate['evidence_status'] = 'review_required'
        # Retain deterministic rejection computed by the existing constructor.
        if candidate['tier'] == 0:
            raise cap.CapabilityError('legacy_deterministic_or_real_time_exclusion')
        candidate['evidence'].append({
            'id': candidate['candidate_id'] + ':nomination', 'kind': 'source_nomination_v1',
            'nomination_sha256': admission['nomination_sha256'],
            'report_sha256': fresh['report_sha256'], 'parser_identity': fresh['parser_identity'],
            'anchor': copy.deepcopy(anchor), 'proposer': nomination['proposer'],
            'reason': nomination['rationale'], 'evidence': copy.deepcopy(nomination['evidence']),
            'semantic_approval': False, 'binding_approval': False,
            'implementation_verified': False, 'execution_authorized': False,
        })
        existing = by_id.get(candidate['candidate_id'])
        if existing is not None and (existing['source']['file'], existing['source']['symbol'], existing['pattern']) != (candidate['source']['file'], candidate['source']['symbol'], candidate['pattern']):
            raise cap.CapabilityError('ambiguous_candidate_identity')
        by_id[candidate['candidate_id']] = candidate
    candidates = sorted(by_id.values(), key=lambda c: (-c['tier'], -c['placement_score'], c['candidate_id']))
    warnings = [{'file': gap['path'], 'reason': gap['reason']} for gap in fresh['coverage']['limitations']]
    # A completed bounded scan is not a global absence proof. Preserve unknown
    # scope and the actual policy in coverage used by analysis_identity.
    coverage = {
        'languages': dict(sorted(Counter(f['language'] for f in files).items())),
        'files_analyzed': sum(f['parser'] == 'python_ast' for f in files),
        'files_considered': fresh['coverage']['files_read'],
        'symbols': len(functions),
        'truncated': any(g['reason'].endswith('_budget') for g in fresh['coverage']['limitations']),
        'analysis_complete_within_policy': fresh['coverage']['complete_within_policy'],
        'parser_counts': dict(sorted(Counter(f['parser'] for f in files).items())),
        'ignored': ([{'reason': 'capability_policy_excluded_entries', 'count': fresh['coverage']['excluded_entries']}]
                    if fresh['coverage']['excluded_entries'] else []),
        'warnings': warnings,
        'limitations': ['Only Python AST facts are admitted by this bridge.',
                        'Configuration and callback sightings are not execution or installed-environment evidence.',
                        'Nominations are source-anchored hypotheses, not semantic or binding approval.',
                        'A bounded snapshot is rechecked, not an atomic repository transaction.'],
        'nomination_bridge': {'contract': CONTRACT, 'report_sha256': fresh['report_sha256'],
                              'bridge_engine_sha256': engine, 'withheld_candidates': withheld,
                              'nomination_digests': sorted(a['nomination_sha256'] for a in admissions),
                              'parser_identity': fresh['parser_identity']},
    }
    inventory = {
        'schema_version': '1.0', 'repository_name': Path(repo).resolve().name,
        'git': {'revision': None, 'dirty': None, 'observation': 'not_performed'},
        'depth': settings['depth'], 'coverage': coverage, 'files': files,
        'configuration_evidence': configs, 'architecture': architecture,
        'candidates': candidates, 'interactions': detect_interactions(candidates),
    }
    inventory['analysis_identity'] = analysis_identity(files, configs, settings, coverage)
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    final = cap.discover_repository(repo, policy)
    if cap._json(final) != cap._json(fresh):
        raise cap.CapabilityError('source_changed_during_inventory_preparation')
    if _engine_identity() != engine:
        raise cap.CapabilityError('bridge_engine_changed_during_preparation')
    result = {
        'schema_version': VERSION, 'contract': CONTRACT,
        'report_sha256': fresh['report_sha256'],
        'bridge_engine_sha256': engine,
        'nominations': copy.deepcopy(nominations), 'admissions': admissions,
        'inventory': inventory, 'inventory_sha256': digest(inventory),
        'semantic_review': 'required', 'binding_review': 'not_performed',
        'implementation_verified': False, 'provider_execution_authorized': False,
        'mutation_authorized': False, 'runtime_activation_authorized': False,
    }
    result['prepared_sha256'] = digest(result)
    _bounded_json(result)
    validate_contract(result, result['contract'])
    return result


def review_nominated_inventory(repo: str | Path, report: dict, prepared: dict,
                               review: dict, cfg: dict, *, policy: cap.DiscoveryPolicy | None = None) -> dict:
    """Apply semantic-only decisions to fresh facts using the existing reviewer.

    Caller-owned review envelopes bind full preparation identity, not just the
    wrapper's unchanged source slice. They cannot carry measured estimates,
    dimension overrides, executable text fields, mutation authority, or a spec.
    """
    _bounded_json(prepared)
    _bounded_json(review)
    if not isinstance(prepared, dict) or not isinstance(prepared.get('nominations'), list):
        raise cap.CapabilityError('invalid_prepared_inventory')
    fresh = prepare_nominated_inventory(repo, report, prepared['nominations'], cfg, policy=policy)
    if canonical(fresh) != canonical(prepared):
        raise cap.CapabilityError('stale_or_tampered_prepared_inventory')
    if type(review) is not dict or set(review) != {'schema_version', 'prepared_sha256', 'reviews'}:
        raise cap.CapabilityError('invalid_repository_review')
    if review['schema_version'] != VERSION or review['prepared_sha256'] != fresh['prepared_sha256']:
        raise cap.CapabilityError('source_stale_repository_review')
    updates = review['reviews']
    if not isinstance(updates, dict) or len(updates) > MAX_INVENTORY_SYMBOLS:
        raise cap.CapabilityError('invalid_repository_review')
    inventory = copy.deepcopy(fresh['inventory'])
    known = {c['candidate_id']: c for c in inventory['candidates']}
    for cid, update in updates.items():
        if not isinstance(update, dict) or set(update) - REVIEW_KEYS or not {'source_sha256', 'reviewer', 'reason', 'approved'} <= set(update):
            raise cap.CapabilityError('invalid_repository_review_fields')
        if cid not in known:
            raise cap.CapabilityError('unknown_review_candidate')
        if any(type(update[key]) is not str or not update[key].strip() or len(update[key]) > maximum
               for key, maximum in (('reviewer', 256), ('reason', 2048))):
            raise cap.CapabilityError('invalid_repository_review_text')
        if type(update['approved']) is not bool:
            raise cap.CapabilityError('invalid_repository_review_approval')
        c = known[cid]
        if update['source_sha256'] != c['source']['source_sha256']:
            raise cap.CapabilityError('source_stale_repository_review')
        if 'hard_real_time' in update and update['hard_real_time'] is not True:
            raise cap.CapabilityError('review_cannot_waive_real_time_exclusion')
        if 'deterministic_alternative' in update and update['deterministic_alternative'] not in ('preferred', 'mandatory'):
            raise cap.CapabilityError('review_can_only_strengthen_deterministic_exclusion')
        rejected = c['tier'] == 0 or c['pattern'] == 'NONE' or c.get('hard_real_time') is True or c['deterministic_alternative'] in ('preferred', 'mandatory')
        if rejected and update['approved']:
            raise cap.CapabilityError('legacy_deterministic_or_real_time_exclusion')
    try:
        # All inputs have been validated before mutation of this private copy.
        apply_reviews(inventory, copy.deepcopy(updates), copy.deepcopy(cfg))
    except InputError:
        raise cap.CapabilityError('repository_semantic_review_rejected') from None
    result = {
        'schema_version': VERSION, 'contract': 'repository-reviewed-inventory-v1',
        'prepared_sha256': fresh['prepared_sha256'], 'report_sha256': fresh['report_sha256'],
        'bridge_engine_sha256': fresh['bridge_engine_sha256'],
        'review_sha256': digest(review), 'inventory': inventory,
        'inventory_sha256': digest(inventory), 'binding_review': 'not_performed',
        'implementation_verified': False, 'provider_execution_authorized': False,
        'mutation_authorized': False, 'runtime_activation_authorized': False,
    }
    result['reviewed_sha256'] = digest(result)
    _bounded_json(result)
    validate_contract(result, result['contract'])
    return result
