"""Causal source/cache/task guard tests; these are not installed qualification."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import py_compile
import sys
from threading import Lock
from types import SimpleNamespace

import pytest

from jev_integration_evaluator import template_packages_runtime as runtime
from jev_integration_evaluator.io import digest, file_hash


def test_owner_audit_preserves_bounded_error_classes_without_provider_text(tmp_path, monkeypatch):
    import json
    tmp_path.chmod(0o700)
    target = tmp_path / 'audit.json'
    monkeypatch.setenv('PACKAGES_OWNER_AUDIT_PATH', str(target))
    audit = runtime._Audit()
    audit.append({'type': 'assessment_error', 'error_class': 'EvaluationTimeoutError',
                  'message': 'private provider text'})
    audit.append({'type': 'assessment_error', 'error_class': '/private/path/provider text'})
    owner = SimpleNamespace(coordinator=SimpleNamespace(snapshot=lambda: {}),
        _routers={'one': SimpleNamespace(stats={'timeouts': 1})})
    audit.write(owner)
    value = json.loads(target.read_text())
    assert value['error_classes'] == ['EvaluationTimeoutError']
    assert value['assessment_timeouts'] == 1
    assert 'private provider text' not in target.read_text()
    assert '/private/path' not in target.read_text()


def binding_for(site, top, host):
    return {'members': {'one': {'site': str(site), 'origins': {
                'host': {'path': str(host), 'wheel_member': top + '/host.py'}}}},
            'source_plan': {'files': [{'path': str(path), 'sha256': file_hash(path)}
                                     for path in [host.parent / '__init__.py', host]]}}


def test_member_initializer_drift_refused_before_side_effect(tmp_path):
    package = tmp_path / 'bounded_member_init'
    package.mkdir()
    initializer = package / '__init__.py'
    initializer.write_text('VALUE = 1\n')
    host = package / 'host.py'
    host.write_text('VALUE = 2\n')
    binding = binding_for(tmp_path, package.name, host)
    marker = tmp_path / 'must-not-run'
    initializer.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    with pytest.raises(RuntimeError, match='^packages_owner_member_source_changed$'):
        runtime._SelectedSourceFinder(binding)
    assert not marker.exists()


def test_member_source_loader_ignores_stale_unrecorded_bytecode(tmp_path):
    package = tmp_path / 'bounded_member_cache'
    package.mkdir()
    (package / '__init__.py').write_text('')
    host = package / 'host.py'
    marker = tmp_path / 'must-not-run'
    original = "VALUE = 'captured'\n".ljust(512, '#')
    malicious = f"from pathlib import Path\nPath({str(marker)!r}).touch()\nVALUE = 'stale'\n".ljust(512, '#')
    host.write_text(malicious)
    stamp = host.stat().st_mtime
    py_compile.compile(str(host), doraise=True)
    host.write_text(original)
    os.utime(host, (stamp, stamp))
    finder = runtime._SelectedSourceFinder(binding_for(tmp_path, package.name, host))
    sys.meta_path.insert(0, finder)
    try:
        loaded = importlib.import_module(package.name + '.host')
        assert loaded.VALUE == 'captured'
        assert not marker.exists()
    finally:
        sys.meta_path.remove(finder)
        for name in (package.name, package.name + '.host'):
            sys.modules.pop(name, None)


def test_member_unbound_sibling_never_falls_through_to_import_path(tmp_path):
    package = tmp_path / 'bounded_member_extra'
    package.mkdir()
    (package / '__init__.py').write_text('')
    host = package / 'host.py'
    host.write_text('from . import surprise\n')
    marker = tmp_path / 'must-not-run'
    (package / 'surprise.py').write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    finder = runtime._SelectedSourceFinder(binding_for(tmp_path, package.name, host))
    sys.meta_path.insert(0, finder)
    try:
        with pytest.raises(ImportError, match='^packages_owner_unbound_member_import$'):
            importlib.import_module(package.name + '.host')
        assert not marker.exists()
    finally:
        sys.meta_path.remove(finder)
        for name in (package.name, package.name + '.host', package.name + '.surprise'):
            sys.modules.pop(name, None)


def test_common_owner_rejects_both_task_fields_changed_together(tmp_path, monkeypatch):
    request = {'task_id': 'original', 'job_id': 'original'}
    routes, called = [], []
    class FakeRuntime:
        coordinator = SimpleNamespace(snapshot=lambda: {}, claim_effect=lambda *_args: 'unit-claim', complete_effect=lambda *_args: None)
        def __init__(self, *args, **kwargs):
            pass
        def router(self, name, payload):
            routes.append((name, payload['task_id']))
            return SimpleNamespace(lock=Lock(), futures=[])
        def runtime_binding(self, name):
            return lambda payload: self.router(name, payload)
        def complete_task(self, task):
            pass
        def close(self):
            pass
    adapters = {name: SimpleNamespace(SPEC={'bindings': {'runtime': 'route'}, 'runtime_files': [], 'runtime': {'task_field': 'task_id'}},
                                     ENABLED=False) for name in ('one', 'two')}
    hosts = {'one': SimpleNamespace(host_runtime=lambda payload: None),
             'two': SimpleNamespace(runtime_for_job=lambda payload: None)}
    def first(payload):
        called.append('one')
        payload['task_id'] = payload['job_id'] = 'changed-together'
        return 0
    def second(payload):
        called.append('two')
        return 0
    limits = {'max_calls_per_task': 2, 'max_cost_per_task': 2, 'max_total_calls': 3,
              'max_total_cost': 3, 'max_in_flight': 1, 'max_tasks': 2}
    startup = {'authority': {'egress_grant': {'budget_digest': digest(limits),
                                             'dependency_digest': digest({'files': []})}}}
    binding = {'members': {name: {'candidate_id': name, 'source_file': ('src/registered_alpha/host.py' if name == 'one' else 'src/work_queue/engine.py'),
                                 'origins': {'host': {'path': str(tmp_path / (name + '.py'))}}}
                           for name in adapters}}
    monkeypatch.setattr(runtime, '_selected', lambda *_args: (startup, binding, adapters, hosts,
                                                {'one': first, 'two': second}, SimpleNamespace(packages=set()), {'one': request, 'two': request}))
    monkeypatch.setattr(runtime, 'HostRuntimeLifecycle', FakeRuntime)
    monkeypatch.setattr(runtime, '_dependency_plan', lambda *_args: {'files': []})
    monkeypatch.setattr(runtime._Audit, 'write', lambda *_args: None)
    with pytest.raises(RuntimeError, match='^packages_owner_task_identity_changed$'):
        runtime._run(request, 'unit-owner-only.py', connected=True)
    assert called == ['one']
    assert routes == [('one', 'original'), ('two', 'original')]


def test_failed_signed_member_import_releases_finder_and_partial_modules(tmp_path, monkeypatch):
    package = tmp_path / 'bounded_member_failure'
    package.mkdir()
    (package / '__init__.py').write_text('PARTIAL = True\n')
    host = package / 'host.py'
    host.write_text("raise RuntimeError('authored_import_refusal')\n")
    binding = binding_for(tmp_path, package.name, host)
    binding['members']['one']['source_file'] = 'authored-source'
    monkeypatch.setattr(runtime, 'SOURCES', {'authored-source': (package.name + '.host', 'entry', 'task_id')})
    finder = runtime._SelectedSourceFinder(binding)
    before = tuple(sys.meta_path)
    with pytest.raises(RuntimeError, match='^authored_import_refusal$'):
        runtime._load_members(binding, finder)
    assert tuple(sys.meta_path) == before
    assert not any(name.split('.')[0] == package.name for name in sys.modules)


def test_owner_size_scope_preserves_legacy_limit_and_preflights_total(tmp_path, monkeypatch):
    from jev_integration_evaluator.integrations import runtime_lifecycle as lifecycle
    large = tmp_path / 'trusted-native-fixture.so'
    large.write_bytes(b'x' * 1_000_001)
    plan = {'files': [{'path': str(large), 'sha256': file_hash(large)}]}
    with pytest.raises(lifecycle.LifecycleError, match='^dependency_plan_drift$'):
        lifecycle.check_dependency_plan(plan)
    lifecycle.check_dependency_plan(plan, maximum=4096, maximum_bytes=4_000_000)
    rows = []
    for index in range(17):
        path = tmp_path / ('bounded-' + str(index))
        with path.open('wb') as target:
            target.truncate(4_000_000)
        rows.append({'path': str(path), 'sha256': '0' * 64})
    reads = []
    monkeypatch.setattr(lifecycle, '_sha', lambda *args: reads.append(args) or '0' * 64)
    with pytest.raises(lifecycle.LifecycleError, match='^dependency_plan_drift$'):
        lifecycle.check_dependency_plan({'files': rows}, maximum=4096, maximum_bytes=4_000_000)
    assert reads == []


def test_owner_audit_failure_preserves_original_refusal(monkeypatch):
    monkeypatch.setattr(runtime, '_selected', lambda *_args: (_ for _ in ()).throw(
        RuntimeError('packages_owner_original_refusal')))
    monkeypatch.setattr(runtime._Audit, '_write', lambda *_args: (_ for _ in ()).throw(
        OSError('/private-sentinel/credential.json')))
    with pytest.raises(RuntimeError, match='^packages_owner_original_refusal$'):
        runtime._run({'task_id': 'fixture'}, 'unit-only-owner', connected=True)


def test_finite_member_loader_checks_real_module_origins(tmp_path, monkeypatch):
    binding = {'members': {}, 'source_plan': {'files': []}}
    sources = {}
    for index, field in enumerate(('task_id', 'job_id')):
        top = 'bounded_origin_' + str(index)
        package = tmp_path / top
        package.mkdir()
        initializer = package / '__init__.py'
        initializer.write_text('')
        host = package / 'host.py'
        host.write_text('def entry(request):\n    return 0\n')
        adapter = package / 'adapter.py'
        adapter.write_text(f"SPEC = {{'candidate_id': {top!r}, 'runtime': {{'task_field': {field!r}}}}}\n")
        binding['members'][top] = {'site': str(tmp_path), 'source_file': top,
            'origins': {role: {'path': str(path), 'wheel_member': top + '/' + path.name,
                              'sha256': file_hash(path)}
                        for role, path in (('host', host), ('adapter', adapter))}}
        binding['source_plan']['files'].extend({'path': str(path), 'sha256': file_hash(path)}
            for path in (initializer, host, adapter))
        sources[top] = (top + '.host', 'entry', field)
    monkeypatch.setattr(runtime, 'SOURCES', sources)
    finder = runtime._SelectedSourceFinder(binding)
    try:
        adapters, hosts, entries = runtime._load_members(binding, finder)
        assert set(adapters) == set(hosts) == set(entries) == set(binding['members'])
        assert all(entry({}) == 0 for entry in entries.values())
    finally:
        runtime._release_finder(finder)


def test_owner_dependency_plan_rechecks_actual_recorded_files(tmp_path):
    members, files = {}, []
    for name in ('alpha', 'queue'):
        package = tmp_path / name
        package.mkdir()
        members[name] = {'origins': {'host': {'path': str(package / 'host.py')}}}
        for filename in ('requirements.lock', 'runtime.json'):
            path = package / filename
            path.write_text('fixture:' + name + ':' + filename)
            files.append({'path': str(path), 'sha256': file_hash(path)})
    binding = {'members': members, 'source_plan': {'files': files}}
    assert runtime._dependency_plan(binding) == {'files': sorted(files, key=lambda row: row['path'])}
