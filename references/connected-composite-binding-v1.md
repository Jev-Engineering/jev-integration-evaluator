# Installed composite connected binding v1

`connected-installed-composite-binding-v1` is a read-only Linux CPython 3.13
provenance report for two to four reviewed Python placements in one installed
package. The separately reviewed `registered_dual_connected` fixture exercises
**two** placements; no three- or four-placement journey is qualified here.

The binder accepts the off-mode composite package and install plans and
receipts plus two receipt digests retained outside the generated bundle. It
recomputes both installed statuses, then reads the composite specifications,
selected-set and console contracts from the source bundle. It checks the
exact source-to-wheel map, wheel `RECORD`, installed `RECORD`, installed module
bytes and the retained `pyproject.toml`. Every host and adapter has its own
origin. The console and options loader have one shared origin each. The
source plan deterministically includes each exact origin once. Installed
origins must be owned regular files with one link and private permissions.

The report binds candidate IDs, selected-set and composite-bundle digests,
package and install plan/receipt digests, wheel and installed generation
digests, source hashes and exact installed paths. A digest of this report is
**not** execution authority. An installed host must independently retain and
authenticate that exact digest, its public verifier key and an expiring egress
grant. `HostRuntimeLifecycle` validates both adapters against one report and
uses one durable coordinator and stable task owner across them. An origin,
environment, verifier, source, grant or budget drift suspends the runtime.

After the off package and install receipts have been independently retained,
derive the report through `template connected-composite-installed-bind` with
`--package-plan`, `--package-receipt`, `--install-plan`, `--install-receipt`,
both `--trusted-*-receipt-sha256` values and a new `--out` path outside the
host and installed environment. The command reads the exact generation again;
it does not launch the console.

The separate connected supervisor starts off, requires an explicit shadow
plan and expiring launch scope, and records intent before releasing the
installed console. The dual fixture's issuer is synthetic and its endpoint is
local TLS. Its public-only options loader is source reviewed; the signing key
stays outside the installed host and package. Package/install receipts remain
off-mode provenance. Connected canary and active remain unavailable without
an observed **combined** treatment study, raw recomputed gate evidence, and
independently authenticated exact deployment and runtime receipts covering
both placements. A single-placement study cannot authorize the composite.
Connected upgrade and rollback remain separate pending work.
