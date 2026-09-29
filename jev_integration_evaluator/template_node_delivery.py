"""Read-only Node launch descriptor for an externally anchored installed generation.

This adapter carries an exact command and independent observation schedule to
a future Node supervisor. It runs bounded Node/npm toolchain probes during
installation revalidation; it does not create a session or launch the host.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import stat

from .contracts import validate_contract
from .io import InputError, digest, file_hash, read_json
from .template_node_installation import _file, installation_status


def _observed(path: Path) -> str | None:
    if (not path.is_absolute() or '..' in path.parts
            or any(part.is_symlink() for part in (path, *path.parents))):
        raise InputError('Node delivery observation path is linked or relative')
    try:
        parent = path.parent.stat()
    except OSError:
        raise InputError('Node delivery observation parent unavailable') from None
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise InputError('Node delivery observation parent is not owner-private')
    if not path.exists():
        return None
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1_000_000:
        raise InputError('Node delivery observation is not a bounded regular file')
    return file_hash(path)


def _environment(values: dict | None) -> dict[str, str]:
    result = copy.deepcopy({} if values is None else values)
    allowed = {'NODE_EFFECT_PATH', 'NODE_READY_PATH', 'NODE_INTEGRATION_PATH'}
    if (type(result) is not dict or len(result) > 3
            or any(type(key) is not str or key not in allowed
                   or type(value) is not str or len(value) > 4096 or '\x00' in value
                   for key, value in result.items())):
        raise InputError('Node delivery launch environment invalid or sensitive')
    return result


def plan_node_delivery(install_plan: dict, *, trusted_install_receipt_sha256: str,
                       observation: dict, launch_environment: dict | None = None) -> dict:
    """Bind installed bytes and external observations without host effects."""
    validate_contract(install_plan, 'node-install-plan-v1')
    validate_contract(observation, 'template-delivery-observation-v1')
    current = installation_status(install_plan,
        trusted_receipt_sha256=trusted_install_receipt_sha256)
    if current['status'] != 'installed_recorded':
        raise InputError('Externally anchored Node installation required')
    root = Path(install_plan['environment_parent']) / ('jev-node-env-' + install_plan['plan_sha256'][:24])
    receipt = read_json(_file(root, 'install-receipt.json'))
    validate_contract(receipt, 'node-install-receipt-v1')
    if receipt['receipt_sha256'] != trusted_install_receipt_sha256:
        raise InputError('Node installed receipt changed')
    if any('..' in Path(row['path']).parts for row in observation['checks']):
        raise InputError('Node delivery observation path contains parent traversal')
    if any(str(Path(row['path'])) != row['path'] for row in observation['checks']):
        raise InputError('Node delivery observation path is not canonical')
    roles = {role: [Path(row['path']) for row in observation['checks'] if row['role'] == role]
             for role in ('ready', 'entrypoint_reached', 'integration_reachable')}
    if any(len(group) != 1 for group in roles.values()):
        raise InputError('Node delivery requires one ready, entrypoint and integration check')
    request = install_plan['package_plan']['request']
    protected = [root] + [Path(request[key]) for key in (
        'host_root', 'render_directory', 'implementation_bundle',
        'tooling_directory', 'offline_cache', 'package_directory')]
    paths = [Path(row['path']) for row in observation['checks']]
    if len(set(paths)) != len(paths):
        raise InputError('Node delivery roles need independent paths')
    for row, path in zip(observation['checks'], paths):
        if (any(path == base or path.is_relative_to(base) for base in protected)
                or _observed(path) != row['before_sha256']
                or row['before_sha256'] == row['expected_sha256']):
            raise InputError('Node delivery observation baseline or ownership changed')
    values = _environment(launch_environment)
    expected_paths = {'NODE_READY_PATH': str(roles['ready'][0]),
                      'NODE_EFFECT_PATH': str(roles['entrypoint_reached'][0]),
                      'NODE_INTEGRATION_PATH': str(roles['integration_reachable'][0])}
    if values != expected_paths:
        raise InputError('Node delivery launch environment does not match observed roles')
    descriptor = {'schema_version': '1.0', 'kind': 'node-delivery-descriptor-v1',
                  'install_plan': copy.deepcopy(install_plan),
                  'trusted_install_receipt_sha256': trusted_install_receipt_sha256,
                  'generation_id': receipt['generation_id'],
                  'generation_path': receipt['generation_path'],
                  'command': receipt['command'],
                  'working_directory': receipt['working_directory'],
                  'executable_sha256': receipt['executable_sha256'],
                  'entrypoint_sha256': receipt['entrypoint_sha256'],
                  'artifact_sha256': receipt['artifact_sha256'],
                  'source_sha256': receipt['source_sha256'],
                  'configuration_sha256': receipt['configuration_sha256'],
                  'secret_references_sha256': receipt['secret_references_sha256'],
                  'observation': copy.deepcopy(observation),
                  'launch_environment': values,
                  'mode': 'off', 'runtime_activation_authorized': False,
                  'launch_status': 'not_started'}
    descriptor['descriptor_sha256'] = digest(descriptor)
    validate_contract(descriptor, 'node-delivery-descriptor-v1')
    return descriptor


def validate_node_delivery(descriptor: dict) -> dict:
    """Revalidate installed bytes and observation baseline before external launch."""
    validate_contract(descriptor, 'node-delivery-descriptor-v1')
    if descriptor['descriptor_sha256'] != digest({k: v for k, v in descriptor.items()
                                                  if k != 'descriptor_sha256'}):
        raise InputError('Node delivery descriptor digest changed')
    current = plan_node_delivery(descriptor['install_plan'],
        trusted_install_receipt_sha256=descriptor['trusted_install_receipt_sha256'],
        observation=descriptor['observation'],
        launch_environment=descriptor['launch_environment'])
    if current != descriptor:
        raise InputError('Node delivery installed descriptor drift')
    return {'status': 'verified_unlaunched', 'descriptor_sha256': descriptor['descriptor_sha256'],
            'generation_id': descriptor['generation_id']}
