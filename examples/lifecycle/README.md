# Synthetic lifecycle example

Run `python scripts/run_v11_demo.py --out ../jev-v11-demo` from the skill root. The runner generates all current-contract inputs, frozen manifests, exact ordered fixtures and reports in a new or empty output directory. It refuses a nonempty directory.

All generated model observations and task outcomes are explicitly synthetic. The examples are generated from code so question-order hashes, study identities and linked schema versions stay internally consistent. No API key or network access is needed. A synthetic holdout passing its numerical bounds still returns activation-enforcement exit code 3; the runner asserts that outcome.

Read `references/lifecycle-and-evidence.md` before substituting observed records. Do not use the generated synthetic run/holdout files to approve a production integration.
