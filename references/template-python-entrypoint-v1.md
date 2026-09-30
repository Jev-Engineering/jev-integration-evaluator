# Python console entrypoint binding v1

`template bind` derives an exact, reviewed console caller contract for
`python.bounded-tail-call@1.0.0` recipe C, D, E, H or M. It reads source and `pyproject.toml`
without importing the target. It writes a bound template request and a binding
report outside the target. It does not modify, execute, install or activate the
host. Existing `template validate`, `template materialize`, `implement-*` commands
and legacy receipts retain their original behavior.

## Declared profile

The execution profile is one process on Linux x86-64, Python 3.10 or
newer, with a regular package in the repository root or `src/`, a
`pyproject.toml` `[project.scripts]` console command, and a reviewed recipe C/D/E/H/M
`module-tail-call-v1` seam. The console function lives in a separate module in
the same package. The selected host module owns the seam, a one-argument task
caller that directly returns that seam call, all recipe C policy/registry/guard
and observation functions, and the generated lifecycle functions. The reviewed
lock and off-mode JSON configuration sit beside the host module. Package data
must include them for an installed command.

Two console shapes are supported:

```python
def main():
    request = make_request()
    return run_task(request)

# Or one bounded workflow, where each request has a unique stable task ID:
def main():
    requests = make_requests()
    for request in requests:
        run_task(request)
    return 0
```

The factories and task caller must be unambiguous, local or statically resolved
reviewed functions. `make_request`/`make_requests` and the three startup input
factories are local, zero-argument functions in the console module. `run_task`
is a static package-local import resolving to the reviewed host module. The
task caller makes one direct seam call, so an effectful recipe C action is not
replayed within a task. A loop factory must return an actual list or tuple of
1–32 dictionaries with distinct nonempty string IDs in the reviewed
`runtime.task_field`. Generated code snapshots the collection and IDs before
startup, rejects a mutated ID before the task call, closes each original ID
after its final effect, and shuts down in `finally`. Task, completion and
shutdown exceptions retain the original task exception or cancellation.
The one-shot startup guard refuses a second launch in the same process.
Recipe E accepts only the bounded task-loop form ending in `return 0` because
its seam may return a structured completion report, which is not a console
exit code. The E task caller must still directly return the selected seam
call. A one-request `return run_task(request)` E console is rejected before
an edit is planned. Recipe H also accepts only the bounded task-loop form
ending in `return 0`: the retained-ID list is not a console exit code. Its
reviewed host consumer requires an explicit `/prune` choice and rejects
`/compact`, missing pins and changed retained bytes before writing a raw
effect. The binder verifies the unchanged request path and caller shape;
the code-owned consumer enforces those H semantics. Recipe M also requires the
bounded task-loop form because a claim disposition is not a console exit code.
The binder verifies caller identity and lifecycle only; citation checks,
approval, audit durability and release remain the M consumer's responsibility.
Recipe D requires the bounded task-loop form because a retrieval handoff result
is not a console exit code. The binder owns task lifecycle and caller identity;
corpus revision, provenance, contradiction retention, and answer release remain
the D consumer's code-owned checks. Recipe C retains both existing forms.
Other recipes remain unsupported by this binder.

The explicit binding file names the chosen script and existing host-owned
startup factories. It cannot synthesize policy, credentials, approvals, audit
storage, runtime locks, observations or authority:

```json
{
  "version": "1.0",
  "script": "my-existing-command",
  "startup_inputs": {
    "budget_limits": "reviewed_limits",
    "audit_log": "reviewed_audit",
    "dependency_plan": "reviewed_dependency_plan",
    "startup_options": "reviewed_startup_options"
  }
}
```

