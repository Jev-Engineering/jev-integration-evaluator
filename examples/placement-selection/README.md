# Synthetic, source-linked placement-selection examples

These records were generated from `host/opaque.py` against the recovered
`1.3.0.dev8` analysis/review code and the integrated repository-scope component.
They do not execute the host, implement its callbacks, establish connectivity,
measure benefit, authenticate a reviewer, or authorize activation.

`semantic-review.json`, `context.json`, `selection-review.json` and
`selection.json` show a positive **synthetic** experimental-selection scenario
with unknown measurements and spending bounds. `negative-semantic-review.json`,
`scope-review.json` and `negative-context.json` show a separate complete negative
**synthetic** judgment covering the whole enumerated source and every seam.
The two scenarios are alternatives: combining the positive semantic opinion
with the negative whole-scope judgment is deliberately rejected as conflicting.

The file and AST anchors match the included synthetic source. The root, parser,
engine, policy and report identities bind the original generation directory;
these copied JSON records cannot be resumed or used as approval after relocation.
Recreate fresh examples with the trusted demo script in a new private directory
outside the checkout. Real reviews and independently retained identity anchors
must be supplied for real repository work. The reviewer labels here identify
fixture authorship only and are not an independent qualification corpus.
