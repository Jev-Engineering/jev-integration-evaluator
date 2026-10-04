"""Finite owner parser refuses helper identity changes without target imports."""
from pathlib import Path

import pytest


def test_owner_installation_import_uses_declared_pre311_tomli_fallback(monkeypatch):
    """Simulate missing stdlib TOML; the hosted 3.10 job uses real tomli."""
    import builtins
    import importlib
    import sys
    try:
        import tomllib as parser
    except ModuleNotFoundError:
        import tomli as parser
    original_import = builtins.__import__
    imports = []

    def without_stdlib_toml(name, *args, **kwargs):
        if name == 'tomllib':
            raise ModuleNotFoundError("No module named 'tomllib'", name='tomllib')
        if name == 'tomli':
            imports.append(name)
            return parser
        return original_import(name, *args, **kwargs)

    module_name = 'jev_integration_evaluator.template_packages_installation'
    previous = sys.modules.pop(module_name, None)
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(builtins, '__import__', without_stdlib_toml)
            module = importlib.import_module(module_name)
        assert imports == ['tomli']
        assert module.tomllib.loads('[project]\nname="finite-owner"\n') == {
            'project': {'name': 'finite-owner'}}
    finally:
        sys.modules.pop(module_name, None)
        package = sys.modules['jev_integration_evaluator']
        if previous is not None:
            sys.modules[module_name] = previous
            package.template_packages_installation = previous
        elif hasattr(package, 'template_packages_installation'):
            del package.template_packages_installation

from jev_integration_evaluator import template_packages_owner as owner

SOURCE = '''from jev_integration_evaluator.template_packages_runtime import baseline_packages_owner, connected_packages_owner

def request():
    return {'task_id': 'owner-task', 'job_id': 'owner-task', 'alpha_request': {'task_id': 'owner-task', 'item': 'fixture-one', 'intent': 'summarize', 'permit': True, 'approved': True}, 'queue_request': {'job_id': 'owner-task', 'item': 'batch-a', 'intent': 'complete', 'allowed': True, 'complete_allowed': True}}

def main():
    payload = request()
    return baseline_packages_owner(payload, __file__)
'''


def write_source(root, suffix=''):
    path = root / owner.OWNER_FILE
    path.parent.mkdir(parents=True)
    path.write_text(SOURCE + suffix)


def test_finite_owner_retains_exact_trusted_import(tmp_path):
    write_source(tmp_path)
    raw, returned, request = owner._owner_source(tmp_path)
    assert raw == SOURCE.encode() and returned.lineno == 8 and request == 'payload'


@pytest.mark.parametrize('mutation', [
    'def connected_packages_owner(*args):\n    return 0\n',
    'class connected_packages_owner:\n    pass\n',
    'from pathlib import Path as connected_packages_owner\n',
    'import os as connected_packages_owner\n',
    'del connected_packages_owner\n',
    'def other(connected_packages_owner):\n    return 0\n',
    'def other():\n    global connected_packages_owner\n',
    'def other():\n    import os as connected_packages_owner\n',
    'def other():\n    try:\n        return 0\n    except Exception as connected_packages_owner:\n        return 0\n',
    "def other():\n    match {}:\n        case {'x': connected_packages_owner}:\n            return 0\n",
    "def other():\n    globals()['connected_packages_owner'] = 0\n",
    'def other():\n    return main.__globals__\n',
    'from os import *\n',
    'from os import mkdir as __getattr__\n',
    'import os as __path__\n',
    'from os import mkdir as __class__\n',
    'def extra():\n    return 0\n',
    'def main():\n    return 0\n',
    'from os import fork as main\n',
    'import os as request\n',
    'def other(main):\n    return 0\n',
])
def test_finite_owner_refuses_helper_shadowing(tmp_path, mutation):
    write_source(tmp_path, mutation)
    with pytest.raises(owner.PackagesOwnerError, match='^packages_owner_source_shape_unsupported$'):
        owner._owner_source(tmp_path)


def test_owner_public_planner_redacts_missing_origin(tmp_path):
    with pytest.raises(owner.PackagesOwnerError) as refused:
        owner.plan_packages_owner(str(tmp_path / 'private-missing'), [],
                                  source_root=str(tmp_path), trusted_binding_sha256='a' * 64)
    assert str(refused.value) == 'packages_owner_source_unavailable'
    assert refused.value.__cause__ is None


