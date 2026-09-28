// Bounded native runtime for reviewed JavaScript/TypeScript recipe C hosts.
// This file is copied only as an owned, hashed implementation artifact.
'use strict';

const crypto = require('node:crypto');

function stable(value, depth = 0, seen = new Set()) {
  if (depth > 32) fail('invalid_canonical_json');
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (typeof value !== 'object' || seen.has(value)) fail('invalid_canonical_json');
  seen.add(value);
  let result;
  if (Array.isArray(value)) {
    if (value.length > 10000) fail('invalid_canonical_json');
    result = '[' + value.map(x => stable(x, depth + 1, seen)).join(',') + ']';
  } else {
    if (!plain(value)) fail('invalid_canonical_json');
    const keys = Object.keys(value).sort();
    if (keys.length > 10000 || keys.some(k => ['__proto__', 'constructor', 'prototype'].includes(k)))
      fail('invalid_canonical_json');
    result = '{' + keys.map(k => JSON.stringify(k) + ':' + stable(value[k], depth + 1, seen)).join(',') + '}';
  }
  seen.delete(value);
  return result;
}

function digest(value) {
  return crypto.createHash('sha256').update(stable(value), 'utf8').digest('hex');
}

function fail(code) { const error = new Error(code); error.code = code; throw error; }
function plain(value) { return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype; }
function frozenCopy(value) {
  const copy = structuredClone(value);
  const freeze = item => {
    if (item !== null && typeof item === 'object') {
      for (const child of Object.values(item)) freeze(child);
      Object.freeze(item);
    }
    return item;
  };
  return freeze(copy);
}

class SharedBudget {
  constructor({max_calls, max_cost, max_tasks = 10000, max_calls_per_task = max_calls}) {
    if (![max_calls, max_tasks, max_calls_per_task].every(x => Number.isSafeInteger(x) && x > 0) ||
        !Number.isFinite(max_cost) || max_cost <= 0) fail('invalid_shared_budget');
    this.limits = Object.freeze({max_calls, max_cost, max_tasks, max_calls_per_task});
    this.calls = 0;
    this.cost = 0;
    this.tasks = new Map();
    this.suspended = false;
  }
  reserve(taskId, upperBound) {
    if (this.suspended || typeof taskId !== 'string' || !taskId ||
        !Number.isFinite(upperBound) || upperBound <= 0) fail('budget_denied');
    let row = this.tasks.get(taskId);
    if (!row) {
      if (this.tasks.size >= this.limits.max_tasks) fail('budget_denied');
      row = {calls: 0, closed: false}; this.tasks.set(taskId, row);
    }
    if (row.closed || row.calls >= this.limits.max_calls_per_task ||
        this.calls >= this.limits.max_calls || this.cost + upperBound > this.limits.max_cost) fail('budget_denied');
    row.calls += 1; this.calls += 1; this.cost += upperBound;
    return Object.freeze({taskId, upperBound});
  }
  closeTask(taskId) {
    const row = this.tasks.get(taskId);
    if (!row) fail('unknown_task');
    row.closed = true; // Retain a bounded tombstone; never reset charges on retry.
  }
  isClosed(taskId) { return this.tasks.get(taskId)?.closed === true; }
  suspend() { this.suspended = true; }
}

