"""Reviewed two-placement Python console composition for one finite task.

Only a same-package, two-script, single-request shape is supported. Planning
parses target source and emits bytes; it never imports or executes target code.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re

from ..io import InputError, digest
from .errors import UnsupportedShape
from .python_entrypoint import _source, _function, inspect_entrypoint


_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


def render_composite_console(root: Path, selection: dict, specs: dict) -> tuple[str, dict]:
    """Replace the primary console task call with one shared-runtime journey.

    The primary reviewed console script is the launch command. The secondary
    script establishes an independently source-bound caller; its own body is
    left unchanged. Both placements must have separate host modules and
    deterministic zero-returning finite task calls.
    """
    ids = selection['candidate_ids']
    if len(ids) != 2 or ids != sorted(set(ids)) or set(ids) != set(specs):
        raise UnsupportedShape('Composite console requires exactly two ordered reviewed placements')
    primary, secondary = (specs[identifier] for identifier in ids)
    contracts = []
    for spec in (primary, secondary):
        binding = spec.get('entrypoint_binding')
        if not isinstance(binding, dict):
            raise UnsupportedShape('Composite placement lacks a reviewed console binding')
        fresh = inspect_entrypoint(root, spec,
                                   {key: binding[key] for key in ('version', 'script', 'startup_inputs')})
        if fresh != binding or fresh['kind'] != 'single-request-v1':
            raise UnsupportedShape('Composite console binding drift or unsupported task loop')
        contracts.append(fresh)
    first, second = contracts
    if (first['file'] != second['file'] or first['function'] == second['function']
            or first['script'] == second['script']):
        raise UnsupportedShape('Composite console requires two distinct scripts and callers')
    entry_path = Path(first['file'])
    host_paths = [Path(spec['source']['file']) for spec in (primary, secondary)]
    if (any(path.parent != entry_path.parent for path in host_paths)
            or len(set(host_paths)) != 2 or
            any(not _SYMBOL.fullmatch(path.stem) for path in host_paths)):
        raise UnsupportedShape('Composite host modules must be distinct in the console package')
    modules = []
    for spec in (primary, secondary):
        name = spec['output']['module']
        if not _SYMBOL.fullmatch(name):
            raise UnsupportedShape('Composite adapter module name unsupported')
        modules.append(name)
    if len(set(modules)) != 2:
        raise UnsupportedShape('Composite adapter modules must be distinct')
    if primary['runtime']['task_field'] != secondary['runtime']['task_field']:
        raise UnsupportedShape('Composite placements disagree on task identity')
    expected = {}
    for spec, host_path in zip((primary, secondary), host_paths):
        for row in spec['runtime_files']:
            path = host_path.parent / Path(row['file']).name
            if path != Path(row['file']):
                raise UnsupportedShape('Composite runtime file escaped reviewed host package')
            sha = hashlib.sha256(row['new_content'].encode('utf-8')).hexdigest()
            if str(path) in expected and expected[str(path)] != sha:
                raise UnsupportedShape('Composite runtime file contents conflict')
            expected[str(path)] = sha
    raw, tree = _source(root, first['file'])
    # Only this separately reviewed host revision may carry the installed
    # connected options through generated composition. The legacy dual host
    # keeps its original rendered bytes and off-only guard.
    loader = root / 'src/registered_dual/connected_authority.py'
    loader_anchored = (loader.is_file()
                       and not any(path.is_symlink() for path in
                                   (loader, loader.parent, loader.parent.parent))
                       and loader.resolve(strict=True).is_relative_to(root.resolve(strict=True)))
    connected_capable = (
        ids == ['JEV-DA938C3C7965', 'JEV-EDF19BDB65F0']
        and first['file'] == 'src/registered_dual/console.py'
        and hashlib.sha256(raw).hexdigest() in (
            'bf3516e197d2ca6cc90514edd663125d0593003c274185d60b0f3e94e47c1dd9',
            # Authored two-task, four-call synthetic generation consoles.
            'b989858b85486ffd6752585269968142ef09e146e61269a11416195b2cf0f144',
            'e42159ca02c231a9374e3b8c71aaeeafe0c887ff1812c8a0381b5498f62d04d6')
        and loader_anchored
        and hashlib.sha256(loader.read_bytes()).hexdigest() ==
            '406cec77bbe986efbada92d1f7385042b43714f2f9fcc1dab88015905be67a68')
    generation_capable = connected_capable and hashlib.sha256(raw).hexdigest() in (
        'b989858b85486ffd6752585269968142ef09e146e61269a11416195b2cf0f144',
        'e42159ca02c231a9374e3b8c71aaeeafe0c887ff1812c8a0381b5498f62d04d6')
    entry = _function(tree, first['function'], 0)
    _function(tree, 'observe_composite_runtime', 3)
    statement = entry.body[-1]
    if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
        raise UnsupportedShape('Composite primary console task call changed')
    suffix = digest({'selection': selection, 'contracts': contracts})[:12]
    prefix = '_jev_composite_' + suffix
    if prefix in raw.decode('utf-8'):
        raise UnsupportedShape('Composite generated symbol conflicts with host source')
    names = {'runtime': prefix + '_runtime', 'opts': prefix + '_opts',
             'task_id': prefix + '_task_id', 'error': prefix + '_error',
             'prior': prefix + '_prior', 'plans': prefix + '_plans',
             'files': prefix + '_files', 'limits': prefix + '_limits'}
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    start = offsets[statement.lineno - 1] + statement.col_offset
    end = offsets[statement.end_lineno - 1] + statement.end_col_offset
    indentation = raw[offsets[statement.lineno - 1]:start].decode('utf-8')
    newline = '\r\n' if b'\r\n' in raw else '\n'
    if b'\r' in raw.replace(b'\r\n', b''):
        raise UnsupportedShape('Composite console bare-CR newline unsupported')
    a, b = first['startup_inputs'], second['startup_inputs']
    task = first['request_symbol']
    host_a, host_b = (prefix + '_host_a', prefix + '_host_b')
    adapter_a, adapter_b = (prefix + '_adapter_a', prefix + '_adapter_b')
    expected_runtime = {Path(path).name: sha for path, sha in expected.items()}
    # All source-controlled names and values were checked before embedding.
    code = [
        f'if type({task}) is not dict or type({task}.get({primary["runtime"]["task_field"]!r})) is not str or not {task}[{primary["runtime"]["task_field"]!r}]:',
        '    raise ValueError("invalid_stable_task_identity")',
        f'{names["task_id"]} = {task}[{primary["runtime"]["task_field"]!r}]',
        'from pathlib import Path as ' + prefix + '_Path',
        'import sys as ' + prefix + '_sys',
        f'from . import {host_paths[0].stem} as {host_a}',
        f'from . import {host_paths[1].stem} as {host_b}',
        f'from . import {modules[0]} as {adapter_a}',
        f'from . import {modules[1]} as {adapter_b}',
        'from jev_integration_evaluator.integrations.runtime_lifecycle import HostRuntimeLifecycle as ' + prefix + '_HostRuntimeLifecycle',
        f'{names["limits"]} = {a["budget_limits"]}()',
        f'if {names["limits"]} != {b["budget_limits"]}():',
        '    raise RuntimeError("composite_shared_budget_mismatch")',
        f'if type({names["limits"]}) is not dict or any({names["limits"]}.get(key) != value for key, value in { {k: selection["shared_runtime"][k] for k in ("max_calls_per_task", "max_cost_per_task")}!r}.items()):',
        '    raise RuntimeError("composite_reviewed_budget_mismatch")',
        f'{names["plans"]} = ({a["dependency_plan"]}(), {b["dependency_plan"]}())',
        f'if any(type(plan) is not dict or set(plan) != {{"files"}} or type(plan["files"]) is not list for plan in {names["plans"]}):',
        '    raise RuntimeError("composite_dependency_plan_invalid")',
        f'{names["files"]} = {{row["path"]: row["sha256"] for plan in {names["plans"]} for row in plan["files"]}}',
        f'if any({names["files"]}.get(row["path"]) != row["sha256"] for plan in {names["plans"]} for row in plan["files"]):',
        '    raise RuntimeError("composite_dependency_plan_conflict")',
        f'if {names["files"]} != {{str({prefix}_Path(__file__).resolve().parent / name): sha for name, sha in {expected_runtime!r}.items()}}:',
        '    raise RuntimeError("composite_dependency_plan_drift")',
        f'{names["opts"]} = {a["startup_options"]}()',
        *([
            f'if type({names["opts"]}) is not dict:',
            '    raise RuntimeError("composite_connected_profile_unqualified")',
            f'{names["opts"]} = dict({names["opts"]})',
            f'{prefix}_connected = {names["opts"]}.get("connected_config") is not None',
            f'if {prefix}_connected and {names["opts"]}.get("startup_mode") != "shadow":',
            '    raise RuntimeError("composite_connected_profile_unqualified")',
            f'{prefix}_enabled = (True if {prefix}_connected else '
            f'{names["opts"]}.pop("enable_experiment", False))',
            f'if type({prefix}_enabled) is not bool or ({prefix}_enabled and {names["opts"]}.get("startup_mode") != "shadow"):',
            '    raise RuntimeError("composite_synthetic_shadow_authority_required")',
        ] if connected_capable else [
            f'if type({names["opts"]}) is not dict or {names["opts"]}.get("connected_config") is not None:',
            '    raise RuntimeError("composite_connected_profile_unqualified")',
            f'{names["opts"]} = dict({names["opts"]})',
            f'{prefix}_enabled = {names["opts"]}.pop("enable_experiment", False)',
            f'if type({prefix}_enabled) is not bool or ({prefix}_enabled and {names["opts"]}.get("startup_mode") != "shadow"):',
            '    raise RuntimeError("composite_synthetic_shadow_authority_required")',
        ]),
        f'{names["runtime"]} = {prefix}_HostRuntimeLifecycle({{{ids[0]!r}: {adapter_a}, {ids[1]!r}: {adapter_b}}},',
        f'    budget_limits={names["limits"]}, audit_log={a["audit_log"]}(),',
        f'    dependency_plan={{"files": [{{"path": path, "sha256": sha}} for path, sha in sorted({names["files"]}.items())]}}, **{names["opts"]})',
        f'{names["prior"]} = ({host_a}.{primary["bindings"]["runtime"]}, {host_b}.{secondary["bindings"]["runtime"]})',
        'try:',
        f'    {host_a}.{primary["bindings"]["runtime"]} = {names["runtime"]}.runtime_binding({ids[0]!r})',
        f'    {host_b}.{secondary["bindings"]["runtime"]} = {names["runtime"]}.runtime_binding({ids[1]!r})',
        f'    {adapter_a}.ENABLED = {prefix}_enabled',
        f'    {adapter_b}.ENABLED = {prefix}_enabled',
        *([
            f'    {prefix}_refused = []',
            f'    for {prefix}_placement in {ids!r}:',
            '        try:',
            f'            {names["runtime"]}.router({prefix}_placement, {task})',
            f'        except Exception as {prefix}_denied:',
            f'            if str({prefix}_denied) != "task_closed_or_budget_suspended":',
            '                raise',
            f'            {prefix}_refused.append({prefix}_placement)',
            f'            {a["audit_log"]}().append({{"type": "runtime_route_refusal", "candidate_id": {prefix}_placement, "reason": "task_closed_or_budget_suspended"}})',
            f'    if {prefix}_refused:',
            '        raise RuntimeError("composite_task_closed_or_budget_suspended")',
        ] if connected_capable and hashlib.sha256(raw).hexdigest() in (
            'b989858b85486ffd6752585269968142ef09e146e61269a11416195b2cf0f144',
            'e42159ca02c231a9374e3b8c71aaeeafe0c887ff1812c8a0381b5498f62d04d6') else []),
        *([
            f'    from jev_integration_evaluator.io import digest as {prefix}_digest',
            f'    {prefix}_claim = ({names["runtime"]}.coordinator.claim_effect({names["task_id"]}, {prefix}_digest({task}), {ids[0]!r}, {('owner:' + first["task_symbol"])!r}) if {prefix}_connected else None)',
        ] if generation_capable else []),
        f'    if {first["task_symbol"]}({task}) != 0:',
        '        raise RuntimeError("composite_primary_task_failed")',
        f'    if type({task}) is not dict or {task}.get({primary["runtime"]["task_field"]!r}) != {names["task_id"]}:',
        '        raise RuntimeError("task_identity_changed")',
        *([
            f'    if {prefix}_claim is not None:',
            f'        {names["runtime"]}.coordinator.complete_effect({prefix}_claim)',
        ] if generation_capable else []),
        *([
            f'    if {prefix}_connected:',
            f'        {prefix}_settle = {names["runtime"]}.router({ids[0]!r}, {task})',
            f'        with {prefix}_settle.lock:',
            f'            {prefix}_pending = tuple({prefix}_settle.futures)',
            f'        for {prefix}_future in {prefix}_pending:',
            f'            {prefix}_future.result(timeout=10)',
        ] if connected_capable and hashlib.sha256(raw).hexdigest() in (
            'b989858b85486ffd6752585269968142ef09e146e61269a11416195b2cf0f144',
            'e42159ca02c231a9374e3b8c71aaeeafe0c887ff1812c8a0381b5498f62d04d6') else []),
        *([
            f'    from jev_integration_evaluator.io import digest as {prefix}_digest',
            f'    {prefix}_claim = ({names["runtime"]}.coordinator.claim_effect({names["task_id"]}, {prefix}_digest({task}), {ids[1]!r}, {('owner:' + second["task_symbol"])!r}) if {prefix}_connected else None)',
        ] if generation_capable else []),
        f'    if {host_b}.{second["task_symbol"]}({task}) != 0:',
        '        raise RuntimeError("composite_secondary_task_failed")',
        f'    if type({task}) is not dict or {task}.get({primary["runtime"]["task_field"]!r}) != {names["task_id"]}:',
        '        raise RuntimeError("task_identity_changed")',
        *([
            f'    if {prefix}_claim is not None:',
            f'        {names["runtime"]}.coordinator.complete_effect({prefix}_claim)',
        ] if generation_capable else []),
        f'    observe_composite_runtime({names["runtime"]}, {task}, {tuple(ids)!r})',
        '    return 0',
        'finally:',
        f'    {names["error"]} = {prefix}_sys.exc_info()[0] is not None',
        f'    {adapter_a}.ENABLED = False',
        f'    {adapter_b}.ENABLED = False',
        f'    {host_a}.{primary["bindings"]["runtime"]}, {host_b}.{secondary["bindings"]["runtime"]} = {names["prior"]}',
        '    try:',
        f'        {names["runtime"]}.complete_task({names["task_id"]})',
        '    except BaseException:',
        f'        if not {names["error"]}: raise',
        '    finally:',
        f'        {names["runtime"]}.close()',
    ]
    replacement = (newline + indentation).join(code).encode('utf-8')
    result = raw[:start] + replacement + raw[end:]
    try:
        ast.parse(result.decode('utf-8'), filename=first['file'])
    except (SyntaxError, UnicodeError):
        raise InputError('Composite console render did not parse') from None
    report = {'version': '1.0', 'profile': 'two-placement-single-request-v1',
              'script': first['script'], 'file': first['file'],
              'file_sha256': hashlib.sha256(result).hexdigest(),
              'pyproject_sha256': first['pyproject_sha256'],
              'candidate_ids': ids, 'selected_set_digest': digest(selection),
              'original_file_sha256': first['file_sha256']}
    return result.decode('utf-8'), report
