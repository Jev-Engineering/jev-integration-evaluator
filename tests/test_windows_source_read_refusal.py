"""Native read refusals of selected source stay path-free in every planner entry point.

A deny-read ACE or a handle that shares nothing makes the first selected-source
read fail with an operating-system error whose text carries the private path.
Binding preparation, planning, status, verification, apply, rollback and bundle
re-plan must instead refuse with one fixed reason and leave no effect.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import traceback

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.io import InputError, read_json
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, implementation_status, plan_implementation,
    rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.template_catalog import (
    bind_template, materialize_template, prepare_template_binding,
    validate_template_request,
)
from jev_integration_evaluator.integrations.composite import (
    plan_composite, status_composite, verify_composite,
)
from test_composite_transaction import _two_hosts
from test_template_python_entrypoint import _prepared


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native local NTFS source read refusal')

# A denied read and a sharing violation are both PermissionError on Windows.
REASON = 'windows_source_read_access_denied'
KINDS = ('denied', 'locked')
SELECTED = ('console', 'pyproject', 'host', 'initializer', 'runtime')


def _icacls(path, *arguments):
    return subprocess.run(['icacls', str(path), *arguments],
                          capture_output=True, text=True, timeout=10)


@contextmanager
def _unreadable(path: Path, kind: str):
    """Make one test-owned file unreadable; always restore it afterwards."""
    if kind == 'denied':
        principal = subprocess.run(['whoami'], capture_output=True, text=True, timeout=10)
        assert principal.returncode == 0
        identity = principal.stdout.strip()
        try:
            # Deny file data reads only; WRITE_DAC stays available for cleanup.
            denied = _icacls(path, '/deny', identity + ':(RD)')
            assert denied.returncode == 0, 'Disposable deny ACE could not be set'
            with pytest.raises(PermissionError):
                path.read_bytes()
            yield
        finally:
            restored = _icacls(path, '/remove:d', identity)
            assert restored.returncode == 0, 'Disposable test ACL could not be restored'
    else:
        from ctypes import wintypes
        _, io_path = cap._windows_absolute_path(path)
        kernel = cap._windows_api()[2]
        # GENERIC_READ, share nothing, OPEN_EXISTING.
        handle = kernel.CreateFileW(io_path, 0x80000000, 0, None, 3, 0, None)
        assert handle != wintypes.HANDLE(-1).value
        try:
            with pytest.raises(PermissionError):
                path.read_bytes()
            yield
        finally:
            assert kernel.CloseHandle(handle)
    path.read_bytes()  # readable again


def _tree(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob('*')) if path.is_file()}


def _entries(root: Path) -> dict:
    """Names, file identities, sizes and write times; no file data is read."""
    result = {}
    for path in sorted(root.rglob('*')):
        info = path.stat()
        result[path.relative_to(root).as_posix()] = (
            cap._windows_file_identity(info), info.st_size, info.st_mtime_ns)
    return result


def _select(target: Path, spec: dict, selected: str) -> Path:
    package = (target / spec['source']['file']).parent
    path = {'console': package / 'console.py', 'pyproject': target / 'pyproject.toml',
            'host': target / spec['source']['file'], 'initializer': package / '__init__.py',
            'runtime': package / 'runtime.json',
            'adapter': package / (spec['output']['module'] + '.py')}[selected]
    assert path.is_file()
    return path


def _refused(operation, base: Path, path: Path) -> None:
    with pytest.raises(InputError) as refused:
        operation()
    error = refused.value
    assert type(error) is InputError
    assert str(error) == REASON and error.args == (REASON,)
    # No chained operating-system exception is rendered with the refusal.
    assert error.__cause__ is None and error.__suppress_context__
    rendered = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    assert 'PermissionError' not in rendered and 'WinError' not in rendered
    for private in (str(base), base.name, str(path), path.name,
                    path.parent.name):
        assert private not in str(error)
    assert str(path) not in rendered and str(base) not in rendered


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('selected', SELECTED)
def test_native_unreadable_source_refuses_binding_preparation(tmp_path, selected, kind):
    target, request, binding = _prepared(tmp_path, tag='read_bind')
    path = _select(target, request['implementation_spec'], selected)
    before, entries = _tree(target), _entries(target)
    with _unreadable(path, kind):
        _refused(lambda: prepare_template_binding(target, request, binding), tmp_path, path)
        _refused(lambda: bind_template(target, request, binding, tmp_path / 'bound'),
                 tmp_path, path)
        # No binding output and no change inside the target.
        assert [entry.name for entry in tmp_path.iterdir()] == ['target']
        assert _entries(target) == entries
    assert _tree(target) == before and _entries(target) == entries
    # The same request binds once the read is allowed again.
    prepared = prepare_template_binding(target, request, binding)
    assert prepared['binding_report']['status'] == 'planned_not_applied'


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('selected', SELECTED)
def test_native_unreadable_source_refuses_fresh_plan(tmp_path, selected, kind):
    target, request, binding = _prepared(tmp_path, tag='read_plan')
    bound = prepare_template_binding(target, request, binding)['request']
    spec, inventory = bound['implementation_spec'], bound['reviewed_inventory']
    path = _select(target, spec, selected)
    before, entries = _tree(target), _entries(target)
    with _unreadable(path, kind):
        for operation in (
                lambda: validate_template_request(target, bound),
                lambda: materialize_template(target, bound, tmp_path / 'template'),
                lambda: plan_implementation(target, inventory, spec['candidate_id'], spec,
                                            tmp_path / 'bundle')):
            _refused(operation, tmp_path, path)
        # No template output, no bundle, journal or receipt, no target change.
        assert [entry.name for entry in tmp_path.iterdir()] == ['target']
        assert _entries(target) == entries
    assert _tree(target) == before and _entries(target) == entries
    planned = plan_implementation(target, inventory, spec['candidate_id'], spec,
                                  tmp_path / 'bundle')
    assert planned['status'] == 'planned' and planned['target_modified'] is False


def _bundle(base: Path, tag: str) -> dict:
    target, request, binding = _prepared(base, tag=tag)
    bound = prepare_template_binding(target, request, binding)['request']
    spec, inventory = bound['implementation_spec'], bound['reviewed_inventory']
    bundle = base / 'private-bundle'
    planned = plan_implementation(target, inventory, spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    return {'base': base, 'target': target, 'bundle': bundle, 'spec': spec,
            'inventory': inventory, 'approval': planned['bundle_digest'],
            'baseline': baseline['receipt_sha256']}


@pytest.fixture(scope='module')
def planned_bundle(tmp_path_factory):
    """One planned, baseline-verified bundle; every refusal must leave it intact."""
    state = _bundle(tmp_path_factory.mktemp('read-refusal-planned'), 'read_planned')
    yield state
    # Refusals had no effect: the reviewed bundle still applies exactly.
    applied = apply_implementation(state['target'], state['bundle'], state['approval'],
                                   baseline_sha256=state['baseline'])
    assert applied['status'] == 'applied_unverified' and 'idempotent' not in applied


@pytest.fixture(scope='module')
def applied_bundle(tmp_path_factory):
    """One applied bundle; every refusal must leave it exactly rollbackable."""
    state = _bundle(tmp_path_factory.mktemp('read-refusal-applied'), 'read_applied')
    applied = apply_implementation(state['target'], state['bundle'], state['approval'],
                                   baseline_sha256=state['baseline'])
    assert applied['status'] == 'applied_unverified'
    state['rollback'] = applied['rollback_digest']
    yield state
    restored = rollback_implementation(state['target'], state['bundle'], state['rollback'])
    assert restored['status'] == 'rolled_back' and 'idempotent' not in restored


def _operation(state: dict, name: str, phase: str):
    target, bundle = state['target'], state['bundle']
    return {
        'status': lambda: implementation_status(target, bundle),
        'verify': lambda: verify_implementation(
            target, bundle, phase, approve_execution=True,
            baseline_sha256=state['baseline'] if phase == 'modified' else None),
        'apply': lambda: apply_implementation(target, bundle, state['approval'],
                                              baseline_sha256=state['baseline']),
        'rollback': lambda: rollback_implementation(target, bundle, state['rollback']),
        'replan': lambda: plan_implementation(
            target, state['inventory'], state['spec']['candidate_id'], state['spec'], bundle),
    }[name]


def _refused_without_effect(state: dict, name: str, phase: str, selected: str, kind: str,
                            expected: str) -> None:
    base, target, bundle = state['base'], state['target'], state['bundle']
    path = _select(target, state['spec'], selected)
    retained, bundle_entries = _tree(bundle), _entries(bundle)
    before, entries = _tree(target), _entries(target)
    with _unreadable(path, kind):
        _refused(_operation(state, name, phase), base, path)
        # No journal record, receipt, lock change or target write on refusal.
        assert _tree(bundle) == retained and _entries(bundle) == bundle_entries
        assert _entries(target) == entries
        assert sorted(entry.name for entry in base.iterdir()) == ['private-bundle', 'target']
    assert _tree(target) == before and _entries(target) == entries
    journal = (bundle / 'journal.jsonl').read_text(encoding='utf-8')
    for private in (str(base), base.name, str(path), path.name):
        assert private not in journal
    assert not (bundle / 'verification-receipt.json').exists()
    assert implementation_status(target, bundle)['status'] == expected
    assert _tree(bundle) == retained


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('selected', SELECTED)
@pytest.mark.parametrize('name', ['status', 'verify', 'apply', 'replan'])
def test_native_unreadable_source_refuses_planned_bundle_operation(
        planned_bundle, name, selected, kind):
    _refused_without_effect(planned_bundle, name, 'baseline', selected, kind, 'planned')


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('selected', ['host', 'runtime', 'adapter'])
@pytest.mark.parametrize('name', ['status', 'verify', 'apply', 'rollback'])
def test_native_unreadable_source_refuses_applied_bundle_operation(
        applied_bundle, name, selected, kind):
    _refused_without_effect(applied_bundle, name, 'modified', selected, kind,
                            'applied_unverified')


@pytest.mark.parametrize('kind', KINDS)
def test_native_unreadable_source_refuses_composite_operations(tmp_path, kind):
    """The composite planner shares the same reads and its own discovery check."""
    root, inventory, selection, specs = _two_hosts(tmp_path)
    bundle = tmp_path / 'private-bundle'
    owned = root / 'host_one.py'
    reviewed_only = root / 'combined_check.py'
    before, entries = _tree(root), _entries(root)
    with _unreadable(owned, kind):
        _refused(lambda: plan_composite(root, inventory, selection, specs, bundle),
                 tmp_path, owned)
        assert [entry.name for entry in tmp_path.iterdir()] == ['host']
        assert _entries(root) == entries
    planned = plan_composite(root, inventory, selection, specs, bundle)
    assert planned['status'] == 'planned'
    composite_plan = read_json(bundle / 'composite-plan.json')
    assert reviewed_only.name in composite_plan['discovery_files']
    assert reviewed_only.name not in {row['file'] for row in composite_plan['owned_files']}
    def artifacts(rows):
        # The operation lock file is created on first use and holds no data.
        return {name: row for name, row in rows.items() if name != 'operation.lock'}
    retained, bundle_entries = _tree(bundle), _entries(bundle)
    assert 'operation.lock' not in retained and 'journal.jsonl' in retained
    for path, operation in (
            (owned, lambda: status_composite(root, bundle)),
            (owned, lambda: verify_composite(root, bundle, 'baseline',
                                             approve_execution=True)),
            (reviewed_only, lambda: verify_composite(root, bundle, 'baseline',
                                                     approve_execution=True))):
        with _unreadable(path, kind):
            _refused(operation, tmp_path, path)
            # No journal record or receipt on refusal.
            assert artifacts(_tree(bundle)) == retained
            assert artifacts(_entries(bundle)) == bundle_entries
            assert _tree(bundle).get('operation.lock', b'0') == b'0'
            assert _entries(root) == entries
    assert _tree(root) == before
    assert status_composite(root, bundle)['status'] == 'planned'
