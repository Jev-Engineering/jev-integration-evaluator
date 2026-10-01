"""Explicit owned recovery of an interrupted Node package build or install.

No pinned Node toolchain is needed. The first group exercises the recovery
journal, the owned-tree snapshot and the approval binding on any platform. The
second group needs native Linux ownership semantics (uid, modes, inodes and
advisory locks) and runs the real build, install, status and recovery code
against small fixture trees. Interruptions are injected with the fault hooks
the classification tests already use; only the upstream source and toolchain
verifier, which needs the pinned toolchain, is replaced.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import stat
from pathlib import Path, PurePosixPath

import pytest

from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import InputError, digest, file_hash, read_json
from jev_integration_evaluator import template_node_installation as node_install

native = pytest.mark.skipif(
    platform.system() != 'Linux' or platform.machine().lower() != 'x86_64',
    reason='native Linux x86-64 ownership, inode and lock semantics required')

SHA = {letter: letter * 64 for letter in 'abcdef'}


def _sealed_plan(**changes) -> dict:
    plan = {'schema_version': '1.0', 'kind': 'node-recovery-plan-v1', 'target': 'generation',
            'step_plan_sha256': SHA['a'], 'root': '/private/generations/jev-node-env-x',
            'stage': 'intent_recorded', 'intent_sha256': SHA['b'], 'root_identity': None,
            'journal': [], 'generation_sha256': None, 'entries': 0,
            'recovery_journal_head': None,
            'operations': ['record_recovery_start', 'record_recovery_complete',
                           'remove_ownership_intent'],
            'mode': 'off', 'runtime_activation_authorized': False}
    plan.update(changes)
    plan['recovery_sha256'] = digest(plan)
    return plan


# Platform-independent journal, snapshot and approval binding.

def test_recovery_journal_is_chained_retained_and_tamper_evident(tmp_path):
    root = tmp_path / 'owned'
    assert node_install._recovery_rows(root) == []
    assert node_install._recovery_summary(root) == {}
    detail = {'stage': 'journal_recorded', 'journal': [{'event': 'install_started'}]}
    first = node_install._recovery_record(root, 'generation', SHA['a'], SHA['b'],
                                          'recovery_started', detail)
    with pytest.raises(InputError, match='incomplete without ownership intent'):
        node_install._recovery_summary(root)
    second = node_install._recovery_record(root, 'generation', SHA['a'], SHA['b'],
                                           'recovery_complete', {'started_sha256': first})
    third = node_install._recovery_record(root, 'generation', SHA['c'], SHA['d'],
                                          'recovery_started', {'stage': 'intent_recorded'})
    fourth = node_install._recovery_record(root, 'generation', SHA['c'], SHA['d'],
                                           'recovery_complete', {'started_sha256': third})
    rows = node_install._recovery_rows(root)
    assert [row['record_sha256'] for row in rows] == [first, second, third, fourth]
    assert [row['previous'] for row in rows] == [None, first, second, third]
    assert rows[0]['detail'] == detail and rows[0]['root'] == str(root)
    assert node_install._recovery_summary(root) == {
        'recovered_attempts': 2, 'recovery_journal_head': fourth}
    path = node_install._recovery_path(root)
    assert path.parent == tmp_path and path.name.startswith('.jev-node-recovery-')
    original = path.read_bytes()
    lines = original.splitlines(keepends=True)

    def refused(raw: bytes, reason: str) -> None:
        path.write_bytes(raw)
        with pytest.raises(InputError, match=reason):
            node_install._recovery_rows(root)
        with pytest.raises(InputError, match=reason):
            node_install._recovery_record(root, 'generation', SHA['e'], SHA['f'],
                                          'recovery_started', {})
        assert path.read_bytes() == raw

    refused(original.replace(b'install_started', b'install_complete'), 'journal changed')
    refused(b''.join(lines[1:]), 'journal changed')            # erased first attempt
    refused(b''.join(lines[:2] + lines[3:]), 'journal changed')  # erased middle row
    refused(original[:-1], 'torn or oversized')
    refused(original + b'{"sequence":4}\n', 'journal changed')
    refused(original + b'not json\n', 'journal changed')
    # A correctly sealed completion that does not close its own start is refused.
    orphan = {'sequence': 4, 'previous': fourth, 'target': 'generation', 'root': str(root),
              'plan_sha256': SHA['c'], 'recovery_sha256': SHA['e'],
              'event': 'recovery_complete', 'detail': {'started_sha256': fourth}}
    orphan['record_sha256'] = digest(orphan)
    refused(original + (json.dumps(orphan, sort_keys=True, separators=(',', ':')) + '\n').encode(),
            'journal changed')
    # A journal copied from another owned root is not accepted for this one.
    other = tmp_path / 'other-owned'
    node_install._recovery_path(other).write_bytes(original)
    with pytest.raises(InputError, match='journal changed'):
        node_install._recovery_rows(other)
    path.write_bytes(original)
    assert len(node_install._recovery_rows(root)) == 4


def test_owned_snapshot_binds_every_entry_and_refuses_hard_links(tmp_path):
    root = tmp_path / 'owned'
    (root / 'app/lib').mkdir(parents=True)
    (root / 'app/start.cjs').write_bytes(b'one\n')
    (root / 'app/lib/util.cjs').write_bytes(b'two\n')
    (root / 'owner.json').write_bytes(b'{}\n')
    first, entries = node_install._owned_snapshot(root, nested_links=False)
    assert entries == 5
    assert node_install._owned_snapshot(root, nested_links=True) == (first, 5)
    (root / 'app/lib/util.cjs').write_bytes(b'TWO\n')
    changed, _ = node_install._owned_snapshot(root, nested_links=False)
    assert changed != first
    (root / 'app/lib/util.cjs').write_bytes(b'two\n')
    assert node_install._owned_snapshot(root, nested_links=False) == (first, 5)
    (root / 'app/extra.cjs').write_bytes(b'')
    added, entries = node_install._owned_snapshot(root, nested_links=False)
    assert added != first and entries == 6
    (root / 'app/extra.cjs').unlink()
    (root / 'app/empty').mkdir()
    assert node_install._owned_snapshot(root, nested_links=False)[0] != first
    (root / 'app/empty').rmdir()
    outside = tmp_path / 'outside.bin'
    outside.write_bytes(b'unrelated\n')
    os.link(outside, root / 'app/linked.bin')
    for nested_links in (False, True):
        with pytest.raises(InputError, match='unsupported file'):
            node_install._owned_snapshot(root, nested_links=nested_links)
    assert outside.read_bytes() == b'unrelated\n'
    with pytest.raises(InputError, match='not a directory'):
        node_install._owned_snapshot(outside, nested_links=False)


def test_recovery_approval_and_binding_refuse_before_any_effect(tmp_path):
    # A POSIX path on every platform: only the binding checks are reached here.
    root = PurePosixPath('/private/generations/jev-node-env-x')
    plan = _sealed_plan(root=str(root))
    validate_contract(plan, 'node-recovery-plan-v1')

    def never():
        raise AssertionError('refusal must precede revalidation and effects')

    def refused(recovery_plan, approved, reason, *, target='generation', step=SHA['a']):
        with pytest.raises(InputError, match=reason):
            node_install._recover(target, step, root, recovery_plan, approved, never)

    refused(plan, '0' * 64, 'Exact Node recovery approval required')
    refused(plan, plan['step_plan_sha256'], 'Exact Node recovery approval required')
    stale = dict(plan, stage='directory_created')            # edited after sealing
    refused(stale, plan['recovery_sha256'], 'Exact Node recovery approval required')
    refused(plan, plan['recovery_sha256'], 'bound to another step or root', step=SHA['c'])
    refused(plan, plan['recovery_sha256'], 'bound to another step or root', target='package')
    escaped = _sealed_plan(root='/private/generations/jev-node-env-other')
    refused(escaped, escaped['recovery_sha256'], 'bound to another step or root')
    for invalid in (dict(plan, extra=True), {k: v for k, v in plan.items() if k != 'journal'},
                    dict(plan, root='relative/root'), dict(plan, mode='shadow'),
                    dict(plan, operations=['remove_owned_root', 'delete_everything', 'x'])):
        refused(invalid, plan['recovery_sha256'], 'Invalid node-recovery-plan-v1 contract')
    assert list(tmp_path.iterdir()) == []


def test_recovery_receipt_contract_is_strict():
    receipt = {'schema_version': '1.0', 'kind': 'node-recovery-receipt-v1',
               'target': 'package', 'status': 'owned_incomplete_package_removed',
               'step_plan_sha256': SHA['a'], 'recovery_sha256': SHA['b'],
               'root': '/private/packages/package', 'stage': 'journal_recorded',
               'intent_sha256': SHA['c'], 'interrupted_journal_head': SHA['d'],
               'generation_sha256': SHA['e'], 'removed_entries': 7,
               'recovery_started_sha256': SHA['f'], 'recovery_journal_head': SHA['a'],
               'retry': 'new_plan_approval_required', 'mode': 'off',
               'runtime_activation_authorized': False, 'receipt_sha256': SHA['b']}
    validate_contract(receipt, 'node-recovery-receipt-v1')
    for invalid in (dict(receipt, runtime_activation_authorized=True),
                    dict(receipt, retry='automatic'), dict(receipt, status='adopted'),
                    dict(receipt, extra=1), dict(receipt, recovery_journal_head=None),
                    {k: v for k, v in receipt.items() if k != 'intent_sha256'}):
        with pytest.raises(InputError, match='Invalid node-recovery-receipt-v1 contract'):
            validate_contract(invalid, 'node-recovery-receipt-v1')


# Native Linux: real build/install/status/recovery code over fixture trees.

STAGES = ('intent_recorded', 'directory_created', 'owner_marked', 'journal_recorded')


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True)
    os.chmod(path, 0o700)
    return path


def _state(base: Path, skip: tuple[Path, ...] = ()) -> dict:
    """Every entry under base with bytes, mode, inode and mtime; links unfollowed."""
    rows = {}
    for folder, directories, names in os.walk(base, followlinks=False):
        directories[:] = [name for name in directories if Path(folder) / name not in skip]
        for name in directories + names:
            path = Path(folder) / name
            if path in skip:
                continue
            info = path.lstat()
            identity = (stat.S_IMODE(info.st_mode), info.st_ino)
            if stat.S_ISLNK(info.st_mode):
                rows[str(path)] = ('link', os.readlink(path), identity)
            elif stat.S_ISDIR(info.st_mode):
                rows[str(path)] = ('directory', identity)
            else:
                rows[str(path)] = ('file', path.read_bytes(), identity, info.st_mtime_ns)
    return rows


class Owned:
    """One target (package build or generation install) with deterministic fault hooks."""

    def __init__(self, tmp_path: Path, monkeypatch, target: str):
        self.tmp, self.patch, self.target = tmp_path, monkeypatch, target
        self.node = tmp_path / 'node-binary'
        self.node.write_bytes(b'fixture executable bytes\n')
        self.unrelated = tmp_path / 'unrelated'
        _private(self.unrelated)
        (self.unrelated / 'keep.bin').write_bytes(b'unrelated bytes\n')
        self.roots: dict[str, Path] = {}
        monkeypatch.setattr(node_install, '_check_install',
                            lambda plan: self.roots[plan['plan_sha256']])
        monkeypatch.setattr(node_install, '_check_plan', lambda plan: None)
        if target == 'package':
            self.parent = _private(tmp_path / 'packages')
            host = _private(tmp_path / 'host')
            (host / 'package.json').write_text('{"name":"fixture","version":"1.0.0"}\n')
            (host / 'start.cjs').write_text('module.exports = 1;\n')
            cache = _private(tmp_path / 'cache')
            (cache / 'index.bin').write_bytes(b'cache\n')
            npm = _private(tmp_path / 'npm')
            (npm / 'bin').mkdir()
            (npm / 'bin/npm-cli.js').write_text('// fixture npm\n')
            self.root = self.parent / 'package'
            source = {path.name: file_hash(path) for path in host.iterdir()}
            self.plan = {'request': {'package_directory': str(self.root),
                                     'host_root': str(host), 'offline_cache': str(cache)},
                         'applied_source_files': source,
                         'offline_cache_sha256': digest(node_install._tree(cache)),
                         'toolchain': {'npm_root': str(npm), 'node': str(self.node),
                                       'npm_tree_sha256': digest(node_install._tree(npm)),
                                       'node_sha256': file_hash(self.node)}}
            self.plan['plan_sha256'] = digest(self.plan)
            self.started, self.completed = 'build_started', 'build_complete'
            self.interrupted_status = 'build_interrupted_review_required'
            self.removed_status = 'owned_incomplete_package_removed'
            # A sibling completed-looking output and loose files must survive.
            sibling = _private(self.parent / 'retained-package')
            (sibling / 'package-receipt.json').write_text('{"retained":true}\n')
        else:
            self.parent = _private(tmp_path / 'generations')
            self.retained_plan, retained_root = self._install_plan('retained', 'old')
            self.retained = node_install.install_node_package(
                self.retained_plan, approved_plan_sha256=self.retained_plan['plan_sha256'])
            assert Path(self.retained['generation_path']) == retained_root
            # The session's selection of the retained generation lives elsewhere.
            self.selection = tmp_path / 'selected-generation.json'
            self.selection.write_text(json.dumps({
                'generation_id': self.retained['generation_id'],
                'receipt_sha256': self.retained['receipt_sha256']}))
            self.plan, self.root = self._install_plan('interrupted', 'new')
            self.started, self.completed = 'install_started', 'install_complete'
            self.interrupted_status = 'install_interrupted_review_required'
            self.removed_status = 'owned_incomplete_generation_removed'
        (self.parent / 'operator-note.txt').write_text('not owned by any run\n')
        self.intent = node_install._intent_path(self.root)
        self.history = node_install._recovery_path(self.root)
        self.locks = self.parent / '.jev-node-locks'

    def _install_plan(self, name: str, text: str) -> tuple[dict, Path]:
        package = _private(self.tmp / ('built-' + name))
        (package / 'app/lib').mkdir(parents=True)
        (package / 'app/package.json').write_text('{"name":"fixture"}\n')
        (package / 'app/start.cjs').write_text('require("./lib/value.cjs");\n')
        (package / 'app/lib/value.cjs').write_text(f'module.exports = "{text}";\n')
        artifact = node_install._tree(package / 'app')
        plan = {'package_plan': {'entrypoint': 'start.cjs',
                                 'toolchain': {'node': str(self.node)}},
                'package_receipt': {'package_directory': str(package),
                                    'artifact_files': artifact,
                                    'artifact_sha256': digest(artifact),
                                    'source_sha256': SHA['a'], 'configuration_sha256': SHA['b'],
                                    'secret_references_sha256': SHA['c']}}
        plan['plan_sha256'] = digest(plan)
        root = self.parent / ('jev-node-env-' + plan['plan_sha256'][:24])
        self.roots[plan['plan_sha256']] = root
        return plan, root

    def effect(self, plan: dict | None = None) -> dict:
        plan = plan or self.plan
        function = (node_install.build_node_package if self.target == 'package'
                    else node_install.install_node_package)
        return function(plan, approved_plan_sha256=plan['plan_sha256'])

    def status(self, plan: dict | None = None, **kwargs) -> dict:
        function = (node_install.package_status if self.target == 'package'
                    else node_install.installation_status)
        return function(plan or self.plan, **kwargs)

    def plan_recovery(self, plan: dict | None = None) -> dict:
        function = (node_install.plan_node_package_recovery if self.target == 'package'
                    else node_install.plan_node_install_recovery)
        return function(plan or self.plan)

    def recover(self, recovery: dict, *, plan: dict | None = None,
                approved_plan: str | None = None, approved: str | None = None) -> dict:
        plan = plan or self.plan
        function = (node_install.recover_node_package if self.target == 'package'
                    else node_install.recover_node_installation)
        return function(plan, recovery,
                        approved_plan_sha256=approved_plan or plan['plan_sha256'],
                        approved_recovery_sha256=approved or recovery['recovery_sha256'])

    def interrupt(self, stage: str = 'journal_recorded') -> None:
        """Stop the real effect at one recorded stage, as a killed process would."""
        with self.patch.context() as patch:
            if stage in ('intent_recorded', 'directory_created'):
                create = node_install._safe_new

                def stop_at_directory(path):
                    if stage == 'directory_created':
                        create(path)
                    raise RuntimeError('injected interruption')
                patch.setattr(node_install, '_safe_new', stop_at_directory)
            elif stage == 'owner_marked' or self.target == 'generation':
                record = node_install._record
                stop_event = self.started if stage == 'owner_marked' else self.completed

                def stop_at_record(root, plan_sha256, event):
                    if event == stop_event:
                        raise RuntimeError('injected interruption')
                    return record(root, plan_sha256, event)
                patch.setattr(node_install, '_record', stop_at_record)
            else:
                # The copied source, cache and npm tool are real; npm never starts.
                def stop_before_npm(*args, **kwargs):
                    raise RuntimeError('injected interruption')
                patch.setattr(node_install.subprocess, 'Popen', stop_before_npm)
            with pytest.raises(RuntimeError, match='injected interruption'):
                self.effect()

    def outside(self) -> dict:
        """Everything except the owned root, its intent, its history and lock files."""
        return _state(self.tmp, skip=(self.root, self.intent, self.history, self.locks))

    def everything(self) -> dict:
        return _state(self.tmp, skip=(self.locks,))

    def refuses(self, reason: str, recovery: dict | None = None, **kwargs) -> None:
        """Planning (when no plan is given) or the effect refuses and changes nothing."""
        before = self.everything()
        with pytest.raises(InputError, match=reason):
            if recovery is None:
                self.plan_recovery(kwargs.get('plan'))
            else:
                self.recover(recovery, **kwargs)
        assert self.everything() == before


@pytest.fixture(params=['package', 'generation'])
def owned(request, tmp_path, monkeypatch):
    return Owned(tmp_path, monkeypatch, request.param)


@native
@pytest.mark.parametrize('stage', STAGES)
def test_approved_recovery_removes_only_the_owned_attempt_and_keeps_history(owned, stage):
    outside = owned.outside()
    assert owned.status() == {'status': 'absent', 'stage': 'none'}
    owned.interrupt(stage)
    classified = owned.status()
    assert classified['status'] == owned.interrupted_status
    journal = node_install._journal(owned.root, owned.plan['plan_sha256']) \
        if stage == 'journal_recorded' else []
    if stage == 'journal_recorded':
        assert [row['event'] for row in journal] == [owned.started]
        assert classified == {'status': owned.interrupted_status,
                              'journal_head': journal[-1]['record_sha256']}
        assert (owned.root / 'app').is_dir()
    else:
        assert classified == {'status': owned.interrupted_status, 'stage': stage}
    # Neither status nor a retry of the interrupted step recovers anything.
    interrupted = owned.everything()
    for _ in range(2):
        assert owned.status() == classified
    with pytest.raises((InputError, FileExistsError)):
        owned.effect()
    assert owned.everything() == interrupted and not owned.history.exists()

    recovery = owned.plan_recovery()
    assert owned.everything() == interrupted          # planning is read-only
    assert recovery == owned.plan_recovery()
    assert recovery['target'] == owned.target and recovery['stage'] == stage
    assert recovery['step_plan_sha256'] == owned.plan['plan_sha256']
    assert recovery['root'] == str(owned.root) and recovery['journal'] == journal
    assert recovery['intent_sha256'] == read_json(owned.intent)['intent_sha256']
    assert recovery['recovery_sha256'] != owned.plan['plan_sha256']
    assert recovery['recovery_journal_head'] is None
    if stage == 'intent_recorded':
        assert recovery['root_identity'] is None and recovery['generation_sha256'] is None
        assert 'remove_owned_root' not in recovery['operations']
    else:
        info = owned.root.lstat()
        assert recovery['root_identity'] == {'device': info.st_dev, 'inode': info.st_ino}
        assert recovery['generation_sha256'] == node_install._owned_snapshot(
            owned.root, nested_links=True)[0]
        assert recovery['entries'] == sum(1 for _ in owned.root.rglob('*'))
        assert 'remove_owned_root' in recovery['operations']
    # The step's own approval digest is not a recovery approval, and vice versa.
    owned.refuses('Exact Node recovery approval required', recovery,
                  approved=owned.plan['plan_sha256'])
    owned.refuses('plan approval required for recovery', recovery,
                  approved_plan=recovery['recovery_sha256'])

    receipt = owned.recover(recovery)
    validate_contract(receipt, 'node-recovery-receipt-v1')
    assert receipt['receipt_sha256'] == digest({k: v for k, v in receipt.items()
                                                if k != 'receipt_sha256'})
    assert receipt['status'] == owned.removed_status and receipt['stage'] == stage
    assert receipt['recovery_sha256'] == recovery['recovery_sha256']
    assert receipt['removed_entries'] == recovery['entries']
    assert receipt['interrupted_journal_head'] == (journal[-1]['record_sha256'] if journal else None)
    assert not owned.root.exists() and not owned.root.is_symlink()
    assert not owned.intent.exists()
    assert owned.outside() == outside                 # nothing else changed
    rows = node_install._recovery_rows(owned.root)
    assert [row['event'] for row in rows] == ['recovery_started', 'recovery_complete']
    assert rows[0]['detail']['journal'] == journal and rows[0]['detail']['stage'] == stage
    assert rows[0]['detail']['generation_sha256'] == recovery['generation_sha256']
    assert rows[0]['plan_sha256'] == owned.plan['plan_sha256']
    assert rows[0]['record_sha256'] == receipt['recovery_started_sha256']
    assert rows[1]['record_sha256'] == receipt['recovery_journal_head']
    assert stat.S_IMODE(owned.history.stat().st_mode) == 0o600
    clean = {'status': 'absent', 'stage': 'none', 'recovered_attempts': 1,
             'recovery_journal_head': receipt['recovery_journal_head']}
    assert owned.status() == clean
    # The consumed recovery plan cannot be replayed.
    history = owned.history.read_bytes()
    owned.refuses('requires a recorded interruption', recovery)
    owned.refuses('requires a recorded interruption')

    if owned.target == 'generation':
        assert owned.status(owned.retained_plan,
                            trusted_receipt_sha256=owned.retained['receipt_sha256']) == {
            'status': 'installed_recorded', 'generation_id': owned.retained['generation_id'],
            'receipt_sha256': owned.retained['receipt_sha256'], 'launch_status': 'not_started'}
        assert read_json(owned.selection)['generation_id'] == owned.retained['generation_id']
        # A fresh, separately approved install of the same plan now completes.
        installed = owned.effect()
        assert owned.status(trusted_receipt_sha256=installed['receipt_sha256'])['status'] \
            == 'installed_recorded'
        assert (owned.root / 'app/lib/value.cjs').read_text() == 'module.exports = "new";\n'
        assert owned.history.read_bytes() == history
        owned.refuses('has a receipt; recovery refused')
    else:
        # A fresh build attempt starts cleanly; interrupted again, its recovery
        # extends the same retained history.
        owned.interrupt('journal_recorded')
        again = owned.plan_recovery()
        assert again['recovery_journal_head'] == receipt['recovery_journal_head']
        assert again['recovery_sha256'] != recovery['recovery_sha256']
        second = owned.recover(again)
        assert owned.history.read_bytes().startswith(history)
        assert [row['event'] for row in node_install._recovery_rows(owned.root)] == [
            'recovery_started', 'recovery_complete'] * 2
        assert owned.status() == {'status': 'absent', 'stage': 'none', 'recovered_attempts': 2,
                                  'recovery_journal_head': second['recovery_journal_head']}
        assert owned.outside() == outside


@native
def test_recovery_refuses_without_a_recorded_interruption(owned):
    owned.refuses('requires a recorded interruption')
    # A directory at the planned path without a prior intent was never owned.
    _private(owned.root)
    (owned.root / 'owner.json').write_text('{}')
    owned.refuses('requires a recorded interruption')
    assert not owned.history.exists()


@native
def test_recovery_refuses_a_completed_step(owned):
    owned.interrupt()
    recovery = owned.plan_recovery()
    receipt_name = 'package-receipt.json' if owned.target == 'package' else 'install-receipt.json'
    (owned.root / receipt_name).write_text('{}\n')
    owned.refuses('has a receipt; recovery refused')
    owned.refuses('has a receipt; recovery refused', recovery)
    assert not owned.history.exists()
    if owned.target == 'generation':
        # The really completed retained generation is refused the same way.
        retained_root = Path(owned.retained['generation_path'])
        before = _state(retained_root)
        with pytest.raises(InputError, match='has a receipt; recovery refused'):
            owned.plan_recovery(owned.retained_plan)
        assert _state(retained_root) == before


@native
def test_recovery_refuses_journal_and_plan_digest_mismatch(owned):
    owned.interrupt()
    recovery = owned.plan_recovery()
    journal = owned.root / 'journal.jsonl'
    original = journal.read_bytes()
    # Another plan aimed at the same root does not own this interruption.
    other = dict(owned.plan, plan_sha256=SHA['f'])
    owned.roots[SHA['f']] = owned.root
    owned.refuses('ownership intent changed', plan=other)
    owned.refuses('bound to another step or root', recovery, plan=other)
    rebound = dict(recovery, step_plan_sha256=SHA['f'])
    rebound['recovery_sha256'] = digest({k: v for k, v in rebound.items()
                                         if k != 'recovery_sha256'})
    owned.refuses('ownership intent changed', rebound, plan=other)
    owned.refuses('plan approval required for recovery', recovery, approved_plan='0' * 64)
    owned.refuses('Exact Node recovery approval required', recovery, approved='0' * 64)
    # A journal edited in place, torn, or extended after review is refused.
    journal.write_bytes(original.replace(owned.started.encode(), owned.completed.encode()))
    owned.refuses('ownership journal changed')
    owned.refuses('ownership journal changed', recovery)
    journal.write_bytes(original + b'{"sequence":')
    owned.refuses('ownership journal changed', recovery)
    journal.write_bytes(original)
    node_install._record(owned.root, owned.plan['plan_sha256'], owned.completed)
    owned.refuses('changed since review', recovery)
    journal.write_bytes(original)
    node_install._record(owned.root, owned.plan['plan_sha256'], 'unknown_event')
    owned.refuses('unknown events')
    journal.write_bytes(original)
    # A recovery plan re-sealed with different reviewed facts does not match the root.
    forged = dict(recovery, generation_sha256=SHA['e'])
    forged['recovery_sha256'] = digest({k: v for k, v in forged.items()
                                        if k != 'recovery_sha256'})
    owned.refuses('changed since review', forged)
    # The parent-side recovery history is part of what was reviewed.
    owned.history.write_text('{"sequence":0}\n')
    owned.refuses('recovery journal changed', recovery)
    owned.history.unlink()
    assert owned.recover(recovery)['status'] == owned.removed_status


@native
def test_recovery_refuses_changed_identity_or_contents(owned):
    outside = owned.outside()
    owned.interrupt()
    recovery = owned.plan_recovery()
    entry = owned.root / 'app/start.cjs'
    original = entry.read_bytes()
    entry.write_bytes(original + b'// changed after review\n')
    owned.refuses('changed since review', recovery)
    entry.write_bytes(original)
    (owned.root / 'app/added-after-review.bin').write_bytes(b'')
    owned.refuses('changed since review', recovery)
    (owned.root / 'app/added-after-review.bin').unlink()
    (owned.root / 'unrelated-top-level').write_text('x')
    owned.refuses('unrelated or linked path', recovery)
    owned.refuses('unrelated or linked path')
    (owned.root / 'unrelated-top-level').unlink()
    os.chmod(owned.root, 0o755)
    owned.refuses('identity or permissions changed', recovery)
    os.chmod(owned.root, 0o700)
    owner = owned.root / 'owner.json'
    marker = owner.read_bytes()
    owner.write_text(json.dumps(dict(json.loads(marker), plan_sha256=SHA['f'])))
    owned.refuses('owned root marker changed', recovery)
    owner.write_bytes(marker)
    os.link(owned.unrelated / 'keep.bin', owned.root / 'app/hard-linked.bin')
    owned.refuses('unsupported file', recovery)
    (owned.root / 'app/hard-linked.bin').unlink()
    # The same bytes in a different directory are not the reviewed directory.
    moved = owned.parent / 'moved-aside'
    owned.root.rename(moved)
    shutil.copytree(moved, owned.root)
    os.chmod(owned.root, 0o700)
    assert node_install._owned_snapshot(owned.root, nested_links=True)[0] \
        == recovery['generation_sha256']
    owned.refuses('changed since review', recovery)
    shutil.rmtree(owned.root)
    moved.rename(owned.root)
    owned.recover(recovery)
    assert owned.outside() == outside


@native
def test_recovery_refuses_symlinks_and_path_escapes(owned):
    owned.interrupt()
    recovery = owned.plan_recovery()
    victim = _private(owned.tmp / 'victim')
    (victim / 'precious.bin').write_bytes(b'precious\n')
    victim_state = _state(victim)
    # A recovery plan naming another directory is never trusted for its path.
    escaped = dict(recovery, root=str(victim))
    escaped['recovery_sha256'] = digest({k: v for k, v in escaped.items()
                                         if k != 'recovery_sha256'})
    owned.refuses('bound to another step or root', escaped)
    # Root replaced by a link to foreign bytes.
    moved = owned.parent / 'moved-aside'
    owned.root.rename(moved)
    owned.root.symlink_to(victim, target_is_directory=True)
    owned.refuses('symlink', recovery)
    owned.refuses('symlink')
    owned.root.unlink()
    moved.rename(owned.root)
    # A top-level entry replaced by a link out of the owned root.
    (owned.root / 'app').rename(owned.parent / 'app-aside')
    (owned.root / 'app').symlink_to(victim, target_is_directory=True)
    owned.refuses('unrelated or linked path', recovery)
    owned.refuses('unrelated or linked path')
    (owned.root / 'app').unlink()
    (owned.parent / 'app-aside').rename(owned.root / 'app')
    # The ownership intent or the recovery history replaced by a link.
    intent = owned.intent.read_bytes()
    owned.intent.unlink()
    owned.intent.symlink_to(victim / 'precious.bin')
    owned.refuses('ownership intent replaced', recovery)
    owned.intent.unlink()
    owned.intent.write_bytes(intent)
    os.chmod(owned.intent, 0o600)
    owned.history.symlink_to(victim / 'precious.bin')
    owned.refuses('recovery journal replaced', recovery)
    owned.history.unlink()
    # A nested link: refused in an install generation, which is a plain copy.
    # In a build stage npm may leave such links; they are reviewed as link text
    # and unlinked, and their target is never read, followed or removed.
    nested = owned.root / 'app/node_modules/.bin'
    nested.mkdir(parents=True)
    (nested / 'tool').symlink_to(victim / 'precious.bin')
    (nested / 'tree').symlink_to(victim, target_is_directory=True)
    if owned.target == 'generation':
        owned.refuses('unrelated or linked path', recovery)
        owned.refuses('unrelated or linked path')
        shutil.rmtree(owned.root / 'app/node_modules')
        owned.recover(recovery)
    else:
        owned.refuses('changed since review', recovery)
        reviewed = owned.plan_recovery()
        assert reviewed['generation_sha256'] != recovery['generation_sha256']
        owned.recover(reviewed)
    assert not owned.root.exists()
    assert _state(victim) == victim_state
    assert (victim / 'precious.bin').read_bytes() == b'precious\n'
    assert not (owned.parent / 'moved-aside').exists()


@native
def test_recovery_refuses_a_second_concurrent_owner(owned):
    import fcntl
    owned.interrupt()
    recovery = owned.plan_recovery()
    lock = owned.locks / (digest(str(owned.root)) + '.lock')
    assert lock.is_file()          # the lock the interrupted effect itself used
    holder = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        owned.refuses('busy with another owner', recovery)
        assert not owned.history.exists()
    finally:
        os.close(holder)
    first = owned.recover(recovery)
    # A second recovery of the same reviewed plan finds nothing left to own.
    owned.refuses('requires a recorded interruption', recovery)
    assert owned.status()['recovery_journal_head'] == first['recovery_journal_head']


@native
def test_interrupted_recovery_stays_classified_and_needs_a_new_review(owned):
    outside = owned.outside()
    owned.interrupt()
    first = owned.plan_recovery()
    journal = first['journal']
    # Interrupted while owned content is being removed: the owner marker and the
    # journal are removed last, so status still classifies the same attempt.
    with owned.patch.context() as patch:
        remove_tree = shutil.rmtree
        last = max(path.name for path in owned.root.iterdir() if path.is_dir())

        def stop_rmtree(path, *args, **kwargs):
            if Path(path) == owned.root / last:
                raise RuntimeError('injected recovery interruption')
            return remove_tree(path, *args, **kwargs)
        stop_rmtree.avoids_symlink_attacks = remove_tree.avoids_symlink_attacks
        patch.setattr(node_install.shutil, 'rmtree', stop_rmtree)
        with pytest.raises(RuntimeError, match='injected recovery interruption'):
            owned.recover(first)
    assert owned.status() == {'status': owned.interrupted_status,
                              'journal_head': journal[-1]['record_sha256']}
    assert sorted(path.name for path in owned.root.iterdir()) == sorted(
        ['journal.jsonl', 'owner.json', last])
    owned.refuses('changed since review', first)
    with pytest.raises((InputError, FileExistsError)):
        owned.effect()
    resumed = owned.plan_recovery()
    assert resumed['stage'] == 'journal_recorded' and resumed['journal'] == journal
    assert resumed['recovery_journal_head'] == node_install._recovery_rows(owned.root)[0]['record_sha256']
    # Interrupted after the owned content is gone but before the directory is.
    with owned.patch.context() as patch:
        remove_directory = os.rmdir

        def stop_rmdir(path, *args, **kwargs):
            # Only the final removal of the owned root itself is interrupted.
            if not kwargs and Path(path) == owned.root:
                raise RuntimeError('injected recovery interruption')
            return remove_directory(path, *args, **kwargs)
        patch.setattr(node_install.os, 'rmdir', stop_rmdir)
        with pytest.raises(RuntimeError, match='injected recovery interruption'):
            owned.recover(resumed)
    assert owned.status() == {'status': owned.interrupted_status, 'stage': 'directory_created'}
    assert list(owned.root.iterdir()) == [] and owned.intent.is_file()
    owned.refuses('changed since review', resumed)
    second = owned.plan_recovery()
    assert second['stage'] == 'directory_created'
    assert second['recovery_journal_head'] == node_install._recovery_rows(owned.root)[1]['record_sha256']
    # Interrupted again after removal, before the completion record.
    with owned.patch.context() as patch:
        record = node_install._recovery_record

        def stop_complete(root, target, plan_sha256, recovery_sha256, event, detail):
            if event == 'recovery_complete':
                raise RuntimeError('injected recovery interruption')
            return record(root, target, plan_sha256, recovery_sha256, event, detail)
        patch.setattr(node_install, '_recovery_record', stop_complete)
        with pytest.raises(RuntimeError, match='injected recovery interruption'):
            owned.recover(second)
    assert owned.status() == {'status': owned.interrupted_status, 'stage': 'intent_recorded'}
    with pytest.raises((InputError, FileExistsError)):
        owned.effect()
    third = owned.plan_recovery()
    assert third['stage'] == 'intent_recorded'
    receipt = owned.recover(third)
    rows = node_install._recovery_rows(owned.root)
    assert [(row['event'], row['recovery_sha256']) for row in rows] == [
        ('recovery_started', first['recovery_sha256']),
        ('recovery_started', resumed['recovery_sha256']),
        ('recovery_started', second['recovery_sha256']),
        ('recovery_started', third['recovery_sha256']),
        ('recovery_complete', third['recovery_sha256'])]
    assert rows[0]['detail']['journal'] == journal     # the original attempt is retained
    assert owned.status() == {'status': 'absent', 'stage': 'none', 'recovered_attempts': 1,
                              'recovery_journal_head': receipt['recovery_journal_head']}
    assert owned.outside() == outside
