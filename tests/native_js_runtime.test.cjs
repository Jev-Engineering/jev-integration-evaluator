'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {digest, SharedBudget, DurableSharedBudget, NativeRouter, TypeSafeConnectedClient,
  validateTypedResponse, ConnectedNativeOwner} =
  require('../jev_integration_evaluator/data/native_js_runtime.cjs');

function fixture(mode = 'off', overrides = {}) {
  const spec = {recipe_id: 'javascript.C', candidate_id: 'candidate', source_sha256: 'a'.repeat(64),
    executed_source_sha256: 'b'.repeat(64),
    registered_action_ids: ['read', 'summarize'],
    questions: {choice: {type: 'choice', criteria: {read: 'Read', summary: 'Summarize', uncertain: 'Unclear'}}},
    primary_question: 'choice', label_actions: {read: 'read', summary: 'summarize', uncertain: null},
    runtime: {canary_scope: 'synthetic', cost_upper_bound: 1, timeout_ms: 40, model: 'model-v1'}};
  const events = [];
  const budget = overrides.budget || new SharedBudget({max_calls: 2, max_cost: 2});
  const audit = overrides.audit || {append: event => events.push(event)};
  const client = overrides.client || {evidence_type: 'synthetic', evaluate: async () => ({choice: {label: 'summary', confidence: 1}})};
  const now = () => Date.parse('2026-09-28T00:00:00Z');
  const activation = {runtime_contract_sha256: digest({spec, budget_limits: budget.limits}),
    source_sha256: spec.executed_source_sha256, canary_scope: 'synthetic',
    issued_at: '2026-09-27T23:59:00Z', expires_at: '2026-09-28T00:01:00Z'};
  const router = new NativeRouter({spec, client, budget, audit, mode,
    activation: mode === 'active' ? activation : null,
    trusted_activation_sha256: mode === 'active' ? digest(activation) : null,
    sourceAttest: overrides.sourceAttest || (() => spec.executed_source_sha256), now});
  let baselineCalls = 0, summaryCalls = 0;
  const original = () => {baselineCalls++; events.push({kind: 'baseline_effect'}); return 'baseline';};
  const bindings = {registry: () => ({read: original, summarize: () => {
    summaryCalls++; events.push({kind: 'summary_effect'}); return 'summary';}}),
    gate: () => ({allowed_actions: ['read', 'summarize'], baseline_permitted: true,
      approval_required: false, approval_granted: true}),
    validate: () => true, blocked: () => 'blocked', evidence: () => ({marker: 'synthetic'}),
    baseline_action: () => 'read'};
  return {router, spec, budget, events, original, bindings,
    counts: () => ({baselineCalls, summaryCalls})};
}

test('off retains one baseline effect and rejects invocation replay', async () => {
  const f = fixture();
  const request = {task_id: 'task', invocation_id: 'one'};
  assert.equal(await f.router.invoke(f.original, request, f.bindings), 'baseline');
  assert.deepEqual(f.counts(), {baselineCalls: 1, summaryCalls: 0});
  await assert.rejects(f.router.invoke(f.original, request, f.bindings), /effect_replay_denied/);
  assert.deepEqual(f.counts(), {baselineCalls: 1, summaryCalls: 0});
  f.budget.closeTask('task');
  await assert.rejects(f.router.invoke(f.original,
    {task_id: 'task', invocation_id: 'two'}, f.bindings), /task_closed/);
});

test('source drift during awaited assessment blocks selected and baseline effects', async () => {
  let current = 'b'.repeat(64);
  const f = fixture('active', {sourceAttest: () => current,
    client: {evaluate: async () => {
      current = 'c'.repeat(64);
      return {choice: {label: 'summary', confidence: 1}};
    }}});
  await assert.rejects(f.router.invoke(f.original,
    {task_id: 'drift-task', invocation_id: 'one'}, f.bindings), /applied_host_source_changed/);
  assert.deepEqual(f.counts(), {baselineCalls: 0, summaryCalls: 0});
});

test('shadow returns baseline and does not execute proposed action', async () => {
  const f = fixture('shadow');
  assert.equal(await f.router.invoke(f.original, {task_id: 'task', invocation_id: 'one'}, f.bindings), 'baseline');
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.deepEqual(f.counts(), {baselineCalls: 1, summaryCalls: 0});
  assert.ok(f.events.some(x => x.kind === 'shadow_result'));
});

