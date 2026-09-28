# Experimental placement selection — local implementation checkpoint

**Historical checkpoint:** Open-issue and "remaining delivery work" statements
below describe the issue #7 development checkpoint, not the final roadmap
state. The [final acceptance ledger](../roadmap-acceptance-ledger.json) was
published in [PR #39](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/39).
For current bounded composite support see
[composite transactions](composite-transactions-v1.md).

Tracking issue: [#7](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/7), under [epic #3](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/3).

This additive checkpoint distinguishes **reviewed experimental preparation** from **optimization conditional on supplied estimates**. It is not the repository command in issue #4, an agent review implementation, a new source recipe, or an activation gate. Issue #7 and the epic remain open until their integration, review, qualification, and merge requirements are satisfied.

## Authority and evidence

`select_placement` accepts a complete existing inventory and a versioned request. It does not scan or import the target. The request pins the entire inventory digest and the selection engine digest. Experimental preparation additionally pins the complete implementation specification. The selector checks agreement between inventory file records, candidate file identities, source-matched semantic reviews, and the recorded analysis digests.

The selection-engine identity includes the selector, optimizer, contract and serialization helpers, the existing inventory schema, and the six new selection schemas. Changing those bytes invalidates an older request. This identifies the source contract, not a qualified interpreter or a cryptographic signer. Environment qualification must be recorded separately.

Experimental selection requires an approval digest supplied through the caller's trusted channel. A reviewer name, scope reference, matching hash, or well-formed agent response is not proof of human identity or actual permission. Computing a hash is never approval. The library's caller must authenticate its approval source; the stdin envelope cannot supply its own approval argument.

All results retain `execution_authorized`, `target_mutation_authorized`, `live_spend_authorized`, `runtime_activation_authorized`, and `benefit_demonstrated` as false. `adoption_recommendation` is null. Even fully populated live bounds do not grant spending authority. Live cost bounds are retained, not converted or enforced by this selector; an eventual live executor must have independently approved units, policy, and enforced budgets.

## Public functions

```python
from jev_integration_evaluator.selection import (
    selection_engine_sha256,
    request_sha256,
    select_placement,
    verify_selection,
    prepare_experimental_plan,
)
```

`selection_engine_sha256()` identifies the current selection implementation and its schemas. `request_sha256(request)` validates and hashes a request; it does not approve it.

`select_placement(inventory, request, approved_request_sha256=None)` returns a sealed selection record. `verify_selection(...)` validates the record and recomputes the decision. Resealing a forged result does not make that result acceptable.

`prepare_experimental_plan(root, inventory, request, spec, output, approved_request_sha256=...)` returns the selection record paired with the existing engine's real preparation result. It delegates source, AST, binding, mapping, recipe, output-ownership, and policy validation to `integrations.lifecycle.plan_implementation`. It writes a private implementation bundle outside the target, but does not apply it, import host modules, run tests, call a provider, or activate treatment. Actual file drift is checked by the existing engine, not inferred from the supplied inventory alone.

The returned selection record must be retained alongside the resulting plan by the caller. This checkpoint does not yet integrate durable selection persistence or resume behavior into the issue #4 repository session. Existing implementation manifests and receipts are not relaxed or replaced.

## Requests and schemas

The request schema is `placement-selection-request.schema.json`. Every field is explicit:

| Field | Meaning |
| --- | --- |
| `schema_version` | `1.0` for this record. |
| `selection_engine_sha256` | Exact selection implementation/schema identity. |
| `mode` | `experimental` or `optimize`. |
| `inventory_sha256` | Digest of the complete supplied inventory. |
| `candidate_id` | One existing candidate for experimentation; null for optimization. |
| `decision_review` | Reviewer, reason, and evidence references for experimentation; null for optimization. |
| `preparation_scope_ref` | Externally supplied preparation-scope reference; not permission by itself. |
| `implementation_spec_sha256` | Exact specification digest when preparing code; null is allowed only before preparation. |
| `constraints` | Existing optimizer constraint fields in optimization mode; null for experimentation. |
| `live_limits` | Explicit cost/call/concurrency bounds or null values; never spending authority. |

The other mirrored schemas are `placement-selection`, `placement-estimates`, `placement-interaction`, `placement-selection-envelope`, and `placement-selection-summary`. The envelope validates structure; nested inventory, request, and specification records are independently validated by their own contracts. New schemas are mirrored under `schemas/` and `jev_integration_evaluator/data/`.

Unknown estimate fields remain null. The selector never substitutes zeroes, inferred savings, synthetic observations, or invented provenance. Known estimates remain conditional on their supplied provenance and the existing optimizer's documented units and assumptions; a supplied estimate is not independently measured benefit.

## Outcomes

| Result | Interpretation |
| --- | --- |
| `experimental_selected` | One source-matched, semantically reviewed candidate was specifically selected for bounded preparation. Recipe support is still checked by the implementation engine. |
| `estimate_based_optimization` | A set was selected under the declared estimate model. This does not establish observed benefit. |
| `insufficient_estimates` | Missing estimates prevented justified optimization; this is not evidence of semantic uselessness. |
| `missing_estimate_provenance` | Numeric inputs exist without the required declared provenance. |
| `no_feasible_positive_set_under_declared_model` | No positive set was returned under the supplied model, bounds, and search method. |
| `selection_review_required` | A semantic review exists, but no external experimental-selection approval was supplied. |
| `semantic_review_required` / `stale_semantic_review` | Review is absent, incomplete, or does not match the candidate's source identity. |
| `semantic_rejection` / `deterministic_rejection` | The selected boundary was rejected. Hard-real-time, deterministic-preferred/mandatory, tier-zero, and `NONE` gates cannot be overridden by either mode. |
| `incomplete_analysis` | The supplied coverage cannot support a negative conclusion. |
| `no_candidates_discovered` | The bounded inventory contains no candidates; this is not proof that arbitrary undiscovered seams are useless. |
| `no_useful_placement_within_reviewed_inventory` | Complete supplied coverage and explicit negative reviews support a negative conclusion only within that reviewed inventory. |

Preparation returns `unsupported_implementation` for the existing engine's `UnsupportedShape` outcome, or `missing_prerequisite` for `MissingBinding`. For example, the current bounded recipe reports an absent supported synchronous binding for an async seam; this checkpoint does not reclassify that validator or advertise async support.

Malformed, stale, inconsistent, over-budget, or unsupported input contracts raise `SelectionError` with a stable, redacted code. The CLI returns these diagnostics without echoing private paths, reviewer text, scope references, provenance text, source, credentials, or host output.

## Resource and interaction bounds

An inventory is limited to 16,000,000 canonical JSON bytes, 2,000 candidates, and 10,000 pairwise interactions. A request is limited to 262,144 bytes and a preparation specification to 2,000,000 bytes. Optimization is limited to 64 reviewed candidates, exact enumeration up to 12, and a beam width of 128 thereafter. The existing optimizer labels heuristic output rather than asserting optimality.

Interactions are limited to explicitly typed pairwise conflicts and conditional utility effects. Unknown dependency/constraint fields and duplicate unordered pairs are rejected, not silently ignored or double-counted. Declared measured interaction effects require provenance; a label and provenance string still do not independently certify a measurement. The separate bounded composite implementation transaction is documented in [composite transactions v1](composite-transactions-v1.md); it does not add composite dependency reasoning to this selector.

## CLI and thin script

The installed module and source-checkout script use the same implementation:

```bash
python -m jev_integration_evaluator.selection < private-selection-envelope.json
python scripts/select_placement.py < private-selection-envelope.json
```

The bounded stdin envelope contains exactly `schema_version`, `inventory`, `request`, and `specification`. For selection-only use, `specification` is null. The CLI emits a metadata-only summary, not the full private evidence record. A valid blocked or unsupported result exits zero; invalid inputs or environmental failures exit two. The structured status, not merely the exit code, determines readiness.

After a trusted caller has independently reviewed and approved the exact request, code preparation can be invoked with explicit paths and the externally retained approval:

```bash
python scripts/select_placement.py \
  --prepare \
  --repo "$TARGET_REPOSITORY" \
  --bundle "$NEW_PRIVATE_BUNDLE" \
  --approve-request "$REVIEWED_SELECTION_SHA256" \
  < "$REVIEWED_ENVELOPE"
```

These are WSL/Linux shell examples. The envelope contains the exact specification when `--prepare` is used. Do not turn an agent-provided command or a hash printed by an earlier invocation into approval automatically. The CLI does not invoke a shell, install dependencies, publish Git changes, or execute a target.

## Offline demonstration and qualification

```bash
python scripts/run_selection_demo.py --out NEW_PRIVATE_DIRECTORY
python scripts/run_selection_demo.py \
  --out DIFFERENT_NEW_PRIVATE_DIRECTORY \
  --verify-synthetic-lifecycle
```

The first command creates its own generated fixture and prepares a real bundle while preserving host bytes. The second explicitly exercises the existing synthetic baseline/apply/modified-verification/status/rollback lifecycle on a different, fresh generated fixture. Both reject an existing output directory and require output outside the checkout. No private target is an input to this demonstration.

The runtime callback in this generated fixture is supplied by the existing synthetic probe. This is not real-bootstrap verification, independently enforced execution isolation, an independently authored host corpus, live provider connectivity, measured application benefit, or production activation.

Targeted tests are:

```bash
python -m pytest -q \
  tests/test_placement_selection.py \
  tests/test_placement_selection_cli.py \
  tests/test_placement_selection_wheel.py \
  tests/test_inputs_optimizer.py
```

The wheel test imports the selector from the installed wheel in a fresh isolated interpreter and drives a generated flat host through the existing synthetic lifecycle. It is installed-evaluator qualification, not installed-package host qualification or the complete release matrix. An isolated Python interpreter is not an operating-system sandbox.

## Remaining delivery work

PRs #18 and #19 already supply discovery, nomination, and the real inventory/semantic-review bridge. Issue #5 still requires a complete source-reviewed no-useful-placement outcome; this checkpoint only qualifies negative conclusions within an explicitly reviewed inventory.

The central repository command and durable session integration, complete source-reviewed negative disposition, agent binding preparation, native isolation, independent corpus, package/method/async expansion, actual runtime bootstrap, composite transactions, executable JS/TS backend, and operational-evidence integration remain in epic #3. No issue is closed by this checkpoint.

Before publication, replay the patch on the exact current main, reconcile concurrent changes without discarding user work, complete release metadata/checksum integration, run the full current-main regressions and required hosted matrix, obtain independent review, create a trusted signed commit, and use the normal PR/check/merge process. A partial reconstructed test checkout is not a substitute for those release gates.
