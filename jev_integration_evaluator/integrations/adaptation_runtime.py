"""Generated adapter runtime for reviewed Python adaptation seams.

This profile intentionally admits only off and offline synthetic shadow.  The
host supplies real policy functions and owns one lifecycle from startup to
shutdown.  No source scan imports or executes a target module.
"""
from __future__ import annotations

import asyncio
import ast
import hashlib
import importlib.metadata
from pathlib import Path
from types import ModuleType
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from ..io import InputError, digest, file_hash
from ..contracts import validate_contract
from .errors import UnsupportedShape
from .host import invoke_bound
from .runtime_lifecycle import HostRuntimeLifecycle, LifecycleError, check_dependency_plan


RUNTIME_SHAPES = frozenset({
    'instance-method-tail-call-v1', 'async-module-tail-call-v1',
    'module-fixed-positional-tail-call-v1',
})
POLICY_ROLES = frozenset({'evidence', 'baseline_action', 'registry', 'gate',
                          'validate', 'blocked', 'guard'})


def inspect_runtime_package(root: Path, *, source_file: str, adapted_source: str,
                            symbol: str, shape: str, script: str,
                            adapter_name: str = 'adapter') -> dict:
    """Bound a regular installed package's direct callers without importing it.

    The independent host review must still attest that callers outside this
    declared package do not exist. Python itself cannot prove that property.
    """
    from ..io import safe_child

    root = Path(root).resolve(strict=True)
    if shape not in RUNTIME_SHAPES or type(script) is not str or not script:
        raise InputError('Unsupported runtime adaptation package request')
    source = safe_child(root, source_file)
    package = source.parent
    if not source.is_file() or not (package / '__init__.py').is_file():
        raise UnsupportedShape('Runtime adaptation requires an existing regular package')
    if not source_file.endswith('.py') or not adapted_source:
        raise InputError('Adapted source bytes required')
    build_file = root / 'pyproject.toml'
    if (not build_file.is_file() or build_file.is_symlink()
            or build_file.stat().st_size > 1_000_000):
        raise UnsupportedShape('Package build configuration is unavailable or exceeds runtime source limit')
    try:
        ast.parse(adapted_source)
        project = tomllib.loads(build_file.read_text(encoding='utf-8'))
    except (UnicodeError, SyntaxError, OSError, ValueError):
        raise UnsupportedShape('Invalid adapted source or package declaration') from None
    declaration = project.get('project')
    if type(declaration) is not dict or type(declaration.get('name')) is not str or not declaration['name']:
        raise UnsupportedShape('Package distribution name is missing')
    scripts = declaration.get('scripts', {})
    target = scripts.get(script) if type(scripts) is dict else None
    if type(target) is not str or target.count(':') != 1:
        raise UnsupportedShape('Declared static console script is required')
    module, function = target.split(':')
    if (not all(part.isidentifier() for part in module.split('.'))
            or not function.isidentifier()):
        raise UnsupportedShape('Unsupported console script target')
    package_name = package.name
    if module.split('.')[0] != package_name:
        raise UnsupportedShape('Console script must remain in the selected regular package')
    console = package.parent.joinpath(*module.split('.')).with_suffix('.py')
    if not console.is_file() or console.parent != package:
        raise UnsupportedShape('Console script source is outside selected package')
    function_names = [node for node in ast.parse(console.read_text(encoding='utf-8')).body
                      if isinstance(node, ast.FunctionDef) and node.name == function]
    if len(function_names) != 1:
        raise UnsupportedShape('Console script function is missing or ambiguous')
    if not adapter_name.isidentifier():
        raise InputError('Invalid generated adapter module name')
    files = sorted(path for path in package.rglob('*.py')
                   if path != package / (adapter_name + '.py'))
    if not 2 <= len(files) <= 63 or any(path.is_symlink() for path in files):
        raise UnsupportedShape('Package Python source set is unsupported')
    package_root = package.relative_to(root).as_posix()
    module_name = source.stem
    selected_name = symbol.split('.')[-1]
    owner = symbol.split('.')[0] if shape == 'instance-method-tail-call-v1' else None
    source_files: dict[str, str] = {}
    calls = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        raw = adapted_source.encode('utf-8') if path == source else path.read_bytes()
        if len(raw) > 1_000_000 or b'\r' in raw.replace(b'\r\n', b''):
            raise UnsupportedShape('Unsupported package source bytes')
        try:
            tree = ast.parse(raw.decode('utf-8'))
        except (UnicodeError, SyntaxError):
            raise UnsupportedShape('Invalid UTF-8 package Python source') from None
        source_files[relative] = file_hash(path) if path != source else hashlib.sha256(raw).hexdigest()
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
                   and ((node.level == 1 and node.module == module_name)
                        or (node.level == 0 and node.module == package_name + '.' + module_name))]
        if imports:
            raise UnsupportedShape('Selected module reexports or from-import callers are unsupported')
        aliases = [alias.asname or alias.name for node in tree.body
                   if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None
                   for alias in node.names if alias.name == module_name]
        if len(aliases) > 1:
            raise UnsupportedShape('Ambiguous selected-module caller import')
        host_alias = aliases[0] if aliases else None
        asyncio_import = any(isinstance(item, ast.Import) and len(item.names) == 1
                             and item.names[0].name == 'asyncio'
                             and item.names[0].asname is None for item in tree.body)
        parents = {child: parent for parent in ast.walk(tree)
                   for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if (isinstance(node, ast.ImportFrom)
                    and any(alias.name == '*' for alias in node.names)):
                raise UnsupportedShape('Star-import caller scope is unsupported')
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ('getattr', 'setattr', 'delattr', 'hasattr',
                                         'dir', 'eval', 'exec', 'globals', 'locals',
                                         'vars', '__import__')):
                raise UnsupportedShape('Dynamic caller lookup is unsupported')
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ('getattr', 'setattr', 'delattr', 'hasattr',
                                           'import_module', 'attrgetter', 'methodcaller',
                                           '__getattribute__', '__getattr__', 'partial')):
                raise UnsupportedShape('Dynamic caller construction is unsupported')
            if isinstance(node, ast.Name) and host_alias and node.id == host_alias and isinstance(node.ctx, (ast.Store, ast.Del)):
                raise UnsupportedShape('Selected-module caller alias is reassigned')
            if isinstance(node, ast.Name) and asyncio_import and node.id == 'asyncio' and isinstance(node.ctx, (ast.Store, ast.Del)):
                raise UnsupportedShape('Asyncio import alias is reassigned')
            if isinstance(node, ast.Attribute) and node.attr == selected_name:
                if (asyncio_import and selected_name == 'run' and isinstance(node.value, ast.Name)
                        and node.value.id == 'asyncio'):
                    continue
                parent = next((candidate for candidate in ast.walk(tree)
                               if isinstance(candidate, ast.Call) and candidate.func is node), None)
                if parent is None:
                    raise UnsupportedShape('Selected seam reference without direct call')
                if owner is not None:
                    receiver = node.value
                    direct = (isinstance(receiver, ast.Call) and not receiver.args and not receiver.keywords
                              and ((path == source and isinstance(receiver.func, ast.Name)
                                    and receiver.func.id == owner)
                                   or (host_alias and isinstance(receiver.func, ast.Attribute)
                                       and receiver.func.attr == owner
                                       and isinstance(receiver.func.value, ast.Name)
                                       and receiver.func.value.id == host_alias)))
                else:
                    direct = (host_alias is not None and isinstance(node.value, ast.Name)
                              and node.value.id == host_alias)
                if not direct:
                    raise UnsupportedShape('Selected seam caller is not an unambiguous direct package call')
                if shape == 'async-module-tail-call-v1' and not isinstance(parents.get(parent), ast.Await):
                    raise UnsupportedShape('Async selected caller must directly await the coroutine')
                calls.append({'file': relative, 'line': node.lineno, 'column': node.col_offset})
            if (path == source and owner is None and isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == selected_name):
                if shape == 'async-module-tail-call-v1' and not isinstance(parents.get(node), ast.Await):
                    raise UnsupportedShape('Async selected caller must directly await the coroutine')
                calls.append({'file': relative, 'line': node.lineno, 'column': node.col_offset})
    if not calls:
        raise UnsupportedShape('No direct selected seam caller in declared package')
    calls.sort(key=lambda row: (row['file'], row['line'], row['column']))
    return {'kind': 'static-regular-package-callers-v1', 'package': package_root,
            'script': script, 'script_target': target,
            'distribution': declaration['name'],
            'pyproject_sha256': file_hash(build_file),
            'source_files': source_files,
            'calls': calls, 'external_callers': 'requires_independent_closed_scope_review'}