test('active rechecks policy, audits before one effect, and retains shared charges', async () => {
  const f = fixture('active');
  assert.equal(await f.router.invoke(f.original, {task_id: 'task', invocation_id: 'one'}, f.bindings), 'summary');
  assert.deepEqual(f.counts(), {baselineCalls: 0, summaryCalls: 1});
  assert.ok(f.events.findIndex(x => x.kind === 'effect_intent') < f.events.findIndex(x => x.kind === 'summary_effect'));
  f.budget.closeTask('task');
  assert.equal(f.budget.calls, 1);
  await assert.rejects(f.router.invoke(f.original, {task_id: 'task', invocation_id: 'two'}, f.bindings), /task_closed/);
  assert.deepEqual(f.counts(), {baselineCalls: 0, summaryCalls: 1});
});

test('cancellation after request cannot trigger fallback effect', async () => {
  const controller = new AbortController();
  const client = {evidence_type: 'synthetic', evaluate: async () => {
    controller.abort(); return {choice: {label: 'summary', confidence: 1}};
  }};
  const f = fixture('active', {client});
  await assert.rejects(f.router.invoke(f.original, {task_id: 'task', invocation_id: 'one'}, f.bindings,
    {signal: controller.signal}), /cancelled/);
  assert.deepEqual(f.counts(), {baselineCalls: 0, summaryCalls: 0});
});

test('forged activation receipt and failed audit cannot authorize effects', async () => {
  const f = fixture('active');
  const forged = {...f.router.activation, source_sha256: 'c'.repeat(64)};
  assert.throws(() => new NativeRouter({spec: f.spec, client: f.router.client,
    budget: f.budget, audit: f.router.audit, mode: 'active', activation: forged,
    trusted_activation_sha256: digest(forged), sourceAttest: f.router.sourceAttest,
    now: f.router.now}), /exact_expiring_activation_required/);
  const events = [];
  const denied = fixture('active', {audit: {append: e => {
    events.push(e); if (e.kind === 'effect_intent') throw Error('audit unavailable');
  }}});
  await assert.rejects(denied.router.invoke(denied.original,
    {task_id: 'task', invocation_id: 'one'}, denied.bindings), /audit unavailable/);
  assert.deepEqual(denied.counts(), {baselineCalls: 0, summaryCalls: 0});
});

test('reviewed contract and activation cannot be changed after router construction', () => {
  const f = fixture('active');
  f.spec.runtime.model = 'unreviewed-model';
  assert.equal(f.router.spec.runtime.model, 'model-v1');
  assert.throws(() => { f.router.spec.runtime.model = 'unreviewed-model'; }, TypeError);
  assert.throws(() => { f.router.activation.expires_at = '2099-01-01T00:00:00Z'; }, TypeError);
});

test('cancellation while audit persists intent prevents baseline and selected effects', async () => {
  for (const [mode, intent] of [['off', 'baseline_intent'], ['active', 'effect_intent']]) {
    const controller = new AbortController();
    const f = fixture(mode, {audit: {append: event => {
      if (event.kind === intent) controller.abort();
    }}});
    await assert.rejects(f.router.invoke(f.original,
      {task_id: 'task', invocation_id: 'one'}, f.bindings, {signal: controller.signal}), /cancelled/);
    assert.deepEqual(f.counts(), {baselineCalls: 0, summaryCalls: 0});
  }
});

test('two routers share one budget and retain the first charge', async () => {
  const budget = new SharedBudget({max_calls: 1, max_cost: 1});
  const first = fixture('active', {budget});
  const second = fixture('active', {budget});
  const [one, two] = await Promise.all([
    first.router.invoke(first.original, {task_id: 'task-a', invocation_id: 'one'}, first.bindings),
    second.router.invoke(second.original, {task_id: 'task-b', invocation_id: 'one'}, second.bindings)]);
  assert.equal(one, 'summary');
  assert.equal(two, 'baseline');
  assert.equal(budget.calls, 1);
  assert.deepEqual(second.counts(), {baselineCalls: 1, summaryCalls: 0});
});

