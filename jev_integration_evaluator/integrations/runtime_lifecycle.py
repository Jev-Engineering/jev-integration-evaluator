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
from ..contracts import parse_utc
from .runtime_ledger import RuntimeLedger
from datetime import datetime, timezone


class LifecycleError(InputError):
    """A fixed diagnostic code; no target data or credential is included."""


SUPPORTED_CONNECTED_MODELS = frozenset({'jev-1.13.0'})


class _NoEgressClient:
    """Default-off placeholder. Any attempted evaluation fails before I/O."""
    is_remote = False
    evidence_type = 'none'

    def evaluate(self, *_args, **_kwargs):
        raise LifecycleError('provider_unavailable_without_egress')


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
    Off-mode startup without ``client`` uses a no-egress placeholder. Shadow
    requires a host-supplied synthetic client. Remote creation requires a
    separately supplied exact egress grant at startup.
    """

    def __init__(self, adapters: dict[str, Any], *, budget_limits: dict[str, Any],
                 audit_log: Any, dependency_plan: dict[str, Any],
                 client: Any = None, egress_grant: dict[str, Any] | None = None,
                 process_model: str = 'single_process', startup_mode: str = 'off',
                 connected_config: dict[str, Any] | None = None,
                 authority: dict[str, Any] | None = None,
                 verify_authority: Any = None,
                 current_environment_digest: Any = None,
                 ledger_path: str | Path | None = None):
        if process_model != 'single_process':
            raise LifecycleError('distributed_coordinator_unsupported')
        if startup_mode not in ('off', 'shadow', 'canary', 'active'):
            raise LifecycleError('activation_requires_separate_reviewed_runtime')
        connected = connected_config is not None
        installed_binding = (connected_config.get('installed_binding')
                             if type(connected_config) is dict else None)
        if connected and startup_mode == 'off':
            raise LifecycleError('connected_off_mode_not_supported')
        if connected and (type(connected_config) is not dict or
                set(connected_config) != ({'endpoint', 'credential_ref', 'model',
                                          'environment_digest', 'source_root',
                                          'source_plan', 'source_bindings'} |
                                         ({'installed_binding'} if installed_binding is not None else set())) or
                connected_config['credential_ref'] != 'env:TYPESAFE_API_KEY' or
                type(connected_config['model']) is not str or
                connected_config['model'] not in SUPPORTED_CONNECTED_MODELS or
                type(connected_config['environment_digest']) is not str or
                len(connected_config['environment_digest']) != 64 or
                not callable(verify_authority) or not callable(current_environment_digest)
                or ledger_path is None):
            raise LifecycleError('connected_configuration_or_authority_required')
        if not connected and startup_mode in ('canary', 'active'):
            raise LifecycleError('activation_requires_separate_reviewed_runtime')
        if (type(adapters) is not dict or not adapters or len(adapters) > 32
                or audit_log is None or not callable(getattr(audit_log, 'append', None))):
            raise LifecycleError('invalid_runtime_startup')
        if any(type(name) is not str or not name for name in adapters):
            raise LifecycleError('invalid_runtime_startup')
        check_dependency_plan(dependency_plan)
        if connected:
            check_dependency_plan(connected_config['source_plan'])
            if installed_binding is not None:
                from ..contracts import validate_contract
                try:
                    validate_contract(installed_binding, 'connected-installed-binding-v1')
                    if (digest({key: value for key, value in installed_binding.items()
                                if key != 'binding_sha256'}) != installed_binding['binding_sha256']
                            or connected_config['source_plan'] != installed_binding['source_plan']
                            or connected_config['source_root'] != installed_binding['site']
                            or verify_authority('installed_binding', installed_binding['binding_sha256']) is not True):
                        raise LifecycleError('connected_installed_binding_unverified')
                except (InputError, KeyError, TypeError, ValueError):
                    raise LifecycleError('connected_installed_binding_unverified') from None
            root = Path(connected_config['source_root'])
            if (not root.is_absolute() or not root.is_dir() or
                    any(part.is_symlink() for part in (root, *root.parents))):
                raise LifecycleError('connected_source_root_invalid')
            root = root.resolve()
            covered = {Path(row['path']).resolve(): row['sha256']
                       for row in connected_config['source_plan']['files']}
            bindings = connected_config['source_bindings']
            if type(bindings) is not dict or set(bindings) != set(adapters):
                raise LifecycleError('connected_source_binding_missing')
            for name, adapter in adapters.items():
                spec = adapter.SPEC
                source_relative = spec.get('source', {}).get('file')
                if not source_relative:
                    raise LifecycleError('connected_source_binding_missing')
                bound = bindings[name]
                if (type(bound) is not dict or set(bound) !=
                        {'reviewed_file_sha256', 'applied_file_sha256',
                         'adapter_path', 'adapter_sha256'} or
                        type(bound['adapter_path']) is not str or not bound['adapter_path']):
                    raise LifecycleError('connected_source_binding_missing')
                adapter_relative = bound['adapter_path']
                origin = getattr(adapter, '__file__', None)
                if installed_binding is not None:
                    origins = installed_binding['origins']
                    if (installed_binding['candidate_id'] != name
                            or installed_binding['source_file'] != source_relative
                            or installed_binding['reviewed_file_sha256'] != spec['source'].get('file_sha256')
                            or installed_binding['applied_file_sha256'] != bound['applied_file_sha256']
                            or adapter_relative != origins['adapter']['wheel_member']
                            or origin is None or Path(origin).resolve() != Path(origins['adapter']['path'])
                            or bound['adapter_sha256'] != origins['adapter']['sha256']
                            or bound['reviewed_file_sha256'] != installed_binding['reviewed_file_sha256']
                            or covered.get(Path(origins['host']['path'])) != origins['host']['sha256']
                            or covered.get(Path(origins['adapter']['path'])) != origins['adapter']['sha256']
                            or covered.get(Path(origins['console']['path'])) != origins['console']['sha256']
                            or covered.get(Path(installed_binding['reviewed_project_path'])) !=
                               installed_binding['reviewed_project_sha256']):
                        raise LifecycleError('connected_source_binding_mismatch')
                    if ('loader' in origins and covered.get(Path(origins['loader']['path'])) !=
                            origins['loader']['sha256']):
                        raise LifecycleError('connected_source_binding_mismatch')
                    if any(not Path(row['path']).resolve().is_relative_to(root)
                           for role, row in origins.items()):
                        raise LifecycleError('connected_source_binding_mismatch')
                else:
                    if origin is None or Path(origin).resolve() != (root / adapter_relative).resolve():
                        raise LifecycleError('connected_source_binding_mismatch')
                    if (spec.get('output', {}).get('module') is not None and
                            adapter_relative != spec['output']['module']):
                        raise LifecycleError('connected_source_binding_mismatch')
                    for relative in (source_relative, adapter_relative):
                        candidate = root / relative
                        if (Path(relative).is_absolute() or '..' in Path(relative).parts
                                or candidate.resolve() not in covered
                                or not candidate.resolve().is_relative_to(root)):
                            raise LifecycleError('connected_source_binding_missing')
                    if (bound['reviewed_file_sha256'] != spec['source'].get('file_sha256')
                            or bound['applied_file_sha256'] != covered[(root / source_relative).resolve()]
                            or bound['adapter_sha256'] != covered[(root / adapter_relative).resolve()]):
                        raise LifecycleError('connected_source_binding_mismatch')
            try:
                if current_environment_digest() != connected_config['environment_digest']:
                    raise LifecycleError('connected_environment_drift')
            except LifecycleError:
                raise
            except Exception:
                raise LifecycleError('connected_environment_identity_unavailable') from None
            if client is not None or egress_grant is not None:
                raise LifecycleError('connected_client_must_be_host_constructed')
            if (type(authority) is not dict or set(authority) != {'egress_grant', 'activation'}
                    or type(authority['egress_grant']) is not dict):
                raise LifecycleError('connected_egress_authority_required')
            grant = authority['egress_grant']
            source_identity = {'root': str(root), 'plan': connected_config['source_plan'],
                               'bindings': connected_config['source_bindings']}
            if installed_binding is not None:
                source_identity['installed_binding_sha256'] = installed_binding['binding_sha256']
            expected_grant = {'endpoint': connected_config['endpoint'],
                              'credential_ref': connected_config['credential_ref'],
                              'model': connected_config['model'],
                              'environment_digest': connected_config['environment_digest'],
                              'source_digest': digest(source_identity),
                              'dependency_digest': digest(dependency_plan),
                              'budget_digest': digest(budget_limits),
                              'adapters_digest': digest({k: digest(v.SPEC) for k, v in adapters.items()}),
                              'mode': startup_mode}
            if any(grant.get(k) != v for k, v in expected_grant.items()):
                raise LifecycleError('connected_egress_binding_mismatch')
            try:
                now = datetime.now(timezone.utc)
                if not parse_utc(grant['issued_at']) <= now < parse_utc(grant['expires_at']):
                    raise LifecycleError('connected_egress_grant_expired')
                if verify_authority('egress_grant', digest(grant)) is not True:
                    raise LifecycleError('connected_egress_grant_unverified')
            except LifecycleError:
                raise
            except Exception:
                raise LifecycleError('connected_egress_grant_invalid') from None
            try:
                client = TypeSafeHTTPClient(allow_network=True,
                    endpoint=connected_config['endpoint'],
                    approved_endpoint=connected_config['endpoint'])
            except (InputError, OSError):
                raise LifecycleError('provider_startup_unavailable') from None
        if connected:
            pass
        elif client is None and egress_grant is None and startup_mode == 'off':
            client = _NoEgressClient()
        elif client is None:
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
        if (startup_mode == 'shadow' and not connected and
                (getattr(client, 'is_remote', False)
                 or getattr(client, 'evidence_type', None) != 'synthetic')):
            raise LifecycleError('synthetic_shadow_requires_offline_client')
        if connected and startup_mode in ('canary', 'active') and (
                type(authority['activation']) is not dict or
                set(authority['activation']) != set(adapters) | {'evidence'} or
                any(type(authority['activation'][name]) is not dict or
                    type(authority['activation'][name].get('receipt')) is not dict
                    for name in adapters)):
            raise LifecycleError('connected_activation_evidence_required')
        try:
            if connected:
                identity = digest({'adapters': {k: digest(v.SPEC) for k, v in adapters.items()},
                                   'configuration': connected_config,
                                   'dependency_plan': dependency_plan,
                                   'budget_limits': budget_limits})
                coordinator = RuntimeLedger(ledger_path, identity=identity, **budget_limits)
            else:
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
                if connected and (selected_config['model'] != connected_config['model']
                                  or runtime['configuration']['mode'] != 'off'):
                    raise LifecycleError('connected_model_or_configuration_mismatch')
                router = adapter.create_router(client, budget_coordinator=coordinator,
                                               audit_log=audit_log, runtime_config=selected_config,
                                               **({'activation': authority['activation'][name]['receipt']}
                                                  if connected and startup_mode in ('canary', 'active') else {}))
                if (not isinstance(router, SafeRouter) or router.budget_coordinator is not coordinator
                        or router.canary_scope != scope or router.config != selected_config
                        or not router.require_expiring_activation or not router.require_runtime_binding):
                    if isinstance(router, SafeRouter):
                        router.close()
                    raise LifecycleError('invalid_adapter_router')
                routers[name] = router
                task_fields[name] = runtime['task_field']
                adapter_digests[name] = digest(spec)
            if connected and startup_mode in ('canary', 'active'):
                self._check_connected_activation(routers, adapters, authority['activation'],
                                                  verify_authority, startup_mode)
        except LifecycleError:
            for router in routers.values():
                router.close()
            if isinstance(coordinator, RuntimeLedger):
                coordinator.release()
            raise
        except BaseException:
            for router in routers.values():
                router.close()
            if isinstance(coordinator, RuntimeLedger):
                coordinator.release()
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
        self._requested_mode = startup_mode
        self._effective_mode = startup_mode
        self._connected_config_digest = digest(connected_config) if connected else None
        self._dependency_plan = copy.deepcopy(dependency_plan)
        self._source_plan = copy.deepcopy(connected_config['source_plan']) if connected else None
        self._installed_binding_digest = (installed_binding['binding_sha256']
                                          if installed_binding is not None else None)
        self._grant_digest = digest(authority['egress_grant']) if connected else None
        self._grant_expires = authority['egress_grant']['expires_at'] if connected else None
        self._deployment_expires = (authority['activation']['evidence']['deployment_grant']['expires_at']
                                    if connected and startup_mode in ('canary', 'active') else None)
        self._verify_authority = verify_authority if connected else None
        self._current_environment_digest = current_environment_digest if connected else None
        self._expected_environment_digest = (connected_config['environment_digest'] if connected else None)
        self._activation_authority = (
            {'study': authority['activation']['evidence']['expected_study_digest'],
             'deployment_grant': digest(authority['activation']['evidence']['deployment_grant']),
             **{f'activation_receipt:{name}': digest(authority['activation'][name]['receipt'])
                for name in adapters}}
            if connected and startup_mode in ('canary', 'active') else {})
        self._rejection_reason = None
        if connected:
            for router in routers.values():
                router.host_source_check = self._check_host_integrity
                router.host_egress_check = self._check_live_files

    @staticmethod
    def qualification_inputs() -> dict[str, Any]:
        """Redacted component contract for a host's independent live qualification."""
        return {'kind': 'host_runtime_connected_qualification_v1',
                'supported_modes': ['off', 'shadow', 'canary', 'active'],
                'connected_config_fields': ['endpoint', 'credential_ref', 'model',
                                            'environment_digest', 'source_root', 'source_plan',
                                            'source_bindings'],
                'authority_fields': ['egress_grant', 'activation'],
                'activation_evidence_fields': ['study', 'baseline', 'treatment',
                                               'gate_bundle', 'inventory',
                                               'expected_study_digest', 'deployment_grant'],
                'required_host_inputs': ['verify_authority', 'ledger_path',
                                         'current_environment_digest', 'budget_limits',
                                         'audit_log', 'dependency_plan'],
                'credential_reference': 'env:TYPESAFE_API_KEY',
                'provider_connectivity': 'not_tested',
                'observed_benefit': 'not_established', 'release_gate_complete': False}

    @staticmethod
    def _check_connected_activation(routers, adapters, activation, verifier, mode):
        from ..study import evaluate_study
        if (type(activation) is not dict or set(activation) != set(routers) | {'evidence'}
                or type(activation['evidence']) is not dict):
            raise LifecycleError('connected_activation_evidence_required')
        evidence = activation['evidence']
        required = {'study', 'baseline', 'treatment', 'gate_bundle', 'inventory',
                    'expected_study_digest', 'deployment_grant'}
        if set(evidence) != required:
            raise LifecycleError('connected_activation_evidence_required')
        try:
            if verifier('study', evidence['expected_study_digest']) is not True:
                raise LifecycleError('connected_study_not_authenticated')
            report = evaluate_study(evidence['study'], evidence['baseline'], evidence['treatment'],
                                    expected_digest=evidence['expected_study_digest'],
                                    gate_bundle=evidence['gate_bundle'], inventory=evidence['inventory'])
            if (report['recommendation'] != 'keep' or not report['holdout_evidence_verified']
                    or evidence['study']['specification']['evidence_type'] != 'observed'
                    or evidence['study']['specification']['jev']['mode'] != mode
                    or not evidence['study']['specification'].get('deployment_gates')):
                raise LifecycleError('connected_observed_gates_not_qualified')
            gates = evidence['study']['specification']['deployment_gates']
            if {gate['candidate_id'] for gate in gates} != set(routers) or len(gates) != len(routers):
                raise LifecycleError('connected_gate_placement_mismatch')
            by_placement = {gate['candidate_id']: gate for gate in gates}
            grant = evidence['deployment_grant']
            if (type(grant) is not dict or grant.get('study_digest') != evidence['expected_study_digest']
                    or grant.get('gate_manifest_digest') != report['gate_evidence']['gate_manifest_digest']
                    or grant.get('baseline_digest') != digest(evidence['baseline'])
                    or grant.get('treatment_digest') != digest(evidence['treatment'])
                    or grant.get('gate_bundle_digest') != digest(evidence['gate_bundle'])
                    or grant.get('inventory_digest') != digest(evidence['inventory'])
                    or grant.get('mode') != mode or
                    not parse_utc(grant['issued_at']) <= datetime.now(timezone.utc) < parse_utc(grant['expires_at'])
                    or verifier('deployment_grant', digest(grant)) is not True):
                raise LifecycleError('connected_deployment_grant_invalid')
            for name, router in routers.items():
                item = activation[name]
                receipt = item['receipt']
                spec = adapters[name].SPEC
                gate = by_placement[name]
                if (gate['questions'] != spec['questions'] or
                        gate['primary_question'] != spec['primary_question'] or
                        gate['model_id'] != router.config['model'] or
                        gate['policy_version'] != router.policy_version or
                        any(gate['source'][key] != spec['source'][key] for key in
                            ('file', 'symbol', 'file_sha256', 'source_sha256')) or
                        receipt.get('holdout_evidence_ref') != gate['holdout_report_digest']):
                    raise LifecycleError('connected_gate_runtime_binding_mismatch')
                if (item.get('runtime_contract_hash') != router.runtime_contract_hash(
                        spec['questions'], spec['primary_question'], spec['evidence_question'],
                        label_actions=spec['label_actions'])
                        or receipt.get('runtime_contract_hash') != item['runtime_contract_hash']
                        or receipt.get('study_digest') != evidence['expected_study_digest']
                        or receipt.get('deployment_id') != grant.get('deployment_id')
                        or verifier('activation_receipt', digest(receipt)) is not True
                        or not router._active_authorized(spec['questions'], spec['primary_question'],
                                                         spec['evidence_question'], spec['label_actions'])):
                    raise LifecycleError('connected_runtime_receipt_invalid')
        except LifecycleError:
            raise
        except Exception:
            raise LifecycleError('connected_activation_evidence_invalid') from None

    def mode_status(self) -> dict[str, Any]:
        with self._lock:
            if not self._closed and self._source_plan is not None:
                try:
                    self._check_live_files()
                except LifecycleError:
                    pass
            effective = 'off' if self._closed or self.coordinator.snapshot()['suspended'] else self._effective_mode
            reason = ('runtime_closed' if self._closed else self._rejection_reason)
            if effective in ('canary', 'active') and any(
                    not router._active_authorized(self._adapters[name].SPEC['questions'],
                    self._adapters[name].SPEC['primary_question'],
                    self._adapters[name].SPEC['evidence_question'],
                    self._adapters[name].SPEC['label_actions'])
                    for name, router in self._routers.items()):
                effective, reason = 'off', 'activation_expired_or_invalid'
            return {'requested_mode': self._requested_mode, 'effective_mode': effective,
                    'rejection_reason': reason,
                    'connected': self._connected_config_digest is not None,
                    'configuration_digest': self._connected_config_digest,
                    'placements': sorted(self._routers), 'owner_pid': self._pid,
                    'budget': self.coordinator.snapshot(), 'secrets_exposed': False}

    def suspend(self) -> None:
        with self._lock:
            for router in self._routers.values():
                router.suspend()
            self.coordinator.suspend()
            self._effective_mode = 'off'
            self._rejection_reason = 'host_suspended'

    def revoke_activation(self) -> None:
        with self._lock:
            for router in self._routers.values():
                router.revoke_activation()
            self.coordinator.suspend()
            self._effective_mode = 'off'
            self._rejection_reason = 'host_revoked'

    def router(self, placement: str, request: dict[str, Any]) -> SafeRouter:
        with self._lock:
            if self._closed or os.getpid() != self._pid:
                raise LifecycleError('runtime_closed_or_forked')
            if placement not in self._routers:
                raise LifecycleError('unregistered_placement')
            self._check_live_files()
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

    def _check_host_integrity(self) -> None:
        if os.getpid() != self._pid:
            raise LifecycleError('runtime_closed_or_forked')
        try:
            check_dependency_plan(self._dependency_plan)
            if self._source_plan is not None:
                check_dependency_plan(self._source_plan)
                if any(digest(self._adapters[name].SPEC) != wanted
                       for name, wanted in self._adapter_digests.items()):
                    raise LifecycleError('connected_adapter_contract_changed')
                if self._current_environment_digest() != self._expected_environment_digest:
                    raise LifecycleError('connected_environment_drift')
                if (self._installed_binding_digest is not None and
                        self._verify_authority('installed_binding', self._installed_binding_digest) is not True):
                    raise LifecycleError('connected_installed_binding_revoked')
        except Exception:
            self.coordinator.suspend()
            self._effective_mode = 'off'
            self._rejection_reason = 'runtime_source_or_configuration_drift'
            raise LifecycleError('runtime_source_or_configuration_drift') from None

    def _check_live_files(self) -> None:
        self._check_host_integrity()
        try:
            if self._source_plan is not None:
                credential_check = getattr(self._client, 'credential_still_current', None)
                if callable(credential_check) and credential_check() is not True:
                    raise LifecycleError('connected_credential_rotated')
                if (datetime.now(timezone.utc) >= parse_utc(self._grant_expires)
                        or self._verify_authority('egress_grant', self._grant_digest) is not True):
                    raise LifecycleError('connected_egress_grant_expired_or_revoked')
                for kind, expected in self._activation_authority.items():
                    authority_kind = 'activation_receipt' if kind.startswith('activation_receipt:') else kind
                    if self._verify_authority(authority_kind, expected) is not True:
                        raise LifecycleError('connected_activation_authority_revoked')
                if self._deployment_expires is not None and datetime.now(timezone.utc) >= parse_utc(self._deployment_expires):
                    raise LifecycleError('connected_deployment_grant_expired')
                for name, router in self._routers.items():
                    expected = self._activation_authority.get(f'activation_receipt:{name}')
                    if expected is not None and digest(router.activation) != expected:
                        raise LifecycleError('connected_activation_receipt_changed')
        except LifecycleError:
            self.coordinator.suspend()
            self._effective_mode = 'off'
            self._rejection_reason = 'runtime_source_configuration_or_egress_drift'
            raise LifecycleError('runtime_source_or_configuration_drift') from None
        except Exception:
            self.coordinator.suspend()
            self._effective_mode = 'off'
            self._rejection_reason = 'runtime_source_configuration_or_egress_drift'
            raise LifecycleError('runtime_source_or_configuration_drift') from None

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
            if isinstance(self.coordinator, RuntimeLedger):
                self.coordinator.suspend(durable=False)
            else:
                self.coordinator.suspend()
            for router in self._routers.values():
                router.close()
            if isinstance(self.coordinator, RuntimeLedger):
                self.coordinator.release()

    def __enter__(self) -> 'HostRuntimeLifecycle':
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
