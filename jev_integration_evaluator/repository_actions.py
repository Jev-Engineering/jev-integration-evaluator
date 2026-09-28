"""Finite, descriptive next actions for repository session results.

These records describe missing inputs. They never carry authorization or cause
an effect; the session engine checks a fresh external scope at each boundary.
"""
from __future__ import annotations

from . import capabilities as cap


# code: (required inputs, authority class, possible next effect, same run)
_ACTIONS = {
    "supply_source_reviewed_inputs": (["reviewed_inventory", "implementation_spec"], "new_review", "none", False),
    "no_further_placement_action": ([], "none", "none", False),
    "review_repository_conclusion_and_missing_opinions": (["conclusion_review"], "new_review", "none", False),
    "review_unsupported_source_shape": (["supported_source_review"], "new_review", "none", False),
    "resolve_scan_coverage_before_implementation": (["complete_source_coverage"], "new_review", "none", True),
    "supply_recorded_source_reviewed_inventory_and_spec": (["reviewed_inventory", "implementation_spec"], "new_review", "none", True),
    "supply_indispensable_host_policy_or_verification": (["host_policy_or_runtime_ownership_or_independent_verification"], "new_review", "none", True),
    "resolve_offline_agent_review_facts": (["existing_host_binding_or_capability_review"], "new_review", "none", True),
    "review_selection_outcome": (["selection_review_or_supported_candidate"], "new_review", "none", True),
    "refresh_source_review_and_selection": (["fresh_source_review", "new_run"], "new_review", "none", False),
    "qualify_composite_transaction": (["composite_transaction_qualification"], "new_review", "none", False),
    "obtain_private_bundle_preparation_scope": (["prepare_scope", "trusted_session_head"], "exact_scope", "private_preparation", True),
    "review_preserved_output_and_explicitly_request_bounded_retry": (["retry_request", "prepare_scope", "trusted_session_head"], "exact_scope", "private_preparation", True),
    "review_prepared_bindings_and_source_shape": (["reviewed_inventory", "implementation_spec", "retry_request"], "new_review", "none", True),
    "supply_missing_host_binding": (["missing_host_binding_review"], "new_review", "none", False),
    "resolve_ambiguous_host_binding": (["unambiguous_host_binding_review"], "new_review", "none", False),
    "select_supported_source_shape": (["supported_source_review"], "new_review", "none", False),
    "resolve_host_prerequisite": (["host_prerequisite"], "new_review", "none", True),
    "review_invalid_preparation_inputs": (["prepared_input_review"], "new_review", "none", True),
    "review_exact_bundle_and_obtain_execution_mutation_scope": (["bundle_review", "execution_scope", "trusted_session_head"], "exact_scope", "trusted_host_execution", True),
    "approve_exact_owned_rollback_digest": (["rollback_scope", "rollback_digest", "trusted_session_head"], "exact_scope", "owned_mutation", True),
    "preserve_concurrent_edits_and_review_owned_bytes": (["owned_byte_review"], "new_review", "none", True),
    "retain_historical_receipts_and_prepare_fresh_review_for_reapplication": (["new_run_review"], "new_review", "none", False),
    "prepare_fresh_source_review_and_bundle_for_new_run": (["new_run_review"], "new_review", "none", False),
    "inspect_bundle_receipts_and_owned_source": (["receipt_and_owned_source_review"], "new_review", "none", True),
    "supply_exact_owned_rollback_scope": (["rollback_scope", "trusted_session_head"], "exact_scope", "owned_mutation", True),
    "supply_externally_retained_session_head": (["trusted_session_head"], "exact_scope", "none", True),
    "inspect_stale_or_changed_verification_receipt": (["receipt_review"], "new_review", "none", True),
    "software_wiring_only_no_activation": ([], "none", "none", False),
    "review_retained_failure_and_explicitly_request_bounded_retry": (["failure_review", "retry_request", "execution_scope", "trusted_session_head"], "exact_scope", "trusted_host_execution", True),
    "review_retained_schedule_and_independent_assertions": (["failed_schedule_review"], "new_review", "none", True),
    "reconcile_existing_bundle_before_any_retry": (["recovery_review"], "new_review", "none", True),
    "supply_external_receipt_anchor_or_owned_rollback_scope": (["external_receipt_anchor_or_rollback_scope", "trusted_session_head"], "external_receipt_or_rollback", "none", True),
    "retain_owned_bundle_for_explicit_recovery": (["rollback_scope", "trusted_session_head"], "exact_scope", "owned_mutation", True),
    "resume_with_externally_retained_session_head": (["trusted_session_head", "execution_scope"], "exact_scope", "trusted_host_execution", True),
    "review_native_bundle_and_scope": (["bundle_review", "native_contract", "native_scope", "trusted_session_head"], "exact_scope", "isolated_execution", True),
    "supply_exact_native_contract_or_isolation_scope": (["native_contract", "native_scope", "trusted_session_head"], "exact_scope", "isolated_execution", True),
    "review_native_postcondition_failure": (["native_oracle_review", "private_output_anchor"], "new_review", "none", True),
    "inspect_native_session_stage": (["session_review"], "new_review", "none", True),
    "reconcile_owned_apply_before_retry": (["owned_byte_review", "trusted_session_head"], "new_review", "none", True),
    "inspect_native_archive_and_external_anchor_before_retry": (["native_receipt_anchor", "private_output_anchor", "trusted_session_head"], "external_receipt_or_rollback", "none", True),
    "review_retained_native_schedule_and_postconditions": (["failed_schedule_review", "native_oracle_review"], "new_review", "none", True),
    "inspect_native_contract_and_private_archive": (["native_contract", "private_output_anchor", "trusted_session_head"], "new_review", "none", True),
    "resupply_exact_offline_agent_review": (["identical_offline_review_envelope", "trusted_session_head"], "new_review", "none", True),
    "resume_native_with_external_anchors": (["trusted_session_head", "native_contract", "native_scope", "native_receipt_anchor", "private_output_anchor"], "exact_scope", "isolated_execution", True),
}

for _operation, _effect in (("baseline", "trusted_host_execution"),
                            ("apply", "owned_mutation"),
                            ("modified", "trusted_host_execution")):
    _ACTIONS[f"obtain_exact_bundle_{_operation}_scope"] = (
        [f"{_operation}_scope", "trusted_session_head"], "exact_scope", _effect, True)

for _operation, _effect in (("baseline", "isolated_execution"),
                            ("apply", "owned_mutation"),
                            ("modified", "isolated_execution")):
    _ACTIONS[f"obtain_exact_native_{_operation}_scope"] = (
        [f"{_operation}_scope", "native_contract", "trusted_session_head"],
        "exact_scope", _effect, True)


def next_action_contract(code: str) -> dict:
    """Return a schema-checked record; unknown internal codes fail closed."""
    if code not in _ACTIONS:
        raise cap.CapabilityError("unknown_repository_next_action")
    inputs, authority, effect, same_run = _ACTIONS[code]
    value = dict(schema_version="1.0", kind="repository-next-action-v1", code=code,
                 required_inputs=list(inputs), authorization=authority,
                 effect=effect, resume_same_run=same_run)
    cap._schema("repository-next-action-v1", value)
    return value
