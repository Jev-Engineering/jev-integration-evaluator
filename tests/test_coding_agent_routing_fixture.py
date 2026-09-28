"""Collect the coding-agent fixture's routing checks in the normal test suite."""

import sys
from pathlib import Path


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "coding-agent"
if str(FIXTURE) not in sys.path:
    sys.path.insert(0, str(FIXTURE))

from test_agent import (  # noqa: E402
    test_abstention_and_malformed_choice_do_not_execute,
    test_argument_shape_and_type_are_host_enforced,
    test_authorized_registered_choice_uses_original_arguments,
    test_executor_error_is_not_recast_as_router_fallback,
    test_permission_denial_does_not_execute,
    test_router_timeout_and_provider_error_do_not_execute,
    test_study_rejects_altered_fake_executor_arguments,
    test_unregistered_action_does_not_execute,
)
