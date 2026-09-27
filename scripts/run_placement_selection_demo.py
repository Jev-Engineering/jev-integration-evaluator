"""Create source-linked synthetic selection examples in a fresh private directory.

This does not execute the synthetic host, plan an implementation, call a provider,
or authenticate review/mutation authority. It is not the independent host corpus.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import nomination_inventory as bridge
from jev_integration_evaluator import placement_selection as selection
from jev_integration_evaluator.config import DEFAULT

HOST = '''def b(x):
    return x["operation"](x)

def q(x):
    return b(x)

raise RuntimeError("This synthetic host must not be imported by preparation")
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    parent = args.out.parent.resolve(strict=True)
    if parent == ROOT or ROOT in parent.parents:
        raise ValueError("Demo outputs must be outside the checkout")
    out = parent / args.out.name
    _, parent_fd = cap._open_directory(parent)
    try:
        os.mkdir(out.name, mode=0o700, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    host = out / "host"
    host.mkdir(mode=0o700)
    (host / "opaque.py").write_text(HOST, encoding="utf-8")
    cfg = copy.deepcopy(DEFAULT)
    cfg["repository"]["typescript_ast"] = False
    report = bridge.discover_repository_capabilities(host, cfg)
    seam = next(s for s in report["seams"] if s["source"]["qualified_symbol"] == "q")
    anchor = seam["source"]
    nomination = {"schema_version": "1.0", "discovery_version": cap.VERSION,
                  "report_sha256": report["report_sha256"], "seam_id": seam["seam_id"],
                  "source": anchor, "pattern": "C", "proposer": "synthetic-demo-author",
                  "rationale": "Synthetic finite-choice nomination; no observed need or authority is asserted.",
                  "evidence": [{k: anchor[k] for k in ("file", "file_sha256", "start_line", "end_line")}]}
    prepared = bridge.prepare_nominated_inventory(host, report, [nomination], cfg)
    candidate = prepared["inventory"]["candidates"][0]
    cid = candidate["candidate_id"]
    semantic = {"schema_version": "1.0", "prepared_sha256": prepared["prepared_sha256"],
                "reviews": {cid: {"source_sha256": candidate["source"]["source_sha256"],
                    "reviewer": "synthetic-demo-reviewer", "reason": "Positive fixture judgment for testing selection only.", "approved": True}}}
    context = selection.prepare_placement_context(host, report, prepared, semantic, cfg)
    requested = {"schema_version": "1.0", "contract": selection.SELECTION_REVIEW,
                 "context_sha256": context["context_sha256"], "candidate_ids": [cid],
                 "reviewer": "synthetic-demo-reviewer", "reason": "Prepare an experimental selection, not an implementation or activation.",
                 "approved": True, "mode": "experimental", "resource_bounds": {
                     "max_calls_total": None, "max_cost_total_usd": None, "deadline_seconds": None}}
    selected = selection.select_experimental_placements(host, report, prepared, semantic, requested, cfg)
    checked = selection.revalidate_experimental_selection(host, report, prepared, semantic, requested, selected, cfg,
                                                          expected_selection_sha256=selected["selection_sha256"])
    assert checked == selected
    negative = copy.deepcopy(semantic)
    negative["reviews"][cid].update({"approved": False, "reason": "Alternative negative fixture judgment; it is not measured benefit evidence."})
    scope = {"schema_version": "1.0", "contract": selection.SCOPE_REVIEW,
             "report_sha256": report["report_sha256"], "prepared_sha256": prepared["prepared_sha256"],
             "reviewer": "synthetic-demo-reviewer", "reason": "Separate complete negative fixture review of enumerated files and seams.",
             "pattern_scope": selection.PATTERN_SCOPE, "snapshot_scope": report["snapshot_scope"],
             "files": [{"file": f["file"], "file_sha256": f["sha256"], "line_count": f["line_count"],
                        "coverage": "entire_file", "disposition": "no_useful_placement",
                        "reason": "Synthetic whole-file A-M review; no general absence proof."} for f in report["files"]],
             "seams": [{"seam_id": s["seam_id"], "source": s["source"], "disposition": "no_useful_placement",
                        "reason": "Synthetic source-matched negative judgment for every enumerated seam."} for s in report["seams"]]}
    negative_context = selection.prepare_placement_context(host, report, prepared, negative, cfg, scope_review=scope)
    assert negative_context["outcome"] == "no_useful_placement"
    assert (host / "opaque.py").read_text() == HOST
    for name, data in {"config.json": cfg, "report.json": report, "nomination.json": nomination,
                       "prepared.json": prepared, "semantic-review.json": semantic,
                       "context.json": context, "selection-review.json": requested,
                       "selection.json": selected, "negative-semantic-review.json": negative,
                       "scope-review.json": scope, "negative-context.json": negative_context}.items():
        cap._write_out(out / name, host, data)
    summary = {"synthetic": True, "host_executed": False, "target_modified": False,
               "provider_connectivity": "not_tested", "benefit_supported": False,
               "activation_authorized": False, "independent_corpus": False,
               "selection_status": selected["status"], "negative_scope_outcome": negative_context["outcome"],
               "selected_count": selected["selected_count"], "unknown_estimates_preserved":
                   all(v is None for v in selected["placements"][0]["estimates"].values()),
               "source_and_selection_revalidated": checked == selected}
    cap._write_out(out / "summary.json", host, summary)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
