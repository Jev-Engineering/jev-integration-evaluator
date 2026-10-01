"""Shared fault checks for the issue 59 use-case journeys (offline synthetic).

One helper interrupts a use case's own reviewed source apply; the other
re-plans a use case's verified package request with its secret reference
missing. Neither starts a runtime, reaches a provider or resolves a credential.
"""
from __future__ import annotations

import copy
from pathlib import Path
import stat

import pytest

from jev_integration_evaluator import template_delivery_journey as journey
from jev_integration_evaluator import template_installation as installer
from jev_integration_evaluator.io import InputError, digest, file_hash, read_json
from jev_integration_evaluator.integrations import lifecycle
from jev_integration_evaluator.template_delivery import DeliveryError
from jev_integration_evaluator.use_case_templates import use_case_matrix


INTERRUPTION = 'injected_use_case_apply_interruption'
REPLAY_REFUSAL = 'Bundle needs explicit recovery/rollback, not another application'
ROLLBACK_APPROVAL_REFUSAL = 'Exact rollback digest approval is required'
OPERATOR_NOTE = b'unrelated operator work during recovery\n'


def _tree(root: Path) -> dict[str, tuple[bytes, int]]:
    """Exact bytes and permission bits of every file below a host root."""
    return {path.relative_to(root).as_posix():
            (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
            for path in sorted(root.rglob('*')) if path.is_file()}


def interrupted_apply_recovery(tmp_path: Path, module, name: str, apply_host, *,
                               letter: str, consumer: str) -> dict:
    """Interrupt a use case's reviewed apply after its first owned write.

    `apply_host` is the use case's own bind, materialize, plan, baseline and
    apply helper, and `module` is the test module whose `apply_implementation`
    name that helper calls. The real apply runs under a delivery journey that
    was created and baseline-anchored first. The interruption is raised from
    the existing patch `progress` callback immediately after the first
    completed write was journaled, so no timing is involved and the host is
    left with one owned file applied and the others at their preimage.
    `consumer` is the host-relative copy of the pinned use-case consumer for
    matrix row `letter`; it is unrelated source that no stage may change.
    """
    real_apply = module.apply_implementation
    assert real_apply is lifecycle.apply_implementation
    real_patch = lifecycle.apply_patch_plan
    seen: dict = {'writes': []}

    def journeyed_apply(target, bundle, approval, *, baseline_sha256):
        target, bundle = Path(target), Path(bundle)
        session = tmp_path / (name + '-journey')
        created = journey.create_journey(session, source_root=str(target), bundle=str(bundle))
        assert created['next_action'] == 'verify_and_anchor_source_baseline'
        anchored = journey.record_journey(
            session, trusted_journey_head=created['journey_head_sha256'],
            stage='baseline_anchored', trusted_receipt_sha256=baseline_sha256)
        assert anchored['run_id'] == created['run_id']
        assert anchored['next_action'] == 'apply_exact_source_bundle'
        seen.update(target=target, bundle=bundle, approval=approval, session=session,
                    baseline_sha256=baseline_sha256, run_id=created['run_id'],
                    head=anchored['journey_head_sha256'], before=_tree(target))

        def interrupted_patch(root, patch, approved, *, progress, **kwargs):
            def stop_after_first_write(event, change):
                progress(event, change)
                if event == 'write_completed':
                    seen['writes'].append(change['file'])
                    raise KeyboardInterrupt(INTERRUPTION)
            return real_patch(root, patch, approved, progress=stop_after_first_write, **kwargs)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(lifecycle, 'apply_patch_plan', interrupted_patch)
            return real_apply(target, bundle, approval, baseline_sha256=baseline_sha256)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, 'apply_implementation', journeyed_apply)
        with pytest.raises(KeyboardInterrupt, match=INTERRUPTION):
            apply_host()
    assert module.apply_implementation is real_apply
    assert lifecycle.apply_patch_plan is real_patch
    target, bundle, session = seen['target'], seen['bundle'], seen['session']
    before = seen['before']

    # Recovery is required: exactly the first owned file was written.
    blocked = lifecycle.implementation_status(target, bundle)
    assert blocked['status'] == 'blocked_recovery'
    identities = blocked['file_identity']
    assert len(seen['writes']) == 1 and len(identities) >= 2
    assert {file for file, state in identities.items() if state == 'applied'} == set(seen['writes'])
    assert {state for file, state in identities.items()
            if file not in seen['writes']} == {'baseline'}
    plan = read_json(bundle / 'implementation-plan.json')
    events = [row['event'] for row in lifecycle._journal(bundle, plan)]
    assert events[-3:] == ['apply_started', 'apply_write_started', 'apply_write_completed']

    def same_blocked_run():
        stuck = journey.journey_status(session, trusted_journey_head=seen['head'])
        assert stuck['run_id'] == seen['run_id']
        assert stuck['evidence_trust'] == 'externally_anchored_history'
        assert stuck['source'] == 'blocked_recovery'
        assert stuck['next_action'] == 'reconcile_exact_source_transaction'
        assert stuck['anchors']['baseline_receipt_sha256'] == seen['baseline_sha256']
        assert stuck['anchors']['modified_receipt_sha256'] is None
        assert (stuck['package'], stuck['installation'], stuck['runtime']) == (
            'unplanned', 'unplanned', 'absent')
    same_blocked_run()

    # Unrelated host source keeps its exact bytes while recovery is pending.
    unrelated = {file: value for file, value in before.items() if file not in identities}
    row = next(row for row in use_case_matrix()['rows'] if row['id'] == letter)
    assert consumer in unrelated and 'pyproject.toml' in unrelated
    assert file_hash(target / consumer) == row['consumer_adapter_sha256']
    partial = _tree(target)
    assert set(partial) - set(before) <= set(seen['writes'])
    for file, value in partial.items():
        assert (value == before.get(file)) == (file not in seen['writes']), file
    note = target / 'OPERATOR-NOTES.txt'
    assert not note.exists()
    note.write_bytes(OPERATOR_NOTE)
    partial = _tree(target)

    # A blind replay of the same approval under the same run is refused and
    # the journey cannot advance past the unfinished source transaction.
    with pytest.raises(InputError) as replay:
        real_apply(target, bundle, seen['approval'], baseline_sha256=seen['baseline_sha256'])
    assert str(replay.value) == REPLAY_REFUSAL
    with pytest.raises(DeliveryError) as advance:
        journey.record_journey(session, trusted_journey_head=seen['head'],
                               stage='source_verified',
                               trusted_receipt_sha256=seen['baseline_sha256'])
    assert str(advance.value) == 'journey_modified_stage_unavailable'
    with pytest.raises(InputError) as unapproved:
        lifecycle.rollback_implementation(target, bundle, '0' * 64)
    assert str(unapproved.value) == ROLLBACK_APPROVAL_REFUSAL
    assert _tree(target) == partial
    assert lifecycle.implementation_status(target, bundle)['status'] == 'blocked_recovery'
    same_blocked_run()

    # Owned rollback restores every preimage byte and mode, removes what the
    # apply created, and leaves the operator's unrelated file alone.
    rolled = lifecycle.rollback_implementation(target, bundle, blocked['rollback_digest'])
    assert rolled['status'] == 'rolled_back'
    assert rolled['unrelated_paths_modified'] is False
    restored = _tree(target)
    assert restored.pop('OPERATOR-NOTES.txt')[0] == OPERATOR_NOTE
    assert restored == before
    assert file_hash(target / consumer) == row['consumer_adapter_sha256']
    spec = read_json(bundle / 'implementation-spec.json')
    assert spec['recipe']['id'] == 'python.' + letter
    # The seam is written first; the owned set is exactly the reviewed edits.
    assert seen['writes'] == [spec['source']['file']]
    assert sorted(identities) == sorted(spec['output']['permitted_edits'])
    entry = spec['entrypoint_binding']
    assert file_hash(target / entry['file']) == entry['file_sha256']
    assert file_hash(target / spec['source']['file']) == spec['source']['file_sha256']
    closed = lifecycle.implementation_status(target, bundle)
    assert closed['status'] == 'rolled_back'
    assert set(closed['file_identity'].values()) == {'baseline'}
    after = journey.journey_status(session, trusted_journey_head=seen['head'])
    assert after['run_id'] == seen['run_id'] and after['source'] == 'rolled_back'
    assert after['next_action'] == 'review_source_transaction'
    assert after['anchors']['modified_receipt_sha256'] is None
    # The rolled-back bundle is closed: it needs a fresh reviewed plan.
    with pytest.raises(InputError) as closed_replay:
        real_apply(target, bundle, seen['approval'], baseline_sha256=seen['baseline_sha256'])
    assert str(closed_replay.value) == REPLAY_REFUSAL
    final = _tree(target)
    assert final.pop('OPERATOR-NOTES.txt')[0] == OPERATOR_NOTE
    assert final == before
    return {'target': target, 'bundle': bundle, 'spec': spec, 'run_id': seen['run_id'],
            'interrupted_write': seen['writes'][0], 'owned': sorted(identities),
            'unrelated': sorted(unrelated)}


