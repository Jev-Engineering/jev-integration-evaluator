"""Source-bound JS recipe C catalog; native journeys require trusted Linux Node."""
from __future__ import annotations

import copy
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest

from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import InputError, digest, file_hash, read_json
from jev_integration_evaluator.template_catalog import (
    inspect_template, list_templates, materialize_template, render_status,
    validate_template_request,
)
from jev_integration_evaluator.template_js_catalog import (
    _package, _source_tree, validate_js_template_request,
)
from jev_integration_evaluator.integrations.js_lifecycle import plan_js
from test_js_lifecycle import fixture

ROOT = Path(__file__).resolve().parents[1]
TRUSTED = ROOT / 'node_modules/typescript/lib/typescript.js'
NATIVE = sys.platform == 'linux' and shutil.which('node') is not None and TRUSTED.is_file()


def request_for(tmp_path, format_name):
    root, source, spec, _ = fixture(tmp_path, format_name)
    entry = source.name if format_name != 'typescript' else 'start.mjs'
    if format_name == 'typescript':
        (root / entry).write_text("import {seam} from './host.mjs';\n", encoding='utf-8')
    package = {'name': 'synthetic-host', 'version': '1.0.0',
               'scripts': {'start': 'node ' + entry}}
    lock = {'name': package['name'], 'version': package['version'], 'lockfileVersion': 3,
            'packages': {'': {'name': package['name'], 'version': package['version']}}}
    (root / 'package.json').write_text(json.dumps(package), encoding='utf-8')
    (root / 'package-lock.json').write_text(json.dumps(lock), encoding='utf-8')
    source_map = _source_tree(root)
    configuration = {'mode': 'off', 'credential_ref': None}
    request = {'schema_version': '1.0', 'template_id': 'javascript.recipe-c',
               'template_version': '1.0.0', 'backend': 'javascript',
               'profile': 'flat-async-recipe-c-v1', 'format': format_name,
               'implementation_spec': spec, 'entrypoint': entry,
               'package_json_sha256': file_hash(root / 'package.json'),
               'package_lock_sha256': file_hash(root / 'package-lock.json'),
               'entrypoint_sha256': file_hash(root / entry),
               'reviewed_package_source_sha256': digest(source_map),
               'configuration': configuration, 'secret_references': {},
               'reviewed_configuration_sha256': digest({'configuration': configuration,
                                                         'secret_references': {}})}
    return root, request


def test_distinct_catalog_contract_and_legacy_python_schema():
    listing = list_templates()['templates']
    assert [x['template_id'] for x in listing] == ['python.bounded-tail-call', 'javascript.recipe-c']
    manifest = inspect_template('javascript.recipe-c')
    validate_contract({k: v for k, v in manifest.items() if k != 'manifest_sha256'},
                      'javascript-template-manifest-v1')
    assert manifest['lifecycle']['install'] == 'pending_node_adapter'
    assert manifest['lifecycle']['authorized_mode'] == 'off'
    assert 'not inspected by catalog' in manifest['compatibility']['install_hooks']['tarball_contents']
    with pytest.raises(InputError, match='Unsupported JavaScript template'):
        inspect_template('javascript.recipe-c', '0.9.0')
    assert read_json(ROOT / 'schemas/template-request-v1.schema.json')['properties']['template_id'] == {
        'const': 'python.bounded-tail-call'}


@pytest.mark.parametrize('format_name', ['esm', 'commonjs', 'typescript'])
def test_package_input_lock_and_reviewed_digest_fail_closed(tmp_path, format_name):
    root, request = request_for(tmp_path, format_name)
    validate_contract(request, 'javascript-template-request-v1')
    row = _package(root, request, format_name)
    assert row['source_sha256'] == request['reviewed_package_source_sha256']
    (root / 'helper.js').write_text('export const value = 1;\n', encoding='utf-8')
    with pytest.raises(InputError, match='source changed'):
        _package(root, request, format_name)
    (root / 'helper.js').unlink()
    bad = copy.deepcopy(request)
    bad['entrypoint'] = '../host.mjs'
    with pytest.raises(InputError):
        validate_contract(bad, 'javascript-template-request-v1')
    package_path = root / 'package.json'
    package = read_json(package_path)
    package['scripts']['postinstall'] = 'node unknown.cjs'
    package_path.write_text(json.dumps(package), encoding='utf-8')
    with pytest.raises(InputError, match='Unsupported finite Node package start profile|hooks'):
        _package(root, request, format_name)
    package_path.write_text(json.dumps({'name': 'synthetic-host', 'version': '1.0.0',
                                        'scripts': {'start': 'node ' + request['entrypoint']}}),
                            encoding='utf-8')
    lock_path = root / 'package-lock.json'
    lock = read_json(lock_path)
    lock['lockfileVersion'] = 2
    lock_path.write_text(json.dumps(lock), encoding='utf-8')
    with pytest.raises(InputError, match='lockfileVersion 3'):
        _package(root, request, format_name)


def test_wrong_secret_reference_and_schema_reject_before_tooling(tmp_path):
    root, request = request_for(tmp_path, 'esm')
    wrong = copy.deepcopy(request)
    wrong['secret_references'] = {'credential': 'env:OTHER'}
    with pytest.raises(InputError, match='configuration or secret reference changed'):
        validate_js_template_request(root, wrong, tooling_dir=tmp_path / 'missing')
    wrong = copy.deepcopy(request)
    wrong['unknown'] = 'data'
    with pytest.raises(InputError, match='Invalid javascript-template-request-v1'):
        validate_template_request(root, wrong, tooling_dir=ROOT)


