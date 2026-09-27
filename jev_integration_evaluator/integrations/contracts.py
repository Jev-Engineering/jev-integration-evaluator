"""Strict non-executing binding validation. JSON data never becomes evaluated code."""
from __future__ import annotations

import copy
from importlib.resources import files
from pathlib import Path
import jsonschema

from ..config import load_config, validate_config
from ..io import InputError, canonical, digest, read_json, safe_child, file_hash
from ..questions import validate_questions
from ..runtime import SafeRouter


def validate_spec(spec: dict) -> dict:
    schema = read_json(Path(str(files('jev_integration_evaluator').joinpath('data/implementation-spec.schema.json'))))
    try:
        jsonschema.Draft202012Validator(schema).validate(spec)
    except jsonschema.ValidationError as exc:
        # Do not echo source, command arguments, or instance values into diagnostics.
        raise InputError('Invalid implementation specification at ' + '/'.join(map(str, exc.absolute_path))) from None
    validate_questions(spec['questions'])
    primary, evidence = spec['primary_question'], spec['evidence_question']
    if primary not in spec['questions'] or spec['questions'][primary]['type'] != 'choice':
        raise InputError('Unsupported: implementation requires an explicit primary Choice, not an inferred Score cutoff')
    if evidence is not None and (evidence not in spec['questions'] or spec['questions'][evidence]['type'] != 'noul'):
        raise InputError('Evidence role must reference an existing Noul')
    if any(q['type'] not in ('choice','noul') for q in spec['questions'].values()):
        raise InputError('Unsupported verification primitive: bounded implementation probes support Choice and Noul only')
    SafeRouter._label_translation(spec['questions'], primary, spec['label_actions'])
    if not any(v is None for v in spec['label_actions'].values()):
        raise InputError('An explicit abstention label is required')
    cfg = load_config()
    cfg['runtime'] = copy.deepcopy(spec['runtime']['configuration'])
    validate_config(cfg)
    if cfg['runtime']['mode'] != 'off':
        raise InputError('Bundled runtime configuration must be off by default')
    if spec['output']['module'] == Path(spec['source']['file']).stem:
        raise InputError('Integration module cannot replace the host module')
    if set(spec['output']['permitted_edits']) != {spec['source']['file'], spec['output']['module'] + '.py'}:
        raise InputError('Permitted edits must name exactly the host and owned adapter')
    if spec['output']['dependencies'] != ['jev-integration-evaluator>=1.3.0.dev1']:
        raise InputError('Declare the installed evaluator dependency; automatic installation is not authorized')
    pattern = spec['recipe']['id'].split('.')[-1]
    if pattern not in ('F','K','M') and not spec['verification']['effect_symbols']:
        raise InputError('Effectful recipes require independent executor/call observations')
    if pattern == 'E' and not any(r['operation']=='increased_by' and r['path'].startswith('after.') for r in spec['policy']['postconditions']):
        raise InputError('Post-action verification requires an independent state-change assertion')
    for phase in ('baseline', 'modified'):
        if any('\x00' in arg for arg in spec['verification'][phase+'_command']):
            raise InputError('Invalid verification command argument')
    identifiers = [c['id'] for c in spec['verification']['cases']]
    if len(identifiers) != len(set(identifiers)):
        raise InputError('Duplicate scheduled verification case')
    labels = spec['questions'][primary]['criteria']
    for case in spec['verification']['cases']:
        if case['assessment_label'] not in labels:
            raise InputError('Verification fixture label is not a declared Choice')
        if spec['runtime']['task_field'] not in case['request']:
            raise InputError('Every scheduled case requires a stable task identity')
        if any(name in spec['bindings'].values() or name == spec['source']['symbol'] for name in case['initial_globals']):
            raise InputError('Fixture data cannot replace callable host bindings')
    if len(canonical(spec)) > 2_000_000:
        raise InputError('Implementation specification exceeds the local byte limit')
    return copy.deepcopy(spec)


def validate_inventory(root: Path, inventory: dict, spec: dict) -> dict:
    if digest(inventory) != spec['inventory_sha256']:
        raise InputError('Reviewed inventory content changed')
    if (not inventory.get('analysis_identity') or digest(inventory['analysis_identity']) != inventory.get('scan_fingerprint')
            or inventory['scan_fingerprint'] != spec['inventory_fingerprint']):
        raise InputError('Inventory analysis fingerprint mismatch')
    candidates = [c for c in inventory.get('candidates', []) if c.get('candidate_id') == spec['candidate_id']]
    if len(candidates) != 1:
        raise InputError('Missing or ambiguous candidate')
    c = candidates[0]
    review = c.get('semantic_review', {})
    source = c.get('source', {})
    if (c.get('tier') == 0 or c.get('pattern') == 'NONE' or c.get('hard_real_time') is True
            or c.get('deterministic_alternative') in ('mandatory', 'preferred')):
        raise InputError('Candidate rejected by deterministic/real-time eligibility gates')
    if (review.get('approved') is not True or not review.get('reviewer') or not review.get('reason')
            or review.get('source_sha256') != source.get('source_sha256')):
        raise InputError('Current source-matched semantic review is required')
    br = spec['binding_review']
    if br['pattern'] != spec['recipe']['id'].split('.')[-1] or br['source_sha256'] != source.get('source_sha256'):
        raise InputError('Recipe requires an explicit source-matched binding review')
    if (source.get('file') != spec['source']['file'] or source.get('symbol') != spec['source']['symbol']
            or source.get('source_sha256') != spec['source']['source_sha256']
            or source.get('file_sha256') != spec['source']['file_sha256']
            or c.get('recommended_experiment', {}).get('id') != spec['experiment_id']):
        raise InputError('Candidate, experiment, qualified symbol, or discovery source identity mismatch')
    # Bind ALL scanned source/configuration evidence, not only the chosen call site.
    seen = {}
    for record in inventory.get('files', []) + inventory.get('configuration_evidence', []):
        rel, expected = record['file'], record['sha256']
        if rel in seen and seen[rel] != expected:
            raise InputError('Conflicting discovery hashes')
        p = safe_child(root, rel)
        if not p.is_file() or file_hash(p) != expected:
            raise InputError('Source drift from the reviewed inventory')
        seen[rel] = expected
    p = safe_child(root, spec['source']['file'])
    if not p.is_file() or file_hash(p) != spec['source']['file_sha256']:
        raise InputError('Selected source changed since review')
    return copy.deepcopy(c)
