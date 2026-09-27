"""Process-local, thread-safe budgets shared by every placement in one workflow.

Reservations are nonrefundable because failures and timeouts can still be billed.
This is not a distributed quota service or a provider-enforced spending cap.
"""
from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass
from .io import InputError, digest, finite


class BudgetDenied(InputError):
    """A deterministic admission refusal; ``reason`` contains no user data."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Reservation:
    token: str


class BudgetCoordinator:
    """A lifetime ledger; all participating routers must share the SAME instance.

    Closing a task does not reset its counters. Closed tasks remain tombstoned up
    to ``max_tasks``; a full ledger rejects new tasks rather than forgetting spend.
    A new coordinator is a new budget scope and requires deliberate host approval.
    """
    def __init__(self, *, max_calls_per_task: int, max_cost_per_task: float,
                 max_total_calls: int, max_total_cost: float, max_in_flight: int = 8,
                 max_tasks: int = 2048):
        for name, value in (("max_calls_per_task", max_calls_per_task),
                            ("max_total_calls", max_total_calls),
                            ("max_in_flight", max_in_flight), ("max_tasks", max_tasks)):
            if type(value) is not int or value < 1:
                raise InputError(name + " must be a positive integer")
        finite(max_cost_per_task, "max_cost_per_task", 0)
        finite(max_total_cost, "max_total_cost", 0)
        self._limits = dict(max_calls_per_task=max_calls_per_task, max_cost_per_task=max_cost_per_task,
                            max_total_calls=max_total_calls, max_total_cost=max_total_cost,
                            max_in_flight=max_in_flight, max_tasks=max_tasks)
        self._lock = threading.RLock()
        self._tasks: dict[str, dict] = {}
        self._inflight: dict[str, tuple[str, float]] = {}
        self._calls = 0
        self._cost = 0.0
        self._suspended = False
        self._overruns = 0
        self._denials: dict[str, int] = {}

    @property
    def limits(self) -> dict:
        return copy.deepcopy(self._limits)

    def _deny(self, reason: str):
        self._denials[reason] = self._denials.get(reason, 0) + 1
        raise BudgetDenied(reason)

    @staticmethod
    def _task_key(task_id: str) -> str:
        if not isinstance(task_id, str) or not task_id:
            raise InputError("A stable nonempty task ID is required")
        return digest(task_id)

    def reserve(self, task_id: str, cost_upper_bound: float) -> Reservation:
        """Atomically charge one call and its upper bound before starting a request."""
        cost = finite(cost_upper_bound, "cost upper bound", 0)
        key = self._task_key(task_id)
        with self._lock:
            if self._suspended:
                self._deny("shared_budget_suspended")
            task = self._tasks.get(key)
            if task is not None and task["closed"]:
                self._deny("shared_task_closed")
            if task is None and len(self._tasks) >= self._limits["max_tasks"]:
                self._deny("shared_task_registry_full")
            if len(self._inflight) >= self._limits["max_in_flight"]:
                self._deny("shared_concurrency_limit")
            if self._calls >= self._limits["max_total_calls"]:
                self._deny("shared_total_call_budget")
            if self._cost + cost > self._limits["max_total_cost"]:
                self._deny("shared_total_cost_budget")
            previous = task or {"calls": 0, "reserved_cost": 0.0, "closed": False}
            if previous["calls"] >= self._limits["max_calls_per_task"]:
                self._deny("shared_task_call_budget")
            if previous["reserved_cost"] + cost > self._limits["max_cost_per_task"]:
                self._deny("shared_task_cost_budget")
            task = self._tasks.setdefault(key, previous)
            task["calls"] += 1
            task["reserved_cost"] += cost
            self._calls += 1
            self._cost += cost
            token = uuid.uuid4().hex
            self._inflight[token] = (key, cost)
            return Reservation(token)

    def settle(self, reservation: Reservation, *, actual_cost: float | None = None) -> None:
        """Release capacity exactly once, retaining spend even on errors/timeouts.

        An actual cost above the declared bound is charged and suspends the shared
        ledger. The past provider charge cannot be undone by local accounting.
        """
        if actual_cost is not None:
            finite(actual_cost, "actual cost", 0)
        if not isinstance(reservation, Reservation):
            raise InputError("Expected a budget reservation")
        with self._lock:
            if reservation.token not in self._inflight:
                raise InputError("Unknown or already settled budget reservation")
            key, bound = self._inflight.pop(reservation.token)
            if actual_cost is not None and actual_cost > bound:
                excess = actual_cost - bound
                self._tasks[key]["reserved_cost"] += excess
                self._cost += excess
                self._overruns += 1
                self._suspended = True

    def close_task(self, task_id: str) -> None:
        """Tombstone the task; in-flight proposals must not be used after closure."""
        key = self._task_key(task_id)
        with self._lock:
            if key not in self._tasks:
                if len(self._tasks) >= self._limits["max_tasks"]:
                    self._deny("shared_task_registry_full")
                self._tasks[key] = {"calls": 0, "reserved_cost": 0.0, "closed": True}
            else:
                self._tasks[key]["closed"] = True

    def suspend(self) -> None:
        with self._lock:
            self._suspended = True

    def permits_result(self, task_id: str) -> bool:
        """Already reserved/cached results remain usable unless closed/suspended.

        Hitting an admission cap does not invalidate the very call that consumed
        the last allowed reservation. This method grants no execution authority.
        """
        key = self._task_key(task_id)
        with self._lock:
            return not self._suspended and not self._tasks.get(key, {}).get("closed", False)

    def snapshot(self) -> dict:
        with self._lock:
            return {"kind": "shared_budget_snapshot", "scope": "process_local_lifetime",
                    "limits": self.limits, "calls": self._calls, "reserved_cost": self._cost,
                    "in_flight": len(self._inflight), "tasks": len(self._tasks),
                    "closed_tasks": sum(t["closed"] for t in self._tasks.values()),
                    "suspended": self._suspended, "cost_bound_overruns": self._overruns,
                    "denials": dict(self._denials), "refunds": 0,
                    "cost_semantics": "reserved upper bounds plus known overruns, not an invoice"}
