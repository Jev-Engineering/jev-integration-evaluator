"""Host owned, stopped connected generation transfer for one installed console.

This module reads reviewed installed bytes. It never imports a target module,
launches a console, creates provider authority, or resets a runtime ledger.
"""
from __future__ import annotations

import ast
import base64
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import ssl
import stat
import subprocess
import sys
import tempfile

from .contracts import parse_utc, validate_contract
from .io import InputError, digest, file_hash, read_json
from .integrations.runtime_ledger import RuntimeLedger
from .integrations.runtime_lifecycle import check_dependency_plan
from . import template_connected_delivery as delivery
from .template_connected_binding import derive_installed_binding


class ConnectedGenerationError(InputError):
    """Fixed diagnostic without source, credential, or private grant content."""


_OPENSSL = Path('/usr/bin/openssl')
_OPENSSL_ENV = {'LANG': 'C', 'OPENSSL_CONF': os.devnull,
                'OPENSSL_MODULES': '/nonexistent', 'OPENSSL_ENGINES': '/nonexistent'}


def _verify(public: Path, kind: str, exact: str, signature: str) -> bool:
    """Verify a detached P-256 signature with the fixed host verifier."""
    try:
        info = _OPENSSL.stat()
        if (_OPENSSL.is_symlink() or not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022
                or len(signature) > 8192):
            return False
        version = subprocess.run([str(_OPENSSL), 'version'], capture_output=True,
                                 timeout=2, env=_OPENSSL_ENV, check=False)
        if version.returncode or not version.stdout.startswith(b'OpenSSL 3.'):
            return False
        pem = public.read_bytes()
        if (len(pem) > 4096 or not pem.startswith(b'-----BEGIN PUBLIC KEY-----\n')
                or b'PRIVATE KEY' in pem):
            return False
        key_info = subprocess.run([str(_OPENSSL), 'pkey', '-pubin', '-text', '-noout'],
                                  input=pem, capture_output=True,
                                  timeout=2, env=_OPENSSL_ENV, check=False)
        if (key_info.returncode or len(key_info.stdout) > 4096
                or b'Public-Key: (256 bit)' not in key_info.stdout
                or b'ASN1 OID: prime256v1' not in key_info.stdout):
            return False
        raw = base64.b64decode(signature, validate=True)
        with tempfile.TemporaryFile(mode='w+b') as stream:
            stream.write(raw)
            stream.flush()
            result = subprocess.run([str(_OPENSSL), 'dgst', '-sha256', '-verify',
                                     str(public), '-signature',
                                     f'/proc/self/fd/{stream.fileno()}'],
                                    input=(kind + ':' + exact).encode('ascii'),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    pass_fds=(stream.fileno(),), timeout=2,
                                    env=_OPENSSL_ENV, check=False)
        return result.returncode == 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def _literal_spec(path: Path) -> dict:
    try:
        tree = ast.parse(path.read_bytes(), filename='<installed-adapter>')
        nodes = [node.value for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'SPEC'
                         for target in node.targets)]
        if len(nodes) != 1:
            raise ValueError()
        spec = ast.literal_eval(nodes[0])
        if type(spec) is not dict:
            raise ValueError()
        return spec
    except (OSError, SyntaxError, ValueError, TypeError, RecursionError):
        raise ConnectedGenerationError('connected_generation_adapter_spec_unavailable') from None


def _verifier_identity() -> dict:
    try:
        info = _OPENSSL.stat()
        version = subprocess.run([str(_OPENSSL), 'version'], capture_output=True,
                                 timeout=2, env=_OPENSSL_ENV, check=False)
        if (_OPENSSL.is_symlink() or not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022
                or version.returncode or len(version.stdout) > 256
                or not version.stdout.startswith(b'OpenSSL 3.')):
            raise ValueError()
        return {'path': str(_OPENSSL), 'sha256': file_hash(_OPENSSL),
                'version': version.stdout.decode('ascii').strip()}
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        raise ConnectedGenerationError('connected_generation_verifier_invalid') from None


