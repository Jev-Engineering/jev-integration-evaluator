// Bounded native runtime for reviewed JavaScript/TypeScript recipe C hosts.
// This file is copied only as an owned, hashed implementation artifact.
'use strict';

const crypto = require('node:crypto');
const https = require('node:https');
const fs = require('node:fs');
const path = require('node:path');

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

function hashRegularFile(filename, maxBytes) {
  const handle = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    const info = fs.fstatSync(handle);
    if (!info.isFile() || info.nlink !== 1 || info.size > maxBytes) fail('connected_source_drift');
    const hash = crypto.createHash('sha256');
    const buffer = Buffer.allocUnsafe(65536);
    for (;;) {
      const length = fs.readSync(handle, buffer, 0, buffer.length, null);
      if (!length) break;
      hash.update(buffer.subarray(0, length));
    }
    return hash.digest('hex');
  } finally { fs.closeSync(handle); }
}

function fail(code) { const error = new Error(code); error.code = code; throw error; }
const CONNECTED_OWNER_TOKEN = Symbol('connected-owner');
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
    this.invocations = new Set();
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
  trackTask(taskId) {
    if (this.suspended || typeof taskId !== 'string' || !taskId) fail('budget_denied');
    if (!this.tasks.has(taskId)) {
      if (this.tasks.size >= this.limits.max_tasks) fail('budget_denied');
      this.tasks.set(taskId, {calls: 0, closed: false});
    }
    if (this.tasks.get(taskId).closed) fail('task_closed');
  }
  closeTask(taskId) {
    const row = this.tasks.get(taskId);
    if (!row) fail('unknown_task');
    row.closed = true; // Retain a bounded tombstone; never reset charges on retry.
  }
  isClosed(taskId) { return this.tasks.get(taskId)?.closed === true; }
  claimInvocation(taskId, invocationId, candidateId) {
    if (this.suspended || typeof invocationId !== 'string' || !invocationId ||
        typeof candidateId !== 'string' || !candidateId) fail('effect_replay_denied');
    const key = digest([taskId, invocationId, candidateId]);
    if (this.invocations.has(key)) fail('effect_replay_denied');
    if (this.invocations.size >= 100000) fail('invocation_ledger_full');
    this.invocations.add(key);
  }
  finishReservation(_reservation) {}
  settleInvocation(_taskId, _invocationId, _candidateId) {}
  suspend() { this.suspended = true; }
}

