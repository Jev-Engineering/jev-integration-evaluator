"""Reproducible analysis identity and conservative, read-only snapshot comparison."""
from __future__ import annotations

import copy
from collections import Counter, defaultdict, deque
from .io import InputError, digest


def analysis_identity(files: list[dict], configs: list[dict], cfg: dict, coverage: dict) -> dict:
    """Hash source, configuration evidence, parser coverage and effective analysis settings.

    Absolute checkout and output paths are excluded from the content identity. File bytes
    are NOT cached here: every scan still reads current files and parses them afresh.
    """
    from . import __version__
    settings = copy.deepcopy(cfg)
    settings["repository"].pop("root", None)
    settings.pop("branding", None)
    return {
        "identity_version": "1.1",
        "analyzer_version": __version__,
        "source_digest": digest(sorted((f["file"], f["sha256"]) for f in files)),
        "configuration_digest": digest(sorted((f["file"], f["sha256"]) for f in configs)),
        "settings_digest": digest(settings),
        "coverage_digest": digest(coverage),
        "parser_digest": digest(sorted((f["file"], f["parser"]) for f in files)),
    }


def _index(scan: dict) -> dict[str, dict]:
    result = {}
    for c in scan.get("candidates", []):
        key = c["candidate_id"]
        if key in result:
            raise InputError("Duplicate candidate identity in snapshot")
        result[key] = c
    return result


def _files(scan: dict) -> dict[str, str]:
    return {f["file"]: f["sha256"] for f in scan.get("files", [])}


def _coverage_complete(scan: dict) -> bool:
    c = scan.get("coverage", {})
    return (c.get("truncated") is False and not c.get("ignored")
            and not c.get("warnings") and not c.get("parser_counts", {}).get("lexical_review_only"))


