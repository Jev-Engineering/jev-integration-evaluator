# coding-agent

A miniature injectable Python agent exposes routing, loop, planning, retry, context, delegation, review and publication seams. Model/executor objects are injected; the scanner does not execute them.

Run from the skill root using the commands in the main README. Do not treat this fixture as production guidance or a live model benchmark.

## Issue 48: registered capability routing

`agent.py::dispatch_once` accepts an advisory router choice among three versioned
registered capabilities. Immediately before a tool call, the host checks registry
membership, permission, and exact argument names and types. A denied, malformed,
unregistered, or abstaining choice cannot reach the executor. The router cannot
change the argument payload or grant itself permission.

The frozen offline study lives in `routing-study-v1.json`. Its input cases and
independently authored route/postcondition oracle are in separate JSON files;
`routing-proposals-v1.json` contains **synthetic** model and JEV choices. The
runner also includes a fixed deterministic cue router. It reproduces the
original fixture's registry-only current behavior, and separately displays
the same choices through the new host guard. All calls go to an isolated fake
executor that only records the proposed name and arguments. No real tool,
provider, target application, or deployment is involved.

From this directory, run:

```powershell
python routing_study.py --out routing-report.json
python -m pytest -q test_agent.py
```

Use a new report path on each run. The report includes source, input, and runner
SHA-256 hashes, every held-out case, all comparator call records, safety and
error counts, preset thresholds, and an explicit disposition. Cost and latency
figures are predeclared synthetic assumptions, not measured provider use. The
study cannot establish live benefit or activation eligibility.
The frozen holdout contains no scheduled timeout or provider failure; unit tests
exercise fail-closed behavior for those failures. The runner verifies the
isolated fake executor's recorded call name and full arguments for every arm.

## Issue 46: independently observed completion

`agent.py::run_steps` remains the historical success-flag comparator. The
separate `completion_study.py` runs that function with its original one-argument
`execute_tool(proposal)` call, then runs deterministic and bounded synthetic JEV
completion arms on fresh in-memory store clones. The host registers only
`set_status` and `add_label`, checks exact arguments, task identity, permission,
legal transitions and a three-attempt cap, and binds every scripted effect to
the action, arguments, before revision and raw-state digest. The JEV label is
advisory; it cannot issue an action or grant permission.

The host observer captures before and after snapshots independently of
`result.success`. A second module, `completion_oracle.py`, reads raw checkpoints
and receipts against a separate scorer-only file. It checks the exact final
field set and labels, catches unrequested mutations, and counts continuation
after a raw checkpoint already met the objective. H10 is rejected for targeting
another task; H11 is permission-denied; H18 legally sets a goal-wrong status;
H19 deliberately simulates an executor side effect and records a contract
violation. All calls and state are synthetic.

The frozen schedule is eight calibration and 24 holdout cases in
`completion/`. Independent pre-result review by graph44 on 2026-09-28 UTC is
recorded in the scorer metadata. The holdout CLI requires those fields and an
externally checked exact study-spec digest. The approved pre-metadata digest is
retained in the study note. The single reviewed holdout run is recorded in
`validation/issue46-holdout-report.json`. To run the calibration fixture:

```powershell
python examples/coding-agent/completion_study.py --split calibration --out validation/issue46-calibration-report.json
python -m pytest -q tests/test_coding_agent_completion.py
```

On the 24-case synthetic holdout, verified completion was 12/24 for each of
current, deterministic and JEV, so JEV gained zero cases over either comparator.
JEV had two false completions, one faulty-executor safety violation and five
uncertain terminal episodes. The predeclared decision was `disable_for_fixture`.
The historical arm had nine false completions and two unauthorized fake executor
calls; the deterministic arm had zero false completions and zero unauthorized
calls. Every arm kept all 24 episodes in its denominator. All six arm orders
occurred four times. The calibration report remains an offline harness check.
Costs and assessment latencies are preset synthetic assumptions. The report
counts missing latency observations, gives assessment p50/p95, and separately
measures local fixture runner wall time. No provider, production executor or
real agent was run. The synthetic result does not support live adoption or
deployment.
