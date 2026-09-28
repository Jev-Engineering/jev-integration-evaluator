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