@pytest.mark.parametrize('mode', [0o750, 0o755])
def test_owner_scope_refuses_nonprivate_source_directory_before_members(tmp_path, monkeypatch, mode):
    root = tmp_path / 'owner'
    root.mkdir(mode=0o700)
    assert owner._owner_scope(str(root), str(tmp_path)) == root
    root.chmod(mode)
    monkeypatch.setattr(owner, '_group', lambda *_args: pytest.fail('member scope was inspected'))
    with pytest.raises(owner.PackagesOwnerError, match='^packages_owner_private_scope_required$'):
        owner.plan_packages_owner(str(root), [], source_root=str(tmp_path),
                                  trusted_binding_sha256='a' * 64)


def test_owner_source_transaction_and_rollback_are_exact(tmp_path, monkeypatch):
    from jev_integration_evaluator.template_connected_packages_binding import derive_installed_packages_binding
    from jev_integration_evaluator import template_connected_packages_binding as binder
    from tests.test_connected_packages_binding import _member, _input
    from jev_integration_evaluator import template_packages_records
    monkeypatch.setattr(template_packages_records, 'installed_records_snapshot', lambda *_values: {})
    monkeypatch.setattr(binder, '_member_import_plan', lambda *_values: [])
    members = [_member(tmp_path, name) for name in ('alpha', 'queue')]
    returned = iter(members)
    monkeypatch.setattr(binder, 'derive_installed_binding', lambda **values: next(returned))
    group = derive_installed_packages_binding([_input('alpha'), _input('queue')], source_root=str(tmp_path))
    specs = {'alpha': {'synthetic_unit_contract': 1}, 'queue': {'synthetic_unit_contract': 2}}
    monkeypatch.setattr(owner, '_group', lambda *args: (group, specs))
    root = tmp_path / 'owner'
    root.mkdir(mode=0o700)
    write_source(root)
    (root / 'pyproject.toml').write_text('# source transaction double only\n')
    plan = owner.plan_packages_owner(str(root), [_input('alpha'), _input('queue')],
                                    source_root=str(tmp_path), trusted_binding_sha256=group['binding_sha256'])
    assert plan['source_preimage'] == SOURCE
    assert 'return connected_packages_owner(payload, __file__)' in plan['patch_plan']['changes'][0]['new_content']
    transactions = tmp_path / 'transactions'
    transactions.mkdir(mode=0o700)
    receipt = owner.apply_packages_owner(plan, str(transactions / 'one'),
                                        approved_plan_sha256=plan['plan_sha256'])
    assert owner.packages_owner_source_status(plan, receipt,
        trusted_receipt_sha256=receipt['receipt_sha256'])['status'] == 'applied_externally_anchored'
    def unavailable(*_args, **_kwargs):
        raise OSError('/private-sentinel/owner-origin')
    with monkeypatch.context() as causal:
        causal.setattr(owner, '_source_current', unavailable)
        calls = (
            lambda: owner.apply_packages_owner(plan, str(transactions / 'unavailable'),
                approved_plan_sha256=plan['plan_sha256']),
            lambda: owner.packages_owner_source_status(plan, receipt,
                trusted_receipt_sha256=receipt['receipt_sha256']),
            lambda: owner.rollback_packages_owner(plan, receipt,
                trusted_receipt_sha256=receipt['receipt_sha256'], approved_plan_sha256=plan['plan_sha256']),
        )
        for call in calls:
            with pytest.raises(owner.PackagesOwnerError) as refused:
                call()
            assert str(refused.value) == 'packages_owner_source_unavailable'
            assert refused.value.__cause__ is None
    assert not (transactions / 'unavailable').exists()
    assert not (transactions / 'one/rollback-intent.json').exists()
    rolled_back = owner.rollback_packages_owner(plan, receipt,
        trusted_receipt_sha256=receipt['receipt_sha256'], approved_plan_sha256=plan['plan_sha256'])
    assert rolled_back['action'] == 'rolled_back'
    assert (root / owner.OWNER_FILE).read_bytes() == SOURCE.encode()
    with pytest.raises(owner.PackagesOwnerError, match='^packages_owner_transaction_changed$'):
        owner.packages_owner_source_status(plan, receipt, trusted_receipt_sha256=receipt['receipt_sha256'])


