# Native Windows installed connected shadow

The `windows-connected` CLI is an additive native Windows path for a separately
reviewed Python console host. It starts with actual off-mode native package and
install receipts, then recomputes the wheel `RECORD`, installed host, adapter,
console and loader bytes, NTFS file identities, owner/DACL material, and the
source plan. The binding report grants no connected exposure. The installed
off-mode configuration does not turn on because a descriptor exists.

Use the normal native `template windows-package` and `template windows-install`
steps first. Retain their exact receipt SHA-256 values independently. Then run
`jev-integration-evaluator windows-connected bind --help` for the finite
package/install/binding inputs. `plan --help` adds an owner-private public
verification key, owner-private exact connected configuration reference,
owner-private observation directory, and a predeclared four-role schedule.
`configure --help` creates one private session and records the reviewed plan.
`launch`, `status`, `observe`, and `stop` use that same session, plan, installed
binding and install plan. `launch` and `stop` require separately issued,
expiring P-256 signed scopes and their independently retained exact SHA-256
values. `observe` requires the externally retained process identity SHA-256.
CLI output contains only receipt identities and fixed status codes; it does
not print the private reference or credential value.

The normal installed console runs in a single owned Windows Job. A durable
launch intent and process identity are recorded before release from a pipe
gate. Status recomputes the source and installed origins. A predeclared ready
marker can be read while the Job is live; entrypoint, integration and outcome
markers can be read after exit or stop. Monitoring can suspend but cannot
restore authority. Stop targets the exact retained Job and verifies process
death. A launch intent makes replay a refusal, including after an interrupted
attempt. Recovery of an unknown pending launch requires independent review.

The child receives a credential reference resolved only at launch, public
key and reference hashes, and a bounded environment. It never receives the
issuer private key. Windows CNG verifies signed grants using a pinned
System32 `bcrypt.dll` identity. The installed host independently checks the
current private reference, public key, NTFS owner/DACL and hardlink state, and
the runtime checks installed origin drift before routes. Source and scope
digests alone are not authority: an independent issuer must authenticate the
exact grant and scope. A local synthetic issuer in tests is only a protocol
fixture.

The native fixture uses a separate registered host and proves offline package
and install, a hard permit refusal, hardlink drift refusal, blocked pending
launch replay, a durable shadow ledger, one-shot replay, exact Job stop, and a
permitted loopback TLS typed response with independent ready and effect
readback. A second installed task receives a wrong-model local response and
still executes only its baseline action. It never contacts a JEV provider. Its local TLS
certificate, issuer key, fixture request and observations are private test
inputs. The response and effects are explicitly synthetic. Run its focused
case with a reviewed private offline wheelhouse:

```powershell
$env:JEV_WINDOWS_TEMPLATE_WHEELHOUSE = 'C:\absolute\owner-private\wheelhouse'
python -m pytest -q tests/test_windows_template_connected.py tests/test_windows_connected_verify.py
```

Native Windows 11 NTFS and the exact interpreter/tooling used by the recorded
test are the only covered hosts until the required hosted matrix runs. The
legacy off-mode native router, package, install and session APIs retain their
prior receipts. This path supports synthetic shadow only. Live provider
credentials, authenticated external issuer operations, observed canary and
active gates, production monitoring, measured benefit, arbitrary target code,
network shares and non-NTFS filesystems remain unqualified. Missing or
untrusted raw gate inputs never become positive activation receipts.
