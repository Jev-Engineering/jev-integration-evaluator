"""Generate source-bound synthetic path support evidence without target imports."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CORPUS = Path(__file__).resolve().parent
NAMES = ("opaque_host", "package_host", "missing_callbacks",
         "deterministic_only", "unsupported_language")


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
    return dict(schema_version="1.0", evidence_type="synthetic_offline",
                qualification_scope="public_path_inspection_only",
                python=platform.python_version(), platform=sys.platform,
                architecture=platform.machine(),
                command_sha256={rel: sha(ROOT / rel) for rel in
                                ("jev_integration_evaluator/repository_run.py",
                                 "jev_integration_evaluator/cli.py")},
                oracle_sha256={rel: sha(ROOT / rel) for rel in
                               ("tests/test_path_corpus_oracle.py",
                                "tests/path_corpus/generate_support.py")},
                cases=rows,
                unrun=["connected_reviewed_spec_preparation", "target_native_runner",
                       "modified_host_verification", "interrupted_apply_resume",
                       "forged_external_receipt_rejection", "dirty_tree_guard",
                       "conflicting_edit_transaction", "installed_host_lifecycle",
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
