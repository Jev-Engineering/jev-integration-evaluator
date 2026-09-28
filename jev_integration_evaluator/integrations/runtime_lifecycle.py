"""Host-owned, process-local startup and shutdown for reviewed Python adapters.

This module never installs dependencies, provisions credentials, or activates a
router. The host owns adapter imports and calls ``start`` once per workflow.
"""
from __future__ import annotations

import hashlib
import copy
import os
from pathlib import Path
import stat
import threading
from typing import Any

from ..budget import BudgetCoordinator, BudgetDenied
from ..client import TypeSafeHTTPClient, validate_response
from ..io import InputError, digest
from ..runtime import SafeRouter


class LifecycleError(InputError):
    """A fixed diagnostic code; no target data or credential is included."""


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def check_dependency_plan(plan: dict[str, Any]) -> None:
    """Check an already prepared exact plan; never resolve or install packages."""
    if (type(plan) is not dict or set(plan) != {'files'} or type(plan['files']) is not list
            or not 1 <= len(plan['files']) <= 64):
        raise LifecycleError('invalid_dependency_plan')
    seen = set()
    for row in plan['files']:
        if (type(row) is not dict or set(row) != {'path', 'sha256'}
                or type(row['path']) is not str or not Path(row['path']).is_absolute()
                or type(row['sha256']) is not str or len(row['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['sha256'])
                or row['path'] in seen):
            raise LifecycleError('invalid_dependency_plan')
        seen.add(row['path'])
        path = Path(row['path'])
        try:
            if (any(component.is_symlink() for component in (path, *path.parents))
                    or not path.is_file() or not stat.S_ISREG(path.stat().st_mode)
                    or path.stat().st_size > 1_000_000 or _sha(path) != row['sha256']):
                raise LifecycleError('dependency_plan_drift')
        except OSError:
            raise LifecycleError('dependency_plan_unavailable') from None


class HostRuntimeLifecycle:
    """One workflow, one coordinator, one router per placement, one task ledger.

    ``adapters`` are reviewed generated modules exposing SPEC/create_router.
    ``client`` is a host-supplied offline client by default. Remote creation
    requires a separately supplied exact egress grant at startup.
    """

    def __init__(self, adapters: dict[str, Any], *, budget_limits: dict[str, Any],
                 audit_log: Any, dependency_plan: dict[str, Any],
                 client: Any = None, egress_grant: dict[str, Any] | None = None,
                 process_model: str = 'single_process', startup_mode: str = 'off'):
        if process_model != 'single_process':
            raise LifecycleError('distributed_coordinator_unsupported')
        if startup_mode not in ('off', 'shadow'):
            raise LifecycleError('activation_requires_separate_reviewed_runtime')
        if (type(adapters) is not dict or not adapters or len(adapters) > 32
                or audit_log is None or not callable(getattr(audit_log, 'append', None))):
            raise LifecycleError('invalid_runtime_startup')
        if any(type(name) is not str or not name for name in adapters):
            raise LifecycleError('invalid_runtime_startup')
        check_dependency_plan(dependency_plan)
        if client is None:
            if (type(egress_grant) is not dict or
                    set(egress_grant) != {'endpoint', 'credential_ref', 'cost_upper_bound'}
                    or egress_grant['credential_ref'] != 'env:TYPESAFE_API_KEY'
                    or type(egress_grant['cost_upper_bound']) not in (int, float)
                    or not 0 < egress_grant['cost_upper_bound'] <= 1):
                raise LifecycleError('explicit_egress_authority_required')
            try:
                client = TypeSafeHTTPClient(allow_network=True,
                    endpoint=egress_grant['endpoint'], approved_endpoint=egress_grant['endpoint'])
            except (InputError, OSError):
                raise LifecycleError('provider_startup_unavailable') from None
        elif getattr(client, 'is_remote', False):
            raise LifecycleError('remote_client_requires_exact_egress_grant')
        elif egress_grant is not None:
            raise LifecycleError('egress_grant_without_remote_client')
        if not callable(getattr(client, 'evaluate', None)) or type(getattr(client, 'is_remote', None)) is not bool:
            raise LifecycleError('invalid_evaluation_client')
        if (startup_mode == 'shadow' and
                (getattr(client, 'is_remote', False)
                 or getattr(client, 'evidence_type', None) != 'synthetic')):
            raise LifecycleError('synthetic_shadow_requires_offline_client')
        try:
            coordinator = BudgetCoordinator(**budget_limits)
        except (TypeError, ValueError, InputError):
            raise LifecycleError('invalid_shared_budget') from None
        routers: dict[str, SafeRouter] = {}
        task_fields: dict[str, str] = {}
        adapter_digests: dict[str, str] = {}
        scope = None
        try:
            for name, adapter in adapters.items():
                spec = adapter.SPEC
                runtime = spec['runtime']
                if (spec['candidate_id'] != name or runtime['configuration']['mode'] != 'off'
                        or type(runtime['task_field']) is not str or not runtime['task_field']
                        or (scope is not None and runtime['canary_scope'] != scope)):
                    raise LifecycleError('runtime_configuration_binding_mismatch')
                scope = runtime['canary_scope']
                selected_config = copy.deepcopy(runtime['configuration'])
                selected_config['mode'] = startup_mode
                router = adapter.create_router(client, budget_coordinator=coordinator,
                                               audit_log=audit_log, runtime_config=selected_config)
                if (not isinstance(router, SafeRouter) or router.budget_coordinator is not coordinator
                        or router.canary_scope != scope or router.config != selected_config
                        or not router.require_expiring_activation or not router.require_runtime_binding):
                    if isinstance(router, SafeRouter):
                        router.close()
                    raise LifecycleError('invalid_adapter_router')
                routers[name] = router
                task_fields[name] = runtime['task_field']
                adapter_digests[name] = digest(spec)
        except LifecycleError:
            for router in routers.values():
                router.close()
            raise
        except BaseException:
            for router in routers.values():
                router.close()
            raise LifecycleError('adapter_startup_failed') from None
        self._pid = os.getpid()
        self._lock = threading.RLock()
        self._closed = False
        self._adapters = dict(adapters)
        self._routers = routers
        self._task_fields = task_fields
        self._adapter_digests = adapter_digests
        self._client = client
        self._audit_log = audit_log
        self._egress_grant = dict(egress_grant) if egress_grant is not None else None
        self._probe_used = False
        self.coordinator = coordinator

    def router(self, placement: str, request: dict[str, Any]) -> SafeRouter:
        with self._lock:
            if self._closed or os.getpid() != self._pid:
                raise LifecycleError('runtime_closed_or_forked')
            if placement not in self._routers:
                raise LifecycleError('unregistered_placement')
            try:
                if digest(self._adapters[placement].SPEC) != self._adapter_digests[placement]:
                    raise LifecycleError('adapter_contract_changed')
            except (TypeError, ValueError, AttributeError):
                raise LifecycleError('adapter_contract_changed') from None
            field = self._task_fields[placement]
            if type(request) is not dict or type(request.get(field)) is not str or not request[field]:
                raise LifecycleError('stable_task_identity_required')
            if not self.coordinator.permits_result(request[field]):
                raise LifecycleError('task_closed_or_budget_suspended')
            return self._routers[placement]

    def runtime_binding(self, placement: str):
        """Return the host callback installed once at application startup."""
        if placement not in self._routers:
            raise LifecycleError('unregistered_placement')
        return lambda request: self.router(placement, request)

    def complete_task(self, task_id: str) -> None:
        with self._lock:
            if self._closed or os.getpid() != self._pid:
                raise LifecycleError('runtime_closed_or_forked')
            self.coordinator.close_task(task_id)
            for router in self._routers.values():
                router.release_task(task_id)

    def connectivity_probe_plan(self) -> dict[str, Any]:
        """Describe one fixed synthetic request; this performs no network I/O."""
        with self._lock:
            if self._closed or os.getpid() != self._pid or self._egress_grant is None:
                raise LifecycleError('provider_probe_unavailable')
            models = {router.config['model'] for router in self._routers.values()}
            timeouts = {router.config['timeout_ms'] for router in self._routers.values()}
            if len(models) != 1 or len(timeouts) != 1:
                raise LifecycleError('provider_probe_configuration_mismatch')
            return {'kind': 'synthetic-provider-connectivity-v1',
                    'endpoint': self._egress_grant['endpoint'],
                    'model': next(iter(models)), 'timeout_ms': next(iter(timeouts)),
                    'cost_upper_bound': self._egress_grant['cost_upper_bound'],
                    'state': {'jev_probe': 'synthetic_connectivity_only'},
                    'questions': {'probe': {'type': 'choice',
                        'instructions': 'Classify this synthetic connectivity marker only.',
                        'criteria': {'marker': 'The synthetic marker is present.',
                                     'other': 'The synthetic marker is absent.'}}}}

    def probe_provider_connectivity(self, *, approved_request_sha256: str,
                                    egress_grant: dict[str, Any]) -> dict[str, Any]:
        """One explicitly approved synthetic egress attempt; never activates routers."""
        with self._lock:
            plan = self.connectivity_probe_plan()
            if (self._probe_used or type(approved_request_sha256) is not str
                    or approved_request_sha256 != digest(plan)
                    or egress_grant != self._egress_grant):
                raise LifecycleError('exact_provider_probe_authority_required')
            try:
                self._audit_log.append({'type': 'synthetic_provider_probe_intent',
                                        'request_sha256': approved_request_sha256,
                                        'activation_authorized': False})
            except Exception:
                raise LifecycleError('provider_probe_audit_unavailable') from None
            self._probe_used = True
        try:
            reservation = self.coordinator.reserve('__jev_synthetic_connectivity_probe__',
                                                   plan['cost_upper_bound'])
        except BudgetDenied:
            raise LifecycleError('provider_probe_budget_denied') from None
        try:
            response = self._client.evaluate(plan['state'], plan['questions'],
                                             plan['model'], plan['timeout_ms'])
            validate_response(response, plan['questions'], plan['model'])
            status = 'synthetic_provider_reachable'
        except Exception:
            status = 'provider_probe_failed'
        finally:
            self.coordinator.settle(reservation)
            self.coordinator.close_task('__jev_synthetic_connectivity_probe__')
        try:
            self._audit_log.append({'type': 'synthetic_provider_probe_result',
                                    'request_sha256': digest(plan), 'status': status,
                                    'activation_authorized': False})
        except Exception:
            raise LifecycleError('provider_probe_audit_unavailable') from None
        return {'status': status, 'request_sha256': digest(plan),
                'synthetic': True, 'activation_authorized': False,
                'provider_benefit_demonstrated': False}

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self.coordinator.suspend()
            for router in self._routers.values():
                router.close()

    def __enter__(self) -> 'HostRuntimeLifecycle':
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
