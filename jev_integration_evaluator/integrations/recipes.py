"""Code-owned recipe contracts and bounded, byte-span Python source transformations."""
from __future__ import annotations

import ast
import codecs
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path
import keyword
import re
import sys

from ..io import InputError, canonical, digest, safe_child
from ..implementation import FORBIDDEN
from .errors import UnsupportedShape, MissingBinding

COMMON = dict(runtime=1, evidence=1, baseline_action=1, registry=1, gate=2, validate=2, blocked=2, guard=1)


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    bindings: dict[str, int]
    contract: str
    version: str = '1.0'
    shape: str = 'module-tail-call-v1'


_DEFS = [
    ('A', 'Before tool execution', {}, 'blocked_zero_executor_calls'),
    ('B', 'Expensive or irreversible action', {'risk': 2}, 'scope_budget_and_irreversible_approval'),
    ('C', 'Registered tool routing', {}, 'final_tool_at_most_once'),
    ('D', 'Retrieval to generation', {'items': 1, 'generate': 2}, 'provenance_and_contradictions_preserved'),
    ('E', 'Post-action verification', {'evidence': 2, 'observe': 1, 'postcondition': 3, 'finish': 3}, 'independent_postcondition_and_no_reexecution'),
    ('F', 'Agent-loop transition', {'attempt': 1}, 'bounded_registered_transition'),
    ('G', 'Planner/executor boundary', {'step_registry': 1, 'finish': 2}, 'bounded_existing_plan_and_per_step_gate'),
    ('H', 'Context retention', {'items': 1, 'retain': 2}, 'pinned_retention_without_compaction'),
    ('I', 'Retry and recovery', {'attempt': 1, 'reserve_retry': 2, 'effect_state': 1, 'completed': 1}, 'bounded_retry_without_completed_effect_replay'),
    ('J', 'Specialist delegation', {'ownership': 2, 'verify_child': 3, 'finish': 3}, 'shared_concurrency_and_child_identity'),
    ('K', 'Code review disposition', {'checks': 1}, 'deterministic_checks_without_publication'),
    ('L', 'Graph identity and mutation', {'revision': 1}, 'revision_and_approval_before_mutation'),
    ('M', 'Final answer validation', {'verify_claims': 1}, 'registered_disposition_without_generation'),
]
RECIPES = {'python.' + letter: Recipe('python.' + letter, title, {**COMMON, **extra}, contract)
           for letter, title, extra, contract in _DEFS}


def recipe_catalog() -> dict:
    return {'schema_version': '1.0', 'language': 'python', 'recipes': [
        {'id': r.id, 'version': r.version, 'title': r.title, 'status': 'implemented_bounded_shape',
         'source_shape': r.shape, 'bindings': r.bindings, 'verification_contract': r.contract}
        for r in RECIPES.values()],
        'unsupported': ['JavaScript/TypeScript rewriting (analysis only)', 'other languages',
                        'methods, nested scopes, decorators, async functions, generators',
                        'branches, multiple statements/call sites, changed signatures, imported/aliased bindings',
                        'non-JSON verification return values; untrusted execution without external isolation']}


def anchor_hash(statement: ast.AST) -> str:
    # Python 3.12 includes an empty ``keywords=[]`` in Call dumps, while later
    # interpreters omit it. Serialize the one supported tail-call shape with
    # explicit fields so packaged review anchors bind across supported versions.
    if (isinstance(statement, ast.Return) and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and len(statement.value.args) == 1 and isinstance(statement.value.args[0], ast.Name)
            and not statement.value.keywords):
        call = statement.value
        function = ast.dump(call.func, annotate_fields=True, include_attributes=False)
        argument = ast.dump(call.args[0], annotate_fields=True, include_attributes=False)
        return digest(f'Return(value=Call(func={function}, args=[{argument}]))')
    return digest(ast.dump(statement, annotate_fields=True, include_attributes=False))


