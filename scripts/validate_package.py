"""Validate package contracts and examples locally; does not execute target code or use a model."""
from pathlib import Path
import argparse,hashlib,json,sys,re
import jsonschema,yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev_integration_evaluator.io import InputError,read_json,read_jsonl,file_hash,write_json,safe_child
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.questions import validate_questions
from jev_integration_evaluator.client import FixtureClient
from jev_integration_evaluator.replay import replay_decisions


def validate(check_manifest=False):
    required=['SKILL.md','README.md','LICENSE','AGENTS.md','ONBOARDING.md','BRANDING.md','CONTRIBUTING.md','SECURITY.md','skill-package.json',
              'schemas/opportunity.schema.json','schemas/experiment.schema.json','schemas/decision.schema.json',
              'scripts/scan_repo.py','scripts/compare_runs.py','references/requirements-traceability.md',
              'references/placement-patterns.md','references/experimental-methodology.md','templates/jev-config.yaml',
              'examples/coding-agent/agent.py','examples/generic-service/service.py','tests/test_scanner.py',
              'CHANGELOG.md','references/lifecycle-and-evidence.md','scripts/run_v11_demo.py',
              'jev_integration_evaluator/lifecycle.py','jev_integration_evaluator/study.py','jev_integration_evaluator/holdout.py','jev_integration_evaluator/robustness.py',
              'schemas/study-spec.schema.json','schemas/study.schema.json','schemas/threshold-spec.schema.json',
              'schemas/threshold-policy.schema.json','schemas/holdout-report.schema.json','schemas/robustness-suite.schema.json',
              'jev_integration_evaluator/budget.py','jev_integration_evaluator/scenarios.py','jev_integration_evaluator/gates.py','jev_integration_evaluator/monitoring.py','jev_integration_evaluator/cohorts.py',
              'scripts/run_v12_demo.py','scripts/v12_fixtures.py','references/operational-evidence-v1.2.md',
              'schemas/scenario-spec.schema.json','schemas/deployment-gate.schema.json','schemas/gate-bundle.schema.json',
              'schemas/monitor-spec.schema.json','schemas/monitor.schema.json','schemas/monitor-outcome.schema.json',
              'tests/test_budget_runtime_v12.py','tests/test_scenarios_v12.py','tests/test_gates_v12.py',
              'tests/test_monitoring_v12.py','tests/test_cli_v12.py',
              'references/executable-integrations.md','scripts/run_implementation_demo.py','scripts/implementation_fixtures.py',
              'jev_integration_evaluator/integrations/recipes.py','jev_integration_evaluator/integrations/host.py',
              'jev_integration_evaluator/integrations/adaptation_shapes.py',
              'jev_integration_evaluator/integrations/adaptation_lifecycle.py',
              'jev_integration_evaluator/integrations/adaptation_review.py',
              'jev_integration_evaluator/integrations/adaptation_prerequisites.py',
              'jev_integration_evaluator/integrations/composite.py',
              'schemas/composite-selection-v1.schema.json','schemas/composite-plan-v1.schema.json',
              'schemas/composite-receipt-v1.schema.json','references/composite-transactions-v1.md',
              'examples/implementation/composite-selection.example.json',
              'tests/test_composite_transaction.py',
              'schemas/offline-adaptation-proposal-v1.schema.json',
              'schemas/offline-adaptation-prerequisites-v1.schema.json',
              'schemas/adaptation-prerequisite-plan-v1.schema.json',
              'schemas/prerequisite-validation-v1.schema.json',
              'schemas/adaptation-request-v1.schema.json','schemas/adaptation-plan-v1.schema.json',
              'references/python-adaptation-v1.md',
              'tests/test_adaptation_shapes.py','tests/test_adaptation_lifecycle.py','tests/test_adaptation_native.py',
              'tests/test_adaptation_review.py','tests/test_adaptation_prerequisites.py',
              'tests/test_adaptation_prerequisite_native.py',
              'tests/test_adaptation_combined_review.py',
              'jev_integration_evaluator/integrations/lifecycle.py','jev_integration_evaluator/integrations/verification.py',
              'schemas/implementation-spec.schema.json','schemas/implementation-plan.schema.json','schemas/implementation-receipt.schema.json',
              'schemas/implementation-manifest.schema.json','schemas/implementation-tests.schema.json',
              'tests/test_executable_recipes.py','tests/test_executable_runtime.py','tests/test_executable_safety.py','tests/test_executable_cli.py','tests/test_executable_wheel.py',
              'tests/test_executable_host_boundaries.py','tests/test_executable_source_scope.py','tests/test_executable_verification_identity.py',
              'jev_integration_evaluator/integrations/runtime_lifecycle.py',
              'jev_integration_evaluator/integrations/runtime_ledger.py',
              'schemas/host-runtime-connected-v1.schema.json',
              'jev_integration_evaluator/data/host-runtime-connected-v1.schema.json',
              'jev_integration_evaluator/template_connected_binding.py',
              'jev_integration_evaluator/template_connected_composite_binding.py',
              'jev_integration_evaluator/template_connected_delivery.py',
              'jev_integration_evaluator/template_connected_generation.py',
              'references/connected-generation-transfer-v1.md',
              'tests/test_connected_generation_ledger.py',
              'tests/test_connected_generation_controller.py',
              'tests/test_connected_generation_installed.py',
              'tests/independent_hosts/registered_alpha_connected_103/qualification.py',
              'tests/independent_hosts/registered_alpha_connected_103/pyproject.toml',
              'tests/independent_hosts/registered_alpha_connected_103/src/registered_alpha/connected_authority.py',
              'schemas/connected-generation-transfer-v1.schema.json',
              'jev_integration_evaluator/data/connected-generation-transfer-v1.schema.json',
              'schemas/connected-generation-transfer-receipt-v1.schema.json',
              'jev_integration_evaluator/data/connected-generation-transfer-receipt-v1.schema.json',
              'schemas/connected-generation-transfer-status-v1.schema.json',
              'jev_integration_evaluator/data/connected-generation-transfer-status-v1.schema.json',
              'schemas/connected-generation-status-v1.schema.json',
              'jev_integration_evaluator/data/connected-generation-status-v1.schema.json',
              'schemas/connected-installed-binding-v1.schema.json',
              'jev_integration_evaluator/data/connected-installed-binding-v1.schema.json',
              'schemas/connected-installed-composite-binding-v1.schema.json',
              'jev_integration_evaluator/data/connected-installed-composite-binding-v1.schema.json',
              'references/connected-installed-binding-v1.md',
              'references/connected-composite-binding-v1.md',
              'references/connected-delivery-v1.md',
              'tests/test_connected_installed_binding.py',
              'tests/test_connected_composite_binding.py',
              'tests/independent_hosts/registered_dual_connected/README.md',
              'tests/independent_hosts/registered_dual_connected/review-v1.json',
              'tests/independent_hosts/registered_dual_connected/installed_journey.py',
              'tests/independent_hosts/registered_dual_connected/pyproject.toml',
              'tests/independent_hosts/registered_dual_connected/src/registered_dual/console.py',
              'tests/independent_hosts/registered_dual_connected/src/registered_dual/connected_authority.py',
              'tests/independent_hosts/registered_alpha_connected/qualification.py',
              'tests/independent_hosts/registered_alpha_connected/pyproject.toml',
              'tests/independent_hosts/registered_alpha_connected/src/registered_alpha/connected_authority.py',
              'schemas/connected-delivery-plan-v1.schema.json',
              'jev_integration_evaluator/data/connected-delivery-plan-v1.schema.json',
              'schemas/connected-delivery-session-v1.schema.json',
              'jev_integration_evaluator/data/connected-delivery-session-v1.schema.json',
              'schemas/connected-delivery-scope-v1.schema.json',
              'jev_integration_evaluator/data/connected-delivery-scope-v1.schema.json',
              'schemas/connected-delivery-result-v1.schema.json',
              'jev_integration_evaluator/data/connected-delivery-result-v1.schema.json',
              'tests/test_host_runtime_connected_modes.py',
              'tests/test_host_runtime_lifecycle.py', 'references/host-runtime-lifecycle.md',
              'validation/WINDOWS-DISCOVERY-VALIDATION-1.3.0.dev12.md',
              'jev_integration_evaluator/integrations/observations.py','schemas/implementation-observation.schema.json',
              'tests/test_executable_failure_receipts.py','tests/test_executable_source_fidelity.py','tests/test_executable_command_receipts.py',
              'examples/implementation/observation.example.json',
              'jev_integration_evaluator/capabilities.py','scripts/discover_capabilities.py','references/capabilities.md',
              'schemas/repository-capabilities.schema.json','schemas/candidate-nomination.schema.json','schemas/admitted-nomination.schema.json',
              'tests/test_capabilities.py','tests/test_capabilities_adversarial.py','tests/test_capabilities_examples.py',
              'tests/test_capabilities_cli.py','tests/test_capabilities_wheel.py',
              'examples/capabilities/report.example.json','examples/capabilities/nomination.example.json',
              'examples/capabilities/admitted.example.json','examples/capabilities/opaque_host/opaque.py']
    required += ['jev_integration_evaluator/nomination_inventory.py',
                 'jev_integration_evaluator/repository_discovery.py',
                 'scripts/prepare_repository_inventory.py', 'scripts/run_capability_demo.py',
                 'references/repository-discovery-v1.md', 'references/platform-support.md',
                 'tests/test_nomination_inventory.py', 'tests/test_repository_discovery_cli.py',
                 'tests/test_repository_discovery_wheel.py', 'tests/test_repository_discovery_windows.py',
                 'tests/test_capabilities_bridge_guards.py',
                 'tests/test_review_gate_invariants.py', 'references/review-gate-invariants.md']
    required += ['jev_integration_evaluator/selection.py',
                 'scripts/select_placement.py', 'scripts/run_selection_demo.py',
                 'references/experimental-selection.md',
                 'tests/test_placement_selection.py', 'tests/test_placement_selection_cli.py',
                 'tests/test_placement_selection_wheel.py']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('placement-estimates', 'placement-interaction',
                              'placement-selection-envelope', 'placement-selection-request',
                              'placement-selection-summary', 'placement-selection')]
    required += ['jev_integration_evaluator/placement_selection.py',
                 'scripts/select_repository_placements.py',
                 'scripts/run_placement_selection_demo.py',
                 'scripts/build_placement_selection_schemas.py',
                 'references/placement-selection-v1.md',
                 'tests/test_repository_placement_selection.py',
                 'tests/test_repository_placement_wheel.py',
                 'tests/test_scope_review_conflicts.py',
                 'tests/test_placement_review_consistency.py',
                 'tests/test_placement_review_consistency_cli.py',
                 'examples/placement-selection/host/opaque.py']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('repository-placement-context-v1',
                              'repository-placement-review-v1',
                              'repository-placement-selection-v1',
                              'repository-scope-review-v1')]
    required += ['jev_integration_evaluator/repository_conclusion.py',
                 'scripts/conclude_repository.py',
                 'scripts/rebuild_repository_conclusion_schemas.py',
                 'scripts/run_repository_conclusion_demo.py',
                 'references/repository-conclusion-v1.md',
                 'tests/test_repository_conclusion.py',
                 'tests/test_repository_conclusion_cli.py',
                 'tests/test_repository_conclusion_wheel.py']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('repository-coverage-review-v1', 'repository-conclusion-v1')]
    required += ['jev_integration_evaluator/repository_run.py',
                 'jev_integration_evaluator/agent_review.py',
                 'jev_integration_evaluator/repository_selection.py',
                 'scripts/run_repository.py', 'scripts/run_repository_session_demo.py',
                 'scripts/run_repository_session_mutations.py',
                 'references/repository-session-command.md',
                 'tests/test_repository_run.py', 'tests/test_repository_run_wheel.py',
                 'tests/test_repository_selection.py',
                 'tests/test_repository_offline_agent_review.py',
                 'references/agent-review-protocol-v1.md',
                 'examples/repository-session/context.example.json',
                 'examples/repository-session/scope-denied.example.json']
    required += ['tests/path_corpus/README.md', 'tests/path_corpus/generate_support.py',
                 'tests/path_corpus/supported_host/host.py',
                 'tests/path_corpus/supported_host/main.py',
                 'tests/path_corpus/supported_host/expected.json',
                 'tests/test_path_corpus_connected.py',
                 'tests/test_path_corpus_oracle.py',
                 'tests/test_path_corpus_mutations.py',
                 'validation/path-corpus-support-v1.json',
                 'validation/PATH-CORPUS-CURRENT-SUPPORT.md']
    required += ['jev_integration_evaluator/integrations/js_backend.py',
                 'jev_integration_evaluator/integrations/js_lifecycle.py',
                 'jev_integration_evaluator/data/js_transform.cjs',
                 'jev_integration_evaluator/data/js_emit.cjs',
                 'jev_integration_evaluator/data/js_probe.cjs',
                 'jev_integration_evaluator/data/native_js_runtime.cjs',
                 'jev_integration_evaluator/template_node_connected_session.py',
                 'references/javascript-typescript-backend-v1.md',
                 'validation/JAVASCRIPT-TYPESCRIPT-SUPPORT.md',
                 'tests/test_js_lifecycle.py', 'tests/test_js_wheel.py',
                 'tests/test_js_backend_trusted.py',
                 'tests/test_js_entrypoint.py', 'tests/js_transform.test.cjs',
                 'tests/native_js_runtime.test.cjs']
    required += ['jev_integration_evaluator/template_catalog.py',
                 'jev_integration_evaluator/integrations/python_entrypoint.py',
                 'jev_integration_evaluator/data/python-bounded-tail-call.template.json',
                 'references/template-catalog-v1.md',
                 'references/template-python-entrypoint-v1.md',
                 'tests/test_template_catalog.py',
                 'tests/test_template_python_entrypoint.py',
                 'tests/test_template_materialization_wheel.py']
    required += ['jev_integration_evaluator/template_installation.py',
                 'references/template-installation-v1.md',
                 'scripts/build_template_installation_schemas.py',
                 'scripts/prepare_template_wheelhouse.py',
                 'tests/test_template_installation.py']
    required += ['jev_integration_evaluator/template_js_catalog.py',
                 'jev_integration_evaluator/data/javascript-recipe-c.template.json',
                 'scripts/build_javascript_template_schemas.py',
                 'tests/test_js_template_delivery.py',
                 'references/javascript-recipe-c-template-v1.md']
    required += ['jev_integration_evaluator/use_case_templates.py',
                 'jev_integration_evaluator/data/use-case-template-matrix-v1.json',
                 'references/use-case-template-matrix-v1.md',
                 'tests/test_reusable_templates.py',
                 'tests/test_use_case_retrieval_host.py',
                 'examples/use-case-host/retrieval_consumer.py',
                 'examples/use-case-host/retrieval_corpus_v1.json',
                 'references/retrieval-template-offline-v1.md',
                 'references/retrieval-template-connected-v1.md',
                 'references/template-claim-connected-v1.md',
                 'tests/test_use_case_claim_connected.py',
                 'tests/independent_hosts/claim_connected/connected_authority.py',
                 'references/graph-template-connected-v1.md',
                 'tests/test_use_case_graph_connected.py',
                 'tests/test_client_timeout_classification.py',
                 'tests/independent_hosts/graph_connected/connected_authority.py',
                 'references/retention-template-connected-v1.md',
                 'tests/test_use_case_retention_connected.py',
                 'tests/independent_hosts/retention_connected/connected_authority.py',
                 'tests/test_use_case_retrieval_connected.py',
                 'tests/independent_hosts/retrieval_connected/connected_authority.py',
                 'tests/test_use_case_graph_installed.py',
                 'references/graph-template-offline-v1.md',
                 'tests/test_use_case_claim_host.py',
                 'tests/test_use_case_claim_bind.py',
                 'tests/test_use_case_retrieval_bind.py',
                 'tests/test_use_case_retention_bind.py',
                 'examples/use-case-host/claim_consumer.py',
                 'references/claim-template-offline-v1.md',
                 'tests/test_use_case_completion_host.py',
                 'examples/use-case-host/completion_consumer.py',
                 'references/completion-template-offline-v1.md',
                 'schemas/use-case-template-matrix-v1.schema.json',
                 'jev_integration_evaluator/data/use-case-template-matrix-v1.schema.json',
                 'schemas/retrieval-answer-handoff-v1.schema.json',
                 'jev_integration_evaluator/data/retrieval-answer-handoff-v1.schema.json']
    required += ['jev_integration_evaluator/template_node_installation.py',
                 'jev_integration_evaluator/template_node_connected.py',
                 'jev_integration_evaluator/template_node_delivery.py',
                 'jev_integration_evaluator/template_node_session.py',
                 'references/template-node-installation-v1.md',
                 'references/template-node-connected-v1.md',
                 'tests/test_node_template_installation.py',
                 'tests/test_node_template_installed_upgrade.py',
                 'tests/test_node_template_installed_esm.py',
                 'tests/test_node_template_connected.py',
                 'tests/test_node_template_session.py']
    required += [f'{directory}/independent-esm-recipe-c-review-v1.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')]
    required += ['tests/independent_hosts/esm_recipe_c/README.md',
                 'tests/independent_hosts/esm_recipe_c/review-v1.json']
    required += [f'tests/independent_hosts/esm_recipe_c/{prefix}{name}'
                 for prefix in ('', 'versions/1.0.1/')
                 for name in ('host.mjs', 'start.mjs', 'package.json',
                              'package-lock.json')]
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('node-package-request-v1', 'node-package-plan-v1',
                              'node-package-receipt-v1', 'node-install-plan-v1',
                              'node-install-receipt-v1', 'node-connected-owner-v1',
                              'node-connected-session-v1',
                              'node-delivery-descriptor-v1',
                              'node-delivery-session-v1',
                              'node-delivery-status-v1')]
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('javascript-template-request-v1',
                              'javascript-template-manifest-v1',
                              'javascript-template-lock-v1')]
    required += ['jev_integration_evaluator/integrations/adaptation_runtime.py',
                 'jev_integration_evaluator/integrations/adaptation_adapter_lifecycle.py',
                 'scripts/prepare_adaptation_runtime.py',
                 'tests/test_template_adaptation_runtime.py',
                 'references/python-adaptation-runtime-v1.md']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('generated-adaptation-adapter-request-v1',
                              'generated-adaptation-adapter-plan-v1',
                              'adaptation-runtime-caller-review-v1',
                              'adaptation-runtime-review-receipt-v1')]
    required += ['jev_integration_evaluator/integrations/composite_console.py',
                 'tests/test_composite_console_delivery.py']
    required += ['jev_integration_evaluator/template_delivery.py',
                 'jev_integration_evaluator/template_delivery_journey.py',
                 'references/template-delivery-session-v1.md',
                 'examples/template-delivery-observation.json',
                 'tests/test_template_delivery_session.py',
                 'tests/test_template_delivery_installed.py',
                 'tests/test_template_delivery_composite.py']
    required += ['tests/independent_hosts/registered_alpha/installed_journey.py',
                 'tests/independent_hosts/registered_alpha/README.md',
                 'tests/test_registered_alpha_installed_faults.py']
    required += ['tests/independent_hosts/registered_alpha/installed_upgrade.py',
                 'tests/independent_hosts/registered_alpha/review-upgrade-v1.json',
                 'tests/independent_hosts/registered_alpha/versions/1.0.1/host.py',
                 'tests/independent_hosts/registered_alpha/versions/1.0.1/pyproject.toml',
                 'tests/test_registered_alpha_installed_upgrade.py']
    required += ['tests/independent_hosts/work_queue/README.md',
                 'tests/independent_hosts/work_queue/pyproject.toml',
                 'tests/independent_hosts/work_queue/src/work_queue/engine.py',
                 'tests/independent_hosts/work_queue/src/work_queue/cli.py',
                 'tests/independent_hosts/work_queue/qualification.py',
                 'tests/independent_hosts/work_queue/installed_journey.py',
                 'tests/independent_hosts/work_queue/review-v1.json',
                 'tests/independent_hosts/work_queue/oracle-v1.json',
                 'tests/test_work_queue_oracle.py',
                 'tests/test_work_queue_installed.py']
    required += [f'{directory}/registered-alpha-offline-report-v1.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')]
    required += [f'{directory}/registered-alpha-upgrade-report-v1.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')]
    required += [f'{directory}/work-queue-offline-report-v1.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')]
    required += ['tests/independent_hosts/registered_dual/README.md',
                 'tests/independent_hosts/registered_dual/pyproject.toml',
                 'tests/independent_hosts/registered_dual/src/registered_dual/alpha.py',
                 'tests/independent_hosts/registered_dual/src/registered_dual/work_queue.py',
                 'tests/independent_hosts/registered_dual/src/registered_dual/console.py',
                 'tests/independent_hosts/registered_dual/qualification.py',
                 'tests/independent_hosts/registered_dual/installed_journey.py',
                 'tests/independent_hosts/registered_dual/review-v1.json',
                 'tests/independent_hosts/registered_dual/oracle-v1.json',
                 'tests/test_registered_dual_composite.py']
    required += [f'{directory}/registered-dual-offline-report-v1.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')]
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('template-delivery-observation-v1',
                              'template-delivery-plan-v1',
                              'template-delivery-scope-v1',
                              'template-delivery-session-v1',
                              'template-delivery-journey-v1')]
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('template-request-v1', 'template-manifest-v1', 'template-lock-v1',
                              'template-entrypoint-binding-v1')]
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('template-package-request-v1', 'template-package-plan-v1',
                              'template-package-receipt-v1', 'template-install-plan-v1',
                              'template-install-receipt-v1')]
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('template-composite-package-request-v1',
                              'template-composite-package-plan-v1',
                              'template-composite-package-receipt-v1',
                              'template-composite-install-plan-v1',
                              'template-composite-install-receipt-v1')]
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('javascript-implementation-spec-v1',
                              'javascript-implementation-plan-v1',
                              'javascript-entrypoint-receipt-v1')]
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('repository-run-context-v1', 'repository-run-scope-v1',
                              'repository-run-selection-v1',
                              'repository-session-v1', 'repository-offline-agent-review-v1')]
    required += ['jev_integration_evaluator/windows_template_preflight.py',
                 'scripts/windows_template_preflight.py',
                 'tests/test_windows_template_preflight.py',
                 'references/windows-template-preparation-v1.md']
    required += [f'{directory}/windows-template-preflight-v1.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')]
    required += ['jev_integration_evaluator/windows_template_package_inputs.py',
                 'tests/test_windows_template_package_inputs.py']
    required += [f'{directory}/windows-template-package-inputs-v1.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')]
    required += ['jev_integration_evaluator/windows_template_owned.py',
                 'jev_integration_evaluator/windows_template_plan.py',
                 'jev_integration_evaluator/windows_template_install.py',
                 'jev_integration_evaluator/windows_template_tree.py',
                 'jev_integration_evaluator/windows_template_session.py',
                 'jev_integration_evaluator/windows_template_run.py',
                 'tests/test_windows_template_owned.py',
                 'tests/test_windows_template_session.py',
                 'tests/test_windows_template_delivery.py',
                 'tests/test_windows_template_run.py',
                 'references/windows-template-native-delivery-v1.md']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('windows-template-package-plan-v1',
                              'windows-template-package-receipt-v1',
                              'windows-template-install-plan-v1',
                              'windows-template-install-receipt-v1',
                              'windows-template-session-v1',
                              'windows-template-process-v1',
                              'windows-template-observation-v1',
                              'windows-template-run-v1',
                              'windows-template-run-intent-v1',
                              'windows-template-run-generation-v1',
                              'windows-template-run-selection-v1')]
    required += ['jev_integration_evaluator/windows_connected_verify.py',
                 'jev_integration_evaluator/windows_template_connected_binding.py',
                 'jev_integration_evaluator/windows_template_connected_delivery.py',
                 'jev_integration_evaluator/windows_template_connected_cli.py',
                 'tests/test_windows_connected_verify.py',
                 'tests/test_windows_template_connected.py',
                 'tests/independent_hosts/registered_alpha_connected_windows/qualification.py',
                 'references/windows-template-connected-v1.md']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('windows-connected-installed-binding-v1',
                              'windows-connected-delivery-plan-v1',
                              'windows-connected-delivery-scope-v1',
                              'windows-connected-session-v1',
                              'windows-connected-observation-v1')]
    for item in required:
        if not (ROOT/item).is_file():raise InputError('Required package file missing: '+item)
    front=(ROOT/'SKILL.md').read_text(encoding='utf-8').split('---',2)
    if len(front)!=3:raise InputError('SKILL.md needs YAML frontmatter')
    metadata=yaml.safe_load(front[1])
    if metadata.get('name')!='jev-integration-evaluator' or not metadata.get('description'):raise InputError('Invalid skill metadata')
    from jev_integration_evaluator import __version__
    project_version=re.search(r'^version\s*=\s*"([^"]+)"',
                              (ROOT/'pyproject.toml').read_text(encoding='utf-8'), re.M)
    if (metadata.get('metadata',{}).get('version')!=__version__
            or read_json(ROOT/'skill-package.json')['version']!=__version__
            or not project_version or project_version.group(1)!=__version__):
        raise InputError('Release version metadata disagree')
    schemas={}
    for path in sorted((ROOT/'schemas').glob('*.schema.json')):
        schema=read_json(path);jsonschema.Draft202012Validator.check_schema(schema)
        if schema!=read_json(ROOT/'jev_integration_evaluator/data'/path.name):raise InputError('Packaged schema mismatch: '+path.name)
        schemas[path.name.removesuffix('.schema.json')]=schema
    from jev_integration_evaluator.template_catalog import inspect_template, list_templates
    template_manifest=read_json(ROOT/'jev_integration_evaluator/data/python-bounded-tail-call.template.json')
    jsonschema.validate(template_manifest, schemas['template-manifest-v1'])
    javascript_manifest=read_json(ROOT/'jev_integration_evaluator/data/javascript-recipe-c.template.json')
    jsonschema.validate(javascript_manifest, schemas['javascript-template-manifest-v1'])
    if inspect_template('python.bounded-tail-call')['template_id']!=list_templates()['templates'][0]['template_id']:
        raise InputError('Packaged template catalog identity mismatch')
    if inspect_template('javascript.recipe-c')['template_id']!=list_templates()['templates'][1]['template_id']:
        raise InputError('Packaged JavaScript template catalog identity mismatch')
    from jev_integration_evaluator.use_case_templates import use_case_matrix, inspect_use_case_source
    use_cases=use_case_matrix()
    jsonschema.validate(use_cases,schemas['use-case-template-matrix-v1'])
    for row in use_cases['rows']:
        inspect_use_case_source(ROOT,row['id'])
    jsonschema.validate(read_json(ROOT/'examples/implementation/composite-selection.example.json'),
                        schemas['composite-selection-v1'])
    jsonschema.validate(read_json(ROOT/'examples/repository-session/context.example.json'),
                        schemas['repository-run-context-v1'])
    denied_scope=read_json(ROOT/'examples/repository-session/scope-denied.example.json')
    jsonschema.validate(denied_scope,schemas['repository-run-scope-v1'])
    if any(denied_scope['grants'].values()):
        raise InputError('Repository session example must deny every grant')
    from jev_integration_evaluator.integrations.contracts import validate_spec, validate_inventory
    from jev_integration_evaluator.integrations.recipes import transform
    implementation_examples=0
    for letter in 'abcdefghijklm':
        example=ROOT/'examples/implementation'/letter
        spec=validate_spec(read_json(example/'binding.example.json'))
        validate_inventory(example/'target',read_json(example/'reviewed-inventory.example.json'),spec)
        transform(example/'target',spec)
        implementation_examples+=1
    jsonschema.validate(read_json(ROOT/'examples/implementation/observation.example.json'),schemas['implementation-observation'])
    from jev_integration_evaluator.capabilities import _digest as capability_digest
    capability_examples={}
    for name,kind in (('report','repository-capabilities'),('nomination','candidate-nomination'),('admitted','admitted-nomination')):
        value=read_json(ROOT/'examples/capabilities'/(name+'.example.json'))
        jsonschema.validate(value,schemas[kind]);capability_examples[name]=value
    report,nomination,admitted=(capability_examples[name] for name in ('report','nomination','admitted'))
    if (report['report_sha256']!=capability_digest({k:v for k,v in report.items() if k!='report_sha256'})
            or report['snapshot_sha256']!=capability_digest(report['files'])
            or nomination['report_sha256']!=report['report_sha256']
            or admitted['report_sha256']!=report['report_sha256']
            or admitted['nomination_sha256']!=capability_digest(nomination)
            or admitted['source']!=nomination['source']):
        raise InputError('Capability example provenance mismatch')
    selected=[s for s in report['seams'] if s['seam_id']==nomination['seam_id']]
    if len(selected)!=1 or selected[0]['source']!=nomination['source']:
        raise InputError('Capability example nomination differs from discovered source')
    for source in [s['source'] for s in report['seams']]:
        path=safe_child(ROOT/'examples/capabilities/opaque_host',source['file'])
        if file_hash(path)!=source['file_sha256'] or not 1<=source['start_line']<=source['end_line']<=len(path.read_bytes().splitlines()):
            raise InputError('Capability example source identity mismatch')
    from jev_integration_evaluator.io import digest
    bridge_examples = {}
    for name, kind in (('capabilities','repository-capabilities'), ('nomination','candidate-nomination'),
                       ('admission','admitted-nomination'), ('prepared','repository-nominated-inventory-v1'),
                       ('review','repository-semantic-review-v1'), ('reviewed','repository-reviewed-inventory-v1')):
        value=read_json(ROOT/'examples/repository-capabilities'/(name+'.example.json'))
        jsonschema.validate(value,schemas[kind]);bridge_examples[name]=value
    cap_report,proposal,admission,prepared,review,reviewed=(bridge_examples[name] for name in
        ('capabilities','nomination','admission','prepared','review','reviewed'))
    for value,key in ((prepared,'prepared_sha256'),(reviewed,'reviewed_sha256')):
        if value[key]!=digest({k:v for k,v in value.items() if k!=key}):
            raise InputError('Bridge example digest mismatch')
    bridge_seams=[s for s in cap_report['seams'] if s['seam_id']==proposal['seam_id']]
    if (cap_report['report_sha256']!=capability_digest({k:v for k,v in cap_report.items() if k!='report_sha256'})
            or cap_report['snapshot_sha256']!=capability_digest(cap_report['files'])
            or len(bridge_seams)!=1 or bridge_seams[0]['source']!=proposal['source']
            or proposal['report_sha256']!=cap_report['report_sha256']
            or prepared['report_sha256']!=cap_report['report_sha256']
            or prepared['nominations']!=[proposal] or prepared['admissions']!=[admission]
            or admission['nomination_sha256']!=capability_digest(proposal)
            or admission['report_sha256']!=cap_report['report_sha256']
            or admission['source']!=proposal['source']
            or review['prepared_sha256']!=prepared['prepared_sha256']
            or reviewed['prepared_sha256']!=prepared['prepared_sha256']
            or reviewed['report_sha256']!=cap_report['report_sha256']
            or reviewed['bridge_engine_sha256']!=prepared['bridge_engine_sha256']
            or reviewed['review_sha256']!=digest(review)):
        raise InputError('Bridge example provenance mismatch')
    for envelope in (prepared,reviewed):
        jsonschema.validate(envelope['inventory'],schemas['inventory'])
        if envelope['inventory_sha256']!=digest(envelope['inventory']):
            raise InputError('Bridge example inventory digest mismatch')
        for item in envelope['inventory']['files']:
            if file_hash(safe_child(ROOT/'examples/repository-capabilities/host',item['file']))!=item['sha256']:
                raise InputError('Bridge example source identity mismatch')
    scope_examples = ROOT/'examples/placement-selection'
    for name, kind in (('context','repository-placement-context-v1'),
                       ('negative-context','repository-placement-context-v1'),
                       ('selection-review','repository-placement-review-v1'),
                       ('selection','repository-placement-selection-v1'),
                       ('scope-review','repository-scope-review-v1')):
        jsonschema.validate(read_json(scope_examples/(name+'.json')), schemas[kind])
    scope_report=read_json(scope_examples/'report.json')
    scope_review=read_json(scope_examples/'scope-review.json')
    from jev_integration_evaluator.placement_selection import _engine_identity as selection_engine_identity
    if (read_json(scope_examples/'context.json')['selection_engine_sha256']!=selection_engine_identity()
            or read_json(scope_examples/'selection.json')['selection_engine_sha256']!=selection_engine_identity()):
        raise InputError('Repository scope example engine identity mismatch')
    if (not scope_report['files'] or
            any(file_hash(safe_child(scope_examples/'host',item['file']))!=item['sha256']
                for item in scope_report['files']) or
            len(scope_review['files'])!=len(scope_report['files']) or
            len(scope_review['seams'])!=len(scope_report['seams']) or
            read_json(scope_examples/'negative-context.json')['outcome']!='no_useful_placement'):
        raise InputError('Repository scope example source or review mismatch')
    cfg=load_config(ROOT/'templates/jev-config.yaml')
    jsonschema.validate({'jev_analysis':cfg},schemas['config'])
    fixture_records=0
    for path in (ROOT/'examples/research').glob('*.jsonl'):
        if path.name in ('decisions.jsonl',):kind='decision'
        elif path.name.startswith('calibration-'):continue
        else:kind='run'
        for row in read_jsonl(path):jsonschema.validate(row,schemas[kind]);fixture_records+=1
    for kind in ('study-spec','threshold-spec','scenario-spec','monitor-spec'):
        jsonschema.validate(read_json(ROOT/'templates'/(kind+'.example.json')),schemas[kind])
    jsonschema.validate(read_json(ROOT/'templates/activation-v1.2.example.json'),schemas['activation'])
    from jev_integration_evaluator.monitoring import freeze_monitor
    freeze_monitor(read_json(ROOT/'templates/monitor-spec.example.json'))
    event_path=ROOT/'examples/research/decisions.jsonl'
    result=replay_decisions(read_jsonl(event_path),FixtureClient(read_json(ROOT/'examples/research/fixture-responses.json')))
    if result['evaluation_failures']:raise InputError('Exact offline replay fixture failed')
    forbidden={'.pem','.key','.p12','.ttf','.otf','.woff','.woff2'}
    for p in ROOT.rglob('*'):
        if any(x in ('node_modules','.venv','.git','__pycache__','.pytest_cache','build','dist') or x.endswith('.egg-info') for x in p.relative_to(ROOT).parts):continue
        if p.is_symlink():raise InputError('Package contains a symlink: '+str(p.relative_to(ROOT)))
        if p.is_file() and (p.suffix in forbidden or p.name=='.env'):raise InputError('Secret/font asset must not be bundled: '+str(p.relative_to(ROOT)))
    checked=0
    if check_manifest:
        manifest=ROOT/'SHA256SUMS'
        if not manifest.exists():raise InputError('Release checksum manifest is absent')
        listed=set()
        for line in manifest.read_text(encoding='utf-8').splitlines():
            expected,relative=line.split('  ',1)
            if not re.fullmatch('[a-f0-9]{64}',expected) or relative in listed:
                raise InputError('Malformed or duplicated release checksum entry')
            listed.add(relative)
            path=safe_child(ROOT,relative)
            if not path.is_file() or file_hash(path)!=expected:raise InputError('Checksum mismatch: '+relative)
            checked+=1
        def included(p):
            parts=p.relative_to(ROOT).parts
            return (p.is_file() and p.name!='SHA256SUMS' and p.suffix not in ('.pyc','.pyo','.zip','.whl')
                    and not any(x in ('node_modules','.venv','.git','__pycache__','.pytest_cache','build','dist')
                                or x.endswith('.egg-info') for x in parts))
        actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if included(p)}
        if actual != listed:
            raise InputError('Release manifest file set differs from package; added or missing files detected')
    return {'status':'passed','schema_count':len(schemas),'synthetic_records_validated':fixture_records,
            'implementation_examples_validated_without_execution':implementation_examples,
            'synthetic_observation_examples_validated':1,
            'capability_examples_validated_without_execution':len(capability_examples),
            'bridge_examples_validated_without_execution':len(bridge_examples),
            'offline_replay_decisions':result['evaluated'],'manifest_files_verified':checked,
            'network_requests':0,'target_code_executed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-manifest',action='store_true');p.add_argument('--out')
    a=p.parse_args()
    try:
        result=validate(a.check_manifest)
        if a.out:write_json(a.out,result)
        print(json.dumps(result,indent=2));return 0
    except Exception as exc:
        print('Validation failed: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
