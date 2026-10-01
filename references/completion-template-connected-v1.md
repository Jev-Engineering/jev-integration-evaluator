# E completion installed shadow protocol

`completion-e-v1` is a Linux x86-64 CPython 3.13 profile for a reviewed
`python.E@1.0` task-loop host. It extends the [offline E host]
(completion-template-offline-v1.md) with a separate installed connected shadow
plan. The fixture uses an independently authored `completion_consumer.py` for
the approved `close_and_label` action and `completion_oracle.py` to judge raw
state. An executor's `ok` report does not certify completion.

The installed journey in `tests/test_use_case_completion_connected.py` creates
a fresh reviewed source binding, materializes the template, verifies baseline,
applies and verifies the generated source and console, then builds and installs
an off-mode wheel. `template connected-installed-bind` derives exact source,
wheel RECORD and installed host, console, adapter and loader origins. The
connected plan checks those origins and a separate owner-private reference.
The normal installed `completion-host` command runs outside the checkouts
under one connected session owner and one durable task/cost ledger. An exact
expiring scope and separately issued detached P-256 signatures authenticate
the binding and shadow egress grant. The private issuer key never enters the
child. `E_CONNECTED_REF` and `E_AUTH_PUBKEY_FILE` are private absolute files;
their SHA-256 values are injected from the supervisor's approved plan.

The reviewed launch environment accepts `E_RAW_STATE_TEMPLATE` and
`E_EFFECT_RECEIPT_TEMPLATE` with `{task_id}` for fresh separate output files,
`E_READY_PATH`, and `E_TASKS=two|duplicate`. Each effect parent must be an
owner-only `0700` directory. The duplicate selector is a negative preflight
fixture: it exits before startup or effects. No free-form task list or host
callback is accepted. The fixed profile also accepts an owner-private
`SSL_CERT_FILE` for the local TLS test.

In connected shadow, the code-owned runtime calls the original E executor
exactly once. Only after it completes does a read-only assessment receive
the actual outcome and host-observed before/after state. A bounded wait lets
that assessment settle in the shared ledger before the task closes. It cannot
approve, retry or replace the executor; an observation or model failure
cannot change the original return or exception. An interrupt or interpreter
exit raised during observation is host control flow, not an observation
failure, and propagates unchanged. Synthetic E shadow without
a connected lifecycle retains its prior behavior.

The independent observation schedule reads first-task state and receipt,
second-task receipt, and the ready marker. The test separately checks both
raw states and receipts against the unchanged completion oracle. It proves
two intended local TLS typed calls, wrong-model and malformed/timeout
fallback effects, a wrong-key scope and reference drift refusal, duplicate
task preflight, replay refusal, and an exact owned stop. The local server is
explicitly synthetic. These results do not show a real JEV provider call,
measured benefit, or observed canary/active gate. Connected upgrade and
generation rollback remain pending; the separately qualified off-mode
upgrade/rollback and source rollback do not grant connected authority.

Use the existing `template bind`, `materialize`, implementation, package and
install CLI stages with exact reviewed inputs as in the offline E reference.
After installation, use `template connected-installed-bind`, then
`connected-plan --host-profile completion-e-v1`, `connected-configure`,
`connected-launch`, `connected-status` and `connected-stop` with independently
retained binding, plan and scope digests. Absent private references, mismatched
source/configuration, unsupported task selector, an unapproved scope or a
changed file fails closed. This fixture does not authorize a real endpoint,
credential, provider spend or activation.