def _module_bindings(tree: ast.Module) -> dict[str, list[ast.AST]]:
    """Collect all possible module-scope stores, including stores in conditionals."""
    found: dict[str, list[ast.AST]] = {}
    def add(name, node):
        found.setdefault(name, []).append(node)
    def visit(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node.name, node)
            # Defaults, decorators and (on some supported interpreters)
            # annotations are evaluated outside the function's local scope.
            # Inspect those expressions, but never treat its body as module code.
            visit(node.args)
            for expression in node.decorator_list:
                visit(expression)
            if node.returns is not None:
                visit(node.returns)
            return
        if isinstance(node, ast.ClassDef):
            add(node.name, node)
            for expression in (*node.decorator_list, *node.bases, *node.keywords):
                visit(expression)
            return
        if isinstance(node, ast.Lambda):
            # A lambda default can rebind its enclosing module; its body cannot.
            visit(node.args)
            return
        if isinstance(node, ast.Import):
            for alias in node.names: add(alias.asname or alias.name.split('.')[0], node)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == '*': raise UnsupportedShape('Unsupported source shape: wildcard imports')
                add(alias.asname or alias.name, node)
        # These bindings are stored as strings, not Name(Store) children.
        # Exception targets are also deleted after the handler completes.
        elif isinstance(node, ast.ExceptHandler) and node.name:
            add(node.name, node)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            add(node.name, node)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            add(node.rest, node)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            add(node.id, node)
        for child in ast.iter_child_nodes(node): visit(child)
    for node in tree.body: visit(node)
    return found


def _function(tree, found, name, arity):
    nodes = found.get(name, [])
    if len(nodes) != 1 or not isinstance(nodes[0], ast.FunctionDef) or nodes[0] not in tree.body:
        raise MissingBinding('Missing or ambiguous top-level function binding: ' + name)
    f = nodes[0]
    if (f.decorator_list or f.args.vararg or f.args.kwarg or f.args.kwonlyargs or f.args.defaults
            or len(f.args.posonlyargs + f.args.args) != arity
            or any(isinstance(n, (ast.Yield, ast.YieldFrom, ast.Await)) for n in ast.walk(f))):
        raise UnsupportedShape('Unsupported function signature/decorator/generator: ' + name)
    return f


def _literal_registry(tree, found, function_name):
    function = _function(tree, found, function_name, 1)
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str): body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        raise UnsupportedShape('Unsupported registry: one return of an explicit module dictionary is required')
    value = body[0].value
    parameters = {arg.arg for arg in function.args.posonlyargs + function.args.args}
    if any(isinstance(node, ast.Name) and node.id in parameters for node in ast.walk(value)):
        raise UnsupportedShape('Unsupported registry: a parameter shadows a required module or built-in symbol')
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'dict' and len(value.args) == 1 and not value.keywords:
        if 'dict' in found: raise UnsupportedShape('Unsupported registry: built-in dict is shadowed')
        value = value.args[0]
    if isinstance(value, ast.Name):
        if len(found.get(value.id, [])) != 1: raise InputError('Ambiguous registry dictionary')
        declarations = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == value.id for t in n.targets)]
        if len(declarations) != 1: raise UnsupportedShape('Unsupported registry dictionary declaration')
        value = declarations[0].value
    if not isinstance(value, ast.Dict) or not 1 <= len(value.keys) <= 255:
        raise UnsupportedShape('Unsupported dynamic registry; explicit finite dictionary keys are required')
    if any(not isinstance(k, ast.Constant) or not isinstance(k.value, str) or not k.value for k in value.keys):
        raise InputError('Registry keys must be explicit nonempty string literals')
    keys = [k.value for k in value.keys]
    if len(set(keys)) != len(keys): raise InputError('Duplicate registry keys')
    return dict(zip(keys, value.values))


