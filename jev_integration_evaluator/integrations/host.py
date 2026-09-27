"""Pattern-specific host wiring. Assessments propose; existing host gates still decide.

Only the deliberately bounded module-tail-call shape uses these contracts. Host
callbacks are trusted application code, not model-provided snippets. Off/shadow
retain the original operation. No handler installs dependencies or grants approval.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import math
import threading
import weakref

from ..budget import BudgetCoordinator
from ..io import InputError, canonical, digest
from ..runtime import HostGate, SafeRouter


class PolicyBlock(Exception):
    """A pre-execution policy failure; the message is a fixed diagnostic code."""


class PartialPlanError(RuntimeError):
    """A plan stopped after an effect; completed results remain available, never replayed."""
    def __init__(self, completed_results, failed_step):
        super().__init__('bounded_plan_stopped_after_completed_steps')
        self.completed_results = tuple(completed_results)
        self.failed_step = failed_step


class UseFallback(Exception):
    pass


_ownership_lock = threading.RLock()
_coordinators: dict[str, weakref.ReferenceType] = {}
_routers: dict[tuple[str, str], weakref.ReferenceType] = {}
_delegation_slots = weakref.WeakKeyDictionary()


def _read(function, *args):
    try:
        return function(*args)
    except Exception:
        raise PolicyBlock('host_binding_failed') from None


def _gate(value):
    if (not isinstance(value, HostGate) or not isinstance(value.allowed_actions, tuple)
            or any(type(getattr(value, k)) is not bool for k in
                   ('hard_block', 'approval_required', 'approval_granted', 'baseline_permitted'))
            or not all(isinstance(k, str) and k for k in value.allowed_actions)
            or len(set(value.allowed_actions)) != len(value.allowed_actions)):
        raise PolicyBlock('invalid_host_gate')
    return value


def _registry(value):
    if (not isinstance(value, dict) or not 1 <= len(value) <= 255
            or not all(isinstance(k, str) and k for k in value)):
        raise PolicyBlock('invalid_registered_options')
    return dict(value)


def _register_owner(spec, router):
    if (not isinstance(router, SafeRouter) or not router.require_expiring_activation
            or not router.require_runtime_binding or not isinstance(router.budget_coordinator, BudgetCoordinator)
            or router.log is None):
        raise PolicyBlock('strict_host_owned_runtime_and_shared_budget_required')
    wanted = spec['runtime']
    actual = copy.deepcopy(router.config)
    actual['mode'] = 'off'  # Actual mode still belongs to the expiring runtime receipt.
    if (actual != wanted['configuration'] or router.policy_version != wanted['policy_version']
            or router.canary_scope != wanted['canary_scope']):
        raise PolicyBlock('runtime_configuration_binding_mismatch')
    scope, placement = router.canary_scope, (router.canary_scope, spec['candidate_id'])
    with _ownership_lock:
        # Dead weak references are bounded ownership tombstones, not permission
        # to reconstruct a router/coordinator and erase previously charged work.
        # A new workflow scope needs separate host review and runtime receipts.
        if len(_routers) >= 1024 and placement not in _routers:
            raise PolicyBlock('host_ownership_registry_full')
        existing = _coordinators.get(scope)
        if existing is not None and existing() is not router.budget_coordinator:
            raise PolicyBlock('workflow_must_share_one_budget_coordinator')
        existing = _routers.get(placement)
        if existing is not None and existing() is not router:
            raise PolicyBlock('runtime_must_not_be_reconstructed_per_decision')
        _coordinators[scope] = weakref.ref(router.budget_coordinator)
        _routers[placement] = weakref.ref(router)


class Context:
    def __init__(self, spec, original, request, bindings, router):
        self.spec, self.original, self.request, self.b = spec, original, request, bindings
        self.router = router
        # Once a host operation starts, no outer router fallback may replay it.
        # Keep the actual exception object: host guards must see its real type.
        self.host_operation_started = False
        self.host_operation_exception = None
        self.host_guard_exception = None
        self.policy = spec['policy']
        self.task_field = spec['runtime']['task_field']
        if not isinstance(request, dict) or not isinstance(request.get(self.task_field), str) or not request[self.task_field]:
            raise PolicyBlock('stable_task_identity_required')
        self.task_id = request[self.task_field]
        try: self.request_hash = digest(request)
        except (TypeError, ValueError): raise PolicyBlock('bounded_json_input_required') from None
        self.options = _registry(_read(self.b['registry'], copy.deepcopy(request)))
        if not set(self.options) <= set(spec['registered_action_ids']):
            raise PolicyBlock('runtime_registry_contains_unreviewed_action_ids')
        self.baseline = _read(self.b['baseline_action'], copy.deepcopy(request))
        if not isinstance(self.baseline, str) or self.baseline not in self.options:
            raise PolicyBlock('baseline_is_not_a_registered_option')

    def host_operation(self, function, *args):
        """Cross the host-effect boundary without converting host control flow."""
        self.host_operation_started = True
        try:
            return function(*args)
        except (PolicyBlock, UseFallback) as exc:
            self.host_operation_exception = exc
            raise

    def stable(self):
        if self.request.get(self.task_field) != self.task_id or digest(self.request) != self.request_hash:
            raise PolicyBlock('task_or_arguments_changed_after_assessment')

    @contextmanager
    def guard(self):
        cm = _read(self.b['guard'], self.request)
        if not hasattr(cm, '__enter__') or not hasattr(cm, '__exit__'):
            raise PolicyBlock('host_atomic_guard_required')
        # A guard may raise its own signal while entering or cleaning up. Keep
        # it distinct from a policy signal raised by the guarded body, without
        # changing the exception the host's __exit__ receives.
        body_exception = None
        try:
            with cm:
                try:
                    yield
                except BaseException as exc:
                    body_exception = exc
                    raise
        except (PolicyBlock, UseFallback) as exc:
            if exc is not body_exception:
                self.host_guard_exception = exc
            raise

    def audit_intent(self, action):
        try:
            self.router.log.append({'type': 'host_execution_intent', 'recipe': self.spec['recipe']['id'],
                                    'candidate_id': self.spec['candidate_id'], 'task_id_hash': digest(self.task_id),
                                    'action_id': action, 'execution_authorized': False})
        except Exception:
            raise PolicyBlock('audit_failed_before_execution') from None

    def late(self, action, *, registry=None, expected=None, receipt=True):
        """Caller holds the EXISTING host lock across this check and the operation."""
        self.stable()
        current = _registry(_read(registry or self.b['registry'], self.request))
        if action not in current:
            raise PolicyBlock('action_no_longer_registered')
        if expected is not None and current[action] is not expected:
            raise PolicyBlock('registered_executor_changed')
        if _read(self.b['validate'], self.request, action) is not True:
            raise PolicyBlock('arguments_or_state_not_valid')
        gate = _gate(_read(self.b['gate'], self.request, action))
        if (action not in gate.allowed_actions or gate.hard_block
                or (gate.approval_required and not gate.approval_granted)):
            raise PolicyBlock('late_host_authorization_denied')
        if receipt and (self.router.suspended or self.router.closed or not self.router.budget_coordinator.permits_result(self.task_id)
                        or not self.router._active_authorized(self.spec['questions'], self.spec['primary_question'],
                                                              self.spec['evidence_question'], self.spec['label_actions'])):
            raise PolicyBlock('runtime_revoked_expired_or_exhausted_before_execution')
        return current[action]

    def evidence(self, outcome=None):
        args = (copy.deepcopy(self.request), outcome) if self.spec['recipe']['id'] == 'python.E' else (copy.deepcopy(self.request),)
        value = _read(self.b['evidence'], *args)
        try:
            if len(canonical(value)) > self.spec['runtime']['max_evidence_bytes']:
                raise PolicyBlock('evidence_byte_limit')
        except (TypeError, ValueError):
            raise PolicyBlock('evidence_must_be_bounded_json') from None
        return value

    def select(self, evidence=None):
        if evidence is None: evidence = self.evidence()
        if not evidence: raise UseFallback('missing_evidence')
        gate = _gate(_read(self.b['gate'], self.request, self.baseline))
        legal = tuple(a for a in gate.allowed_actions if a in self.options)
        gate = HostGate(legal, gate.hard_block, gate.approval_required, gate.approval_granted, gate.baseline_permitted)
        d = self.router.route(task_id=self.task_id, state=evidence, questions=self.spec['questions'],
                              primary_question=self.spec['primary_question'], evidence_question=self.spec['evidence_question'],
                              baseline_action=self.baseline, gate=gate, label_actions=self.spec['label_actions'],
                              estimated_cost_upper_bound=self.spec['runtime']['cost_upper_bound'],
                              immutable_state=False, cache_scope=None,
                              provenance={'candidate_id': self.spec['candidate_id'], 'experiment_id': self.spec['experiment_id'],
                                          'source_location': {'file': self.spec['source']['file'], 'symbol': self.spec['source']['symbol'],
                                                              'source_sha256': self.spec['source']['source_sha256']}})
        self.stable()
        if d.source != 'jev_assessment': raise UseFallback(d.reason)
        if d.action not in self.options: raise PolicyBlock('unregistered_proposal')
        return d.action

    def fallback(self, reason):
        if self.policy['fallback'] != 'baseline':
            return self.host_operation(self.b['blocked'], self.request, reason)
        with self.guard():
            self.audit_intent(self.baseline)
            self.late(self.baseline, receipt=False)
            return self.host_operation(self.original, self.request)

    def execute(self, action, extra=None):
        fn = self.options.get(action)
        if not callable(fn): raise PolicyBlock('registered_option_is_not_callable')
        with self.guard():
            self.audit_intent(action)
            if extra is not None: extra()
            self.late(action, expected=fn)
            # There is deliberately no retry or fallback surrounding this call.
            return self.host_operation(fn, self.request)


def _action_a(c):
    action = c.select()
    if action != c.baseline:
        raise PolicyBlock('preexecution_decision_blocked')
    return c.execute(action)


def _action_b(c):
    action = c.select()
    def risk_check():
        value = _read(c.b['risk'], c.request, action)
        if not isinstance(value, dict): raise PolicyBlock('invalid_host_risk_policy')
        remaining, cost = value.get('budget_remaining'), value.get('estimated_cost')
        if (type(remaining) not in (int, float) or type(cost) not in (int, float)
                or not math.isfinite(remaining) or not math.isfinite(cost) or cost < 0 or remaining < cost
                or value.get('scope_authorized') is not True
                or type(value.get('irreversible')) is not bool
                or (value['irreversible'] and value.get('approval_granted') is not True)):
            raise PolicyBlock('scope_budget_or_irreversible_approval_denied')
    return c.execute(action, risk_check)


def _action_c(c):
    return c.execute(c.select())


def _items(c, provenance=False):
    records = _read(c.b['items'], copy.deepcopy(c.request))
    if not isinstance(records, list) or len(records) > c.policy['max_items']:
        raise PolicyBlock('item_bound_exceeded')
    if any(not isinstance(x, dict) or not isinstance(x.get('id'), str) or not x['id'] for x in records):
        raise PolicyBlock('invalid_item_identity')
    if len({x['id'] for x in records}) != len(records): raise PolicyBlock('duplicate_item_identity')
    if provenance and any(not x.get('provenance') for x in records): raise PolicyBlock('missing_evidence_provenance')
    try:
        if len(canonical(records)) > c.spec['runtime']['max_evidence_bytes']: raise PolicyBlock('item_byte_limit')
    except (ValueError, TypeError): raise PolicyBlock('items_must_be_json') from None
    return copy.deepcopy(records)


def _selected_items(c, action, records, pinned):
    keep = c.options[action]
    ids = {x['id'] for x in records}
    if (not isinstance(keep, (list, tuple)) or not all(isinstance(k, str) for k in keep)
            or len(set(keep)) != len(keep) or not set(keep) <= ids):
        raise PolicyBlock('invalid_existing_selection_option')
    selected = set(keep) | {x['id'] for x in records if pinned(x)}
    return [copy.deepcopy(x) for x in records if x['id'] in selected]


def _action_d(c):
    records = _items(c, provenance=True)
    action = c.select()
    selected = _selected_items(c, action, records,
                               lambda x: x.get('contradictory') is True or x.get('uncertain') is True)
    with c.guard():
        c.audit_intent(action)
        if _items(c, provenance=True) != records: raise PolicyBlock('retrieved_evidence_changed')
        if c.late(action) != c.options[action]: raise PolicyBlock('evidence_selection_changed')
        # Relevance only selects supplied records. It never turns them into facts.
        return c.host_operation(c.b['generate'], c.request, selected)


def _lookup(value, path):
    for key in path:
        if not isinstance(value, dict) or key not in value: raise PolicyBlock('postcondition_observation_missing')
        value = value[key]
    return value


def _postconditions(c, before, after, outcome):
    environment = {'before': before, 'after': after, 'outcome': outcome}
    saw_independent_change = False
    for rule in c.policy['postconditions']:
        path = rule['path'].split('.')
        value = _lookup(environment, path)
        if rule['operation'] == 'equals':
            if value != rule['value']: return False
        else:
            if path[0] != 'after': return False
            prior = _lookup(before, path[1:])
            delta = rule['value']
            if (type(value) not in (int, float) or type(prior) not in (int, float) or type(delta) not in (int, float)
                    or not all(math.isfinite(n) for n in (value, prior, delta)) or delta == 0 or value - prior != delta):
                return False
            saw_independent_change = True
    return saw_independent_change


def _action_e(c):
    # Execute once under the existing host policy. No assessment can authorize it.
    with c.guard():
        c.audit_intent(c.baseline)
        c.late(c.baseline, receipt=False)
        before = copy.deepcopy(_read(c.b['observe'], c.request))
        outcome = c.host_operation(c.original, c.request)
        # A completed side effect is never described as rolled back by this handler.
        try: after = copy.deepcopy(_read(c.b['observe'], c.request))
        except PolicyBlock: return c.host_operation(c.b['finish'], c.request, outcome, c.policy['failure_action'])
    disposition = c.policy['failure_action']
    try:
        action = c.select({'host': c.evidence(copy.deepcopy(outcome)), 'before': before, 'after': after, 'outcome': outcome})
        independently_valid = _postconditions(c, before, after, outcome)
        host_valid = _read(c.b['postcondition'], c.request, outcome, {'before': before, 'after': after}) is True
        with c.guard():
            c.late(action)
            if action == c.policy['success_action'] and independently_valid and host_valid:
                disposition = action
    except (PolicyBlock, UseFallback) as exc:
        if exc is c.host_guard_exception:
            raise
        pass
    # The host's read-only finishing operation receives the REAL completed outcome.
    return c.host_operation(c.b['finish'], c.request, outcome, disposition)


def _transition_value(c, action, values):
    value = c.options.get(action)
    if value not in values: raise PolicyBlock('unregistered_disposition_value')
    with c.guard():
        c.audit_intent(action)
        if c.late(action) != value: raise PolicyBlock('disposition_changed')
        return value


def _action_f(c):
    step = _read(c.b['attempt'], c.request)
    if type(step) is not int or step < 0: raise PolicyBlock('invalid_step_index')
    if any(v not in ('continue', 'stop', 'inspect') for v in c.options.values()):
        raise PolicyBlock('invalid_agent_transition_registry')
    if step >= c.policy['max_steps']:
        c.stable()
        # No extra iteration, model call, or fallback execution at the step limit.
        if 'stop' not in c.options.values(): raise PolicyBlock('registered_stop_transition_required')
        return 'stop'
    action = c.select()
    if _read(c.b['attempt'], c.request) != step: raise PolicyBlock('agent_step_changed')
    return _transition_value(c, action, ('continue', 'stop', 'inspect'))


def _action_g(c):
    action = c.select()
    plan = c.options[action]
    if (not isinstance(plan, (list, tuple)) or not 1 <= len(plan) <= c.policy['max_steps']
            or not all(isinstance(step, str) and step for step in plan) or len(set(plan)) != len(plan)):
        raise PolicyBlock('unsupported_plan_shape_or_duplicate_nonidempotent_step')
    steps = _registry(_read(c.b['step_registry'], c.request))
    if any(step not in steps or not callable(steps[step]) for step in plan):
        raise PolicyBlock('plan_contains_unregistered_steps')
    results = []
    # Validate the plan option, then recheck legality for EACH actual step.
    with c.guard():
        if c.late(action) != plan: raise PolicyBlock('registered_plan_changed')
    for step in plan:
        try:
            with c.guard():
                c.audit_intent(step)
                fn = c.late(step, registry=c.b['step_registry'], expected=steps[step])
                results.append(c.host_operation(fn, c.request))
        except PolicyBlock as exc:
            if exc is c.host_operation_exception or exc is c.host_guard_exception:
                raise
            if results:
                raise PartialPlanError(results, step) from exc
            raise
    return c.host_operation(c.b['finish'], c.request, results)


def _action_h(c):
    if c.request.get(c.policy['choice_field']) != '/prune':
        raise PolicyBlock('explicit_prune_required_compaction_is_a_separate_host_operation')
    records = _items(c)
    action = c.select()
    selected = _selected_items(c, action, records, lambda x: x.get('pinned') is True)
    with c.guard():
        c.audit_intent(action)
        if _items(c) != records: raise PolicyBlock('context_changed_after_assessment')
        if c.late(action) != c.options[action]: raise PolicyBlock('retention_option_changed')
        return c.host_operation(c.b['retain'], c.request, selected)


def _action_i(c):
    state = _read(c.b['effect_state'], c.request)
    if not isinstance(state, dict) or type(state.get('idempotent')) is not bool:
        raise PolicyBlock('explicit_effect_state_required')
    if state.get('state') == 'completed':
        c.stable()
        return c.host_operation(c.b['completed'], c.request)
    if state.get('state') not in ('not_started', 'unknown') or (state['state'] == 'unknown' and not state['idempotent']):
        raise PolicyBlock('nonidempotent_effect_must_not_be_repeated')
    attempt = _read(c.b['attempt'], c.request)
    if type(attempt) is not int or not 0 <= attempt < c.policy['max_retries']:
        raise PolicyBlock('retry_limit')
    action = c.select()
    def reserve():
        if _read(c.b['effect_state'], c.request) != state or _read(c.b['attempt'], c.request) != attempt:
            raise PolicyBlock('recovery_state_changed')
        if _read(c.b['reserve_retry'], c.request, action) is not True:
            raise PolicyBlock('host_retry_reservation_denied')
        reserved = _read(c.b['attempt'], c.request)
        if type(reserved) is not int or reserved != attempt + 1 or reserved > c.policy['max_retries']:
            raise PolicyBlock('invalid_retry_reservation')
        if _read(c.b['effect_state'], c.request) != state:
            raise PolicyBlock('effect_changed_during_retry_reservation')
    # Reservations and all model charges are retained after a failed call.
    return c.execute(action, reserve)


def _action_j(c):
    action = c.select()
    coordinator, maximum = c.router.budget_coordinator, c.policy['max_concurrent']
    with _ownership_lock:
        existing = _delegation_slots.get(coordinator)
        if existing is None:
            existing = (maximum, threading.BoundedSemaphore(maximum))
            _delegation_slots[coordinator] = existing
        if existing[0] != maximum: raise PolicyBlock('shared_delegation_limit_mismatch')
        slots = existing[1]
    if not slots.acquire(blocking=False): raise PolicyBlock('delegation_concurrency_limit')
    try:
        def owner():
            if _read(c.b['ownership'], c.request, action) is not True: raise PolicyBlock('delegation_ownership_denied')
        result = c.execute(action, owner)
        valid = (isinstance(result, dict) and result.get('task_id') == c.task_id and result.get('owner') == action)
        try:
            valid = valid and _read(c.b['verify_child'], c.request, action, result) is True
        except PolicyBlock:
            valid = False  # The child already completed; retain its real outcome for inspection.
        return c.host_operation(c.b['finish'], c.request, result, 'accept' if valid else 'inspect')
    finally:
        slots.release()


def _action_k(c):
    action = c.select()
    if _read(c.b['checks'], c.request) is not True:
        action = c.policy['failed_checks_action']
    # Return a finite disposition, not a publication/approval/merge callback.
    return _transition_value(c, action, ('accept', 'inspect', 'comment', 'request_changes'))


def _action_l(c):
    before = copy.deepcopy(_read(c.b['revision'], c.request))
    if set(c.spec['label_actions']) != {'same', 'related', 'different', 'uncertain'}:
        raise PolicyBlock('graph_semantics_must_be_explicit')
    if set(c.policy['mutating_actions']) & set(c.policy['nonmutating_actions']):
        raise PolicyBlock('ambiguous_graph_mutation_policy')
    if c.baseline not in c.policy['nonmutating_actions']:
        raise PolicyBlock('graph_baseline_must_not_merge_uncertain_entities')
    action = c.select()
    if action not in c.policy['mutating_actions'] + c.policy['nonmutating_actions']:
        raise PolicyBlock('undeclared_graph_consequence')
    def revision():
        if _read(c.b['revision'], c.request) != before: raise PolicyBlock('graph_revision_changed')
        if action in c.policy['mutating_actions']:
            gate = _gate(_read(c.b['gate'], c.request, action))
            if gate.approval_granted is not True: raise PolicyBlock('graph_mutation_requires_host_approval')
    return c.execute(action, revision)


def _action_m(c):
    evidence = c.evidence()
    action = c.select(evidence)
    grounded = (isinstance(evidence, dict) and isinstance(evidence.get('claims'), list)
                and isinstance(evidence.get('evidence'), list) and bool(evidence['claims']) and bool(evidence['evidence']))
    if not grounded or _read(c.b['verify_claims'], c.request) is not True:
        action = c.policy['failed_claims_action']
    # Any answer revision remains a distinct, explicitly invoked host operation.
    return _transition_value(c, action, ('accept', 'inspect', 'revise'))


HANDLERS = dict(zip('ABCDEFGHIJKLM', (_action_a, _action_b, _action_c, _action_d, _action_e, _action_f, _action_g,
                                     _action_h, _action_i, _action_j, _action_k, _action_l, _action_m)))


def invoke_bound(spec, original, request, bindings):
    """Called only from generated host edits. Never accepts executable source text."""
    c = None
    try:
        router = _read(bindings['runtime'], request)
        if isinstance(router, SafeRouter) and router.config['mode'] == 'off':
            pass  # Run the original below, outside the router-signal handlers.
        elif isinstance(router, SafeRouter) and router.config['mode'] == 'shadow':
            # Evaluate only observational evidence. No treatment handler or host
            # execution gate can change the original return/exception/state here.
            try:
                _register_owner(spec, router)
                c = Context(spec, original, request, bindings, router)
                if spec['recipe']['id'] != 'python.E': c.select()
            except (PolicyBlock, UseFallback, InputError): pass
        else:
            _register_owner(spec, router)
            c = Context(spec, original, request, bindings, router)
            return HANDLERS[spec['recipe']['id'].split('.')[-1]](c)
    except UseFallback as exc:
        if c is not None:
            if c.host_operation_started:
                raise
            try:
                return c.fallback(str(exc))
            except PolicyBlock as blocked:
                if c.host_operation_started:
                    raise
                return bindings['blocked'](request, str(blocked))
        return bindings['blocked'](request, 'runtime_fallback_without_context')
    except PolicyBlock as exc:
        if c is not None and c.host_operation_started:
            raise
        return bindings['blocked'](request, str(exc))
    # A host is allowed to raise the same exception classes used internally by
    # the router. Off/shadow must propagate those exceptions without fallback.
    return original(request)