test('two routers sharing a coordinator reject the same invocation identity', async () => {
  const budget = new SharedBudget({max_calls: 2, max_cost: 2});
  const first = fixture('off', {budget});
  const second = fixture('off', {budget});
  const request = {task_id: 'task', invocation_id: 'same'};
  assert.equal(await first.router.invoke(first.original, request, first.bindings), 'baseline');
  await assert.rejects(second.router.invoke(second.original, request, second.bindings), /effect_replay_denied/);
  assert.deepEqual(first.counts(), {baselineCalls: 1, summaryCalls: 0});
  assert.deepEqual(second.counts(), {baselineCalls: 0, summaryCalls: 0});
});

test('assessment is audited before evaluation and failed audit prevents egress', async () => {
  let calls = 0;
  const client = {evidence_type: 'synthetic', evaluate: async () => {
    calls++; return {choice: {label: 'summary', confidence: 1}};
  }};
  const f = fixture('active', {client, audit: {append: event => {
    if (event.kind === 'assessment_intent') throw Error('audit unavailable');
  }}});
  assert.equal(await f.router.invoke(f.original,
    {task_id: 'task', invocation_id: 'one'}, f.bindings), 'baseline');
  assert.equal(calls, 0);
  assert.equal(f.budget.calls, 1);
});

test('async executor rejection is terminal and cannot replay a baseline effect', async () => {
  const f = fixture('active');
  let attempts = 0;
  f.bindings.registry = () => ({read: f.original, summarize: async () => {
    attempts++; throw Error('synthetic_executor_rejected');
  }});
  const request = {task_id: 'task', invocation_id: 'one'};
  await assert.rejects(f.router.invoke(f.original, request, f.bindings), /synthetic_executor_rejected/);
  await assert.rejects(f.router.invoke(f.original, request, f.bindings), /effect_replay_denied/);
  assert.equal(attempts, 1);
  assert.deepEqual(f.counts(), {baselineCalls: 0, summaryCalls: 0});
});

test('host permission change after assessment blocks both proposed and fallback effect', async () => {
  let permitted = true;
  const client = {evidence_type: 'synthetic', evaluate: async () => {
    permitted = false;
    return {choice: {label: 'summary', confidence: 1}};
  }};
  const f = fixture('active', {client});
  f.bindings.validate = () => permitted;
  const result = await f.router.invoke(f.original,
    {task_id: 'task', invocation_id: 'one'}, f.bindings);
  assert.equal(result, 'blocked');
  assert.deepEqual(f.counts(), {baselineCalls: 0, summaryCalls: 0});
});

test('provider that never resolves times out within the bound to exactly one baseline effect', async () => {
  let evaluations = 0, requestedTimeout = null;
  const client = {evidence_type: 'synthetic', evaluate: (_state, _questions, _model, timeoutMs) => {
    evaluations++; requestedTimeout = timeoutMs; return new Promise(() => {});
  }};
  const f = fixture('active', {client});
  const request = {task_id: 'task', invocation_id: 'one'};
  const bound = f.spec.runtime.timeout_ms;
  const started = process.hrtime.bigint();
  assert.equal(await f.router.invoke(f.original, request, f.bindings), 'baseline');
  const elapsedMs = Number(process.hrtime.bigint() - started) / 1e6;
  assert.equal(requestedTimeout, bound);
  assert.ok(elapsedMs >= bound - 5 && elapsedMs < bound + 2000, `timeout after ${elapsedMs}ms`);
  assert.deepEqual(f.counts(), {baselineCalls: 1, summaryCalls: 0});
  assert.deepEqual(f.events.map(x => x.kind), ['assessment_intent', 'baseline_intent', 'baseline_effect']);
  assert.equal(f.events[1].reason, 'assessment_unavailable');
  // The call and its cost upper bound are reserved before egress and never refunded.
  assert.equal(f.budget.calls, 1);
  assert.equal(f.budget.cost, f.spec.runtime.cost_upper_bound);
  await assert.rejects(f.router.invoke(f.original, request, f.bindings), /effect_replay_denied/);
  assert.equal(evaluations, 1);
  assert.deepEqual(f.counts(), {baselineCalls: 1, summaryCalls: 0});
});