def _validate_registry_contract(tree, found, spec):
    registry = _literal_registry(tree, found, spec['bindings']['registry'])
    mapped = {v for v in spec['label_actions'].values() if v is not None}
    if not mapped <= set(registry): raise InputError('Assessment translation references an unregistered host consequence')
    pattern = spec['recipe']['id'].split('.')[-1]
    if pattern in ('A','B','C','I','J','L'):
        for value in registry.values():
            if not isinstance(value, ast.Name): raise InputError('Action registry values must name existing functions')
            _function(tree, found, value.id, 1)
    elif pattern in ('D','G','H'):
        try: values = {k: ast.literal_eval(v) for k,v in registry.items()}
        except (ValueError,TypeError,RecursionError): raise InputError('Selection/plan registry must contain explicit finite ID lists') from None
        if any(not isinstance(v,(list,tuple)) or not all(isinstance(x,str) for x in v) or len(v)!=len(set(v)) for v in values.values()):
            raise InputError('Selection/plan options must be unique finite ID lists')
        if pattern == 'G':
            steps = _literal_registry(tree, found, spec['bindings']['step_registry'])
            if any(not 1 <= len(v) <= spec['policy']['max_steps'] or not set(v) <= set(steps) for v in values.values()):
                raise InputError('Plan option exceeds bounds or references an unknown step')
            for value in steps.values():
                if not isinstance(value, ast.Name): raise InputError('Step registry must contain existing callable symbols')
                _function(tree, found, value.id, 1)
    else:
        try: values = {k:ast.literal_eval(v) for k,v in registry.items()}
        except (ValueError,TypeError,RecursionError): raise InputError('Disposition registry must contain literal values') from None
        allowed = {'F':('continue','stop','inspect'),'K':('accept','inspect','comment','request_changes'),'M':('accept','inspect','revise')}
        if pattern in allowed and any(v not in allowed[pattern] for v in values.values()):
            raise InputError('Disposition registry contains an unsupported consequence')
        if pattern == 'F' and 'stop' not in values.values(): raise InputError('Agent transition registry needs an existing stop option')
        if pattern in ('K','M'):
            key = spec['policy']['failed_checks_action' if pattern=='K' else 'failed_claims_action']
            if key not in values or values[key]=='accept': raise InputError('Failed independent checks cannot map to acceptance')
        if pattern == 'E' and not {spec['policy']['success_action'],spec['policy']['failure_action']} <= set(values):
            raise InputError('Postcondition dispositions are not registered')
    if pattern=='L':
        policy=spec['policy']
        if set(spec['label_actions']) != {'same','related','different','uncertain'}:
            raise InputError('Graph recipe requires explicit same/related/different/uncertain semantics')
        if (set(policy['mutating_actions']) & set(policy['nonmutating_actions']) or
                not set(policy['mutating_actions'] + policy['nonmutating_actions']) <= set(registry)):
            raise InputError('Invalid graph consequence policy')
    return sorted(registry)


