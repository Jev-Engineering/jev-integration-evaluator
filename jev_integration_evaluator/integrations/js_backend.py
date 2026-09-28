"""Trusted, non-executing JavaScript/TypeScript source transformation boundary."""
from __future__ import annotations

import hashlib
import json
import os
import re
from importlib.resources import files
from pathlib import Path
import shutil
import subprocess

from ..io import InputError, file_hash, safe_child


def js_support_matrix() -> dict:
    """Static capability contract, not a claim about an arbitrary target."""
    return dict(schema_version='1.0', implementation_contract='javascript-owned-bundle-v1',
                discovery_contract='python-static-capabilities-v1',
                discovery_js_ts='unparsed_by_this_contract',
                supported_recipe='C', supported_formats=['esm', 'commonjs', 'typescript'],
                owned_bundle_platforms=['linux'], unsupported_platforms=['windows', 'darwin'],
                unsupported_recipes=[letter for letter in 'ABCDEFGHIJKLM' if letter != 'C'],
                runtime_strategy='native_javascript_default_off',
                qualification_scope='synthetic_installed_wheel_entrypoints',
                target_verified=False, provider_connectivity='not_tested', activation_authorized=False)


def trusted_js_tool_identity(tooling_dir: Path) -> dict:
    """Pin executable and package tooling bytes outside any target."""
    tool_root = Path(tooling_dir).resolve(strict=True)
    compiler = (tool_root / 'node_modules/typescript/lib/typescript.js').resolve(strict=True)
    node_name = shutil.which('node')
    if (not compiler.is_file() or not compiler.is_relative_to(tool_root)
            or node_name is None):
        raise InputError('Pinned trusted JavaScript tooling unavailable')
    node = Path(node_name).resolve(strict=True)
    if not node.is_file():
        raise InputError('Pinned trusted JavaScript tooling unavailable')
    data = Path(str(files('jev_integration_evaluator').joinpath('data')))
    return dict(node_path=str(node), node_sha256=file_hash(node),
                compiler_path=str(compiler), compiler_sha256=file_hash(compiler),
                compiler_version='5.8.3', transformer_sha256=file_hash(data / 'js_transform.cjs'),
                runtime_sha256=file_hash(data / 'native_js_runtime.cjs'),
                probe_sha256=file_hash(data / 'js_probe.cjs'),
                emitter_sha256=file_hash(data / 'js_emit.cjs'),
                backend_sha256=file_hash(Path(__file__)),
                lifecycle_sha256=file_hash(Path(__file__).with_name('js_lifecycle.py')))