def _installed(plan: dict, dependency_plan: dict, limits: dict) -> dict:
    # The old session has already produced its scheduled effects, so replaying
    # the prelaunch observation-baseline check would reject a valid stopped run.
    # Recompute immutable installed provenance and current source/reference
    # bytes here; the prospective child gets the full fresh-plan check below.
    validate_contract(plan, 'connected-delivery-plan-v1')
    if plan.get('host_profile') is not None:
        raise ConnectedGenerationError('connected_generation_profile_not_supported')
    if digest({key: value for key, value in plan.items() if key != 'plan_sha256'}) != plan['plan_sha256']:
        raise ConnectedGenerationError('connected_generation_plan_changed')
    binding = plan['installed_binding']
    base = plan['off_provenance']
    receipt = delivery.offline._receipt(base['install_plan'],
                                         base['trusted_install_receipt_sha256'])
    actual = derive_installed_binding(base['install_plan']['package_plan'],
        base['install_plan']['package_receipt'], base['install_plan'], receipt,
        trusted_package_receipt_sha256=plan['trusted_package_receipt_sha256'],
        trusted_install_receipt_sha256=base['trusted_install_receipt_sha256'])
    if (actual != binding or actual['binding_sha256'] != plan['trusted_binding_sha256']
            or 'loader' not in actual['origins']):
        raise ConnectedGenerationError('connected_generation_installed_binding_changed')
    for row in binding['source_plan']['files']:
        if file_hash(Path(row['path'])) != row['sha256']:
            raise ConnectedGenerationError('connected_generation_installed_source_changed')
    for name, expected in plan['reference_sha256'].items():
        path = Path(base['launch_environment'][name])
        delivery._check_reference(str(path))
        if file_hash(path) != expected:
            raise ConnectedGenerationError('connected_generation_reference_changed')
    config_path = Path(plan['off_provenance']['launch_environment']['REGISTERED_ALPHA_CONNECTED_REF'])
    public = Path(plan['off_provenance']['launch_environment']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'])
    delivery._check_reference(str(config_path))
    delivery._check_reference(str(public))
    if file_hash(public) != plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE']:
        raise ConnectedGenerationError('connected_generation_public_key_changed')
    manifest = read_json(config_path)
    if (type(manifest) is not dict or set(manifest) !=
            {'schema_version', 'mode', 'connected_config', 'authority', 'ledger_path', 'signatures'}
            or manifest['schema_version'] != '1.0' or manifest['mode'] != 'shadow'
            or type(manifest['signatures']) is not dict):
        raise ConnectedGenerationError('connected_generation_reference_invalid')
    config = manifest['connected_config']
    authority = manifest['authority']
    validate_contract(config, 'host-runtime-connected-v1')
    validate_contract(authority, 'host-runtime-connected-v1')
    if (type(config) is not dict or type(authority) is not dict
            or type(authority.get('egress_grant')) is not dict
            or config.get('installed_binding') != binding
            or config.get('source_plan') != binding['source_plan']
            or config.get('source_root') != binding['site']
            or type(config.get('source_bindings')) is not dict
            or set(config['source_bindings']) != {binding['candidate_id']}
            or type(limits) is not dict):
        raise ConnectedGenerationError('connected_generation_runtime_binding_changed')
    cert = base['launch_environment'].get('SSL_CERT_FILE')
    environment_digest = digest({
        'python': str(Path(receipt['installed']['python']).resolve()),
        'version': list(sys.version_info[:3]),
        'implementation': platform.python_implementation(),
        'openssl': ssl.OPENSSL_VERSION,
        'signature_verifier': _verifier_identity(),
        'public_key_sha256': file_hash(public),
        'cert_sha256': file_hash(Path(cert)) if cert else None,
        'credential_present': True})
    if config['environment_digest'] != environment_digest:
        raise ConnectedGenerationError('connected_generation_environment_changed')
    check_dependency_plan(dependency_plan)
    if (digest(dependency_plan) != authority['egress_grant'].get('dependency_digest')
            or digest(limits) != authority['egress_grant'].get('budget_digest')
            or not _verify(public, 'installed_binding', binding['binding_sha256'],
                           manifest['signatures'].get('installed_binding', ''))
            or not _verify(public, 'egress_grant', digest(authority['egress_grant']),
                           manifest['signatures'].get('egress_grant', ''))):
        raise ConnectedGenerationError('connected_generation_runtime_authority_unverified')
    spec = _literal_spec(Path(binding['origins']['adapter']['path']))
    candidate = binding['candidate_id']
    bound = config['source_bindings'][candidate]
    if (spec.get('candidate_id') != candidate
            or spec.get('source', {}).get('file') != binding['source_file']
            or spec['source'].get('file_sha256') != binding['reviewed_file_sha256']
            or bound != {'reviewed_file_sha256': binding['reviewed_file_sha256'],
                         'applied_file_sha256': binding['applied_file_sha256'],
                         'adapter_path': binding['origins']['adapter']['wheel_member'],
                         'adapter_sha256': binding['origins']['adapter']['sha256']}):
        raise ConnectedGenerationError('connected_generation_adapter_binding_changed')
    expected = {'endpoint': config['endpoint'], 'credential_ref': config['credential_ref'],
                'model': config['model'], 'environment_digest': config['environment_digest'],
                'source_digest': digest({'root': binding['site'], 'plan': binding['source_plan'],
                                         'bindings': config['source_bindings'],
                                         'installed_binding_sha256': binding['binding_sha256']}),
                'dependency_digest': digest(dependency_plan), 'budget_digest': digest(limits),
                'adapters_digest': digest({candidate: digest(spec)}), 'mode': 'shadow'}
    if any(authority['egress_grant'].get(name) != value for name, value in expected.items()):
        raise ConnectedGenerationError('connected_generation_egress_binding_changed')
    identity = digest({'adapters': {candidate: digest(spec)},
                       'configuration': config, 'dependency_plan': dependency_plan,
                       'budget_limits': limits})
    ledger = Path(manifest['ledger_path'])
    if (not ledger.is_absolute() or any(part.is_symlink() for part in (ledger, *ledger.parents))
            or not ledger.parent.is_dir()):
        raise ConnectedGenerationError('connected_generation_ledger_path_invalid')
    delivery.offline._private(ledger.parent)
    return {'identity': identity, 'placement': candidate, 'ledger': ledger,
            'binding_sha256': binding['binding_sha256'], 'public': public,
            'egress_expires_at': authority['egress_grant']['expires_at']}


def _stopped(directory: str | Path, trusted_head: str) -> tuple[dict, dict]:
    _, rows, state, plan = delivery._open(directory)
    result = delivery.connected_session_status(directory, trusted_session_head=trusted_head)
    if (rows[-1]['record_sha256'] != trusted_head or state['stage'] != 'stopped'
            or state['pending'] is not None or result['process_alive']
            or 'launch_effect_unknown' in state['failures']
            or not result['installed_sources_current'] or not result['private_references_current']):
        raise ConnectedGenerationError('connected_generation_stopped_session_required')
    return state, plan


def plan_connected_generation_transfer(old_session: str | Path, new_plan: dict,
        *, trusted_old_head: str, old_dependency_plan: dict, new_dependency_plan: dict,
        limits: dict, action: str, issued_at: str, expires_at: str) -> dict:
    """Derive an unsigned exact grant from stopped installed sources and ledger."""
    delivery.offline._linux_profile()
    old_state, old_plan = _stopped(old_session, trusted_old_head)
    delivery._check_plan(new_plan)
    old = _installed(old_plan, old_dependency_plan, limits)
    new = _installed(new_plan, new_dependency_plan, limits)
    cutoff = old_state.get('generation_parent', {}).get('original_expires_at',
                                                         old['egress_expires_at'])
    now = datetime.now(timezone.utc)
    if (action not in ('upgrade', 'rollback') or old['identity'] == new['identity']
            or old['ledger'] != new['ledger'] or old['public'] != new['public']
            or parse_utc(new['egress_expires_at']) > parse_utc(cutoff)
            or not parse_utc(issued_at) <= now < parse_utc(expires_at)
            or parse_utc(expires_at) > min(parse_utc(cutoff),
                                           parse_utc(new['egress_expires_at']))):
        raise ConnectedGenerationError('connected_generation_scope_invalid')
    ledger = RuntimeLedger(old['ledger'], identity=old['identity'], **limits)
    try:
        history = digest(ledger.generation_snapshot())
    finally:
        ledger.release()
    grant = {'schema_version': '1.0', 'kind': 'connected-generation-transfer-v1',
             'action': action, 'old_identity': old['identity'],
             'new_identity': new['identity'],
             'old_plan_sha256': old_plan['plan_sha256'],
             'new_plan_sha256': new_plan['plan_sha256'],
             'old_binding_sha256': old['binding_sha256'],
             'new_binding_sha256': new['binding_sha256'],
             'session_head_sha256': trusted_old_head,
             'history_sha256': history, 'limits': copy.deepcopy(limits),
             'old_placements': [old['placement']],
             'new_to_old_placements': {new['placement']: old['placement']},
             'issued_at': issued_at, 'expires_at': expires_at}
    validate_contract(grant, 'connected-generation-transfer-v1')
    return grant


def _authority(plan: dict, grant: dict, signature_file: str | Path):
    binding = plan['installed_binding']
    public = Path(plan['off_provenance']['launch_environment']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE'])
    delivery._check_reference(str(public))
    if file_hash(public) != plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE']:
        raise ConnectedGenerationError('connected_generation_public_key_changed')
    signature_file = Path(signature_file)
    delivery._check_reference(str(signature_file))
    try:
        signature = signature_file.read_text(encoding='ascii')
    except (OSError, UnicodeError):
        raise ConnectedGenerationError('connected_generation_signature_invalid') from None
    if (binding['binding_sha256'] != grant['old_binding_sha256']
            or not _verify(public, 'generation_transfer', digest(grant), signature)):
        raise ConnectedGenerationError('connected_generation_transfer_unverified')
    signature_sha256 = file_hash(signature_file)
    verifier_sha256 = file_hash(_OPENSSL)
    def verify(kind: str, exact: str) -> bool:
        try:
            delivery._check_reference(str(public))
            delivery._check_reference(str(signature_file))
            return (kind == 'generation_transfer' and exact == digest(grant)
                    and file_hash(public) == plan['reference_sha256']['REGISTERED_ALPHA_AUTH_PUBKEY_FILE']
                    and file_hash(signature_file) == signature_sha256
                    and file_hash(_OPENSSL) == verifier_sha256
                    and _verify(public, kind, exact, signature_file.read_text(encoding='ascii')))
        except (OSError, UnicodeError, InputError):
            return False
    return verify


def transfer_connected_generation(old_session: str | Path, new_session: str | Path,
        new_plan: dict, *, trusted_old_head: str, approved_new_plan_sha256: str,
        old_dependency_plan: dict, new_dependency_plan: dict, grant: dict,
        signature_file: str | Path) -> dict:
    """Prepare one inert child, transfer the same ledger, then unlock startup."""
    validate_contract(grant, 'connected-generation-transfer-v1')
    old_state, old_plan = _stopped(old_session, trusted_old_head)
    verify = _authority(old_plan, grant, signature_file)
    expected = plan_connected_generation_transfer(old_session, new_plan,
        trusted_old_head=trusted_old_head, old_dependency_plan=old_dependency_plan,
        new_dependency_plan=new_dependency_plan, limits=grant['limits'], action=grant['action'],
        issued_at=grant['issued_at'], expires_at=grant['expires_at'])
    if grant != expected or new_plan['plan_sha256'] != approved_new_plan_sha256:
        raise ConnectedGenerationError('connected_generation_exact_grant_required')
    old = _installed(old_plan, old_dependency_plan, grant['limits'])
    parent = {'run_id': old_state['run_id'], 'old_plan_sha256': old_plan['plan_sha256'],
              'old_session_head_sha256': trusted_old_head, 'grant_sha256': digest(grant),
              'action': grant['action'], 'original_expires_at': old_state.get(
                  'generation_parent', {}).get('original_expires_at', old['egress_expires_at']),
              'failure_history': list(old_state['failures'])}
    child = Path(new_session)
    if child.exists():
        _, _, state, plan = delivery._open(child)
        if (state.get('generation_parent') != parent or plan != new_plan
                or state['stage'] != 'generation_pending'):
            raise ConnectedGenerationError('connected_generation_child_changed')
    else:
        delivery.create_connected_session(child, new_plan,
            approved_plan_sha256=approved_new_plan_sha256, generation_parent=parent)
    receipt = RuntimeLedger.transfer_generation(old['ledger'], grant=grant,
                                                 verify_authority=verify)
    result = reconcile_connected_generation(old_session, new_session, grant=grant,
        signature_file=signature_file, trusted_old_head=trusted_old_head)
    return {'ledger_receipt': receipt, 'child': result}


def connected_generation_status(old_session: str | Path, new_session: str | Path,
        *, grant: dict, signature_file: str | Path, trusted_old_head: str) -> dict:
    """Read exact old/new journal and durable ledger receipt without replay."""
    validate_contract(grant, 'connected-generation-transfer-v1')
    old_state, old_plan = _stopped(old_session, trusted_old_head)
    verify = _authority(old_plan, grant, signature_file)
    _, rows, state, new_plan = delivery._open(new_session)
    parent = state.get('generation_parent')
    if (parent is None or parent['run_id'] != old_state['run_id']
            or parent['old_plan_sha256'] != old_plan['plan_sha256']
            or grant['old_plan_sha256'] != old_plan['plan_sha256']
            or grant['new_plan_sha256'] != new_plan['plan_sha256']
            or parent['old_session_head_sha256'] != trusted_old_head
            or parent['grant_sha256'] != digest(grant)
            or parent['action'] != grant['action']
            or new_plan['installed_binding']['binding_sha256'] != grant['new_binding_sha256']):
        raise ConnectedGenerationError('connected_generation_child_changed')
    old_reference = read_json(Path(old_plan['off_provenance']['launch_environment'][
        'REGISTERED_ALPHA_CONNECTED_REF']))
    status = RuntimeLedger.generation_transfer_status(old_reference['ledger_path'],
        grant=grant, verify_authority=verify)
    result = {'kind': 'connected-generation-status-v1', 'run_id': old_state['run_id'],
              'grant_sha256': digest(grant), 'ledger': status,
              'child_stage': state['stage'], 'child_head_sha256': rows[-1]['record_sha256']}
    validate_contract(result, 'connected-generation-status-v1')
    return result


def reconcile_connected_generation(old_session: str | Path, new_session: str | Path,
        *, grant: dict, signature_file: str | Path, trusted_old_head: str) -> dict:
    """Finish only an already committed cutover; never repeat the transfer."""
    status = connected_generation_status(old_session, new_session, grant=grant,
        signature_file=signature_file, trusted_old_head=trusted_old_head)
    if status['ledger']['status'] != 'committed':
        return status
    _, old_plan = _stopped(old_session, trusted_old_head)
    verify = _authority(old_plan, grant, signature_file)
    old_reference = read_json(Path(old_plan['off_provenance']['launch_environment'][
        'REGISTERED_ALPHA_CONNECTED_REF']))
    def activate(ledger_status: dict) -> None:
        if (ledger_status['current_identity'] != grant['new_identity']
                or ledger_status['current_generation_grant_sha256'] != digest(grant)
                or ledger_status['current_history_sha256'] != ledger_status['receipt']['after_sha256']):
            raise ConnectedGenerationError('connected_generation_stale_transfer')
        child = delivery.offline._safe_directory(new_session, exists=True)
        with delivery._locked(child):
            _, rows, state, plan = delivery._open(child)
            if (plan['plan_sha256'] != grant['new_plan_sha256']
                    or state.get('generation_parent', {}).get('grant_sha256') != digest(grant)):
                raise ConnectedGenerationError('connected_generation_child_changed')
            if state['stage'] == 'generation_pending':
                state['stage'] = 'installed'
                delivery._event(child, rows, 'generation_committed', state)
            elif state['stage'] != 'installed':
                raise ConnectedGenerationError('connected_generation_child_changed')
    RuntimeLedger.generation_transfer_status(old_reference['ledger_path'],
        grant=grant, verify_authority=verify, on_current=activate)
    return connected_generation_status(old_session, new_session, grant=grant,
        signature_file=signature_file, trusted_old_head=trusted_old_head)