def transform(root: Path, spec: dict) -> dict:
    """Read and parse only. Return exact host and owned-adapter changes; never write a target."""
    r = RECIPES[spec['recipe']['id']]
    roles = set(spec['bindings'])
    missing, extra = set(r.bindings) - roles, roles - set(r.bindings)
    if missing: raise MissingBinding('Missing bindings: ' + ', '.join(sorted(missing)))
    if extra: raise InputError('Unexpected recipe bindings: ' + ', '.join(sorted(extra)))
    rel = spec['source']['file']
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*\.py', rel) or keyword.iskeyword(Path(rel).stem):
        raise UnsupportedShape('Unsupported source shape: use a flat Python module at the target root')
    reserved_modules = set(sys.stdlib_module_names) | {'jev_integration_evaluator','jsonschema','yaml'}
    if Path(rel).stem in reserved_modules or spec['output']['module'] in reserved_modules:
        raise UnsupportedShape('Unsupported module import collision with trusted runtime/standard-library names')
    output = spec['output']['module'] + '.py'
    if keyword.iskeyword(spec['output']['module']) or FORBIDDEN.search(rel) or FORBIDDEN.search(output):
        raise InputError('Protected or invalid implementation output path')
    p, new_module = safe_child(root, rel), safe_child(root, output)
    if new_module.exists(): raise InputError('Integration-owned output already exists; do not overwrite it')
    raw = p.read_bytes()
    if len(raw) > 2_000_000 or raw.startswith(b'\xef\xbb\xbf'):
        raise UnsupportedShape('Unsupported oversized/BOM source; UTF-8 without BOM is required')
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        if codecs.lookup(encoding).name != 'utf-8':
            raise UnsupportedShape('Unsupported source encoding: UTF-8 is required')
    except (SyntaxError, LookupError):
        raise UnsupportedShape('Unsupported or invalid source encoding: UTF-8 is required') from None
    try:
        text = raw.decode('utf-8')
        tree = ast.parse(text, filename=rel)
    except (UnicodeError, SyntaxError):
        raise InputError('Source must be valid UTF-8 Python') from None
    found = _module_bindings(tree)
    f = _function(tree, found, spec['source']['symbol'], 1)
    body = f.body[:]
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
        raise UnsupportedShape('Unsupported source shape: one direct tail-call return is required')
    statement, call = body[0], body[0].value
    parameter = (f.args.posonlyargs + f.args.args)[0].arg
    if (not isinstance(call.func, ast.Name) or len(call.args) != 1 or call.keywords
            or not isinstance(call.args[0], ast.Name) or call.args[0].id != parameter):
        raise UnsupportedShape('Unsupported call: one unchanged input parameter and a named baseline function required')
    if anchor_hash(statement) != spec['source']['anchor_sha256']:
        raise InputError('AST statement anchor differs from the reviewed binding')
    _function(tree, found, spec['verification']['entry_point'], 1)
    for effect in spec['verification']['effect_symbols']:
        nodes = found.get(effect, [])
        if len(nodes) != 1 or not isinstance(nodes[0], ast.FunctionDef) or nodes[0] not in tree.body:
            raise InputError('Effect observation must identify an existing top-level function')
    original = call.func.id
    if parameter in {original, *spec['bindings'].values()}:
        raise UnsupportedShape('Unsupported seam: a parameter shadows a required module symbol')
    _function(tree, found, original, 1)
    if original == f.name: raise UnsupportedShape('Unsupported recursive seam')
    for role, arity in r.bindings.items():
        _function(tree, found, spec['bindings'][role], arity)
        if spec['bindings'][role] == f.name:
            raise InputError('A host binding cannot recursively invoke the selected seam')
    registered_actions = _validate_registry_contract(tree, found, spec)
    # Bind effect observation to the parsed executable registry, not a caller-selected
    # irrelevant function whose zero calls could conceal an actual side effect.
    pattern = r.id.split('.')[-1]
    observed = set(spec['verification']['effect_symbols'])
    if pattern in ('A','B','C','I','J','L'):
        expected_effects = {v.id for v in _literal_registry(tree, found, spec['bindings']['registry']).values()}
    elif pattern == 'G':
        expected_effects = {v.id for v in _literal_registry(tree, found, spec['bindings']['step_registry']).values()}
    elif pattern in ('D','H'):
        expected_effects = {spec['bindings']['generate' if pattern=='D' else 'retain']}
    elif pattern == 'E':
        baseline = _function(tree, found, original, 1)
        statements = baseline.body[:]
        if statements and isinstance(statements[0], ast.Expr) and isinstance(statements[0].value, ast.Constant) and isinstance(statements[0].value.value, str):
            statements = statements[1:]
        operation = statements[0].value if len(statements)==1 and isinstance(statements[0], ast.Return) else None
        argument = (baseline.args.posonlyargs + baseline.args.args)[0].arg
        if (not isinstance(operation, ast.Call) or not isinstance(operation.func, ast.Name)
                or len(operation.args)!=1 or operation.keywords
                or not isinstance(operation.args[0], ast.Name) or operation.args[0].id!=argument):
            raise UnsupportedShape('Unsupported post-action baseline: one named executor tail call is required')
        if operation.func.id == argument:
            raise UnsupportedShape('Unsupported post-action baseline: a parameter shadows the executor')
        _function(tree, found, operation.func.id, 1)
        expected_effects = {operation.func.id}
    else:
        expected_effects = observed  # F observes its bounded caller loop; K/M return dispositions only.
    if observed != expected_effects:
        raise InputError('Effect observations must exactly cover the parsed executor/consumer registry')
    alias = '_jev_invoke_' + digest(spec)[:16]
    if alias in found or alias == parameter: raise InputError('Generated import alias conflicts with an existing symbol')
    # AST offsets are UTF-8 byte offsets, not Unicode character offsets.
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines: offsets.append(offsets[-1] + len(line))
    start = offsets[call.lineno - 1] + call.col_offset
    end = offsets[call.end_lineno - 1] + call.end_col_offset
    bindings = ', '.join(role + '=' + spec['bindings'][role] for role in sorted(r.bindings))
    replacement = f'{alias}({original}, {parameter}, {bindings})'.encode()
    changed = raw[:start] + replacement + raw[end:]
    newline = b'\r\n' if b'\r\n' in raw else b'\n'
    if b'\r' in raw.replace(b'\r\n', b''):
        raise UnsupportedShape('Unsupported bare-CR newline convention')
    # Insert after module docstring/future imports and preserve shebang/encoding comments.
    insertion = 0
    for node in tree.body:
        is_doc = (node is tree.body[0] and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                  and isinstance(node.value.value, str))
        if is_doc or (isinstance(node, ast.ImportFrom) and node.module == '__future__'):
            insertion = offsets[node.end_lineno]
        else:
            first_line = node.lineno
            if getattr(node, 'decorator_list', []):
                # Decorator AST spans omit the opening @ and parentheses. Locate
                # the first real @ token after the docstring/future-import prefix,
                # including when the decorator expression starts on a later line.
                first_line = next(token.start[0] for token in tokenize.tokenize(io.BytesIO(raw).readline)
                                  if token.type == tokenize.OP and token.string == '@'
                                  and token.start[0] < node.lineno
                                  and offsets[token.start[0] - 1] >= insertion)
            insertion = max(insertion, offsets[first_line - 1])
            break
    import_line = f'from {spec["output"]["module"]} import invoke as {alias}'.encode() + newline
    changed = changed[:insertion] + import_line + changed[insertion:]
    host = changed.decode('utf-8')
    ast.parse(host, filename=rel)
    runtime_spec = {k: spec[k] for k in ('candidate_id', 'experiment_id', 'source', 'recipe', 'questions',
                                        'primary_question', 'evidence_question', 'label_actions', 'runtime', 'policy')}
    runtime_spec['registered_action_ids'] = registered_actions
    adapter = _adapter(runtime_spec)
    ast.parse(adapter, filename=output)
    return {'changes': [{'file': rel, 'new_content': host}, {'file': output, 'new_content': adapter}],
            'entry_point': f'{Path(rel).stem}:{f.name}', 'baseline_symbol': original,
            'adapter_symbol': f'{spec["output"]["module"]}:invoke', 'binding_digest': digest(spec['bindings']),
            'source_shape': r.shape, 'recipe_contract': r.contract,
            'required_bindings': sorted(r.bindings), 'imports_resolved_by': 'installed evaluator wheel when enabled'}


