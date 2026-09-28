# Independent path-input host corpus

These project-owned synthetic hosts are authored independently of
`scripts/implementation_fixtures.py` and generated adapters. They are offline
qualification inputs, not measured application benefit. The oracle in
`tests/test_path_corpus_oracle.py` states expected behavior directly.

`supported_host/` is the independently authored flat Python host for the
connected offline path. Its separate source and baseline oracle are pinned in
`expected.json`. `tests/test_path_corpus_connected.py` takes only a copied host
path, discovers and reviews its opaque `reviewed_boundary`, records an offline
agent proposal and caller-owned policy, then exercises exact-scope plan,
baseline, apply and modified verification. The test checks off/shadow/active
receipts and exactly one completed effect, plus interruption/resume, dirty Git
edits, post-apply conflict preservation, tampered receipt and forged external
receipt-anchor rejection, and host
mutation detection. The verifier injects a synthetic runtime in scratch probes;
installed host startup remains unqualified until the separate host lifecycle
path is reviewed and integrated.

`opaque_host/` exercises an opaque callback name, exactly-once effect, denied
action, and a caller that must preserve the callback result. Its policy is:
permit only `read` and `summarize`; every other proposed action is denied
before an effect occurs. It currently has only path inspection and independent
baseline/oracle checks. The connected review-to-verification qualification is
limited to `supported_host/` and the trusted-host synthetic verifier.

Fixture provenance: newly authored for this repository, no external source or
private data. Changes to these source files and to their oracle need separate
review before qualification evidence is accepted.

`package_host/` is an ordinary importable Python package with a real runner,
host-owned finite permission rule, and a one-effect baseline. `missing_callbacks/`
has a possible seam but no independent observation, policy, or runtime owner.
`deterministic_only/` keeps exact arithmetic outside semantic placement scope.
`unsupported_language/` records an unqualified Go parser/backend path. Each
fixture has source hashes frozen in its own `expected.json`; these oracles are
separate from implementation fixture generation and from generated adapters.

Truncated discovery is checked by the path-only oracle. A forged external
baseline receipt anchor is rejected during trusted-host recovery; target-native
runner behavior remains unrun. The generated support report
records exact platform and source identities and keeps these limits explicit.
