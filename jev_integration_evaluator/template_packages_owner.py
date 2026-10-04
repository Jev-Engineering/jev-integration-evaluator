"""Finite source-owned console composition of two separately installed packages.

Planning never imports a target. Signed runtime/launch scope and actual installed
owner provenance are separate from this source transaction and its byte hashes.
"""
from __future__ import annotations

import ast
import os
import stat
from pathlib import Path

from .contracts import validate_contract
from .implementation import make_patch_plan
from .io import InputError, digest, file_hash, read_json, safe_child
from .template_connected_generation import _literal_spec
from .template_connected_packages_binding import derive_installed_packages_binding


PROFILE = 'registered-alpha-queue-pair-v1'
OWNER_FILE = 'src/registered_packages/console.py'
SOURCES = {
    'src/registered_alpha/host.py': ('registered_alpha.host', 'public_entry', 'task_id'),
    'src/work_queue/engine.py': ('work_queue.engine', 'handle_job', 'job_id'),
}

RUNTIME_BINDINGS = {'src/registered_alpha/host.py': 'host_runtime',
                    'src/work_queue/engine.py': 'runtime_for_job'}


class PackagesOwnerError(InputError):
    """Bounded refusal for an unsupported or changed owner contract."""


def _bounded_source_operation(function):
    from functools import wraps
    @wraps(function)
    def bounded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except PackagesOwnerError:
            raise
        except (OSError, ValueError, TypeError, KeyError):
            raise PackagesOwnerError('packages_owner_source_unavailable') from None
    return bounded


def _group(packages: list[dict], source_root: str) -> tuple[dict, dict]:
    binding = derive_installed_packages_binding(packages, source_root=source_root)
    if {member['source_file'] for member in binding['members'].values()} != set(SOURCES):
        raise PackagesOwnerError('packages_owner_source_profile_unsupported')
    specs = {}
    for candidate, member in binding['members'].items():
        spec = _literal_spec(Path(member['origins']['adapter']['path']))
        _, public_entry, task_field = SOURCES[member['source_file']]
        package = next(item for item in packages if item['package_plan']['plan_sha256'] == member['package_plan_sha256'])
        bound_spec = read_json(Path(package['package_plan']['request']['implementation_bundle']) / 'implementation-spec.json')
        if (spec.get('candidate_id') != candidate
                or spec.get('recipe', {}).get('id') != 'python.C'
                or spec.get('source', {}).get('file') != member['source_file']
                or spec['source'].get('file_sha256') != member['reviewed_file_sha256']
                or spec.get('runtime', {}).get('task_field') != task_field
                or bound_spec.get('entrypoint_binding', {}).get('task_symbol') != public_entry
                or bound_spec.get('bindings', {}).get('runtime') != RUNTIME_BINDINGS[member['source_file']]
                or any(spec.get(field) != bound_spec.get(field) for field in (
                    'source', 'recipe', 'questions', 'primary_question', 'evidence_question', 'label_actions', 'runtime'))):
            raise PackagesOwnerError('packages_owner_member_contract_changed')
        specs[candidate] = spec
    return binding, specs


