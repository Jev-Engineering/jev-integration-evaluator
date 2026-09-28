"""Source-bound structural preparation for two narrow Python seam shapes.

This module does not approve or apply a patch. The caller must bind the returned
bytes to a reviewed plan and execute an independent behavioral verifier.
"""
from __future__ import annotations

import ast
import hashlib
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from ..io import InputError, digest, file_hash, safe_child
from .errors import UnsupportedShape
from .recipes import _module_bindings


@dataclass(frozen=True)
class Shape:
    name: str
    version: str
    preconditions: tuple[str, ...]


SHAPES = {
    'instance-method-tail-call-v1': Shape('instance-method-tail-call-v1', '1.0', (
        'undecorated ordinary class and instance method',
        'one receiver and one request argument, without defaults or variadics',
        'one return of a receiver method called with the unchanged request',
    )),
    'async-module-tail-call-v1': Shape('async-module-tail-call-v1', '1.0', (
        'undecorated top-level async function with one request argument',
        'one return awaiting an async named function called with the unchanged request',
    )),
}


REVIEWED_REQUEST_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'dependentRequired': {key: ['review_context_sha256', 'host_policy_sha256',
                                'trusted_binding_review_sha256', 'agent_proposal_sha256']
                          for key in ('review_context_sha256', 'host_policy_sha256',
                                      'trusted_binding_review_sha256', 'agent_proposal_sha256')},
    'required': ['strategy', 'candidate_id', 'inventory_sha256', 'inventory_fingerprint',
                 'source', 'binding_review', 'adapter_name'],
    'properties': {
        'strategy': {'type': 'object', 'additionalProperties': False,
                     'required': ['shape', 'version'], 'properties': {
                         'shape': {'enum': list(SHAPES)}, 'version': {'const': '1.0'}}},
        'candidate_id': {'type': 'string', 'minLength': 1},
        'inventory_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
        'inventory_fingerprint': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
        'source': {'type': 'object', 'additionalProperties': False,
                   'required': ['file', 'symbol', 'source_sha256', 'file_sha256', 'anchor_sha256'],
                   'properties': {key: {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
                                  for key in ('source_sha256', 'file_sha256', 'anchor_sha256')}
                   | {'file': {'type': 'string', 'minLength': 1},
                      'symbol': {'type': 'string', 'minLength': 1}}},
        'binding_review': {'type': 'object', 'additionalProperties': False,
                           'required': ['reviewer', 'reason', 'source_sha256', 'adapter_file', 'adapter_sha256'],
                           'properties': {'reviewer': {'type': 'string', 'minLength': 1},
                                          'reason': {'type': 'string', 'minLength': 1},
                                          'source_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
                                          'adapter_file': {'type': 'string', 'minLength': 1},
                                          'adapter_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}}},
        'adapter_name': {'type': 'string', 'pattern': '^[A-Za-z_][A-Za-z_0-9]*$'},
        'review_context_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
        'host_policy_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
        'trusted_binding_review_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
        'agent_proposal_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
        'caller_scope': {'type': 'object', 'additionalProperties': False,
                         'required': ['kind','discovery_sha256','source_files_sha256',
                                      'selected_symbol','calls','unknown_external_callers'],
                         'properties': {
                             'kind': {'const': 'bounded-python-caller-scope-v1'},
                             'discovery_sha256': {'type':'string','pattern':'^[0-9a-f]{64}$'},
                             'source_files_sha256': {'type':'string','pattern':'^[0-9a-f]{64}$'},
                             'selected_symbol': {'type':'string','minLength':1},
                             'calls': {'type':'array','minItems':1,'maxItems':256,
                                       'items': {'type':'object','additionalProperties':False,
                                                 'required':['file','line','column'],
                                                 'properties': {
                                                     'file': {'type':'string','minLength':1},
                                                     'line': {'type':'integer','minimum':1},
                                                     'column': {'type':'integer','minimum':0}}}},
                             'unknown_external_callers': {'const': True}}},
    },
}


def _body(function):
    body = function.body[:]
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        raise UnsupportedShape('Shape requires exactly one tail return')
    return body[0]


def _simple_args(function, expected):
    args = function.args
    if (function.decorator_list or args.vararg or args.kwarg or args.kwonlyargs or args.defaults
            or args.kw_defaults or len(args.posonlyargs + args.args) != expected):
        raise UnsupportedShape('Decorators, defaults, keyword-only and variadic arguments are unsupported')
    return [a.arg for a in args.posonlyargs + args.args]


def _unique(nodes, name, kind):
    found = [node for node in nodes if getattr(node, 'name', None) == name]
    found.extend(node for node in nodes if isinstance(node, (ast.Assign, ast.AnnAssign))
                 and any(isinstance(target, ast.Name) and target.id == name
                         for target in (node.targets if isinstance(node, ast.Assign) else [node.target])))
    if len(found) != 1 or not isinstance(found[0], kind):
        raise UnsupportedShape('Missing or ambiguous selected source symbol')
    return found[0]


def _statement(raw, statement):
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    return offsets[statement.lineno - 1] + statement.col_offset, offsets[statement.end_lineno - 1] + statement.end_col_offset


def prepare_shape(raw: bytes, *, shape: str, symbol: str, source_sha256: str,
                  anchor_sha256: str, adapter_name: str) -> dict:
    """Return an exact byte edit for a reviewed shape, without target execution.

    The output is a proposal. ``adapter_name`` names an existing reviewed module
    binding; it cannot create one or grant execution authority.
    """
    if shape not in SHAPES or SHAPES[shape].version != '1.0':
        raise UnsupportedShape('Unknown adaptation strategy/version')
    if hashlib.sha256(raw).hexdigest() != source_sha256:
        raise InputError('Adaptation source differs from reviewed bytes')
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        if encoding.lower().replace('_', '-') not in ('utf-8', 'utf-8-sig') or raw.startswith(b'\xef\xbb\xbf'):
            raise UnsupportedShape('Adaptation requires UTF-8 without BOM')
        tree = ast.parse(raw.decode('utf-8'))
    except (UnicodeError, SyntaxError):
        raise UnsupportedShape('Invalid UTF-8 Python source') from None
    if not adapter_name.isidentifier() or adapter_name.startswith('__'):
        raise InputError('Invalid reviewed adapter binding')
    if b'\r' in raw.replace(b'\r\n', b''):
        raise UnsupportedShape('Bare CR source is unsupported')
    if shape == 'instance-method-tail-call-v1':
        names = symbol.split('.')
        if len(names) != 2 or not all(name.isidentifier() for name in names):
            raise UnsupportedShape('Instance method requires Class.method symbol')
        found = _module_bindings(tree)
        if len(found.get(names[0], [])) != 1:
            raise UnsupportedShape('Ambiguous class binding')
        cls = _unique(tree.body, names[0], ast.ClassDef)
        if cls.bases or cls.keywords or cls.decorator_list:
            raise UnsupportedShape('Class bases, metaclasses and decorators are unsupported')
        if any(not isinstance(node, (ast.FunctionDef, ast.Pass)) and not
               (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))
               for node in cls.body):
            raise UnsupportedShape('Dynamic class body is unsupported')
        function = _unique(cls.body, names[1], ast.FunctionDef)
        receiver, request = _simple_args(function, 2)
        statement = _body(function)
        call = statement.value
        if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute)
                or not isinstance(call.func.value, ast.Name) or call.func.value.id != receiver
                or len(call.args) != 1 or call.keywords or not isinstance(call.args[0], ast.Name)
                or call.args[0].id != request or call.func.attr == function.name):
            raise UnsupportedShape('Method requires one unchanged receiver-bound tail call')
        baseline = _unique(cls.body, call.func.attr, ast.FunctionDef)
        _simple_args(baseline, 2)
        if any(n.name in ('__getattribute__', '__getattr__', '__getdescriptor__') for n in cls.body
               if isinstance(n, ast.FunctionDef)):
            raise UnsupportedShape('Dynamic receiver attribute lookup is unsupported')
        replacement = f'{adapter_name}.invoke({receiver}.{baseline.name}, {request})'
    else:
        if '.' in symbol or not symbol.isidentifier():
            raise UnsupportedShape('Async strategy requires a top-level function')
        found = _module_bindings(tree)
        if len(found.get(symbol, [])) != 1:
            raise UnsupportedShape('Ambiguous async seam binding')
        function = _unique(tree.body, symbol, ast.AsyncFunctionDef)
        (request,) = _simple_args(function, 1)
        statement = _body(function)
        await_node = statement.value
        call = await_node.value if isinstance(await_node, ast.Await) else None
        if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
                or len(call.args) != 1 or call.keywords or not isinstance(call.args[0], ast.Name)
                or call.args[0].id != request or call.func.id == function.name):
            raise UnsupportedShape('Async strategy requires one awaited named tail call')
        baseline = _unique(tree.body, call.func.id, ast.AsyncFunctionDef)
        if len(found.get(baseline.name, [])) != 1:
            raise UnsupportedShape('Ambiguous async baseline binding')
        _simple_args(baseline, 1)
        replacement = f'await {adapter_name}.invoke_async({baseline.name}, {request})'
    if adapter_name in {n.id for n in ast.walk(function) if isinstance(n, ast.Name)}:
        raise UnsupportedShape('Adapter binding collides with selected function scope')
    # The AST anchor identifies the exact selected statement; source_sha256 binds
    # comments and all surrounding definitions that AST alone would omit.
    if digest(ast.dump(statement, annotate_fields=True, include_attributes=False)) != anchor_sha256:
        raise InputError('Adaptation statement differs from reviewed anchor')
    start, end = _statement(raw, statement.value)
    changed = raw[:start] + replacement.encode('utf-8') + raw[end:]
    ast.parse(changed.decode('utf-8'))
    return {'strategy': {'shape': shape, 'version': SHAPES[shape].version},
            'symbol': symbol, 'baseline_symbol': baseline.name,
            'source_sha256': source_sha256, 'anchor_sha256': anchor_sha256,
            'new_sha256': hashlib.sha256(changed).hexdigest(), 'new_content': changed.decode('utf-8')}


