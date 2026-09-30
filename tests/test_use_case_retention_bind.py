"""Reviewed H console bind, installed off-mode choice and raw retention effect."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import shutil
import sys

import pytest
import jev_integration_evaluator as evaluator_package

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.template_catalog import (
    bind_template, materialize_template, prepare_template_binding, validate_template_request,
)
from jev_integration_evaluator.integrations.errors import UnsupportedShape
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, implementation_status, plan_implementation, rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator import template_installation as installer
from tests.test_template_installation import _metadata
from tests.test_use_case_retention_host import _host, _probe_effect_path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
           and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13))
pytestmark = pytest.mark.skipif(not PROFILE, reason='H installed bind profile requires Linux CPython 3.13')
BINDING = {'version': '1.0', 'script': 'retention-host',
           'startup_inputs': {'budget_limits': 'limits', 'audit_log': 'audit',
                              'dependency_plan': 'dependencies', 'startup_options': 'options'}}


def _bound_host(target: Path, *, version: str = '1.0.0', installed: bool = False,
                connected_loader: Path | None = None) -> tuple[dict, dict, dict]:
    _, spec, request = _host(target, version)
    source = target / spec['source']['file']
    entry = spec['verification']['entry_point']
    if connected_loader is not None:
        assert installed
        shutil.copyfile(connected_loader, target / 'retention_host/connected_authority.py')
        original = source.read_text(encoding='utf-8')
        marker = "    STATE['kept'] = retention_consumer.commit(request, action)\n"
        assert original.count(marker) == 1
        before = (
            "    import os\n"
            "    from pathlib import Path\n"
            "    directory = os.environ.get('H_EFFECT_DIRECTORY')\n"
            "    if directory:\n"
            "        task = request['task_id']\n"
            "        if task not in ('retention-one', 'retention-two'):\n"
            "            raise ValueError('unregistered retention task')\n"
            "        os.environ['H_RETAINED_PATH'] = str(Path(directory) / (task + '.json'))\n")
        after = (
            "    if directory and request['task_id'] == 'retention-one':\n"
            "        with Path(os.environ['H_READY_PATH']).open('x', encoding='utf-8') as stream:\n"
            "            stream.write('ready\\n')\n"
            "        if os.environ.get('H_HOLD') == '1':\n"
            "            import time\n"
            "            deadline = time.monotonic() + 15\n"
            "            release = Path(os.environ['H_RELEASE_PATH'])\n"
            "            while not release.exists() and time.monotonic() < deadline:\n"
            "                time.sleep(.02)\n"
            "            if not release.exists():\n"
            "                raise TimeoutError('retention_release_timeout')\n")
        source.write_text(original.replace(marker, before + marker + after), encoding='utf-8')
    elif installed:
        original = source.read_text(encoding='utf-8')
        marker = "    STATE['kept'] = retention_consumer.commit(request, action)\n"
        assert original.count(marker) == 1
        ready = (
            "    import os\n"
            "    ready_path = os.environ.get('H_READY_PATH')\n"
            "    if ready_path:\n"
            "        from pathlib import Path\n"
            "        with Path(ready_path).open('x', encoding='utf-8') as stream:\n"
            "            stream.write('ready\\n')\n"
            "        import time\n"
            "        time.sleep(15)\n"
        )
        source.write_text(original.replace(marker, marker + ready), encoding='utf-8')
    requests = (
        'def make_requests():\n'
        "    command = os.environ['H_COMMAND']\n"
        "    base = {'task_id': 'retention-task', 'command': command}\n"
        "    mode = os.environ.get('H_REQUEST_SCENARIO', 'normal')\n"
        "    if mode == 'duplicate':\n"
        "        return [base, dict(base)]\n"
        "    if mode == 'budget':\n"
        "        proposed = [base, {**base, 'task_id': 'other-task'}]\n"
        "        if len(proposed) > limits()['max_tasks']:\n"
        "            raise ValueError('retention task budget refused')\n"
        "        return proposed\n"
        "    return [base]\n"
    ) if installed else (
        'def make_requests():\n'
        "    return [{'task_id': 'retention-task', 'command': os.environ['H_COMMAND']}]\n"
    )
    if connected_loader is not None:
        requests = (
            'def make_requests():\n'
            "    command = os.environ['H_COMMAND']\n"
            "    mode = os.environ.get('H_TASKS', 'two')\n"
            "    if mode not in ('two', 'duplicate'):\n"
            "        raise ValueError('unregistered retention task schedule')\n"
            "    ids = ('retention-one', 'retention-one') if mode == 'duplicate' else ('retention-one', 'retention-two')\n"
            "    return [{'task_id': task, 'command': command} for task in ids]\n")
    console = target / 'retention_host/console.py'
    console.write_text(
        f'from .{source.stem} import {entry}\n'
        'from pathlib import Path\nimport hashlib\nimport os\n'
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
        'def options():\n    return {}\n' +
        requests +
        'def main():\n'
        '    requests = make_requests()\n'
        '    for request in requests:\n'
        f'        {entry}(request)\n'
        '    return 0\n'
        "if __name__ == '__main__':\n    raise SystemExit(main())\n",
        encoding='utf-8')
    if connected_loader is not None:
        raw = console.read_text(encoding='utf-8')
        raw = raw.replace('import hashlib\nimport os\n',
                          'import hashlib\nimport os\nimport json\nimport threading\n')
        old_audit = ('    def __init__(self): self.records = []\n'
                     '    def append(self, record): self.records.append(record)\n')
        new_audit = '''    def __init__(self):
        self.records = []
        self.lock = threading.Lock()
    def append(self, record):
        self.records.append(record)
        if record.get('type') == 'assessment_error' and record.get('error_class') == 'EvaluationTimeoutError':
            directory = os.environ.get('H_EFFECT_DIRECTORY')
            if directory:
                path = Path(directory) / 'timeout-events.jsonl'
                raw = (json.dumps(dict(type='assessment_error', error_class='EvaluationTimeoutError'), sort_keys=True) + '\n').encode()
                with self.lock:
                    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(descriptor, 'ab') as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
'''
        assert raw.count(old_audit) == 1
        raw = raw.replace(old_audit, new_audit)
        raw = raw.replace('max_tasks=1)', 'max_tasks=2)')
        raw = raw.replace('def options():\n    return {}\n',
                          'def options():\n    from . import connected_authority\n    return connected_authority.options()\n')
        console.write_text(raw, encoding='utf-8')
    runtime_files = {
        'requirements.lock': ('dependency_lock', 'jev-integration-evaluator==1.3.0.dev1\n',
                              'jev-integration-evaluator==1.3.0.dev12\n'),
        'runtime.json': ('configuration', '{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
                         '{"jev_runtime":{"mode":"off","credential_ref":null,"feature_flag":false}}\n'),
    }
    for name, (kind, old, new) in runtime_files.items():
        path = target / 'retention_host' / name
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
        '[tool.setuptools.package-data]\nretention_host = ["*.lock", "*.json"]\n',
        encoding='utf-8')
    cfg = load_config()
    cfg['repository']['typescript_ast'] = False
    inventory = scan_repo(target, cfg)
    candidate = next(row for row in inventory['candidates']
                     if row['source']['symbol'] == 'select_boundary_retention_consumer')
    reason = ('Reviewed H host preserves pinned source items and explicit choice; '
              'the code-owned consumer rejects /compact and checks raw retention')
    apply_reviews(inventory, {candidate['candidate_id']: {
        'source_sha256': candidate['source']['source_sha256'], 'approved': True,
        'reviewer': 'offline-retention-bind-author', 'reason': reason}}, cfg)
    spec['candidate_id'] = candidate['candidate_id']
    spec['experiment_id'] = candidate['recommended_experiment']['id']
    spec['source'].update({'file_sha256': candidate['source']['file_sha256'],
                           'source_sha256': candidate['source']['source_sha256']})
    spec['binding_review'].update({'source_sha256': candidate['source']['source_sha256'],
                                   'reason': reason})
    for name, (kind, old, _) in runtime_files.items():
        inventory['configuration_evidence'].append({
            'file': 'retention_host/' + name,
            'sha256': hashlib.sha256(old.encode()).hexdigest()})
    inventory['analysis_identity']['configuration_digest'] = digest(inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    spec['inventory_sha256'] = digest(inventory)
    spec['inventory_fingerprint'] = inventory['scan_fingerprint']
    request['reviewed_inventory'] = inventory
    return inventory, spec, request


def test_h_template_bind_source_drift_and_unsupported_shape(tmp_path):
    target = tmp_path / 'host'
    _, spec, request = _bound_host(target)
    prepared = prepare_template_binding(target, request, BINDING)
    entry = prepared['request']['implementation_spec']['entrypoint_binding']
    assert entry['kind'] == 'task-loop-v1'
    assert entry['file'] == 'retention_host/console.py'
    assert entry['pyproject_sha256'] == file_hash(target / 'pyproject.toml')
    assert validate_template_request(target, prepared['request'])['status'] == 'validated'
    output = tmp_path / 'bound'
    report = bind_template(target, request, BINDING, output)
    assert report['request_sha256'] == digest(prepared['request'])
    assert json.loads((output / 'template-request.json').read_text()) == prepared['request']
    request_path, binding_path = tmp_path / 'request.json', tmp_path / 'binding.json'
    request_path.write_text(json.dumps(request), encoding='utf-8')
    binding_path.write_text(json.dumps(BINDING), encoding='utf-8')
    cli_output = tmp_path / 'bound-by-cli'
    cli_env = os.environ.copy()
    if Path(evaluator_package.__file__).resolve().is_relative_to(ROOT):
        cli_env['PYTHONPATH'] = str(ROOT)
    else:
        cli_env.pop('PYTHONPATH', None)
    cli = subprocess.run([sys.executable, '-m', 'jev_integration_evaluator',
        'template', 'bind', '--repo', str(target), '--request', str(request_path),
        '--binding', str(binding_path), '--out', str(cli_output)],
        cwd=tmp_path, env=cli_env, capture_output=True, text=True, timeout=30)
    assert cli.returncode == 0, cli.stderr
    assert json.loads((cli_output / 'binding-report.json').read_text()) == prepared['binding_report']
    assert json.loads((cli_output / 'template-request.json').read_text()) == prepared['request']
    console = target / entry['file']
    original = console.read_bytes()
    console.write_bytes(original + b'\n# unreviewed caller\n')
    with pytest.raises(InputError, match='drift|changed'):
        validate_template_request(target, prepared['request'])
    console.write_bytes(original)
    single = original.decode().replace(
        '    requests = make_requests()\n    for request in requests:\n'
        f'        {spec["verification"]["entry_point"]}(request)\n    return 0\n',
        '    request = make_requests()\n'
        f'    return {spec["verification"]["entry_point"]}(request)\n')
    assert single != original.decode()
    console.write_text(single, encoding='utf-8')
    with pytest.raises(UnsupportedShape, match='bounded explicit request loop'):
        prepare_template_binding(target, request, BINDING)


def test_h_bound_installed_normal_console_choice_and_raw_effect(tmp_path):
    wheelhouse_name = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not wheelhouse_name:
        pytest.skip('exact private offline wheelhouse required')
    wheelhouse = Path(wheelhouse_name).resolve(strict=True)
    target = tmp_path / 'host'
    inventory, _, request = _bound_host(target)
    prepared = prepare_template_binding(target, request, BINDING)
    bound = prepared['request']
    spec = bound['implementation_spec']
    assert validate_template_request(target, bound)['status'] == 'validated'
    template = tmp_path / 'template'
    materialize_template(target, bound, template)
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, inventory, spec['candidate_id'], spec, bundle)
    with pytest.MonkeyPatch.context() as env:
        env.setenv('H_RETAINED_PATH', _probe_effect_path(tmp_path, 'probe'))
        baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'baseline_passed'
        applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                       baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(target, bundle, 'modified',
            approve_execution=True, baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    assert implementation_status(target, bundle,
        trusted_receipt_sha256=modified['receipt_sha256'])['status'] == 'verified'
    wheels = sorted(wheelhouse.glob('*.whl'))
    rows = [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels]
    requirements = [{'name': name, 'version': version, 'wheel': path.name,
                     'sha256': file_hash(path)}
                    for path in wheels for name, version in [_metadata(path)]]
    environments = tmp_path / 'environments'
    environments.mkdir(mode=0o700)
    configuration = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    package_request = {
        'schema_version': '1.0', 'host_root': str(target),
        'implementation_bundle': str(bundle),
        'trusted_modified_receipt_sha256': modified['receipt_sha256'],
        'template_directory': str(template),
        'reviewed_package_source_sha256': digest(installer._tree(target)),
        'reviewed_configuration_sha256': digest(configuration),
        'interpreter': sys.executable,
        'build_tools': {name: importlib.metadata.version(name)
                        for name in ('pip', 'setuptools', 'wheel')},
        'wheelhouse': str(wheelhouse), 'wheels': rows, 'requirements': requirements,
        'package_directory': str(tmp_path / 'package'),
        'environment_parent': str(environments), 'console_script': 'retention-host',
        'configuration': configuration, 'secret_references': {}}
    package_plan = installer.plan_package(package_request)
    package_receipt = installer.build_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_install(package_plan, package_receipt)
    installed = installer.install_package(install_plan,
        approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'
    environment = Path(installed['environment'])
    script = environment / 'venv/bin/retention-host'
    origin = Path(installed['installed']['entrypoint_origin'])
    assert origin == environment / 'venv/lib/python3.13/site-packages/retention_host/console.py'
    assert origin.is_file() and not origin.is_symlink()
    assert script.is_file() and str(script) == installed['installed']['console_script']
    assert b'start_jev_runtime' in origin.read_bytes()
    effects = tmp_path / 'effects'
    effects.mkdir(mode=0o700)
    clean = {'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path), 'LANG': 'C.UTF-8',
             'JEV_RUNTIME_MODE': 'off', 'H_COMMAND': '/prune',
             'H_RETAINED_PATH': str(effects / 'retained.json')}
    result = subprocess.run([str(script)], cwd=tmp_path, env=clean,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    raw = (effects / 'retained.json').read_bytes()
    items = json.loads(raw)
    assert [item['id'] for item in items] == ['pinned', 'work', 'old']
    assert items[0]['byte_sha256'] == hashlib.sha256(b'region east').hexdigest()
    assert items[0]['source_ref'] == 'reviewed-one'
    blocked_effect = effects / 'blocked.json'
    blocked = subprocess.run([str(script)], cwd=tmp_path,
        env={**clean, 'H_COMMAND': '/compact', 'H_RETAINED_PATH': str(blocked_effect)},
        capture_output=True, text=True, timeout=30)
    assert blocked.returncode != 0 and not blocked_effect.exists()
    missing = subprocess.run([str(script)], cwd=tmp_path,
        env={key: value for key, value in {**clean, 'H_RETAINED_PATH': str(effects / 'missing.json')}.items()
             if key != 'H_COMMAND'}, capture_output=True, text=True, timeout=30)
    assert missing.returncode != 0 and not (effects / 'missing.json').exists()
    assert rollback_implementation(target, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
    assert file_hash(target / spec['entrypoint_binding']['file']) == spec['entrypoint_binding']['file_sha256']
