"""Always-on gate-planner contracts for the installed Node connected owner.

Every study, holdout row, grant, receipt and installed generation here is an
in-test fixture. The ``observed`` label on fixture rows only reaches the
planner's qualified branch; it is not observed evidence, a live measurement
or deployment authority, and no fixture is written outside ``tmp_path``.

The pinned Linux Node/npm installation check (``installation_status``) is
replaced by a byte fixture so these tests run on every platform. Where the
POSIX private-file reader cannot run, a portable reader with the same digest
check stands in. The gate recomputation, evidence classification and grant
binding under test are never replaced unless a test says so explicitly.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest

from jev_integration_evaluator import template_node_connected as connected
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.holdout import validate_holdout
from jev_integration_evaluator.io import InputError, canonical, digest, file_hash, loads
from jev_integration_evaluator.study import evaluate_study, freeze_study
from scripts import v12_fixtures


POSIX_REFERENCES = hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'getuid')
LIMITS = {'max_calls': 2, 'max_cost': 2}
FIXTURE_SPEC = {'recipe_id': 'javascript.C', 'candidate_id': 'fixture-candidate',
                'executed_source_sha256': 'b' * 64}
NOT_QUALIFIED = 'Observed connected gate evidence is not qualified'
BINDING = 'Connected deployment or receipt binding differs from raw gates'
EXPIRED = 'Unexpired connected deployment grant and receipt required'
_PROTOTYPES: dict = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(offset: timedelta) -> str:
    return (_now() + offset).isoformat()


def _fixture_reference(row: dict, root: Path) -> object:
    """Portable stand-in for hosts without O_NOFOLLOW/getuid; same digest rule."""
    if type(row) is not dict or set(row) != {'path', 'sha256'}:
        raise InputError('Invalid connected evidence reference')
    path = Path(row['path'])
    if not path.is_absolute() or path.is_relative_to(root) or path.is_symlink():
        raise InputError('Connected evidence reference unavailable or changed')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise InputError('Connected evidence reference unavailable or changed')
    return loads(raw.decode('utf-8'))


@pytest.fixture(autouse=True)
def _portable_references(monkeypatch):
    if not POSIX_REFERENCES:
        monkeypatch.setattr(connected, '_private_reference', _fixture_reference)


def _fixture_study(mode: str, *, evidence: str = 'observed', holdout: str = 'passing') -> dict:
    """Fabricated all-gate study whose raw rows the planner must recompute."""
    key = (mode, evidence, holdout)
    if key not in _PROTOTYPES:
        cfg = load_config()
        cfg['validation'].update(bootstrap_samples=120, bayesian_samples=200)
        inventory, old, baseline, treatment, bundle, _ = v12_fixtures.all_gate_study(
            cfg, evidence=evidence)
        specification = copy.deepcopy(old['specification'])
        specification['jev']['mode'] = mode
        gates = specification['deployment_gates']
        if holdout == 'failing':
            # Honest digests over rows whose labels contradict the accepted choice.
            entry = bundle['gates'][0]
            for row in entry['holdout_rows'][:30]:
                row['label'] = 'stop'
            report = validate_holdout(entry['threshold_plan'], entry['holdout_rows'],
                                      expected_digest=entry['threshold_plan']['contract_digest'])
            assert report['eligible_for_activation'] is False
            gates[0]['holdout_report_digest'] = report['contract_digest']
        if holdout == 'insufficient':
            # Fewer accepted holdout rows than the frozen minimum of 30.
            _, candidates = v12_fixtures.inventory(cfg)
            gate, entry, _, _, report = v12_fixtures.gate_fixture(
                candidates[0], 0, evidence=evidence, n=20)
            assert report['eligible_for_activation'] is False
            gates[0], bundle['gates'][0] = gate, entry
        bundle['gate_manifest_digest'] = digest(gates)
        study = freeze_study(specification, cfg, inventory=inventory)
        for row in baseline + treatment:
            row['study_digest'] = study['contract_digest']
            row['gate_manifest_digest'] = digest(gates)
        for row in treatment:
            row['mode'] = mode
            row['calibration_validated'] = True
        _PROTOTYPES[key] = {'study': study, 'baseline': baseline, 'treatment': treatment,
                            'gate_bundle': bundle, 'inventory': inventory}
    return copy.deepcopy(_PROTOTYPES[key])


def _write_references(directory: Path, raw: dict) -> dict:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    references = {}
    for name, value in raw.items():
        path = directory / (name + '.json')
        path.write_bytes(canonical(value))
        os.chmod(path, 0o600)
        references[name] = {'path': str(path), 'sha256': file_hash(path)}
    return references


def _fixture_activation(tmp_path: Path, mode: str, raw: dict, *, spec: dict = FIXTURE_SPEC,
                        limits: dict = LIMITS) -> dict:
    """Fixture grant and receipt bound to the exact raw rows; never authority."""
    grant = {'study_digest': raw['study']['contract_digest'],
             'gate_manifest_digest': digest(raw['study']['specification']['deployment_gates']),
             'mode': mode, 'baseline_digest': digest(raw['baseline']),
             'treatment_digest': digest(raw['treatment']),
             'gate_bundle_digest': digest(raw['gate_bundle']),
             'inventory_digest': digest(raw['inventory']),
             'deployment_id': 'FIXTURE-NOT-AUTHORITY', 'cohort_fraction': .1,
             'issued_at': _stamp(timedelta(minutes=-1)),
             'expires_at': _stamp(timedelta(minutes=5))}
    receipt = {'deployment_id': grant['deployment_id'],
               'source_sha256': spec['executed_source_sha256'],
               'runtime_contract_sha256': digest({'spec': spec, 'budget_limits': limits}),
               'issued_at': grant['issued_at'], 'expires_at': grant['expires_at']}
    return {'evidence_refs': _write_references(tmp_path.resolve() / 'private-evidence', raw),
            'expected_study_digest': raw['study']['contract_digest'],
            'deployment_grant': grant, 'receipt': receipt}


def _gate(tmp_path: Path, mode: str, activation: dict | None, *, now: datetime | None = None):
    request = {'mode': mode, 'budget_limits': LIMITS, 'activation': activation}
    return connected._activation(request, FIXTURE_SPEC,
                                 tmp_path.resolve() / 'fixture-generation', now)


def test_shadow_reads_no_gate_evidence_and_refuses_carried_activation(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('shadow must not read or evaluate canary/active evidence')
    monkeypatch.setattr(connected, '_private_reference', unexpected)
    monkeypatch.setattr(connected, 'evaluate_study', unexpected)
    assert _gate(tmp_path, 'shadow', None, now=_now()) is None
    with pytest.raises(InputError, match='Shadow must not carry activation evidence'):
        _gate(tmp_path, 'shadow', {'evidence_refs': {}}, now=_now())


@pytest.mark.parametrize('mode', ['canary', 'active'])
def test_canary_and_active_require_raw_gate_references(tmp_path, mode):
    for activation in (None, {}, {'recomputed_report': {'recommendation': 'keep'}}):
        with pytest.raises(InputError, match='Connected activation requires raw gate references'):
            _gate(tmp_path, mode, activation, now=_now())


@pytest.mark.parametrize('mode', ['canary', 'active'])
def test_fixture_positive_control_binds_only_recomputed_digests(tmp_path, mode):
    raw = _fixture_study(mode)
    activation = _fixture_activation(tmp_path, mode, raw)
    result = _gate(tmp_path, mode, activation, now=_now())
    gates = raw['study']['specification']['deployment_gates']
    assert result['recomputed_report'] == {
        'recommendation': 'keep', 'holdout_evidence_verified': True,
        'evidence_type': 'observed', 'mode': mode, 'spec_sha256': digest(FIXTURE_SPEC),
        'study_digest': raw['study']['contract_digest'],
        'gate_manifest_digest': digest(gates),
        'raw_references_sha256': digest(activation['evidence_refs'])}
    assert result['deployment_grant'] == activation['deployment_grant']
    assert result['receipt'] == activation['receipt']
    assert result['evidence_refs'] == activation['evidence_refs']
    # The recomputation itself never authorizes deployment.
    report = evaluate_study(raw['study'], raw['baseline'], raw['treatment'],
                            expected_digest=raw['study']['contract_digest'],
                            gate_bundle=raw['gate_bundle'], inventory=raw['inventory'])
    assert report['recommendation'] == 'keep' and report['deployment_authorized'] is False


@pytest.mark.parametrize('mode', ['canary', 'active'])
def test_synthetic_evidence_is_refused(tmp_path, mode):
    raw = _fixture_study(mode, evidence='synthetic')
    with pytest.raises(InputError, match=NOT_QUALIFIED):
        _gate(tmp_path, mode, _fixture_activation(tmp_path, mode, raw), now=_now())


def test_keep_shaped_report_cannot_promote_synthetic_label(tmp_path, monkeypatch):
    # Only here is the recomputation replaced, to isolate the evidence-type rule.
    raw = _fixture_study('canary', evidence='synthetic')
    activation = _fixture_activation(tmp_path, 'canary', raw)
    monkeypatch.setattr(connected, 'evaluate_study', lambda *args, **kwargs: {
        'recommendation': 'keep', 'holdout_evidence_verified': True,
        'gate_evidence': {'gate_manifest_digest':
                          activation['deployment_grant']['gate_manifest_digest']}})
    with pytest.raises(InputError, match=NOT_QUALIFIED):
        _gate(tmp_path, 'canary', activation, now=_now())


@pytest.mark.parametrize('holdout', ['failing', 'insufficient'])
def test_failing_or_insufficient_raw_holdout_is_refused(tmp_path, holdout):
    raw = _fixture_study('canary', holdout=holdout)
    report = evaluate_study(raw['study'], raw['baseline'], raw['treatment'],
                            expected_digest=raw['study']['contract_digest'],
                            gate_bundle=raw['gate_bundle'], inventory=raw['inventory'])
    assert report['holdout_evidence_verified'] is False
    assert report['recommendation'] == 'needs_more_evidence'
    with pytest.raises(InputError, match=NOT_QUALIFIED):
        _gate(tmp_path, 'canary', _fixture_activation(tmp_path, 'canary', raw), now=_now())


@pytest.mark.parametrize('claim', ['activation_summary', 'extra_reference',
                                   'boolean_gate_entry', 'relabelled_rows'])
def test_success_shaped_summary_never_replaces_raw_rows(tmp_path, claim):
    success = {'recommendation': 'keep', 'holdout_evidence_verified': True,
               'evidence_type': 'observed', 'mode': 'canary'}
    if claim in ('activation_summary', 'extra_reference'):
        raw = _fixture_study('canary', holdout='failing')
        activation = _fixture_activation(tmp_path, 'canary', raw)
        if claim == 'activation_summary':
            activation['recomputed_report'] = success
        else:
            activation['evidence_refs'].update(
                _write_references(tmp_path.resolve() / 'private-evidence', {'report': success}))
        with pytest.raises(InputError, match='Connected activation requires raw gate references'):
            _gate(tmp_path, 'canary', activation, now=_now())
        return
    raw = _fixture_study('canary')
    if claim == 'boolean_gate_entry':
        raw['gate_bundle']['gates'][0] = {'gate_id': 'gate-0', 'eligible_for_activation': True,
                                          'numerical_checks_pass': True}
    else:
        # The frozen passing report digest is kept while the raw labels now fail.
        for row in raw['gate_bundle']['gates'][0]['holdout_rows'][:30]:
            row['label'] = 'stop'
    with pytest.raises(InputError) as refused:
        _gate(tmp_path, 'canary', _fixture_activation(tmp_path, 'canary', raw), now=_now())
    assert NOT_QUALIFIED not in str(refused.value) and BINDING not in str(refused.value)


def test_missing_canary_outcomes_stay_in_the_denominator(tmp_path):
    # Dropping an unreported pair from both arms is refused outright.
    dropped = _fixture_study('canary')
    scheduled = len(dropped['baseline'])
    dropped['baseline'].pop()
    dropped['treatment'].pop()
    with pytest.raises(InputError, match='Run cohort differs from frozen test schedule'):
        _gate(tmp_path, 'canary', _fixture_activation(tmp_path, 'canary', dropped), now=_now())
    # A missing outcome cannot be reported as a success.
    promoted = _fixture_study('canary')
    promoted['treatment'][0].update(run_status='not_run', success=True)
    with pytest.raises(InputError, match='cannot count as success'):
        _gate(tmp_path, 'canary', _fixture_activation(tmp_path, 'canary', promoted), now=_now())
    # Retained as explicit non-successes, missing outcomes count against the arm.
    missing = _fixture_study('canary')
    absent = [row for row in missing['treatment'] if row['success']]
    assert len(absent) > scheduled // 2
    for row in absent:
        row.update(run_status='not_run', success=False)
    report = evaluate_study(missing['study'], missing['baseline'], missing['treatment'],
                            expected_digest=missing['study']['contract_digest'],
                            gate_bundle=missing['gate_bundle'], inventory=missing['inventory'])
    checks = report['study_validation']
    assert checks['scheduled_test_pairs'] == checks['observed_pairs'] == scheduled
    assert checks['jev_status_counts']['not_run'] == len(absent)
    assert report['holdout_evidence_verified'] is True and report['recommendation'] != 'keep'
    with pytest.raises(InputError, match=NOT_QUALIFIED):
        _gate(tmp_path, 'canary', _fixture_activation(tmp_path, 'canary', missing), now=_now())


def test_study_or_deployment_grant_for_another_mode_is_refused(tmp_path):
    active_study = _fixture_study('active')
    with pytest.raises(InputError, match=NOT_QUALIFIED):
        _gate(tmp_path, 'canary', _fixture_activation(tmp_path, 'canary', active_study),
              now=_now())
    raw = _fixture_study('canary')
    wrong_mode = _fixture_activation(tmp_path, 'active', raw)
    with pytest.raises(InputError, match=BINDING):
        _gate(tmp_path, 'canary', wrong_mode, now=_now())


@pytest.mark.parametrize('owner,field', [
    ('deployment_grant', 'study_digest'), ('deployment_grant', 'gate_manifest_digest'),
    ('deployment_grant', 'baseline_digest'), ('deployment_grant', 'treatment_digest'),
    ('deployment_grant', 'gate_bundle_digest'), ('deployment_grant', 'inventory_digest'),
    ('receipt', 'deployment_id'), ('receipt', 'source_sha256'),
    ('receipt', 'runtime_contract_sha256')])
def test_grant_or_receipt_bound_to_other_digests_is_refused(tmp_path, owner, field):
    raw = _fixture_study('canary')
    activation = _fixture_activation(tmp_path, 'canary', raw)
    activation[owner][field] = digest(['another binding', field])
    with pytest.raises(InputError, match=BINDING):
        _gate(tmp_path, 'canary', activation, now=_now())


def test_receipt_for_another_runtime_contract_is_refused(tmp_path):
    raw = _fixture_study('canary')
    for other in ({'spec': {**FIXTURE_SPEC, 'candidate_id': 'another-candidate'}},
                  {'limits': {'max_calls': 200, 'max_cost': 2}}):
        activation = _fixture_activation(tmp_path, 'canary', raw, **other)
        with pytest.raises(InputError, match=BINDING):
            _gate(tmp_path, 'canary', activation, now=_now())
    with pytest.raises(InputError, match=BINDING):
        _gate(tmp_path, 'canary', {**_fixture_activation(tmp_path, 'canary', raw),
                                   'deployment_grant': 'approved'}, now=_now())


@pytest.mark.parametrize('owner', ['deployment_grant', 'receipt'])
@pytest.mark.parametrize('window', ['expired', 'not_yet_valid', 'no_expiry', 'naive_time'])
def test_new_plan_refuses_deployment_authority_outside_its_window(tmp_path, owner, window):
    raw = _fixture_study('canary')
    activation = _fixture_activation(tmp_path, 'canary', raw)
    item = activation[owner]
    if window == 'expired':
        item.update(issued_at=_stamp(timedelta(hours=-2)), expires_at=_stamp(timedelta(hours=-1)))
    if window == 'not_yet_valid':
        item.update(issued_at=_stamp(timedelta(hours=1)), expires_at=_stamp(timedelta(hours=2)))
    if window == 'no_expiry':
        del item['expires_at']
    if window == 'naive_time':
        item['expires_at'] = '2999-01-01T00:00:00'
    with pytest.raises(InputError, match=EXPIRED):
        _gate(tmp_path, 'canary', activation, now=_now())
    # The status recomputation passes no clock: binding only, time stays with the host.
    assert _gate(tmp_path, 'canary', activation, now=None)['deployment_grant'] == \
        activation['deployment_grant']


def test_changed_raw_reference_bytes_are_refused(tmp_path):
    raw = _fixture_study('canary')
    activation = _fixture_activation(tmp_path, 'canary', raw)
    path = Path(activation['evidence_refs']['treatment']['path'])
    path.write_bytes(path.read_bytes() + b'\n')
    os.chmod(path, 0o600)
    with pytest.raises(InputError, match='Connected evidence reference unavailable or changed'):
        _gate(tmp_path, 'canary', activation, now=_now())


# -- planner and status over an installed-generation byte fixture --------------

def _fixture_generation(tmp_path: Path, monkeypatch, mode: str) -> dict:
    """Synthetic installed generation bytes; the pinned install check is replaced."""
    base = tmp_path.resolve()
    plan_sha256 = digest('fixture install plan')
    root = base / 'generations' / ('jev-node-env-' + plan_sha256[:24])
    app, bundle, rendered = root / 'app', base / 'bundle', base / 'render'
    for directory in (app, bundle, rendered, base / 'toolchain', base / 'ledger'):
        directory.mkdir(parents=True)
    names = ('host.cjs', 'jev_runtime.cjs', 'jev_adapter.cjs', 'start.cjs',
             'package.json', 'package-lock.json')
    for name in names:
        (app / name).write_text('// fixture bytes for ' + name + '\n', encoding='utf-8')
    node, npm = base / 'toolchain/node', base / 'toolchain/npm-cli.js'
    node.write_text('fixture node bytes\n', encoding='utf-8')
    npm.write_text('fixture npm bytes\n', encoding='utf-8')
    reviewed = {'configuration': {'runtime': {'mode': 'off', 'model': 'jev-1.13.0'}},
                'secret_references': {'TYPESAFE_API_KEY': 'env:TYPESAFE_API_KEY'}}
    (rendered / 'template-request.json').write_text(json.dumps(reviewed), encoding='utf-8')
    source_spec = {'candidate_id': 'fixture-candidate',
                   'source': {'file': 'host.cjs', 'sha256': digest('reviewed fixture source')},
                   'runtime': {'runtime': {'model': 'jev-1.13.0', 'mode': 'off'},
                               'questions': {}, 'primary_question': 'choice'}}
    (bundle / 'spec.json').write_text(json.dumps(source_spec), encoding='utf-8')
    (bundle / 'plan.json').write_text(json.dumps({
        'spec_sha256': digest(source_spec),
        'generated_sha256': {name: file_hash(app / name) for name in names[:3]}}),
        encoding='utf-8')
    receipt = {'mode': 'off', 'runtime_activation_authorized': False,
               'command': [str(node), str(app / 'start.cjs')],
               'entrypoint_sha256': file_hash(app / 'start.cjs'),
               'executable_sha256': file_hash(node),
               'configuration_sha256': digest(reviewed)}
    receipt['receipt_sha256'] = digest(receipt)
    (root / 'install-receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    install_plan = {'environment_parent': str(base / 'generations'), 'plan_sha256': plan_sha256,
                    'package_plan': {'format': 'commonjs', 'toolchain': {'npm_cli': str(npm)},
                                     'request': {'implementation_bundle': str(bundle),
                                                 'render_directory': str(rendered)}}}

    def recorded(plan, *, trusted_receipt_sha256=None):
        if plan != install_plan or trusted_receipt_sha256 != receipt['receipt_sha256']:
            raise InputError('fixture generation is not externally anchored')
        return {'status': 'installed_recorded'}
    monkeypatch.setattr(connected, 'installation_status', recorded)
    request = {'schema_version': '1.0', 'kind': 'node-connected-request-v1',
               'install_plan': install_plan,
               'trusted_install_receipt_sha256': receipt['receipt_sha256'],
               'mode': mode, 'endpoint': 'https://api.typesafe.ai/v1/systemone',
               'credential_ref': 'env:TYPESAFE_API_KEY', 'model': 'jev-1.13.0',
               'environment_digest': digest('fixture environment'),
               'budget_limits': dict(LIMITS),
               'ledger_path': str(base / 'ledger/runtime.sqlite'),
               'egress_grant': None, 'activation': None}
    core, spec, _ = connected.inspect_connected_core(request)
    request['egress_grant'] = {
        'core_sha256': digest(core), 'mode': mode, 'endpoint': request['endpoint'],
        'model': request['model'], 'credential_ref': request['credential_ref'],
        'environment_digest': request['environment_digest'],
        'issued_at': _stamp(timedelta(minutes=-1)), 'expires_at': _stamp(timedelta(minutes=5))}
    return {'request': request, 'core': core, 'spec': spec, 'app': app,
            'reviewed_request': rendered / 'template-request.json'}


def test_shadow_plan_binds_exact_unexpired_egress_grant_without_gates(tmp_path, monkeypatch):
    fixture = _fixture_generation(tmp_path, monkeypatch, 'shadow')
    request = fixture['request']
    descriptor = connected.plan_node_connected(request)
    assert descriptor['mode'] == 'shadow' and descriptor['activation'] is None
    assert descriptor['core_sha256'] == digest(fixture['core'])
    assert descriptor['egress_grant'] == request['egress_grant']
    trusted = descriptor['descriptor_sha256']
    assert connected.connected_status(request, descriptor, trusted_descriptor_sha256=trusted) == {
        'status': 'bound_unlaunched', 'descriptor_sha256': trusted, 'mode': 'shadow',
        'provider_requests': 0}
    with pytest.raises(InputError, match='Connected descriptor or referenced evidence changed'):
        connected.connected_status(request, descriptor, trusted_descriptor_sha256='0' * 64)
    for field, value in (('core_sha256', digest('another core')), ('mode', 'canary'),
                         ('mode', 'active'), ('endpoint', 'https://example.invalid/v1'),
                         ('environment_digest', digest('another environment'))):
        changed = {**request, 'egress_grant': {**request['egress_grant'], field: value}}
        with pytest.raises(InputError, match='Exact connected egress grant binding required'):
            connected.plan_node_connected(changed)
    with pytest.raises(InputError, match='Exact connected egress grant binding required'):
        connected.plan_node_connected({**request, 'egress_grant': None})
    with pytest.raises(InputError, match='Shadow must not carry activation evidence'):
        connected.plan_node_connected({**request, 'activation': {'evidence_refs': {}}})


@pytest.mark.parametrize('window', ['expired', 'not_yet_valid', 'no_expiry'])
def test_new_plan_refuses_egress_grant_outside_its_window(tmp_path, monkeypatch, window):
    request = _fixture_generation(tmp_path, monkeypatch, 'shadow')['request']
    grant = dict(request['egress_grant'])
    if window == 'expired':
        grant.update(issued_at=_stamp(timedelta(hours=-2)), expires_at=_stamp(timedelta(hours=-1)))
    if window == 'not_yet_valid':
        grant.update(issued_at=_stamp(timedelta(hours=1)), expires_at=_stamp(timedelta(hours=2)))
    if window == 'no_expiry':
        del grant['expires_at']
    with pytest.raises(InputError, match='Unexpired connected egress grant required'):
        connected.plan_node_connected({**request, 'egress_grant': grant})


def test_status_keeps_binding_after_expiry_but_no_new_plan_is_issued(tmp_path, monkeypatch):
    request = _fixture_generation(tmp_path, monkeypatch, 'shadow')['request']
    descriptor = connected.plan_node_connected(request)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=2)
    monkeypatch.setattr(connected, 'datetime', Later)
    with pytest.raises(InputError, match='Unexpired connected egress grant required'):
        connected.plan_node_connected(request)
    status = connected.connected_status(
        request, descriptor, trusted_descriptor_sha256=descriptor['descriptor_sha256'])
    assert status['status'] == 'bound_unlaunched' and status['provider_requests'] == 0


def test_shadow_grant_cannot_plan_canary_and_canary_needs_raw_gates(tmp_path, monkeypatch):
    fixture = _fixture_generation(tmp_path, monkeypatch, 'canary')
    request = fixture['request']
    shadow_grant = {**request['egress_grant'], 'mode': 'shadow'}
    with pytest.raises(InputError, match='Exact connected egress grant binding required'):
        connected.plan_node_connected({**request, 'egress_grant': shadow_grant})
    with pytest.raises(InputError, match='Connected activation requires raw gate references'):
        connected.plan_node_connected(request)


def test_canary_plan_fixture_control_and_refusals_through_the_planner(tmp_path, monkeypatch):
    fixture = _fixture_generation(tmp_path, monkeypatch, 'canary')
    request, spec = fixture['request'], fixture['spec']
    raw = _fixture_study('canary')
    request['activation'] = _fixture_activation(tmp_path, 'canary', raw, spec=spec)
    descriptor = connected.plan_node_connected(request)
    report = descriptor['activation']['recomputed_report']
    assert report['mode'] == 'canary' and report['spec_sha256'] == digest(spec)
    assert report['study_digest'] == raw['study']['contract_digest']
    trusted = descriptor['descriptor_sha256']
    assert connected.connected_status(
        request, descriptor, trusted_descriptor_sha256=trusted)['mode'] == 'canary'
    # A receipt for a different budget scope no longer matches this runtime contract.
    with pytest.raises(InputError, match=BINDING):
        connected.plan_node_connected({**request, 'budget_limits': {'max_calls': 9, 'max_cost': 2},
            'egress_grant': {**request['egress_grant'], 'core_sha256': digest(
                {**fixture['core'], 'budget_limits': {'max_calls': 9, 'max_cost': 2}})}})
    synthetic = _fixture_activation(tmp_path / 'synthetic', 'canary',
                                    _fixture_study('canary', evidence='synthetic'), spec=spec)
    with pytest.raises(InputError, match=NOT_QUALIFIED):
        connected.plan_node_connected({**request, 'activation': synthetic})
    expired = copy.deepcopy(request)
    expired['activation']['deployment_grant'].update(
        issued_at=_stamp(timedelta(hours=-2)), expires_at=_stamp(timedelta(hours=-1)))
    with pytest.raises(InputError, match=EXPIRED):
        connected.plan_node_connected(expired)
    # Raw evidence changed after planning: the status recheck used before launch refuses.
    path = Path(request['activation']['evidence_refs']['gate_bundle']['path'])
    path.write_bytes(path.read_bytes() + b' ')
    os.chmod(path, 0o600)
    with pytest.raises(InputError, match='Connected evidence reference unavailable or changed'):
        connected.connected_status(request, descriptor, trusted_descriptor_sha256=trusted)


@pytest.mark.parametrize('drift', ['reviewed_configuration', 'runtime_bytes', 'adapter_bytes'])
def test_configuration_or_source_drift_after_install_blocks_plan_and_status(
        tmp_path, monkeypatch, drift):
    fixture = _fixture_generation(tmp_path, monkeypatch, 'shadow')
    request = fixture['request']
    descriptor = connected.plan_node_connected(request)
    trusted = descriptor['descriptor_sha256']
    if drift == 'reviewed_configuration':
        target = fixture['reviewed_request']
        changed = json.loads(target.read_text(encoding='utf-8'))
        changed['configuration']['runtime']['mode'] = 'shadow'
        replacement = json.dumps(changed).encode()
        message = 'Connected reviewed off configuration changed'
    else:
        target = fixture['app'] / ('jev_runtime.cjs' if drift == 'runtime_bytes'
                                   else 'jev_adapter.cjs')
        replacement = target.read_bytes() + b'// drift\n'
        message = ('Connected source or installed toolchain drift' if drift == 'runtime_bytes'
                   else 'Connected installed adapter drift')
    original = target.read_bytes()
    target.write_bytes(replacement)
    with pytest.raises(InputError, match=message):
        connected.inspect_connected_core(request)
    with pytest.raises(InputError, match=message):
        connected.plan_node_connected(request)
    # connected_status is the recheck the session supervisor runs before launch.
    with pytest.raises(InputError, match=message):
        connected.connected_status(request, descriptor, trusted_descriptor_sha256=trusted)
    target.write_bytes(original)
    assert connected.connected_status(
        request, descriptor, trusted_descriptor_sha256=trusted)['status'] == 'bound_unlaunched'
