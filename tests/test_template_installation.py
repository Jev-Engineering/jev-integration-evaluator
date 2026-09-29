"""Offline installed host qualification for the declared Linux CPython 3.13 profile."""
from __future__ import annotations

from email.parser import BytesParser
from contextlib import redirect_stdout
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import zipfile

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash, read_json, write_json
from jev_integration_evaluator.cli import main as cli_main
from jev_integration_evaluator.integrations.lifecycle import apply_implementation, plan_implementation
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.template_catalog import materialize_template
from jev_integration_evaluator import template_installation as installer
from scripts.implementation_fixtures import fixture


pytestmark = pytest.mark.skipif(
    not (sys.platform == 'linux' and platform.machine().lower() == 'x86_64'
         and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13)),
    reason='Installed profile is Linux x86-64 CPython 3.13 only')
ROOT = Path(__file__).resolve().parents[1]


def _metadata(path):
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))
        data = BytesParser().parsebytes(archive.read(name))
        return data['Name'], data['Version']


def _prepared(tmp_path):
    host = tmp_path / 'host'
    inventory, spec = fixture(host, 'C', tag='package_install')
    (host / 'host_cli.py').write_text(
        'import json\nfrom jev_integration_evaluator.template_catalog import list_templates\n'
        'def main():\n    print(json.dumps({"entrypoint_reached": True, '
        '"template_count": len(list_templates()["templates"])}))\n    return 0\n', encoding='utf-8')
    tools = {name: importlib.metadata.version(name) for name in ('pip', 'setuptools', 'wheel')}
    modules = ['host_cli', Path(spec['source']['file']).stem, spec['output']['module']]
    (host / 'pyproject.toml').write_text(
        '[build-system]\nrequires = ["setuptools==' + tools['setuptools'] + '", "wheel==' +
        tools['wheel'] + '"]\nbuild-backend = "setuptools.build_meta"\n'
        '[project]\nname = "jev-synthetic-host"\nversion = "0.1.0"\n'
        'requires-python = ">=3.13"\ndependencies = ["jev-integration-evaluator==1.3.0.dev12"]\n'
        '[project.scripts]\nsynthetic-host = "host_cli:main"\n'
        '[tool.setuptools]\npy-modules = ' + json.dumps(modules) + '\n', encoding='utf-8')
    request = {'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
               'template_version': '1.0.0', 'backend': 'python', 'profile': 'module-tail-call-v1',
               'reviewed_inventory': inventory, 'implementation_spec': spec}
    template = tmp_path / 'template'
    materialize_template(host, request, template)
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(host, inventory, spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(host, bundle, 'baseline', approve_execution=True)
    apply_implementation(host, bundle, planned['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(host, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    if not os.environ.get('JEV_TEMPLATE_WHEELHOUSE'):
        pytest.skip('Explicitly prepared offline template wheelhouse required')
    wheelhouse = Path(os.environ['JEV_TEMPLATE_WHEELHOUSE']).resolve()
    assert wheelhouse.is_dir()
    wheels = sorted(wheelhouse.glob('*.whl'))
    rows = [{'filename': p.name, 'sha256': file_hash(p)} for p in wheels]
    reqs = [{'name': name, 'version': version, 'wheel': p.name, 'sha256': file_hash(p)}
            for p in wheels for name, version in [_metadata(p)]]
    envs = tmp_path / 'environments'; envs.mkdir(mode=0o700)
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': 'env:TYPESAFE_API_KEY'}}
    package_request = {
        'schema_version': '1.0', 'host_root': str(host), 'implementation_bundle': str(bundle),
        'trusted_modified_receipt_sha256': modified['receipt_sha256'],
        'template_directory': str(template), 'interpreter': sys.executable,
        'reviewed_package_source_sha256': digest(installer._tree(host)),
        'reviewed_configuration_sha256': digest(config),
        'wheelhouse': str(wheelhouse), 'package_directory': str(tmp_path / 'package'),
        'environment_parent': str(envs), 'console_script': 'synthetic-host',
        'build_tools': tools, 'wheels': rows, 'requirements': reqs,
        'configuration': config, 'secret_references': {'credential': 'env:TYPESAFE_API_KEY'},
    }
    return package_request


def test_clean_installed_host_and_repeated_installation(tmp_path, monkeypatch):
    request = _prepared(tmp_path)
    package_plan = installer.plan_package(request)
    missing_ref = dict(request); missing_ref['secret_references'] = {}
    with pytest.raises(InputError, match='configuration_secret_reference_mismatch'):
        installer.plan_package(missing_ref)
    wrong_ref = dict(request); wrong_ref['secret_references'] = {'credential': 'env:OTHER'}
    with pytest.raises(InputError, match='configuration_secret_reference_mismatch'):
        installer.plan_package(wrong_ref)
    unsafe_script = dict(request); unsafe_script['console_script'] = '../synthetic-host'
    with pytest.raises(InputError, match='console_script_name_invalid'):
        installer.plan_package(unsafe_script)
    missing_interpreter = dict(request); missing_interpreter['interpreter'] = '/missing/python3.13'
    with pytest.raises(InputError, match='interpreter_must_match_planner'):
        installer.plan_package(missing_interpreter)
    drifted_wheels = dict(request); drifted_wheels['wheels'] = [dict(row) for row in request['wheels']]
    drifted_wheels['wheels'][0]['sha256'] = '0' * 64
    with pytest.raises(InputError, match='wheel_hash_drift'):
        installer.plan_package(drifted_wheels)
    Path(request['package_directory']).mkdir()
    with pytest.raises(InputError, match='package_ownership_mismatch'):
        installer.build_package(package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    Path(request['package_directory']).rmdir()
    write_json(tmp_path / 'package-request.json', request)
    with redirect_stdout(io.StringIO()):
        assert cli_main(['template', 'package', '--request', str(tmp_path / 'package-request.json'),
                         '--out', str(tmp_path / 'package-plan.json')]) == 0
    assert read_json(tmp_path / 'package-plan.json') == package_plan
    real_record = installer._record
    def interrupt_completion(root, plan_sha256, event):
        if event == 'build_completed':
            raise KeyboardInterrupt('receipt written before completion event')
        return real_record(root, plan_sha256, event)
    monkeypatch.setattr(installer, '_record', interrupt_completion)
    with pytest.raises(KeyboardInterrupt):
        installer.build_package(package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    monkeypatch.setattr(installer, '_record', real_record)
    recovered = installer.recover_package(package_plan,
                                          approved_plan_sha256=package_plan['plan_sha256'])
    assert recovered['status'] == 'already_built'
    receipt = installer.build_package(package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    assert installer.build_package(package_plan, approved_plan_sha256=package_plan['plan_sha256']) == receipt
    assert installer._environment_parent(request) == Path(request['environment_parent'])
    install_plan = installer.plan_install(package_plan, receipt)
    from copy import deepcopy
    for overlapping in (request['host_root'], request['implementation_bundle'],
                        request['template_directory'], request['wheelhouse'],
                        request['package_directory']):
        altered = deepcopy(install_plan)
        altered['environment_parent'] = overlapping
        altered['plan_sha256'] = 'a' * 64
        with pytest.raises(InputError, match='environment_generation_overlap'):
            installer._check_environment_disjoint(altered)
    for colliding in (installer._environment(install_plan),
                      installer._environment(install_plan) / 'nested',
                      Path(request['environment_parent'])):
        altered = deepcopy(install_plan)
        altered['package_plan']['request']['wheelhouse'] = str(colliding)
        with pytest.raises(InputError, match='environment_generation_overlap'):
            installer._check_environment_disjoint(altered)
    write_json(tmp_path / 'package-receipt.json', receipt)
    with redirect_stdout(io.StringIO()):
        assert cli_main(['template', 'install-plan', '--package-plan', str(tmp_path / 'package-plan.json'),
                         '--package-receipt', str(tmp_path / 'package-receipt.json'),
                         '--out', str(tmp_path / 'install-plan.json')]) == 0
    assert read_json(tmp_path / 'install-plan.json') == install_plan
    def interrupt_install_completion(root, plan_sha256, event):
        if event == 'install_completed':
            raise KeyboardInterrupt('installed receipt written before completion event')
        return real_record(root, plan_sha256, event)
    monkeypatch.setattr(installer, '_record', interrupt_install_completion)
    with pytest.raises(KeyboardInterrupt):
        installer.install_package(install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    monkeypatch.setattr(installer, '_record', real_record)
    adopted = installer.recover_installation(install_plan,
                                             approved_plan_sha256=install_plan['plan_sha256'])
    assert adopted['status'] == 'already_installed'
    installed = installer.install_package(install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.install_package(install_plan, approved_plan_sha256=install_plan['plan_sha256']) == installed
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'
    interpreter_link = Path(installed['installed']['python'])
    pinned_target = os.readlink(interpreter_link)
    interpreter_link.unlink(); interpreter_link.symlink_to('/bin/sh')
    assert installer.installation_status(install_plan)['status'] == 'installed_drift'
    interpreter_link.unlink(); interpreter_link.symlink_to(pinned_target)
    command = Path(installed['installed']['console_script'])
    command_bytes, command_mode = command.read_bytes(), stat.S_IMODE(command.stat().st_mode)
    command.unlink(); command.symlink_to('/bin/true')
    assert installer.installation_status(install_plan)['status'] == 'installed_drift'
    command.unlink(); command.write_bytes(command_bytes); command.chmod(command_mode)
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'
    result = subprocess.run([installed['installed']['console_script']], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30,
                            env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path)})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'entrypoint_reached': True, 'template_count': 1}
    assert installed['mode'] == 'off' and installed['provider_reachable'] is False
    origin = subprocess.run([installed['installed']['python'], '-I', '-c',
                             'import jev_integration_evaluator as j;print(j.__file__)'],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30,
                            env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path)})
    assert origin.returncode == 0
    assert Path(origin.stdout.strip()).resolve().is_relative_to(Path(installed['environment']) / 'venv')

    # A fresh approved configuration produces a new generation and retains the
    # first verified environment for the later delivery supervisor's rollback.
    next_request = dict(request)
    next_request['configuration'] = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    next_request['reviewed_configuration_sha256'] = digest(next_request['configuration'])
    next_request['secret_references'] = {}
    next_request['package_directory'] = str(tmp_path / 'package-next')
    next_package_plan = installer.plan_package(next_request)
    next_receipt = installer.build_package(next_package_plan,
                                           approved_plan_sha256=next_package_plan['plan_sha256'])
    next_plan = installer.plan_install(next_package_plan, next_receipt)
    next_installed = installer.install_package(next_plan,
                                               approved_plan_sha256=next_plan['plan_sha256'])
    assert next_installed['environment'] != installed['environment']
    assert Path(installed['environment']).is_dir()
    assert installer.installation_status(install_plan)['status'] == 'installed_recorded'


@pytest.mark.parametrize('interrupt_call', [2, 3])
def test_drift_and_partial_install_recovery_preserve_unrelated(tmp_path, monkeypatch, interrupt_call):
    request = _prepared(tmp_path)
    package_plan = installer.plan_package(request)
    receipt = installer.build_package(package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_install(package_plan, receipt)
    unrelated = Path(request['environment_parent']) / 'unrelated.txt'
    unrelated.write_text('preserve', encoding='utf-8')
    real_run = installer._run
    calls = []
    def interrupt_install(args, *, cwd, timeout=180):
        calls.append(args)
        if len(calls) == interrupt_call:
            raise KeyboardInterrupt('synthetic interruption at reviewed install phase')
        return real_run(args, cwd=cwd, timeout=timeout)
    monkeypatch.setattr(installer, '_run', interrupt_install)
    with pytest.raises(KeyboardInterrupt):
        installer.install_package(install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan)['status'] == 'interrupted_recovery_required'
    with pytest.raises(InputError, match='install_interrupted'):
        installer.install_package(install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    generation_sha256 = installer.installation_status(install_plan)['generation_sha256']
    assert installer.recover_installation(install_plan, approved_plan_sha256=install_plan['plan_sha256'],
                                          approved_generation_sha256=generation_sha256)['status'] == 'owned_incomplete_generation_removed'
    assert unrelated.read_text(encoding='utf-8') == 'preserve'
    root = installer._environment(install_plan)
    root.symlink_to(Path(request['environment_parent']))
    with pytest.raises(InputError, match='environment_ownership_mismatch'):
        installer.install_package(install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    root.unlink()
    monkeypatch.setattr(installer, '_run', real_run)
    installed = installer.install_package(install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert installed['mode'] == 'off'
    changed = dict(request)
    changed['reviewed_configuration_sha256'] = '0' * 64
    with pytest.raises(InputError, match='reviewed_configuration_drift'):
        installer.plan_package(changed, _allow_existing_output=True)


def test_partial_build_needs_exact_generation_review(tmp_path, monkeypatch):
    request = _prepared(tmp_path)
    plan = installer.plan_package(request)
    unrelated = tmp_path / 'unrelated.txt'; unrelated.write_text('keep', encoding='utf-8')
    real_run = installer._run
    def interrupt_build(args, *, cwd, timeout=180):
        raise KeyboardInterrupt('synthetic interruption during build hook')
    monkeypatch.setattr(installer, '_run', interrupt_build)
    with pytest.raises(KeyboardInterrupt):
        installer.build_package(plan, approved_plan_sha256=plan['plan_sha256'])
    with pytest.raises(InputError, match='build_interrupted'):
        installer.build_package(plan, approved_plan_sha256=plan['plan_sha256'])
    with pytest.raises(InputError, match='exact_generation_review_required'):
        installer.recover_package(plan, approved_plan_sha256=plan['plan_sha256'])
    snapshot = installer._owned_tree(Path(request['package_directory']), python=Path(sys.executable))
    result = installer.recover_package(plan, approved_plan_sha256=plan['plan_sha256'],
                                       approved_generation_sha256=snapshot)
    assert result['status'] == 'owned_incomplete_package_removed'
    assert unrelated.read_text(encoding='utf-8') == 'keep'
    monkeypatch.setattr(installer, '_run', real_run)
    assert installer.build_package(plan, approved_plan_sha256=plan['plan_sha256'])['source_sha256'] == plan['source_sha256']
    after_build_request = dict(request)
    after_build_request['package_directory'] = str(tmp_path / 'package-after-build')
    after_build_plan = installer.plan_package(after_build_request)
    real_write = installer.write_json
    def interrupt_receipt(path, value):
        if Path(path).name == 'package-receipt.json':
            raise KeyboardInterrupt('wheel built before receipt write')
        return real_write(path, value)
    monkeypatch.setattr(installer, 'write_json', interrupt_receipt)
    with pytest.raises(KeyboardInterrupt):
        installer.build_package(after_build_plan, approved_plan_sha256=after_build_plan['plan_sha256'])
    monkeypatch.setattr(installer, 'write_json', real_write)
    assert installer.package_status(after_build_plan)['status'] == 'interrupted_recovery_required'
    generation = installer.package_status(after_build_plan)['generation_sha256']
    assert installer.recover_package(after_build_plan, approved_plan_sha256=after_build_plan['plan_sha256'],
                                     approved_generation_sha256=generation)['status'] == 'owned_incomplete_package_removed'
    assert installer.build_package(after_build_plan,
                                   approved_plan_sha256=after_build_plan['plan_sha256'])['source_sha256'] == plan['source_sha256']
