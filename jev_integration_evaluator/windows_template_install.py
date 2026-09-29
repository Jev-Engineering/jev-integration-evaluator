"""Offline native Windows install generation for an exact reviewed package."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from . import capabilities as cap
from .contracts import validate_contract
from .io import InputError, digest, file_hash, loads
from .windows_template_owned import (
    check_private_directory, create_private_directory, read_private_json,
    write_private_bytes_exclusive, write_private_json_exclusive,
)
from .windows_template_package_inputs import inspect_windows_template_package_inputs
from .windows_template_plan import (
    _effect_environment, _generation as _package_generation,
    _requirements_lock, _run, plan_windows_template_package,
    windows_package_status,
)
from .windows_template_owned import acl_sha256
from .windows_template_tree import installed_tree_snapshot


def _generation(plan: dict) -> Path:
    return Path(plan['package_plan']['request']['environment_parent']) / (
        'jev-env-' + plan['plan_sha256'][:24])


def _owned_package_receipt(package_plan: dict, trusted_sha256: str) -> dict:
    """Read the package receipt from the plan-derived private generation."""
    root = _package_generation(package_plan)
    try:
        owner = loads(cap._windows_secure_input(root / 'owner.json', 1_000_000))
        owned = owner['owned_directory']
        check_private_directory(owned)
        if owner['plan_sha256'] != package_plan['plan_sha256'] or owned['path'] != str(root):
            raise InputError('windows_install_package_receipt_unavailable')
        canonical = read_private_json(owned, 'package-receipt.json')
    except (OSError, KeyError, TypeError, ValueError, cap.CapabilityError):
        raise InputError('windows_install_package_receipt_unavailable') from None
    validate_contract(canonical, 'windows-template-package-receipt-v1')
    if (canonical['owned_directory'] != owned
            or canonical['package_directory'] != str(root)
            or canonical['plan_sha256'] != package_plan['plan_sha256']
            or canonical['receipt_sha256'] != trusted_sha256
            or digest({key: value for key, value in canonical.items()
                       if key != 'receipt_sha256'}) != trusted_sha256):
        raise InputError('windows_install_package_receipt_unverified')
    return canonical


def owned_windows_install_receipt(plan: dict, trusted_sha256: str) -> dict:
    """Return the exact private installed receipt after full read-only status."""
    status = windows_install_status(plan, trusted_receipt_sha256=trusted_sha256)
    if (status['status'] != 'installed_recorded'
            or status['receipt_trust'] != 'externally_anchored'):
        raise InputError('windows_session_install_unverified')
    root = _generation(plan)
    try:
        owner = loads(cap._windows_secure_input(root / 'owner.json', 1_000_000))
        owned = owner['owned_directory']
        check_private_directory(owned)
        if owner['plan_sha256'] != plan['plan_sha256'] or owned['path'] != str(root):
            raise InputError('windows_session_install_receipt_unavailable')
        canonical = read_private_json(owned, 'install-receipt.json')
    except (OSError, KeyError, TypeError, ValueError, cap.CapabilityError):
        raise InputError('windows_session_install_receipt_unavailable') from None
    validate_contract(canonical, 'windows-template-install-receipt-v1')
    expected_python = root / 'venv' / 'Scripts' / 'python.exe'
    expected_console = (root / 'venv' / 'Scripts' /
                        (plan['package_plan']['inputs']['console_script'] + '.exe'))
    if (canonical['receipt_sha256'] != trusted_sha256
            or digest({key: value for key, value in canonical.items()
                       if key != 'receipt_sha256'}) != trusted_sha256
            or canonical['plan_sha256'] != plan['plan_sha256']
            or canonical['owned_directory'] != owned
            or canonical['environment'] != str(root)
            or canonical['installed']['python'] != str(expected_python)
            or canonical['installed']['console_script'] != str(expected_console)):
        raise InputError('windows_session_install_receipt_unverified')
    return canonical


def plan_windows_template_install(package_plan: dict, package_receipt: dict,
                                  *, trusted_package_receipt_sha256: str) -> dict:
    """Plan one native Scripts/python.exe generation after anchored package build."""
    validate_contract(package_plan, 'windows-template-package-plan-v1')
    validate_contract(package_receipt, 'windows-template-package-receipt-v1')
    status = windows_package_status(package_plan,
                                    trusted_receipt_sha256=trusted_package_receipt_sha256)
    canonical = _owned_package_receipt(package_plan, trusted_package_receipt_sha256)
    if (package_plan != plan_windows_template_package(package_plan['request'])
            or trusted_package_receipt_sha256 != package_receipt['receipt_sha256']
            or status['status'] != 'built_recorded'
            or status['receipt_trust'] != 'externally_anchored'
            or status['receipt_sha256'] != package_receipt['receipt_sha256']
            or package_receipt != canonical):
        raise InputError('windows_install_package_unverified')
    config = package_plan['request']['configuration']
    if config['jev_runtime']['mode'] != 'off':
        raise InputError('windows_install_off_mode_required')
    body = {'schema_version': '1.0', 'kind': 'windows-template-install-plan-v1',
            'package_plan': package_plan, 'package_receipt': package_receipt,
            'trusted_package_receipt_sha256': trusted_package_receipt_sha256,
            'operations': ['create_private_venv', 'install_hash_checked_wheels',
                           'verify_installed_record_and_console', 'write_off_configuration'],
            'runtime_activation_authorized': False}
    body['plan_sha256'] = digest(body)
    validate_contract(body, 'windows-template-install-plan-v1')
    return body


_VERIFY = '''import base64,hashlib,importlib,importlib.metadata as m,json,sys
from pathlib import Path
expected=json.loads(sys.argv[1]); entry=json.loads(sys.argv[2]); base=Path(sys.prefix).resolve()
if base!=Path(sys.argv[3]).resolve(): raise RuntimeError('venv origin')
out={}; files={}
for name,version in expected.items():
    dist=m.distribution(name); origin=Path(dist.locate_file('')).resolve()
    if dist.version!=version or not origin.is_relative_to(base): raise RuntimeError('distribution origin')
    if dist.files is None: raise RuntimeError('RECORD absent')
    for item in dist.files:
        path=Path(dist.locate_file(item)).resolve()
        if not path.is_relative_to(base) or not path.is_file(): raise RuntimeError('RECORD path')
        raw=path.read_bytes()
        if item.size is not None and len(raw)!=item.size: raise RuntimeError('RECORD size')
        if item.hash is not None:
            if item.hash.mode!='sha256': raise RuntimeError('RECORD hash type')
            actual=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
            if actual!=item.hash.value: raise RuntimeError('RECORD hash')
        files[path.relative_to(base).as_posix()]=hashlib.sha256(raw).hexdigest()
    out[name]={'version':dist.version,'origin':str(origin)}
host=m.distribution(entry['distribution'])
matches=[e for e in host.entry_points if e.group=='console_scripts' and e.name==entry['script']]
if len(matches)!=1 or matches[0].value!=entry['value']: raise RuntimeError('entrypoint metadata')
module_name,qualifier=entry['value'].split(':',1)
relative=module_name.replace('.','/')
candidates=[Path(host.locate_file(item)).resolve() for item in host.files
            if Path(item).as_posix().endswith(relative+'.py')
            or Path(item).as_posix().endswith(relative+'/__init__.py')]
if len(candidates)!=1 or not candidates[0].is_relative_to(base): raise RuntimeError('entrypoint origin')
if sys.argv[4]=='1':
    module=importlib.import_module(module_name)
    if Path(module.__file__).resolve()!=candidates[0]: raise RuntimeError('entry module origin')
    target=module
    for component in qualifier.split('.'): target=getattr(target,component)
    if not callable(target): raise RuntimeError('entry target')
print(json.dumps({'distributions':out,'files_sha256':files,'entrypoint_origin':str(candidates[0])}))'''


def _verify_environment(plan: dict, root: Path, *, import_entry: bool) -> dict:
    package = plan['package_plan']
    receipt = plan['package_receipt']
    venv = root / 'venv'
    python = venv / 'Scripts/python.exe'
    script = venv / 'Scripts' / (package['inputs']['console_script'] + '.exe')
    for path in (python, script):
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise InputError('windows_install_executable_missing_or_linked')
    if loads(cap._windows_secure_input(root / 'config.json', 100_000)) != package['request']['configuration']:
        raise InputError('windows_install_configuration_drift')
    versions = {row['name']: row['version'] for row in package['inputs']['wheel_files']}
    versions[package['inputs']['project_name']] = package['inputs']['project_version']
    entry = {'distribution': package['inputs']['project_name'],
             'script': package['inputs']['console_script'],
             'value': package['inputs']['entry_point']}
    try:
        output = subprocess.run([str(python), '-I', '-c', _VERIFY,
                                 json.dumps(versions), json.dumps(entry),
                                 str(venv), '1' if import_entry else '0'],
                                cwd=root, env=_effect_environment(root, venv / 'Scripts'),
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=60)
        if output.returncode or len(output.stdout) > 4_000_000:
            raise InputError('windows_install_metadata_unavailable')
        metadata = json.loads(output.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise InputError('windows_install_metadata_unavailable') from None
    if type(metadata.get('files_sha256')) is not dict or not metadata['files_sha256']:
        raise InputError('windows_install_metadata_unavailable')
    return {'python': str(python), 'python_sha256': file_hash(python),
            'console_script': str(script), 'console_script_sha256': file_hash(script),
            'entrypoint_origin': metadata['entrypoint_origin'],
            'installed_files_sha256': digest(metadata['files_sha256']),
            'installed_files': metadata['files_sha256'],
            'distributions': versions}


def _verify_installed_bytes(plan: dict, root: Path, expected: dict) -> None:
    """Read current installed bytes directly; never start target or site code."""
    venv = root / 'venv'
    paths = (('python', 'python_sha256'), ('console_script', 'console_script_sha256'))
    for key, hash_key in paths:
        path = Path(expected[key])
        if (not cap._path_is_within(path, venv)
                or hashlib.sha256(cap._windows_secure_input(path, 64_000_000)).hexdigest()
                != expected[hash_key]):
            raise InputError('windows_install_executable_drift')
    files = expected['installed_files']
    if type(files) is not dict or not 1 <= len(files) <= 4096:
        raise InputError('windows_install_record_invalid')
    total = 0
    for relative, sha in files.items():
        if (type(relative) is not str or '\\' in relative or ':' in relative
                or relative.startswith('/') or '..' in relative.split('/')):
            raise InputError('windows_install_record_invalid')
        raw = cap._windows_secure_input(venv.joinpath(*relative.split('/')), 64_000_000)
        total += len(raw)
        if total > 256_000_000 or hashlib.sha256(raw).hexdigest() != sha:
            raise InputError('windows_install_distribution_drift')
    if digest(files) != expected['installed_files_sha256']:
        raise InputError('windows_install_record_invalid')
    if (loads(cap._windows_secure_input(root / 'config.json', 100_000)) != plan[
            'package_plan']['request']['configuration']
            or acl_sha256(root / 'config.json') != expected['config_acl_sha256']):
        raise InputError('windows_install_configuration_drift')


def install_windows_template_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    """Execute one offline installation; an incomplete intent blocks replay."""
    validate_contract(plan, 'windows-template-install-plan-v1')
    if (approved_plan_sha256 != plan['plan_sha256']
            or plan['plan_sha256'] != digest({k: v for k, v in plan.items()
                                             if k != 'plan_sha256'})
            or plan != plan_windows_template_install(plan['package_plan'],
                plan['package_receipt'], trusted_package_receipt_sha256=
                plan['trusted_package_receipt_sha256'])):
        raise InputError('windows_install_exact_authority_or_plan_required')
    root = _generation(plan)
    if root.exists():
        raise InputError('windows_install_existing_generation_requires_status_review')
    owned = create_private_directory(root)
    write_private_json_exclusive(owned, 'owner.json', {'plan_sha256': plan['plan_sha256'],
                                                       'owned_directory': owned})
    write_private_json_exclusive(owned, 'install-intent.json',
                                 {'plan_sha256': plan['plan_sha256'], 'status': 'started'})
    venv = root / 'venv'
    _run([sys.executable, '-I', '-m', 'venv', str(venv)], root=root,
         scripts=Path(sys.executable).parent)
    python = venv / 'Scripts/python.exe'
    if not python.is_file():
        raise InputError('windows_install_venv_incomplete')
    package = plan['package_plan']
    wheelhouse = Path(package['request']['wheelhouse'])
    # Exact pre-effect source/wheel/receipt check. Only selected reviewed files
    # were copied to the host build stage; excluded source trees remain absent.
    if inspect_windows_template_package_inputs(
            package['request']['host_root'], package['request']['reviewed_source_files'],
            wheelhouse, package['request']['reviewed_wheels'],
            package['request']['output_parent'], package['request']['environment_parent'],
            package['request']['console_script']) != package['inputs']:
        raise InputError('windows_install_package_inputs_changed')
    wheels = [str(wheelhouse / row['filename']) for row in package['inputs']['wheel_files']]
    write_private_bytes_exclusive(owned, 'requirements.lock',
                                  _requirements_lock(package['inputs']['wheel_files']))
    _run([str(python), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps',
          '--require-hashes', '--find-links', str(wheelhouse),
          '-r', str(root / 'requirements.lock')], root=root, scripts=venv / 'Scripts')
    host_wheel = (Path(plan['package_receipt']['package_directory']) / 'dist' /
                  plan['package_receipt']['wheel_filename'])
    if file_hash(host_wheel) != plan['package_receipt']['wheel_sha256']:
        raise InputError('windows_install_host_wheel_changed')
    host_row = {'name': package['inputs']['project_name'],
                'version': package['inputs']['project_version'],
                'sha256': plan['package_receipt']['wheel_sha256']}
    write_private_bytes_exclusive(owned, 'host.lock', _requirements_lock([host_row]))
    _run([str(python), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps',
          '--require-hashes', '--find-links', str(host_wheel.parent),
          '-r', str(root / 'host.lock')], root=root, scripts=venv / 'Scripts')
    _run([str(python), '-I', '-m', 'pip', 'check'], root=root, scripts=venv / 'Scripts')
    write_private_json_exclusive(owned, 'config.json', package['request']['configuration'])
    installed = _verify_environment(plan, root, import_entry=True)
    installed['config_acl_sha256'] = acl_sha256(root / 'config.json')
    tree = installed_tree_snapshot(venv)
    installed['tree_files'] = tree['files']
    installed['tree_acls'] = tree['acls']
    installed['tree_sha256'] = digest(installed['tree_files'])
    installed['tree_acl_sha256'] = digest(installed['tree_acls'])
    installed['tree_identity_sha256'] = digest(tree['identities'])
    receipt = {'schema_version': '1.0', 'kind': 'windows-template-install-receipt-v1',
               'plan_sha256': plan['plan_sha256'],
               'package_receipt_sha256': plan['package_receipt']['receipt_sha256'],
               'environment': str(root), 'owned_directory': owned,
               'installed': installed, 'mode': 'off',
               'runtime_activation_authorized': False}
    receipt['receipt_sha256'] = digest(receipt)
    validate_contract(receipt, 'windows-template-install-receipt-v1')
    write_private_json_exclusive(owned, 'install-receipt.json', receipt)
    return receipt


def windows_install_status(plan: dict, *, trusted_receipt_sha256: str | None = None) -> dict:
    """Read-only historical install state, without importing the target module."""
    validate_contract(plan, 'windows-template-install-plan-v1')
    if plan['plan_sha256'] != digest({k: v for k, v in plan.items() if k != 'plan_sha256'}):
        raise InputError('windows_install_plan_digest_changed')
    root = _generation(plan)
    if not root.exists():
        return {'status': 'absent', 'receipt_trust': 'absent'}
    try:
        owner = loads(cap._windows_secure_input(root / 'owner.json', 1_000_000))
        owned = owner['owned_directory']
        check_private_directory(owned)
        if owner['plan_sha256'] != plan['plan_sha256'] or owned['path'] != str(root):
            raise InputError('windows_install_ownership_changed')
        if read_private_json(owned, 'install-intent.json') != {
                'plan_sha256': plan['plan_sha256'], 'status': 'started'}:
            raise InputError('windows_install_intent_changed')
        if not (root / 'install-receipt.json').exists():
            return {'status': 'blocked_recovery', 'receipt_trust': 'absent'}
        receipt = read_private_json(owned, 'install-receipt.json')
        validate_contract(receipt, 'windows-template-install-receipt-v1')
        if (receipt['receipt_sha256'] != digest({k: v for k, v in receipt.items()
                                                 if k != 'receipt_sha256'})
                or receipt['plan_sha256'] != plan['plan_sha256']
                or receipt['owned_directory'] != owned):
            raise InputError('windows_install_receipt_changed')
        _verify_installed_bytes(plan, root, receipt['installed'])
        tree = installed_tree_snapshot(root / 'venv')
        if (tree['files'] != receipt['installed']['tree_files']
                or tree['acls'] != receipt['installed']['tree_acls']
                or digest(receipt['installed']['tree_files']) !=
                receipt['installed']['tree_sha256']
                or digest(receipt['installed']['tree_acls']) !=
                receipt['installed']['tree_acl_sha256']
                or digest(tree['identities']) !=
                receipt['installed']['tree_identity_sha256']):
            raise InputError('windows_install_tree_drift')
        return {'status': 'installed_recorded',
                'receipt_trust': ('externally_anchored' if trusted_receipt_sha256 ==
                                  receipt['receipt_sha256'] else 'recorded_untrusted'),
                'receipt_sha256': receipt['receipt_sha256']}
    except InputError:
        raise
    except (OSError, KeyError, TypeError, ValueError):
        raise InputError('windows_install_status_unavailable') from None
