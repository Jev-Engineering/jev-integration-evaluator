# Independent work-queue host

This separately authored regular Python package varies the registered-tool
layout from Alpha. `work-queue` calls `work_queue.cli:main`, which constructs a
job and enters `work_queue.engine:choose_operation`. The existing baseline
`enqueue` operation writes a real JSONL event; `complete` requires separate host
permission and completion approval. Both use an owner-private effect ledger and
refuse a repeated job ID. The source contains no generated adapter.

`review-v1.json` freezes the current source bytes and pattern C seam.
`oracle-v1.json` independently freezes four pre-template cases, including the
approved `complete` intent that still takes the deterministic `enqueue`
baseline before integration. `tests/test_work_queue_oracle.py` checks these
cases, source binding, materialization, baseline verification, reviewed apply,
and modified verification on a disposable copy. Synthetic modified verification
uses PID-separated probe effects; it is not installed-host evidence.

`installed_journey.py` requires Linux x86-64 CPython 3.13, an owner-private
offline wheelhouse containing the exact evaluator wheel and dependency closure,
and separate owner-private workspace and external anchor directories. It copies
the authored host, checks the pinned `review-v1.json` digest and every reviewed
source/build file before and after copying, and rejects unexpected source tree
entries before a fresh source scan can select a candidate. It then uses the
public template APIs for binding, planning,
verification, package/install, journey promotion, supervised off-mode normal
command, observation, disable and owned source rollback. Its read-only origin
audit checks the pinned interpreter symlink, both installed distributions and
the host entrypoint path without executing a second interpreter. A controlled
pre-release start interruption is reconciled under the same run ID; one later
normal invocation writes the independently expected `enqueue` event. A repeat
of that installed command with the same job ID is refused by the host ledger.
The output follows strict `work-queue-offline-report-v1` with a packaged mirror.
Focused negative tests change authored bytes, copied bytes, and the review itself;
each stops before source matching, planning, or an external effect.

For the opt-in test, set `JEV_WORK_QUEUE_INSTALLED_PYTHON` to an evaluator
interpreter installed from the exact reviewed wheel and
`JEV_WORK_QUEUE_WHEELHOUSE` to that wheelhouse, then run
`python -m pytest -q tests/test_work_queue_installed.py` from the checkout.
The test process starts the driver outside both checkouts, and the normal host
command runs from its installed environment. Missing inputs produce a skip.
The declared build tools are setuptools 84.0.0 and wheel 0.48.0; the installed
profile is Linux x86-64 CPython 3.13. The report retains source, modified,
install and raw-effect digests, one run ID and installed module paths. External
anchor files retain stage-specific receipt and session heads.

| Qualification row | State |
| --- | --- |
| Frozen source oracle and source-bound recipe C plan | Offline fixture test |
| Exact installed package/console, raw `enqueue`, disable and rollback | Opt-in installed test |
| Interrupted pre-release start and duplicate job effect | Opt-in installed test |
| Composite two-placement shared budget and identity | Pending distinct fixture |
| Connected provider, authorized mode and measured benefit | Pending external authority and study |

This is a second **single-placement offline fixture**. It is not a composite
shared-budget qualification, provider connection, authorized canary/active
operation, measured benefit, or a production host. The prior Alpha fault slice
remains the stronger interruption/drift matrix; this host demonstrates a fresh
naming/layout instantiation without hand editing generated source.