class DurableSharedBudget extends SharedBudget {
  constructor({limits, ledgerPath, identity}) {
    super(limits);
    if (typeof ledgerPath !== 'string' || !path.isAbsolute(ledgerPath) ||
        typeof identity !== 'string' || !/^[a-f0-9]{64}$/.test(identity)) fail('invalid_ledger_identity');
    const parent = path.dirname(ledgerPath);
    const parentInfo = fs.lstatSync(parent);
    if (!parentInfo.isDirectory() || parentInfo.isSymbolicLink() ||
        (parentInfo.mode & 0o077) !== 0 || parentInfo.uid !== process.getuid())
      fail('invalid_ledger_parent');
    for (const candidate of [ledgerPath, ledgerPath + '-wal', ledgerPath + '-shm']) {
      if (fs.existsSync(candidate) && fs.lstatSync(candidate).isSymbolicLink()) fail('invalid_ledger_path');
    }
    const {DatabaseSync} = require('node:sqlite');
    this.database = new DatabaseSync(ledgerPath);
    fs.chmodSync(ledgerPath, 0o600);
    try {
      this.database.exec('PRAGMA locking_mode=EXCLUSIVE; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;');
      this.database.exec('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)');
      const row = this.database.prepare('SELECT payload FROM state WHERE id=1').get();
      this.identity = identity;
      this.pending = new Set();
      if (row) {
        const saved = JSON.parse(row.payload);
        if (saved.identity !== identity || digest(saved.limits) !== digest(this.limits) ||
            saved.suspended || saved.pending.length) fail('runtime_ledger_unresolved_or_revoked');
        this.calls = saved.calls; this.cost = saved.cost;
        this.tasks = new Map(saved.tasks);
        this.invocations = new Set(saved.invocations);
      } else this._save();
    } catch (error) {
      this.database.close();
      throw error;
    }
  }
  _save() {
    const payload = JSON.stringify({identity: this.identity, limits: this.limits,
      calls: this.calls, cost: this.cost, tasks: [...this.tasks],
      invocations: [...this.invocations], pending: [...this.pending], suspended: this.suspended});
    this.database.prepare('INSERT INTO state(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload').run(payload);
  }
  reserve(taskId, upperBound) {
    const reservation = super.reserve(taskId, upperBound);
    const serial = this.calls;
    this.pending.add('provider:' + digest([taskId, serial]));
    this._save();
    return Object.freeze({...reservation, serial});
  }
  finishReservation(reservation) {
    // A conservative unresolved reservation prevents restart if a process dies before this step.
    this.pending.delete('provider:' + digest([reservation.taskId, reservation.serial]));
    this._save();
  }
  trackTask(taskId) { super.trackTask(taskId); this._save(); }
  claimInvocation(taskId, invocationId, candidateId) {
    super.claimInvocation(taskId, invocationId, candidateId);
    this.pending.add('effect:' + digest([taskId, invocationId, candidateId]));
    this._save();
  }
  settleInvocation(taskId, invocationId, candidateId) {
    this.pending.delete('effect:' + digest([taskId, invocationId, candidateId]));
    this._save();
  }
  closeTask(taskId) { super.closeTask(taskId); this._save(); }
  suspend() { super.suspend(); this._save(); }
  close() { this.database.close(); }
}

