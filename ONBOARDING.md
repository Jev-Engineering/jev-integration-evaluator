# Progressive onboarding

Start with facts already supplied by the user and the local scan. Do not ask for a repository path twice, ask about languages the scan identifies, or infer modification/network authority from access to files. Default to analysis and STANDARD depth. A null benchmark/trace path explicitly means unavailable, not permission to invent data.

The `onboard` command accepts an optional JSON answer object. It returns at most five missing fields at a time, keeps subsequent missing fields separate and reuses all answers. Fields are `objective`, `latency_budget_ms`, `cost_budget_per_task`, `risk_tolerance`, `environment`, `benchmark_path`, `trace_path`, and, only for implementation, `modification_authority`. Optional metadata includes mode, depth, repository and branding.

Infer non-sensitive facts from source/configuration and record the supporting location. Ask only for information that materially changes the result: the measurable goal, acceptable resource envelope, unacceptable errors, environment, available outcome evidence and explicit action scope. Local scanning may continue with unknown budgets; optimization admission and remote spend cannot treat unknown as zero.

QUICK identifies leading seams and rejections. STANDARD requires actual source review and complete report design. RESEARCH adds execution and analysis only for supplied/authorized traces, tests and study data. Selecting RESEARCH does not grant code-execution or API-spending permission.

For several repositories, scan each root separately with separate output directories; do not let equal relative paths imply the same source. Build a reviewed cross-repository plan using explicit repository identifiers and pinned revisions. Public API contracts, product prices and model pins must be freshly verified before a live rollout, not assumed from these offline examples.

When a caller asks for a reusable integration template, collect the current reviewed inventory and source-specific implementation specification first. `template validate` checks these inputs against the current host, and `template materialize` writes private planner inputs only. Neither operation grants modification, execution, network, or activation authority. See `references/template-catalog-v1.md`.

Example answered intake:

```json
{
  "objective": "Improve independently verified task completion without more total model calls",
  "latency_budget_ms": 250,
  "cost_budget_per_task": 0.01,
  "risk_tolerance": "Never bypass host approval, permissions, or irreversible-action policy",
  "environment": "experimental",
  "benchmark_path": null,
  "trace_path": null
}
```

When benchmark evidence is absent, recommend constructing/fixing that evidence before integration. Do not weaken success criteria merely to make a placement look useful.

## Multi-placement and canary extensions

Ask only when the workflow reaches the relevant gate: which placements share a task budget; whether tasks span processes; the stable combined-treatment canary scope; which source-reviewed gates belong to the deployed treatment; who retains threshold/study digests; and which cohorts/operational limits require complete monitoring. Reuse recorded constraints and source evidence. Missing costs or outcome data are blockers, not zero estimates. Scenario alternatives must be explicitly declared assumptions, not guessed probabilities. Do not demand monitoring setup for analysis-only intake. See `references/operational-evidence-v1.2.md`.

For connected host runtime qualification, record the pinned endpoint/model,
environment and reviewed source/configuration digests, budget scope, host-owned
ledger location, and the independent authority that verifies egress,
deployment, study and exact-runtime receipt digests. Do not ask for or store a
plaintext key; the runtime accepts `env:TYPESAFE_API_KEY` only as a reference.
Ask for raw observed holdouts and full scheduled paired outcomes only when
canary or active treatment is proposed. Preserve missing outcomes in the
denominator. A connectivity marker, installer receipt, config flag, or
fabricated test fixture cannot establish deployment eligibility. See
`references/host-runtime-lifecycle.md` for the mode table and restart contract.
