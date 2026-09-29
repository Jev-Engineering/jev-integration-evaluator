# Registered Alpha host

This package is an independently authored, finite Python console application
used as a target for installed-template qualification. The source contains no
generated integration. `registered-alpha` calls `make_request()` and then its
public registered-action entrypoint. The reviewed recipe C seam is
`registered_alpha.host:select_registered_tool`.

The host owns two actions, `inspect` and `summarize`. Both require a permitted
request; `summarize` additionally requires host approval. `inspect` is the
deterministic baseline. The host writes an append-only event containing a
stable task ID, action and synthetic item to `REGISTERED_ALPHA_EFFECTS`. It refuses
a duplicate task ID under a file lock. `REGISTERED_ALPHA_AUDIT` retains hashes of
runtime audit records without storing prompts or credentials. Both files must
be in owner-private directories outside the installed environment.

The separately configured synthetic implementation probe may instead set
`REGISTERED_ALPHA_PROBE_EFFECTS_DIR` to an owner-private directory. Each probe process
then writes a PID-named effect file, so one scheduled mode cannot consume
another mode's task ID. Installed normal entrypoint qualification uses the
exact shared `REGISTERED_ALPHA_EFFECTS` path to test duplicate-task enforcement
across launches.

The normal console command accepts only finite `REGISTERED_ALPHA_INTENT` (`inspect`
or `summarize`), `REGISTERED_ALPHA_ITEM` (`fixture-one` or `fixture-two`),
`REGISTERED_ALPHA_PERMIT`/`REGISTERED_ALPHA_APPROVED` (`0` or `1`), and an ASCII task ID of at
most 64 letters, numbers, `_` or `-`. Its default remains the permitted
`inspect` baseline. The caller's intent and approval are distinct: approval
never selects the action and the classifier never grants approval.

For a bounded live observation, set `REGISTERED_ALPHA_HOLD=1` with owner-private
absolute `REGISTERED_ALPHA_READY` and `REGISTERED_ALPHA_RELEASE` paths. The action creates
the ready file while the process is alive, waits at most 15 seconds for the
release file, and only then writes its effect. A ready file alone does not
prove entrypoint completion, provider connectivity or authorization. The
qualification driver must observe the process identity, ready marker and
effect file independently.

This package is a disposable offline fixture. Its authored baseline can be
run before any template application. It is not a production app or a live
provider measurement.

`installed_journey.py` prepares a disposable copied host and, with an explicitly
reviewed offline wheelhouse and evaluator containing the #56 delivery APIs,
drives source verification, package/install, one supervised off-mode invocation,
raw effect inspection, disable and owned source rollback. It requires separate
owner-private workspace and external anchor directories. The script does not
create provider grants, credentials, connected-mode receipts or a benefit claim.

The opt-in `tests/test_registered_alpha_installed_faults.py` runs that driver
with `JEV_REGISTERED_ALPHA_INSTALLED_PYTHON` set to an evaluator interpreter
installed from the exact reviewed wheel and `JEV_REGISTERED_ALPHA_WHEELHOUSE`
set to its offline dependency closure. The test runs outside both checkouts.
From the evaluator checkout, run
`JEV_REGISTERED_ALPHA_INSTALLED_PYTHON=/absolute/private/venv/bin/python JEV_REGISTERED_ALPHA_WHEELHOUSE=/absolute/private/wheelhouse python -m pytest -q tests/test_registered_alpha_installed_faults.py`.
With either input absent, this opt-in test reports a skip. Its result validates
`registered-alpha-offline-report-v1` against the packaged strict schema.
The driver checks both installed distributions' metadata and module/entrypoint
paths without executing an interpreter during that audit. It rejects a changed
interpreter symlink target before any origin probe. The separately scoped
supervisor later starts the installed normal command. The driver injects an
interruption during the locked
dependency install, verifies the incomplete owned generation, refuses a blind
repeat, and uses the public exact-generation recovery API before retrying.
It then checks revoked launch scope, changed source and installed configuration,
an injected interruption before child release, same-run recovery, two repeated
normal-command attempts with the same task ID,
post-disable launch refusal and rollback refusal after a concurrent source edit.
Only the first installed command may append one `inspect` effect. The
interruption is a controlled offline fault injection before child release; it
does not establish recovery from every possible process crash point. The
driver retains the pending and recovered journal heads plus the reviewed
incomplete generation digest in the external anchor directory. A separate
source-stage test interrupts apply after its durable intent and requires owned
rollback. Other install interruption points, connected shadow and
provider/authorized modes remain separate unqualified rows.

`installed_upgrade.py` adds a separate offline, versioned installed journey.
`review-upgrade-v1.json` pins the original 1.0.0 source and an independently
authored 1.0.1 variant before either copy is scanned or packaged. The 1.0.1
change is confined to package metadata and the host-owned `inspect` effect
label: the registered decision stays `inspect`, while the raw effect says
`inspect-v2`. Both generations undergo source baseline, apply, modified
verification, offline package build and private install. The driver checks
installed host/evaluator origins and retains external receipt anchors.

One off-mode delivery session invokes 1.0.0, stops it, rejects wrong cutover
authority and drift, stages 1.0.1 in the same run ID, invokes it, disables it,
and restores the retained 1.0.0 generation with an exact rollback digest.
The original 1.0.0 observation expected an initially empty effect file, so it
cannot safely be replayed after two effects. A **new, separately scoped**
off-mode delivery session then invokes the retained 1.0.0 installed command
against a fresh two-row baseline. The independent event file must contain
exactly `inspect`, `inspect-v2`, `inspect` for three distinct task IDs. The
rollback validation session has its own run ID; the upgrade/rollback journal
keeps its original run ID. Both installed environments and all receipts remain
for review. This does not qualify an in-place replay of the first session's
old observation or a connected provider.

The opt-in `tests/test_registered_alpha_installed_upgrade.py` uses the same
`JEV_REGISTERED_ALPHA_INSTALLED_PYTHON` and
`JEV_REGISTERED_ALPHA_WHEELHOUSE` inputs as the fault journey. It validates
the strict packaged `registered-alpha-upgrade-report-v1` contract and reads
the raw event file independently of the driver report. The offline result is
synthetic fixture evidence only; provider reachability, authorized modes and
measured benefit remain unqualified.
