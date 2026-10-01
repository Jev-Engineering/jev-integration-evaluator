"""Source-bound L task-loop console binding; SQLite effects remain host owned."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys

import pytest

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.template_catalog import (
    bind_template, materialize_template, prepare_template_binding, validate_template_request,
)
from jev_integration_evaluator.integrations.errors import UnsupportedShape
from jev_integration_evaluator.integrations.contracts import validate_spec
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation, rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from tests.test_use_case_graph_host import _graph_host


PROFILE = (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
           and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13))
pytestmark = pytest.mark.skipif(not PROFILE, reason='L bound fixture requires Linux x86-64 CPython 3.13')
BINDING = {'version': '1.0', 'script': 'graph-host',
           'startup_inputs': {'budget_limits': 'limits', 'audit_log': 'audit',
                              'dependency_plan': 'dependencies', 'startup_options': 'options'}}


def _bound_host(target: Path, *, version: str = '1.0.0', installed: bool = False,
                connected_authority_source: Path | None = None,
                generation_task: str | None = None) -> tuple[dict, dict]:
    if generation_task is not None:
        assert generation_task in ('graph-one', 'graph-two')
        assert installed and connected_authority_source is not None
    _, spec = _graph_host(target, version)
    if connected_authority_source is not None:
        assert installed
        (target / 'graph_host/connected_authority.py').write_bytes(
            connected_authority_source.read_bytes())
    entry = spec['verification']['entry_point']
    console = target / 'graph_host/console.py'
    if installed and connected_authority_source is not None:
        source = target / spec['source']['file']
        original = source.read_text(encoding='utf-8')
        merge = "    STATE['revision'] = graph_runtime.merge(request, STATE)\n"
        assert original.count(merge) == 2
        pre = (
            "    import os\n"
            "    if request['task_id'] == 'graph-two':\n"
            "        os.environ['GRAPH_EFFECT_PATH'] = os.environ['GRAPH_SECOND_EFFECT_PATH']\n"
            "        STATE['expected_revision'] = 1\n"
        ) if generation_task is None else (
            # A generation host owns one pinned task, one effect path and its
            # own SQLite graph at the initial revision.
            "    import os\n"
        )
        post = (
            f"    if request['task_id'] == '{generation_task or 'graph-one'}':\n"
            "        from pathlib import Path\n"
            "        ready = Path(os.environ['GRAPH_READY_PATH'])\n"
            "        with ready.open('x', encoding='utf-8') as stream:\n"
            "            stream.write('ready\\n')\n"
            "        if os.environ.get('L_HOLD') == '1':\n"
            "            import time\n"
            "            release = Path(os.environ['L_RELEASE_PATH'])\n"
            "            deadline = time.monotonic() + 15\n"
            "            while not release.exists() and time.monotonic() < deadline:\n"
            "                time.sleep(.02)\n"
            "            if not release.exists(): raise TimeoutError('graph_release_timeout')\n"
        )
        source.write_text(original.replace(merge, pre + merge + post), encoding='utf-8')
    elif installed:
        source = target / spec['source']['file']
        original = source.read_text(encoding='utf-8')
        merge = "    STATE['revision'] = graph_runtime.merge(request, STATE)\n"
        assert original.count(merge) == 2
        # The reviewed host emits readiness only after its pinned consumer has
        # committed the SQLite effect; this is authored before the fresh scan.
        ready = (
            "    import os\n"
            "    from pathlib import Path\n"
            "    ready_path = os.environ.get('GRAPH_READY_PATH')\n"
            "    if ready_path:\n"
            "        with Path(ready_path).open('x', encoding='utf-8') as stream:\n"
            "            stream.write('ready\\n')\n"
            "        import time\n"
            "        time.sleep(15)\n"
        )
        source.write_text(original.replace(merge, merge + ready), encoding='utf-8')
    if connected_authority_source is not None:
        owner = '' if generation_task is None else (
            # The retained generation reuses the original effect directory. A
            # second normal console must refuse ownership before shadow
            # fallback can call the original graph consumer again.
            "    if os.environ.get('L_CONNECTED_REF'):\n"
            "        with (Path(os.environ['GRAPH_EFFECT_PATH']).parent / 'owner.txt').open('x', encoding='utf-8') as stream:\n"
            "            stream.write('one-runtime-startup\\n')\n")
        schedule = (
            "    return [{'task_id': 'graph-one', 'graph_action': 'reconcile_same'},\n"
            "            {'task_id': 'graph-two' if os.environ.get('L_TASKS', 'two') == 'two' else 'graph-one', 'graph_action': 'reconcile_same'}]\n"
        ) if generation_task is None else (
            "    release = os.environ.get('L_RELEASE_PATH')\n"
            "    if release:\n"
            "        with Path(release).with_suffix('.attempt').open('x', encoding='utf-8') as stream:\n"
            "            stream.write('attempt\\n')\n"
            f"    return [{{'task_id': '{generation_task}', 'graph_action': 'reconcile_same'}}]\n")
        console.write_text(
            f'from .{Path(spec["source"]["file"]).stem} import {entry}\n'
            f'from . import {Path(spec["source"]["file"]).stem} as observed_host\n'
            'from . import connected_authority\n'
            'from pathlib import Path\nimport hashlib\nimport json\nimport os\nimport threading\nimport time\n'
            'class Audit:\n'
            '    def __init__(self):\n'
            '        self.records = []\n'
            '        self.lock = threading.Lock()\n'
            '    def append(self, record):\n'
            '        self.records.append(record)\n'
            "        if record.get('type') == 'assessment_error' and record.get('error_class') in ('EvaluationTimeoutError', 'JSONDecodeError'):\n"
            "            folder = Path(os.environ['GRAPH_EFFECT_PATH']).parent\n"
            "            path = folder / 'failure-events.jsonl'\n"
            "            raw = (json.dumps({'type': 'assessment_error', 'error_class': record['error_class']}, sort_keys=True) + '\\n').encode()\n"
            '            with self.lock:\n'
            '                descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)\n'
            "                with os.fdopen(descriptor, 'ab') as stream:\n"
            '                    stream.write(raw)\n'
            '                    stream.flush()\n'
            '                    os.fsync(stream.fileno())\n'
            'def limits():\n'
            + owner +
            '    return dict(max_calls_per_task=2, max_cost_per_task=2, '
            'max_total_calls=2, max_total_cost=2, max_in_flight=1, max_tasks=2)\n'
            'def audit():\n    return Audit()\n'
            'def dependencies():\n'
            '    base = Path(__file__).resolve().parent\n'
            "    return {'files': [{'path': str(base / name), 'sha256': hashlib.sha256((base / name).read_bytes()).hexdigest()} for name in ('requirements.lock', 'runtime.json')]}\n"
            'def options():\n    return connected_authority.options()\n'
            'def make_requests():\n'
            "    if os.environ.get('L_APPROVAL', '1') == '0':\n"
            "        observed_host.STATE['approval'] = False\n"
            "    observed_host.STATE['expected_revision'] = int(os.environ.get('L_EXPECTED_REVISION', '0'))\n"
            + schedule +
            'def main():\n'
            '    requests = make_requests()\n'
            '    for request in requests:\n'
            f'        {entry}(request)\n'
            '    return 0\n'
            "if __name__ == '__main__':\n    raise SystemExit(main())\n",
            encoding='utf-8')
    else:
        console.write_text(
        f'from .{Path(spec["source"]["file"]).stem} import {entry}\n'
        'from pathlib import Path\nimport hashlib\n'
        'class Audit:\n'
        '    def __init__(self): self.records = []\n'
        '    def append(self, record): self.records.append(record)\n'
        'def limits():\n'
        '    return dict(max_calls_per_task=2, max_cost_per_task=2, '
        'max_total_calls=2, max_total_cost=2, max_in_flight=1, max_tasks=1)\n'
        'def audit():\n    return Audit()\n'
        'def dependencies():\n'
        '    base = Path(__file__).resolve().parent\n'
        "    return {'files': [{'path': str(base / name), 'sha256': hashlib.sha256((base / name).read_bytes()).hexdigest()} for name in ('requirements.lock', 'runtime.json')]}\n"
        'def options():\n    return {}\n'
        'def make_requests():\n'
        "    return [{'task_id': 'graph-task', 'graph_action': 'reconcile_same'}]\n"
        'def main():\n'
        '    requests = make_requests()\n'
        '    for request in requests:\n'
        f'        {entry}(request)\n'
        '    return 0\n'
        "if __name__ == '__main__':\n    raise SystemExit(main())\n",
            encoding='utf-8')
    for name, kind, old, new in (
        ('requirements.lock', 'dependency_lock', 'jev-integration-evaluator==1.3.0.dev1\n',
         'jev-integration-evaluator==1.3.0.dev12\n'),
        ('runtime.json', 'configuration', '{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
         '{"jev_runtime":{"mode":"off","credential_ref":null,"feature_flag":false}}\n'),
    ):
        (target / 'graph_host' / name).write_text(old, encoding='utf-8')
        relative = 'graph_host/' + name
        spec.setdefault('runtime_files', []).append({
            'file': relative, 'kind': kind,
            'old_sha256': hashlib.sha256(old.encode()).hexdigest(), 'new_content': new})
        spec['output']['permitted_edits'].append(relative)
    spec['host_lifecycle'] = {'kind': 'module-startup-v1',
                              'startup': 'start_jev_runtime', 'shutdown': 'stop_jev_runtime',
                              'complete_task': 'finish_jev_task'}
    project = target / 'pyproject.toml'
    project.write_text(project.read_text(encoding='utf-8') +
                       '[tool.setuptools.package-data]\ngraph_host = ["*.lock", "*.json"]\n',
                       encoding='utf-8')
    cfg = load_config()
    cfg['repository']['typescript_ast'] = False
    inventory = scan_repo(target, cfg)
    candidate = next(row for row in inventory['candidates']
                     if row['source']['symbol'] == 'select_boundary_graph_consumer')
    reason = ('Reviewed L finite caller; approval, exact entities, revision and '
              'pre-mutation audit remain host-owned and independently read back')
    apply_reviews(inventory, {candidate['candidate_id']: {
        'source_sha256': candidate['source']['source_sha256'], 'approved': True,
        'reviewer': 'offline-graph-bind-author', 'reason': reason}}, cfg)
    spec['candidate_id'] = candidate['candidate_id']
    spec['experiment_id'] = candidate['recommended_experiment']['id']
    spec['source'].update({'file_sha256': candidate['source']['file_sha256'],
                           'source_sha256': candidate['source']['source_sha256']})
    spec['binding_review'].update({'source_sha256': candidate['source']['source_sha256'],
                                   'reason': reason})
    for name in ('requirements.lock', 'runtime.json'):
        inventory['configuration_evidence'].append({
            'file': 'graph_host/' + name,
            'sha256': file_hash(target / 'graph_host' / name)})
    inventory['analysis_identity']['configuration_digest'] = digest(inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    spec['inventory_sha256'] = digest(inventory)
    spec['inventory_fingerprint'] = inventory['scan_fingerprint']
    request = {'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
               'template_version': '1.0.0', 'backend': 'python',
               'profile': 'module-tail-call-v1', 'reviewed_inventory': inventory,
               'implementation_spec': spec}
    return inventory, request


def test_l_bound_console_source_and_owned_edit(tmp_path):
    target = tmp_path / 'host'
    inventory, request = _bound_host(target)
    prepared = prepare_template_binding(target, request, BINDING)
    entry = prepared['request']['implementation_spec']['entrypoint_binding']
    assert entry['kind'] == 'task-loop-v1'
    assert entry['file'] == 'graph_host/console.py'
    assert entry['pyproject_sha256'] == file_hash(target / 'pyproject.toml')
    invalid = dict(prepared['request']['implementation_spec'])
    invalid['entrypoint_binding'] = dict(entry, kind='single-request-v1', item_symbol=None)
    with pytest.raises(InputError, match='Invalid implementation specification'):
        validate_spec(invalid)
    bound = prepared['request']
    assert validate_template_request(target, bound)['status'] == 'validated'
    report = bind_template(target, request, BINDING, tmp_path / 'bound')
    assert report['request_sha256'] == digest(bound)
    materialize_template(target, bound, tmp_path / 'template')
    spec = bound['implementation_spec']
    preimages = {name: (target / name).read_bytes() for name in (
        spec['source']['file'], 'graph_host/console.py',
        'graph_host/requirements.lock', 'graph_host/runtime.json',
        'graph_host/graph_runtime.py', 'graph_host/graph.py')}
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, inventory, spec['candidate_id'], spec, bundle)
    effects = tmp_path / 'effects'
    effects.mkdir(mode=0o700)
    with pytest.MonkeyPatch.context() as env:
        env.setenv('GRAPH_EFFECT_PATH', str(effects / 'graph-{pid}.json'))
        env.setenv('GRAPH_DB_PATH', str(effects / 'graph-{pid}.sqlite'))
        baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'baseline_passed'
        applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                       baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                         baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert b'start_jev_runtime' in (target / 'graph_host/console.py').read_bytes()
    console_effect = effects / 'normal-console.json'
    console_db = effects / 'normal-console.sqlite'
    launched = subprocess.run(
        [sys.executable, '-m', 'graph_host.console'], cwd=target, text=True,
        capture_output=True, timeout=30,
        env={**os.environ, 'PYTHONPATH': str(target), 'GRAPH_EFFECT_PATH': str(console_effect),
             'GRAPH_DB_PATH': str(console_db)})
    assert launched.returncode == 0, launched.stderr
    observed = json.loads(console_effect.read_text(encoding='utf-8'))
    assert observed['revision'] == 1
    with sqlite3.connect(console_db.as_uri() + '?mode=ro', uri=True) as db:
        assert db.execute('SELECT value FROM revision').fetchall() == [(1,)]
        assert db.execute('SELECT key, provenance FROM entities ORDER BY key').fetchall() == [
            ('left', 'registry-left'), ('right', 'registry-right')]
        audit = [json.loads(row[0]) for row in db.execute('SELECT receipt FROM audit')]
        merges = [json.loads(row[0]) for row in db.execute('SELECT receipt FROM merges')]
    assert audit == merges == [observed['receipt']]
    assert rollback_implementation(target, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
    assert {name: (target / name).read_bytes() for name in preimages} == preimages


def test_l_bound_console_rejects_drift_and_single_call(tmp_path):
    target = tmp_path / 'host'
    _, request = _bound_host(target)
    prepared = prepare_template_binding(target, request, BINDING)
    console = target / 'graph_host/console.py'
    original = console.read_bytes()
    console.write_bytes(original + b'\n# unreviewed caller\n')
    with pytest.raises(InputError, match='drift|changed'):
        validate_template_request(target, prepared['request'])
    console.write_bytes(original)
    entry = request['implementation_spec']['verification']['entry_point']
    single = original.decode().replace(
        '    requests = make_requests()\n    for request in requests:\n'
        f'        {entry}(request)\n    return 0\n',
        '    request = make_requests()\n'
        f'    return {entry}(request)\n')
    assert single != original.decode()
    console.write_text(single, encoding='utf-8')
    with pytest.raises(UnsupportedShape, match='bounded explicit request loop'):
        prepare_template_binding(target, request, BINDING)
