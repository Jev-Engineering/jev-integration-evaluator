"""Offline decision replay. Never manufacture downstream counterfactual outcomes."""
from __future__ import annotations
from .client import validate_response
from .io import InputError, digest, finite
from .questions import validate_questions


def replay_decisions(events: list[dict], client, model: str="jev-1.13.0", timeout_ms: int=2000, *, max_calls: int=5, max_total_cost: float=0.01,
                     cost_upper_bound_per_call: float | None=None) -> dict:
    if client.is_remote:
        if type(max_calls) is not int or max_calls < 1: raise InputError("Remote replay requires a positive call ceiling")
        finite(max_total_cost,"max total replay cost",0)
        if cost_upper_bound_per_call is None: raise InputError("Remote replay requires an explicit conservative per-call cost upper bound")
        finite(cost_upper_bound_per_call,"per-call cost bound",0)
        if len(events)>max_calls or len(events)*cost_upper_bound_per_call>max_total_cost:
            raise InputError("Remote replay exceeds the authorized call/cost budget; split the input intentionally")
    decisions=[]; ids=set()
    for e in events:
        required=("decision_id","source_location","state","questions","primary_question","baseline_decision")
        if any(k not in e for k in required): raise InputError("Replay requires source, immutable state, candidates/questions, and baseline decision")
        if e["decision_id"] in ids: raise InputError("Duplicate decision ID")
        ids.add(e["decision_id"])
        validate_questions(e["questions"])
        primary=e["primary_question"]
        if primary not in e["questions"] or e["questions"][primary]["type"]!="choice": raise InputError("Replay primary question must be a Choice")
        labels=e["questions"][primary]["criteria"]
        if e["baseline_decision"] not in labels: raise InputError("Baseline action outside candidate set")
        if "ground_truth" in e and e["ground_truth"] not in labels: raise InputError("Ground-truth label outside candidate set")
        row={"decision_id":e["decision_id"],"source_location":e["source_location"],"state_hash":digest(e["state"]),
             "questions_hash":digest(e["questions"]),"baseline_decision":e["baseline_decision"],"evidence_type":e.get("evidence_type","unlabeled")}
        try:
            response=client.evaluate(e["state"],e["questions"],model,timeout_ms)
            validate_response(response,e["questions"],model)
            answer=response["answers"][primary]
            row.update({"jev_decision":answer["choice"],"probabilities":answer["probabilities"],"provider_confidence":answer["confidence"],
                        "agreement":e["baseline_decision"]==answer["choice"],"usage":response["usage"],"status":"evaluated"})
            if "ground_truth" in e:
                row.update({"baseline_correct":e["baseline_decision"]==e["ground_truth"],"jev_correct":answer["choice"]==e["ground_truth"]})
        except Exception as exc:
            row.update({"status":"evaluation_failed","error_class":type(exc).__name__,"jev_decision":None})
        decisions.append(row)
    labeled=[r for r in decisions if "baseline_correct" in r]
    evaluated=[r for r in decisions if r["status"]=="evaluated"]
    return {"decision_count":len(decisions),"evaluated":len(evaluated),"evaluation_failures":len(decisions)-len(evaluated),
            "agreement_rate":sum(r["agreement"] for r in evaluated)/len(evaluated) if evaluated else None,
            "labeled_decisions":len(labeled),
            "decision_accuracy_rescues":sum(not r["baseline_correct"] and r["jev_correct"] for r in labeled),
            "decision_accuracy_regressions":sum(r["baseline_correct"] and not r["jev_correct"] for r in labeled),
            "decision_accuracy_denominator_note":"Only successfully evaluated labeled decisions; report failures separately, do not hide missing outcomes.",
            "downstream_task_success":"not identifiable from decision replay alone",
            "decisions":decisions}