class NativeRouter {
  constructor({spec, client, audit, budget, mode = 'off', activation = null,
               trusted_activation_sha256 = null, sourceAttest = null, now = () => Date.now(),
               connectedToken = null, authorize = null}) {
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
        !/^[a-f0-9]{64}$/.test(spec.executed_source_sha256) ||
        new Set(spec.registered_action_ids).size !== spec.registered_action_ids.length)
      fail('invalid_reviewed_runtime_spec');
    stable(spec);
    if (!(budget instanceof SharedBudget) || !audit || typeof audit.append !== 'function' ||
        typeof sourceAttest !== 'function' || sourceAttest() !== spec.executed_source_sha256 ||
        !['off', 'shadow', 'active'].includes(mode) || typeof now !== 'function') fail('invalid_runtime_owner');
    if (mode !== 'off' && (!client || typeof client.evaluate !== 'function')) fail('evaluation_client_required');
    if (client?.evidence_type === 'connected' &&
        (connectedToken !== CONNECTED_OWNER_TOKEN || typeof authorize !== 'function'))
      fail('connected_owner_required');
    if (mode === 'shadow' && client.evidence_type !== 'synthetic' &&
        connectedToken !== CONNECTED_OWNER_TOKEN) fail('synthetic_shadow_only');
    if (mode === 'active') {
      if (!plain(activation) || digest(activation) !== trusted_activation_sha256 ||
          activation.runtime_contract_sha256 !== digest({spec, budget_limits: budget.limits}) ||
          activation.source_sha256 !== spec.executed_source_sha256 ||
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
    this.sourceAttest = sourceAttest; this.now = now; this.closed = false;
    this.authorize = authorize;
  }
  close() { this.closed = true; this.budget.suspend(); }
  _attest() {
    if (this.sourceAttest() !== this.spec.executed_source_sha256) fail('applied_host_source_changed');
  }
  _check(request, bindings, original) {
    if (this.closed || this.budget.suspended || !plain(request) ||
        typeof request.task_id !== 'string' || !request.task_id ||
        typeof request.invocation_id !== 'string' || !request.invocation_id ||
        typeof original !== 'function' || !plain(bindings) ||
        !['registry', 'gate', 'validate', 'blocked', 'evidence', 'baseline_action'].every(x => typeof bindings[x] === 'function'))
      fail('invalid_host_binding');
    this.budget.trackTask(request.task_id);
    this.budget.claimInvocation(request.task_id, request.invocation_id, this.spec.candidate_id);
    // Shared owner retains tombstones across routers; no retry can replay effects.
  }
  async _fallback(original, request, bindings, reason, signal) {
    const baseline = bindings.baseline_action(request);
    const gate = bindings.gate(request, baseline);
    if (!plain(gate) || !Array.isArray(gate.allowed_actions) ||
        gate.hard_block === true || gate.baseline_permitted !== true ||
        !gate.allowed_actions.includes(baseline) || !bindings.validate(request, baseline)) {
      await this.audit.append({kind: 'blocked', reason, task_sha256: digest(request.task_id)});
      const blocked = await bindings.blocked(request, reason);
      this.budget.settleInvocation(request.task_id, request.invocation_id, this.spec.candidate_id);
      return blocked;
    }
    await this.audit.append({kind: 'baseline_intent', reason, task_sha256: digest(request.task_id)});
    if (signal?.aborted) fail('cancelled');
    if (this.authorize) this.authorize('effect');
    this._attest();
    const result = await original(request);
    this.budget.settleInvocation(request.task_id, request.invocation_id, this.spec.candidate_id);
    return result;
  }
  async _assessment(request, bindings, signal) {
    const state = bindings.evidence(request);
    if (!plain(state) || Buffer.byteLength(stable(state), 'utf8') > 96000) fail('invalid_evidence');
    const reservation = this.budget.reserve(request.task_id, this.spec.runtime.cost_upper_bound);
    await this.audit.append({kind: 'assessment_intent', task_sha256: digest(request.task_id),
      model_sha256: digest(this.spec.runtime.model)});
    if (signal?.aborted) fail('cancelled');
    if (this.authorize) this.authorize('egress');
    const timeoutMs = this.spec.runtime.timeout_ms;
    let timer;
    let cancellation;
    let responseArrived = false;
    try {
      const timeout = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('timeout')), timeoutMs); });
      const cancelled = signal ? new Promise((_, reject) => {
        if (signal.aborted) reject(new Error('cancelled'));
        else { cancellation = () => reject(new Error('cancelled')); signal.addEventListener('abort', cancellation, {once: true}); }
      }) : new Promise(() => {});
      const response = await Promise.race([
        Promise.resolve().then(() => this.client.evaluate(state, this.spec.questions, this.spec.runtime.model, timeoutMs, signal)),
        timeout, cancelled]);
      responseArrived = true;
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
      if (responseArrived) this.budget.finishReservation(reservation);
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
    if (this.authorize) this.authorize('effect');
    this._attest();
    const result = await registry[action](request); // Never retry after an effect or its rejection.
    this.budget.settleInvocation(request.task_id, request.invocation_id, this.spec.candidate_id);
    return result;
  }
}

function finiteProbability(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
}

