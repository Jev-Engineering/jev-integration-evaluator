"""Independent, source-verified CommonJS recipe C installed host journey."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator import template_js_catalog
from jev_integration_evaluator import template_node_installation as installer
from jev_integration_evaluator import template_node_delivery as delivery
from jev_integration_evaluator import template_node_session as session
from jev_integration_evaluator.integrations.js_lifecycle import (
    apply_js, plan_js, rollback_js, status_js, verify_js,
)
from jev_integration_evaluator.template_catalog import materialize_template
from test_js_template_delivery import request_for
from test_node_template_installation import native_tools
from test_node_template_installed_upgrade import (
    NPM_CLI_SHA256, NPM_TREE_SHA256, NODE_SHA256,
    TRUSTED_TYPESCRIPT_TREE_SHA256, _observe, _observations, _scope,
)


def _installed(tmp_path: Path, name: str, version: str, item: str,
               tooling: Path, node: Path, npm: Path) -> dict:
    work = tmp_path / name
    work.mkdir(mode=0o700)
    source, request = request_for(work, 'commonjs')
    host = source / 'host.cjs'
    if version == '1.0.1':
        before = ("events.push(['read', request.item]); "
                  "globalThis.__jev_probe_effect?.('read', request.item); "
                  "return 'read:' + request.item;")
        after = ("events.push(['read', request.item]); "
                 "globalThis.__jev_probe_effect?.('read', request.item + ':v2'); "
                 "return 'read:' + request.item + ':v2';")
        text = host.read_text(encoding='utf-8')
        assert text.count(before) == 1
        host.write_text(text.replace(before, after), encoding='utf-8')
        request['implementation_spec']['source']['sha256'] = file_hash(host)
    reviewed_host = host.read_bytes()
    package_path, lock_path = source / 'package.json', source / 'package-lock.json'
    package, lock = (json.loads(path.read_text()) for path in (package_path, lock_path))
    package.update(name='independent-commonjs-recipe-c', version=version)
    package['scripts']['start'] = 'node start.cjs'
    lock.update(name=package['name'], version=version)
    lock['packages'][''].update(name=package['name'], version=version)
    package_path.write_text(json.dumps(package), encoding='utf-8')
    lock_path.write_text(json.dumps(lock), encoding='utf-8')
    marker = ':v2' if version == '1.0.1' else ''
    entry = source / 'start.cjs'
    entry.write_text(
        'const fs = require("node:fs");\n'
        'const seam = require("./host.cjs");\n'
        'if (process.env.JEV_RUNTIME_MODE !== "off") throw Error("mode");\n'
        'for (const key of ["NODE_EFFECT_PATH","NODE_READY_PATH","NODE_INTEGRATION_PATH"]) '
        'if (!process.env[key]) throw Error("missing path");\n'
        'globalThis.__jev_probe_effect = (action,item) => '
        'fs.writeFileSync(process.env.NODE_EFFECT_PATH, action+":"+item+"\\n", {flag:"wx"});\n'
        'async function main() {\n'
        f'  const result = await seam({{task_id:"task",invocation_id:"normal-{version}",'
        f'item:"{item}",permit:true}});\n'
        f'  if (result !== "read:{item}{marker}") throw Error("seam result");\n'
        '  fs.writeFileSync(process.env.NODE_READY_PATH,"ready\\n",{flag:"wx"});\n'
        '  fs.writeFileSync(process.env.NODE_INTEGRATION_PATH,"integration\\n",{flag:"wx"});\n'
        '  await new Promise(resolve => setTimeout(resolve, 800));\n'
        '}\nmain().catch(() => {process.exitCode = 1;});\n', encoding='utf-8')
    request['entrypoint'] = 'start.cjs'
    request['entrypoint_sha256'] = file_hash(entry)
    request['package_json_sha256'] = file_hash(package_path)
    request['package_lock_sha256'] = file_hash(lock_path)
    request['reviewed_package_source_sha256'] = digest(template_js_catalog._source_tree(source))
    cases = [{'id': 'normal-' + version,
              'request': {'task_id': 'task', 'invocation_id': 'case-' + version,
                          'item': item, 'permit': True},
              'result': 'read:' + item + marker,
              'events': [['read', item]], 'effects': [['read', item + marker]]}]
    request['implementation_spec']['verification_sha256'] = digest(cases)
    request['implementation_spec']['verification_cases_count'] = len(cases)
    rendered = tmp_path / (name + '-render')
    materialize_template(source, request, rendered, tooling_dir=tooling)
    bundle = tmp_path / (name + '-bundle')
    planned = plan_js(source, request['implementation_spec'], bundle, tooling_dir=tooling)
    baseline = verify_js(source, bundle, 'baseline', cases, tooling_dir=tooling,
                         approve_execution=True)
    assert baseline['status'] == 'passed'
    apply_js(source, bundle, planned['bundle_sha256'],
             baseline_sha256=baseline['receipt_sha256'], tooling_dir=tooling)
    modified = verify_js(source, bundle, 'modified', cases, tooling_dir=tooling,
                         baseline_sha256=baseline['receipt_sha256'], approve_execution=True)
    assert modified['status'] == 'passed'
    verified = status_js(source, bundle, tooling_dir=tooling,
                         trusted_modified_sha256=modified['receipt_sha256'])
    assert verified['status'] == 'verified'
    packages = tmp_path / (name + '-packages')
    packages.mkdir(mode=0o700)
    request_install = {
        'schema_version': '1.0', 'kind': 'node-package-request-v1',
        'host_root': str(source), 'render_directory': str(rendered),
        'implementation_bundle': str(bundle),
        'trusted_modified_sha256': modified['receipt_sha256'],
        'node': str(node), 'node_sha256': file_hash(node),
        'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
        'npm_tree_sha256': digest(installer._tree(npm.parent.parent)),
        'tooling_directory': str(tooling), 'offline_cache': str(tmp_path / 'cache'),
        'package_directory': str(packages / 'package'),
        'environment_parent': str(tmp_path / 'generations')}
    package_plan = installer.plan_node_package(request_install)
    package_receipt = installer.build_node_package(
        package_plan, approved_plan_sha256=package_plan['plan_sha256'])
    install_plan = installer.plan_node_install(package_plan, package_receipt,
        trusted_package_receipt_sha256=package_receipt['receipt_sha256'])
    installed = installer.install_node_package(install_plan,
        approved_plan_sha256=install_plan['plan_sha256'])
    assert installer.installation_status(install_plan,
        trusted_receipt_sha256=installed['receipt_sha256'])['status'] == 'installed_recorded'
    assert Path(installed['command'][1]) == Path(installed['generation_path']) / 'app/start.cjs'
    assert file_hash(Path(installed['command'][1])) == installed['entrypoint_sha256']
    app = Path(installed['generation_path']) / 'app'
    assert json.loads((app / 'package.json').read_text())['scripts']['start'] == 'node start.cjs'
    assert file_hash(app / 'host.cjs') == file_hash(host)
    assert app != source and not app.is_relative_to(Path(__file__).resolve().parents[1])
    return {'source': source, 'bundle': bundle, 'rollback_digest': verified['rollback_digest'],
            'reviewed_host': reviewed_host, 'install_plan': install_plan,
            'installed': installed, 'version': version, 'item': item}


def test_real_installed_commonjs_upgrade_fault_and_retained_rollback(tmp_path, monkeypatch):
    tools = native_tools()
    compiler_name = os.environ.get('JEV_TRUSTED_TYPESCRIPT_PACKAGE')
    compiler = Path(compiler_name) if compiler_name else Path('/nonexistent-typescript-package')
    if tools is None or not (compiler / 'lib/typescript.js').is_file():
        pytest.skip('pinned Linux Node/npm and trusted TypeScript 5.8.3 required')
    node, npm = tools
    assert file_hash(node) == NODE_SHA256
    assert file_hash(npm) == NPM_CLI_SHA256
    assert digest(installer._tree(npm.parent.parent)) == NPM_TREE_SHA256
    assert digest(installer._tree(compiler)) == TRUSTED_TYPESCRIPT_TREE_SHA256
    tooling = tmp_path / 'tooling'
    (tooling / 'node_modules').mkdir(parents=True)
    os.chmod(tooling, 0o700)
    shutil.copytree(compiler, tooling / 'node_modules/typescript')
    (tmp_path / 'cache').mkdir(mode=0o700)
    (tmp_path / 'generations').mkdir(mode=0o700)
    old = _installed(tmp_path, 'commonjs-one', '1.0.0', 'alpha', tooling, node, npm)
    new = _installed(tmp_path, 'commonjs-two', '1.0.1', 'beta', tooling, node, npm)
    assert old['installed']['source_sha256'] != new['installed']['source_sha256']
    assert old['installed']['generation_id'] != new['installed']['generation_id']

    def descriptor(host, name):
        observation, environment, effect = _observations(tmp_path / name,
            host['version'], host['item'])
        plan = delivery.plan_node_delivery(host['install_plan'],
            trusted_install_receipt_sha256=host['installed']['receipt_sha256'],
            observation=observation, launch_environment=environment)
        assert delivery.validate_node_delivery(plan)['status'] == 'verified_unlaunched'
        return plan, environment, effect

    first, first_env, first_effect = descriptor(old, 'commonjs-old-effects')
    second, second_env, second_effect = descriptor(new, 'commonjs-new-effects')
    path = tmp_path / 'commonjs-session'
    created = session.create_node_session(path, first)
    first_launch = _scope(created, 'launch', first)
    running = session.launch_node_session(path, scope=first_launch,
        approved_scope_sha256=first_launch['scope_sha256'])
    observed = _observe(path, running)
    assert observed['observations']['entrypoint_reached']
    assert Path(first_env['NODE_EFFECT_PATH']).read_bytes() == first_effect == b'read:alpha\n'
    assert all(file_hash(Path(row['path'])) == row['expected_sha256']
               for row in first['observation']['checks'])
    stop = _scope(observed, 'stop', first)
    stopped = session.stop_node_session(path, scope=stop,
        approved_scope_sha256=stop['scope_sha256'], grace_seconds=0)
    assert stopped['stage'] == 'stopped'
    upgrade = _scope(stopped, 'upgrade', first, extra=second['descriptor_sha256'])
    original_append = session._append

    def interrupt(directory, rows, event, state):
        if event == 'upgrade_staged':
            raise RuntimeError('synthetic selection interruption')
        return original_append(directory, rows, event, state)

    monkeypatch.setattr(session, '_append', interrupt)
    with pytest.raises(RuntimeError, match='synthetic selection interruption'):
        session.upgrade_node_session(path, second, scope=upgrade,
            approved_scope_sha256=upgrade['scope_sha256'])
    monkeypatch.setattr(session, '_append', original_append)
    pending = session.node_session_status(path)
    assert pending['pending'] == 'upgrade' and pending['run_id'] == created['run_id']
    assert not Path(second_env['NODE_EFFECT_PATH']).exists()
    upgraded = session.resume_node_session(path,
        trusted_session_head=pending['session_head_sha256'])
    assert upgraded['stage'] == 'upgrade_staged' and upgraded['run_id'] == created['run_id']
    second_launch = _scope(upgraded, 'launch', second)
    running_new = session.launch_node_session(path, scope=second_launch,
        approved_scope_sha256=second_launch['scope_sha256'])
    observed_new = _observe(path, running_new)
    assert Path(second_env['NODE_EFFECT_PATH']).read_bytes() == second_effect == b'read:beta:v2\n'
    assert first_effect != second_effect
    disable = _scope(observed_new, 'disable', second)
    disabled = session.stop_node_session(path, scope=disable,
        approved_scope_sha256=disable['scope_sha256'], disable=True, grace_seconds=0)
    assert disabled['stage'] == 'disabled'
    rollback = _scope(disabled, 'rollback', second,
                      extra=disabled['previous_generation_rollback_digest'])
    restored = session.rollback_node_session(path, scope=rollback,
        approved_scope_sha256=rollback['scope_sha256'])
    assert restored['stage'] == 'rolled_back'
    assert restored['run_id'] == created['run_id']
    assert restored['generation_id'] == old['installed']['generation_id']
    assert all(Path(host['installed']['generation_path']).is_dir() for host in (old, new))
    assert Path(first_env['NODE_EFFECT_PATH']).read_bytes() == first_effect
    assert Path(second_env['NODE_EFFECT_PATH']).read_bytes() == second_effect
    stale_launch = _scope(restored, 'launch', first)
    with pytest.raises(InputError):
        session.launch_node_session(path, scope=stale_launch,
            approved_scope_sha256=stale_launch['scope_sha256'])
    for host in (new, old):
        rolled = rollback_js(host['source'], host['bundle'], host['rollback_digest'],
                             tooling_dir=tooling)
        assert rolled['status'] == 'rolled_back'
        assert (host['source'] / 'host.cjs').read_bytes() == host['reviewed_host']