def prepare_reviewed_shape(root: Path, inventory: dict, request: dict) -> dict:
    """Prepare only after source, inventory and separate binding review agree.

    The returned proposal has no apply authority. In particular, an adapter
    digest is a review identity, not evidence that adapter code is trustworthy.
    """
    try:
        jsonschema.Draft202012Validator(REVIEWED_REQUEST_SCHEMA).validate(request)
    except jsonschema.ValidationError as exc:
        raise InputError('Invalid adaptation request at ' + '/'.join(map(str, exc.absolute_path))) from None
    if (digest(inventory) != request['inventory_sha256']
            or inventory.get('scan_fingerprint') != request['inventory_fingerprint']
            or digest(inventory.get('analysis_identity')) != inventory.get('scan_fingerprint')):
        raise InputError('Reviewed inventory identity differs from adaptation request')
    candidates = [c for c in inventory.get('candidates', []) if c.get('candidate_id') == request['candidate_id']]
    if len(candidates) != 1:
        raise InputError('Missing or ambiguous reviewed adaptation candidate')
    candidate = candidates[0]
    source, review = request['source'], candidate.get('semantic_review', {})
    if (candidate.get('tier') == 0 or candidate.get('pattern') == 'NONE'
            or candidate.get('hard_real_time') is True
            or candidate.get('deterministic_alternative') in ('mandatory', 'preferred')
            or review.get('approved') is not True or not review.get('reviewer') or not review.get('reason')
            or review.get('source_sha256') != source['source_sha256']
            or any(candidate.get('source', {}).get(k) != source[k]
                   for k in ('file', 'symbol', 'source_sha256', 'file_sha256'))):
        raise InputError('Current eligible source-matched candidate review is required')
    binding = request['binding_review']
    if binding['source_sha256'] != source['source_sha256']:
        raise InputError('Binding review differs from selected source')
    root = Path(root).resolve(strict=True)
    adapter_records = [row for row in inventory.get('files', [])
                       if row.get('file') == binding['adapter_file']
                       and row.get('sha256') == binding['adapter_sha256']]
    if len(adapter_records) != 1 or binding['adapter_file'] == source['file']:
        raise InputError('Reviewed adapter must be a distinct scanned source file')
    if binding['adapter_file'] != request['adapter_name'] + '.py' or '/' in source['file']:
        raise UnsupportedShape('Preparation currently requires a flat statically imported adapter module')
    for row in inventory.get('files', []) + inventory.get('configuration_evidence', []):
        path = safe_child(root, row['file'])
        if not path.is_file() or file_hash(path) != row['sha256']:
            raise InputError('Reviewed repository snapshot changed')
    path = safe_child(root, source['file'])
    if not path.is_file() or file_hash(path) != source['file_sha256']:
        raise InputError('Selected source changed')
    validate_static_adapter_import(path.read_bytes(), request['adapter_name'])
    adapter_path = safe_child(root, binding['adapter_file'])
    validate_adapter_callback(adapter_path.read_bytes(), request['strategy']['shape'])
    proposal = prepare_shape(path.read_bytes(), shape=request['strategy']['shape'],
                             symbol=source['symbol'], source_sha256=source['file_sha256'],
                             anchor_sha256=source['anchor_sha256'], adapter_name=request['adapter_name'])
    proposal['candidate_id'] = request['candidate_id']
    proposal['source_file'] = source['file']
    proposal['review_digest'] = digest({'semantic_review': review, 'binding_review': binding})
    proposal['request_digest'] = digest(request)
    return proposal


