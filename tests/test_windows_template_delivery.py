"""Native installed console journey with private offline wheelhouse."""
from __future__ import annotations

from email.parser import BytesParser
import hashlib
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

import pytest

from jev_integration_evaluator.io import InputError, digest
from jev_integration_evaluator.template_catalog import (
    materialize_template, prepare_template_binding,
)
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.windows_template_plan import (
    build_windows_template_package, plan_windows_template_package,
    windows_package_status,
)
from jev_integration_evaluator.windows_template_install import (
    install_windows_template_package, plan_windows_template_install,
    windows_install_status,
)
from jev_integration_evaluator.windows_template_session import (
    create_windows_template_session, launch_windows_template_session,
    stop_windows_template_session, windows_session_status,
)
from test_template_python_entrypoint import _prepared


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='native Windows NTFS only')


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wheel_name(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        name = next(name for name in archive.namelist()
                    if name.endswith('.dist-info/METADATA'))
        return BytesParser().parsebytes(archive.read(name))['Name']


def _request(tmp_path):
    wheelhouse = os.environ.get('JEV_WINDOWS_TEMPLATE_WHEELHOUSE')
    if not wheelhouse:
        pytest.skip('Explicit native Windows offline wheelhouse required')
    wheelhouse = Path(wheelhouse)
    assert wheelhouse.is_dir()
    tools = {name: __import__('importlib').metadata.version(name)
             for name in ('setuptools', 'wheel')}
    target, template_request, binding = _prepared(tmp_path, tag='windows_delivery')
    project = target / 'pyproject.toml'
    project.write_text(project.read_text(encoding='utf-8').replace(
        'requires = ["setuptools>=68"]',
        'requires = ["setuptools==' + tools['setuptools'] + '", "wheel==' +
        tools['wheel'] + '"]'), encoding='utf-8')
    prepared = prepare_template_binding(target, template_request, binding)
    spec = prepared['request']['implementation_spec']
    template = tmp_path / 'template'
    materialize_template(target, prepared['request'], template)
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, template_request['reviewed_inventory'],
                                  spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                   baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    source_files = {p.relative_to(target).as_posix(): _hash(p) for p in target.rglob('*')
                    if p.is_file() and not any(part in
                    {'.git', '.pytest_cache', '__pycache__', 'build', 'dist'}
                    for part in p.relative_to(target).parts[:-1])}
    wheels = {p.name: _hash(p) for p in wheelhouse.glob('*.whl')}
    output = tmp_path / 'packages'; output.mkdir()
    environments = tmp_path / 'environments'; environments.mkdir()
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    request = {'host_root': str(target), 'reviewed_source_files': source_files,
               'implementation_bundle': str(bundle),
               'trusted_modified_receipt_sha256': modified['receipt_sha256'],
               'template_directory': str(template), 'wheelhouse': str(wheelhouse),
               'reviewed_wheels': wheels, 'output_parent': str(output),
               'environment_parent': str(environments),
               'console_script': binding['script'], 'interpreter': sys.executable,
               'configuration': config, 'reviewed_configuration_sha256': digest(config)}
    return request, applied, target, bundle, spec


def test_native_offline_package_install_and_normal_console(tmp_path):
    request, applied, target, bundle, spec = _request(tmp_path)
    plan = plan_windows_template_package(request)
    assert plan['inputs']['entry_point'] == 'atlas_pkg.console:main'
    assert windows_package_status(plan)['status'] == 'absent'
    package = build_windows_template_package(plan,
                                             approved_plan_sha256=plan['plan_sha256'])
    assert windows_package_status(plan, trusted_receipt_sha256=
                                  package['receipt_sha256'])['receipt_trust'] == 'externally_anchored'
    install_plan = plan_windows_template_install(
        plan, package, trusted_package_receipt_sha256=package['receipt_sha256'])
    assert windows_install_status(install_plan)['status'] == 'absent'
    installed = install_windows_template_package(
        install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert windows_install_status(install_plan, trusted_receipt_sha256=
                                  installed['receipt_sha256'])['status'] == 'installed_recorded'
    marker = __import__('jev_integration_evaluator.integrations.recipes',
                        fromlist=['host_lifecycle_marker']).host_lifecycle_marker(
                            spec['host_lifecycle'], spec['bindings']['runtime'], spec['candidate_id'])
    record = tmp_path / 'record.json'
    session = create_windows_template_session(
        tmp_path / 'session', install_plan, installed,
        trusted_install_receipt_sha256=installed['receipt_sha256'],
        launch_environment={'JEV_FIXTURE_RECORD': str(record),
                            'JEV_FIXTURE_MARKER': marker})
    assert windows_session_status(session)['status'] == 'created'
    identity = launch_windows_template_session(
        session, install_plan, approved_session_sha256=session['session_sha256'])
    assert identity['pid'] > 0
    with pytest.raises(InputError, match='launch_already_attempted'):
        launch_windows_template_session(
            session, install_plan, approved_session_sha256=session['session_sha256'])
    import time
    deadline = time.monotonic() + 30
    while not record.is_file() and time.monotonic() < deadline:
        time.sleep(.05)
    assert record.is_file()
    status = windows_session_status(session,
                                    trusted_identity_sha256=identity['identity_sha256'])
    assert status['receipt_trust'] == 'externally_anchored'
    stopped = stop_windows_template_session(session,
                                             approved_identity_sha256=identity['identity_sha256'])
    assert not stopped['process_alive']
    added = Path(installed['installed']['python']).parents[1] / 'Lib' / 'site-packages' / 'sitecustomize.py'
    added.write_text('raise RuntimeError("unreviewed")\n', encoding='utf-8')
    with pytest.raises(InputError, match='tree_drift'):
        windows_install_status(install_plan,
                               trusted_receipt_sha256=installed['receipt_sha256'])
