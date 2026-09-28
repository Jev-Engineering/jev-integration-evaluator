"""Actual edited synthetic JS/TS host entrypoints under Node, default off."""
from importlib.resources import files
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from jev_integration_evaluator.integrations.js_backend import (
    render_js_adapter, transform_js_source)


TOOLING = Path(__file__).resolve().parents[1]
PINNED = TOOLING / 'node_modules' / 'typescript' / 'lib' / 'typescript.js'
pytestmark = pytest.mark.skipif(shutil.which('node') is None or not PINNED.is_file(),
                                reason='Trusted Node/TypeScript 5.8.3 tooling absent')
BINDINGS = {'registry': 'hostRegistry', 'gate': 'hostGate', 'validate': 'hostValidate',
            'blocked': 'hostBlocked', 'evidence': 'hostEvidence',
            'baseline_action': 'hostBaseline'}
HELPERS = '''function hostRegistry(request) { return {read: original, summarize: summarize}; }
function hostGate(request, action) { return {allowed_actions: ['read', 'summarize'], baseline_permitted: true}; }
function hostValidate(request, action) { return request.permit === true; }
function hostBlocked(request, reason) { return 'blocked'; }
function hostEvidence(request) { return {intent: request.intent}; }
function hostBaseline(request) { return 'read'; }
async function summarize(request) { events.push(['summary', request.item]); return 'summary:' + request.item; }
'''


def _build_host(tmp_path, format_name):
    root = tmp_path / 'host'
    root.mkdir()
    suffix = {'esm': '.mjs', 'commonjs': '.cjs', 'typescript': '.ts'}[format_name]
    typed = format_name == 'typescript'
    selected = ('export async function seam(request: {task_id:string, invocation_id:string, item:string, permit:boolean, intent:string}): Promise<string> '
                if typed else 'export async function seam(request) '
                if format_name == 'esm' else 'async function seam(request) ')
    original = ('async function original(request: {item:string}): Promise<string> '
                if typed else 'async function original(request) ')
    source = ('export const events = [];\n' if format_name != 'commonjs' else 'const events = [];\n')
    source += selected + '{ return await original(request); }\n'
    source += original + "{ events.push(['read', request.item]); return 'read:' + request.item; }\n"
    source += HELPERS
    if format_name == 'commonjs':
        source += 'module.exports = seam;\nmodule.exports.events = events;\n'
    (root / ('host' + suffix)).write_text(source, encoding='utf-8')
    transformed = transform_js_source(root, 'host' + suffix, symbol='seam',
                                      original='original', adapter_alias='jevAdapter',
                                      adapter_path='./jev_adapter.cjs', bindings=BINDINGS,
                                      tooling_dir=TOOLING)
    (root / ('host' + suffix)).write_text(transformed['transformed_source'], encoding='utf-8')
    if typed:
        (root / 'host.mjs').write_text(transformed['emitted_source'], encoding='utf-8')
    runtime = Path(str(files('jev_integration_evaluator').joinpath('data/native_js_runtime.cjs')))
    shutil.copyfile(runtime, root / 'jev_runtime.cjs')
    spec = {'recipe_id': 'javascript.C', 'candidate_id': 'synthetic-candidate',
            'source_sha256': transformed['source_sha256'],
            'registered_action_ids': ['read', 'summarize'],
            'questions': {'choice': {'type': 'choice', 'criteria': {
                'read': 'Read', 'summary': 'Summarize', 'uncertain': 'Unclear'}}},
            'primary_question': 'choice',
            'label_actions': {'read': 'read', 'summary': 'summarize', 'uncertain': None},
            'runtime': {'mode': 'off', 'canary_scope': 'synthetic',
                        'cost_upper_bound': 1, 'timeout_ms': 40, 'model': 'model-v1'}}
    (root / 'jev_adapter.cjs').write_text(render_js_adapter(spec), encoding='utf-8')
    return root


@pytest.mark.parametrize('format_name', ['esm', 'commonjs', 'typescript'])
def test_default_off_uses_actual_edited_entrypoint(tmp_path, format_name):
    root = _build_host(tmp_path, format_name)
    if format_name == 'commonjs':
        script = "const m=require('./host.cjs'); m({task_id:'task',invocation_id:'one',item:'x',permit:true,intent:'read'}).then(result=>console.log(JSON.stringify({result,events:m.events})));"
    else:
        script = "import('./host.mjs').then(async m=>{const result=await m.seam({task_id:'task',invocation_id:'one',item:'x',permit:true,intent:'read'}); console.log(JSON.stringify({result,events:m.events}));});"
    run = subprocess.run([shutil.which('node'), '-e', script], cwd=root, text=True,
                         capture_output=True, timeout=10, check=False)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {'result': 'read:x', 'events': [['read', 'x']]}


@pytest.mark.parametrize('mode,expected', [('shadow', 'read:x'), ('active', 'summary:x')])
def test_host_startup_offline_shadow_and_receipt_bound_active(tmp_path, mode, expected):
    root = _build_host(tmp_path, 'esm')
    script = '''
const runtime = require('./jev_runtime.cjs');
const adapter = require('./jev_adapter.cjs');
const budget = new runtime.SharedBudget({max_calls: 2, max_cost: 2});
const audit = {events: [], append(event) {this.events.push(event);}};
let calls = 0;
const client = {evidence_type: 'synthetic', evaluate: async () => {
  calls++; return {choice: {label: 'summary', confidence: 1}};
}};
const now = () => Date.parse('2026-09-28T00:00:00Z');
const activation = {runtime_contract_sha256: runtime.digest({spec: adapter.SPEC, budget_limits: budget.limits}),
  source_sha256: adapter.SPEC.source_sha256, canary_scope: 'synthetic',
  issued_at: '2026-09-27T23:59:00Z', expires_at: '2026-09-28T00:01:00Z'};
adapter.initialize({mode: 'MODE', budget, audit, client, now,
  activation: 'MODE' === 'active' ? activation : null,
  trusted_activation_sha256: 'MODE' === 'active' ? runtime.digest(activation) : null});
import('./host.mjs').then(async host => {
  const result = await host.seam({task_id:'task',invocation_id:'one',item:'x',permit:true,intent:'summary'});
  await new Promise(resolve => setTimeout(resolve, 1));
  console.log(JSON.stringify({result, events:host.events, calls, audit:audit.events.map(x=>x.kind)}));
});
'''.replace('MODE', mode)
    run = subprocess.run([shutil.which('node'), '-e', script], cwd=root, text=True,
                         capture_output=True, timeout=10, check=False)
    assert run.returncode == 0, run.stderr
    observed = json.loads(run.stdout)
    assert observed['result'] == expected
    assert observed['calls'] == 1
    assert observed['events'] == ([['read', 'x']] if mode == 'shadow' else [['summary', 'x']])
    assert ('effect_intent' in observed['audit']) is (mode == 'active')
