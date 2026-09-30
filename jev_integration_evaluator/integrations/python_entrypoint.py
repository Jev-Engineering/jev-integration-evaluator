"""Static, source-bound console entrypoint profile for reviewed Python C/D/E/H/L/M tasks."""
from __future__ import annotations

import ast
import codecs
import io
from pathlib import Path
import re
import tokenize

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from ..io import InputError, file_hash, safe_child
from .errors import UnsupportedShape
from .package_bindings import StaticBindings, module_layout

_SYMBOL = re.compile(r'[A-Za-z_][A-Za-z_0-9]*\Z')
_SCRIPT = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,127}\Z')
_INPUTS = ('budget_limits', 'audit_log', 'dependency_plan', 'startup_options')


def _source(root: Path, rel: str) -> tuple[bytes, ast.Module]:
    path = safe_child(root, rel)
    if not path.is_file() or path.is_symlink():
        raise UnsupportedShape('Console entrypoint source is unavailable')
    raw = path.read_bytes()
    if len(raw) > 2_000_000 or raw.startswith(b'\xef\xbb\xbf'):
        raise UnsupportedShape('Unsupported console entrypoint source encoding or size')
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        if codecs.lookup(encoding).name != 'utf-8':
            raise UnsupportedShape('Console entrypoint source must declare UTF-8')
        tree = ast.parse(raw.decode('utf-8'), filename=rel)
    except (SyntaxError, UnicodeError, LookupError):
        raise UnsupportedShape('Invalid UTF-8 console entrypoint source') from None
    return raw, tree


def _script(root: Path, name: str) -> tuple[str, str]:
    if type(name) is not str or not _SCRIPT.fullmatch(name):
        raise InputError('Invalid console script name')
    path = safe_child(root, 'pyproject.toml')
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000:
        raise UnsupportedShape('Missing or unsupported pyproject.toml')
    try:
        document = tomllib.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError):
        raise UnsupportedShape('Invalid pyproject.toml') from None
    project = document.get('project')
    if type(project) is not dict:
        raise UnsupportedShape('Missing or malformed pyproject [project] table')
    scripts = project.get('scripts', {})
    if type(scripts) is not dict or name not in scripts or type(scripts[name]) is not str:
        raise UnsupportedShape('Declared console script is absent or ambiguous')
    target = scripts[name]
    if target.count(':') != 1 or '[' in target or ']' in target:
        raise UnsupportedShape('Unsupported console script target')
    module, symbol = target.split(':')
    if (not module or any(not _SYMBOL.fullmatch(part) for part in module.split('.'))
            or not _SYMBOL.fullmatch(symbol)):
        raise UnsupportedShape('Invalid console script target')
    return module, symbol


def _function(tree: ast.Module, name: str, arity: int) -> ast.FunctionDef:
    from .recipes import _module_bindings
    nodes = _module_bindings(tree).get(name, [])
    if len(nodes) != 1 or not isinstance(nodes[0], ast.FunctionDef) or nodes[0] not in tree.body:
        raise UnsupportedShape('Missing or ambiguous entrypoint function: ' + name)
    node = nodes[0]
    if (node.decorator_list or node.args.vararg or node.args.kwarg or node.args.kwonlyargs
            or node.args.defaults or node.args.kw_defaults
            or len(node.args.posonlyargs) + len(node.args.args) != arity):
        raise UnsupportedShape('Unsupported entrypoint function signature: ' + name)
    return node