def transform_js_source(root: Path, source_file: str, *, symbol: str, original: str,
                        adapter_alias: str, adapter_path: str, bindings: dict[str, str],
                        tooling_dir: Path) -> dict:
    """Use a pinned compiler outside the target; never load target config/plugins.

    The returned bytes are a proposal only. A separate reviewed bundle must bind
    them to the original source and exact runtime files before any target write.
    """
    root = Path(root).resolve(strict=True)
    tool_root = Path(tooling_dir).resolve(strict=True)
    if tool_root == root or tool_root.is_relative_to(root):
        raise InputError('Trusted TypeScript tooling must be outside the target')
    compiler = tool_root / 'node_modules' / 'typescript' / 'lib' / 'typescript.js'
    try:
        real_compiler = compiler.resolve(strict=True)
    except OSError:
        raise InputError('Pinned trusted TypeScript compiler unavailable') from None
    if (not real_compiler.is_file() or not real_compiler.is_relative_to(tool_root)
            or real_compiler.is_relative_to(root)):
        raise InputError('Pinned trusted TypeScript compiler unavailable')
    node = shutil.which('node')
    if node is None or Path(node).resolve().is_relative_to(root):
        raise InputError('Trusted Node runtime unavailable')
    source_path = safe_child(root, source_file)
    if not source_path.is_file() or source_path.stat().st_size > 500_000:
        raise InputError('Unsupported JavaScript source file')
    raw = source_path.read_bytes()
    try:
        source = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise InputError('JavaScript source must be UTF-8') from None
    helper = Path(str(files('jev_integration_evaluator').joinpath('data/js_transform.cjs')))
    if helper.resolve(strict=True).is_relative_to(root):
        raise InputError('Trusted transformer must be outside the target')
    request = dict(file=source_file, source=source, symbol=symbol, original=original,
                   adapter_alias=adapter_alias, adapter_path=adapter_path, bindings=bindings)
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in {'NODE_PATH', 'NODE_OPTIONS', 'NPM_CONFIG_PREFIX', 'NPM_CONFIG_USERCONFIG'}}
    env['JEV_TRUSTED_TYPESCRIPT'] = str(real_compiler)
    try:
        result = subprocess.run([str(node), str(helper)], input=json.dumps(request), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=helper.parent, env=env, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise InputError('Trusted JavaScript transformer unavailable') from None
    if result.returncode != 0 or len(result.stdout) > 2_000_000:
        # Never surface parser output or source excerpts in diagnostics.
        raise InputError('Unsupported or invalid trusted JavaScript transform')
    try:
        output = json.loads(result.stdout)
        generated = output['transformed_source']
        if (output['source_sha256'] != hashlib.sha256(raw).hexdigest()
                or output['generated_sha256'] != hashlib.sha256(generated.encode('utf-8')).hexdigest()
                or output['compiler_version'] != '5.8.3'
                or output['selected_symbol'] != symbol or output['original_symbol'] != original
                or output['format'] not in {'esm', 'commonjs', 'typescript'}
                or (output['format'] == 'typescript' and (
                    type(output['emitted_source']) is not str or
                    output['emitted_sha256'] != hashlib.sha256(
                        output['emitted_source'].encode('utf-8')).hexdigest()))
                or (output['format'] != 'typescript' and (
                    output['emitted_source'] is not None or output['emitted_sha256'] is not None))):
            raise ValueError('mismatch')
    except (KeyError, TypeError, ValueError, UnicodeEncodeError):
        raise InputError('Trusted JavaScript transform result invalid') from None
    return output


def render_js_adapter(spec: dict, *, runtime_path: str = './jev_runtime.cjs') -> str:
    """Render a default-off CJS adapter; host startup supplies all live owners."""
    if (type(spec) is not dict or set(spec) != {
            'recipe_id', 'candidate_id', 'source_sha256', 'applied_source_sha256',
            'executed_source_sha256', 'source_file', 'executed_file', 'registered_action_ids',
            'questions', 'primary_question', 'label_actions', 'runtime'}
            or spec['recipe_id'] != 'javascript.C' or type(spec['runtime']) is not dict
            or spec['runtime'].get('mode') != 'off'
            or runtime_path != './jev_runtime.cjs'
            or any(not isinstance(spec.get(key), str) or not re.fullmatch(r'[A-Za-z_$][\w$-]*\.(?:mjs|cjs|ts)', spec[key])
                   for key in ('source_file', 'executed_file'))
            or any(not isinstance(spec.get(key), str) or not re.fullmatch('[a-f0-9]{64}', spec[key])
                   for key in ('applied_source_sha256', 'executed_source_sha256'))):
        raise InputError('Invalid bounded JavaScript adapter specification')
    try:
        encoded = json.dumps(spec, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                             allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise InputError('Invalid bounded JavaScript adapter specification') from None
    if len(encoded.encode('utf-8')) > 120_000:
        raise InputError('JavaScript adapter specification exceeds byte bound')
    # JSON literal cannot execute proposal text. NativeRouter performs its own
    # strict semantic validation when the host starts or first invokes off mode.
    return f'''// Generated reviewed recipe C adapter. Default mode is off.
'use strict';
const {{NativeRouter, SharedBudget}} = require({json.dumps(runtime_path)});
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const SPEC = Object.freeze(JSON.parse({json.dumps(encoded, ensure_ascii=False)}));
const SPEC_SHA256 = {json.dumps(hashlib.sha256(encoded.encode('utf-8')).hexdigest())};
let owner = null;
function attestSource() {{
  for (const [file, expected] of [[SPEC.source_file, SPEC.applied_source_sha256],
                                  [SPEC.executed_file, SPEC.executed_source_sha256]]) {{
    const actual = crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname, file))).digest('hex');
    if (actual !== expected) throw Error('applied_host_source_changed');
  }}
  return SPEC.executed_source_sha256;
}}
const defaultAudit = {{events: [], append(event) {{
  if (this.events.length >= 1024) throw Error('default_audit_full');
  this.events.push(event);
}}}};
function initialize(options = {{}}) {{
  if (owner !== null) throw Error('runtime_already_started');
  attestSource();
  const budget = options.budget || new SharedBudget({{max_calls: 1, max_cost: 1}});
  owner = new NativeRouter({{spec: SPEC, budget, audit: options.audit || defaultAudit,
    client: options.client || null, mode: options.mode || 'off',
    activation: options.activation || null,
    trusted_activation_sha256: options.trusted_activation_sha256 || null,
    sourceAttest: attestSource,
    now: options.now || (() => Date.now())}});
  return owner;
}}
function invoke(original, request, bindings, options) {{
  if (owner === null) initialize();
  return owner.invoke(original, request, bindings, options);
}}
function completeTask(taskId) {{ if (owner === null) throw Error('runtime_not_started'); owner.budget.closeTask(taskId); }}
function close() {{ if (owner !== null) owner.close(); }}
module.exports = Object.freeze({{SPEC, SPEC_SHA256, initialize, invoke, completeTask, close}});
'''