def _owner_source(root: Path, *, source_bytes: bytes | None = None) -> tuple[bytes, ast.Return, str]:
    """One fixed normal command; no target configuration or module is loaded."""
    path = safe_child(root, OWNER_FILE)
    try:
        raw = path.read_bytes() if source_bytes is None else source_bytes
        if len(raw) > 65536 or b'\r' in raw:
            raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        tree = ast.parse(raw, filename='<registered-packages-owner>')
        mains = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == 'main']
        if len(mains) != 1:
            raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        main = mains[0]
        statements = main.body
        if (main.decorator_list or main.args.args or main.args.posonlyargs
                or main.args.kwonlyargs or main.args.vararg or main.args.kwarg
                or len(statements) != 2):
            raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        factory, returned = statements
        if (not isinstance(factory, ast.Assign) or len(factory.targets) != 1
                or not isinstance(factory.targets[0], ast.Name)
                or not isinstance(factory.value, ast.Call)
                or not isinstance(factory.value.func, ast.Name)
                or factory.value.args or factory.value.keywords
                or not isinstance(returned, ast.Return)
                or not isinstance(returned.value, ast.Call)
                or not isinstance(returned.value.func, ast.Name)
                or returned.value.func.id != 'baseline_packages_owner'
                or returned.value.keywords or len(returned.value.args) != 2
                or not isinstance(returned.value.args[0], ast.Name)
                or returned.value.args[0].id != factory.targets[0].id
                or not isinstance(returned.value.args[1], ast.Name)
                or returned.value.args[1].id != '__file__'):
            raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        factories = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == factory.value.func.id and node.name != 'main']
        if len(factories) != 1:
            raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        source_factory = factories[0]
        if (source_factory.name.startswith('__') or source_factory.args.args or source_factory.args.posonlyargs or source_factory.args.kwonlyargs
                or source_factory.args.vararg or source_factory.args.kwarg
                or len(source_factory.body) != 1 or not isinstance(source_factory.body[0], ast.Return)):
            raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        try:
            source_request = ast.literal_eval(source_factory.body[0].value)
        except (ValueError, TypeError):
            raise PackagesOwnerError('packages_owner_source_shape_unsupported') from None
        if (type(source_request) is not dict or type(source_request.get('task_id')) is not str
                or not source_request['task_id'] or source_request.get('job_id') != source_request['task_id']):
            raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        if (set(source_request) != {'task_id', 'job_id', 'alpha_request', 'queue_request'}
                or type(source_request['alpha_request']) is not dict
                or type(source_request['queue_request']) is not dict
                or set(source_request['alpha_request']) != {'task_id', 'item', 'intent', 'permit', 'approved'}
                or set(source_request['queue_request']) != {'job_id', 'item', 'intent', 'allowed', 'complete_allowed'}
                or source_request['alpha_request']['task_id'] != source_request['task_id']
                or source_request['queue_request']['job_id'] != source_request['task_id']):
            raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
                   and node.module == 'jev_integration_evaluator.template_packages_runtime'
                   and node.level == 0]
        if (len(imports) != 1
                or {alias.name for alias in imports[0].names} != {
                    'baseline_packages_owner', 'connected_packages_owner'}
                or any(alias.asname is not None for alias in imports[0].names)):
            raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        # The finite owner has declarations only; no import-time execution,
        # wildcard imports, indirect namespace mutation or helper rebinding.
        protected = {'baseline_packages_owner', 'connected_packages_owner', '__file__'}
        entry_names = {'main', source_factory.name}
        allowed_imports = {'__future__', 'os', 'pathlib', 'json', 'hashlib'}
        for statement in tree.body:
            if isinstance(statement, ast.FunctionDef):
                annotations = [statement.returns, *(arg.annotation for arg in
                    (*statement.args.args, *statement.args.posonlyargs, *statement.args.kwonlyargs))]
                if (statement not in (main, source_factory) or statement.decorator_list or statement.name in protected
                        or statement.args.defaults or any(value is not None for value in statement.args.kw_defaults)
                        or any(annotation is not None and not (isinstance(annotation, ast.Name)
                               and annotation.id in {'dict', 'int', 'str', 'bool'})
                               for annotation in annotations)):
                    raise PackagesOwnerError('packages_owner_source_shape_unsupported')
            elif isinstance(statement, ast.ImportFrom):
                if statement not in imports and (statement.level or statement.module not in allowed_imports):
                    raise PackagesOwnerError('packages_owner_source_shape_unsupported')
            elif isinstance(statement, ast.Import):
                if any(alias.name not in allowed_imports for alias in statement.names):
                    raise PackagesOwnerError('packages_owner_source_shape_unsupported')
            elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
                pass
            else:
                raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        for node in ast.walk(tree):
            bound = None
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                bound = node.id
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound = node.name
            elif isinstance(node, ast.arg):
                bound = node.arg
            elif isinstance(node, ast.ExceptHandler):
                bound = node.name
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
                bound = node.name
            elif isinstance(node, ast.MatchMapping):
                bound = node.rest
            if bound in protected or (bound in entry_names and node not in (main, source_factory)):
                raise PackagesOwnerError('packages_owner_source_shape_unsupported')
            if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in imports:
                if any(alias.name == '*' or alias.name.startswith('__')
                       or (alias.asname or alias.name.split('.')[0]).startswith('__')
                       or (alias.asname or alias.name.split('.')[0]) in protected | entry_names
                       for alias in node.names):
                    raise PackagesOwnerError('packages_owner_source_shape_unsupported')
            if isinstance(node, (ast.Global, ast.Nonlocal)) and protected.intersection(node.names):
                raise PackagesOwnerError('packages_owner_source_shape_unsupported')
            if isinstance(node, ast.Name) and node.id in {
                    'globals', 'locals', 'vars', 'eval', 'exec', '__import__', 'setattr', 'delattr'}:
                raise PackagesOwnerError('packages_owner_source_shape_unsupported')
            if isinstance(node, ast.Attribute) and node.attr.startswith('__'):
                raise PackagesOwnerError('packages_owner_source_shape_unsupported')
        return raw, returned, factory.targets[0].id
    except PackagesOwnerError:
        raise
    except (OSError, SyntaxError, ValueError, TypeError):
        raise PackagesOwnerError('packages_owner_source_unavailable') from None