def validate_static_adapter_import(raw: bytes, adapter_name: str) -> None:
    try:
        tree = ast.parse(raw.decode('utf-8'))
    except (UnicodeError, SyntaxError):
        raise UnsupportedShape('Selected adaptation source is not valid UTF-8 Python') from None
    imports = [node for node in tree.body if isinstance(node, ast.Import)
               and len(node.names) == 1 and node.names[0].name == adapter_name
               and node.names[0].asname is None]
    if len(imports) != 1 or len(_module_bindings(tree).get(adapter_name, [])) != 1:
        raise UnsupportedShape('Adapter must be one unambiguous existing static module import')


def validate_adapter_callback(raw: bytes, shape: str) -> None:
    """Check only syntax and obvious placeholders; policy still needs review."""
    try:
        adapter_tree = ast.parse(raw.decode('utf-8'))
    except (UnicodeError, SyntaxError):
        raise UnsupportedShape('Reviewed adapter is not valid UTF-8 Python') from None
    callback_name = 'invoke_async' if shape == 'async-module-tail-call-v1' else 'invoke'
    callback_type = ast.AsyncFunctionDef if callback_name == 'invoke_async' else ast.FunctionDef
    if len(_module_bindings(adapter_tree).get(callback_name, [])) != 1:
        raise UnsupportedShape('Missing or ambiguous reviewed adapter callback')
    callback = _unique(adapter_tree.body, callback_name, callback_type)
    _simple_args(callback, 2)
    if (not callback.body or all(isinstance(n, ast.Pass) or
            (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and n.value.value is Ellipsis)
            for n in callback.body) or
            (len(callback.body) == 1 and isinstance(callback.body[0], ast.Return)
             and isinstance(callback.body[0].value, ast.Constant)
             and callback.body[0].value.value in (None, True, False))):
        raise UnsupportedShape('Placeholder or constant adapter callback is unsupported')
