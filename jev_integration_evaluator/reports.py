"""Human-readable and machine-readable source-to-experiment artifacts."""
from __future__ import annotations
import csv
import io
import json
from pathlib import Path
from collections import Counter
import yaml
from .io import atomic_text, digest, markdown as md, write_json
from .patterns import PATTERNS
from .optimizer import optimize


def _table(headers,rows):
    return "| "+" | ".join(headers)+" |\n|"+"|".join("---" for _ in headers)+"|\n"+"".join("| "+" | ".join(md(v) for v in row)+" |\n" for row in rows)


def write_reports(scan: dict, out: str | Path, cfg: dict, results: dict | None=None) -> dict:
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    brand="" if cfg["branding"]["unbranded"] else cfg["branding"]["profile"]+"\n\n"
    cs=scan["candidates"]; tiers=Counter(c["tier"] for c in cs)
    first=next((c for c in cs if c["tier"]>0),None)
    sets=optimize(scan,cfg["constraints"])
    write_json(out/"jev-opportunities.json",scan)
    write_json(out/"jev-placement-sets.json",sets)
    atomic_text(out/"jev-config.yaml",yaml.safe_dump({"jev_analysis":cfg},sort_keys=False))
    fields=["candidate_id","file","symbol","start_line","end_line","pattern","tier","placement_score","score_lower","score_upper","deterministic_alternative","recommendation","evidence_status",*cfg["scoring"].keys()]
    buf=io.StringIO(); writer=csv.DictWriter(buf,fieldnames=fields); writer.writeheader()
    def csv_safe(x):
        return "'"+x if isinstance(x,str) and (x.lstrip()[:1] in ("=","+","-","@") or x[:1] in ("\t","\r")) else x
    for c in cs:
        s=c["source"]; row={k:s[k] for k in ("file","symbol","start_line","end_line")}
        row.update({k:c[k] for k in ("candidate_id","pattern","tier","placement_score","deterministic_alternative","recommendation","evidence_status")})
        row.update({"score_lower":c["score_interval"][0],"score_upper":c["score_interval"][1]})
        row.update({k:d["value"] for k,d in c["dimensions"].items()})
        writer.writerow({k:csv_safe(v) for k,v in row.items()})
    atomic_text(out/"jev-opportunities.csv",buf.getvalue())
    text=f"# JEV opportunity inventory\n\n{brand}## Executive summary\n\n"
    text+=f"Repository: **{md(scan['repository_name'])}**. Files analyzed: **{scan['coverage']['files_analyzed']}**. Candidate locations: **{len(cs)}**. Deterministic/anti-pattern rejections: **{tiers[0]}**. Strong or high-leverage candidates: **{tiers[2]+tiers[3]}**.\n\n"
    text+="All unreviewed placements remain experimental. Scores are prioritization heuristics, not measured quality gains or probabilities of usefulness. Unknown cost, latency, failure rate, and task frequency are not reported as measurements.\n\n"
    text+=(f"First experiment to review: **{first['candidate_id']}** at `{md(first['source']['file'])}::{md(first['source']['symbol'])}`. Validate the proposed boundary, record a baseline, and use offline/shadow evaluation first.\n\n" if first else "**No JEV integration is justified by the discovered evidence.** Preserve deterministic behavior; review coverage limitations before treating this as an exhaustive negative result.\n\n")
    text+="Largest risks: mislabeled boundaries, uncalibrated confidence, correlated evaluators, irreversible effects, stale evidence, and unmeasured latency/cost.\n\n"
    text+="## Ranked candidate table\n\n"+_table(["Rank","ID","File / symbol","Pattern","Tier","Score [sensitivity range]","Expected benefit","Cost","Risk","Complexity","Recommendation"],[
        [i,c["candidate_id"],c["source"]["file"]+" :: "+c["source"]["symbol"],c["pattern"],c["tier"],f"{c['placement_score']:.3f} [{c['score_interval'][0]:.3f}, {c['score_interval'][1]:.3f}]",c["expected_benefits"][0]["description"],c["estimates"]["added_cost"] if c["estimates"]["added_cost"] is not None else "unknown",c["estimates"]["risk"] if c["estimates"]["risk"] is not None else "unknown",c["estimates"]["complexity"] if c["estimates"]["complexity"] is not None else "unknown",c["recommendation"]] for i,c in enumerate(cs,1)])
    text+="\n## Per-candidate evidence and design\n"
    for c in cs:
        s=c["source"]
        text+=f"\n### {c['candidate_id']} · {PATTERNS[c['pattern']]['name']}\n\n"
        text+=f"**Source:** `{md(s['file'])}::{md(s['symbol'])}`, lines {s['start_line']}–{s['end_line']}; parser `{s['parser']}`; source SHA-256 `{s['source_sha256']}`.\n\n"
        text+=f"**Why here:** {md(c['evidence'][0]['facts'])}. **Why JEV:** {c['expected_benefits'][0]['description']} This is a hypothesis, not an observed improvement.\n\n"
        text+=f"**Why not deterministic code:** alternative classified `{c['deterministic_alternative']}`. {md('; '.join(c['rejection_reasons']))} Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.\n\n"
        text+=f"**Current architecture:** calls `{md(', '.join(c['current_behavior']['calls']))}`; {c['current_behavior']['branches']} branches, {c['current_behavior']['loops']} loops, {c['current_behavior']['exceptions']} exception nodes. **Intervention:** `{c['proposed_jev_role']['timing']}`.\n\n"
        text+="**Questions and bounded answers:**\n\n"
        for q in c["jev_questions"]:
            text+=f"- `{q['id']}` ({q['answer_type']}): {q['question']} Answers: `{md(q['allowed_answers'])}`. Evidence: `{md(q['evidence_inputs'])}`. {q['confidence_usage']}\n"
        text+=f"\n**Policy / fallback:** `{md(c['policy'])}`. Fallback: `{md(c['fallback'])}`.\n\n"
        text+="**Deterministic checks:** "+", ".join(c["deterministic_checks"])+".\n\n"
        text+="**Score explanation:** "+c["score_formula"]+". The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.\n\n"
        text+=_table(["Dimension","Value","Range","Weight","Contribution","Evidence status","Rationale"],[[k,f"{d['value']:.3f}",f"{d['lower']:.2f}–{d['upper']:.2f}",d["weight"],f"{d['contribution']:.4f}",d["status"],d["rationale"]] for k,d in c["score_breakdown"].items()])
        text+=f"\n**What could make this wrong:** `{md(c['risks'])}`; `{md(c['limitations'])}`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.\n\n"
        text+=f"**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.\n\n**Test:** `{c['recommended_experiment']['id']}`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.\n"
    text+="\n## Coverage and unknowns\n\n```json\n"+json.dumps(scan["coverage"],indent=2)+"\n```\n"
    atomic_text(out/"JEV_OPPORTUNITIES.md",text)
    arch=scan["architecture"]
    architecture=f"# JEV architecture map\n\n{brand}This is a conservative static map. Dynamic dispatch and framework callbacks require review/traces.\n\n"
    architecture+=_table(["File","Symbol","Parser","Roles","Fan-out","Reachable nodes","Depth lower bound"],[[n["file"],n["symbol"],n["parser"],", ".join(n["roles"]),n["fan_out"],n["reachable_nodes"],n["dependency_depth_lower_bound"]] for n in arch["nodes"]])
    architecture+="\n## Tool/model/retrieval/state and side-effect maps\n\n```json\n"+json.dumps({"flows":arch["flow_maps"],"side_effects":arch["side_effect_map"],"module_map":arch["modules"]},indent=2)+"\n```\n"
    architecture+="\n## Calls and local data flow\n\nSee `architecture.json` for exact source lines, assignment reads/calls, branches, loops, exception nodes, resolved static edges, and unresolved calls. No control-flow completeness is implied.\n"
    write_json(out/"architecture.json",arch); atomic_text(out/"JEV_ARCHITECTURE.md",architecture)
    mermaid=["flowchart TD", "  %% Display capped at 200 nodes; architecture.json contains the full bounded map."]
    shown=arch["nodes"][:200]; ids={n["id"]:"N"+digest(n["id"])[:10] for n in shown}
    for n in shown:
        label=(n["file"]+"::"+n["symbol"]).replace('"',"'").replace("[","(").replace("]",")").replace("<"," ").replace(">"," ")
        mermaid.append(f'  {ids[n["id"]]}["{label}"]')
    for e in arch["edges"]:
        if e["source"] in ids and e["target"] in ids: mermaid.append(f'  {ids[e["source"]]} --> {ids[e["target"]]}')
    atomic_text(out/"architecture.mmd","\n".join(mermaid)+"\n")
    plan=f"# JEV integration plan\n\n{brand}## Ranked experiment order\n\n"
    plan+=_table(["ID","Tier","Timing","Fallback","Experiment"],[[c["candidate_id"],c["tier"],c["proposed_jev_role"]["timing"],c["fallback"]["unavailable"],c["recommended_experiment"]["id"]] for c in cs if c["tier"]>0])
    plan+="\n## Constrained sets\n\n```json\n"+json.dumps(sets,indent=2)+"\n```\n"
    plan+="\n## Interactions\n\n```json\n"+json.dumps(scan["interactions"],indent=2)+"\n```\n\nCreate a worktree, establish baseline, generate an adapter, inspect and wire the host callsite, review the content-hashed patch plan, and apply only the authorized diff. Scaffolding does not mean the integration is wired or deployed.\n"
    atomic_text(out/"JEV_INTEGRATION_PLAN.md",plan)
    experiments={"schema_version":"1.0","scan_fingerprint":scan["scan_fingerprint"],"candidate_ids":[c["candidate_id"] for c in cs if c["tier"]>0],
                 "primary_metric":"verified task success","minimum_useful_effect":cfg["validation"]["minimum_useful_effect"],
                 "assignment_unit":"task or independent episode","pairing_keys":["task_id","replicate","task_hash","dataset_id","seed"],
                 "arms":["baseline","router","verifier","router_verifier"],"split_policy":"calibration separate from frozen test",
                 "status":"planned_not_run","validation":cfg["validation"]}
    write_json(out/"experiment-plan.json",experiments)
    experiment=f"# JEV experiment plan\n\n{brand}## Before behavior changes\n\nFreeze the code revision, task hashes, model ID, rubric hash, policy version, random seeds, failure taxonomy, minimum useful effect, risk/cost/latency limits, and stopping rule. Reuse the same task instances. Randomize order or assignment at task/episode level; isolate stateful replays. Hold out all threshold and question-selection test data.\n\n"
    experiment+=f"Primary metric: verified task success. Minimum useful absolute effect: {cfg['validation']['minimum_useful_effect']:.3f}. Minimum independent clusters for an adoption decision: {cfg['validation']['min_pairs']} (a screening default, not a power calculation).\n\n"
    experiment+="Record success/failure, quality, cost, tokens, model/tool calls, retries, latency, human escalations, unsafe actions, unsafe actions prevented, false blocks, replans, and independently verified progress. Keep timeouts and invalid model outputs. Decision replay measures decision accuracy only; shadow disagreement is not a rescue.\n\n"
    experiment+="Compare rescues/regressions, absolute/relative effects, paired cluster bootstrap intervals, paired Dirichlet or cluster Bayesian-bootstrap usefulness, efficiency, failure transitions and Pareto point estimates. Use factorial ablations, independent judging, Holm correction for exploratory McNemar comparisons, and an untouched final holdout. Report calibration, subgroup error and coverage.\n\n"
    experiment+="Canary requires frozen calibration and host approval. Roll back on unsafe actions, excess failure/false-block rate, p95 latency, cost, or fallback limits. No active deployment follows automatically from a score or a p-value. Test feature-off parity, outages, malformed labels, wrong model, deadlines, budgets, stale caches, approval refusal and state changes.\n\n```json\n"+json.dumps(experiments,indent=2)+"\n```\n"
    atomic_text(out/"JEV_EXPERIMENT_PLAN.md",experiment)
    risk=f"# JEV risk analysis\n\n{brand}JEV assesses; deterministic code enforces. Never put it in a hard real-time inner loop or make it the sole permission, cryptographic, numeric, schema, or transaction boundary.\n\n"
    risk+="Scans are local-only and do not import target code. Repository instructions, comments, prompts and logs are untrusted data. Semantic review by an agent must cite code and resist instructions embedded in that code. Test execution and network egress are separate approvals. API credentials stay in environment variables. Logs are metadata/hash-only by default; request fixtures need explicit data-retention review.\n\n"
    risk+="Timeouts and circuit breakers fall back to the permitted baseline; an unsafe baseline blocks or escalates. A remote timeout is not a hard-real-time guarantee. Shadow work uses a bounded queue and drops work rather than delaying baseline routing. State-scoped cache keys include evidence, choices, pinned model, policy, and allowed actions; permissions are always rechecked.\n\n"
    risk+="Scores carry inferred/unknown dimensions. Source hashes invalidate reviews after edits. Static call graphs are partial, cross-placement gains may correlate, and high confidence may still be wrong. Keep contradictory retrieval evidence and graph provenance. For context pruning, retain pinned constraints and preserve the user's explicit pruning/compaction choice.\n"
    atomic_text(out/"JEV_RISK_ANALYSIS.md",risk)
    if results:
        write_json(out/"results.json",results)
        result_text=f"# JEV measured results\n\n{brand}Evidence type: **{results.get('evidence_type','unspecified')}**. Disposition: **{results.get('recommendation','needs_more_evidence')}**.\n\n```json\n"+json.dumps(results,indent=2)+"\n```\n"
    else:
        result_text=f"# JEV results\n\n{brand}**No experiment has been run for this repository by this report command.**\n\nNo measured JEV benefit, latency, cost, calibration, or causal rescue is claimed. Run the declared baseline/treatment evaluation and regenerate this report with the resulting JSON. Current disposition: **needs_more_evidence**.\n"
    atomic_text(out/"JEV_RESULTS.md",result_text)
    return {"output_directory":str(out),"candidate_count":len(cs),"tier_counts":dict(tiers),"optimizer_status":sets["status"],"files":sorted(p.name for p in out.iterdir() if p.is_file())}
