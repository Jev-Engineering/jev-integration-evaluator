"""Source-bound M console caller; installed claim effects have a separate journey."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.template_catalog import (
    bind_template, materialize_template, prepare_template_binding, validate_template_request,
)
from jev_integration_evaluator.integrations.errors import UnsupportedShape
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation, rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from tests.test_use_case_claim_host import PROFILE, _source_host


BINDING = {'version': '1.0', 'script': 'claim-host',
           'startup_inputs': {'budget_limits': 'limits', 'audit_log': 'audit',
                              'dependency_plan': 'dependencies', 'startup_options': 'options'}}
pytestmark = pytest.mark.skipif(not PROFILE, reason='M source-bound bind fixture requires Linux x86-64 CPython 3.13')


def _bound_host(target: Path, *, version: str = '1.0.0', installed: bool = False,
                connected_authority_source: Path | None = None) -> tuple[dict, dict]:
    _, spec, request = _source_host(target, version)
    entry = spec['verification']['entry_point']
    console = target / 'claim_host/console.py'
    if connected_authority_source is not None:
        assert installed
        (target / 'claim_host/connected_authority.py').write_bytes(
            connected_authority_source.read_bytes())
    if installed:
        source = target / spec['source']['file']
        original = source.read_text(encoding='utf-8')
        old = ("def legacy_dispatch_claim_support(request):\n"
               "    return 'inspect'\n")
        new = ("def legacy_dispatch_claim_support(request):\n"
               "    if os.environ.get('M_SUPPORT_PATH'):\n"
               "        mode = os.environ.get('M_CLAIM_SCENARIO', 'normal')\n"
               f"        variant = {'revise' if version == '1.0.1' else 'accept'!r} if mode == 'normal' else ('accept' if mode in ('duplicate', 'budget') else mode)\n"
               '        draft = claim_consumer.fixture_draft(request, variant)\n'
               '        claim_consumer.commit(request, host_approved=True, generated=draft)\n'
               "        ready = os.environ.get('M_READY_PATH')\n"
               '        if ready:\n'
               "            with Path(ready).open('x', encoding='utf-8') as stream:\n"
               "                stream.write('ready\\n')\n"
               '            time.sleep(15)\n'
               "    return 'inspect'\n")
        assert original.count(old) == 1
        source.write_text(original.replace(
            'from __future__ import annotations\n',
            'from __future__ import annotations\nimport os\nimport time\n'
            'from pathlib import Path\nfrom . import claim_consumer\n', 1).replace(old, new),
                          encoding='utf-8')
        if connected_authority_source is not None:
            original = source.read_text(encoding='utf-8')
            # Author this finite host before scanning or deriving any binding.
            start = original.index('def legacy_dispatch_claim_support(request):\n')
            end = original.find('\ndef ', start + 1)
            assert end != -1
            original = original[:start] + _connected_baseline() + original[end:]
            source.write_text(original, encoding='utf-8')
    console.write_text(
        _installed_console(entry, version, Path(spec['source']['file']).stem) if installed else
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
        "    return [{'task_id': 'claim-task', 'evidence': ['fixture-permit-register-v1']}]\n"
        'def main():\n'
        '    requests = make_requests()\n'
        '    for request in requests:\n'
        f'        {entry}(request)\n'
        '    return 0\n'
        "if __name__ == '__main__':\n    raise SystemExit(main())\n",
        encoding='utf-8')
    if connected_authority_source is not None:
        console.write_text(_connected_console(entry, Path(spec['source']['file']).stem),
                           encoding='utf-8')
    runtime_files = {
        'requirements.lock': ('dependency_lock', 'jev-integration-evaluator==1.3.0.dev1\n',
                              'jev-integration-evaluator==1.3.0.dev12\n'),
        'runtime.json': ('configuration', '{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
                         '{"jev_runtime":{"mode":"off","credential_ref":null,"feature_flag":false}}\n'),
    }
    for name, (kind, old, new) in runtime_files.items():
        path = target / 'claim_host' / name
        path.write_text(old, encoding='utf-8')
        relative = path.relative_to(target).as_posix()
        spec.setdefault('runtime_files', []).append({
            'file': relative, 'kind': kind,
            'old_sha256': hashlib.sha256(old.encode()).hexdigest(), 'new_content': new})
        spec['output']['permitted_edits'].append(relative)
    spec['host_lifecycle'] = {'kind': 'module-startup-v1',
                              'startup': 'start_jev_runtime', 'shutdown': 'stop_jev_runtime',
                              'complete_task': 'finish_jev_task'}
    project = target / 'pyproject.toml'
    project.write_text(project.read_text(encoding='utf-8') +
        '[tool.setuptools.package-data]\nclaim_host = ["*.lock", "*.json"]\n',
        encoding='utf-8')
    cfg = load_config()
    cfg['repository']['typescript_ast'] = False
    inventory = scan_repo(target, cfg)
    candidate = next(row for row in inventory['candidates']
                     if row['source']['symbol'] == 'select_boundary_claim_support')
    reason = ('Reviewed M caller has one task call per bounded request; '
              'code-owned citation, support, audit and release checks remain outside this binder')
    apply_reviews(inventory, {candidate['candidate_id']: {
        'source_sha256': candidate['source']['source_sha256'], 'approved': True,
        'reviewer': 'offline-claim-bind-author', 'reason': reason}}, cfg)
    spec['candidate_id'] = candidate['candidate_id']
    spec['experiment_id'] = candidate['recommended_experiment']['id']
    spec['source'].update({'file_sha256': candidate['source']['file_sha256'],
                           'source_sha256': candidate['source']['source_sha256']})
    spec['binding_review'].update({'source_sha256': candidate['source']['source_sha256'],
                                   'reason': reason})
    for name, (kind, old, _) in runtime_files.items():
        inventory['configuration_evidence'].append({
            'file': 'claim_host/' + name,
            'sha256': hashlib.sha256(old.encode()).hexdigest()})
    inventory['analysis_identity']['configuration_digest'] = digest(inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    spec['inventory_sha256'] = digest(inventory)
    spec['inventory_fingerprint'] = inventory['scan_fingerprint']
    request['reviewed_inventory'] = inventory
    request['implementation_spec'] = spec
    return inventory, request


def _connected_baseline() -> str:
    return '''def legacy_dispatch_claim_support(request):
    if not os.environ.get('M_EFFECT_DIRECTORY'):
        return 'inspect'
    task = request['task_id']
    if task not in ('claim-one', 'claim-two'):
        raise ValueError('unregistered claim task')
    directory = Path(os.environ['M_EFFECT_DIRECTORY']) / task
    for name, member in (('M_SUPPORT_PATH', 'support.json'),
                         ('M_AUDIT_PATH', 'audit.json'),
                         ('M_CLAIM_PATH', 'claim.json')):
        os.environ[name] = str(directory / member)
    if task == 'claim-two':
        with Path(os.environ['M_READY_PATH']).open('x', encoding='utf-8') as stream:
            stream.write('ready\\n')
        if os.environ.get('M_HOLD') == '1':
            deadline = time.monotonic() + 15
            release = Path(os.environ['M_RELEASE_PATH'])
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            if not release.exists():
                raise TimeoutError('claim_release_timeout')
    variant = os.environ.get('M_CLAIM_SCENARIO', 'accept')
    draft = claim_consumer.fixture_draft(request, variant)
    claim_consumer.commit(request, host_approved=os.environ.get('M_APPROVAL', '1') == '1',
                          generated=draft)
    return 'inspect'
'''


def _connected_console(entry: str, source_stem: str) -> str:
    return f'''from .{source_stem} import {entry}
from . import claim_consumer
from pathlib import Path
import os
import hashlib
class Audit:
    def __init__(self): self.records = []
    def append(self, record): self.records.append(record)
def limits():
    return dict(max_calls_per_task=2, max_cost_per_task=2,
                max_total_calls=2, max_total_cost=2, max_in_flight=1, max_tasks=2)
def audit():
    return Audit()
def dependencies():
    base = Path(__file__).resolve().parent
    return {{'files': [{{'path': str(base / name), 'sha256': hashlib.sha256((base / name).read_bytes()).hexdigest()}} for name in ('requirements.lock', 'runtime.json')]}}
def options():
    from . import connected_authority
    return connected_authority.options()
def make_requests():
    mode = os.environ.get('M_TASKS', 'two')
    if mode not in ('two', 'duplicate'):
        raise ValueError('unregistered claim task schedule')
    variant = os.environ.get('M_CLAIM_SCENARIO', 'accept')
    base = claim_consumer.fixture_request(variant)
    ids = ('claim-one', 'claim-one') if mode == 'duplicate' else ('claim-one', 'claim-two')
    return [{{**base, 'task_id': task}} for task in ids]
def main():
    requests = make_requests()
    for request in requests:
        {entry}(request)
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
'''


def _installed_console(entry: str, version: str, source_stem: str) -> str:
    """Author the reviewed finite host before inventory and source binding."""
    variant = 'revise' if version == '1.0.1' else 'accept'
    return (
        f'from .{source_stem} import {entry}\n'
        'from . import claim_consumer\n'
        'from pathlib import Path\nimport os\n'
        'def limits():\n'
        '    return dict(max_calls_per_task=2, max_cost_per_task=2, '
        'max_total_calls=2, max_total_cost=2, max_in_flight=1, max_tasks=1)\n'
        'class Audit:\n'
        '    def __init__(self): self.records = []\n'
        '    def append(self, record): self.records.append(record)\n'
        'def audit():\n    return Audit()\n'
        'def dependencies():\n'
        '    import hashlib\n'
        '    base = Path(__file__).resolve().parent\n'
        "    return {'files': [{'path': str(base / name), 'sha256': hashlib.sha256((base / name).read_bytes()).hexdigest()} for name in ('requirements.lock', 'runtime.json')]}\n"
        'def options():\n    return {}\n'
        'def make_requests():\n'
        "    mode = os.environ.get('M_CLAIM_SCENARIO', 'normal')\n"
        f"    variant = {variant!r} if mode == 'normal' else mode\n"
        "    if mode == 'budget':\n"
        "        base = claim_consumer.fixture_request('accept')\n"
        "        proposed = [base, {**base, 'task_id': 'other-1'}]\n"
        "        if len(proposed) > limits()['max_tasks']:\n"
        "            raise ValueError('claim task budget refused')\n"
        "        return proposed\n"
        "    if mode == 'duplicate':\n"
        "        return [claim_consumer.fixture_request('accept')] * 2\n"
        '    return [claim_consumer.fixture_request(variant)]\n'
        'def main():\n'
        '    requests = make_requests()\n'
        '    for request in requests:\n'
        f'        {entry}(request)\n'
        '    return 0\n'
        "if __name__ == '__main__':\n    raise SystemExit(main())\n"
    )


def test_m_bound_console_source_and_owned_edit(tmp_path):
    target = tmp_path / 'host'
    inventory, request = _bound_host(target)
    prepared = prepare_template_binding(target, request, BINDING)
    entry = prepared['request']['implementation_spec']['entrypoint_binding']
    assert entry['kind'] == 'task-loop-v1'
    assert entry['file'] == 'claim_host/console.py'
    assert entry['pyproject_sha256'] == file_hash(target / 'pyproject.toml')
    bound = prepared['request']
    assert validate_template_request(target, bound)['status'] == 'validated'
    report = bind_template(target, request, BINDING, tmp_path / 'bound')
    assert report['request_sha256'] == digest(bound)
    assert json.loads((tmp_path / 'bound/template-request.json').read_text()) == bound
    materialize_template(target, bound, tmp_path / 'template')
    spec = bound['implementation_spec']
    preimages = {name: (target / name).read_bytes() for name in (
        spec['source']['file'], 'claim_host/console.py',
        'claim_host/requirements.lock', 'claim_host/runtime.json',
        'claim_host/claim_consumer.py')}
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, inventory, spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                   baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert b'start_jev_runtime' in (target / 'claim_host/console.py').read_bytes()
    assert rollback_implementation(target, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
    assert {name: (target / name).read_bytes() for name in preimages} == preimages


def test_m_bound_console_rejects_drift_and_single_call(tmp_path):
    target = tmp_path / 'host'
    _, request = _bound_host(target)
    prepared = prepare_template_binding(target, request, BINDING)
    console = target / 'claim_host/console.py'
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