function validateTypedResponse(response, questions, model) {
  if (!plain(response) || response.model !== model || !plain(response.answers) ||
      Object.keys(response.answers).sort().join('|') !== Object.keys(questions).sort().join('|') ||
      !plain(response.usage) || !['input_tokens', 'output_tokens'].every(
        key => Number.isSafeInteger(response.usage[key]) && response.usage[key] >= 0))
    fail('invalid_typed_response');
  for (const [name, question] of Object.entries(questions)) {
    const answer = response.answers[name];
    if (!plain(question) || !plain(answer) || answer.type !== question.type) fail('invalid_typed_response');
    if (question.type === 'noul') {
      if (!finiteProbability(answer.noul) || Object.hasOwn(answer, 'confidence')) fail('invalid_typed_response');
      continue;
    }
    const labels = question.type === 'choice' ? Object.keys(question.criteria || {}) :
      Array.isArray(question.criteria) ? question.criteria.map((_, i) => String(i)) : [];
    if (!['choice', 'score'].includes(question.type) || !labels.length ||
        !finiteProbability(answer.confidence) || !plain(answer.probabilities) ||
        Object.keys(answer.probabilities).sort().join('|') !== labels.sort().join('|') ||
        !Object.values(answer.probabilities).every(finiteProbability) ||
        Math.abs(Object.values(answer.probabilities).reduce((a, b) => a + b, 0) - 1) > 1e-5)
      fail('invalid_typed_response');
    if (question.type === 'choice') {
      if (!labels.includes(answer.choice) ||
          answer.probabilities[answer.choice] + 1e-6 < Math.max(...Object.values(answer.probabilities)))
        fail('invalid_typed_response');
    } else {
      const expected = Object.entries(answer.probabilities).reduce((sum, [key, probability]) =>
        sum + Number(key) * probability, 0);
      if (!Number.isFinite(answer.score) || answer.score < 0 || answer.score > labels.length - 1 ||
          Math.abs(answer.score - expected) > 1e-4 || !plain(answer.legend) ||
          Object.keys(answer.legend).sort().join('|') !== labels.join('|')) fail('invalid_typed_response');
    }
  }
  return response;
}

function parseUniqueJson(raw) {
  const source = raw.toString('utf8');
  let position = 0;
  const space = () => { while (/\s/.test(source[position] || '')) position++; };
  const string = () => {
    const begin = position++;
    let escaped = false;
    while (position < source.length) {
      const char = source[position++];
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === '"') return JSON.parse(source.slice(begin, position));
    }
    fail('invalid_typed_response');
  };
  const value = depth => {
    if (depth > 32) fail('invalid_typed_response');
    space();
    if (source[position] === '{') {
      position++; space(); const keys = new Set();
      if (source[position] === '}') { position++; return; }
      while (position < source.length) {
        if (source[position] !== '"') fail('invalid_typed_response');
        const key = string();
        if (keys.has(key)) fail('invalid_typed_response');
        keys.add(key); space();
        if (source[position++] !== ':') fail('invalid_typed_response');
        value(depth + 1); space();
        const next = source[position++];
        if (next === '}') return;
        if (next !== ',') fail('invalid_typed_response');
        space();
      }
      fail('invalid_typed_response');
    }
    if (source[position] === '[') {
      position++; space();
      if (source[position] === ']') { position++; return; }
      while (position < source.length) {
        value(depth + 1); space();
        const next = source[position++];
        if (next === ']') return;
        if (next !== ',') fail('invalid_typed_response');
      }
      fail('invalid_typed_response');
    }
    if (source[position] === '"') { string(); return; }
    const start = position;
    while (position < source.length && !/[\s,}\]]/.test(source[position])) position++;
    if (position === start) fail('invalid_typed_response');
    JSON.parse(source.slice(start, position));
  };
  try {
    value(0); space();
    if (position !== source.length) fail('invalid_typed_response');
    return JSON.parse(source);
  } catch (_) { fail('invalid_typed_response'); }
}

function nativeHttpsPost(endpoint, payload, key, timeoutMs, signal) {
  return new Promise((resolve, reject) => {
    const request = https.request(endpoint, {method: 'POST', timeout: timeoutMs, signal,
      headers: {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
        'User-Agent': 'jev-integration-evaluator/1.3', 'Content-Length': payload.length}}, response => {
      const chunks = []; let size = 0;
      response.on('data', chunk => {
        size += chunk.length;
        if (size > 2_000_000) { request.destroy(); reject(Error('provider_response_too_large')); }
        else chunks.push(chunk);
      });
      response.on('end', () => {
        if (response.statusCode !== 200) reject(Error('provider_http_failure'));
        else resolve(Buffer.concat(chunks));
      });
      response.on('error', () => reject(Error('provider_transport_failed')));
    });
    request.on('timeout', () => { request.destroy(); reject(Error('provider_timeout')); });
    request.on('error', () => reject(Error('provider_transport_failed')));
    request.end(payload);
  });
}

