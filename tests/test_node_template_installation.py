"""Native offline Node package/install effects; JS source review is separately anchored."""
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator import template_node_installation as node_install
from jev_integration_evaluator import template_js_catalog
from jev_integration_evaluator.io import write_json
from test_js_template_delivery import request_for


def native_tools():
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        return None
    node = shutil.which('node')
    if not node:
        return None
    node = Path(node).resolve()
    npm = node.parent.parent / 'lib/node_modules/npm/bin/npm-cli.js'
    if not npm.is_file():
        return None
    versions = (subprocess.run([str(node), '--version'], capture_output=True, text=True).stdout.strip(),
                subprocess.run([str(node), str(npm), '--version'], capture_output=True, text=True).stdout.strip())
    return (node, npm) if versions == ('v24.18.0', '11.16.0') else None


@pytest.mark.parametrize('extension', ['mjs', 'cjs'])
def test_offline_owned_package_install_and_drift(tmp_path, monkeypatch, extension):
    tools = native_tools()
    if tools is None:
        pytest.skip('native pinned Node v24.18.0/npm 11.16.0 absent')
    node, npm = tools
    host = tmp_path / 'host'; host.mkdir()
    entry = f'start.{extension}'
    (host / entry).write_text('process.stdout.write("off\\n");\n', encoding='utf-8')
    (host / 'package.json').write_text(json.dumps({'name': 'offline-fixture', 'version': '1.0.0',
                               'scripts': {'start': 'node ' + entry}}), encoding='utf-8')
    (host / 'package-lock.json').write_text(json.dumps({'name': 'offline-fixture',
                               'version': '1.0.0', 'lockfileVersion': 3,
                               'packages': {'': {'name': 'offline-fixture', 'version': '1.0.0'}}}),
                               encoding='utf-8')
    source = {path.name: file_hash(path) for path in host.iterdir()}
    for name in ('cache', 'render', 'bundle', 'tooling', 'packages', 'generations'):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
    request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
               'host_root': str(host), 'render_directory': str(tmp_path / 'render'),
               'implementation_bundle': str(tmp_path / 'bundle'),
               'trusted_modified_sha256': 'a' * 64, 'node': str(node),
               'node_sha256': file_hash(node), 'npm_cli': str(npm),
               'npm_cli_sha256': file_hash(npm), 'tooling_directory': str(tmp_path / 'tooling'),
               'offline_cache': str(tmp_path / 'cache'),
               'package_directory': str(tmp_path / 'packages' / 'package'),
               'environment_parent': str(tmp_path / 'generations')}
    toolchain = {'node': str(node), 'node_sha256': file_hash(node),
                 'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
                 'node_version': 'v24.18.0', 'npm_version': '11.16.0', 'tooling': {}}
    plan = {'schema_version': '1.0', 'kind': 'node-package-plan-v1',
            'request': request, 'render_lock_sha256': 'b' * 64,
            'implementation_plan_sha256': 'c' * 64,
            'applied_source_files': source, 'applied_source_sha256': digest(source),
            'offline_cache_sha256': digest({}), 'toolchain': toolchain,
            'configuration_sha256': 'd' * 64, 'secret_references_sha256': 'e' * 64,
            'package_profile_sha256': 'f' * 64, 'format': 'esm' if extension == 'mjs' else 'commonjs',
            'entrypoint': entry, 'mode': 'off', 'runtime_activation_authorized': False}
    plan['plan_sha256'] = digest(plan)
    # The source/render/modified-receipt verifier needs trusted TS 5.8.3.
    # This fixture replaces only that upstream read-only planner so the real
    # native npm effect and owned generation can be tested without it.
    monkeypatch.setattr(node_install, 'plan_node_package',
                        lambda actual, _allow_existing_output=False: plan if actual == request else None)
    with pytest.raises(InputError, match='approval'):
        node_install.build_node_package(plan, approved_plan_sha256='0' * 64)
    package = node_install.build_node_package(plan, approved_plan_sha256=plan['plan_sha256'])
    assert node_install.package_status(plan, trusted_receipt_sha256=package['receipt_sha256'])['status'] == 'packaged_recorded'
    staged_entry = Path(package['package_directory']) / 'app' / entry
    original = staged_entry.read_bytes()
    staged_entry.write_text('changed\n', encoding='utf-8')
    with pytest.raises(InputError, match='drift'):
        node_install.package_status(plan, trusted_receipt_sha256=package['receipt_sha256'])
    staged_entry.write_bytes(original)
    install_plan = node_install.plan_node_install(plan, package)
    with pytest.raises(InputError, match='approval'):
        node_install.install_node_package(install_plan, approved_plan_sha256='0' * 64)
    receipt = node_install.install_node_package(install_plan, approved_plan_sha256=install_plan['plan_sha256'])
    assert receipt['command'][0] == str(node) and receipt['mode'] == 'off'
    assert receipt['launch_status'] == 'not_started'
    assert node_install.installation_status(install_plan, trusted_receipt_sha256=receipt['receipt_sha256'])['status'] == 'installed_recorded'
    installed_entry = Path(receipt['command'][1])
    installed_entry.write_text('changed\n', encoding='utf-8')
    with pytest.raises(InputError, match='drift'):
        node_install.installation_status(install_plan, trusted_receipt_sha256=receipt['receipt_sha256'])