test('late provider result after timeout is discarded and leaves its reservation unresolved', async () => {
  class RecordingBudget extends SharedBudget {
    constructor(limits) { super(limits); this.finished = []; }
    finishReservation(reservation) { this.finished.push(reservation); }
  }
  const run = async delayMs => {
    let late;
    const client = {evidence_type: 'synthetic', evaluate: () => {
      late = new Promise(resolve => setTimeout(
        () => resolve({choice: {label: 'summary', confidence: 1}}), delayMs));
      return late;
    }};
    const f = fixture('active', {client, budget: new RecordingBudget({max_calls: 2, max_cost: 2})});
    const result = await f.router.invoke(f.original, {task_id: 'task', invocation_id: 'one'}, f.bindings);
    await late;
    await new Promise(resolve => setImmediate(resolve));
    return {f, result};
  };
  const timedOut = await run(120);
  assert.equal(timedOut.result, 'baseline');
  assert.deepEqual(timedOut.f.counts(), {baselineCalls: 1, summaryCalls: 0});
  assert.deepEqual(timedOut.f.events.map(x => x.kind),
    ['assessment_intent', 'baseline_intent', 'baseline_effect']);
  assert.equal(timedOut.f.budget.calls, 1);
  assert.equal(timedOut.f.budget.cost, 1);
  assert.deepEqual(timedOut.f.budget.finished, []);
  // Control: the same provider answering inside the bound selects the action and settles.
  const prompt = await run(1);
  assert.equal(prompt.result, 'summary');
  assert.deepEqual(prompt.f.counts(), {baselineCalls: 0, summaryCalls: 1});
  assert.equal(prompt.f.budget.finished.length, 1);
  assert.equal(prompt.f.budget.calls, 1);
});

test('shadow provider timeout keeps one baseline effect and audits only a failed assessment', async () => {
  const client = {evidence_type: 'synthetic', evaluate: () => new Promise(() => {})};
  const f = fixture('shadow', {client});
  const bound = f.spec.runtime.timeout_ms;
  const started = process.hrtime.bigint();
  assert.equal(await f.router.invoke(f.original, {task_id: 'task', invocation_id: 'one'}, f.bindings), 'baseline');
  assert.deepEqual(f.counts(), {baselineCalls: 1, summaryCalls: 0});
  assert.ok(!f.events.some(x => x.kind === 'shadow_failed'));
  while (!f.events.some(x => x.kind === 'shadow_failed') &&
         Number(process.hrtime.bigint() - started) / 1e6 < bound + 2000)
    await new Promise(resolve => setTimeout(resolve, 5));
  const elapsedMs = Number(process.hrtime.bigint() - started) / 1e6;
  assert.ok(elapsedMs >= bound - 5 && elapsedMs < bound + 2000, `shadow timeout after ${elapsedMs}ms`);
  assert.deepEqual(f.events.map(x => x.kind).sort(),
    ['assessment_intent', 'baseline_effect', 'baseline_intent', 'shadow_failed']);
  assert.deepEqual(f.counts(), {baselineCalls: 1, summaryCalls: 0});
  assert.equal(f.budget.calls, 1);
  assert.equal(f.budget.cost, f.spec.runtime.cost_upper_bound);
});