class TypeSafeConnectedClient {
  constructor({endpoint, approvedEndpoint, credentialRef = 'env:TYPESAFE_API_KEY',
               model = 'jev-1.13.0', transport = nativeHttpsPost, environment = process.env}) {
    let url;
    try { url = new URL(endpoint); } catch (_) { fail('invalid_provider_endpoint'); }
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash ||
        (endpoint !== 'https://api.typesafe.ai/v1/systemone' && endpoint !== approvedEndpoint) ||
        credentialRef !== 'env:TYPESAFE_API_KEY' || model !== 'jev-1.13.0' ||
        typeof transport !== 'function' || typeof environment?.TYPESAFE_API_KEY !== 'string' ||
        !environment.TYPESAFE_API_KEY) fail('invalid_connected_client');
    this.endpoint = endpoint; this.model = model; this.transport = transport;
    this.environment = environment; this.key = environment.TYPESAFE_API_KEY;
    this.evidence_type = 'connected';
  }
  credentialStillCurrent() {
    const current = this.environment.TYPESAFE_API_KEY;
    return typeof current === 'string' && Buffer.byteLength(current) === Buffer.byteLength(this.key) &&
      crypto.timingSafeEqual(Buffer.from(current), Buffer.from(this.key));
  }
  async evaluate(state, questions, model, timeoutMs, signal) {
    if (!this.credentialStillCurrent()) fail('provider_credential_rotated');
    if (model !== this.model || !Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 120000)
      fail('invalid_connected_request');
    const payload = Buffer.from(JSON.stringify({state, questions, model}), 'utf8');
    if (payload.length > 96000) fail('provider_request_too_large');
    let raw;
    try { raw = await this.transport(this.endpoint, payload, this.key, timeoutMs, signal); }
    catch (_) { fail('provider_transport_failed'); }
    if (!Buffer.isBuffer(raw) || raw.length > 2_000_000) fail('provider_response_too_large');
    const response = parseUniqueJson(raw);
    validateTypedResponse(response, questions, model);
    const choices = Object.fromEntries(Object.entries(questions)
      .filter(([, question]) => question.type === 'choice')
      .map(([name]) => [name, {label: response.answers[name].choice,
        confidence: response.answers[name].confidence}]));
    if (!Object.keys(choices).length) fail('connected_primary_choice_required');
    return choices;
  }
}

