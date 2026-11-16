'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const path = require('node:path');
const vm = require('node:vm');
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

test('semicolon-free directives retain strict behavior and shebang with trailing comments', async () => {
  const source = '#!/usr/bin/env node\r\n"custom directive"\r\n' +
    "'use strict' // retained comment\r\n" +
    'async function seam(request) { return await original(request); }\r\n' +
    'async function original(request) { return this; }\r\nmodule.exports = seam;\r\n';
  const result = run(request('host.cjs', source));
  assert.equal(result.status, 0, result.stderr);
  const transformed = JSON.parse(result.stdout).transformed_source;
  assert.match(transformed, /^#!\/usr\/bin\/env node\r\n"custom directive"\r\n'use strict';\r\nconst jevAdapter = require/);
  assert.match(transformed, /\/\/ retained comment/);
  const module = {exports: null};
  vm.runInNewContext(transformed, {module, require: () => ({invoke: original => original()})});
  assert.equal(await module.exports({}), undefined);
});

test('semicolon-free prologues transform in ESM and TypeScript without widening syntax support', () => {
  for (const [file, source] of [
    ['host.mjs', '"directive"\nexport async function seam(request) { return await original(request); }\nasync function original(request) { return request; }\n'],
    ['host.ts', '"directive"\nexport async function seam(request: string): Promise<string> { return await original(request); }\nasync function original(request: string): Promise<string> { return request; }\n']]) {
    const result = run(request(file, source));
    assert.equal(result.status, 0, result.stderr);
    assert.match(JSON.parse(result.stdout).transformed_source, /^"directive";\nimport jevAdapter/);
    const invalid = run(request(file, source + 'async function late() { return import("./other.mjs"); }\n'));
    assert.equal(invalid.status, 2);
    assert.match(invalid.stderr, /unsupported_js_binding_or_syntax/);
  }
});

test('semicolon-free directive prologues retain their meaning across native formats', async () => {
  const cases = [
    {file: 'host.cjs', directives: "'use asm'\n'use strict'\n", shebang: ''},
    {file: 'host.cjs', directives: '"custom directive"\r\n\'use strict\'\r\n', shebang: '#!/usr/bin/env node\r\n'},
    {file: 'host.mjs', directives: "'first directive'\n'second directive'\n", shebang: ''},
    {file: 'host.ts', directives: "'first directive'\n'second directive'\n", shebang: '#!/usr/bin/env node\n'},
  ];
  for (const {file, directives, shebang} of cases) {
    const commonjs = file.endsWith('.cjs');
    const typescript = file.endsWith('.ts');
    const type = typescript ? ': string' : '';
    const resultType = typescript ? ': Promise<string>' : '';
    const body = `${commonjs ? '' : 'export '}async function seam(request${type})${resultType} { return await original(request); }\n` +
      `async function original(request${type})${resultType} { return request; }\n` +
      (commonjs ? 'module.exports = seam;\n' : '');
    const result = run(request(file, shebang + directives + body));
    assert.equal(result.status, 0, `${file}: ${result.stderr}`);
    const output = JSON.parse(result.stdout);
    const transformed = output.transformed_source;
    const originalDirectives = directives.trim().split(/\r?\n/);
    assert.ok(transformed.startsWith(shebang), `${file}: shebang changed`);
    let cursor = shebang.length;
    for (const directive of originalDirectives) {
      assert.equal(transformed.slice(cursor, cursor + directive.length), directive);
      cursor += directive.length;
      const separator = transformed.slice(cursor).match(/^[;\s]*/)[0];
      assert.ok(separator.includes(';') || /[\r\n]/.test(separator), `${file}: directive lacks a statement boundary`);
      cursor += separator.length;
    }
    assert.match(transformed.slice(cursor), commonjs ? /^const jevAdapter = require/ : /^import jevAdapter from/);
    if (typescript) assert.match(output.emitted_source, /first directive/);
    if (commonjs) {
      // An unbound function's `this` distinguishes strict mode from sloppy mode.
      const module = {exports: {}};
      const adapter = {invoke: async (original, request) => original(request)};
      const source = transformed.replace(/^#![^\n]*(?:\n|$)/, '') +
        '\nmodule.exports.strictThis = function () { return this; };\n';
      vm.runInNewContext(`(function (module, exports, require) {\n${source}\n})`)(module, module.exports, () => adapter);
      const strictThis = module.exports.strictThis;
      assert.equal(strictThis(), undefined);
      assert.equal(await module.exports('synthetic'), 'synthetic');
    }
  }
});

test('malformed directive source fails closed', () => {
  const value = request('host.cjs', "'use strict\nasync function seam(request) { return await original(request); }\n" +
    'async function original(request) { return request; }\nmodule.exports = seam;\n');
  const result = run(value);
  assert.equal(result.status, 2);
  assert.equal(result.stdout, '');
  assert.match(result.stderr, /unsupported_js_syntax/);
});

test('CommonJS later export replacement cannot escape reviewed entrypoint', () => {
  const value = request('host.cjs',
    'async function seam(request) { return await original(request); }\n' +
    'async function original(request) { return request; }\n' +
    'module.exports = seam;\nmodule.exports = original;\n');
  assert.equal(run(value).status, 2);
});

test('explicit source-owned cancellation binding forwards only AbortSignal options', () => {
  const base = 'export async function seam(request) { return await original(request); }\nasync function original(request) { return request; }\n';
  const value = request('host.mjs',base+'function hostOptions(request) { return {signal: request.signal}; }\n');
  value.bindings = {...bindings,invocation_options:'hostOptions'};
  const result = run(value);
  assert.equal(result.status,0,result.stderr);
  assert.match(JSON.parse(result.stdout).transformed_source,/hostOptions\(request\)\)/);
  for (const source of [
    'function hostOptions(request) { return {signal: request.signal,mode:"active"}; }',
    'async function hostOptions(request) { return {signal: request.signal}; }',
    'function hostOptions(request) { sideEffect(); return {signal: request.signal}; }',
    'function hostOptions(request) { return {signal: createSignal()}; }']) {
    const invalid=request('host.mjs',base+source+'\n');
    invalid.bindings={...bindings,invocation_options:'hostOptions'};
    assert.equal(run(invalid).status,2);
  }
  const bodyless=request('host.ts',
    'export async function seam(request: {signal:AbortSignal}): Promise<string> { return await original(request); }\n' +
    'async function original(request: {signal:AbortSignal}): Promise<string> { return "x"; }\n' +
    'declare function hostOptions(request: {signal:AbortSignal}): {signal:AbortSignal};\n');
  bodyless.bindings={...bindings,invocation_options:'hostOptions'};
  const refused=run(bodyless);
  assert.equal(refused.status,2);
  assert.match(refused.stderr,/unsupported_js_invocation_options/);
});