def _owner_scope(owner_root: str, source_root: str) -> Path:
    """Retain the exact canonical private paths before following source children."""
    original_root, original_common = Path(owner_root), Path(source_root)
    for original in (original_root, original_common):
        if (not original.is_absolute()
                or any(part.is_symlink() for part in (original, *original.parents))):
            raise PackagesOwnerError('packages_owner_private_scope_required')
    root, common = original_root.resolve(strict=True), original_common.resolve(strict=True)
    if (str(root) != owner_root or str(common) != source_root
            or root == common or not root.is_relative_to(common)):
        raise PackagesOwnerError('packages_owner_private_scope_required')
    for current in (root, common):
        info = current.stat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise PackagesOwnerError('packages_owner_private_scope_required')
    return root


def _plan_packages_owner(owner_root: str, packages: list[dict], *, source_root: str,
                        trusted_binding_sha256: str) -> dict:
    """Render a finite normal-console startup; this grants no source execution."""
    root = _owner_scope(owner_root, source_root)
    binding, specs = _group(packages, source_root)
    if binding['binding_sha256'] != trusted_binding_sha256:
        raise PackagesOwnerError('packages_owner_exact_binding_required')
    raw, returned, request = _owner_source(root)
    lines = raw.splitlines(keepends=True)
    start = sum(map(len, lines[:returned.lineno - 1])) + returned.col_offset
    end = sum(map(len, lines[:returned.end_lineno - 1])) + returned.end_col_offset
    replacement = f'return connected_packages_owner({request}, __file__)'.encode('utf-8')
    rendered = raw[:start] + replacement + raw[end:]
    patch = make_patch_plan(root, [{'file': OWNER_FILE,
                                    'new_content': rendered.decode('utf-8')}],
                            binding['candidate_ids'])
    result = {'schema_version': '1.0', 'kind': 'packages-owner-source-plan-v1',
              'profile': PROFILE, 'owner_root': str(root), 'owner_file': OWNER_FILE,
              'owner_project_sha256': file_hash(root / 'pyproject.toml'),
              'binding': binding, 'trusted_binding_sha256': trusted_binding_sha256,
              'packages': packages, 'adapter_specs_sha256': {
                  name: digest(spec) for name, spec in sorted(specs.items())},
              'source_preimage': raw.decode('utf-8'),
              'source_mode': stat.S_IMODE(safe_child(root, OWNER_FILE).stat().st_mode),
              'patch_plan': patch}
    result['plan_sha256'] = digest(result)
    validate_contract(result, 'packages-owner-source-plan-v1')
    return result


def plan_packages_owner(owner_root: str, packages: list[dict], *, source_root: str,
                        trusted_binding_sha256: str) -> dict:
    """Public source planner with bounded, content-free filesystem refusals."""
    try:
        return _plan_packages_owner(owner_root, packages, source_root=source_root,
                                    trusted_binding_sha256=trusted_binding_sha256)
    except PackagesOwnerError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise PackagesOwnerError('packages_owner_source_unavailable') from None


def _source_current(plan: dict, *, applied: bool) -> None:
    from .contracts import verify
    import stat
    verify(plan, 'plan_sha256')
    validate_contract(plan, 'packages-owner-source-plan-v1')
    from .io import digest as content_digest
    import hashlib
    root = _owner_scope(plan['owner_root'], plan['binding']['site'])
    raw, returned, request = _owner_source(root,
                                          source_bytes=plan['source_preimage'].encode('utf-8'))
    lines = raw.splitlines(keepends=True)
    start = sum(map(len, lines[:returned.lineno - 1])) + returned.col_offset
    end = sum(map(len, lines[:returned.end_lineno - 1])) + returned.end_col_offset
    rendered = raw[:start] + f'return connected_packages_owner({request}, __file__)'.encode() + raw[end:]
    patch = plan['patch_plan']
    verify(patch, 'plan_digest')
    if (patch['repository_identity'] != content_digest(plan['owner_root'])
            or patch['candidate_ids'] != plan['binding']['candidate_ids']
            or len(patch['changes']) != 1 or patch['changes'][0]['file'] != OWNER_FILE
            or patch['changes'][0]['operation'] != 'update'
            or patch['changes'][0]['old_sha256'] != hashlib.sha256(raw).hexdigest()
            or patch['changes'][0]['new_content'] != rendered.decode()
            or patch['changes'][0]['new_sha256'] != hashlib.sha256(rendered).hexdigest()):
        raise PackagesOwnerError('packages_owner_rendered_contract_changed')
    if file_hash(root / 'pyproject.toml') != plan['owner_project_sha256']:
        raise PackagesOwnerError('packages_owner_project_changed')
    path = safe_child(root, OWNER_FILE)
    info = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != plan['source_mode']):
        raise PackagesOwnerError('packages_owner_source_identity_changed')
    change = plan['patch_plan']['changes'][0]
    if file_hash(path) != change['new_sha256' if applied else 'old_sha256']:
        raise PackagesOwnerError('packages_owner_source_changed')
    binding, specs = _group(plan['packages'], plan['binding']['site'])
    if (binding != plan['binding'] or {name: digest(spec) for name, spec in sorted(specs.items())}
            != plan['adapter_specs_sha256']):
        raise PackagesOwnerError('packages_owner_member_changed')