class ConnectedNativeOwner {
  constructor({spec, descriptor, audit, verifyAuthority, currentEnvironmentDigest,
               sourceAttest, environment = process.env, transport = nativeHttpsPost,
               now = () => Date.now()}) {
    if (process.platform !== 'linux' || process.version !== 'v24.18.0' ||
        !plain(descriptor) || descriptor.schema_version !== '1.0' ||
        descriptor.kind !== 'node-connected-owner-v1' ||
        digest(descriptor.runtime_profile) !== digest({platform: 'linux', node: 'v24.18.0',
          apis: ['node:sqlite.DatabaseSync', 'AbortSignal', 'node:https', 'node:crypto']}) ||
        !['shadow', 'canary', 'active'].includes(descriptor.mode) ||
        descriptor.spec_sha256 !== digest(spec) || spec.runtime.model !== 'jev-1.13.0' ||
        descriptor.model !== 'jev-1.13.0' || descriptor.credential_ref !== 'env:TYPESAFE_API_KEY' ||
        typeof verifyAuthority !== 'function' || typeof currentEnvironmentDigest !== 'function' ||
        typeof sourceAttest !== 'function' || typeof now !== 'function' ||
        !audit || typeof audit.append !== 'function') fail('invalid_connected_owner');
    if (transport !== nativeHttpsPost && descriptor.mode !== 'shadow') fail('fixture_transport_shadow_only');
    this.fixtureTransport = transport !== nativeHttpsPost;
    const core = {schema_version: descriptor.schema_version, kind: descriptor.kind,
      runtime_profile: descriptor.runtime_profile,
      mode: descriptor.mode, spec_sha256: descriptor.spec_sha256,
      source_sha256: descriptor.source_sha256, source_plan: descriptor.source_plan,
      environment_digest: descriptor.environment_digest,
      endpoint: descriptor.endpoint, credential_ref: descriptor.credential_ref,
      model: descriptor.model, budget_limits: descriptor.budget_limits,
      ledger_path: descriptor.ledger_path,
      install_receipt_sha256: descriptor.install_receipt_sha256,
      configuration_sha256: descriptor.configuration_sha256};
    if (descriptor.core_sha256 !== digest(core) || !plain(descriptor.egress_grant) ||
        descriptor.descriptor_sha256 !== digest(Object.fromEntries(
          Object.entries(descriptor).filter(([key]) => key !== 'descriptor_sha256'))) ||
        descriptor.egress_grant.core_sha256 !== descriptor.core_sha256 ||
        descriptor.egress_grant.mode !== descriptor.mode ||
        descriptor.egress_grant.endpoint !== descriptor.endpoint ||
        descriptor.egress_grant.model !== descriptor.model ||
        descriptor.egress_grant.credential_ref !== descriptor.credential_ref ||
        descriptor.egress_grant.environment_digest !== descriptor.environment_digest ||
        descriptor.source_sha256 !== spec.executed_source_sha256 ||
        !plain(descriptor.source_plan) || !Array.isArray(descriptor.source_plan.files) ||
        !descriptor.source_plan.files.length || descriptor.source_plan.files.length > 64 ||
        !/^[a-f0-9]{64}$/.test(descriptor.environment_digest)) fail('connected_grant_binding_invalid');
    this.descriptor = frozenCopy(descriptor);
    this.verifyAuthority = verifyAuthority;
    this.currentEnvironmentDigest = currentEnvironmentDigest;
    this.sourceAttest = sourceAttest;
    this.now = now;
    this.closed = false;
    this._checkLive('startup');
    const limits = descriptor.budget_limits;
    if (!plain(limits) || !Number.isSafeInteger(limits.max_calls) ||
        !Number.isFinite(limits.max_cost)) fail('invalid_connected_budget');
    const identity = digest({core_sha256: descriptor.core_sha256,
      egress_grant_sha256: digest(descriptor.egress_grant),
      activation_sha256: descriptor.activation ? digest(descriptor.activation) : null});
    this.budget = new DurableSharedBudget({limits, ledgerPath: descriptor.ledger_path, identity});
    try {
      this.client = new TypeSafeConnectedClient({endpoint: descriptor.endpoint,
        approvedEndpoint: descriptor.endpoint, credentialRef: descriptor.credential_ref,
        model: descriptor.model, transport, environment});
      const common = {spec, budget: this.budget, audit, client: this.client,
        sourceAttest, now, connectedToken: CONNECTED_OWNER_TOKEN,
        authorize: phase => this._authorize(phase)};
      if (descriptor.mode === 'shadow') {
        if (descriptor.activation !== null) fail('unexpected_connected_activation');
        this.router = new NativeRouter({...common, mode: 'shadow'});
      } else {
        this._checkActivation(spec);
        const receipt = descriptor.activation.receipt;
        const activation = {runtime_contract_sha256: digest({spec, budget_limits: this.budget.limits}),
          source_sha256: spec.executed_source_sha256, canary_scope: spec.runtime.canary_scope,
          issued_at: receipt.issued_at, expires_at: receipt.expires_at};
        this.router = new NativeRouter({...common, mode: 'active', activation,
          trusted_activation_sha256: digest(activation)});
        if (descriptor.mode === 'canary') this.baselineRouter = new NativeRouter({
          spec, budget: this.budget, audit, mode: 'off', sourceAttest, now,
          authorize: phase => this._authorize(phase)});
      }
    } catch (error) {
      this.budget.close();
      throw error;
    }
  }
  _checkFiles() {
    const seen = new Set();
    const roles = new Set();
    for (const row of this.descriptor.source_plan.files) {
      if (!plain(row) || typeof row.path !== 'string' || !path.isAbsolute(row.path) ||
          typeof row.role !== 'string' || !/^[a-f0-9]{64}$/.test(row.sha256) ||
          seen.has(row.path) || roles.has(row.role)) fail('connected_source_plan_invalid');
      seen.add(row.path);
      roles.add(row.role);
      try {
        for (let current = row.path; current !== path.dirname(current); current = path.dirname(current)) {
          if (fs.lstatSync(current).isSymbolicLink()) fail('connected_source_drift');
        }
        const maxBytes = row.role === 'node' ? 250_000_000 :
          row.role === 'typescript_compiler' ? 64_000_000 : 2_000_000;
        if (hashRegularFile(row.path, maxBytes) !== row.sha256)
          fail('connected_source_drift');
      } catch (_) { fail('connected_source_drift'); }
    }
    if (!['executed_source', 'runtime', 'adapter', 'entrypoint', 'package', 'lock', 'node', 'npm',
          'reviewed_configuration']
        .every(role => roles.has(role))) fail('connected_source_plan_incomplete');
    const source = this.descriptor.source_plan.files.find(row => row.role === 'executed_source');
    if (source.sha256 !== this.descriptor.source_sha256) fail('connected_source_binding_mismatch');
  }
  _checkLive(_phase) {
    if (this.closed) fail('connected_owner_closed');
    const descriptor = this.descriptor;
    const grant = descriptor.egress_grant;
    if (!(Date.parse(grant.issued_at) <= this.now() && this.now() < Date.parse(grant.expires_at)) ||
        this.verifyAuthority('egress_grant', digest(grant)) !== true ||
        this.currentEnvironmentDigest() !== descriptor.environment_digest ||
        (this.client && !this.client.credentialStillCurrent()))
      fail('connected_authority_expired_or_revoked');
    this._checkFiles();
    if (this.sourceAttest() !== descriptor.source_sha256) fail('connected_source_drift');
    if (descriptor.mode !== 'shadow') this._checkActivationLive();
  }
  _checkActivation(spec) {
    const activation = this.descriptor.activation;
    if (!plain(activation) || !plain(activation.recomputed_report) ||
        activation.recomputed_report.recommendation !== 'keep' ||
        activation.recomputed_report.holdout_evidence_verified !== true ||
        activation.recomputed_report.evidence_type !== 'observed' ||
        activation.recomputed_report.mode !== this.descriptor.mode ||
        activation.recomputed_report.spec_sha256 !== digest(spec) ||
        !plain(activation.deployment_grant) || !plain(activation.receipt) ||
        activation.deployment_grant.study_digest !== activation.recomputed_report.study_digest ||
        activation.deployment_grant.gate_manifest_digest !== activation.recomputed_report.gate_manifest_digest ||
        activation.deployment_grant.mode !== this.descriptor.mode ||
        activation.receipt.runtime_contract_sha256 !== digest({spec, budget_limits: this.budget.limits}) ||
        activation.receipt.deployment_id !== activation.deployment_grant.deployment_id ||
        activation.receipt.source_sha256 !== spec.executed_source_sha256)
      fail('connected_activation_invalid');
    this._checkActivationLive();
  }
  _checkActivationLive() {
    const item = this.descriptor.activation;
    if (!plain(item.evidence_refs)) fail('connected_evidence_reference_drift');
    for (const row of Object.values(item.evidence_refs)) {
      try {
        if (!plain(row) || typeof row.path !== 'string' || !path.isAbsolute(row.path) ||
            fs.lstatSync(row.path).isSymbolicLink() ||
            crypto.createHash('sha256').update(fs.readFileSync(row.path)).digest('hex') !== row.sha256)
          fail('connected_evidence_reference_drift');
      } catch (_) { fail('connected_evidence_reference_drift'); }
    }
    for (const [kind, value] of [['gate_recomputation', item.recomputed_report],
                                  ['deployment_grant', item.deployment_grant],
                                  ['activation_receipt', item.receipt]]) {
      if (this.verifyAuthority(kind, digest(value)) !== true) fail('connected_activation_revoked');
    }
    if (this.verifyAuthority('study', item.recomputed_report.study_digest) !== true ||
        !(Date.parse(item.deployment_grant.issued_at) <= this.now() &&
          this.now() < Date.parse(item.deployment_grant.expires_at)) ||
        !(Date.parse(item.receipt.issued_at) <= this.now() &&
          this.now() < Date.parse(item.receipt.expires_at))) fail('connected_activation_expired');
  }
  _authorize(phase) {
    try { this._checkLive(phase); }
    catch (error) {
      if (this.budget && !this.budget.suspended) this.budget.suspend();
      throw error;
    }
  }
  async invoke(original, request, bindings, options = {}) {
    this._authorize('invoke');
    let router = this.router;
    if (this.descriptor.mode === 'canary') {
      const fraction = this.descriptor.activation.deployment_grant.cohort_fraction;
      if (!finiteProbability(fraction)) fail('invalid_canary_cohort');
      const bucket = Number.parseInt(digest(request.task_id).slice(0, 8), 16) / 0x100000000;
      if (bucket >= fraction) router = this.baselineRouter;
    }
    return router.invoke(original, request, bindings, options);
  }
  completeTask(taskId) { this.budget.closeTask(taskId); }
  suspend() { this.budget.suspend(); }
  status() {
    if (!this.closed && !this.budget.suspended) {
      try { this._authorize('status'); } catch (_) { /* durable suspension is reported below */ }
    }
    return Object.freeze({mode: this.budget.suspended ? 'off' : this.descriptor.mode,
    suspended: this.budget.suspended, calls: this.budget.calls, cost: this.budget.cost,
    evidence_type: this.fixtureTransport ? 'synthetic_protocol' : 'provider_unqualified'}); }
  close() { this.closed = true; this.budget.close(); }
}