class NativeRouter {
  constructor({spec, client, audit, budget, mode = 'off', activation = null,
               trusted_activation_sha256 = null, now = () => Date.now()}) {
    if (!plain(spec) || spec.recipe_id !== 'javascript.C' || !plain(spec.questions) ||
        !plain(spec.label_actions) || !plain(spec.runtime) ||
        !Array.isArray(spec.registered_action_ids) || !spec.registered_action_ids.length ||
        typeof spec.primary_question !== 'string' || !plain(spec.questions[spec.primary_question]) ||
        spec.questions[spec.primary_question].type !== 'choice' ||
        !plain(spec.questions[spec.primary_question].criteria) ||
        Object.keys(spec.questions[spec.primary_question].criteria).sort().join('|') !==
          Object.keys(spec.label_actions).sort().join('|') ||
        spec.label_actions.uncertain !== undefined && spec.label_actions.uncertain !== null ||
        spec.registered_action_ids.some(x => typeof x !== 'string' || !x) ||
        Object.values(spec.label_actions).some(x => x !== null && !spec.registered_action_ids.includes(x)))
      fail('invalid_reviewed_runtime_spec');
    if (!Number.isSafeInteger(spec.runtime.timeout_ms) || spec.runtime.timeout_ms < 1 ||
        spec.runtime.timeout_ms > 120000 || !Number.isFinite(spec.runtime.cost_upper_bound) ||
        spec.runtime.cost_upper_bound <= 0 || typeof spec.runtime.model !== 'string' ||
        !spec.runtime.model || /(latest|preview)$/.test(spec.runtime.model) ||
        typeof spec.candidate_id !== 'string' || !spec.candidate_id ||
        !/^[a-f0-9]{64}$/.test(spec.source_sha256) ||
        new Set(spec.registered_action_ids).size !== spec.registered_action_ids.length)
      fail('invalid_reviewed_runtime_spec');
    stable(spec);
    if (!(budget instanceof SharedBudget) || !audit || typeof audit.append !== 'function' ||
        !['off', 'shadow', 'active'].includes(mode) || typeof now !== 'function') fail('invalid_runtime_owner');
    if (mode !== 'off' && (!client || typeof client.evaluate !== 'function')) fail('evaluation_client_required');
    if (mode === 'shadow' && client.evidence_type !== 'synthetic') fail('synthetic_shadow_only');
    if (mode === 'active') {
      if (!plain(activation) || digest(activation) !== trusted_activation_sha256 ||
          activation.runtime_contract_sha256 !== digest({spec, budget_limits: budget.limits}) ||
          activation.source_sha256 !== spec.source_sha256 ||
          activation.canary_scope !== spec.runtime.canary_scope ||
          typeof activation.issued_at !== 'string' || typeof activation.expires_at !== 'string' ||
          !Number.isFinite(Date.parse(activation.issued_at)) || !Number.isFinite(Date.parse(activation.expires_at)) ||
          !(Date.parse(activation.issued_at) <= now() && now() < Date.parse(activation.expires_at)) ||
          Date.parse(activation.expires_at) - Date.parse(activation.issued_at) > 3600000)
        fail('exact_expiring_activation_required');
    }
    if (mode !== 'active' && (activation !== null || trusted_activation_sha256 !== null))
      fail('unexpected_activation');
    this.spec = frozenCopy(spec); this.client = client; this.audit = audit;
    this.budget = budget; this.mode = mode;
    this.activation = activation === null ? null : frozenCopy(activation);
    this.now = now; this.closed = false; this.invocations = new Set();
  }
  close() { this.closed = true; this.budget.suspend(); }
  _check(request, bindings, original) {
    if (this.closed || this.budget.suspended || !plain(request) ||
        typeof request.task_id !== 'string' || !request.task_id ||
        typeof request.invocation_id !== 'string' || !request.invocation_id ||
        typeof original !== 'function' || !plain(bindings) ||
        !['registry', 'gate', 'validate', 'blocked', 'evidence', 'baseline_action'].every(x => typeof bindings[x] === 'function'))
      fail('invalid_host_binding');
    if (this.budget.isClosed(request.task_id)) fail('task_closed');
    const key = digest([request.task_id, request.invocation_id, this.spec.candidate_id]);
    if (this.invocations.has(key)) fail('effect_replay_denied');
    this.invocations.add(key); // No retry can reexecute an effect after timeout or rejection.
  }
  async _fallback(original, request, bindings, reason, signal) {
    const baseline = bindings.baseline_action(request);
    const gate = bindings.gate(request, baseline);
    if (!plain(gate) || !Array.isArray(gate.allowed_actions) ||
        gate.hard_block === true || gate.baseline_permitted !== true ||
        !gate.allowed_actions.includes(baseline) || !bindings.validate(request, baseline)) {
      await this.audit.append({kind: 'blocked', reason, task_sha256: digest(request.task_id)});
      return bindings.blocked(request, reason);
    }
    await this.audit.append({kind: 'baseline_intent', reason, task_sha256: digest(request.task_id)});
    if (signal?.aborted) fail('cancelled');
    return original(request);
  }
  async _assessment(request, bindings, signal) {
    const state = bindings.evidence(request);
    if (!plain(state) || Buffer.byteLength(stable(state), 'utf8') > 96000) fail('invalid_evidence');
    this.budget.reserve(request.task_id, this.spec.runtime.cost_upper_bound);
    await this.audit.append({kind: 'assessment_intent', task_sha256: digest(request.task_id),
      model_sha256: digest(this.spec.runtime.model)});
    if (signal?.aborted) fail('cancelled');
    const timeoutMs = this.spec.runtime.timeout_ms;
    let timer;
    let cancellation;
    try {
      const timeout = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('timeout')), timeoutMs); });
      const cancelled = signal ? new Promise((_, reject) => {
        if (signal.aborted) reject(new Error('cancelled'));
        else { cancellation = () => reject(new Error('cancelled')); signal.addEventListener('abort', cancellation, {once: true}); }
      }) : new Promise(() => {});
      const response = await Promise.race([
        Promise.resolve().then(() => this.client.evaluate(state, this.spec.questions, this.spec.runtime.model, timeoutMs, signal)),
        timeout, cancelled]);
      if (signal?.aborted) fail('cancelled');
      const labels = this.spec.questions[this.spec.primary_question].criteria;
      const choice = response?.[this.spec.primary_question];
      if (!plain(choice) || typeof choice.label !== 'string' || !(choice.label in labels) ||
          typeof choice.confidence !== 'number' || choice.confidence < 0.75 || choice.confidence > 1)
        fail('invalid_assessment');
      return choice.label;
    } finally {
      clearTimeout(timer);
      if (cancellation) signal.removeEventListener('abort', cancellation);
    }
  }
  async invoke(original, request, bindings, {signal} = {}) {
    this._check(request, bindings, original);
    if (signal?.aborted) fail('cancelled');
    if (this.mode === 'off') return this._fallback(original, request, bindings, 'feature_off', signal);
    if (this.mode === 'shadow') {
      this._assessment(request, bindings, signal).then(
        label => this.audit.append({kind: 'shadow_result', label_sha256: digest(label), task_sha256: digest(request.task_id)}),
        () => this.audit.append({kind: 'shadow_failed', task_sha256: digest(request.task_id)})).catch(() => {});
      return this._fallback(original, request, bindings, 'shadow', signal);
    }
    if (this.activation.revoked === true || this.now() >= Date.parse(this.activation.expires_at))
      return this._fallback(original, request, bindings, 'activation_expired', signal);
    let label;
    try { label = await this._assessment(request, bindings, signal); }
    catch (_) {
      if (signal?.aborted) fail('cancelled');
      return this._fallback(original, request, bindings, 'assessment_unavailable', signal);
    }
    const action = this.spec.label_actions[label];
    if (action === null) return this._fallback(original, request, bindings, 'abstain', signal);
    const registry = bindings.registry(request);
    const gate = bindings.gate(request, action);
    if (!plain(registry) || !Object.hasOwn(registry, action) || typeof registry[action] !== 'function' ||
        !plain(gate) || !Array.isArray(gate.allowed_actions) || gate.hard_block === true ||
        !gate.allowed_actions.includes(action) ||
        gate.approval_required === true && gate.approval_granted !== true ||
        !bindings.validate(request, action) || signal?.aborted)
      return this._fallback(original, request, bindings, 'host_policy_denied', signal);
    await this.audit.append({kind: 'effect_intent', action_sha256: digest(action), task_sha256: digest(request.task_id)});
    if (signal?.aborted) fail('cancelled');
    return registry[action](request); // Never retry after an effect or its rejection.
  }
}

module.exports = Object.freeze({digest, SharedBudget, NativeRouter});