def inspect_entrypoint(root: Path, spec: dict, binding: dict) -> dict:
    """Derive fresh paths and hashes; never import or execute host modules."""
    if (type(binding) is not dict or set(binding) != {'version', 'script', 'startup_inputs'}
            or binding['version'] != '1.0' or type(binding['startup_inputs']) is not dict
            or set(binding['startup_inputs']) != set(_INPUTS)
            or any(type(value) is not str or not _SYMBOL.fullmatch(value)
                   for value in binding['startup_inputs'].values())):
        raise InputError('Invalid explicit console entrypoint binding')
    if (spec['recipe']['id'] not in ('python.C', 'python.D', 'python.E', 'python.H', 'python.L', 'python.M')
            or 'package_binding' not in spec or 'host_lifecycle' not in spec):
        raise UnsupportedShape('Console profile requires a package-bound recipe C, D, E, H, L or M lifecycle')
    if spec['package_binding']['namespace']:
        raise UnsupportedShape('Console profile requires a regular package')
    module, symbol = _script(root, binding['script'])
    prefix = 'src' if spec['source']['file'].startswith('src/') else ''
    entry_rel = '/'.join(filter(None, (prefix, *module.split('.')))) + '.py'
    import_root, actual_module, _ = module_layout(root, entry_rel, namespace=False)
    if import_root != prefix or actual_module != module:
        raise UnsupportedShape('Console script module differs from package layout')
    if module.split('.')[0] != spec['package_binding']['module'].split('.')[0]:
        raise UnsupportedShape('Console script must use the reviewed host package')
    raw, tree = _source(root, entry_rel)
    entry = _function(tree, symbol, 0)
    statements = entry.body[:]
    if statements and isinstance(statements[0], ast.Expr) and isinstance(statements[0].value, ast.Constant) and isinstance(statements[0].value.value, str):
        statements = statements[1:]
    if (len(statements) not in (2, 3) or not isinstance(statements[0], ast.Assign)
            or len(statements[0].targets) != 1 or not isinstance(statements[0].targets[0], ast.Name)
            or not isinstance(statements[0].value, ast.Call)
            or not isinstance(statements[0].value.func, ast.Name)
            or statements[0].value.args or statements[0].value.keywords):
        raise UnsupportedShape('Console entrypoint requires a local zero-argument request factory')
    request_name = statements[0].targets[0].id
    kind = 'single-request-v1' if len(statements) == 2 else 'task-loop-v1'
    if spec['recipe']['id'] == 'python.E' and kind != 'task-loop-v1':
        raise UnsupportedShape('Completion console requires a bounded task loop returning 0')
    if spec['recipe']['id'] == 'python.D' and kind != 'task-loop-v1':
        raise UnsupportedShape('Retrieval console requires a bounded explicit request loop')
    if spec['recipe']['id'] == 'python.H' and kind != 'task-loop-v1':
        raise UnsupportedShape('Retention console requires a bounded explicit request loop')
    if spec['recipe']['id'] == 'python.L' and kind != 'task-loop-v1':
        raise UnsupportedShape('Graph console requires a bounded explicit request loop')
    if spec['recipe']['id'] == 'python.M' and kind != 'task-loop-v1':
        raise UnsupportedShape('Claim console requires a bounded explicit request loop')
    item_name = None
    if kind == 'single-request-v1':
        if not isinstance(statements[1], ast.Return):
            raise UnsupportedShape('Single-request console entrypoint must return its task call')
        task_call = statements[1].value
        expected_arg = request_name
    else:
        loop, final = statements[1:]
        if (not isinstance(loop, ast.For) or loop.orelse or not isinstance(loop.target, ast.Name)
                or not isinstance(loop.iter, ast.Name) or loop.iter.id != request_name
                or len(loop.body) != 1 or not isinstance(loop.body[0], ast.Expr)
                or not isinstance(final, ast.Return) or not isinstance(final.value, ast.Constant)
                or type(final.value.value) is not int or final.value.value != 0):
            raise UnsupportedShape('Task-loop console entrypoint requires one task call per request and return 0')
        item_name = loop.target.id
        task_call = loop.body[0].value
        expected_arg = item_name
    if (not isinstance(task_call, ast.Call) or not isinstance(task_call.func, ast.Name) or len(task_call.args) != 1
            or task_call.keywords or not isinstance(task_call.args[0], ast.Name)
            or task_call.args[0].id != expected_arg):
        raise UnsupportedShape('Console entrypoint must pass its unchanged request once')
    resolver = StaticBindings(root, entry_rel, namespace=False)
    _function(tree, statements[0].value.func.id, 0)
    task_rel, task_symbol, task = resolver.resolve(task_call.func.id)
    if task_rel != spec['source']['file']:
        raise UnsupportedShape('Console task call must resolve to the selected host module')
    body = task.body[:]
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if (task.decorator_list or task.args.posonlyargs or task.args.vararg or task.args.kwarg
            or task.args.kwonlyargs or task.args.defaults or task.args.kw_defaults
            or len(task.args.args) != 1):
        raise UnsupportedShape('Console task caller must accept one unchanged request')
    if (len(body) != 1 or not isinstance(body[0], ast.Return)
            or not isinstance(body[0].value, ast.Call)
            or not isinstance(body[0].value.func, ast.Name)
            or len(body[0].value.args) != 1 or body[0].value.keywords
            or not isinstance(body[0].value.args[0], ast.Name)
            or body[0].value.args[0].id != task.args.args[0].arg):
        raise UnsupportedShape('Console task caller must make one direct seam call')
    seam_rel, seam_symbol, _ = resolver.resolve_from(resolver.module_for(task_rel), body[0].value.func.id)
    if seam_rel != spec['source']['file'] or seam_symbol != spec['source']['symbol']:
        raise UnsupportedShape('Console task caller does not reach selected seam')
    for name in binding['startup_inputs'].values():
        _function(tree, name, 0)
    # Require the lifecycle functions to be imported through static reviewed bindings.
    for name in spec['host_lifecycle'].values():
        if name == 'module-startup-v1':
            continue
        # They are generated after apply, so verify reserved names and the package path instead.
        if not _SYMBOL.fullmatch(name):
            raise InputError('Invalid reviewed lifecycle symbol')
    if entry_rel == spec['source']['file']:
        raise UnsupportedShape('Console entrypoint must be in a separate package module')
    if any(row['file'] != (Path(spec['source']['file']).parent / Path(row['file']).name).as_posix()
           for row in spec['runtime_files']):
        raise UnsupportedShape('Console runtime files must sit beside the selected host module')
    return {'version': '1.0', 'kind': kind, 'script': binding['script'], 'module': module,
            'function': symbol, 'file': entry_rel, 'file_sha256': file_hash(safe_child(root, entry_rel)),
            'pyproject_sha256': file_hash(safe_child(root, 'pyproject.toml')),
            'request_symbol': request_name, 'item_symbol': item_name,
            'task_symbol': task_call.func.id,
            'startup_inputs': dict(binding['startup_inputs']),
            'contributing_sources': dict(resolver.dependencies)}