def compare_snapshots(before: dict, after: dict, *, allow_repository_mismatch: bool = False) -> dict:
    """Never inherit approvals, measurements or dispositions from an older scan.

    Reverse static dependencies flag possible impact, NOT proof of semantic change.
    Dynamic/unresolved calls always require human review of the map's limitations.
    """
    names_match = before.get("repository_name") == after.get("repository_name")
    if not names_match and not allow_repository_mismatch:
        raise InputError("Repository names differ; explicitly authorize this snapshot comparison")
    old, new = _index(before), _index(after)
    bf, af = _files(before), _files(after)
    modified = sorted(p for p in bf.keys() & af.keys() if bf[p] != af[p])
    added = sorted(af.keys() - bf.keys())
    absent = sorted(bf.keys() - af.keys())
    bcfg = {f["file"]: f["sha256"] for f in before.get("configuration_evidence", [])}
    acfg = {f["file"]: f["sha256"] for f in after.get("configuration_evidence", [])}
    config_changed = bcfg != acfg
    bi, ai = before.get("analysis_identity"), after.get("analysis_identity")
    legacy = not bi or not ai
    settings_changed = legacy or bi.get("settings_digest") != ai.get("settings_digest")
    parser_changed = legacy or bi.get("analyzer_version") != ai.get("analyzer_version")
    coverage_comparable = (not legacy and not settings_changed and not parser_changed
                           and _coverage_complete(before) and _coverage_complete(after))
    # Build a union of both static call maps so removed edges still invalidate callers.
    reverse = defaultdict(set)
    for scan in (before, after):
        for edge in scan.get("architecture", {}).get("edges", []):
            reverse[edge["target"]].add(edge["source"])
    impacted = set()
    for scan in (before, after):
        for n in scan.get("architecture", {}).get("nodes", []):
            if n["file"] in set(modified + absent + added):
                impacted.add(n["id"])
    queue = deque(sorted(impacted))
    while queue:
        for caller in reverse[queue.popleft()]:
            if caller not in impacted:
                impacted.add(caller)
                queue.append(caller)
    rows = []
    for cid in sorted(old.keys() | new.keys()):
        b, a = old.get(cid), new.get(cid)
        reasons = []
        if b is None:
            state = "new"
            reasons.append("new_candidate_requires_review")
        elif a is None:
            state = "removed" if coverage_comparable else "not_observed"
            reasons.append("absent_in_new_snapshot" if coverage_comparable else "absence_not_proven_with_partial_or_changed_coverage")
        else:
            bs, ass = b["source"], a["source"]
            if (bs["file"], bs["symbol"], b["pattern"]) != (ass["file"], ass["symbol"], a["pattern"]):
                raise InputError("Candidate ID reused for a different source boundary")
            state = "changed" if bs["source_sha256"] != ass["source_sha256"] else "unchanged"
            if state == "changed":
                reasons.append("source_body_changed")
            elif (bs["start_line"], bs["end_line"]) != (ass["start_line"], ass["end_line"]):
                state = "line_shift_only"
            if bs.get("file_sha256") != ass.get("file_sha256"):
                reasons.append("surrounding_file_context_changed")
            if ass["file"] + "::" + ass["symbol"] in impacted:
                reasons.append("static_dependency_or_file_may_have_changed")
            if config_changed:
                reasons.append("repository_configuration_changed")
            if settings_changed:
                reasons.append("analysis_settings_changed_or_legacy")
            if parser_changed:
                reasons.append("analyzer_changed_or_legacy")
            if bs.get("parser") != ass.get("parser"):
                reasons.append("source_parser_changed")
        source = (a or b)["source"]
        rows.append({
            "candidate_id": cid, "change": state,
            "file": source["file"], "symbol": source["symbol"],
            "prior_source_sha256": b["source"]["source_sha256"] if b else None,
            "current_source_sha256": a["source"]["source_sha256"] if a else None,
            "requires_review": bool(reasons), "reasons": reasons,
            "prior_evidence_reusable_automatically": False,
            "score_delta": round(a["placement_score"] - b["placement_score"], 8) if a and b else None,
        })
    # Unique exact-body matches are suggestions only; renaming may change callers/policy.
    moves = []
    for removed in sorted(old.keys() - new.keys()):
        b = old[removed]
        matches = [a for cid, a in new.items() if cid not in old and a["pattern"] == b["pattern"]
                   and a["source"]["source_sha256"] == b["source"]["source_sha256"]]
        if len(matches) == 1:
            moves.append({"previous_id": removed, "possible_new_id": matches[0]["candidate_id"],
                          "status": "exact_body_match_requires_review_not_identity_transfer"})
    result = {
        "schema_version": "1.1", "before_fingerprint": before.get("scan_fingerprint"),
        "after_fingerprint": after.get("scan_fingerprint"), "repository_names_match": names_match,
        "legacy_identity": legacy, "coverage_comparable_for_absence": coverage_comparable,
        "configuration_changed": config_changed, "settings_changed": settings_changed,
        "files": {"modified": modified, "added": added, "no_longer_observed": absent},
        "counts": dict(Counter(r["change"] for r in rows)), "candidates": rows,
        "possible_moves": moves, "automatically_carried_approvals": 0,
        "limitations": ["Every new scan starts with fresh source evidence; no stale review is copied.",
                        "Static impact is conservative and cannot resolve all dynamic callers.",
                        "A matching repository name is not an authenticated repository identity.",
                        "No parser cache or target-code execution is used."],
    }
    result["report_digest"] = digest(result)
    return result


def render_change_report(report: dict) -> str:
    """Render only structured diff metadata; never execute or interpolate source instructions."""
    import html
    def cell(value):
        return html.escape(str(value)).replace('|', r'\|').replace('`', "'").replace('\n', ' ')
    lines = ['# JEV snapshot change review', '',
             '**No prior approvals, measurements, or deployment decisions were carried forward.**', '',
             f"Configuration changed: **{report['configuration_changed']}**. Analysis settings changed: **{report['settings_changed']}**.",
             f"Coverage sufficient to interpret absence as removal: **{report['coverage_comparable_for_absence']}**.", '',
             '| Candidate | Source | Change | Requires review | Reasons |',
             '|---|---|---|---|---|']
    for row in report['candidates']:
        lines.append('| ' + ' | '.join(cell(v) for v in (row['candidate_id'], row['file'] + '::' + row['symbol'],
                     row['change'], row['requires_review'], '; '.join(row['reasons']) or 'No detected change')) + ' |')
    lines += ['', '## Interpretation', '',
              'A matching body or candidate ID is not permission to reuse old measurements. Review source, surrounding configuration and affected callers before a new experiment.', '',
              'This is a comparison of full fresh scans, not incremental parsing. Missing results under partial coverage remain “not observed,” not proven removals.', '',
              'Report digest: `' + report['report_digest'] + '`.', '']
    return '\n'.join(lines)
