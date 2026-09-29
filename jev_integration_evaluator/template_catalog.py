"""Packaged, source-bound template contracts. Rendering never executes target code."""
from __future__ import annotations

import copy
import os
from importlib.resources import files
from pathlib import Path

from . import __version__
from .contracts import validate_contract
from .io import InputError, digest, file_hash, read_json, write_json
from .integrations.contracts import validate_inventory, validate_spec
from .integrations.recipes import RECIPES, transform
from .integrations.lifecycle import engine_identity

TEMPLATE_ID = 'python.bounded-tail-call'
TEMPLATE_VERSION = '1.0.0'
RESOURCE = 'python-bounded-tail-call.template.json'


def template_error(exc: Exception) -> dict:
    """The same redacted, versioned rejection envelope used by the template CLI."""
    return {'schema_version': '1.0', 'status': 'rejected',
            'error': type(exc).__name__, 'message': str(exc)}


def _manifest() -> dict:
    manifest = read_json(Path(str(files('jev_integration_evaluator').joinpath('data', RESOURCE))))
    validate_contract(manifest, 'template-manifest-v1')
    if (manifest.get('schema_version') != '1.0' or manifest.get('template_id') != TEMPLATE_ID
            or manifest.get('template_version') != TEMPLATE_VERSION
            or manifest.get('evaluator_version') != __version__
            or manifest.get('recipe_versions') != {key: value.version for key, value in RECIPES.items()}):
        raise InputError('Packaged template manifest differs from supported recipe catalog')
    return manifest


def list_templates() -> dict:
    manifest = _manifest()
    return {'schema_version': '1.0', 'templates': [{
        'template_id': manifest['template_id'], 'template_version': manifest['template_version'],
        'backend': manifest['backend'], 'profile': manifest['source_grammar'],
        'manifest_sha256': digest(manifest)}]}


def inspect_template(template_id: str, version: str = TEMPLATE_VERSION) -> dict:
    manifest = _manifest()
    if template_id != TEMPLATE_ID or version != TEMPLATE_VERSION:
        raise InputError('Unsupported template ID or version; v1 refuses unknown and legacy manifests')
    return copy.deepcopy(manifest) | {'manifest_sha256': digest(manifest)}


def validate_template_request(root: str | Path, request: dict) -> dict:
    """Validate current source and all nested planner contracts before any output write."""
    validate_contract(request, 'template-request-v1')
    manifest = inspect_template(request['template_id'], request['template_version'])
    if request['backend'] != manifest['backend'] or request['profile'] != manifest['source_grammar']:
        raise InputError('Unsupported template backend or profile')
    inventory = request['reviewed_inventory']
    spec = validate_spec(request['implementation_spec'])
    if (spec['recipe']['id'] not in manifest['recipe_versions']
            or spec['recipe']['version'] != manifest['recipe_versions'][spec['recipe']['id']]
            or spec['recipe']['shape'] != manifest['source_grammar']):
        raise InputError('Unsupported template recipe version or source grammar')
    if spec['runtime']['configuration']['model'] != manifest['runtime_model']:
        raise InputError('Unsupported template runtime model pin')
    validate_contract(inventory, 'inventory')
    validate_inventory(Path(root).resolve(strict=True), inventory, spec)
    # This read-only parse/transform catches actual grammar and adapter
    # collisions before any output directory is created.
    transform(Path(root).resolve(strict=True), spec)
    return {
        'schema_version': '1.0', 'status': 'validated',
        'template_id': TEMPLATE_ID, 'template_version': TEMPLATE_VERSION,
        'manifest_sha256': manifest['manifest_sha256'], 'evaluator_version': __version__,
        'renderer_sha256': file_hash(Path(__file__)),
        'tool_sha256': engine_identity(),
        'request_sha256': digest(request), 'inventory_sha256': digest(inventory),
        'spec_sha256': digest(spec), 'source_sha256': spec['source']['source_sha256'],
        'source_file_sha256': spec['source']['file_sha256'],
        'policy_sha256': digest({'policy': spec['policy'], 'runtime': spec['runtime'],
                                 'questions': spec['questions'], 'label_actions': spec['label_actions']}),
        'candidate_id': spec['candidate_id'], 'recipe': copy.deepcopy(spec['recipe']),
        'lifecycle': copy.deepcopy(manifest['lifecycle']),
        'target_modified': False, 'target_executed': False,
    }