def render_entrypoint(raw: bytes, tree: ast.Module, contract: dict, spec: dict) -> str:
    """Replace only the checked return statement; preserve all other host bytes."""
    entry = _function(tree, contract['function'], 0)
    selected = entry.body[-1] if contract['kind'] == 'single-request-v1' else entry.body[-2]
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines: offsets.append(offsets[-1] + len(line))
    start = offsets[selected.lineno - 1]
    end = offsets[selected.end_lineno - 1] + selected.end_col_offset
    indent = raw[start:offsets[selected.lineno-1] + selected.col_offset].decode('utf-8')
    newline = '\r\n' if b'\r\n' in raw else '\n'
    if b'\r' in raw.replace(b'\r\n', b''):
        raise UnsupportedShape('Unsupported bare-CR entrypoint')
    from ..io import digest
    suffix = digest(contract)[:16]
    host_module = spec['package_binding']['module']
    alias = '_jev_host_' + suffix
    exc_alias = '_jev_exc_' + suffix
    err_alias = '_jev_cleanup_' + suffix
    id_alias = '_jev_id_' + suffix
    ids_alias = '_jev_ids_' + suffix
    drift_alias = '_jev_drift_' + suffix
    generated = {alias, exc_alias, err_alias, id_alias, ids_alias, drift_alias,
                 '_jev_sys_' + suffix, '_jev_item_' + suffix,
                 '_jev_index_' + suffix, '_jev_error_' + suffix}
    if any(isinstance(node, ast.Name) and node.id in generated for node in ast.walk(entry)):
        raise UnsupportedShape('Generated console symbol conflicts with reviewed caller')
    request = contract['request_symbol']
    task = contract['task_symbol']
    lifecycle = spec['host_lifecycle']
    inputs = contract['startup_inputs']
    task_field = spec['runtime']['task_field']
    preflight = ([
        f'{indent}if type({request}) not in (list, tuple):',
        f'{indent}    raise ValueError("invalid_bounded_task_schedule")',
        f'{indent}{request} = tuple({request})',
        f'{indent}if not 1 <= len({request}) <= 32:',
        f'{indent}    raise ValueError("invalid_bounded_task_schedule")',
        f'{indent}if any(type(_jev_item_{suffix}) is not dict or type(_jev_item_{suffix}.get({task_field!r})) is not str or not _jev_item_{suffix}[{task_field!r}] for _jev_item_{suffix} in {request}):',
        f'{indent}    raise ValueError("invalid_stable_task_identity")',
        f'{indent}{ids_alias} = tuple(_jev_item_{suffix}[{task_field!r}] for _jev_item_{suffix} in {request})',
        f'{indent}if len(set({ids_alias})) != len({ids_alias}):',
        f'{indent}    raise ValueError("duplicate_task_identity")',
    ] if contract['kind'] == 'task-loop-v1' else [
        f'{indent}if type({request}) is not dict or type({request}.get({task_field!r})) is not str or not {request}[{task_field!r}]:',
        f'{indent}    raise ValueError("invalid_stable_task_identity")',
        f'{indent}{id_alias} = {request}[{task_field!r}]',
    ])
    common = preflight + [
        f'{indent}from {host_module.rpartition(".")[0]} import {host_module.rpartition(".")[2]} as {alias}',
        f'{indent}import sys as _jev_sys_{suffix}',
        f'{indent}{alias}.{lifecycle["startup"]}(budget_limits={inputs["budget_limits"]}(), audit_log={inputs["audit_log"]}(), dependency_plan={inputs["dependency_plan"]}(), **{inputs["startup_options"]}())',
    ]
    if contract['kind'] == 'task-loop-v1':
        item = contract['item_symbol']
        code = common + [
            f'{indent}try:',
            f'{indent}    for _jev_index_{suffix}, {item} in enumerate({request}):',
            f'{indent}        {id_alias} = {ids_alias}[_jev_index_{suffix}]',
            f'{indent}        try:',
            f'{indent}            if type({item}) is not dict or {item}.get({task_field!r}) != {id_alias}: raise RuntimeError("task_identity_changed")',
            f'{indent}            {task}({item})',
            f'{indent}        finally:',
            f'{indent}            {exc_alias} = _jev_sys_{suffix}.exc_info()[0] is not None',
            f'{indent}            {drift_alias} = type({item}) is not dict or {item}.get({task_field!r}) != {id_alias}',
            f'{indent}            try:',
            f'{indent}                {alias}.{lifecycle["complete_task"]}({id_alias})',
            f'{indent}            except BaseException:',
            f'{indent}                if not {exc_alias}:',
            f'{indent}                    raise',
            f'{indent}            if {drift_alias} and not {exc_alias}:',
            f'{indent}                raise RuntimeError("task_identity_changed")',
            f'{indent}finally:',
            f'{indent}    {exc_alias} = _jev_sys_{suffix}.exc_info()[0] is not None',
            f'{indent}    try:',
            f'{indent}        {alias}.{lifecycle["shutdown"]}()',
            f'{indent}    except BaseException:',
            f'{indent}        if not {exc_alias}:',
            f'{indent}            raise',
        ]
    else:
        code = common + [
        f'{indent}try:',
        f'{indent}    return {task}({request})',
        f'{indent}finally:',
        f'{indent}    {exc_alias} = _jev_sys_{suffix}.exc_info()[0] is not None',
        f'{indent}    {drift_alias} = type({request}) is not dict or {request}.get({task_field!r}) != {id_alias}',
        f'{indent}    {err_alias} = None',
        f'{indent}    try:',
        f'{indent}        {alias}.{lifecycle["complete_task"]}({id_alias})',
        f'{indent}    except BaseException as _jev_error_{suffix}:',
        f'{indent}        {err_alias} = _jev_error_{suffix}',
        f'{indent}    try:',
        f'{indent}        {alias}.{lifecycle["shutdown"]}()',
        f'{indent}    except BaseException as _jev_error_{suffix}:',
        f'{indent}        if {err_alias} is None:',
        f'{indent}            {err_alias} = _jev_error_{suffix}',
        f'{indent}    if not {exc_alias} and {err_alias} is not None:',
        f'{indent}        raise {err_alias}',
        f'{indent}    if not {exc_alias} and {drift_alias}:',
        f'{indent}        raise RuntimeError("task_identity_changed")',
        ]
    result = raw[:start] + newline.join(code).encode('utf-8') + raw[end:]
    ast.parse(result.decode('utf-8'), filename=contract['file'])
    return result.decode('utf-8')
