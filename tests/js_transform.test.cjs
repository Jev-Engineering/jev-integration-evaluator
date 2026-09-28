'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const path = require('node:path');
const helper = path.resolve(__dirname, '../jev_integration_evaluator/data/js_transform.cjs');
const bindings = {registry: 'hostRegistry', gate: 'hostGate', validate: 'hostValidate',
  blocked: 'hostBlocked', evidence: 'hostEvidence', baseline_action: 'hostBaseline'};
const helpers = Object.values(bindings).map(name => `function ${name}(request) { return request; }`).join('\n') + '\n';
const request = (file, source) => ({file, source: source + helpers, symbol: 'seam', original: 'original',
  adapter_alias: 'jevAdapter', adapter_path: './jev_adapter.cjs', bindings});
function run(value) {
  const result = spawnSync(process.execPath, [helper], {input: JSON.stringify(value), encoding: 'utf8',
    cwd: path.dirname(helper), timeout: 12000,
    env: {...process.env, JEV_TRUSTED_TYPESCRIPT: require.resolve('typescript'), NODE_PATH: '', NODE_OPTIONS: ''}});
  return result;
}

test('trusted parser emits bounded ESM, CommonJS and TypeScript edits', () => {
  const examples = [
    request('host.mjs', 'export async function seam(request) { return await original(request); }\nasync function original(request) { return request; }\n'),
    request('host.cjs', 'async function seam(request) { return await original(request); }\nasync function original(request) { return request; }\nmodule.exports = seam;\n'),
    request('host.ts', 'export async function seam(request: {task_id:string}): Promise<string> { return await original(request); }\nasync function original(request: {task_id:string}): Promise<string> { return request.task_id; }\n')];
  for (const item of examples) {
    const result = run(item);
    assert.equal(result.status, 0, result.stderr);
    const output = JSON.parse(result.stdout);
    assert.equal(output.compiler_version, '5.8.3');
    assert.match(output.transformed_source, /return await jevAdapter\.invoke\(original, request, \{/);
    assert.ok(/^[a-f0-9]{64}$/.test(output.generated_sha256));
    if (item.file.endsWith('.ts')) assert.ok(/^[a-f0-9]{64}$/.test(output.emitted_sha256));
  }
});

test('parser rejects dynamic import, callback reassignment, collision and unsupported seam', () => {
  const base = 'export async function seam(request) { return await original(request); }\nasync function original(request) { return request; }\n';
  for (const source of [
    base + "async function late() { return import('./plugin.mjs'); }\n",
    base + 'original = async () => 1;\n',
    base + 'original ||= async () => 1;\n',
    base + 'const jevAdapter = 1;\n',
    base.replace('return await original(request)', 'return await original(other)')]) {
    const result = run(request('host.mjs', source));
    assert.equal(result.status, 2);
    assert.doesNotMatch(result.stderr, /original\(request\)|plugin\.mjs/);
  }
});

test('target compiler configuration cannot enter the trusted transform request', () => {
  const value = request('host.ts', 'export async function seam(request: string): Promise<string> { return await original(request); }\nasync function original(request: string): Promise<string> { return request; }\n');
  value.tsconfig = './target/tsconfig.json';
  const result = run(value);
  assert.equal(result.status, 2);
});

test('CommonJS transform preserves the strict directive prologue', () => {
  const value = request('host.cjs', "'use strict';\nasync function seam(request) { return await original(request); }\nasync function original(request) { return request; }\nmodule.exports = seam;\n");
  const result = run(value);
  assert.equal(result.status, 0, result.stderr);
  const transformed = JSON.parse(result.stdout).transformed_source;
  assert.match(transformed, /^'use strict';\s*const jevAdapter = require/);
});

test('CommonJS later export replacement cannot escape reviewed entrypoint', () => {
  const value = request('host.cjs',
    'async function seam(request) { return await original(request); }\n' +
    'async function original(request) { return request; }\n' +
    'module.exports = seam;\nmodule.exports = original;\n');
  assert.equal(run(value).status, 2);
});