test('typed TypeSafe client validates exact model, answer and key rotation without network', async () => {
  const environment = {TYPESAFE_API_KEY: 'fixture-only-key'};
  const questions = {choice: {type: 'choice', criteria: {read: 'Read', uncertain: 'Unclear'}}};
  const response = {model: 'jev-1.13.0', answers: {choice: {type: 'choice', choice: 'read',
    confidence: 0.9, probabilities: {read: 0.9, uncertain: 0.1}}},
    usage: {input_tokens: 3, output_tokens: 2}};
  let requests = 0;
  const transport = async (url, body, key) => {
    requests++;
    assert.equal(url, 'https://api.typesafe.ai/v1/systemone');
    assert.equal(key, 'fixture-only-key');
    assert.deepEqual(JSON.parse(body.toString()), {state: {marker: 'fixture'}, questions,
      model: 'jev-1.13.0'});
    return Buffer.from(JSON.stringify(response));
  };
  const client = new TypeSafeConnectedClient({endpoint: 'https://api.typesafe.ai/v1/systemone',
    environment, transport});
  assert.deepEqual(await client.evaluate({marker: 'fixture'}, questions, 'jev-1.13.0', 100),
    {choice: {label: 'read', confidence: 0.9}});
  const twoChoices = {secondary: {type: 'choice', criteria: {read: 'Read', uncertain: 'Unclear'}},
    primary: {type: 'choice', criteria: {read: 'Read', uncertain: 'Unclear'}}};
  const twoAnswers = {model: 'jev-1.13.0', answers: {
    secondary: {type: 'choice', choice: 'uncertain', confidence: 0.9,
      probabilities: {read: 0.1, uncertain: 0.9}},
    primary: {type: 'choice', choice: 'read', confidence: 0.9,
      probabilities: {read: 0.9, uncertain: 0.1}}},
    usage: {input_tokens: 3, output_tokens: 2}};
  const multi = new TypeSafeConnectedClient({endpoint: 'https://api.typesafe.ai/v1/systemone',
    environment, transport: async () => Buffer.from(JSON.stringify(twoAnswers))});
  assert.deepEqual(await multi.evaluate({}, twoChoices, 'jev-1.13.0', 100), {
    secondary: {label: 'uncertain', confidence: 0.9},
    primary: {label: 'read', confidence: 0.9}});
  assert.equal(requests, 1);
  assert.throws(() => validateTypedResponse({...response, model: 'jev-latest'}, questions,
    'jev-1.13.0'), /invalid_typed_response/);
  assert.throws(() => validateTypedResponse({...response, answers: {choice: {
    ...response.answers.choice, probabilities: {read: 0.2, uncertain: 0.8}}}}, questions,
    'jev-1.13.0'), /invalid_typed_response/);
  const duplicate = new TypeSafeConnectedClient({endpoint: 'https://api.typesafe.ai/v1/systemone',
    environment, transport: async () => Buffer.from(JSON.stringify(response).replace(
      '"model":"jev-1.13.0"', '"model":"jev-1.13.0","model":"jev-1.13.0"'))});
  await assert.rejects(duplicate.evaluate({marker: 'fixture'}, questions, 'jev-1.13.0', 100),
    /invalid_typed_response/);
  environment.TYPESAFE_API_KEY = 'rotated-fixture-key';
  await assert.rejects(client.evaluate({marker: 'fixture'}, questions, 'jev-1.13.0', 100),
    /provider_credential_rotated/);
  assert.equal(requests, 1);
  const direct = fixture();
  assert.throws(() => new NativeRouter({spec: direct.spec, client,
    budget: direct.budget, audit: direct.router.audit, mode: 'shadow',
    sourceAttest: () => direct.spec.executed_source_sha256}), /connected_owner_required/);
});

test('durable native ledger retains charges and refuses unresolved or revoked restarts',
  {skip: process.platform !== 'linux' || process.version !== 'v24.18.0'}, () => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'jev-node-ledger-'));
  fs.chmodSync(parent, 0o700);
  const limits = {max_calls: 2, max_cost: 2};
  const identity = 'a'.repeat(64);
  const ledgerPath = path.join(parent, 'ledger.sqlite');
  try {
    let ledger = new DurableSharedBudget({limits, ledgerPath, identity});
    assert.throws(() => new DurableSharedBudget({limits, ledgerPath, identity}));
    ledger.trackTask('one');
    const reservation = ledger.reserve('one', 1);
    ledger.finishReservation(reservation);
    ledger.claimInvocation('one', 'first', 'candidate');
    ledger.settleInvocation('one', 'first', 'candidate');
    ledger.close();
    ledger = new DurableSharedBudget({limits, ledgerPath, identity});
    assert.equal(ledger.calls, 1);
    assert.throws(() => ledger.claimInvocation('one', 'first', 'candidate'), /effect_replay_denied/);
    ledger.claimInvocation('one', 'second', 'candidate');
    ledger.close();
    assert.throws(() => new DurableSharedBudget({limits, ledgerPath, identity}),
      /runtime_ledger_unresolved_or_revoked/);
  } finally {
    fs.rmSync(parent, {recursive: true, force: true});
  }
});