def _source_root(module: ModuleType) -> tuple[Path, bool]:
    source = Path(module.__file__).resolve()
    build_root = source.parents[module.SOURCE_ROOT_DEPTH]
    if (build_root / 'pyproject.toml').is_file():
        return build_root, False
    return source.parents[1], True


def _owned_plan(module: ModuleType) -> dict:
    root, installed = _source_root(module)
    rows = []
    for rel, sha in sorted(module.SOURCE_FILES.items()):
        installed_rel = rel.removeprefix('src/') if installed else rel
        rows.append({'path': str((root / installed_rel).resolve()), 'sha256': sha})
    project = root / 'pyproject.toml'
    if project.is_file():
        rows.append({'path': str(project.resolve()),
                     'sha256': module.BUILD_PYPROJECT_SHA256})
    return {'files': rows}


def start_adapter(module: ModuleType, *, budget_limits: dict, audit_log: Any,
                  policy_bindings: dict, adapter_plan: dict,
                  review_receipt: dict, verify_review: Any,
                  client: Any = None,
                  startup_mode: str = 'off') -> HostRuntimeLifecycle:
    """Bind current installed bytes and one process-local runtime at startup."""
    if getattr(module, '_STARTED', False):
        raise LifecycleError('adaptation_runtime_already_started')
    validate_contract(adapter_plan, 'generated-adaptation-adapter-plan-v1')
    validate_contract(review_receipt, 'adaptation-runtime-review-receipt-v1')
    if module.SHAPE not in RUNTIME_SHAPES or startup_mode not in ('off', 'shadow'):
        raise LifecycleError('adaptation_runtime_mode_unsupported')
    if (type(policy_bindings) is not dict or set(policy_bindings) != POLICY_ROLES
            or any(not callable(value) for value in policy_bindings.values())):
        raise LifecycleError('reviewed_host_policy_bindings_required')
    from .lifecycle import engine_identity

    adapter_sha256 = file_hash(Path(module.__file__))
    adapter_relative = (Path(module.SPEC['source']['file']).parent /
                        Path(module.__file__).name).as_posix()
    if (adapter_plan['contract_digest'] != digest({
            key: value for key, value in adapter_plan.items() if key != 'contract_digest'})
            or adapter_plan['stage'] != 'final'
            or adapter_plan['engine_identity'] != engine_identity()
            or adapter_plan['spec_sha256'] != digest(module.SPEC)
            or adapter_plan['source_file'] != module.SPEC['source']['file']
            or adapter_plan['source_after_sha256'] != module.SPEC['source']['file_sha256']
            or adapter_plan['caller_scope_sha256'] != module.CALLER_SCOPE_SHA256
            or adapter_plan['owned_file']['file'] != adapter_relative
            or adapter_plan['owned_file']['new_sha256'] != adapter_sha256
            or adapter_plan['adaptation_verification_sha256'] is None):
        raise LifecycleError('final_adaptation_adapter_plan_mismatch')
    if (type(review_receipt) is not dict
            or set(review_receipt) != {'adapter_sha256', 'adapter_plan_sha256',
                                       'adaptation_verification_sha256',
                                       'adapted_source_sha256',
                                       'adapted_symbol_sha256',
                                       'caller_scope_sha256', 'pyproject_sha256',
                                       'script_target', 'reviewer', 'approved'}
            or review_receipt['approved'] is not True
            or type(review_receipt['reviewer']) is not str or not review_receipt['reviewer']
            or review_receipt['adapted_source_sha256'] != module.SPEC['source']['file_sha256']
            or review_receipt['adapted_symbol_sha256'] != module.SPEC['source']['source_sha256']
            or review_receipt['caller_scope_sha256'] != module.CALLER_SCOPE_SHA256
            or review_receipt['pyproject_sha256'] != module.BUILD_PYPROJECT_SHA256
            or review_receipt['script_target'] != module.SCRIPT_TARGET
            or review_receipt['adapter_sha256'] != adapter_sha256
            or review_receipt['adapter_plan_sha256'] != adapter_plan['contract_digest']
            or review_receipt['adaptation_verification_sha256'] !=
               adapter_plan['adaptation_verification_sha256']
            or not callable(verify_review)
            or verify_review('adaptation_runtime_review', digest(review_receipt)) is not True):
        raise LifecycleError('authenticated_post_adaptation_review_required')
    root, _installed = _source_root(module)
    project_file = root / 'pyproject.toml'
    if project_file.is_file():
        if file_hash(project_file) != module.BUILD_PYPROJECT_SHA256:
            raise LifecycleError('adaptation_build_configuration_drift')
    else:
        try:
            distribution = importlib.metadata.distribution(module.DISTRIBUTION)
            scripts = [entry.value for entry in distribution.entry_points
                       if entry.group == 'console_scripts' and entry.name == module.SCRIPT]
        except importlib.metadata.PackageNotFoundError:
            raise LifecycleError('installed_adaptation_distribution_missing') from None
        if scripts != [module.SCRIPT_TARGET]:
            raise LifecycleError('installed_adaptation_console_binding_drift')
    plan = _owned_plan(module)
    check_dependency_plan(plan)
    if module.SPEC['source']['file_sha256'] not in module.SOURCE_FILES.values():
        raise LifecycleError('adapted_source_not_bound')
    runtime = HostRuntimeLifecycle({module.SPEC['candidate_id']: module},
                                   budget_limits=budget_limits, audit_log=audit_log,
                                   dependency_plan=plan, client=client,
                                   startup_mode=startup_mode)
    module._POLICY_BINDINGS = dict(policy_bindings)
    module._RUNTIME = runtime
    module._STARTED = True
    return runtime


