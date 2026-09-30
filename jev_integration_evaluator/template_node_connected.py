"""Prepare an installed Node connected owner from anchored bytes and raw gate references.

Planning is read only. The returned digest is a binding, never authority to
connect. The installed host must authenticate every grant independently.
"""
from __future__ import annotations

import os
import hashlib
from pathlib import Path
import stat

from .io import InputError, digest, file_hash, loads, read_json
from .contracts import validate_contract
from .study import evaluate_study
from .template_node_installation import installation_status


_ROLES = ('executed_source', 'runtime', 'entrypoint', 'package', 'lock', 'node', 'npm')


def _private_reference(row: dict, root: Path) -> object:
    if (type(row) is not dict or set(row) != {'path', 'sha256'} or
            type(row['path']) is not str or type(row['sha256']) is not str):
        raise InputError('Invalid connected evidence reference')
    path = Path(row['path'])
    if (not path.is_absolute() or path.is_relative_to(root) or
            any(part.is_symlink() for part in (path, *path.parents))):
        raise InputError('Connected evidence reference unavailable or changed')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                    info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077 or
                    info.st_size > 16_000_000):
                raise InputError('Connected evidence reference unavailable or changed')
            raw = stream.read(16_000_001)
    except OSError:
        raise InputError('Connected evidence reference unavailable or changed') from None
    if len(raw) > 16_000_000 or hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise InputError('Connected evidence reference unavailable or changed')
    return loads(raw.decode('utf-8'))


def _activation(request: dict, spec: dict, root: Path) -> dict | None:
    if request['mode'] == 'shadow':
        if request.get('activation') is not None:
            raise InputError('Shadow must not carry activation evidence')
        return None
    activation = request.get('activation')
    if (type(activation) is not dict or set(activation) !=
            {'evidence_refs', 'expected_study_digest', 'deployment_grant', 'receipt'} or
            type(activation['evidence_refs']) is not dict or
            set(activation['evidence_refs']) !=
            {'study', 'baseline', 'treatment', 'gate_bundle', 'inventory'}):
        raise InputError('Connected activation requires raw gate references')
    raw = {name: _private_reference(row, root)
           for name, row in activation['evidence_refs'].items()}
    report = evaluate_study(raw['study'], raw['baseline'], raw['treatment'],
                            expected_digest=activation['expected_study_digest'],
                            gate_bundle=raw['gate_bundle'], inventory=raw['inventory'])
    if (report['recommendation'] != 'keep' or not report['holdout_evidence_verified'] or
            raw['study']['specification']['evidence_type'] != 'observed' or
            raw['study']['specification']['jev']['mode'] != request['mode']):
        raise InputError('Observed connected gate evidence is not qualified')
    gate_manifest = report['gate_evidence']['gate_manifest_digest']
    grant = activation['deployment_grant']
    receipt = activation['receipt']
    if (type(grant) is not dict or type(receipt) is not dict or
            grant.get('study_digest') != activation['expected_study_digest'] or
            grant.get('gate_manifest_digest') != gate_manifest or
            grant.get('mode') != request['mode'] or
            grant.get('baseline_digest') != digest(raw['baseline']) or
            grant.get('treatment_digest') != digest(raw['treatment']) or
            grant.get('gate_bundle_digest') != digest(raw['gate_bundle']) or
            grant.get('inventory_digest') != digest(raw['inventory']) or
            receipt.get('deployment_id') != grant.get('deployment_id') or
            receipt.get('source_sha256') != spec['executed_source_sha256'] or
            receipt.get('runtime_contract_sha256') !=
            digest({'spec': spec, 'budget_limits': request['budget_limits']})):
        raise InputError('Connected deployment or receipt binding differs from raw gates')
    summary = {'recommendation': 'keep', 'holdout_evidence_verified': True,
               'evidence_type': 'observed', 'mode': request['mode'],
               'spec_sha256': digest(spec),
               'study_digest': activation['expected_study_digest'],
               'gate_manifest_digest': gate_manifest,
               'raw_references_sha256': digest(activation['evidence_refs'])}
    return {'recomputed_report': summary,
            'deployment_grant': grant, 'receipt': receipt,
            'evidence_refs': activation['evidence_refs']}


