# Progressive onboarding

Start with facts already supplied by the user and the local scan. Do not ask for a repository path twice, ask about languages the scan identifies, or infer modification/network authority from access to files. Default to analysis and STANDARD depth. A null benchmark/trace path explicitly means unavailable, not permission to invent data.

The `onboard` command accepts an optional JSON answer object. It returns at most five missing fields at a time, keeps subsequent missing fields separate and reuses all answers. Fields are `objective`, `latency_budget_ms`, `cost_budget_per_task`, `risk_tolerance`, `environment`, `benchmark_path`, `trace_path`, and, only for implementation, `modification_authority`. Optional metadata includes mode, depth, repository and branding.

Infer non-sensitive facts from source/configuration and record the supporting location. Ask only for information that materially changes the result: the measurable goal, acceptable resource envelope, unacceptable errors, environment, available outcome evidence and explicit action scope. Local scanning may continue with unknown budgets; optimization admission and remote spend cannot treat unknown as zero.

QUICK identifies leading seams and rejections. STANDARD requires actual source review and complete report design. RESEARCH adds execution and analysis only for supplied/authorized traces, tests and study data. Selecting RESEARCH does not grant code-execution or API-spending permission.

For several repositories, scan each root separately with separate output directories; do not let equal relative paths imply the same source. Build a reviewed cross-repository plan using explicit repository identifiers and pinned revisions. Public API contracts, product prices and model pins must be freshly verified before a live rollout, not assumed from these offline examples.

When a caller asks for a reusable integration template, collect the current reviewed inventory and source-specific implementation specification first. `template validate` checks these inputs against the current host, and `template materialize` writes private planner inputs only. For a Python recipe C package with a reviewed console script, collect an explicit `template-entrypoint-binding-v1` file and use `template bind` before validation/materialization; see `references/template-python-entrypoint-v1.md`. None of these operations grants modification, execution, network, or activation authority. See `references/template-catalog-v1.md`.

For the six issue #59 use cases, read the [source-contract matrix](references/use-case-template-matrix-v1.md) first. A matched fixture digest and offline oracle do not establish a target binding or installed journey; each host needs fresh review and separate effect authority.
The separate [L graph](references/graph-template-offline-v1.md),
[D retrieval](references/retrieval-template-offline-v1.md),
[E completion](references/completion-template-offline-v1.md),
[M claim support](references/claim-template-offline-v1.md) and
[H retention](references/retention-template-offline-v1.md) operator references
describe their synthetic off-mode installed journeys and pending recipe-specific
console binds except E's bounded task-loop and H's explicit-choice bounded-loop
bindings. They do not establish
provider or benefit qualification.

For offline Node recipe C packaging, collect the independently retained JS modified verification receipt, exact applied source and render lock, native pinned Node/npm, trusted TypeScript 5.8.3, private offline npm cache, off configuration and secret references. The separate `node-package-request-v1` stages an owned generation only after two exact approvals; see `references/template-node-installation-v1.md`. Missing tooling or a changed source fails closed. A separate Node session may launch only that installed off-mode command under an exact scope and independently checked ready/effect paths; it does not grant connected mode. The independently pinned ESM fixture in `tests/independent_hosts/esm_recipe_c` exercises installed off-mode launch, versioned upgrade and retained rollback with raw host effects.

For a method, async function, or fixed-positional tail call, use the separate generated adaptation runtime profile in `references/python-adaptation-runtime-v1.md`. Collect an independent closed caller review, a static regular-package console declaration, source-matched semantic review, real host policy functions and exact source hashes. Prepare the generated bootstrap adapter, verify the legacy one-source adaptation, then rescan and review the adapted bytes before final adapter revision and installed execution. Its off/shadow receipt is separate from a verified implementation bundle for `template package`.

For installed Python host delivery, collect the externally trusted modified
implementation receipt, a reviewed full package-source digest, exact CPython
3.13/Linux x86-64 interpreter and build-tool pins, an offline hash-checked
wheelhouse, strict off configuration and secret references, and an owner-private
environment parent. `template package` and `template install-plan` are
read-only plans; build/install/recovery effects need their own exact scope.
Retain each plan/receipt digest outside its directory. Never infer launch,
connected mode, or measured benefit from an install receipt. See
`references/template-installation-v1.md`.

For one source-to-runtime run, create a private `template journey-create`
record after the reviewed implementation plan and before apply. Pin each
externally retained source/package/install receipt and exact plan with
`template journey-record`; inspect `template journey-status` for interrupted
effects and use the existing owner-specific recovery commands. Promote only a
verified installation with `template journey-promote`.

For an installed console invocation, also collect an independently authored
ready/effect observation schedule and exact operation scope. `template
delivery-plan` and `template deploy --plan` prepare the session without
running the host. A second `template deploy` with a valid scope starts only
the recorded off-mode console generation. Retain the returned session head
outside the session; use `template status` and `template observe` to distinguish
recorded observations from current process/readiness state. See
`references/template-delivery-session-v1.md`.

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

For reviewed JavaScript recipe C source, identify the exact `.mjs`, `.cjs` or
`.ts` implementation spec, package and lock digests, Node start entrypoint,
off-mode configuration and external trusted tooling before using the
[JS template catalog](references/javascript-recipe-c-template-v1.md).
Catalog materialization does not request install or launch authority.

For native Windows Python console work, inspect the read-only NTFS preparation
contract in [Windows template preparation](references/windows-template-preparation-v1.md)
before proposing any apply or installed journey. A preparation receipt is not
runtime or mutation authority. The selected package-input inventory is a
separate read-only API for reviewed files in its declared source traversal and
selected wheels; skipped directories remain outside that inventory;
it does not verify an applied implementation or run a native installer.
For a separately approved applied-source receipt and exact offline wheel
inventory, use the [native Windows API checkpoint](references/windows-template-native-delivery-v1.md)
for owner-private package/install generations, supervised off-mode normal
consoles, and retained installed-version cutover and rollback. Retain all
receipt digests externally. Local Windows 11 CPython 3.10/3.13/3.14 installed
fixture runs have retained private receipts.
Windows Server mutating and installed qualification remains pending.

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