def test_missing_trusted_typescript_fails_before_output(tmp_path):
    tools = native_tools()
    if tools is None:
        pytest.skip('native pinned Node v24.18.0/npm 11.16.0 absent')
    node, npm = tools
    for name in ('host', 'render', 'bundle', 'tooling', 'cache', 'packages', 'generations'):
        (tmp_path / name).mkdir(mode=0o700)
        os.chmod(tmp_path / name, 0o700)
    request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
               'host_root': str(tmp_path / 'host'), 'render_directory': str(tmp_path / 'render'),
               'implementation_bundle': str(tmp_path / 'bundle'),
               'trusted_modified_sha256': 'a' * 64,
               'node': str(node), 'node_sha256': file_hash(node),
               'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
               'tooling_directory': str(tmp_path / 'tooling'),
               'offline_cache': str(tmp_path / 'cache'),
               'package_directory': str(tmp_path / 'packages' / 'new'),
               'environment_parent': str(tmp_path / 'generations')}
    with pytest.raises(InputError, match='tooling|compiler'):
        node_install.plan_node_package(request)
    assert not (tmp_path / 'packages' / 'new').exists()


@pytest.mark.parametrize('format_name', ['esm', 'commonjs'])
def test_planner_binds_render_lock_and_full_applied_source(tmp_path, monkeypatch, format_name):
    tools = native_tools()
    if tools is None:
        pytest.skip('native pinned Node v24.18.0/npm 11.16.0 absent')
    node, npm = tools
    host, source_request = request_for(tmp_path, format_name)
    source = host / source_request['implementation_spec']['source']['file']
    profile = template_js_catalog._package(host, source_request, format_name)
    render = tmp_path / 'render'; render.mkdir(mode=0o700)
    bundle = tmp_path / 'bundle'; bundle.mkdir(mode=0o700)
    for name in ('cache', 'packages', 'generations', 'tooling'):
        (tmp_path / name).mkdir(mode=0o700)
        os.chmod(tmp_path / name, 0o700)
    os.chmod(render, 0o700)
    os.chmod(bundle, 0o700)
    tool_identity = {'node_path': str(node), 'node_sha256': file_hash(node),
                     'compiler_path': str(tmp_path / 'tooling' / 'typescript.js'),
                     'compiler_sha256': '1' * 64, 'compiler_version': '5.8.3'}
    tool_identity.update({key: '2' * 64 for key in ('transformer_sha256', 'runtime_sha256',
                           'probe_sha256', 'emitter_sha256', 'backend_sha256', 'lifecycle_sha256')})
    toolchain = {'node': str(node), 'node_sha256': file_hash(node),
                 'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
                 'node_version': 'v24.18.0', 'npm_version': '11.16.0', 'tooling': tool_identity}
    manifest = template_js_catalog.inspect_js_template()
    resources = {'template-manifest.json': {k: v for k, v in manifest.items() if k != 'manifest_sha256'},
                 'template-request.json': source_request,
                 'implementation-spec.json': source_request['implementation_spec'],
                 'package-profile.json': profile}
    for name, value in resources.items():
        write_json(render / name, value)
    resource_hashes = {name: file_hash(render / name) for name in resources}
    original_source = source.read_text(encoding='utf-8')
    source.write_text(original_source + '\n// reviewed applied fixture\n', encoding='utf-8')
    generated = {source.name: file_hash(source)}
    js_plan = {'spec_sha256': digest(source_request['implementation_spec']),
               'tooling': tool_identity, 'format': format_name,
               'generated_sha256': generated, 'contract_digest': '3' * 64}
    write_json(bundle / 'plan.json', js_plan)
    write_json(bundle / 'modified-receipt.json', {'plan_sha256': '3' * 64, 'status': 'passed'})
    lock = {'schema_version': '1.0', 'status': 'materialized',
            'template_id': 'javascript.recipe-c', 'template_version': '1.0.0',
            'manifest_sha256': manifest['manifest_sha256'],
            'evaluator_version': manifest['evaluator_version'],
            'renderer_sha256': file_hash(Path(template_js_catalog.__file__)),
            'tooling': tool_identity, 'request_sha256': digest(source_request),
            'spec_sha256': digest(source_request['implementation_spec']),
            'candidate_id': source_request['implementation_spec']['candidate_id'],
            'format': format_name, 'source_sha256': source_request['implementation_spec']['source']['sha256'],
            'generated_sha256': file_hash(source), 'emitted_sha256': None,
            'package': profile, 'configuration_sha256': source_request['reviewed_configuration_sha256'],
            'secret_references_sha256': digest({}), 'lifecycle': manifest['lifecycle'],
            'target_modified': False, 'target_executed': False,
            'owned_resources': resource_hashes,
            'planner': {'command': 'js-plan', 'spec': 'implementation-spec.json',
                        'tooling': str(tmp_path / 'tooling'), 'output': 'new external private bundle'}}
    lock['lock_sha256'] = digest(lock)
    write_json(render / 'template-lock.json', lock)
    write_json(render / 'render-status.json', {'schema_version': '1.0', 'status': 'complete',
               'lock_sha256': lock['lock_sha256'], 'resources': resource_hashes})
    request = {'schema_version': '1.0', 'kind': 'node-package-request-v1',
               'host_root': str(host), 'render_directory': str(render),
               'implementation_bundle': str(bundle),
               'trusted_modified_sha256': file_hash(bundle / 'modified-receipt.json'),
               'node': str(node), 'node_sha256': file_hash(node),
               'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
               'tooling_directory': str(tmp_path / 'tooling'),
               'offline_cache': str(tmp_path / 'cache'),
               'package_directory': str(tmp_path / 'packages' / 'new'),
               'environment_parent': str(tmp_path / 'generations')}
    monkeypatch.setattr(node_install, '_toolchain', lambda *_: toolchain)
    monkeypatch.setattr(node_install.js_lifecycle, 'status_js', lambda *args, **kwargs: {'status': 'verified'})
    plan = node_install.plan_node_package(request)
    assert plan['applied_source_files'][source.name] == file_hash(source)
    assert plan['format'] == format_name and not Path(request['package_directory']).exists()
    (host / 'unreviewed.js').write_text('new file\n', encoding='utf-8')
    with pytest.raises(InputError, match='source drift'):
        node_install.plan_node_package(request)