def _request(module: ModuleType, values: tuple) -> Any:
    if module.SHAPE == 'module-fixed-positional-tail-call-v1':
        if type(values) is not tuple or len(values) != module.POSITIONAL_COUNT:
            raise LifecycleError('fixed_positional_argument_count_changed')
        request = values[module.REQUEST_POSITION]
    else:
        if len(values) != 1:
            raise LifecycleError('adaptation_argument_count_changed')
        request = values[0]
    return request


def _has_task(module: ModuleType, request: Any) -> bool:
    field = module.SPEC['runtime']['task_field']
    return (type(request) is dict and type(request.get(field)) is str
            and bool(request[field]))


def _bindings(module: ModuleType) -> dict:
    runtime = getattr(module, '_RUNTIME', None)
    if runtime is None:
        raise LifecycleError('adaptation_runtime_not_started')
    return dict(module._POLICY_BINDINGS, runtime=runtime.runtime_binding(module.SPEC['candidate_id']))


def invoke_sync(module: ModuleType, original: Any, values: tuple) -> Any:
    """Preserve the exact receiver/arguments and execute the baseline once."""
    if module.SHAPE == 'async-module-tail-call-v1':
        raise LifecycleError('async_seam_requires_await')
    if module.SHAPE == 'module-fixed-positional-tail-call-v1':
        request = _request(module, values)
        baseline = lambda _request: original(*values)
    else:
        request = _request(module, values)
        baseline = original
    runtime = getattr(module, '_RUNTIME', None)
    if runtime is None:
        return baseline(request)
    if not _has_task(module, request):
        check_dependency_plan(_owned_plan(module))
        return baseline(request)
    if runtime.mode_status()['effective_mode'] == 'off':
        runtime.router(module.SPEC['candidate_id'], request)
        return baseline(request)
    return invoke_bound(module.SPEC, baseline, request, _bindings(module))