// A host explicitly pins one runtime copy and a finite placement set. This
// owner is for offline synthetic fixtures only, never connected authority.
const runtimeOwners = new WeakSet();
function createRuntimeOwner({specHashes, limits, ledgerPath}) {
  if (!Array.isArray(specHashes) || specHashes.length < 2 || specHashes.length > 4 ||
      new Set(specHashes).size !== specHashes.length ||
      specHashes.some(value => typeof value !== 'string' || !/^[a-f0-9]{64}$/.test(value)))
    fail('invalid_runtime_owner_placements');
  const reviewed = Object.freeze([...specHashes].sort());
  const budget = new DurableSharedBudget({limits, ledgerPath,
    identity: digest({kind: 'synthetic-installed-placement-owner/v1', specHashes: reviewed, limits})});
  const bound = new Set();
  const owner = Object.freeze({runtimePath: __filename,
    createRouter(options) {
      const specHash = digest(options.spec);
      if (!reviewed.includes(specHash) || bound.has(specHash) ||
          options.client?.evidence_type !== 'synthetic') fail('runtime_owner_placement_mismatch');
      const router = new NativeRouter({...options, budget});
      bound.add(specHash);
      return router;
    },
    status: () => Object.freeze({calls: budget.calls, cost: budget.cost,
      suspended: budget.suspended, placements_bound: bound.size,
      evidence_type: 'synthetic_installed_protocol'}),
    close: () => budget.close()});
  runtimeOwners.add(owner);
  return owner;
}
function isRuntimeOwner(owner) { return runtimeOwners.has(owner); }

module.exports = Object.freeze({digest, SharedBudget, DurableSharedBudget, NativeRouter,
  TypeSafeConnectedClient, validateTypedResponse, ConnectedNativeOwner, createRuntimeOwner, isRuntimeOwner});