def test_module_import_hook_is_refused_before_source_effect(tmp_path):
    import subprocess
    import sys
    hook_marker = tmp_path / 'hook-marker'
    hook = ("\nfrom pathlib import Path\n"
            "def __getattr__(name):\n"
            f"    Path({str(hook_marker)!r}).write_text('import-hook')\n"
            "    raise AttributeError(name)\n")
    # Explicitly authored disposable import probe: main is never invoked and
    # no runtime/provider is created. This proves normal from-import triggers
    # the extra hook, rather than relying on an unused function assumption.
    authored = tmp_path / 'authored_import_probe.py'
    authored.write_text('def main():\n    return 0\n' + hook)
    result = subprocess.run([sys.executable, '-I', '-c',
        'import sys; sys.path.insert(0,sys.argv[1]); from authored_import_probe import main',
        str(tmp_path)], capture_output=True, timeout=10)
    assert result.returncode == 0 and hook_marker.read_text() == 'import-hook'
    hook_marker.unlink()
    write_source(tmp_path, hook)
    with pytest.raises(owner.PackagesOwnerError, match='^packages_owner_source_shape_unsupported$'):
        owner._owner_source(tmp_path)
    assert not hook_marker.exists()


@pytest.mark.parametrize('alias', ['owner', 'ancestor', 'common'])
def test_source_status_and_rollback_refuse_replaced_scope_before_external_write(tmp_path, monkeypatch, alias):
    """A byte-identical duplicate cannot substitute for the approved root path."""
    import shutil
    from jev_integration_evaluator.template_connected_packages_binding import derive_installed_packages_binding
    from jev_integration_evaluator import template_connected_packages_binding as binder
    from jev_integration_evaluator import template_packages_records
    from tests.test_connected_packages_binding import _member, _input

    common = tmp_path / 'common'
    common.mkdir(mode=0o700)
    monkeypatch.setattr(template_packages_records, 'installed_records_snapshot', lambda *_values: {})
    monkeypatch.setattr(binder, '_member_import_plan', lambda *_values: [])
    returned = iter([_member(common, name) for name in ('alpha', 'queue')])
    monkeypatch.setattr(binder, 'derive_installed_binding', lambda **values: next(returned))
    packages = [_input('alpha'), _input('queue')]
    group = derive_installed_packages_binding(packages, source_root=str(common))
    specs = {'alpha': {'synthetic_unit_contract': 1}, 'queue': {'synthetic_unit_contract': 2}}
    monkeypatch.setattr(owner, '_group', lambda *args: (group, specs))
    ancestor = common / 'owners'
    ancestor.mkdir(mode=0o700)
    root = ancestor / 'owner'
    root.mkdir(mode=0o700)
    write_source(root)
    (root / 'pyproject.toml').write_text('# source transaction double only\n')
    plan = owner.plan_packages_owner(str(root), packages, source_root=str(common),
                                    trusted_binding_sha256=group['binding_sha256'])
    transactions = tmp_path / 'transactions'
    transactions.mkdir(mode=0o700)
    receipt = owner.apply_packages_owner(plan, str(transactions / 'one'),
                                        approved_plan_sha256=plan['plan_sha256'])
    replaced = {'owner': root, 'ancestor': ancestor, 'common': common}[alias]
    relocated = tmp_path / 'relocated'
    replaced.rename(relocated)
    external = tmp_path / 'external'
    shutil.copytree(relocated, external)
    before = {str(path.relative_to(external)): path.read_bytes()
              for path in external.rglob('*') if path.is_file()}
    replaced.symlink_to(external, target_is_directory=True)
    # Refuse before even parsing the source preimage or looking at target bytes.
    monkeypatch.setattr(owner, '_owner_source', lambda *_args, **_kwargs:
                        pytest.fail('aliased owner source was inspected'))
    for call in (
        lambda: owner.packages_owner_source_status(plan, receipt,
            trusted_receipt_sha256=receipt['receipt_sha256']),
        lambda: owner.rollback_packages_owner(plan, receipt,
            trusted_receipt_sha256=receipt['receipt_sha256'], approved_plan_sha256=plan['plan_sha256']),
    ):
        with pytest.raises(owner.PackagesOwnerError, match='^packages_owner_private_scope_required$'):
            call()
    assert not (transactions / 'one/rollback-intent.json').exists()
    assert {str(path.relative_to(external)): path.read_bytes()
            for path in external.rglob('*') if path.is_file()} == before


def test_dunder_literal_factory_cannot_be_a_module_hook(tmp_path):
    path = tmp_path / owner.OWNER_FILE
    path.parent.mkdir(parents=True)
    path.write_text(SOURCE.replace('def request():', 'def __getattr__():')
                          .replace('payload = request()', 'payload = __getattr__()'))
    with pytest.raises(owner.PackagesOwnerError, match='^packages_owner_source_shape_unsupported$'):
        owner._owner_source(tmp_path)
