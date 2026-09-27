# Placement playbooks: A–M

Each detector identifies a source-supported hypothesis. The agent must inspect the actual producer, consumer, alternatives and consequences before recommending a placement. All reported benefits begin unmeasured.

## A — before tool execution

**Timing:** `after_candidate_generation_before_execution`. **Hypothesis:** Test whether bounded selection reduces invalid or unnecessary tool calls.

**Atomic question:** Which legal candidate action advances the stated subgoal using the supplied evidence?

| Choice | Criterion |
|---|---|
| `inspect` | Read the missing local state |
| `search` | Find missing evidence |
| `edit` | Apply an already scoped change |
| `test` | Check a stated hypothesis |
| `escalate` | A person must resolve a blocker |
| `uncertain` | Evidence is insufficient to choose |

**Evidence:** objective, subgoal, legal_candidates, state, recent_actions.

**Host-owned checks:** tool allowlist, argument schema, resource scope, authorization, idempotency.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## B — expensive or irreversible action

**Timing:** `before_policy_gate`. **Hypothesis:** Test whether semantic scope assessment catches unintended side effects before deterministic policy.

**Atomic question:** Does the proposed action exceed the explicitly authorized intent described in the evidence?

| Choice | Criterion |
|---|---|
| `within_intent` | Evidence explicitly covers this action and scope |
| `outside_intent` | The action or scope contradicts stated intent |
| `uncertain` | Intent is missing or ambiguous |

**Evidence:** proposed_action, authorization_scope, user_intent, environment.

**Host-owned checks:** permissions, explicit approval, production scope, transaction boundaries, rollback readiness.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## C — tool function routing

**Timing:** `before_dispatch`. **Hypothesis:** Test bounded capability routing against the existing dispatcher.

**Atomic question:** Which available handler has the declared capability needed for this request?

| Choice | Criterion |
|---|---|
| `deterministic_handler` | The request is completely covered by a deterministic handler |
| `specialist` | A registered specialist matches the semantic task |
| `general_model` | Open-ended generation or reasoning is required |
| `human` | An authorized person must decide |
| `uncertain` | No handler is supported by evidence |

**Evidence:** request, handler_registry, capabilities, constraints.

**Host-owned checks:** registered handlers, argument types, handler availability, permissions.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## D — retrieval generation boundary

**Timing:** `after_retrieval_before_prompt_assembly`. **Hypothesis:** Test evidence selection without silently deleting contradictory sources.

**Atomic question:** What is this passage's evidentiary relationship to the specific question?

| Choice | Criterion |
|---|---|
| `supports` | Directly supports a relevant answer claim |
| `contradicts` | Directly contradicts a relevant answer claim |
| `background` | Related but not supporting evidence |
| `irrelevant` | Not relevant to the question |
| `uncertain` | Relationship cannot be established |

**Evidence:** query, claim, passage, source_metadata.

**Host-owned checks:** source identity, access controls, date comparisons, citation IDs, token budget.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## E — post action verification

**Timing:** `after_operation_before_advancing_subgoal`. **Hypothesis:** Test semantic completion rather than equating HTTP success with task success.

**Atomic question:** Do the observed postconditions establish that the stated subgoal was accomplished?

| Choice | Criterion |
|---|---|
| `succeeded` | All semantic postconditions are supported |
| `partial` | Only some are supported |
| `failed` | Evidence contradicts accomplishment |
| `unexpected_state` | An unrequested state change is observed |
| `uncertain` | Postconditions were not observed |

**Evidence:** subgoal, expected_postconditions, before_state, after_state, tool_result.

**Host-owned checks:** exit code, HTTP status, schema, exact postconditions, transaction integrity.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## F — agent loop transition

**Timing:** `between_observe_act_iterations`. **Hypothesis:** Test fewer unproductive iterations and premature completions.

**Atomic question:** Which transition is justified by the current goal, observed state, and unresolved blockers?

| Choice | Criterion |
|---|---|
| `continue` | An available step can advance the goal |
| `gather_evidence` | Evidence needed for the next decision is missing |
| `replan` | The current plan cannot satisfy constraints |
| `complete` | All stated completion conditions have evidence |
| `human` | An authorized person must resolve the blocker |
| `uncertain` | The state is inadequate to classify |

**Evidence:** goal, state, completion_conditions, blockers, recent_progress.

**Host-owned checks:** step budget, time budget, state invariants, legal transitions, verified completion.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## G — planner executor boundary

**Timing:** `after_planning_before_execution`. **Hypothesis:** Test pre-execution detection of semantic dependency errors.

**Atomic question:** Does the next plan step have unresolved dependencies in the supplied state?

| Choice | Criterion |
|---|---|
| `resolved` | All declared prerequisites have evidence |
| `unresolved` | At least one declared prerequisite is not met |
| `uncertain` | Prerequisite evidence is incomplete |

**Evidence:** goal, plan, next_step, dependency_state, constraints.

**Host-owned checks:** dependency DAG, step schema, approval, resource budget, executor allowlist.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## H — context and compaction

**Timing:** `before_context_eviction`. **Hypothesis:** Test relevance-based retention; a generative model still performs any summarization.