test('separate native processes cannot reset a held ledger or replay its settled effects',
  {skip: process.platform !== 'linux' || process.version !== 'v24.18.0'}, () => {
  const {spawnSync} = require('node:child_process');
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'jev-node-contention-'));
  fs.chmodSync(parent, 0o700);
  const ledgerPath = path.join(parent, 'ledger.sqlite');
  const limits = {max_calls: 2, max_cost: 2};
  const identity = 'a'.repeat(64);
  const runtime = require.resolve('../jev_integration_evaluator/data/native_js_runtime.cjs');
  const child = mode => {
    const result = spawnSync(process.execPath, ['-e', `
      const assert = require('node:assert/strict');
      const {DurableSharedBudget} = require(process.argv[1]);
      const args = JSON.parse(process.argv[2]);
      if (process.argv[3] === 'contend') {
        assert.throws(() => new DurableSharedBudget(args), /locked/);
      } else {
        const ledger = new DurableSharedBudget(args);
        try {
          assert.equal(ledger.calls, 1);
          assert.equal(ledger.cost, 1);
          assert.throws(() => ledger.claimInvocation('one', 'first', 'candidate'),
            /effect_replay_denied/);
          const reservation = ledger.reserve('two', 1);
          ledger.finishReservation(reservation);
          assert.throws(() => ledger.reserve('three', 1), /budget_denied/);
          assert.equal(ledger.calls, 2);
          assert.equal(ledger.cost, 2);
        } finally { ledger.close(); }
      }
      process.stdout.write('verified');
    `, runtime, JSON.stringify({limits, ledgerPath, identity}), mode],
      {encoding: 'utf8', timeout: 10000, env: {PATH: process.env.PATH}});
    assert.equal(result.error, undefined);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, 'verified');
  };
  let ledger;
  try {
    ledger = new DurableSharedBudget({limits, ledgerPath, identity});
    const reservation = ledger.reserve('one', 1);
    ledger.finishReservation(reservation);
    ledger.claimInvocation('one', 'first', 'candidate');
    ledger.settleInvocation('one', 'first', 'candidate');
    child('contend'); // a real peer process must fail before it can reserve
    assert.equal(ledger.calls, 1);
    assert.equal(ledger.cost, 1);
    ledger.close(); ledger = null;
    child('resume'); // release transfers ownership, never a fresh budget
    ledger = new DurableSharedBudget({limits, ledgerPath, identity});
    assert.equal(ledger.calls, 2);
    assert.equal(ledger.cost, 2);
    assert.throws(() => ledger.reserve('four', 1), /budget_denied/);
  } finally {
    if (ledger) ledger.close();
    fs.rmSync(parent, {recursive: true, force: true});
  }
});

