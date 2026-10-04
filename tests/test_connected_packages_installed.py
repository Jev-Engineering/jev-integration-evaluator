"""Public finite owner of two independent installs; synthetic local TLS only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import ssl
import subprocess
import sys
from threading import Thread
import time

import pytest

from tests.connected_generation_journey import synthetic_typed_answers

from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.integrations.lifecycle import plan_implementation, apply_implementation
from jev_integration_evaluator.integrations.verification import verify_implementation
from jev_integration_evaluator.template_catalog import prepare_template_binding, materialize_template
from jev_integration_evaluator.template_connected_packages_binding import derive_installed_packages_binding
from jev_integration_evaluator.template_packages_owner_binding import derive_owned_packages_binding
from jev_integration_evaluator.template_packages_authority import planned_environment_digest
from jev_integration_evaluator.template_connected_generation import _literal_spec
from jev_integration_evaluator.template_connected_delivery import (
    plan_connected_delivery, create_connected_session, launch_connected_session,
    connected_session_status, stop_connected_session,
)
from jev_integration_evaluator.integrations.runtime_ledger import RuntimeLedger
from jev_integration_evaluator.io import InputError, digest, file_hash, read_json
from tests.connected_generation_journey import _metadata, _observation, _scope, _durable_identity
from tests.test_connected_installed_binding import _issuer, _issue
from tests.independent_hosts.registered_alpha_connected.qualification import ROOT as ALPHA, source_matched_request as alpha_request
from tests.independent_hosts.work_queue.qualification import ROOT as QUEUE, source_matched_request as queue_request

PROFILE = sys.platform == 'linux' and platform.machine().lower() == 'x86_64' and sys.version_info[:2] == (3, 13)
pytestmark = pytest.mark.skipif(not PROFILE, reason='Linux x86-64 CPython 3.13')
TASK = 'independent-packages-task-one'


def _wheelhouse(root):
    prepared = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if not prepared:
        pytest.skip('explicit prepared offline wheelhouse required')
    target = root / 'wheelhouse'
    target.mkdir(mode=0o700)
    for path in Path(prepared).glob('*.whl'):
        name, _version = _metadata(path)
        if name.lower().replace('_', '-') != 'jev-integration-evaluator':
            shutil.copy2(path, target / path.name)
    repository = Path(__file__).resolve().parents[1]
    built = subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-deps',
        '--no-build-isolation', '--wheel-dir', str(target), str(repository)],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    assert built.returncode == 0, 'trusted current evaluator wheel build failed'
    wheels = sorted(target.glob('*.whl'))
    rows = [{'filename': path.name, 'sha256': file_hash(path)} for path in wheels]
    requirements = [{'name': name, 'version': version, 'wheel': path.name, 'sha256': file_hash(path)}
                    for path in wheels for name, version in [_metadata(path)]]
    return target, rows, requirements


def _install_member(root, fixture, qualifier, script, wheelhouse, rows, requirements, monkeypatch):
    root.mkdir(mode=0o700)
    host = root / 'host'
    shutil.copytree(fixture, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    if script == 'work-queue':
        # Author a real source-reviewed loader before fresh scan/binding. The
        # common owner uses its own signed boundary, not this legacy callback.
        shutil.copy2(ALPHA / 'src/registered_alpha/connected_authority.py',
                     host / 'src/work_queue/connected_authority.py')
    # A fresh offline scope declares the deadline before scanning/review and
    # compilation. Full installed provenance checks count toward this bound;
    # this fixture does not qualify the unchanged legacy two-second deadline.
    request, binding = qualifier(host, runtime_timeout_ms=10_000)
    bound = prepare_template_binding(host, request, binding)['request']
    template = root / 'template'
    materialize_template(host, bound, template)
    spec = bound['implementation_spec']
    bundle = root / 'bundle'
    plan = plan_implementation(host, bound['reviewed_inventory'], spec['candidate_id'], spec, bundle)
    probe = root / 'probe'
    probe.mkdir(mode=0o700)
    with monkeypatch.context() as patch:
        patch.setenv('REGISTERED_ALPHA_PROBE_EFFECTS_DIR', str(probe))
        patch.setenv('WORK_QUEUE_PROBE_EFFECTS_DIR', str(probe))
        baseline = verify_implementation(host, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'baseline_passed'
        apply_implementation(host, bundle, plan['bundle_digest'], baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(host, bundle, 'modified', approve_execution=True,
                                         baseline_sha256=baseline['receipt_sha256'])
        assert modified['status'] == 'verified'
    environments = root / 'environments'
    environments.mkdir(mode=0o700)
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    package = installer.plan_package({'schema_version': '1.0', 'host_root': str(host),
        'implementation_bundle': str(bundle), 'trusted_modified_receipt_sha256': modified['receipt_sha256'],
        'template_directory': str(template), 'reviewed_package_source_sha256': digest(installer._tree(host)),
        'reviewed_configuration_sha256': digest(config), 'interpreter': sys.executable,
        'wheelhouse': str(wheelhouse), 'package_directory': str(root / 'package'),
        'environment_parent': str(environments), 'console_script': script,
        'build_tools': {name: importlib.metadata.version(name) for name in ('pip', 'setuptools', 'wheel')},
        'wheels': rows, 'requirements': requirements, 'configuration': config, 'secret_references': {}})
    built = installer.build_package(package, approved_plan_sha256=package['plan_sha256'])
    install = installer.plan_install(package, built)
    receipt = installer.install_package(install, approved_plan_sha256=install['plan_sha256'])
    return {'package_plan': package, 'package_receipt': built, 'install_plan': install,
            'install_receipt': receipt, 'trusted_package_receipt_sha256': built['receipt_sha256'],
            'trusted_install_receipt_sha256': receipt['receipt_sha256']}


def _owner_cli(*args):
    from jev_integration_evaluator.cli import execute, parser
    return execute(parser().parse_args(['template', *args]))


def _install_owner(root, common, members, group, wheelhouse, rows, requirements):
    root.mkdir(mode=0o700)
    source = root / 'host'
    source.mkdir(mode=0o700)
    package = source / 'src/registered_packages'
    package.mkdir(parents=True)
    (package / '__init__.py').write_bytes(b'')
    request = {'task_id': TASK, 'job_id': TASK,
               'alpha_request': {'task_id': TASK, 'item': 'fixture-one', 'intent': 'summarize', 'permit': True, 'approved': True},
               'queue_request': {'job_id': TASK, 'item': 'batch-a', 'intent': 'complete', 'allowed': True, 'complete_allowed': True}}
    original = ('from jev_integration_evaluator.template_packages_runtime import baseline_packages_owner, connected_packages_owner\n\n'
                'def request():\n    return ' + repr(request) + '\n\n'
                'def main():\n    payload = request()\n    return baseline_packages_owner(payload, __file__)\n')
    (package / 'console.py').write_text(original)
    (source / 'pyproject.toml').write_text(
        '[build-system]\nrequires = ["setuptools==' + importlib.metadata.version('setuptools') + '", "wheel==' + importlib.metadata.version('wheel') + '"]\nbuild-backend = "setuptools.build_meta"\n\n'
        '[project]\nname = "jev-independent-registered-packages-owner"\nversion = "1.0.0"\nrequires-python = ">=3.13"\ndependencies = ["jev-integration-evaluator==' + importlib.metadata.version('jev-integration-evaluator') + '"]\n\n'
        '[project.scripts]\nregistered-packages = "registered_packages.console:main"\n\n'
        '[tool.setuptools.packages.find]\nwhere = ["src"]\n')
    members_path = root / 'members.json'
    members_path.write_text(json.dumps(members))
    source_plan_path = root / 'owner-source-plan.json'
    source_plan = _owner_cli('packages-owner-plan', '--repo', str(source), '--members', str(members_path),
        '--source-root', str(common), '--trusted-binding-sha256', group['binding_sha256'], '--out', str(source_plan_path))
    transaction = _owner_cli('packages-owner-apply', '--plan', str(source_plan_path),
        '--transaction', str(root / 'transaction'), '--approve-plan-sha256', source_plan['plan_sha256'])
    environments = root / 'environments'
    environments.mkdir(mode=0o700)
    config = {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    package_request = {'schema_version': '1.0', 'host_root': str(source),
        'owner_source_plan': source_plan, 'owner_source_receipt': transaction,
        'trusted_owner_source_receipt_sha256': transaction['receipt_sha256'],
        'reviewed_package_source_sha256': digest(installer._tree(source)),
        'reviewed_configuration_sha256': digest(config), 'interpreter': sys.executable,
        'wheelhouse': str(wheelhouse), 'package_directory': str(root / 'package'),
        'environment_parent': str(environments), 'console_script': 'registered-packages',
        'build_tools': {name: importlib.metadata.version(name) for name in ('pip', 'setuptools', 'wheel')},
        'wheels': rows, 'requirements': requirements, 'configuration': config, 'secret_references': {}}
    package_request_path = root / 'owner-package-request.json'
    package_request_path.write_text(json.dumps(package_request))
    package_plan_path = root / 'owner-package-plan.json'
    plan = _owner_cli('owner-package-plan', '--request', str(package_request_path), '--out', str(package_plan_path))
    built = _owner_cli('owner-package-build', '--plan', str(package_plan_path), '--approve-plan-sha256', plan['plan_sha256'])
    built_path = root / 'owner-built-receipt.json'
    built_path.write_text(json.dumps(built))
    install_plan_path = root / 'owner-install-plan.json'
    installation = _owner_cli('owner-install-plan', '--package-plan', str(package_plan_path),
        '--package-receipt', str(built_path), '--out', str(install_plan_path))
    receipt = _owner_cli('owner-install', '--plan', str(install_plan_path), '--approve-plan-sha256', installation['plan_sha256'])
    status = _owner_cli('owner-install-status', '--plan', str(install_plan_path))
    assert status['status'] == 'installed_recorded'
    return {'package_plan': plan, 'package_receipt': built, 'install_plan': installation,
            'install_receipt': receipt, 'trusted_package_receipt_sha256': built['receipt_sha256'],
            'trusted_install_receipt_sha256': receipt['receipt_sha256']}, source_plan, transaction, original, request


def _refuse_installed_owner_escalation(owner, delivery_plan, ledger):
    """Actual signed installed startup must refuse before ledger/provider dispatch."""
    environment = dict(os.environ)
    environment.update(delivery_plan['off_provenance']['launch_environment'])
    for name, origin in (('PACKAGES_OWNER_CONNECTED_REF_SHA256', 'PACKAGES_OWNER_CONNECTED_REF'),
                         ('PACKAGES_OWNER_AUTH_PUBKEY_SHA256', 'PACKAGES_OWNER_AUTH_PUBKEY_FILE')):
        environment[name] = file_hash(Path(environment[origin]))
    binding = delivery_plan['installed_binding']
    console = binding['owner']['origins']['console']['path']
    python = Path(owner['install_receipt']['environment']) / 'venv/bin/python'
    code = """import json,sys
