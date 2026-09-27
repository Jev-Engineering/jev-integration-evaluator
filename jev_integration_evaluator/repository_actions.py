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
    "resolve_scan_coverage_before_implementation": (["complete_source_coverage"], "new_review", "none", True),
    "supply_recorded_source_reviewed_inventory_and_spec": (["reviewed_inventory", "implementation_spec"], "new_review", "none", True),
    "obtain_private_bundle_preparation_scope": (["prepare_scope", "trusted_session_head"], "exact_scope", "private_preparation", True),
    "review_preserved_output_and_explicitly_request_bounded_retry": (["retry_request", "prepare_scope", "trusted_session_head"], "exact_scope", "private_preparation", True),
    "review_prepared_bindings_and_source_shape": (["reviewed_inventory", "implementation_spec", "retry_request"], "new_review", "none", True),
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
}

for _operation, _effect in (("baseline", "trusted_host_execution"),
                            ("apply", "owned_mutation"),
                            ("modified", "trusted_host_execution")):
    _ACTIONS[f"obtain_exact_bundle_{_operation}_scope"] = (
        [f"{_operation}_scope", "trusted_session_head"], "exact_scope", _effect, True)


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