def test_flat_locked_dependency_and_declared_hook_rejection(tmp_path):
    root, request = request_for(tmp_path, 'esm')
    package_path, lock_path = root / 'package.json', root / 'package-lock.json'
    package = read_json(package_path)
    package['dependencies'] = {'fixture-dep': '1.2.3'}
    package_path.write_text(json.dumps(package), encoding='utf-8')
    lock = read_json(lock_path)
    lock['packages']['']['dependencies'] = package['dependencies']
    lock['packages']['node_modules/fixture-dep'] = {
        'version': '1.2.3',
        'resolved': 'https://registry.npmjs.org/fixture-dep/-/fixture-dep-1.2.3.tgz',
        'integrity': 'sha512-' + base64.b64encode(b'x' * 64).decode('ascii'),
    }
    lock_path.write_text(json.dumps(lock), encoding='utf-8')
    request['package_json_sha256'] = file_hash(package_path)
    request['package_lock_sha256'] = file_hash(lock_path)
    request['reviewed_package_source_sha256'] = digest(_source_tree(root))
    assert _package(root, request, 'esm')['dependency_count'] == 1
    # The catalog accepts the declared lock shape; it has not read the tarball.
    lock['packages']['node_modules/fixture-dep']['hasInstallScript'] = True
    lock_path.write_text(json.dumps(lock), encoding='utf-8')
    with pytest.raises(InputError, match='Unsupported Node dependency lock row'):
        _package(root, request, 'esm')
    lock['packages']['node_modules/fixture-dep']['hasInstallScript'] = False
    lock_path.write_text(json.dumps(lock), encoding='utf-8')
    with pytest.raises(InputError, match='Unsupported Node dependency package behavior'):
        _package(root, request, 'esm')


@pytest.mark.skipif(not NATIVE, reason='Native Linux Node and trusted TypeScript 5.8.3 required')
@pytest.mark.parametrize('format_name', ['esm', 'commonjs', 'typescript'])
def test_native_source_bound_materialization_and_existing_planner(tmp_path, format_name):
    root, request = request_for(tmp_path, format_name)
    before = {p.name: file_hash(p) for p in root.iterdir()}
    validated = validate_template_request(root, request, tooling_dir=ROOT)
    first = materialize_template(root, request, tmp_path / 'first', tooling_dir=ROOT)
    second = materialize_template(root, request, tmp_path / 'second', tooling_dir=ROOT)
    assert first == second and first['source_sha256'] == request['implementation_spec']['source']['sha256']
    assert first['tooling']['compiler_version'] == '5.8.3'
    assert first['lifecycle']['launch'] == 'pending_delivery_supervisor'
    assert validated['target_modified'] is False and validated['target_executed'] is False
    validate_contract(first, 'javascript-template-lock-v1')
    assert render_status(tmp_path / 'first')['status'] == 'marker_complete_unverified'
    assert {p.name: file_hash(p) for p in root.iterdir()} == before
    planned = plan_js(root, read_json(tmp_path / 'first/implementation-spec.json'),
                      tmp_path / 'js-bundle', tooling_dir=ROOT)
    assert planned['status'] == 'planned' and planned['target_modified'] is False
    with (root / request['entrypoint']).open('ab') as stream:
        stream.write(b'\n// changed\n')
    with pytest.raises(InputError, match='changed'):
        materialize_template(root, request, tmp_path / 'drift', tooling_dir=ROOT)
    assert not (tmp_path / 'drift').exists()


@pytest.mark.skipif(not NATIVE, reason='Native Linux Node and trusted TypeScript 5.8.3 required')
@pytest.mark.parametrize('format_name', ['esm', 'commonjs', 'typescript'])
def test_installed_evaluator_cli_materializes_without_checkout_import(tmp_path, format_name):
    root, request = request_for(tmp_path, format_name)
    wheels = tmp_path / 'wheels'; wheels.mkdir()
    build = subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-build-isolation',
                            '--no-deps', '-w', str(wheels), str(ROOT)], cwd=tmp_path,
                           capture_output=True, text=True, timeout=90)
    assert build.returncode == 0, build.stderr
    wheel = next(wheels.glob('jev_integration_evaluator-*.whl'))
    environment = tmp_path / 'evaluator-venv'
    venv.EnvBuilder(with_pip=False, system_site_packages=True).create(environment)
    python = environment / 'bin/python'
    installed = subprocess.run([sys.executable, '-m', 'pip', '--python', str(python),
                                'install', '--no-index', '--no-deps', str(wheel)],
                               capture_output=True, text=True, timeout=90)
    assert installed.returncode == 0, installed.stderr
    request_path = tmp_path / 'request.json'
    request_path.write_text(json.dumps(request), encoding='utf-8')
    out = tmp_path / 'materialized'
    env = os.environ.copy(); env.pop('PYTHONPATH', None)
    run = subprocess.run([str(environment / 'bin/jev-integration-evaluator'),
                          'template', 'materialize', '--repo', str(root),
                          '--request', str(request_path), '--tooling', str(ROOT),
                          '--out', str(out)], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    lock = read_json(out / 'template-lock.json')
    validate_contract(lock, 'javascript-template-lock-v1')
    assert lock['format'] == format_name
    assert read_json(out / 'render-status.json')['status'] == 'complete'
    origin = subprocess.run([str(python), '-c',
                             'import jev_integration_evaluator as x;print(x.__file__)'],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    assert origin.returncode == 0 and str(environment) in origin.stdout