from registered_packages.console import request
from jev_integration_evaluator.template_packages_runtime import _selected,_dependency_plan,_release_finder,_Audit
from jev_integration_evaluator.integrations.runtime_lifecycle import HostRuntimeLifecycle,LifecycleError
startup,binding,adapters,hosts,entries,finder,payloads=_selected(request(),sys.argv[1])
try:
    scopes=[adapter.SPEC['runtime']['canary_scope'] for adapter in adapters.values()]
    assert len(set(scopes))==2
    limits={'max_calls_per_task':2,'max_cost_per_task':2,'max_total_calls':3,'max_total_cost':3,'max_in_flight':1,'max_tasks':2}
    refusals={}
    for mode in ('canary','active'):
        escalation=dict(startup,startup_mode=mode)
        try:
            HostRuntimeLifecycle(adapters,budget_limits=limits,audit_log=_Audit(),dependency_plan=_dependency_plan(binding),**escalation)
        except LifecycleError as refused:
            assert str(refused)=='connected_composite_combined_gate_required'
            refusals[mode]=str(refused)
        else:
            raise AssertionError('owner escalation unexpectedly started')
    print(json.dumps(refusals,sort_keys=True))
finally:
    _release_finder(finder)
"""
    assert not ledger.exists() and not Path(str(ledger) + '.sqlite').exists()
    result = subprocess.run([str(python), '-I', '-c', code, console], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, 'installed owner escalation refusal did not finish'
    assert json.loads(result.stdout) == {mode: 'connected_composite_combined_gate_required'
                                       for mode in ('canary', 'active')}
    assert not ledger.exists() and not Path(str(ledger) + '.sqlite').exists()


def _raw(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _exited(session):
    deadline = time.monotonic() + 30
    while True:
        result = connected_session_status(session)
        if not result['process_alive']:
            return result
        assert time.monotonic() < deadline
        time.sleep(.02)


def test_normal_installed_owner_shares_exact_ledger_across_two_independent_packages(tmp_path, monkeypatch):
    wheelhouse, rows, requirements = _wheelhouse(tmp_path)
    members = [_install_member(tmp_path / 'alpha', ALPHA, alpha_request, 'registered-alpha', wheelhouse, rows, requirements, monkeypatch),
               _install_member(tmp_path / 'queue', QUEUE, queue_request, 'work-queue', wheelhouse, rows, requirements, monkeypatch)]
    primitive = derive_installed_packages_binding(members, source_root=str(tmp_path))
    owner, source_plan, transaction, original, request = _install_owner(tmp_path / 'owner', tmp_path,
        members, primitive, wheelhouse, rows, requirements)
    binding = derive_owned_packages_binding(members, owner, source_root=str(tmp_path))
    assert len({member['site'] for member in binding['members'].values()}) == 2
    assert set(binding['distributions']) == {'jev-independent-registered-alpha', 'jev-independent-work-queue'}
    assert binding['owner']['site'] not in {member['site'] for member in binding['members'].values()}
    assert all(any(row['path'].endswith('/' + package + '/__init__.py') for row in binding['source_plan']['files'])
               for package in ('registered_alpha', 'work_queue'))
    private, public = _issuer(tmp_path)
    cert, cert_key = tmp_path / 'loopback.crt', tmp_path / 'loopback.key'
    result = subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
        '-keyout', str(cert_key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
        '-addext', 'subjectAltName=IP:127.0.0.1', '-days', '1'], capture_output=True, timeout=20)
    assert result.returncode == 0
    cert.chmod(0o600); cert_key.chmod(0o600)
    calls = []
    class LocalTypeSafe(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(digest(payload))
            answers = synthetic_typed_answers(payload['questions'], 'alternative')
            raw = json.dumps({'model': payload['model'], 'answers': answers,
                              'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), LocalTypeSafe)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(str(cert), str(cert_key))
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    cutoff = datetime.now(timezone.utc) + timedelta(minutes=10)
    monkeypatch.setenv('TYPESAFE_API_KEY', 'fake-offline-independent-packages-key')
    specs = {name: _literal_spec(Path(member['origins']['adapter']['path']))
             for name, member in binding['members'].items()}
    assert all(spec['runtime']['configuration']['timeout_ms'] == 10_000
               for spec in specs.values())
    covered = {row['path']: row['sha256'] for row in binding['source_plan']['files']}
    dependencies = {'files': sorted([{'path': str(Path(member['origins']['host']['path']).parent / filename),
        'sha256': covered[str(Path(member['origins']['host']['path']).parent / filename)]}
        for member in binding['members'].values() for filename in ('requirements.lock', 'runtime.json')], key=lambda row: row['path'])}
    source_bindings = {name: {'reviewed_file_sha256': member['reviewed_file_sha256'],
        'applied_file_sha256': member['applied_file_sha256'], 'adapter_path': member['origins']['adapter']['wheel_member'],
        'adapter_sha256': member['origins']['adapter']['sha256']} for name, member in binding['members'].items()}
    environment_digest = planned_environment_digest(binding['owner'], public_key_file=str(public),
        certificate_file=str(cert), credential_present=True)
    config = {'endpoint': f'https://127.0.0.1:{server.server_address[1]}', 'credential_ref': 'env:TYPESAFE_API_KEY',
        'model': 'jev-1.13.0', 'environment_digest': environment_digest, 'source_root': binding['site'],
        'source_plan': binding['source_plan'], 'source_bindings': source_bindings, 'installed_binding': binding}
    sessions = []
    def prepare(label, ledger, per_task=2, reuse=None):
        folder = tmp_path / label; folder.mkdir(mode=0o700)
        alpha = (folder if reuse is None else reuse) / 'alpha.jsonl'
        queue = (folder if reuse is None else reuse) / 'queue.jsonl'
        ready, release, audit = folder / 'ready', folder / 'release', folder / 'audit.json'
        limits = {'max_calls_per_task': per_task, 'max_cost_per_task': 2, 'max_total_calls': 3,
                  'max_total_cost': 3, 'max_in_flight': 1, 'max_tasks': 2}
        grant = {'endpoint': config['endpoint'], 'credential_ref': config['credential_ref'], 'model': config['model'],
            'environment_digest': environment_digest, 'source_digest': digest({'root': binding['site'],
                'plan': binding['source_plan'], 'bindings': source_bindings, 'installed_binding_sha256': binding['binding_sha256']}),
            'dependency_digest': digest(dependencies), 'budget_digest': digest(limits),
            'adapters_digest': digest({name: digest(spec) for name, spec in specs.items()}), 'mode': 'shadow',
            'issued_at': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), 'expires_at': cutoff.isoformat()}
        reference = folder / 'reference.json'
        reference.write_text(json.dumps({'schema_version': '1.0', 'mode': 'shadow', 'connected_config': config,
            'authority': {'egress_grant': grant, 'activation': None}, 'ledger_path': str(ledger),
            'signatures': {'installed_binding': _issue(private, 'installed_binding', binding['binding_sha256']),
                           'egress_grant': _issue(private, 'egress_grant', digest(grant))}}))
        reference.chmod(0o600)
        environment = {'PACKAGES_OWNER_CONNECTED_REF': str(reference), 'PACKAGES_OWNER_AUTH_PUBKEY_FILE': str(public),
            'PACKAGES_OWNER_READY_PATH': str(ready), 'PACKAGES_OWNER_RELEASE_PATH': str(release),
            'PACKAGES_OWNER_AUDIT_PATH': str(audit), 'PACKAGES_OWNER_HOLD': '1',
            'REGISTERED_ALPHA_EFFECTS': str(alpha), 'WORK_QUEUE_EFFECTS': str(queue), 'SSL_CERT_FILE': str(cert)}
        observed = queue if reuse is None else folder / 'never-replayed.jsonl'
        raw_queue = _raw({'job_id': TASK, 'operation': 'enqueue', 'item': 'batch-a'})
        plan = plan_connected_delivery(owner['install_plan'],
            trusted_install_receipt_sha256=owner['trusted_install_receipt_sha256'],
            trusted_package_receipt_sha256=owner['trusted_package_receipt_sha256'],
            installed_binding=binding, trusted_binding_sha256=binding['binding_sha256'],
            observation=_observation(ready, b'ready\n', observed, raw_queue), launch_environment=environment,
            host_profile='registered-alpha-queue-pair-v1')
        return folder, plan, limits, alpha, queue, ready, release, audit
    def launch(stage, name, expect_ready):
        folder, plan, limits, alpha, queue, ready, release, audit = stage
        session = tmp_path / name
        status = create_connected_session(session, plan, approved_plan_sha256=plan['plan_sha256'])
        sessions.append((session, plan))
        scope = _scope(status, plan, 'launch', cutoff, 'PACKAGES_OWNER_AUTH_PUBKEY_FILE')
        launch_connected_session(session, scope=scope, approved_scope_sha256=scope['scope_sha256'])
        if expect_ready:
            deadline = time.monotonic() + 30
            while not ready.exists():
                assert time.monotonic() < deadline, 'normal owner did not reach both integrations'
                time.sleep(.02)
            assert ready.read_bytes() == b'ready\n'
            release.write_bytes(b'go\n')
        status = _exited(session)
        scope = _scope(status, plan, 'stop', cutoff, 'PACKAGES_OWNER_AUTH_PUBKEY_FILE')
        stopped = stop_connected_session(session, scope=scope, approved_scope_sha256=scope['scope_sha256'])
        assert stopped['stage'] == 'stopped'
        return read_json(audit)
    try:
        ledger = tmp_path / 'common.ledger'
        first = prepare('first-effects', ledger)
        _refuse_installed_owner_escalation(owner, first[1], ledger)
        assert calls == []
        audit = launch(first, 'first-session', True)
        assert len(calls) == 2
        assert set(audit['assessed']) == set(binding['candidate_ids'])
        assert audit['ledger']['calls'] == 2 and audit['ledger']['closed_tasks'] == 1
        assert not audit['ledger']['suspended']
        assert audit['prefix'] == str(Path(owner['install_receipt']['environment']) / 'venv')
        assert audit['evaluator_origin'] == binding['owner']['origins']['evaluator']['path']
        assert first[3].read_bytes() == _raw({'task_id': TASK, 'action': 'inspect', 'item': 'fixture-one'})
        assert first[4].read_bytes() == _raw({'job_id': TASK, 'operation': 'enqueue', 'item': 'batch-a'})
        raw_before = {path: path.read_bytes() for path in first[0].iterdir() if path.is_file()}
        identity = _durable_identity(ledger)
        retained = RuntimeLedger(ledger, identity=identity, **first[2])
        try:
            history = retained.generation_snapshot()
            for name, member in binding['members'].items():
                alpha_member = member['source_file'].endswith('/host.py')
                payload = request['alpha_request' if alpha_member else 'queue_request']
                operation = 'owner:public_entry' if alpha_member else 'owner:handle_job'
                key = digest([identity, digest(TASK), digest(payload), name, operation])
                assert [key, 'completed'] in history['effects']
                with pytest.raises(InputError, match='^runtime_effect_already_claimed$'):
                    retained.claim_effect(TASK, digest(payload), name, operation)
        finally:
            retained.release()
        replay = prepare('retained-replay', ledger, reuse=first[0])
        denied = launch(replay, 'retained-session', False)
        assert denied['types'].count('runtime_route_refusal') == 2
        assert {name for name in denied['candidates'] if name is not None} == set(binding['candidate_ids'])
        assert denied['ledger']['calls'] == 2 < first[2]['max_total_calls']
        assert not denied['ledger']['suspended'] and len(calls) == 2
        assert all(path.read_bytes() == raw for path, raw in raw_before.items())
        limited = prepare('limited-effects', tmp_path / 'limited.ledger', per_task=1)
        limited_audit = launch(limited, 'limited-session', True)
        assert len(calls) == 3 and len(limited_audit['assessed']) == 1
        assert limited_audit['ledger']['calls'] == 1
        assert limited_audit['ledger']['denials']['shared_task_call_budget'] == 1
        assert limited[3].read_bytes() == first[3].read_bytes()
        assert limited[4].read_bytes() == first[4].read_bytes()
        owner_plan_path = tmp_path / 'owner/owner-source-plan.json'
        transaction_receipt_path = Path(transaction['transaction_directory']) / 'receipt.json'
        source_status = _owner_cli('packages-owner-status', '--plan', str(owner_plan_path),
            '--receipt', str(transaction_receipt_path), '--trusted-receipt-sha256', transaction['receipt_sha256'])
        assert source_status['status'] == 'applied_externally_anchored'
        rolled = _owner_cli('packages-owner-rollback', '--plan', str(owner_plan_path),
            '--receipt', str(transaction_receipt_path), '--trusted-receipt-sha256', transaction['receipt_sha256'],
            '--approve-plan-sha256', source_plan['plan_sha256'])
        assert rolled['action'] == 'rolled_back'
        assert (Path(source_plan['owner_root']) / source_plan['owner_file']).read_text() == original
        retained = RuntimeLedger(ledger, identity=identity, **first[2])
        try:
            assert retained.generation_snapshot() == history
        finally:
            retained.release()
        assert len(calls) == 3
    finally:
        for session, plan in sessions:
            status = connected_session_status(session)
            if status['stage'] != 'stopped':
                scope = _scope(status, plan, 'stop', cutoff, 'PACKAGES_OWNER_AUTH_PUBKEY_FILE')
                stop_connected_session(session, scope=scope, approved_scope_sha256=scope['scope_sha256'])
        server.shutdown(); server.server_close(); thread.join(timeout=5)
