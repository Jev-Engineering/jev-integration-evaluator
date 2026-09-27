"""First-class placement patterns. These are rubrics, not claims of measured benefit."""
from __future__ import annotations

# Ordered labels include an abstention. The host narrows candidate actions further.
PATTERNS = {
    "A": {"name": "before_tool_execution", "category": "tool_routing", "timing": "after_candidate_generation_before_execution",
          "question": "Which legal candidate action advances the stated subgoal using the supplied evidence?",
          "choices": {"inspect": "Read the missing local state", "search": "Find missing evidence", "edit": "Apply an already scoped change", "test": "Check a stated hypothesis", "escalate": "A person must resolve a blocker", "uncertain": "Evidence is insufficient to choose"},
          "inputs": ["objective", "subgoal", "legal_candidates", "state", "recent_actions"],
          "benefit": "Test whether bounded selection reduces invalid or unnecessary tool calls.",
          "deterministic": ["tool allowlist", "argument schema", "resource scope", "authorization", "idempotency"]},
    "B": {"name": "expensive_or_irreversible_action", "category": "risk_assessment", "timing": "before_policy_gate",
          "question": "Does the proposed action exceed the explicitly authorized intent described in the evidence?",
          "choices": {"within_intent": "Evidence explicitly covers this action and scope", "outside_intent": "The action or scope contradicts stated intent", "uncertain": "Intent is missing or ambiguous"},
          "inputs": ["proposed_action", "authorization_scope", "user_intent", "environment"],
          "benefit": "Test whether semantic scope assessment catches unintended side effects before deterministic policy.",
          "deterministic": ["permissions", "explicit approval", "production scope", "transaction boundaries", "rollback readiness"]},
    "C": {"name": "tool_function_routing", "category": "tool_routing", "timing": "before_dispatch",
          "question": "Which available handler has the declared capability needed for this request?",
          "choices": {"deterministic_handler": "The request is completely covered by a deterministic handler", "specialist": "A registered specialist matches the semantic task", "general_model": "Open-ended generation or reasoning is required", "human": "An authorized person must decide", "uncertain": "No handler is supported by evidence"},
          "inputs": ["request", "handler_registry", "capabilities", "constraints"],
          "benefit": "Test bounded capability routing against the existing dispatcher.",
          "deterministic": ["registered handlers", "argument types", "handler availability", "permissions"]},
    "D": {"name": "retrieval_generation_boundary", "category": "retrieval_filtering", "timing": "after_retrieval_before_prompt_assembly",
          "question": "What is this passage's evidentiary relationship to the specific question?",
          "choices": {"supports": "Directly supports a relevant answer claim", "contradicts": "Directly contradicts a relevant answer claim", "background": "Related but not supporting evidence", "irrelevant": "Not relevant to the question", "uncertain": "Relationship cannot be established"},
          "inputs": ["query", "claim", "passage", "source_metadata"],
          "benefit": "Test evidence selection without silently deleting contradictory sources.",
          "deterministic": ["source identity", "access controls", "date comparisons", "citation IDs", "token budget"]},
    "E": {"name": "post_action_verification", "category": "result_verification", "timing": "after_operation_before_advancing_subgoal",
          "question": "Do the observed postconditions establish that the stated subgoal was accomplished?",
          "choices": {"succeeded": "All semantic postconditions are supported", "partial": "Only some are supported", "failed": "Evidence contradicts accomplishment", "unexpected_state": "An unrequested state change is observed", "uncertain": "Postconditions were not observed"},
          "inputs": ["subgoal", "expected_postconditions", "before_state", "after_state", "tool_result"],
          "benefit": "Test semantic completion rather than equating HTTP success with task success.",
          "deterministic": ["exit code", "HTTP status", "schema", "exact postconditions", "transaction integrity"]},
    "F": {"name": "agent_loop_transition", "category": "state_transition", "timing": "between_observe_act_iterations",
          "question": "Which transition is justified by the current goal, observed state, and unresolved blockers?",
          "choices": {"continue": "An available step can advance the goal", "gather_evidence": "Evidence needed for the next decision is missing", "replan": "The current plan cannot satisfy constraints", "complete": "All stated completion conditions have evidence", "human": "An authorized person must resolve the blocker", "uncertain": "The state is inadequate to classify"},
          "inputs": ["goal", "state", "completion_conditions", "blockers", "recent_progress"],
          "benefit": "Test fewer unproductive iterations and premature completions.",
          "deterministic": ["step budget", "time budget", "state invariants", "legal transitions", "verified completion"]},
    "G": {"name": "planner_executor_boundary", "category": "plan_validation", "timing": "after_planning_before_execution",
          "question": "Does the next plan step have unresolved dependencies in the supplied state?",
          "choices": {"resolved": "All declared prerequisites have evidence", "unresolved": "At least one declared prerequisite is not met", "uncertain": "Prerequisite evidence is incomplete"},
          "inputs": ["goal", "plan", "next_step", "dependency_state", "constraints"],
          "benefit": "Test pre-execution detection of semantic dependency errors.",
          "deterministic": ["dependency DAG", "step schema", "approval", "resource budget", "executor allowlist"]},
    "H": {"name": "context_and_compaction", "category": "context_retention", "timing": "before_context_eviction",
          "question": "Does this context item contain an unresolved constraint or fact necessary for the current task?",
          "choices": {"keep": "Preserve verbatim because an unresolved constraint or exact fact depends on it", "compress": "Its meaning matters but exact phrasing does not", "drop": "It is superseded or immaterial with supporting evidence", "uncertain": "Retention value cannot be established"},
          "inputs": ["current_task", "context_item", "unresolved_constraints", "superseding_evidence"],
          "benefit": "Test relevance-based retention; a generative model still performs any summarization.",
          "deterministic": ["pinned instructions", "source references", "token counting", "unresolved constraint retention", "user pruning choice"]},
    "I": {"name": "retry_recovery", "category": "recovery", "timing": "after_failure_before_retry",
          "question": "Which recovery strategy is supported by the error evidence and previous attempted fixes?",
          "choices": {"retry_same": "An explicitly transient failure justifies a bounded retry", "retry_modified": "Evidence identifies an allowed parameter correction", "inspect": "The failure cause is not yet known", "alternate_tool": "Another legal tool addresses the established cause", "replan": "The current strategy is contradicted", "rollback": "An approved reversible operation must be undone", "escalate": "Human input is required", "abort": "No safe useful continuation exists", "uncertain": "Evidence is insufficient"},
          "inputs": ["error", "previous_attempts", "state", "legal_recovery_actions"],
          "benefit": "Test reduced repetition and recovery calls, retaining deterministic backoff.",
          "deterministic": ["retry ceiling", "backoff", "transient status codes", "idempotency", "rollback authority"]},
    "J": {"name": "multi_agent_routing", "category": "agent_routing", "timing": "before_specialist_dispatch",
          "question": "Which registered specialist capability best matches this bounded subtask?",
          "choices": {"coding": "Implement a scoped change", "research": "Find and verify external evidence", "testing": "Design or run authorized tests", "security": "Assess a security-specific concern", "review": "Independently evaluate a patch", "data": "Inspect structured data", "human": "Human authority or expertise is required", "uncertain": "No capability match is supported"},
          "inputs": ["subtask", "specialist_capabilities", "allowed_agents", "budget"],
          "benefit": "Test reduced misrouting without granting additional agent permissions.",
          "deterministic": ["registered agents", "budget", "concurrency", "least privilege", "delegation depth"]},
    "K": {"name": "code_review_gate", "category": "code_review", "timing": "after_diff_and_tests_before_review_disposition",
          "question": "Does the supplied diff implement the specific acceptance criterion under review?",
          "choices": {"satisfied": "Changed behavior and tests support this criterion", "not_satisfied": "A required behavior is missing or contradicted", "uncertain": "The evidence is inadequate"},
          "inputs": ["acceptance_criterion", "diff", "test_results", "source_context"],
          "benefit": "Test atomic review checks, never automatic permission to merge.",
          "deterministic": ["CI status", "required approvals", "signature rules", "branch protections", "scope checks"]},
    "L": {"name": "graph_entity_mutation", "category": "entity_resolution", "timing": "after_candidate_generation_before_graph_mutation",
          "question": "Do these two candidate records refer to the same real-world entity according to the identity criteria?",
          "choices": {"same": "Identity criteria support one real-world entity", "related": "Entities are related but distinct", "different": "Identity evidence conflicts", "uncertain": "Identity cannot be established"},
          "inputs": ["left_record", "right_record", "identity_criteria", "provenance", "conflicting_evidence"],
          "benefit": "Test reduced false merges while retaining provenance and reversible mutations.",
          "deterministic": ["unique IDs", "graph schema", "referential integrity", "transaction", "merge approval", "provenance preservation"]},
    "M": {"name": "final_answer_validation", "category": "answer_validation", "timing": "after_generation_before_delivery",
          "question": "Does the cited evidence support this specific generated claim in its original context?",
          "choices": {"supported": "The source supports the precise claim", "contradicted": "The source contradicts the claim", "unsupported": "The source does not establish the claim", "uncertain": "The source context is insufficient"},
          "inputs": ["request", "claim", "citation", "source_context"],
          "benefit": "Test atomic evidence checks before a separate revision step.",
          "deterministic": ["required sections", "output schema", "citation existence", "verbatim spans", "length bounds"]},
    "NONE": {"name": "deterministic_or_generative_antipattern", "category": "do_not_use", "timing": "bypass",
             "question": "", "choices": {}, "inputs": [], "benefit": "Preserve deterministic computation or an appropriate generative model.", "deterministic": ["existing deterministic implementation"]},
}