def inspect_connected_core(request: dict) -> tuple[dict, dict, Path]:
    """Recheck installed bytes and show the exact scope to authenticate."""
    if (type(request) is not dict or set(request) !=
            {'schema_version', 'kind', 'install_plan', 'trusted_install_receipt_sha256',
             'mode', 'endpoint', 'credential_ref', 'model', 'environment_digest',
             'budget_limits', 'ledger_path', 'egress_grant', 'activation'} or
            request['schema_version'] != '1.0' or
            request['kind'] != 'node-connected-request-v1' or
            request['mode'] not in ('shadow', 'canary', 'active') or
            request['credential_ref'] != 'env:TYPESAFE_API_KEY' or
            request['model'] != 'jev-1.13.0'):
        raise InputError('Invalid connected Node request')
    plan = request['install_plan']
    if installation_status(plan, trusted_receipt_sha256=request['trusted_install_receipt_sha256'])['status'] != 'installed_recorded':
        raise InputError('Externally anchored installed Node generation required')
    root = Path(plan['environment_parent']) / ('jev-node-env-' + plan['plan_sha256'][:24])
    receipt = read_json(root / 'install-receipt.json')
    if receipt['receipt_sha256'] != request['trusted_install_receipt_sha256']:
        raise InputError('Installed Node receipt changed')
    bundle = Path(plan['package_plan']['request']['implementation_bundle'])
    source_spec = read_json(bundle / 'spec.json')
    implementation = read_json(bundle / 'plan.json')
    if (implementation['spec_sha256'] != digest(source_spec) or
            source_spec['runtime']['runtime']['model'] != request['model'] or
            source_spec['runtime']['runtime']['mode'] != 'off' or
            receipt['mode'] != 'off' or receipt['runtime_activation_authorized'] is not False):
        raise InputError('Connected plan must derive from reviewed default-off source')
    selected = source_spec['source']['file']
    executed = 'host.mjs' if plan['package_plan']['format'] == 'typescript' else selected
    expected = implementation['generated_sha256']
    spec = {'recipe_id': 'javascript.C', 'candidate_id': source_spec['candidate_id'],
            'source_sha256': source_spec['source']['sha256'],
            'applied_source_sha256': expected[selected],
            'executed_source_sha256': expected[executed],
            'source_file': selected, 'executed_file': executed,
            **source_spec['runtime']}
    app = root / 'app'
    paths = {'executed_source': app / executed, 'runtime': app / 'jev_runtime.cjs',
             'entrypoint': Path(receipt['command'][1]), 'package': app / 'package.json',
             'lock': app / 'package-lock.json',
             'node': Path(receipt['command'][0]),
             'npm': Path(plan['package_plan']['toolchain']['npm_cli'])}
    files = [{'role': role, 'path': str(paths[role]), 'sha256': file_hash(paths[role])}
             for role in _ROLES]
    if (files[0]['sha256'] != spec['executed_source_sha256'] or
            files[1]['sha256'] != expected['jev_runtime.cjs'] or
            files[2]['sha256'] != receipt['entrypoint_sha256'] or
            files[5]['sha256'] != receipt['executable_sha256']):
        raise InputError('Connected source or installed toolchain drift')
    if selected != executed:
        files.append({'role': 'reviewed_source', 'path': str(app / selected),
                      'sha256': file_hash(app / selected)})
    files.append({'role': 'adapter', 'path': str(app / 'jev_adapter.cjs'),
                  'sha256': file_hash(app / 'jev_adapter.cjs')})
    if files[-1]['sha256'] != expected['jev_adapter.cjs']:
        raise InputError('Connected installed adapter drift')
    rendered = Path(plan['package_plan']['request']['render_directory'])
    reviewed_request = rendered / 'template-request.json'
    reviewed = read_json(reviewed_request)
    if digest({'configuration': reviewed['configuration'],
               'secret_references': reviewed['secret_references']}) != receipt['configuration_sha256']:
        raise InputError('Connected reviewed off configuration changed')
    files.append({'role': 'reviewed_configuration', 'path': str(reviewed_request),
                  'sha256': file_hash(reviewed_request)})
    if plan['package_plan']['format'] == 'typescript':
        compiler = Path(plan['package_plan']['toolchain']['tooling']['compiler_path'])
        files.append({'role': 'typescript_compiler', 'path': str(compiler),
                      'sha256': file_hash(compiler)})
    ledger = Path(request['ledger_path'])
    if not ledger.is_absolute() or ledger.is_relative_to(root) or ledger.is_relative_to(app):
        raise InputError('Connected ledger must be outside installed generation')
    core = {'schema_version': '1.0', 'kind': 'node-connected-owner-v1',
            'runtime_profile': {'platform': 'linux', 'node': 'v24.18.0',
                                'apis': ['node:sqlite.DatabaseSync', 'AbortSignal',
                                         'node:https', 'node:crypto']},
            'mode': request['mode'], 'spec_sha256': digest(spec),
            'source_sha256': spec['executed_source_sha256'],
            'source_plan': {'files': files},
            'environment_digest': request['environment_digest'],
            'endpoint': request['endpoint'], 'credential_ref': request['credential_ref'],
            'model': request['model'], 'budget_limits': request['budget_limits'],
            'ledger_path': str(ledger),
            'install_receipt_sha256': receipt['receipt_sha256'],
            'configuration_sha256': receipt['configuration_sha256']}
    return core, spec, root


def plan_node_connected(request: dict) -> dict:
    """Bind an authenticated grant and independently recomputed raw gates."""
    core, spec, root = inspect_connected_core(request)
    grant = request['egress_grant']
    if (type(grant) is not dict or grant.get('core_sha256') != digest(core) or
            grant.get('mode') != request['mode'] or
            grant.get('endpoint') != request['endpoint'] or
            grant.get('model') != request['model'] or
            grant.get('credential_ref') != request['credential_ref'] or
            grant.get('environment_digest') != request['environment_digest']):
        raise InputError('Exact connected egress grant binding required')
    descriptor = {**core, 'core_sha256': digest(core), 'egress_grant': grant,
                  'activation': _activation(request, spec, root)}
    descriptor['descriptor_sha256'] = digest(descriptor)
    validate_contract(descriptor, 'node-connected-owner-v1')
    return descriptor


def connected_status(request: dict, descriptor: dict, *, trusted_descriptor_sha256: str) -> dict:
    """Recompute source/gate binding; never launch, adopt or renew authority."""
    validate_contract(descriptor, 'node-connected-owner-v1')
    if descriptor.get('descriptor_sha256') != trusted_descriptor_sha256 or \
            descriptor != plan_node_connected(request):
        raise InputError('Connected descriptor or referenced evidence changed')
    return {'status': 'bound_unlaunched', 'descriptor_sha256': trusted_descriptor_sha256,
            'mode': descriptor['mode'], 'provider_requests': 0}