The request factory runs once before task preflight. The budget, audit,
dependency and startup-options factories run once after preflight and before
the workflow.
`startup_options()` returns keyword arguments for the existing generated
`start_jev_runtime` function. It may return `{}` for default-off startup.
Synthetic shadow requires a separate explicit host offline client and
`enable_experiment=True`. Connected canary/active modes must pass the exact
configuration, external authority verifier, environment digest and durable
ledger required by `HostRuntimeLifecycle`; a binding report is not authority.
Runtime validation remains code-owned.

## Binding and owned patch

Start with a current source-matched `template-request-v1` containing a reviewed
inventory and implementation spec. For this profile, the spec also declares a
regular `package_binding`, `host_lifecycle`, and reviewed `runtime_files` with
the lock and off JSON config. Then run:

```bash
jev-integration-evaluator template bind --repo /reviewed/host --request /private/request.json --binding /private/console-binding.json --out /private/new-binding
jev-integration-evaluator template validate --repo /reviewed/host --request /private/new-binding/template-request.json
jev-integration-evaluator template materialize --repo /reviewed/host --request /private/new-binding/template-request.json --out /private/new-render
jev-integration-evaluator implement-plan --repo /reviewed/host --inventory /private/new-render/reviewed-inventory.json --candidate REVIEWED_CANDIDATE --spec /private/new-render/implementation-spec.json --out /private/new-bundle
```

`template bind` writes `template-request.json`, `binding-report.json`, and a
completion marker in a new private directory. The derived spec adds
`entrypoint_binding` with the exact console script, module/function, source
hash, `pyproject.toml` hash, caller-chain hashes, request and task symbols,
startup input names, and single/loop shape. It adds only the entrypoint module
to `output.permitted_edits`. `implement-plan` then owns exact host, adapter,
entrypoint, lock and config bytes in one existing bundle, including preimages,
diff, manifest and verification schedule. `implement-apply`/`implement-rollback`
retain their exact digest, lock, journal and owned-byte rules.

Before handing an applied source tree to the environment installer in issue
#55 or the supervisor in issue #56, retain the implementation **bundle path**,
externally retained baseline and modified receipt SHA-256 digests, the
`implementation_status(..., trusted_receipt_sha256=MODIFIED_DIGEST)` readback
of `verified`, exact `owned_files` old/new hashes, the normal console script
name, and this source-bound entrypoint contract. The installer checks that
applied status independently and binds its own complete source snapshot. A
later source, policy, registry, `pyproject.toml`, lock or config change
requires a fresh binding and plan. A receipt copied from the bundle is not an
external trust anchor by itself.

## Qualification and limits

The component tests build and install two independently named synthetic
packages with regular and `src/` layouts, run their installed console scripts
in off and synthetic shadow modes, and observe effects and lifecycle state.
They also exercise a two-task loop with one coordinator and router, completion
after each effect, exception/cancellation propagation, repeated start, stale
sources, malformed/ambiguous bindings, and exact owned rollback. A shadow
decision can route without yielding an independent completed model assessment;
the installed synthetic loop test observed one or two client calls for two
routed tasks and does not claim two completed assessments.
The generated startup requires a connected `source_plan.files` entry for the
exact applied console source and the bound `pyproject.toml`, with their
reviewed SHA-256 values, before constructing the lifecycle. The lifecycle
then checks those file bytes. If either file is absent or its hash drifts,
startup fails closed. An installed wheel without the bound `pyproject.toml`
cannot claim connected authority from this profile; issue #57 must qualify
the installed source layout and its authority plan.

These tests do not
prove live provider benefit, production activation, arbitrary host packages,
framework autoloading, dynamic plugins, decorators, asynchronous entrypoints,
namespace packages, multiprocess workers or target-native isolation. Issue
#55 owns build/install receipts and issue #57 owns full independent connected
launch qualification. An unsupported parser or caller shape returns a fixed
diagnostic before producing a patch.

Python 3.10 uses the small conditional `tomli` dependency; Python 3.11+
uses `tomllib`. Build and test the installed host with its selected Python and
package metadata rather than assuming a source import proves console launch.