async def invoke_async(module: ModuleType, original: Any, request: dict) -> Any:
    """Run only read-only synthetic assessment in a worker, then await once."""
    if module.SHAPE != 'async-module-tail-call-v1':
        raise LifecycleError('sync_seam_requires_sync_invoke')
    _request(module, (request,))
    runtime = getattr(module, '_RUNTIME', None)
    if runtime is not None:
        if not _has_task(module, request):
            check_dependency_plan(_owned_plan(module))
            return await original(request)
        mode = runtime.mode_status()['effective_mode']
        if mode == 'shadow':
            bindings = _bindings(module)
            await asyncio.to_thread(invoke_bound, module.SPEC, lambda _request: None,
                                    request, bindings)
        elif mode == 'off':
            runtime.router(module.SPEC['candidate_id'], request)
        else:
            raise LifecycleError('async_connected_or_activation_unsupported')
    return await original(request)


def render_adapter(*, spec: dict, shape: str, source_files: dict[str, str],
                   pyproject_sha256: str, script: str, script_target: str,
                   distribution: str, caller_scope_sha256: str,
                   request_position: int = 0, positional_count: int = 1,
                   source_root_depth: int = 1) -> str:
    """Return an importable adapter module bound to adapted source and callers."""
    if type(spec) is not dict or shape not in RUNTIME_SHAPES or spec.get('recipe', {}).get('id') != 'python.C':
        raise InputError('Unsupported runtime adaptation shape or recipe')
    required_spec = {'candidate_id', 'experiment_id', 'source', 'recipe', 'questions',
                     'primary_question', 'evidence_question', 'label_actions', 'runtime',
                     'policy', 'registered_action_ids'}
    if (type(spec) is not dict or set(spec) != required_spec
            or type(spec['candidate_id']) is not str or not spec['candidate_id']
            or type(spec['registered_action_ids']) is not list
            or not spec['registered_action_ids']
            or any(type(action) is not str or not action for action in spec['registered_action_ids'])
            or len(set(spec['registered_action_ids'])) != len(spec['registered_action_ids'])
            or type(spec['source']) is not dict
            or type(spec['source'].get('source_sha256')) is not str
            or len(spec['source']['source_sha256']) != 64
            or type(spec['runtime']) is not dict
            or type(spec['runtime'].get('configuration')) is not dict
            or spec['runtime']['configuration'].get('mode') != 'off'
            or type(spec['runtime'].get('task_field')) is not str
            or not spec['runtime']['task_field']):
        raise InputError('Invalid reviewed runtime adapter specification')
    if type(source_root_depth) is not int or source_root_depth not in (1, 2):
        raise InputError('Unsupported regular package source root depth')
    if (type(source_files) is not dict or not source_files
            or any(type(name) is not str or not name or Path(name).is_absolute()
                   or '..' in Path(name).parts or type(sha) is not str or len(sha) != 64
                   or any(char not in '0123456789abcdef' for char in sha)
                   for name, sha in source_files.items())):
        raise InputError('Exact adapted source and caller hashes required')
    if (shape == 'module-fixed-positional-tail-call-v1' and
            (not 2 <= positional_count <= 8 or not 0 <= request_position < positional_count)):
        raise InputError('Fixed positional request binding invalid')
    if shape != 'module-fixed-positional-tail-call-v1' and (request_position, positional_count) != (0, 1):
        raise InputError('Single-request adaptation binding invalid')
    if spec.get('source', {}).get('file_sha256') not in source_files.values():
        raise InputError('Runtime spec must bind the adapted source bytes')
    if (type(caller_scope_sha256) is not str or len(caller_scope_sha256) != 64
            or any(char not in '0123456789abcdef' for char in caller_scope_sha256)):
        raise InputError('Complete direct caller scope hash required')
    if (type(pyproject_sha256) is not str or len(pyproject_sha256) != 64
            or any(char not in '0123456789abcdef' for char in pyproject_sha256)
            or not all(type(value) is str and value for value in
                       (script, script_target, distribution))):
        raise InputError('Exact package build and console binding required')
    result = f'''"""Generated source-bound runtime adapter; host policy supplied at startup."""
SPEC = {spec!r}
SHAPE = {shape!r}
SOURCE_FILES = {dict(sorted(source_files.items()))!r}
CALLER_SCOPE_SHA256 = {caller_scope_sha256!r}
BUILD_PYPROJECT_SHA256 = {pyproject_sha256!r}
SCRIPT = {script!r}
SCRIPT_TARGET = {script_target!r}
DISTRIBUTION = {distribution!r}
SOURCE_ROOT_DEPTH = {source_root_depth}
REQUEST_POSITION = {request_position}
POSITIONAL_COUNT = {positional_count}
_STARTED = False
_RUNTIME = None
_POLICY_BINDINGS = None

def create_router(client, *, budget_coordinator, audit_log, runtime_config=None, activation=None, thresholds=None):
    from jev_integration_evaluator.runtime import SafeRouter
    return SafeRouter(client, runtime_config or SPEC['runtime']['configuration'],
        policy_version=SPEC['runtime']['policy_version'], thresholds=thresholds,
        activation=activation, audit_log=audit_log, budget_coordinator=budget_coordinator,
        canary_scope=SPEC['runtime']['canary_scope'], require_expiring_activation=True,
        require_runtime_binding=True)

def startup(*, budget_limits, audit_log, policy_bindings, adapter_plan,
            review_receipt, verify_review,
            client=None, startup_mode='off'):
    import sys
    from jev_integration_evaluator.integrations.adaptation_runtime import start_adapter
    return start_adapter(sys.modules[__name__], budget_limits=budget_limits, audit_log=audit_log,
        policy_bindings=policy_bindings, adapter_plan=adapter_plan,
        review_receipt=review_receipt,
        verify_review=verify_review, client=client,
        startup_mode=startup_mode)

def complete_task(task_id):
    if _RUNTIME is None:
        raise RuntimeError('adaptation_runtime_not_started')
    _RUNTIME.complete_task(task_id)

def shutdown():
    global _RUNTIME
    if _RUNTIME is not None:
        _RUNTIME.close()
        _RUNTIME = None

def invoke(original, request):
    import sys
    from jev_integration_evaluator.integrations.adaptation_runtime import invoke_sync
    return invoke_sync(sys.modules[__name__], original, request if SHAPE == 'module-fixed-positional-tail-call-v1' else (request,))

async def invoke_async(original, request):
    import sys
    from jev_integration_evaluator.integrations.adaptation_runtime import invoke_async
    return await invoke_async(sys.modules[__name__], original, request)
'''
    import ast
    ast.parse(result)
    return result
