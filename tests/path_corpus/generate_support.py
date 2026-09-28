"""Generate source-bound synthetic path support evidence without target imports."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CORPUS = Path(__file__).resolve().parent
NAMES = ("opaque_host", "package_host", "supported_host", "missing_callbacks",
         "deterministic_only", "unsupported_language")
CONNECTED_TEST = "tests/test_path_corpus_connected.py"
CONNECTED_CASES = 14


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate() -> dict:
    rows = []
    for name in NAMES:
        host = CORPUS / name
        expected = json.loads((host / "expected.json").read_text(encoding="utf-8"))
        source = expected["source_sha256"]
        if any(sha(host / rel) != digest for rel, digest in source.items()):
            raise ValueError("Corpus source differs from independent oracle")
        command = [sys.executable, "-m", "jev_integration_evaluator",
                   "repository-run", str(host)]
        done = subprocess.run(command, cwd=ROOT, capture_output=True,
                              text=True, timeout=30, check=True)
        if done.stderr:
            raise ValueError("Public command emitted unexpected stderr")
        result = json.loads(done.stdout)
        rows.append(dict(host=name, source_sha256=source,
                         status=result["status"],
                         discovery_outcome=result["report"]["discovery_outcome"],
                         target_executed=result["target_executed"],
                         target_modified=result["target_modified"],
                         runtime_activation_authorized=result["runtime_activation_authorized"]))
    connected = subprocess.run([sys.executable, "-m", "pytest", "-q", CONNECTED_TEST],
                               cwd=ROOT, capture_output=True, text=True, timeout=180, check=False)
    summary = re.search(r"\b(\d+) passed\b", connected.stdout)
    passed_cases = int(summary.group(1)) if summary else 0
    connected_status = ("passed" if connected.returncode == 0 and
                        passed_cases == CONNECTED_CASES and "skipped" not in connected.stdout else "failed")
    supported_source = json.loads((CORPUS / "supported_host" / "expected.json").read_text(
        encoding="utf-8"))["source_sha256"]
    return dict(schema_version="1.0", evidence_type="synthetic_offline",
                qualification_scope=("public_path_inspection_and_synthetic_connected_fixture"
                                     if connected_status == "passed" else "public_path_inspection_only"),
                python=platform.python_version(), platform=sys.platform,
                architecture=platform.machine(),
                command_sha256={rel: sha(ROOT / rel) for rel in
                                ("jev_integration_evaluator/repository_run.py",
                                 "jev_integration_evaluator/agent_review.py",
                                 "jev_integration_evaluator/integrations/verification.py",
                                 "jev_integration_evaluator/cli.py")},
                oracle_sha256={rel: sha(ROOT / rel) for rel in
                               ("tests/test_path_corpus_oracle.py",
                                "tests/test_path_corpus_connected.py",
                                "tests/path_corpus/generate_support.py")},
                cases=rows,
                connected=dict(test=CONNECTED_TEST, status=connected_status,
                               passed_cases=passed_cases,
                               source_sha256=supported_source,
                               asserted_paths=["discovery_review_plan_baseline_apply_modified",
                                               "external_cli_review_input_and_owned_plan",
                                               "offline_off_shadow_active_once_each",
                                               "baseline_and_apply_interruption_resume",
                                               "dirty_git_conflict_preservation",
                                               "post_apply_conflict_preservation",
                                               "tampered_baseline_receipt_blocks_mutation",
                                               "forged_external_receipt_anchor_blocks_recovery",
                                               "independent_policy_and_duplicate_effect_mutations"],
                               execution_environment="trusted_host_synthetic",
                               provider_connectivity="not_tested", activation_authorized=False),
                unrun=["target_native_runner", "installed_host_lifecycle",
                       "hosted_python_matrix", "javascript_typescript_backend",
                       "live_provider_benefit", "activation"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        raise SystemExit("Output already exists")
    output.write_text(json.dumps(generate(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "written", "cases": len(NAMES),
                      "evidence_type": "synthetic_offline"}))


if __name__ == "__main__":
    main()
