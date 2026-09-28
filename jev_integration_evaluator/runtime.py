"""Bounded assessment sidecar. This module NEVER executes an action or grants authority."""
from __future__ import annotations
import copy
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, asdict
from typing import Any
from .client import EvaluationClient, validate_response
from .io import InputError, digest, finite
from .questions import validate_questions
from .budget import BudgetCoordinator, BudgetDenied


@dataclass(frozen=True)
class HostGate:
    allowed_actions: tuple[str,...]
    hard_block: bool=False
    approval_required: bool=False
    approval_granted: bool=False
    baseline_permitted: bool=True


@dataclass(frozen=True)
class Decision:
    action: str
    source: str
    reason: str
    assessment: dict | None=None


@dataclass(frozen=True)
class Thresholds:
    probability_floor: float=0.90
    confidence_floor: float=0.75
    inspect_probability_floor: float=0.65
    evidence_yes_floor: float=0.90

    def validate(self):
        for name in ("probability_floor","confidence_floor","inspect_probability_floor","evidence_yes_floor"):
            finite(getattr(self,name),name,0,1)
        if self.inspect_probability_floor>self.probability_floor:
            raise InputError("Inspection floor cannot exceed the action floor")


class SafeRouter:
    """Off by default; shadow calls use a bounded worker queue and cannot affect returned actions.

    A trusted host must revalidate state, permissions and action-specific approval at
    execution time. Threshold selection/activation are external recorded approvals.
    Cache entries contain assessments, never permissions or approval decisions.
    """
    def __init__(self, client: EvaluationClient, config: dict, *, policy_version: str="v1", thresholds: Thresholds | None=None,
                 activation: dict | None=None, audit_log=None, shadow_workers: int=1,
                 action_thresholds: dict[str, Thresholds] | None=None, require_expiring_activation: bool=False,
                 budget_coordinator: BudgetCoordinator | None=None, max_concurrent_calls: int=8,
                 require_runtime_binding: bool=False, canary_scope: str | None=None):
        self.client=client; self.config=copy.deepcopy(config); self.policy_version=policy_version
        from .config import load_config, validate_config
        validation_config=load_config();validation_config["runtime"]=self.config
        try: validate_config(validation_config)
        except (KeyError,TypeError) as exc: raise InputError("Incomplete/invalid runtime configuration") from exc
        self.thresholds=thresholds or Thresholds(); self.thresholds.validate()
        self.action_thresholds=copy.deepcopy(action_thresholds or {})
        if type(require_expiring_activation) is not bool:
            raise InputError("require_expiring_activation must be boolean")
        self.require_expiring_activation=require_expiring_activation
        if type(require_runtime_binding) is not bool:
            raise InputError("require_runtime_binding must be boolean")
        self.require_runtime_binding=require_runtime_binding
        if canary_scope is not None and (not isinstance(canary_scope,str) or not canary_scope):
            raise InputError("canary_scope must be a nonempty string or null")
        self.canary_scope=canary_scope or policy_version
        if budget_coordinator is not None and not isinstance(budget_coordinator,BudgetCoordinator):
            raise InputError("Expected a shared BudgetCoordinator")
        if type(max_concurrent_calls) is not int or not 1 <= max_concurrent_calls <= 1024:
            raise InputError("max_concurrent_calls must be 1..1024")
        self.budget_coordinator=budget_coordinator
        self.max_concurrent_calls=max_concurrent_calls
        self.request_slots=threading.BoundedSemaphore(max_concurrent_calls)
        for action, limits in self.action_thresholds.items():
            if not isinstance(action,str) or not action or not isinstance(limits,Thresholds):
                raise InputError("Per-action thresholds require registered action names and Thresholds")
            limits.validate()
            if any(getattr(limits,k)<getattr(self.thresholds,k) for k in asdict(self.thresholds)):
                raise InputError("Per-action thresholds cannot weaken any global threshold")
        if type(shadow_workers) is not int or not 1 <= shadow_workers <= 64:
            raise InputError("shadow_workers must be 1..64")
        self.activation=copy.deepcopy(activation or {}); self.log=audit_log
        self.suspended=False
        self.lock=threading.RLock(); self.cache={}; self.tasks={}; self.failures=0; self.open_until=0.0
        self.pool=ThreadPoolExecutor(max_workers=shadow_workers,thread_name_prefix="jev-shadow")
        self.slots=threading.BoundedSemaphore(max(1,shadow_workers*2)); self.futures=set(); self.closed=False
        self.stats={"calls":0,"errors":0,"cache_hits":0,"shadow_dropped":0,"timeouts":0}

    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def close(self):
        self.closed=True
        # The remote transport is bounded by its own timeout; this is not hard real-time scheduling.
        self.pool.shutdown(wait=True,cancel_futures=True)

    def suspend(self):
        """Latch off future and in-flight proposals. Recreate the router to reactivate.

        This cannot cancel an already sent remote request or revoke a previously
        returned action. Host policy must still recheck at actual execution time.
        """
        with self.lock:
            self.suspended=True
            self.cache.clear()
            if callable(getattr(self.budget_coordinator, 'claim_effect', None)):
                self.budget_coordinator.suspend()

    def revoke_activation(self):
        with self.lock:
            self.activation["revoked"]=True
            self.suspended=True
            self.cache.clear()
            if callable(getattr(self.budget_coordinator, 'claim_effect', None)):
                self.budget_coordinator.suspend()

    def release_task(self, task_id: str):
        """Host calls only when the whole task ends; premature release resets its budget."""
        with self.lock: self.tasks.pop(task_id,None)

    def _event(self,event):
        event.setdefault("evidence_type",getattr(self.client,"evidence_type","observed"))
        if self.log is not None:
            self.log.append(event)

    def _fallback(self,baseline,gate,reason,assessment=None):
        if gate.hard_block: return Decision("block","policy","deterministic_hard_block",assessment)
        if gate.approval_required and not gate.approval_granted: return Decision("request_approval","policy","host_approval_required",assessment)
        if not gate.baseline_permitted or baseline not in gate.allowed_actions:
            return Decision("block","policy","no_permitted_baseline",assessment)
        return Decision(baseline,"baseline",reason,assessment)

    def runtime_contract_hash(self, questions, primary_question, evidence_question=None, *, label_actions=None):
        """Bind the exact operational policy and question roles for host approval.

        Changing canary exposure, prices, deadlines, thresholds or the chosen
        primary/evidence question invalidates a v1.2 receipt. No authority is
        created by computing this hash.
        """
        from .robustness import request_fingerprint
        contract={"runtime":self.config, "policy_version":self.policy_version,
                       "ordered_questions_hash":request_fingerprint(None,questions,self.config["model"]),
                       "primary_question":primary_question, "evidence_question":evidence_question,
                       "thresholds":asdict(self.thresholds),
                       "action_thresholds":{k:asdict(v) for k,v in self.action_thresholds.items()},
                       "max_concurrent_calls":self.max_concurrent_calls, "canary_scope":self.canary_scope,
                       "shared_budget_limits":self.budget_coordinator.limits if self.budget_coordinator else None}
        # Omitting a translation preserves byte-for-byte legacy receipt semantics.
        if label_actions is not None:
            contract["label_actions"]=self._label_translation(questions,primary_question,label_actions)
        return digest(contract)

    @staticmethod
    def _label_translation(questions, primary, label_actions):
        if label_actions is None:
            return None
        if (not isinstance(label_actions,dict) or primary not in questions
                or questions[primary].get("type")!="choice"
                or set(label_actions)!=set(questions[primary]["criteria"])
                or any(v is not None and (not isinstance(v,str) or not v) for v in label_actions.values())):
            raise InputError("Translation must exhaustively map Choice labels to host IDs or explicit abstention")
        if "uncertain" in label_actions and label_actions["uncertain"] is not None:
            raise InputError("Uncertainty cannot be translated into execution authority")
        return copy.deepcopy(label_actions)

    def _active_authorized(self, questions, primary=None, evidence_q=None, label_actions=None):
        from .contracts import parse_utc
        from .robustness import request_fingerprint
        from datetime import datetime, timezone
        a=self.activation
        if self.require_runtime_binding or "runtime_contract_hash" in a:
            if (not self.require_expiring_activation or a.get("runtime_contract_hash") !=
                    self.runtime_contract_hash(questions,primary,evidence_q,label_actions=label_actions)):
                return False
        if a.get("revoked",False) is not False:
            return False
        has_expiry=any(k in a for k in ("issued_at","expires_at"))
        if self.require_expiring_activation or has_expiry:
            try:
                issued=parse_utc(a.get("issued_at")); expires=parse_utc(a.get("expires_at"))
            except (InputError,TypeError,ValueError):
                return False
            if not issued <= datetime.now(timezone.utc) < expires:
                return False
        if self.require_expiring_activation:
            if (a.get("evidence_type")!="observed" or not isinstance(a.get("activation_id"),str)
                    or not a["activation_id"] or a.get("ordered_questions_hash")!=request_fingerprint(None,questions,self.config["model"])):
                return False
        if self.action_thresholds and a.get("action_thresholds_hash")!=digest({k:asdict(v) for k,v in self.action_thresholds.items()}):
            return False
        return (a.get("approved") is True and a.get("calibration_validated") is True
                and a.get("model")==self.config["model"] and a.get("policy_version")==self.policy_version
                and a.get("questions_hash")==digest(questions) and a.get("thresholds_hash")==digest(asdict(self.thresholds))
                and bool(a.get("holdout_evidence_ref")))

    def route(self, *, task_id: str, state: Any, questions: dict, primary_question: str, baseline_action: str,
              gate: HostGate, evidence_question: str | None=None, immutable_state: bool=False,
              cache_scope: str | None=None, estimated_cost_upper_bound: float | None=None,
              provenance: dict | None=None, label_actions: dict[str,str | None] | None=None) -> Decision:
        # Freeze caller-owned inputs before validating, hashing or scheduling.
        questions=copy.deepcopy(questions)
        state=copy.deepcopy(state)
        validate_questions(questions)
        label_actions=self._label_translation(questions,primary_question,label_actions)
        if type(immutable_state) is not bool:
            raise InputError("immutable_state must be an explicit boolean")
        if cache_scope is not None and (not isinstance(cache_scope,str) or not cache_scope):
            raise InputError("cache_scope must be a nonempty string or null")
        if not isinstance(gate,HostGate) or any(type(getattr(gate,k)) is not bool for k in ("hard_block","approval_required","approval_granted","baseline_permitted")):
            raise InputError("Host authorization flags must be explicit booleans")
        if not isinstance(gate.allowed_actions,tuple) or not all(isinstance(a,str) and a for a in gate.allowed_actions) or len(set(gate.allowed_actions))!=len(gate.allowed_actions):
            raise InputError("Host legal actions must be a tuple of unique nonempty strings")
        provenance=copy.deepcopy(provenance or {})
        if set(provenance)-{"candidate_id","experiment_id","source_location"}: raise InputError("Unsupported runtime provenance key")
        if provenance:
            source=provenance.get("source_location",{})
            if not all(isinstance(source.get(k),str) and source[k] for k in ("file","symbol","source_sha256")):
                raise InputError("Runtime provenance must include exact file, symbol and source hash")
        if self.closed: return self._fallback(baseline_action,gate,"router_closed")
        if self.suspended: return self._fallback(baseline_action,gate,"runtime_suspended")
        if primary_question not in questions or questions[primary_question]["type"]!="choice": raise InputError("Routing requires a primary Choice")
        if evidence_question is not None and (evidence_question not in questions or questions[evidence_question]["type"]!="noul"):
            raise InputError("Evidence question must be a Noul")
        if set(self.action_thresholds)-set(questions[primary_question]["criteria"]):
            raise InputError("Action-specific thresholds refer to unregistered choices")
        if not isinstance(task_id,str) or not task_id: raise InputError("Stable task_id is required for budgeting and canary assignment")
        if self.budget_coordinator and not self.budget_coordinator.permits_result(task_id):
            return self._fallback(baseline_action,gate,"shared_budget_closed_or_suspended")
        if gate.hard_block or (gate.approval_required and not gate.approval_granted):
            return self._fallback(baseline_action,gate,"host_gate")
        mode=self.config["mode"]
        if mode=="off": return self._fallback(baseline_action,gate,"feature_off")
        if mode not in ("shadow","canary","active"): raise InputError("Unsupported mode")
        if mode in ("active","canary") and not self._active_authorized(questions,primary_question,evidence_question,label_actions):
            return self._fallback(baseline_action,gate,"activation_or_calibration_missing")
        if mode=="canary":
            from .cohorts import canary_arm
            if canary_arm(task_id,self.canary_scope,self.config["canary_fraction"])=="baseline":
                return self._fallback(baseline_action,gate,"canary_baseline_cohort")
        if estimated_cost_upper_bound is not None: finite(estimated_cost_upper_bound,"estimated cost upper bound",0)
        if self.client.is_remote and estimated_cost_upper_bound is None:
            return self._fallback(baseline_action,gate,"unknown_spend_upper_bound")
        args=(task_id,copy.deepcopy(state),copy.deepcopy(questions),primary_question,baseline_action,gate,evidence_question,immutable_state,cache_scope,estimated_cost_upper_bound or 0.0,provenance,label_actions)
        if mode=="shadow":
            if not self.slots.acquire(blocking=False):
                with self.lock: self.stats["shadow_dropped"]+=1
                return self._fallback(baseline_action,gate,"shadow_queue_full")
            def work():
                try:
                    decision=self._assess(*args)
                    self._event({**provenance,"type":"shadow_comparison","task_id_hash":digest(task_id),"baseline":baseline_action,
                                 "proposed":decision.action,"reason":decision.reason,"agreement":decision.action==baseline_action,
                                 "counterfactual_outcome":"unknown; not a rescue/regression"})
                    return decision
                finally: self.slots.release()
            try:
                fut=self.pool.submit(work)
            except RuntimeError:
                self.slots.release(); return self._fallback(baseline_action,gate,"shadow_executor_closed")
            with self.lock: self.futures.add(fut)
            fut.add_done_callback(self._finished)
            return self._fallback(baseline_action,gate,"shadow_baseline_controls")
        return self._assess(*args)

    def _finished(self,future):
        with self.lock: self.futures.discard(future)
        try: future.result()
        except Exception:
            with self.lock: self.stats["errors"]+=1

    def _assess(self,task_id,state,questions,primary,baseline,gate,evidence_q,immutable,scope,cost_bound,provenance,label_actions=None):
        from .robustness import request_fingerprint
        cache_contract={"ordered_request":request_fingerprint(state,questions,self.config["model"]),
                        "policy_version":self.policy_version,"allowed_actions":gate.allowed_actions,"scope":scope}
        if label_actions is not None: cache_contract["label_actions"]=label_actions
        key=digest(cache_contract)
        now=time.monotonic(); cached=None; saved_latency=0.0
        reservation=None; request_slot=False; actual_cost=None
        cacheable=immutable and bool(scope) and self.config["cache_ttl_s"]>0
        with self.lock:
            if self.suspended or self.closed:
                return self._fallback(baseline,gate,"runtime_suspended_or_closed_during_assessment")
            if self.config["mode"] in ("active","canary") and not self._active_authorized(questions,primary,evidence_q,label_actions):
                return self._fallback(baseline,gate,"activation_expired_or_revoked_during_assessment")
            if self.budget_coordinator and not self.budget_coordinator.permits_result(task_id):
                return self._fallback(baseline,gate,"shared_budget_closed_or_suspended")
            if cacheable:
                entry=self.cache.get(key)
                if entry and entry[0]>now: cached=copy.deepcopy(entry[1]); saved_latency=entry[2]; self.stats["cache_hits"]+=1
                elif entry: self.cache.pop(key,None)
            if cached is None:
                if now<self.open_until: return self._fallback(baseline,gate,"circuit_open")
                if task_id not in self.tasks and len(self.tasks)>=2048:
                    return self._fallback(baseline,gate,"task_budget_registry_full")
                budget=self.tasks.setdefault(task_id,{"calls":0,"reserved_cost":0.0})
                if budget["calls"]>=self.config["max_calls_per_task"]:
                    return self._fallback(baseline,gate,"call_budget_exhausted")
                if budget["reserved_cost"]+cost_bound>self.config["max_cost_per_task"]+1e-12:
                    return self._fallback(baseline,gate,"cost_budget_exhausted")
                if not self.request_slots.acquire(blocking=False):
                    return self._fallback(baseline,gate,"router_concurrency_limit")
                request_slot=True
                if self.budget_coordinator:
                    try:
                        reservation=self.budget_coordinator.reserve(task_id,cost_bound)
                    except BudgetDenied as exc:
                        self.request_slots.release()
                        return self._fallback(baseline,gate,exc.reason)
                    except Exception:
                        self.request_slots.release()
                        raise
                # Reserve the full upper bound; do not refund failures or pretend timed-out requests were free.
                budget["calls"]+=1; budget["reserved_cost"]+=cost_bound; self.stats["calls"]+=1
        started=time.monotonic()
        try:
            egress_check = getattr(self, 'host_egress_check', None)
            if egress_check is not None:
                egress_check()
            response=cached or self.client.evaluate(copy.deepcopy(state),copy.deepcopy(questions),self.config["model"],self.config["timeout_ms"])
            if egress_check is not None:
                egress_check()
            validate_response(response,questions,self.config["model"])
            # Capture known usage even when the response arrived too late to use.
            in_price=self.config.get("input_usd_per_million"); out_price=self.config.get("output_usd_per_million")
            actual_cost=((response["usage"]["input_tokens"]*in_price+response["usage"]["output_tokens"]*out_price)/1e6
                         if cached is None and in_price is not None and out_price is not None else None)
            elapsed=(time.monotonic()-started)*1000
            if elapsed>self.config["timeout_ms"]:
                with self.lock: self.stats["timeouts"]+=1
                raise InputError("late_response")
            in_price=self.config.get("input_usd_per_million"); out_price=self.config.get("output_usd_per_million")
            cost=(response["usage"]["input_tokens"]*in_price+response["usage"]["output_tokens"]*out_price)/1e6 if in_price is not None and out_price is not None else None
            with self.lock:
                if cached is None and cost is not None and cost>cost_bound:
                    if task_id not in self.tasks:
                        raise InputError("task_released_during_inference")
                    self.tasks[task_id]["reserved_cost"]+=cost-cost_bound
                    if self.tasks[task_id]["reserved_cost"]>self.config["max_cost_per_task"]:
                        raise InputError("actual_cost_budget_exceeded")
                self.failures=0
            if reservation is not None:
                self.budget_coordinator.settle(reservation,actual_cost=actual_cost)
                reservation=None
            a=response["answers"][primary]; choice=a["choice"]; p=a["probabilities"][choice]; conf=a["confidence"]
            selected=label_actions[choice] if label_actions is not None else choice
            thresholds=self.action_thresholds.get(choice,self.thresholds)
            if evidence_q is not None and response["answers"][evidence_q]["noul"]<thresholds.evidence_yes_floor:
                decision=self._fallback(baseline,gate,"insufficient_semantic_evidence",a)
            elif choice=="uncertain" or selected is None: decision=self._fallback(baseline,gate,"explicit_abstention",a)
            elif selected not in gate.allowed_actions: decision=self._fallback(baseline,gate,"illegal_model_action",a)
            elif p<thresholds.probability_floor or conf<thresholds.confidence_floor:
                if p>=thresholds.inspect_probability_floor and "inspect" in gate.allowed_actions:
                    decision=Decision("inspect","policy","gather_more_evidence",a)
                else: decision=self._fallback(baseline,gate,"low_confidence_or_probability",a)
            else: decision=Decision(selected,"jev_assessment","bounded_proposal_not_execution_authorization",a)
            in_price=self.config.get("input_usd_per_million"); out_price=self.config.get("output_usd_per_million")
            cost=(response["usage"]["input_tokens"]*in_price+response["usage"]["output_tokens"]*out_price)/1e6 if in_price is not None and out_price is not None else None
            with self.lock:
                if self.suspended or self.closed:
                    decision=self._fallback(baseline,gate,"runtime_suspended_or_closed_during_assessment")
                elif self.config["mode"] in ("active","canary") and not self._active_authorized(questions,primary,evidence_q,label_actions):
                    decision=self._fallback(baseline,gate,"activation_expired_or_revoked_during_assessment")
            if self.budget_coordinator and not self.budget_coordinator.permits_result(task_id):
                decision=self._fallback(baseline,gate,"shared_budget_closed_or_suspended")
            self._event({**provenance,"type":"assessment","task_id_hash":digest(task_id),"request_hash":key,"model":response["model"],
                         "policy_version":self.policy_version,"questions_hash":digest(questions),"mode":self.config["mode"],
                         "decision":decision.action,"reason":decision.reason,"selected_probability":p,"provider_confidence":conf,
                         "latency_ms":elapsed,"cache_hit":cached is not None,"usage":response["usage"],
                         "cost":0.0 if cached else cost,"cost_status":"cached_no_new_inference" if cached else "calculated_from_configured_price" if cost is not None else "unknown",
                         "estimated_latency_saved_ms":max(0.0,saved_latency-elapsed) if cached else 0.0,
                         "estimated_cost_saved":cost if cached and cost is not None else 0.0})
            if self.budget_coordinator and not self.budget_coordinator.permits_result(task_id):
                return self._fallback(baseline,gate,"shared_budget_closed_or_suspended")
            with self.lock:
                if self.suspended or self.closed:
                    return self._fallback(baseline,gate,"runtime_suspended_or_closed_during_assessment")
                if self.config["mode"] in ("active","canary") and not self._active_authorized(questions,primary,evidence_q,label_actions):
                    return self._fallback(baseline,gate,"activation_expired_or_revoked_during_assessment")
                if cacheable and cached is None:
                    if len(self.cache)>=self.config["max_cache_entries"]: self.cache.pop(next(iter(self.cache)))
                    self.cache[key]=(time.monotonic()+self.config["cache_ttl_s"],copy.deepcopy(response),elapsed)
            return decision
        except Exception as exc:
            with self.lock:
                self.failures+=1; self.stats["errors"]+=1
                if self.failures>=self.config["circuit_failures"]: self.open_until=time.monotonic()+self.config["circuit_cooldown_s"]
            # Deliberately suppress provider text, payloads and exception messages in logs.
            try: self._event({**provenance,"type":"assessment_error","task_id_hash":digest(task_id),"request_hash":key,"error_class":type(exc).__name__,"mode":self.config["mode"]})
            except Exception: pass
            return self._fallback(baseline,gate,"evaluation_or_audit_failure")
        finally:
            # Failed, late and unaudited requests retain their reservation charge.
            # Shared capacity is released even when validation or logging failed.
            try:
                if reservation is not None:
                    self.budget_coordinator.settle(reservation,actual_cost=actual_cost)
            finally:
                if request_slot:
                    self.request_slots.release()


def rollback_check(window: dict, limits: dict) -> dict:
    """Deterministic canary stop rules. Caller supplies matched, observed window metrics."""
    for k in ("unsafe_actions", "failure_rate", "p95_added_latency_ms", "mean_added_cost", "fallback_rate"):
        finite(window[k],k,0)
        finite(limits[k],"limit "+k,0)
    reasons=[k for k in limits if k in window and window[k]>limits[k]]
    return {"rollback":bool(reasons),"reasons":reasons,"recommended_mode":"off" if reasons else "unchanged",
            "note":"The host owns feature-flag changes. Do not auto-expand canary exposure from this check."}