def prepare_template_binding(root: str | Path, request: dict, binding: dict) -> dict:
    """Derive a fresh console caller contract without editing or importing the host."""
    validate_contract(request, 'template-request-v1')
    validate_contract(binding, 'template-entrypoint-binding-v1')
    inspect_template(request['template_id'], request['template_version'])
    from .integrations.python_entrypoint import inspect_entrypoint
    target = Path(root).resolve(strict=True)
    bound = copy.deepcopy(request)
    spec = bound['implementation_spec']
    entrypoint = inspect_entrypoint(target, spec, binding)
    spec['entrypoint_binding'] = entrypoint
    if entrypoint['file'] in spec['output']['permitted_edits']:
        raise InputError('Console entrypoint is already an owned edit')
    spec['output']['permitted_edits'].append(entrypoint['file'])
    validation = validate_template_request(target, bound)
    return {'schema_version': '1.0', 'status': 'bound',
            'request': bound,
            'binding_report': {'schema_version': '1.0', 'status': 'planned_not_applied',
                               'entrypoint': entrypoint,
                               'request_sha256': digest(bound),
                               'inventory_sha256': validation['inventory_sha256'],
                               'spec_sha256': validation['spec_sha256'],
                               'source_sha256': validation['source_sha256'],
                               'target_modified': False, 'target_executed': False}}


def bind_template(root: str | Path, request: dict, binding: dict, output: str | Path) -> dict:
    """Write a reviewed binding report and derived request to a new private directory."""
    prepared = prepare_template_binding(root, request, binding)
    target = Path(root).resolve(strict=True)
    out = Path(output).absolute()
    if any(part.is_symlink() for part in (out, *out.parents)):
        raise InputError('Binding output path may not traverse symlinks')
    out = out.resolve()
    if out == target or out.is_relative_to(target):
        raise InputError('Binding output must be outside the target')
    try:
        out.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        raise InputError('Binding output already exists') from None
    os.chmod(out, 0o700)
    write_json(out / 'bind-status.json', {'schema_version': '1.0', 'status': 'incomplete'})
    write_json(out / 'template-request.json', prepared['request'])
    write_json(out / 'binding-report.json', prepared['binding_report'])
    write_json(out / 'bind-status.json', {'schema_version': '1.0', 'status': 'complete',
                                          'request_sha256': file_hash(out / 'template-request.json'),
                                          'report_sha256': file_hash(out / 'binding-report.json')})
    return prepared['binding_report'] | {'output': str(out)}


def render_status(output: str | Path) -> dict:
    """Classify incomplete output, including a crash before the first marker."""
    out = Path(output).absolute()
    if any(part.is_symlink() for part in (out, *out.parents)):
        raise InputError('Template output path may not traverse symlinks')
    if not out.exists(): state = 'absent'
    elif not out.is_dir(): state = 'invalid_output'
    elif (out / 'render-status.json').is_symlink(): state = 'invalid_marker'
    elif not (out / 'render-status.json').is_file(): state = 'incomplete_unmarked'
    else:
        try:
            marker = read_json(out / 'render-status.json', max_bytes=10_000)
            state = ('marker_complete_unverified' if marker['status'] == 'complete' else 'incomplete') if (
                type(marker) is dict and marker.get('schema_version') == '1.0'
                and marker.get('status') in ('complete', 'incomplete')) else 'invalid_marker'
        except (OSError, ValueError, KeyError, TypeError):
            state = 'invalid_marker'
    return {'schema_version': '1.0', 'status': state}


def materialize_template(root: str | Path, request: dict, output: str | Path) -> dict:
    """Create exclusive deterministic planner inputs outside the target.

    An interrupted render retains an incomplete marker and cannot be reused.
    """
    result = validate_template_request(root, request)
    target = Path(root).resolve(strict=True)
    out = Path(output).absolute()
    if any(part.is_symlink() for part in (out, *out.parents)):
        raise InputError('Template output path may not traverse symlinks')
    out = out.resolve()
    if out == target or out.is_relative_to(target):
        raise InputError('Template output must be outside the target')
    try:
        out.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        raise InputError('Template output collision: ' + render_status(out)['status']) from None
    os.chmod(out, 0o700)
    # The first durable artifact distinguishes interrupted work from success.
    write_json(out / 'render-status.json', {'schema_version': '1.0', 'status': 'incomplete',
                                            'request_sha256': result['request_sha256']})
    resources = {
        'template-manifest.json': _manifest(),
        'template-request.json': request,
        'implementation-spec.json': request['implementation_spec'],
        'reviewed-inventory.json': request['reviewed_inventory'],
    }
    for name, value in resources.items():
        write_json(out / name, value)
    resource_hashes = {name: file_hash(out / name) for name in sorted(resources)}
    lock = result | {'status': 'materialized', 'owned_resources': resource_hashes,
                     'planner': {'command': 'implement-plan',
                                 'inventory': 'reviewed-inventory.json',
                                 'spec': 'implementation-spec.json',
                                 'candidate': result['candidate_id'],
                                 'output': 'new external private bundle'}}
    lock['lock_sha256'] = digest(lock)
    validate_contract(lock, 'template-lock-v1')
    write_json(out / 'template-lock.json', lock)
    write_json(out / 'render-status.json', {'schema_version': '1.0', 'status': 'complete',
                                            'lock_sha256': lock['lock_sha256'],
                                            'resources': resource_hashes})
    return lock
