"""Deterministic finite owner startup rendered by the public source planner.

Only the signed selected Alpha/queue pair and the genuinely installed owner
may execute. Applications retain their own legal registries and side effects.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from .contracts import validate_contract, verify
from .io import digest, file_hash
from .integrations.runtime_lifecycle import HostRuntimeLifecycle, check_dependency_plan
from .template_packages_authority import options
from .template_packages_owner import SOURCES, RUNTIME_BINDINGS


class _CapturedSourceLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, name, path, raw):
        super().__init__(name, path)
        self._captured_source = raw

    def get_code(self, fullname):
        # Standard source compilation uses the signature-checked captured bytes;
        # installed or unrecorded bytecode is never consulted for member code.
        return self.source_to_code(self._captured_source, self.path)


class _SelectedSourceFinder(importlib.abc.MetaPathFinder):
    def __init__(self, binding):
        self.sources = {}
        self.packages = set()
        covered = {row['path']: row['sha256'] for row in binding['source_plan']['files']}
        for member in binding['members'].values():
            top = Path(member['origins']['host']['wheel_member']).parts[0]
            self.packages.add(top)
            site = Path(member['site'])
            for path, wanted in covered.items():
                source = Path(path)
                if not source.is_relative_to(site / top) or source.suffix != '.py':
                    continue
                relative = source.relative_to(site)
                package = relative.name == '__init__.py'
                parts = relative.parts[:-1] if package else (*relative.parts[:-1], relative.stem)
                name = '.'.join(parts)
                raw = source.read_bytes()
                if hashlib.sha256(raw).hexdigest() != wanted or name in self.sources:
                    raise RuntimeError('packages_owner_member_source_changed')
                self.sources[name] = (str(source), raw, package)
        if any(name in sys.modules for name in self.sources) or any(top in sys.modules for top in self.packages):
            raise RuntimeError('packages_owner_member_module_preloaded')
        if not all(top in self.sources and self.sources[top][2] for top in self.packages):
            raise RuntimeError('packages_owner_regular_member_package_required')

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] not in self.packages:
            return None
        if fullname not in self.sources:
            raise ImportError('packages_owner_unbound_member_import')
        source, raw, package = self.sources[fullname]
        loader = _CapturedSourceLoader(fullname, source, raw)
        return importlib.util.spec_from_file_location(fullname, source, loader=loader,
            submodule_search_locations=[str(Path(source).parent)] if package else None)


def _release_finder(finder):
    if finder in sys.meta_path:
        sys.meta_path.remove(finder)
    for name in tuple(sys.modules):
        if name.split('.')[0] in finder.packages:
            sys.modules.pop(name, None)


class _Audit:
    def __init__(self):
        self.rows = []

    def append(self, record):
        self.rows.append(record)

    def _write(self, runtime=None):
        value = {'types': [row.get('type') for row in self.rows],
                 'reasons': [row.get('reason') for row in self.rows],
                 'candidates': [row.get('candidate_id') for row in self.rows],
                 'assessed': [row['candidate_id'] for row in self.rows if row.get('type') == 'assessment'],
                 'error_classes': [row['error_class'] for row in self.rows
                     if row.get('type') == 'assessment_error'
                     and type(row.get('error_class')) is str
                     and len(row['error_class']) <= 64 and row['error_class'].isidentifier()],
                 'prefix': sys.prefix,
                 'evaluator_origin': str(Path(__file__).resolve().parent / '__init__.py')}
        if runtime is not None:
            value['ledger'] = runtime.coordinator.snapshot()
            value['assessment_timeouts'] = sum(router.stats['timeouts']
                for router in runtime._routers.values())
        path = Path(os.environ['PACKAGES_OWNER_AUDIT_PATH'])
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise RuntimeError('packages_owner_audit_origin_invalid')
        if path.parent.stat().st_uid != os.geteuid() or path.parent.stat().st_mode & 0o077:
            raise RuntimeError('packages_owner_audit_scope_invalid')
        with path.open('x', encoding='utf-8') as output:
            json.dump(value, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())


    def write(self, runtime=None):
        try:
            self._write(runtime)
        except (OSError, ValueError, TypeError, KeyError):
            raise RuntimeError('packages_owner_audit_unavailable') from None


def _selected(request, owner_file):
    if (type(request) is not dict or type(request.get('task_id')) is not str
            or not request['task_id'] or request.get('job_id') != request['task_id']):
        raise RuntimeError('packages_owner_same_task_identity_required')
    payloads_by_source = {'src/registered_alpha/host.py': request.get('alpha_request'),
                          'src/work_queue/engine.py': request.get('queue_request')}
    for source, payload in payloads_by_source.items():
        field = SOURCES[source][2]
        if type(payload) is not dict or payload.get(field) != request['task_id']:
            raise RuntimeError('packages_owner_same_task_identity_required')
    startup = options()
    if not startup:
        raise RuntimeError('packages_owner_signed_scope_required')
    config = startup['connected_config']
    binding = config['installed_binding']
    validate_contract(binding, 'connected-installed-packages-binding-v1')
    verify(binding, 'binding_sha256')
    owner = binding.get('owner')
    if (owner is None or str(Path(owner_file).resolve(strict=True)) != owner['origins']['console']['path']
            or str(Path(sys.prefix).resolve()) != str(Path(owner['environment']) / 'venv')
            or str(Path(__file__).resolve().parent / '__init__.py') != owner['origins']['evaluator']['path']
            or startup['verify_authority']('installed_binding', binding['binding_sha256']) is not True
            or startup['current_environment_digest']() != config['environment_digest']
            or config['source_plan'] != binding['source_plan'] or config['source_root'] != binding['site']
            or {row['source_file'] for row in binding['members'].values()} != set(SOURCES)):
        raise RuntimeError('packages_owner_installed_scope_changed')
    check_dependency_plan(binding['source_plan'], maximum=4096, maximum_bytes=4_000_000)
    # The finite finder never consults member sys.path or bytecode. It loads
    # only captured signed application source, including package initialization.
    finder = _SelectedSourceFinder(binding)
    adapters, hosts, entries = _load_members(binding, finder)
    payloads = {name: payloads_by_source[member['source_file']] for name, member in binding['members'].items()}
    return startup, binding, adapters, hosts, entries, finder, payloads

def _load_members(binding, finder):
    sys.meta_path.insert(0, finder)
    try:
        adapters, hosts, entries = {}, {}, {}
        for candidate, member in binding['members'].items():
            module_name, entry, task_field = SOURCES[member['source_file']]
            host = importlib.import_module(module_name)
            adapter_name = member['origins']['adapter']['wheel_member'][:-3].replace('/', '.')
            adapter = importlib.import_module(adapter_name)
            if (str(Path(host.__file__).resolve(strict=True)) != member['origins']['host']['path']
                    or str(Path(adapter.__file__).resolve(strict=True)) != member['origins']['adapter']['path']
                    or file_hash(Path(host.__file__)) != member['origins']['host']['sha256']
                    or file_hash(Path(adapter.__file__)) != member['origins']['adapter']['sha256']
                    or adapter.SPEC['candidate_id'] != candidate
                    or adapter.SPEC['runtime']['task_field'] != task_field):
                raise RuntimeError('packages_owner_member_origin_changed')
            adapters[candidate], hosts[candidate], entries[candidate] = adapter, host, getattr(host, entry)
        if len({adapter.SPEC['runtime']['task_field'] for adapter in adapters.values()}) != 2:
            raise RuntimeError('packages_owner_member_task_contract_changed')
        return adapters, hosts, entries
    except BaseException:
        _release_finder(finder)
        raise


def _dependency_plan(binding):
    covered = {row['path']: row['sha256'] for row in binding['source_plan']['files']}
    dependencies = {}
    for member in binding['members'].values():
        base = Path(member['origins']['host']['path']).parent
        for filename in ('requirements.lock', 'runtime.json'):
            path = str(base / filename)
            if path not in covered or file_hash(Path(path)) != covered[path]:
                raise RuntimeError('packages_owner_runtime_file_changed')
            dependencies[path] = covered[path]
    return {'files': [{'path': path, 'sha256': sha} for path, sha in sorted(dependencies.items())]}


def _run(request, owner_file, *, connected):
    audit = _Audit()
    runtime = None
    priors = {}
    finder = None
    try:
        original_task = request.get('task_id') if type(request) is dict else None
        original_request_digest = digest(request)
        startup, binding, adapters, hosts, entries, finder, payloads = _selected(request, owner_file)
        def check_task():
            if (digest(request) != original_request_digest or request.get('task_id') != original_task or request.get('job_id') != original_task
                    or any(payload.get(adapters[name].SPEC['runtime']['task_field']) != original_task
                           for name, payload in payloads.items())):
                raise RuntimeError('packages_owner_task_identity_changed')
        # Budget values are signature-owned, not selected by target environment.
        grant = startup['authority']['egress_grant']
        permitted_limits = [{'max_calls_per_task': per_task, 'max_cost_per_task': 2,
                             'max_total_calls': 3, 'max_total_cost': 3,
                             'max_in_flight': 1, 'max_tasks': 2} for per_task in (1, 2)]
        limits = next((scope for scope in permitted_limits if digest(scope) == grant['budget_digest']), None)
        if limits is None:
            raise RuntimeError('packages_owner_finite_budget_changed')
        dependency_plan = _dependency_plan(binding)
        if grant['dependency_digest'] != digest(dependency_plan):
            raise RuntimeError('packages_owner_dependency_plan_changed')
        runtime = HostRuntimeLifecycle(adapters, budget_limits=limits, audit_log=audit,
            dependency_plan=dependency_plan, **(startup if connected else {}))
        ordered = sorted(adapters, key=lambda name: binding['members'][name]['source_file'])
        refused = []
        for name in ordered:
            check_task()
            try:
                runtime.router(name, payloads[name])
            except Exception as denied:
                if str(denied) != 'task_closed_or_budget_suspended':
                    raise
                audit.append({'type': 'runtime_route_refusal', 'candidate_id': name,
                              'reason': 'task_closed_or_budget_suspended'})
                refused.append(name)
        if refused:
            raise RuntimeError('packages_owner_task_closed')
        for name in ordered:
            host, adapter = hosts[name], adapters[name]
            symbol = RUNTIME_BINDINGS[binding['members'][name]['source_file']]
            priors[name] = (symbol, getattr(host, symbol), adapter.ENABLED)
            setattr(host, symbol, runtime.runtime_binding(name))
            adapter.ENABLED = connected
        for name in ordered:
            check_task()
            claim = runtime.coordinator.claim_effect(original_task, digest(payloads[name]), name,
                'owner:' + SOURCES[binding['members'][name]['source_file']][1]) if connected else None
            if entries[name](payloads[name]) != 0:
                raise RuntimeError('packages_owner_member_task_failed')
            check_task()
            if claim is not None:
                runtime.coordinator.complete_effect(claim)
            router = runtime.router(name, payloads[name])
            with router.lock:
                futures = tuple(router.futures)
            for future in futures:
                future.result(timeout=10)
            check_task()
        ready = Path(os.environ['PACKAGES_OWNER_READY_PATH'])
        if ready.is_symlink() or any(parent.is_symlink() for parent in ready.parents):
            raise RuntimeError('packages_owner_ready_origin_invalid')
        with ready.open('xb') as output:
            output.write(b'ready\n'); output.flush(); os.fsync(output.fileno())
        if os.environ.get('PACKAGES_OWNER_HOLD') == '1':
            release = Path(os.environ['PACKAGES_OWNER_RELEASE_PATH'])
            deadline = time.monotonic() + 20
            while not release.exists():
                if time.monotonic() > deadline:
                    raise RuntimeError('packages_owner_release_missing')
                time.sleep(.01)
        return 0
    except RuntimeError as error:
        reason = str(error)
        if reason.startswith('packages_owner_') and reason.replace('_', '').isalnum():
            audit.append({'type': 'owner_refusal', 'reason': reason})
        raise
    except (OSError, ValueError, TypeError, KeyError):
        audit.append({'type': 'owner_refusal', 'reason': 'packages_owner_runtime_scope_unavailable'})
        raise RuntimeError('packages_owner_runtime_scope_unavailable') from None
    finally:
        for name, (symbol, prior, enabled) in priors.items():
            setattr(hosts[name], symbol, prior)
            adapters[name].ENABLED = enabled
        failure = sys.exc_info()[1]
        try:
            if runtime is not None:
                runtime.complete_task(original_task)
            audit.write(runtime)
        except RuntimeError:
            if failure is None:
                raise
        finally:
            if runtime is not None:
                runtime.close()
            if finder is not None:
                _release_finder(finder)


def baseline_packages_owner(request, owner_file):
    return _run(request, owner_file, connected=False)


def connected_packages_owner(request, owner_file):
    return _run(request, owner_file, connected=True)