def missing_secret_package_refusals(request: dict, refused_output: Path) -> None:
    """Re-plan a verified off-mode package request with its secret missing.

    `request` is the exact request an installed journey already planned. Each
    candidate names a fresh output, so a refusal is decided by the secret
    contract alone, and nothing may be created for it.
    """
    environments = Path(request['environment_parent'])
    generations = sorted(path.name for path in environments.iterdir())
    assert request['configuration'] == {'jev_runtime': {'mode': 'off', 'credential_ref': None}}
    assert request['secret_references'] == {}
    assert not refused_output.exists()
    reference = 'env:TYPESAFE_API_KEY'

    def candidate(credential_ref, references, *, reviewed=True):
        value = copy.deepcopy(request)
        value['package_directory'] = str(refused_output)
        value['configuration'] = {'jev_runtime': {'mode': 'off',
                                                  'credential_ref': credential_ref}}
        if reviewed:
            value['reviewed_configuration_sha256'] = digest(value['configuration'])
        if references is None:
            del value['secret_references']
        else:
            value['secret_references'] = references
        return value

    keyless = candidate(None, {})
    del keyless['configuration']['jev_runtime']['credential_ref']
    keyless['reviewed_configuration_sha256'] = digest(keyless['configuration'])
    contract = 'Invalid template-package-request-v1 contract'
    for value, reason in (
            # The configuration names a credential the request does not declare.
            (candidate(reference, {}), 'configuration_secret_reference_mismatch'),
            # The request declares a secret the configuration does not use.
            (candidate(None, {'credential': reference}),
             'configuration_secret_reference_mismatch'),
            (candidate(reference, {'credential': 'env:ANOTHER_REFERENCE'}),
             'configuration_secret_reference_mismatch'),
            # The reference changed after the configuration was reviewed.
            (candidate(reference, {'credential': reference}, reviewed=False),
             'reviewed_configuration_drift'),
            (candidate(None, None), contract),
            (keyless, contract),
            (candidate('synthetic-inline-value', {}), contract),
            (candidate(reference, {'credential': 'synthetic-inline-value'}), contract)):
        with pytest.raises(InputError) as refused:
            installer.plan_package(value)
        assert str(refused.value) == reason, reason
        assert not refused_output.exists()
        assert sorted(path.name for path in environments.iterdir()) == generations