**Atomic question:** Does this context item contain an unresolved constraint or fact necessary for the current task?

| Choice | Criterion |
|---|---|
| `keep` | Preserve verbatim because an unresolved constraint or exact fact depends on it |
| `compress` | Its meaning matters but exact phrasing does not |
| `drop` | It is superseded or immaterial with supporting evidence |
| `uncertain` | Retention value cannot be established |

**Evidence:** current_task, context_item, unresolved_constraints, superseding_evidence.

**Host-owned checks:** pinned instructions, source references, token counting, unresolved constraint retention, user pruning choice.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## I — retry recovery

**Timing:** `after_failure_before_retry`. **Hypothesis:** Test reduced repetition and recovery calls, retaining deterministic backoff.

**Atomic question:** Which recovery strategy is supported by the error evidence and previous attempted fixes?

| Choice | Criterion |
|---|---|
| `retry_same` | An explicitly transient failure justifies a bounded retry |
| `retry_modified` | Evidence identifies an allowed parameter correction |
| `inspect` | The failure cause is not yet known |
| `alternate_tool` | Another legal tool addresses the established cause |
| `replan` | The current strategy is contradicted |
| `rollback` | An approved reversible operation must be undone |
| `escalate` | Human input is required |
| `abort` | No safe useful continuation exists |
| `uncertain` | Evidence is insufficient |

**Evidence:** error, previous_attempts, state, legal_recovery_actions.

**Host-owned checks:** retry ceiling, backoff, transient status codes, idempotency, rollback authority.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## J — multi agent routing

**Timing:** `before_specialist_dispatch`. **Hypothesis:** Test reduced misrouting without granting additional agent permissions.

**Atomic question:** Which registered specialist capability best matches this bounded subtask?

| Choice | Criterion |
|---|---|
| `coding` | Implement a scoped change |
| `research` | Find and verify external evidence |
| `testing` | Design or run authorized tests |
| `security` | Assess a security-specific concern |
| `review` | Independently evaluate a patch |
| `data` | Inspect structured data |
| `human` | Human authority or expertise is required |
| `uncertain` | No capability match is supported |

**Evidence:** subtask, specialist_capabilities, allowed_agents, budget.

**Host-owned checks:** registered agents, budget, concurrency, least privilege, delegation depth.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## K — code review gate

**Timing:** `after_diff_and_tests_before_review_disposition`. **Hypothesis:** Test atomic review checks, never automatic permission to merge.

**Atomic question:** Does the supplied diff implement the specific acceptance criterion under review?

| Choice | Criterion |
|---|---|
| `satisfied` | Changed behavior and tests support this criterion |
| `not_satisfied` | A required behavior is missing or contradicted |
| `uncertain` | The evidence is inadequate |

**Evidence:** acceptance_criterion, diff, test_results, source_context.

**Host-owned checks:** CI status, required approvals, signature rules, branch protections, scope checks.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## L — graph entity mutation

**Timing:** `after_candidate_generation_before_graph_mutation`. **Hypothesis:** Test reduced false merges while retaining provenance and reversible mutations.

**Atomic question:** Do these two candidate records refer to the same real-world entity according to the identity criteria?

| Choice | Criterion |
|---|---|
| `same` | Identity criteria support one real-world entity |
| `related` | Entities are related but distinct |
| `different` | Identity evidence conflicts |
| `uncertain` | Identity cannot be established |

**Evidence:** left_record, right_record, identity_criteria, provenance, conflicting_evidence.

**Host-owned checks:** unique IDs, graph schema, referential integrity, transaction, merge approval, provenance preservation.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## M — final answer validation

**Timing:** `after_generation_before_delivery`. **Hypothesis:** Test atomic evidence checks before a separate revision step.

**Atomic question:** Does the cited evidence support this specific generated claim in its original context?

| Choice | Criterion |
|---|---|
| `supported` | The source supports the precise claim |
| `contradicted` | The source contradicts the claim |
| `unsupported` | The source does not establish the claim |
| `uncertain` | The source context is insufficient |

**Evidence:** request, claim, citation, source_context.

**Host-owned checks:** required sections, output schema, citation existence, verbatim spans, length bounds.

**Bypass / experiment:** bypass when deterministic evidence resolves the decision, the feature is off, an immutable valid cache entry applies, or resource/authorization gates prevent assessment. Compare matched tasks with independently verified outcomes; test missing evidence, malformed answers, low confidence and false blocks. Use the existing permitted baseline or inspection/approval route on failure.

## Cross-placement design

Router + verifier, retrieval filter + claim checker, plan validator + risk assessment, context selector + recovery controller, and entity classifier + graph mutation gate can complement each other. They can also share error sources. The inventory emits interaction hypotheses with **zero** assumed positive synergy. Same-boundary A/C routing duplicates conflict by default. Use isolated ablations and measured joint latency before changing those assumptions.

Do not implement an entire illustrative architecture. A narrowly targeted verifier may be worth more than a router, and a strong deterministic implementation can make every proposed JEV box unnecessary. Keep retrieval contradictions and provenance rather than filtering solely to consensus; uncertain entity matches must not merge by default. Context decisions select what survives; a separate model performs any authorized generative compaction.