test('connected shadow owner checks independent grant and installed bytes before fake transport',
  {skip: process.platform !== 'linux' || process.version !== 'v24.18.0'}, async () => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'jev-connected-shadow-'));
  fs.chmodSync(parent, 0o700);
  try {
    const roles = ['executed_source', 'runtime', 'adapter', 'entrypoint', 'package', 'lock',
      'node', 'npm', 'reviewed_configuration'];
    const files = roles.map(role => {
      const filename = path.join(parent, role);
      fs.writeFileSync(filename, role);
      return {role, path: filename,
        sha256: require('node:crypto').createHash('sha256').update(role).digest('hex')};
    });
    const f = fixture();
    const spec = {...f.spec, executed_source_sha256: files[0].sha256,
      runtime: {...f.spec.runtime, model: 'jev-1.13.0'}};
    const now = () => Date.parse('2026-09-28T00:00:00Z');
    const environment = {TYPESAFE_API_KEY: 'offline-fixture-placeholder'};
    const core = {schema_version: '1.0', kind: 'node-connected-owner-v1',
      runtime_profile: {platform: 'linux', node: 'v24.18.0',
        apis: ['node:sqlite.DatabaseSync', 'AbortSignal', 'node:https', 'node:crypto']},
      mode: 'shadow',
      spec_sha256: digest(spec), source_sha256: spec.executed_source_sha256,
      source_plan: {files}, environment_digest: 'c'.repeat(64),
      endpoint: 'https://api.typesafe.ai/v1/systemone', credential_ref: 'env:TYPESAFE_API_KEY',
      model: 'jev-1.13.0', budget_limits: {max_calls: 2, max_cost: 2},
      ledger_path: path.join(parent, 'ledger.sqlite'),
      install_receipt_sha256: 'd'.repeat(64), configuration_sha256: 'e'.repeat(64)};
    const grant = {core_sha256: digest(core), mode: 'shadow', endpoint: core.endpoint,
      model: core.model, credential_ref: core.credential_ref,
      environment_digest: core.environment_digest,
      issued_at: '2026-09-27T23:59:00Z', expires_at: '2026-09-28T00:01:00Z'};
    const descriptorBody = {...core, core_sha256: digest(core), egress_grant: grant,
      activation: null};
    const descriptor = {...descriptorBody, descriptor_sha256: digest(descriptorBody)};
    const linkedSource = path.join(parent, 'linked-source');
    fs.linkSync(files[0].path, linkedSource);
    assert.throws(() => new ConnectedNativeOwner({spec, descriptor, audit: f.router.audit,
      verifyAuthority: () => true, currentEnvironmentDigest: () => core.environment_digest,
      sourceAttest: () => spec.executed_source_sha256,
      environment: {TYPESAFE_API_KEY: 'offline-fixture-placeholder'}, now,
      transport: async () => { throw Error('unexpected'); }}), /connected_source_drift/);
    assert.equal(fs.readFileSync(files[0].path, 'utf8'), 'executed_source');
    fs.unlinkSync(linkedSource);
    let allowed = true; let evaluations = 0;
    const owner = new ConnectedNativeOwner({spec, descriptor, audit: f.router.audit,
      verifyAuthority: (kind, sha) => allowed && kind === 'egress_grant' && sha === digest(grant),
      currentEnvironmentDigest: () => core.environment_digest,
      sourceAttest: () => spec.executed_source_sha256, environment, now,
      transport: async () => {
        evaluations++;
        return Buffer.from(JSON.stringify({model: 'jev-1.13.0',
          answers: {choice: {type: 'choice', choice: 'read', confidence: 1,
            probabilities: {read: 1, summary: 0, uncertain: 0}}},
          usage: {input_tokens: 1, output_tokens: 1}}));
      }});
    assert.equal(owner.status().evidence_type, 'synthetic_protocol');
    assert.equal(await owner.invoke(f.original,
      {task_id: 'task', invocation_id: 'first'}, f.bindings), 'baseline');
    for (let i = 0; i < 30 && evaluations === 0; i++) await new Promise(setImmediate);
    assert.equal(evaluations, 1);
    allowed = false;
    await assert.rejects(owner.invoke(f.original,
      {task_id: 'task', invocation_id: 'second'}, f.bindings), /connected_authority_expired_or_revoked/);
    assert.deepEqual(f.counts(), {baselineCalls: 1, summaryCalls: 0});
    assert.deepEqual(owner.status().mode, 'off');
    owner.close();
    allowed = true;
    assert.throws(() => new ConnectedNativeOwner({spec, descriptor, audit: f.router.audit,
      verifyAuthority: (kind, sha) => kind === 'egress_grant' && sha === digest(grant),
      currentEnvironmentDigest: () => core.environment_digest,
      sourceAttest: () => spec.executed_source_sha256, environment, now,
      transport: async () => { throw Error('unexpected'); }}),
      /runtime_ledger_unresolved_or_revoked/);
  } finally {
    fs.rmSync(parent, {recursive: true, force: true});
  }
});

test('source-bound host owner shares one durable ledger across reviewed runtime copies',
  {skip: process.platform !== 'linux' || process.version !== 'v24.18.0'}, () => {
  const runtime = require('../jev_integration_evaluator/data/native_js_runtime.cjs');
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'jev-reviewed-owner-'));
  fs.chmodSync(parent, 0o700);
  const first = fixture('active'), second = fixture('active');
  second.spec.candidate_id = 'second';
  const hashes = [runtime.digest(first.spec),runtime.digest(second.spec)];
  const owner = runtime.createRuntimeOwner({specHashes:hashes,limits:{max_calls:1,max_cost:1},
    ledgerPath:path.join(parent,'ledger.sqlite')});
  assert.equal(runtime.isRuntimeOwner(owner),true);
  assert.equal(runtime.isRuntimeOwner({...owner}),false);
  assert.throws(()=>owner.createRouter({spec:{...first.spec,candidate_id:'unreviewed'},client:{evidence_type:'synthetic'}}),
    /runtime_owner_placement_mismatch/);
  owner.close();
  fs.rmSync(parent,{recursive:true,force:true});
});
