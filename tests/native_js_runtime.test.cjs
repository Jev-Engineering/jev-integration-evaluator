'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {digest, SharedBudget, NativeRouter} = require('../jev_integration_evaluator/data/native_js_runtime.cjs');

function fixture(mode = 'off', overrides = {}) {
  const spec = {recipe_id: 'javascript.C', candidate_id: 'candidate', source_sha256: 'a'.repeat(64),
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
    source_sha256: spec.source_sha256, canary_scope: 'synthetic',
    issued_at: '2026-09-27T23:59:00Z', expires_at: '2026-09-28T00:01:00Z'};
  const router = new NativeRouter({spec, client, budget, audit, mode,
    activation: mode === 'active' ? activation : null,
    trusted_activation_sha256: mode === 'active' ? digest(activation) : null, now});
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
  const forged = {...f.router.activation, source_sha256: 'b'.repeat(64)};
  assert.throws(() => new NativeRouter({spec: f.spec, client: f.router.client,
    budget: f.budget, audit: f.router.audit, mode: 'active', activation: forged,
    trusted_activation_sha256: digest(forged), now: f.router.now}), /exact_expiring_activation_required/);
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
