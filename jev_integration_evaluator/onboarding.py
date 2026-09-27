"""Progressive intake which reuses explicit answers and repository facts."""
from __future__ import annotations
from .io import InputError

FIELDS={
    "objective":"What outcome should improve: quality, reliability, model calls, cost, or another measurable objective?",
    "latency_budget_ms":"What is the permitted added latency per task, and is any path hard real-time?",
    "cost_budget_per_task":"What is the maximum additional inference spend per task?",
    "risk_tolerance":"Which errors or actions are unacceptable, and which require explicit approval?",
    "environment":"Is this experimental, staging, or production code?",
    "benchmark_path":"Which existing benchmark or independently labeled task set should be reused?",
    "trace_path":"Are source-versioned runtime traces available? Use null when unavailable.",
    "modification_authority":"Which paths/operations may the agent modify, and who approves code execution/egress?",
}

def onboard(scan: dict, answers: dict | None=None, mode: str="analysis") -> dict:
    answers=answers or {}
    if mode not in ("analysis","implementation"): raise InputError("Invalid onboarding mode")
    unknown=set(answers)-set(FIELDS)-{"mode","depth","repository","branding"}
    if unknown: raise InputError("Unknown onboarding answer fields: "+", ".join(sorted(unknown)))
    needed=[k for k in FIELDS if k not in answers and (k!="modification_authority" or mode=="implementation")]
    return {"repository":scan["repository_name"],"mode":mode,"depth":answers.get("depth",scan["depth"]),
            "observed":{"languages":scan["coverage"]["languages"],"existing_jev_signatures":any(any("typesafe" in str(e).lower() or "system_one" in str(e) for e in n["calls"]) for n in scan["architecture"]["nodes"]),
                        "test_symbols":sum(n["is_test"] for n in scan["architecture"]["nodes"])},
            "answers":answers,"questions":[{"field":k,"question":FIELDS[k]} for k in needed[:5]],
            "remaining_fields":needed[5:],"state":"ready_for_analysis" if not needed else "progressive_intake",
            "safe_defaults":{"mode":"analysis","network":False,"target_test_execution":False,"deployment":False},
            "note":"Analysis may continue with explicitly unknown constraints; unknown budgets block certified optimization and live spend, not local scanning."}
