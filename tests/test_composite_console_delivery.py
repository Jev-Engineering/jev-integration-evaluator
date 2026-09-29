"""A source-bound two-placement console plan from two independently reviewed seams."""
from __future__ import annotations

import copy
from email.parser import BytesParser
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

import pytest

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.integrations.composite import (
    apply_composite, plan_composite, verify_composite)
from jev_integration_evaluator.integrations.python_entrypoint import inspect_entrypoint
from jev_integration_evaluator.io import digest, file_hash, read_json
from jev_integration_evaluator.template_catalog import materialize_template
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from scripts.implementation_fixtures import fixture


pytestmark = pytest.mark.skipif(
    not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
         and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)),
    reason='Composite installed console profile requires Linux x86-64 CPython 3.13')


def _prepared(tmp_path, *, fail_second=False, delivery_effects=False):
    root = tmp_path / 'host'
    _, first = fixture(root, 'C', tag='one', layout='package',
                       package_name='coupled_pkg', console_exit=True,
                       effect_sink=delivery_effects)
    _, second = fixture(root, 'C', tag='two', layout='package',
                        package_name='coupled_pkg', console_exit=True,
                        effect_sink=delivery_effects)
    package = root / 'coupled_pkg'
    if fail_second:
        source = package / 'host_two.py'
        body = source.read_text(encoding='utf-8')
        body = body.replace('from threading import RLock\n',
                            'from threading import RLock\nimport os\n')
        original = "def perform_primary_two(request):\n"
        changed = ('def perform_primary_two(request):\n'
                   '    if os.environ.get("JEV_TEST_FAIL_SECOND") == "1":\n'
                   '        raise RuntimeError("second_placement_failed")\n')
        assert original in body
        source.write_text(body.replace(original, changed), encoding='utf-8')
    build_tools = {name: importlib.metadata.version(name) for name in ('pip', 'setuptools', 'wheel')}
    (root / 'pyproject.toml').write_text(
        '[build-system]\nrequires = ["setuptools==' + build_tools['setuptools']
        + '", "wheel==' + build_tools['wheel'] + '"]\n'
        'build-backend = "setuptools.build_meta"\n[project]\n'
        'name = "coupled-host"\nversion = "1.0.0"\n'
        'dependencies = ["jev-integration-evaluator==1.3.0.dev12"]\n'
        '[project.scripts]\ncombined-host = "coupled_pkg.console:main_one"\n'
        'second-host = "coupled_pkg.console:main_two"\n'
        '[tool.setuptools.package-data]\ncoupled_pkg = ["*.lock", "*.json"]\n',
        encoding='utf-8')
    (package / 'console.py').write_text('''from .host_one import public_entry_one
from .host_two import public_entry_two
from pathlib import Path
import hashlib
import json
import os

EVENTS = []
COMPOSITE_OBSERVATION = {}

class Audit:
    def append(self, record):
        EVENTS.append(record)

def limits_one():
    return dict(max_calls_per_task=2, max_cost_per_task=2, max_total_calls=2,
                max_total_cost=2, max_in_flight=1, max_tasks=1)

def limits_two():
    return limits_one()

def audit_one():
    return Audit()

def audit_two():
    return Audit()

def dependencies_one():
    base = Path(__file__).resolve().parent
    return {'files': [{'path': str(base / name),
                       'sha256': hashlib.sha256((base / name).read_bytes()).hexdigest()}
                      for name in ('requirements.lock', 'runtime.json')]}

def dependencies_two():
    return dependencies_one()

def options_one():
    import os
    if os.environ.get('JEV_TEST_SHADOW') != '1':
        return {}
    from jev_integration_evaluator.integrations.probe import SyntheticClient
    return {'startup_mode': 'shadow', 'client': SyntheticClient('alternative'),
            'enable_experiment': True}

def options_two():
    return options_one()

def observe_composite_runtime(runtime, request, candidate_ids):
    routers = [runtime.router(candidate, request) for candidate in candidate_ids]
    snapshot = runtime.coordinator.snapshot()
    COMPOSITE_OBSERVATION.update({
        'tokens': [str(id(router.budget_coordinator)) for router in routers],
        'scopes': [router.canary_scope for router in routers],
        'calls': snapshot['calls'], 'cost': snapshot['reserved_cost']})

def make_one():
    if os.environ.get('DELIVERY_AUDIT_PATH'):
        import atexit
        atexit.register(_delivery_audit)
    return {'task_id': 'shared-task', 'objective': 'offline fixture', 'command': '/prune'}

def make_two():
    return make_one()

def main_one():
    request = make_one()
    return public_entry_one(request)

def main_two():
    request = make_two()
    return public_entry_two(request)

def _delivery_audit():
    path = os.environ.get('DELIVERY_AUDIT_PATH')
    if not path:
        return
    from . import host_one, host_two
    assessments = [row for row in EVENTS if row.get('type') == 'assessment']
    Path(path).write_text(json.dumps({
        'assessed': [row['candidate_id'] for row in assessments],
        'task_hashes': [row['task_id_hash'] for row in assessments],
        'modes': [row['mode'] for row in assessments],
        'tokens': COMPOSITE_OBSERVATION.get('tokens', []),
        'calls': COMPOSITE_OBSERVATION.get('calls'),
        'one': host_one.STATE['effects'],
        'two': host_two.STATE['effects'],
    }), encoding='utf-8')
''', encoding='utf-8')
    runtime = {
        'requirements.lock': ('dependency_lock', 'jev-integration-evaluator==1.3.0.dev1\n',
                              'jev-integration-evaluator==1.3.0.dev12\n'),
        'runtime.json': ('configuration', '{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
                         '{"jev_runtime":{"mode":"off","credential_ref":"env:TYPESAFE_API_KEY"}}\n'),
    }
    for name, (_, old, _) in runtime.items():
        (package / name).write_text(old, encoding='utf-8')
    cfg = load_config(); cfg['repository']['typescript_ast'] = False
    inventory = scan_repo(root, cfg)
    chosen = {}
    for spec in (first, second):
        matching = [candidate for candidate in inventory['candidates']
                    if candidate['source']['symbol'] == spec['source']['symbol']]
        assert len(matching) == 1
        chosen[spec['source']['symbol']] = matching[0]
    apply_reviews(inventory, {
        candidate['candidate_id']: {'source_sha256': candidate['source']['source_sha256'],
            'approved': True, 'reviewer': 'synthetic-composite-test-author',
            'reason': 'Reviewed exact finite fixture source'}
        for candidate in chosen.values()}, cfg)
    for name, (_, old, _) in runtime.items():
        inventory['configuration_evidence'].append({
            'file': 'coupled_pkg/' + name, 'sha256': hashlib.sha256(old.encode()).hexdigest()})
    inventory['analysis_identity']['configuration_digest'] = digest(inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    specs = {}
    for source_spec, tag, script in ((first, 'one', 'combined-host'),
                                      (second, 'two', 'second-host')):
        spec = copy.deepcopy(source_spec)
        candidate = chosen[spec['source']['symbol']]
        spec.update(candidate_id=candidate['candidate_id'],
                    experiment_id=candidate['recommended_experiment']['id'],
                    inventory_sha256=digest(inventory),
                    inventory_fingerprint=inventory['scan_fingerprint'])
        spec['source'].update(file_sha256=candidate['source']['file_sha256'],
                              source_sha256=candidate['source']['source_sha256'])
        spec['binding_review']['source_sha256'] = candidate['source']['source_sha256']
        spec['runtime']['canary_scope'] = 'same-reviewed-workflow'
        spec['runtime']['configuration']['max_calls_per_task'] = 2
        spec['runtime']['configuration']['max_cost_per_task'] = 2
        spec['host_lifecycle'] = {'kind': 'module-startup-v1',
                                  'startup': 'start_jev_runtime',
                                  'shutdown': 'stop_jev_runtime',
                                  'complete_task': 'finish_jev_task'}
        spec['runtime_files'] = []
        for name, (kind, old, new) in runtime.items():
            rel = 'coupled_pkg/' + name
            spec['runtime_files'].append({'file': rel, 'kind': kind,
                'old_sha256': hashlib.sha256(old.encode()).hexdigest(),
                'new_content': new})
            spec['output']['permitted_edits'].append(rel)
        spec['output']['permitted_edits'].append('coupled_pkg/console.py')
        binding = {'version': '1.0', 'script': script,
                   'startup_inputs': {'budget_limits': 'limits_' + tag,
                                      'audit_log': 'audit_' + tag,
                                      'dependency_plan': 'dependencies_' + tag,
                                      'startup_options': 'options_' + tag}}
        spec['entrypoint_binding'] = inspect_entrypoint(root, spec, binding)
        specs[spec['candidate_id']] = spec
    ids = sorted(specs)
    selection = {'schema_version': 'composite-selection-v1', 'candidate_ids': ids,
        'dependencies': [], 'conflicts': [],
        'shared_runtime': {'task_field': 'task_id', 'policy_version': 'fixture-v1',
            'canary_scope': 'same-reviewed-workflow',
            'max_calls_per_task': 2, 'max_cost_per_task': 2},
        'combined_verification': {'command': [sys.executable, '-V'],
            'shared_task_id': 'shared-task',
            'expected_results': {identifier: 0 for identifier in ids}}}
    primary_function = specs[ids[0]]['entrypoint_binding']['function']
    bootstrap = ('import json,os,sys;os.environ["JEV_TEST_SHADOW"]="1";sys.path.insert(0,'
                 + repr(str(Path(__file__).resolve().parents[1])) + ');'
                 'sys.path.insert(0,os.getcwd());'
                 'from coupled_pkg import console,host_one,host_two;'
                 'result=getattr(console,' + repr(primary_function) + ')();'
                 'assert result==0 and host_one.STATE["effects"]==["first"] '
                 'and host_two.STATE["effects"]==["first"];'
                 'observed=console.COMPOSITE_OBSERVATION;'
                 'assessed=sorted(row["candidate_id"] for row in console.EVENTS '
                 'if row.get("type")=="assessment");'
                 'assert assessed==' + repr(ids) + ';'
                 'print(json.dumps({"schema_version":"composite-host-observation-v1",'
                 '"candidate_ids":' + repr(ids) + ',"task_id":"shared-task",'
                 '"coordinator_tokens":observed["tokens"],'
                 '"canary_scopes":observed["scopes"],'
                 '"assessment_calls":observed["calls"],'
                 '"total_cost":observed["cost"],'
                 '"audit_candidate_ids":assessed,'
                 '"results":' + repr({identifier: 0 for identifier in ids}) + '}))')
    selection['combined_verification']['command'] = [sys.executable, '-I', '-c', bootstrap]
    return root, inventory, selection, specs


def test_two_reviewed_console_bindings_render_one_shared_runtime(tmp_path):
    root, inventory, selection, specs = _prepared(tmp_path, delivery_effects=True)
    bundle = tmp_path / 'bundle'
    planned = plan_composite(root, inventory, selection, specs, bundle)
    report = read_json(bundle / 'composite-console.json')
    patch = read_json(bundle / 'patch-plan.json')
    console = next(row['new_content'] for row in patch['changes']
                   if row['file'] == 'coupled_pkg/console.py')
    assert planned['status'] == 'planned'
    assert report['candidate_ids'] == selection['candidate_ids']
    assert report['script'] in {'combined-host', 'second-host'}
    assert console.count('HostRuntimeLifecycle(') == 1
    assert all('runtime_binding(' + repr(identifier) + ')' in console
               for identifier in selection['candidate_ids'])
    assert 'complete_task(' in console
    assert (root / 'coupled_pkg/console.py').read_text(encoding='utf-8') != console


def test_two_real_seams_run_from_one_normal_console_after_reviewed_apply(tmp_path):
    root, inventory, selection, specs = _prepared(tmp_path)
    bundle = tmp_path / 'bundle'
    plan = plan_composite(root, inventory, selection, specs, bundle)
    baseline = verify_composite(root, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    apply_composite(root, bundle, plan['bundle_digest'],
                    baseline_sha256=baseline['receipt_sha256'])
    report = read_json(bundle / 'composite-console.json')
    function = 'main_one' if report['script'] == 'combined-host' else 'main_two'
    code = ('import json; from coupled_pkg import console,host_one,host_two; '
            'result=getattr(console,' + repr(function) + ')(); '
            'assessments=[row for row in console.EVENTS if row.get("type")=="assessment"]; '
            'print(json.dumps({"result":result,"one":host_one.STATE["effects"],'
            '"two":host_two.STATE["effects"],"audit":len(console.EVENTS),'
            '"assessed":[row["candidate_id"] for row in assessments],'
            '"task_hashes":[row["task_id_hash"] for row in assessments],'
            '"modes":[row["mode"] for row in assessments]}))')
    parent = Path(__file__).resolve().parents[1]
    run = subprocess.run([sys.executable, '-c', code], cwd=root,
                         env={**os.environ, 'PYTHONPATH': str(parent), 'JEV_TEST_SHADOW': '1'},
                         capture_output=True, text=True, timeout=25)
    assert run.returncode == 0, run.stderr
    observed = json.loads(run.stdout)
    assert observed['result'] == 0
    # Shadow observes two real routing decisions while executing the baseline.
    assert observed['one'] == ['first']
    assert observed['two'] == ['first']
    assert sorted(observed['assessed']) == selection['candidate_ids']
    assert len(set(observed['task_hashes'])) == 1
    assert observed['modes'] == ['shadow', 'shadow']
    assert observed['audit'] >= 4
    modified = verify_composite(root, bundle, 'modified', approve_execution=True,
                                baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'


def test_verified_composite_builds_and_installs_one_owned_generation(tmp_path):
    if not os.environ.get('JEV_TEMPLATE_WHEELHOUSE'):
        pytest.skip('Explicitly prepared offline wheelhouse required')
    root, inventory, selection, specs = _prepared(tmp_path, fail_second=True,
                                                  delivery_effects=True)
    templates = {}
    for identifier, spec in specs.items():
        directory = tmp_path / ('template-' + identifier)
        request = {'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
                   'template_version': '1.0.0', 'backend': 'python',
                   'profile': 'module-tail-call-v1', 'reviewed_inventory': inventory,
                   'implementation_spec': spec}
        materialize_template(root, request, directory)
        templates[identifier] = str(directory)
    bundle = tmp_path / 'bundle'
    planned = plan_composite(root, inventory, selection, specs, bundle)
    baseline = verify_composite(root, bundle, 'baseline', approve_execution=True)
    apply_composite(root, bundle, planned['bundle_digest'],
                    baseline_sha256=baseline['receipt_sha256'])
    modified = verify_composite(root, bundle, 'modified', approve_execution=True,
                                baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    wheelhouse = Path(os.environ['JEV_TEMPLATE_WHEELHOUSE']).resolve()
    wheels = sorted(wheelhouse.glob('*.whl'))
    assert wheels
    def metadata(path):
        with zipfile.ZipFile(path) as archive:
            name = next(item for item in archive.namelist()
                        if item.endswith('.dist-info/METADATA'))
            record = BytesParser().parsebytes(archive.read(name))
            return record['Name'], record['Version']
    environment_parent = tmp_path / 'environments'
    environment_parent.mkdir(mode=0o700)
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    package_request = {
        'schema_version': '1.0', 'host_root': str(root),
        'implementation_bundle': str(bundle),
        'trusted_modified_receipt_sha256': modified['receipt_sha256'],
        'template_directories': templates,
        'reviewed_package_source_sha256': digest(installer._tree(root)),
        'reviewed_configuration_sha256': digest(config),
        'interpreter': sys.executable, 'wheelhouse': str(wheelhouse),
        'package_directory': str(tmp_path / 'package'),
        'environment_parent': str(environment_parent),
        'console_script': read_json(bundle / 'composite-console.json')['script'],
        'build_tools': {name: importlib.metadata.version(name)
                        for name in ('pip', 'setuptools', 'wheel')},
        'wheels': [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels],
        'requirements': [{'name': name, 'version': version,
                          'wheel': path.name, 'sha256': file_hash(path)}
                         for path in wheels for name, version in [metadata(path)]],
        'configuration': config, 'secret_references': {},
    }
    package_plan = installer.plan_composite_package(package_request)
    assert package_plan['candidate_ids'] == selection['candidate_ids']
    package_receipt = installer.build_composite_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_composite_install(package_plan, package_receipt)
    install_receipt = installer.install_composite_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert install_receipt['candidate_ids'] == selection['candidate_ids']
    assert installer.composite_installation_status(install_plan)['status'] == 'installed_recorded'
    command = install_receipt['installed']['console_script']
    audit = tmp_path / 'installed-audit.json'
    one = tmp_path / 'installed-effect-one.bin'
    two = tmp_path / 'installed-effect-two.bin'
    run = subprocess.run([command], cwd=tmp_path, capture_output=True, text=True,
                         timeout=25, env={**os.environ, 'JEV_TEST_SHADOW': '1',
                                          'DELIVERY_AUDIT_PATH': str(audit),
                                          'DELIVERY_EFFECT_PATH_ONE': str(one),
                                          'DELIVERY_EFFECT_PATH_TWO': str(two)})
    assert run.returncode == 0, run.stderr
    observed = json.loads(audit.read_text(encoding='utf-8'))
    assert sorted(observed['assessed']) == selection['candidate_ids']
    assert observed['modes'] == ['shadow', 'shadow']
    assert len(set(observed['task_hashes'])) == 1
    assert len(set(observed['tokens'])) == 1
    assert observed['calls'] == 2
    assert observed['one'] == observed['two'] == ['first']
    assert one.read_bytes() == two.read_bytes() == b'first\n'
    failed_one = tmp_path / 'failed-effect-one.bin'
    failed_two = tmp_path / 'failed-effect-two.bin'
    failed_audit = tmp_path / 'failed-audit.json'
    failed = subprocess.run([command], cwd=tmp_path, capture_output=True, text=True,
                            timeout=25, env={**os.environ, 'JEV_TEST_SHADOW': '1',
                                             'JEV_TEST_FAIL_SECOND': '1',
                                             'DELIVERY_AUDIT_PATH': str(failed_audit),
                                             'DELIVERY_EFFECT_PATH_ONE': str(failed_one),
                                             'DELIVERY_EFFECT_PATH_TWO': str(failed_two)})
    assert failed.returncode != 0
    assert failed_one.read_bytes() == b'first\n'
    assert not failed_two.exists()
    failure = json.loads(failed_audit.read_text(encoding='utf-8'))
    assert sorted(failure['assessed']) == selection['candidate_ids']
    assert len(set(failure['task_hashes'])) == 1
    assert installer.install_composite_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256']) == install_receipt
    assert installer.recover_composite_installation(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])['status'] == 'already_installed'
    receipt_path = Path(installer.composite_installation_status(install_plan)['environment']) / 'install-receipt.json'
    altered = read_json(receipt_path)
    altered['selected_set_digest'] = '0' * 64
    receipt_path.write_text(json.dumps(altered), encoding='utf-8')
    assert installer.composite_installation_status(install_plan)['status'] == 'installed_drift'


def test_second_placement_failure_keeps_first_effect_without_retry(tmp_path):
    root, inventory, selection, specs = _prepared(tmp_path, fail_second=True)
    bundle = tmp_path / 'bundle'
    plan = plan_composite(root, inventory, selection, specs, bundle)
    baseline = verify_composite(root, bundle, 'baseline', approve_execution=True)
    apply_composite(root, bundle, plan['bundle_digest'],
                    baseline_sha256=baseline['receipt_sha256'])
    report = read_json(bundle / 'composite-console.json')
    function = 'main_one' if report['script'] == 'combined-host' else 'main_two'
    code = ('import json\nfrom coupled_pkg import console,host_one,host_two\n'
            'error=None\n'
            'try:\n result=getattr(console,' + repr(function) + ')()\n'
            'except RuntimeError as exc:\n error=str(exc)\n'
            'print(json.dumps({"error":error,"one":host_one.STATE["effects"],'
            '"two":host_two.STATE["effects"]}))')
    run = subprocess.run([sys.executable, '-c', code], cwd=root,
                         env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
                              'JEV_TEST_SHADOW': '1', 'JEV_TEST_FAIL_SECOND': '1'},
                         capture_output=True, text=True, timeout=25)
    assert run.returncode == 0, run.stderr
    observed = json.loads(run.stdout)
    assert observed['error'] == 'second_placement_failed'
    assert observed['one'] == ['first']
    assert observed['two'] == []