@_bounded_source_operation
def apply_packages_owner(plan: dict, transaction_directory: str, *,
                         approved_plan_sha256: str) -> dict:
    """Apply exactly one reviewed console transaction, never execute a target."""
    from .contracts import seal
    from .implementation import apply_patch_plan
    from .io import write_json
    from .template_installation import _effect_lock
    from .template_delivery import _safe_directory, _private
    if approved_plan_sha256 != plan.get('plan_sha256'):
        raise PackagesOwnerError('packages_owner_exact_source_authority_required')
    target = _safe_directory(transaction_directory, exists=False)
    _private(target.parent)
    if target.is_relative_to(Path(plan['owner_root'])):
        raise PackagesOwnerError('packages_owner_transaction_external_required')
    with _effect_lock(target.parent, 'owner-source-' + plan['plan_sha256'][:24]):
        _source_current(plan, applied=False)
        target.mkdir(mode=0o700)
        write_json(target / 'plan.json', plan)
        write_json(target / 'intent.json', {'plan_sha256': plan['plan_sha256'], 'action': 'apply'})
        apply_patch_plan(plan['owner_root'], plan['patch_plan'], plan['patch_plan']['plan_digest'])
        _source_current(plan, applied=True)
        receipt = seal({'schema_version': '1.0', 'kind': 'packages-owner-source-receipt-v1',
                        'plan_sha256': plan['plan_sha256'], 'transaction_directory': str(target),
                        'action': 'applied', 'owner_file_sha256': plan['patch_plan']['changes'][0]['new_sha256'],
                        'target_executed': False}, 'receipt_sha256')
        validate_contract(receipt, receipt['kind'])
        write_json(target / 'receipt.json', receipt)
        return receipt


@_bounded_source_operation
def packages_owner_source_status(plan: dict, receipt: dict, *, trusted_receipt_sha256: str) -> dict:
    """Recheck an externally anchored source transaction, without replaying it."""
    from .contracts import verify
    from .io import read_json
    verify(receipt, 'receipt_sha256', trusted_receipt_sha256)
    validate_contract(receipt, 'packages-owner-source-receipt-v1')
    from .template_delivery import _safe_directory, _private
    target = _safe_directory(receipt['transaction_directory'], exists=True)
    _private(target)
    if (receipt['owner_file_sha256'] != plan['patch_plan']['changes'][0]['new_sha256']
            or receipt['action'] != 'applied' or receipt['plan_sha256'] != plan['plan_sha256']
            or read_json(target / 'plan.json') != plan
            or read_json(target / 'receipt.json') != receipt
            or (target / 'rollback-intent.json').exists()):
        raise PackagesOwnerError('packages_owner_transaction_changed')
    _source_current(plan, applied=True)
    return {'status': 'applied_externally_anchored', 'target_executed': False}


@_bounded_source_operation
def rollback_packages_owner(plan: dict, receipt: dict, *, trusted_receipt_sha256: str,
                            approved_plan_sha256: str) -> dict:
    """Restore the exact preimage only while the owned source is unchanged."""
    from .contracts import seal
    from .io import atomic_text, write_json
    from .template_installation import _effect_lock
    if approved_plan_sha256 != plan.get('plan_sha256'):
        raise PackagesOwnerError('packages_owner_exact_source_authority_required')
    target = Path(receipt['transaction_directory'])
    with _effect_lock(target.parent, 'owner-source-' + plan['plan_sha256'][:24]):
        packages_owner_source_status(plan, receipt, trusted_receipt_sha256=trusted_receipt_sha256)
        write_json(target / 'rollback-intent.json', {'plan_sha256': plan['plan_sha256'], 'action': 'rollback'})
        root = _owner_scope(plan['owner_root'], plan['binding']['site'])
        atomic_text(safe_child(root, OWNER_FILE), plan['source_preimage'])
        _source_current(plan, applied=False)
        result = seal({'schema_version': '1.0', 'kind': 'packages-owner-source-receipt-v1',
                       'plan_sha256': plan['plan_sha256'], 'transaction_directory': str(target),
                       'action': 'rolled_back', 'owner_file_sha256': plan['patch_plan']['changes'][0]['old_sha256'],
                       'target_executed': False}, 'receipt_sha256')
        validate_contract(result, result['kind'])
        write_json(target / 'rollback-receipt.json', result)
        return result
