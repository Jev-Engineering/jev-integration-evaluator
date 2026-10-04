"""Separately installed, freshly reviewed dual generations; local TLS only."""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys

import pytest

from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.integrations.composite import (
    apply_composite, plan_composite, verify_composite,
)
from jev_integration_evaluator.io import digest, file_hash, read_json
from jev_integration_evaluator.template_catalog import materialize_template
from tests.independent_hosts.registered_dual_connected.qualification import (
    ROOT, source_matched_composite,
)

PROFILE = (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
           and sys.version_info[:2] == (3, 13))
pytestmark = pytest.mark.skipif(not PROFILE, reason='Linux x86-64 CPython 3.13')


def install_dual(root: Path, version: str, task: str, wheelhouse: Path,
                 rows: list[dict], requirements: list[dict], monkeypatch):
    """Author bounded generation source before any scan, review or plan."""
    root.mkdir(mode=0o700)
    host = root / 'host'
    shutil.copytree(ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    project = host / 'pyproject.toml'
    project.write_text(project.read_text().replace('version = "1.0.2"',
                                                 f'version = "{version}"'))
    console = host / 'src/registered_dual/console.py'
    source = console.read_text().replace("'max_total_calls': 2", "'max_total_calls': 6")
    source = source.replace("'max_tasks': 1", "'max_tasks': 2")
    source = source.replace("'max_total_cost': 2", "'max_total_cost': 6")
    # Each generation authors a stable task; environment cannot replace it.
    source = source.replace("os.environ.get('DUAL_TASK_ID', 'dual-task-one')", repr(task))
    # The marker records startup without denying a retained runtime invocation.
    # These are authored fixture bytes included in the fresh source review.
    marker = '''
    release = Path(os.environ['DUAL_RELEASE_PATH'])
    release.with_suffix('.attempt').write_bytes(b'attempt\\n')
    owner = Path(os.environ['DUAL_READY_PATH']).parent / 'owner.txt'
    try:
        fd = os.open(owner, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return
    try:
        os.write(fd, b'one-runtime-startup\\n')
        os.fsync(fd)
    finally:
        os.close(fd)
'''
    startup = ('\n_STARTUP_OBSERVED = False\n\ndef _owned_startup() -> None:\n'
               '    global _STARTUP_OBSERVED\n'
               "    if _STARTUP_OBSERVED or 'DUAL_RELEASE_PATH' not in os.environ:\n"
               '        return\n' + marker + '    _STARTUP_OBSERVED = True\n\n')
    source = source.replace('def make_alpha() -> dict:\n',
                            startup + 'def make_alpha() -> dict:\n    _owned_startup()\n')
    source = source.replace("b'dual-ready\\n'", "b'ready\\n'")
    console.write_text(source)
    expected = {'dual-upgrade-one': 'b989858b85486ffd6752585269968142ef09e146e61269a11416195b2cf0f144',
                'dual-upgrade-two': 'e42159ca02c231a9374e3b8c71aaeeafe0c887ff1812c8a0381b5498f62d04d6'}
    assert file_hash(console) == expected[task]
    inventory, selection, specs = source_matched_composite(host)
    templates = {}
    for candidate, spec in specs.items():
        output = root / ('template-' + candidate)
        materialize_template(host, {'schema_version': '1.0',
            'template_id': 'python.bounded-tail-call', 'template_version': '1.0.0',
            'backend': 'python', 'profile': 'module-tail-call-v1',
            'reviewed_inventory': inventory, 'implementation_spec': spec}, output)
        templates[candidate] = str(output)
    bundle = root / 'bundle'
    planned = plan_composite(host, inventory, selection, specs, bundle)
    probe = root / 'probe'
    probe.mkdir(mode=0o700)
    with monkeypatch.context() as patch:
        for name in ('REGISTERED_ALPHA_PROBE_EFFECTS_DIR', 'WORK_QUEUE_PROBE_EFFECTS_DIR'):
            patch.setenv(name, str(probe))
        patch.setenv('DUAL_SHADOW', '1')
        baseline = verify_composite(host, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'baseline_passed'
        apply_composite(host, bundle, planned['bundle_digest'],
                        baseline_sha256=baseline['receipt_sha256'])
        verified = verify_composite(host, bundle, 'modified', approve_execution=True,
                                    baseline_sha256=baseline['receipt_sha256'])
        assert verified['status'] == 'verified'
    environments = root / 'environments'
    environments.mkdir(mode=0o700)
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    request = {'schema_version': '1.0', 'host_root': str(host),
        'implementation_bundle': str(bundle),
        'trusted_modified_receipt_sha256': verified['receipt_sha256'],
        'template_directories': templates,
        'reviewed_package_source_sha256': digest(installer._tree(host)),
        'reviewed_configuration_sha256': digest(config), 'interpreter': sys.executable,
        'wheelhouse': str(wheelhouse), 'package_directory': str(root / 'package'),
        'environment_parent': str(environments),
        'console_script': read_json(bundle / 'composite-console.json')['script'],
        'build_tools': {name: importlib.metadata.version(name)
                        for name in ('pip', 'setuptools', 'wheel')},
        'wheels': rows, 'requirements': requirements,
        'configuration': config, 'secret_references': {}}
    package_plan = installer.plan_composite_package(request)
    built = installer.build_composite_package(package_plan,
        approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_composite_install(package_plan, built)
    receipt = installer.install_composite_package(install_plan,
        approved_plan_sha256=install_plan['plan_sha256'])
    return {'target': host / 'src'}, install_plan, receipt


TASKS = ('dual-upgrade-one', 'dual-upgrade-two')


def _layout(folder: Path, task: str) -> dict:
    ready, release = folder / 'ready.txt', folder / 'release.txt'
    alpha = {'action': 'inspect', 'item': 'fixture-one', 'task_id': task}
    queue = {'operation': 'enqueue', 'item': 'fixture-one', 'task_id': task}
    raw = lambda value: (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    return {'environment': {'REGISTERED_ALPHA_EFFECTS': str(folder / 'alpha.jsonl'),
                'WORK_QUEUE_EFFECTS': str(folder / 'queue.jsonl'),
                'DUAL_AUDIT_PATH': str(folder / 'audit.json'), 'DUAL_PERMIT': '1',
                'DUAL_HOLD': '1', 'DUAL_READY_PATH': str(ready),
                'DUAL_RELEASE_PATH': str(release)},
            'ready': ready, 'release': release,
            'effects': [(folder / 'alpha.jsonl', raw(alpha)),
                        (folder / 'queue.jsonl', raw(queue))]}


def _verify(layout: dict, task: str) -> None:
    for path, expected in layout['effects']:
        assert path.read_bytes() == expected
        assert json.loads(expected)['task_id'] == task


def test_installed_dual_connected_upgrade_and_retained_rollback(tmp_path, monkeypatch):
    from tests.connected_generation_journey import GenerationJourney, run_generation_journey
    def install(tmp, index, version, task, wheelhouse, rows, requirements):
        return install_dual(tmp / f'dual-{index}', version, task, wheelhouse,
                            rows, requirements, monkeypatch)
    journey = GenerationJourney(host_profile='registered-dual-connected-v1',
        package='registered_dual', reference_name='REGISTERED_DUAL_CONNECTED_REF',
        public_name='REGISTERED_DUAL_AUTH_PUBKEY_FILE', release_name='DUAL_RELEASE_PATH',
        tasks=TASKS, preferred_label=None,
        other_profiles=('retrieval-d-v1', 'retention-h-v1', 'graph-l-v1',
                        'claim-m-v1', 'completion-e-v1'),
        install=install, layout=_layout, verify=_verify, composite=True,
        calls_per_generation=2, replay_headroom=2)
    result = run_generation_journey(tmp_path, monkeypatch, journey)
    assert result['calls'] == 4
