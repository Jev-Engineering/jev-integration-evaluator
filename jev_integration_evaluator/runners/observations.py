"""Bounded independent native lifecycle observations; never an authority source.

The oracle is frozen before execution and supplied with an externally retained
hash by the trusted session owner. Target-produced JSON alone cannot authenticate
its own reachability or effects; session dispatch must separately authenticate
host ownership/review and the exact bundle/phase/attempt anchors.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .isolated_python import RunnerError, canonical, inspect_receipt, request_digest

_HEX = re.compile(r'[0-9a-f]{64}\Z')
_STATE_KEYS = {'reached', 'result', 'effects', 'state', 'assessments', 'dependency_origin'}


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _observation(data: bytes) -> dict[str, Any]:
    if len(data) > 4096 or not data.endswith(b'\n') or data.count(b'\n') != 1:
        raise RunnerError('invalid_native_observation')
    try:
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError('duplicate key')
                value[key] = item
            return value
        value = json.loads(data, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (ValueError, UnicodeError):
        raise RunnerError('invalid_native_observation') from None
    if (type(value) is not dict or set(value) != _STATE_KEYS
            or value['reached'] is not True
            or type(value['result']) is not str or len(value['result']) > 256
            or type(value['effects']) is not list or len(value['effects']) > 32
            or any(type(item) is not str or len(item) > 128 for item in value['effects'])
            or type(value['state']) is not dict or len(value['state']) > 32
            or any(type(key) is not str or len(key) > 64
                   or type(item) not in (bool, int, str) or len(str(item)) > 256
                   for key, item in value['state'].items())
            or type(value['assessments']) is not int or not 0 <= value['assessments'] <= 32
            or type(value['dependency_origin']) is not str
            or len(value['dependency_origin']) > 256):
        raise RunnerError('invalid_native_observation')
    return value


def inspect_lifecycle_postconditions(
    oracle: dict[str, Any], *, trusted_oracle_sha256: str,
    baseline_spec: dict[str, Any], baseline_receipt: dict[str, Any],
    baseline_outputs: dict[str, tuple[bytes, bytes]], trusted_baseline_receipt_sha256: str,
    modified_spec: dict[str, Any], modified_receipt: dict[str, Any],
    modified_outputs: dict[str, tuple[bytes, bytes]], trusted_modified_receipt_sha256: str,
) -> dict[str, Any]:
    """Evaluate complete baseline/off/shadow schedule with no dropped failures.

    Returns observation evidence only. Repository identity, bundle ownership,
    oracle independence and external anchors are authenticated by the caller.
    """
    if not isinstance(trusted_oracle_sha256, str) or not _HEX.fullmatch(trusted_oracle_sha256):
        raise RunnerError('external_oracle_anchor_required')
    if _hash(canonical(oracle)) != trusted_oracle_sha256:
        raise RunnerError('external_oracle_anchor_mismatch')
    expected_keys = {'schema_version', 'kind', 'repository_identity', 'context_sha256',
                     'bundle_digest', 'adapter', 'baseline', 'modified'}
    if type(oracle) is not dict or set(oracle) != expected_keys:
        raise RunnerError('invalid_native_oracle')
    if oracle['schema_version'] != '1.0' or oracle['kind'] != 'native-postconditions-v1' or oracle['adapter'] != 'json-state-v1':
        raise RunnerError('unsupported_native_oracle')
    for key in ('repository_identity', 'context_sha256', 'bundle_digest'):
        if not isinstance(oracle[key], str) or not _HEX.fullmatch(oracle[key]):
            raise RunnerError('invalid_native_oracle_binding')
    phases = (
        ('baseline', baseline_spec, baseline_receipt, baseline_outputs, trusted_baseline_receipt_sha256),
        ('modified', modified_spec, modified_receipt, modified_outputs, trusted_modified_receipt_sha256),
    )
    rows = []
    observations = {}
    for phase, spec, receipt, outputs, trusted_receipt in phases:
        if not isinstance(trusted_receipt, str) or not _HEX.fullmatch(trusted_receipt):
            raise RunnerError('external_receipt_anchor_required')
        inspect_receipt(spec, receipt, trusted_receipt_sha256=trusted_receipt)
        binding = oracle[phase]
        if (type(binding) is not dict or set(binding) != {'request_sha256', 'source_manifest_sha256', 'attempt', 'cases'}
                or binding['request_sha256'] != request_digest(spec)
                or binding['source_manifest_sha256'] != receipt['source_manifest_sha256']
                or type(binding['attempt']) is not int or not 1 <= binding['attempt'] <= 3
                or type(binding['cases']) is not list
                or len(binding['cases']) != len(spec['schedule'])):
            raise RunnerError('native_oracle_phase_binding_mismatch')
        if set(outputs) - {case['case_id'] for case in spec['schedule']}:
            raise RunnerError('unexpected_native_output')
        for expected, case, execution in zip(binding['cases'], spec['schedule'], receipt['cases']):
            if (type(expected) is not dict or set(expected) != {'case_id', 'entry_sha256', 'observation'}
                    or expected['case_id'] != case['case_id']):
                raise RunnerError('native_oracle_schedule_mismatch')
            entry = next((file for file in spec['files'] if file['path'] == case['entry']), None)
            if entry is None or expected['entry_sha256'] != entry['sha256']:
                raise RunnerError('native_oracle_source_mismatch')
            wanted = expected['observation']
            if _observation(canonical(wanted) + b'\n') != wanted:
                raise RunnerError('invalid_native_oracle_observation')
            output = outputs.get(case['case_id'])
            observed = None
            matched = False
            if output is not None:
                stdout, stderr = output
                if _hash(stdout) != execution['stdout_sha256'] or _hash(stderr) != execution['stderr_sha256']:
                    raise RunnerError('native_output_receipt_mismatch')
                if (execution['outcome'] == 'exited_zero' and execution['isolation_established']
                        and receipt['source_identity_valid'] and stderr == b''):
                    try:
                        observed = _observation(stdout)
                    except RunnerError:
                        pass
                    matched = observed == wanted
            rows.append({'phase': phase, 'attempt': binding['attempt'], 'case_id': case['case_id'],
                         'execution_outcome': execution['outcome'], 'postcondition_matched': matched})
            observations[(phase, case['case_id'])] = observed
    # These are explicit lifecycle relations in addition to exact expected rows.
    if [r['case_id'] for r in rows if r['phase'] == 'baseline'] != ['baseline'] or [
            r['case_id'] for r in rows if r['phase'] == 'modified'] != ['off', 'shadow']:
        raise RunnerError('unsupported_native_lifecycle_schedule')
    base = observations[('baseline', 'baseline')]
    off = observations[('modified', 'off')]
    shadow = observations[('modified', 'shadow')]
    parity = bool(base and off and shadow and
                  all(base[key] == off[key] == shadow[key] for key in ('result', 'effects', 'state')) and
                  base['assessments'] == off['assessments'] == 0 and shadow['assessments'] > 0 and
                  base['dependency_origin'] == off['dependency_origin'] == shadow['dependency_origin'])
    return {'schema_version': '1.0', 'kind': 'native-postcondition-report-v1',
            'oracle_sha256': trusted_oracle_sha256,
            'repository_identity': oracle['repository_identity'],
            'context_sha256': oracle['context_sha256'],
            'bundle_digest': oracle['bundle_digest'],
            'scheduled': len(rows), 'recorded': len(rows), 'cases': rows,
            'parity_matched': parity,
            'postconditions_satisfied': parity and all(row['postcondition_matched'] for row in rows),
            'integration_verified': False, 'activation_eligible': False}
