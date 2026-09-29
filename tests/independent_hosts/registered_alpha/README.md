# Registered Alpha host

This package is an independently authored, finite Python console application
used as a target for installed-template qualification. The source contains no
generated integration. `registered-alpha` calls `make_request()` and then its
public registered-action entrypoint. The reviewed recipe C seam is
`registered_alpha.host:select_registered_tool`.

The host owns two actions, `inspect` and `summarize`. Both require a permitted
request; `summarize` additionally requires host approval. `inspect` is the
deterministic baseline. The host writes an append-only event containing a
stable task ID, action and synthetic item to `JEV_ALPHA_EFFECTS`. It refuses
a duplicate task ID under a file lock. `JEV_ALPHA_AUDIT` retains hashes of
runtime audit records without storing prompts or credentials. Both files must
be in owner-private directories outside the installed environment.

The separately configured synthetic implementation probe may instead set
`JEV_ALPHA_PROBE_EFFECTS_DIR` to an owner-private directory. Each probe process
then writes a PID-named effect file, so one scheduled mode cannot consume
another mode's task ID. Installed normal entrypoint qualification uses the
exact shared `JEV_ALPHA_EFFECTS` path to test duplicate-task enforcement
across launches.

The normal console command accepts only finite `JEV_ALPHA_INTENT` (`inspect`
or `summarize`), `JEV_ALPHA_ITEM` (`fixture-one` or `fixture-two`),
`JEV_ALPHA_PERMIT`/`JEV_ALPHA_APPROVED` (`0` or `1`), and an ASCII task ID of at
most 64 letters, numbers, `_` or `-`. Its default remains the permitted
`inspect` baseline. The caller's intent and approval are distinct: approval
never selects the action and the classifier never grants approval.

For a bounded live observation, set `JEV_ALPHA_HOLD=1` with owner-private
absolute `JEV_ALPHA_READY` and `JEV_ALPHA_RELEASE` paths. The action creates
the ready file while the process is alive, waits at most 15 seconds for the
release file, and only then writes its effect. A ready file alone does not
prove entrypoint completion, provider connectivity or authorization. The
qualification driver must observe the process identity, ready marker and
effect file independently.

This package is a disposable offline fixture. Its authored baseline can be
run before any template application. It is not a production app or a live
provider measurement.