# Each role is inferred from concrete calls, never only from the enclosing function name.
CALL_ROLES = {
    "model": ("llm.", "model.generate", "model.invoke", "chat.completions", "messages.create", "completion(", "generate_text", "ask_model", "planner.plan", "reasoner.", "system_one", "systemone"),
    "tool": ("execute_tool", "tools[", "tool.execute", "executor.", "execute_action", "dispatch", "run_tool", "registry[", "handlers["),
    "retrieve": ("retrieve", "retriever", "similarity_search", "vector.search", "search_documents", "hybrid_search", "graph.search", "bm25"),
    "write": ("unlink", "rmtree", "remove_file", "delete", "drop_table", "deploy", "publish", "send_email", "purchase", "migrate", "chmod", "set_permissions", "write_text", "write_bytes", "push", "commit", "restart", "graph.merge", "merge_entities", "database.update", "db.update", "subprocess."),
    "graph": ("graph.", "merge_entities", "sameas", "entity_match", "entity_resolve", "neo4j", "cypher", "deduplicate", "link_entity", "resolve_entity"),
    "agent": ("agent.", "agents[", "specialists[", "orchestrator.", "delegate", "spawn_agent", "select_agent"),
    "context": ("compact", "summarize", "prune", "truncate", "memory.", "context.", "retain", "filter_context"),
    "review": ("review", "get_diff", "run_tests", "pytest", "acceptance", "lint", "static_analysis"),
    "plan": ("planner.", "plan_steps", "validate_plan", "make_plan", "replan"),
    "observe": ("observe", "inspect_state", "get_state", "snapshot", "sense"),
    "verify": ("verify", "check_result", "validate_result", "postcondition", "citation_check"),
    "deterministic": ("sorted", "hashlib.", "hmac.", "json.loads", "jsonschema.", "re.match", "re.fullmatch", "os.path.exists", "path.exists", "check_permission", "has_permission", "is_authorized", "datetime.", "int", "float", "len", "sum", "min", "max", "abs", "round", "range", "isinstance", "math.", "type"),
}

def roles_for_calls(calls: list[dict]) -> dict[str, list[dict]]:
    result = {}
    for role, needles in CALL_ROLES.items():
        matches = []
        for c in calls:
            text = c["name"].lower()
            if any((text == n or ("." in n and n in text)) if role == "deterministic" else (text == n or n in text) for n in needles):
                matches.append(c)
        if matches:
            result[role] = matches
    return result
