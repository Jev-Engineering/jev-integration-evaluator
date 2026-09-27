# Repository roadmap acceptance ledger

The machine-readable [ledger](../roadmap-acceptance-ledger.json) captures the live
GitHub acceptance text for epic #3 and children #4–#15 at the recorded snapshot.
It records issue checkbox state separately from verified evidence. An unchecked
item is open; a checked item still needs source, test, review and merge evidence
before it can be credited in a release audit.

| Issue | Current state | Native open prerequisites | Workstream |
| --- | --- | --- | --- |
| #3 | Open epic | Children | Integration |
| #4 | Open; PR #26 is partial foundation | None | Repository session |
| #5 | Closed; preserve existing outcome | None | Discovery history |
| #6 | Open | #4 | Agent review |
| #7 | Open; four checked boxes, command connection pending | #4 | Selection |
| #8 | Open; PR #27 draft and unqualified | #4 | Native verification |
| #9 | Open | #6, #7, #8 | Independent corpus |
| #10 | Open; ready label corrected | None | Python packages |
| #11 | Open | #6, #10, #8 | Python strategies |
| #12 | Open | #6, #10, #8 | Runtime lifecycle |
| #13 | Open | #4, #6 | Transactions |
| #14 | Open | #6, #8 | JavaScript/TypeScript |
| #15 | Open | #7, #12 | Observed evidence |

The initial audit found a clean local `main` at
`fa44cf7c28fe918f946ab3d4f9856d759f7260ea`, matching `origin/main`.
Draft PR #27 at `c16c71e3f8dd61abc6a196cdce12594e90a00861` has generic
green jobs, no recorded independent review and no privileged native-runner
qualification. The repository session's secure filesystem requires POSIX;
native Windows tests that fail this prerequisite are not acceptance evidence.

Each issue remains open until its requirements have fresh, revision-bound
qualification, independent review, signed publication, normal merge and
post-merge readback. Missing evidence is recorded as `unverified` in the JSON
ledger rather than inferred from issue checkboxes or historical validation.