def _adapter(spec):
    return f'''"""Generated bounded host integration. Feature off; activation requires a separate host receipt."""
SPEC = {spec!r}
ENABLED = False

def invoke(original, request, **bindings):
    if ENABLED is not True:
        return original(request)
    from jev_integration_evaluator.integrations.host import invoke_bound
    return invoke_bound(SPEC, original, request, bindings)

def create_router(client, *, budget_coordinator, audit_log, runtime_config=None, activation=None, thresholds=None):
    from jev_integration_evaluator.runtime import SafeRouter
    from jev_integration_evaluator.budget import BudgetCoordinator
    if not isinstance(budget_coordinator, BudgetCoordinator) or audit_log is None:
        raise ValueError("A shared host-owned coordinator and audit sink are required")
    return SafeRouter(client, runtime_config or SPEC["runtime"]["configuration"],
                      policy_version=SPEC["runtime"]["policy_version"], thresholds=thresholds,
                      activation=activation, audit_log=audit_log, budget_coordinator=budget_coordinator,
                      canary_scope=SPEC["runtime"]["canary_scope"], require_expiring_activation=True,
                      require_runtime_binding=True)

def contract_hash(router):
    return router.runtime_contract_hash(SPEC["questions"], SPEC["primary_question"], SPEC["evidence_question"],
                                        label_actions=SPEC["label_actions"])
'''
