# Independent dual registered-action host

This disposable regular Python package combines two existing, separately
authored finite host seams under one console owner: `alpha.select_registered_tool`
and `work_queue.choose_operation`. The Alpha and work-queue single-host
packages cannot themselves share a process-local coordinator or task field.
This fixture adapts their source-supported shape into one reviewed package and
one stable `task_id`; it does not claim a distributed budget across packages.

`review-v1.json` freezes the host source and build bytes, both candidate
identities and source hashes. The driver also pins the independently authored
`oracle-v1.json`, which states the two
baseline JSONL effects and the two-call budget. `installed_journey.py` pins the
review digest, checks authored and copied source bytes before a fresh scan,
and compares both fresh candidates to the frozen review. It uses the public
composite template, implementation, package/install, journey and delivery APIs.
The selected normal console script (`registered-dual-queue` for this frozen
candidate ordering) runs from its installed environment
outside the checkout. Its two transformed seams invoke one
`HostRuntimeLifecycle` and one `BudgetCoordinator` during a code-owned offline
synthetic shadow, while `JEV_RUNTIME_MODE` remains `off`. Separate host-owned
JSONL files carry the actual Alpha and queue baseline effects. The host audit
records assessed IDs, shared coordinator identity, task hashes and call count;
the driver checks the raw files against the oracle independently.

The driver interrupts the waiting child before release, reconciles the same
delivery run, then launches once. It calls both transformed seams again while
the shared owner is still live: the two-call budget permits no new assessment,
and the audit records `shared_total_call_budget` twice. Both host effect
ledgers reject the repeated task. A separate invocation
with the same task ID is also rejected. The driver disables the session and
rolls back the owned composite source edits. Its strict report schema has an
identical packaged copy.

For the opt-in installed test, set `JEV_DUAL_INSTALLED_PYTHON` to the fresh
Linux x86-64 CPython 3.13 evaluator interpreter installed from the exact
reviewed wheel, and `JEV_DUAL_WHEELHOUSE` to its owner-private offline
dependency closure. Run `python -m pytest -q
tests/test_registered_dual_composite.py`. Missing installed inputs skip only
the installed row. The source-bound synthetic row still runs on Linux.

This is an offline fixture. The connected provider, authorized canary/active
operation, asynchronous cancellation, and measured task benefit remain unrun.
The source-stage combined check is synthetic; installed raw effects and
module/distribution origins are distinct evidence. The prior single-host
Alpha fault matrix and work-queue variation remain separate qualifications.
