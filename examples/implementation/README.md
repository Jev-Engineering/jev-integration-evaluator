# Source-matched synthetic implementation examples

Each `a`–`m` directory has an **unmodified synthetic target**, a real scanner/review inventory, and a strict `binding.example.json`. These examples contain no final replacement source and require no live key. The generator is `scripts/implementation_fixtures.py`; the end-to-end CLI demonstration is `scripts/run_implementation_demo.py`.

Do not apply an example to a different source by merely changing its hashes. Copy the target into a new workspace, scan/review that actual source and regenerate its binding identities. The demo does this automatically and restores every target before exiting. It distinguishes synthetic changed decisions, actual host-wiring evidence, and the absence of any deployment/benefit claim.

Host callback contracts, supported shapes, permissions and the exact command sequence are documented in `references/executable-integrations.md`. The fixture's runtime callback is intentionally supplied by the separately authorized probe; it is not a production provider bootstrap implementation. Unanchored status remains applied-but-unverified until an independently trusted receipt digest is supplied.
