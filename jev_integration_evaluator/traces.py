"""Source-correlated trace analysis and hash-chained metadata logs."""
from __future__ import annotations
import math
import os
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from .io import InputError, canonical, digest, finite, loads, read_jsonl, redact


def correlate_traces(scan: dict, events: list[dict], cfg: dict) -> dict:
    from .scoring import score_candidate
    if events and "event_hash" in events[0]:
        verify_log(events)
        events=[{**row["event"],"task_id":row["event"].get("task_id_hash"),
                 "tokens":0 if row["event"].get("cache_hit",False) else sum(row["event"].get("usage",{}).get(k,0) for k in ("input_tokens","output_tokens")),
                 "model_calls":int(row["event"].get("type")=="assessment" and not row["event"].get("cache_hit",False))}
                for row in events]
    index = defaultdict(list)
    ignored = Counter()
    for e in events:
        if e.get("type") in ("shadow_comparison","assessment_error"):
            ignored["comparison/error metadata is not a completed decision observation"]+=1
            continue
        src = e.get("source_location", {})
        if not all(src.get(k) for k in ("file", "symbol", "source_sha256")):
            ignored["missing exact source identity"] += 1; continue
        for field in ("latency_ms", "model_calls", "tokens", "retries"):
            if field in e: finite(e[field], "trace " + field, 0)
        if "success" in e and e["success"] is not None and type(e["success"]) is not bool: raise InputError("Trace success must be boolean/null")
        index[(src["file"], src["symbol"], src["source_sha256"])].append(e)
    matched_keys = set()
    for c in scan["candidates"]:
        s = c["source"]; key = (s["file"], s["symbol"], s["source_sha256"])
        es = index.get(key, [])
        if not es: continue
        matched_keys.add(key)
        types={x.get("evidence_type","observed") for x in es}
        if not types <= {"observed","synthetic"} or len(types)!=1:
            raise InputError("Source trace cohort mixes evidence types; stratify synthetic and observed events")
        evidence_type=next(iter(types))
        outcomes = [x["success"] for x in es if type(x.get("success")) is bool]
        latencies = [x["latency_ms"] for x in es if "latency_ms" in x]
        states = [x["state_hash"] for x in es if x.get("state_hash")]
        task_ids = {x["task_id"] for x in es if x.get("task_id")}
        counts_per_task = len(es)/len(task_ids) if task_ids else None
        c["runtime_evidence"] = {"evidence_type":evidence_type,"matched_events": len(es), "tasks": len(task_ids), "calls_per_task": counts_per_task,
                                  "failure_rate": 1-mean(outcomes) if outcomes else None,
                                  "latency_ms_mean": mean(latencies) if latencies else None,
                                  "repeated_state_events": len(states)-len(set(states)),
                                  "branches": dict(Counter(str(x["branch"]) for x in es if "branch" in x)),
                                  "model_calls": sum(x.get("model_calls", 0) for x in es),
                                  "tokens": sum(x.get("tokens", 0) for x in es),
                                  "retries": sum(x.get("retries", 0) for x in es),
                                  "causality": "observational; correlation with downstream failure is not causal attribution"}
        for field, value in (("current_failure_rate", c["runtime_evidence"]["failure_rate"]), ("decision_frequency", min(1, math.log1p(counts_per_task)/math.log(101)) if counts_per_task is not None else None)):
            if value is not None:
                c["dimensions"][field] = {"value": value, "lower": max(0, value-0.15), "upper": min(1, value+0.15),
                                          "status": "observed" if evidence_type=="observed" else "inferred", "rationale": "Matched source-hash trace aggregate ("+evidence_type+"); interval is a scoring sensitivity range, not a confidence interval",
                                          "evidence_refs": [c["candidate_id"]+":trace"]}
        c["evidence"].append({"id": c["candidate_id"]+":trace", "kind": "runtime_trace", "source": s, "events_digest": digest(es), "count": len(es)})
        score_candidate(c, cfg)
    ignored["source hash/file/symbol not in this scan"] += sum(len(es) for k, es in index.items() if k not in matched_keys)
    scan["trace_correlation"] = {"events": len(events), "matched_source_keys": len(matched_keys), "ignored": dict(ignored)}
    return scan


class AuditLog:
    """Single-process/thread-safe append-only hash chain. Not tamper-proof or multi-process safe.

    Store one file per worker. Hashes detect modifications with an externally retained
    final digest. A trusted service must supply stronger provenance for adversarial use.
    """
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.is_symlink(): raise InputError("Log path cannot be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.previous = "0"*64; self.sequence = 0
        if self.path.exists():
            rows = read_jsonl(self.path)
            verify_log(rows)
            if rows: self.previous = rows[-1]["event_hash"]; self.sequence = rows[-1]["sequence"]

    def append(self, event: dict) -> dict:
        with self.lock:
            row = {"sequence": self.sequence+1, "timestamp_unix": time.time(), "monotonic_ns": time.monotonic_ns(),
                   "previous_hash": self.previous, "event": redact(event)}
            row["event_hash"] = digest(row)
            # O_NOFOLLOW where supported, mode 0600; never export credentials/raw evidence by default.
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags, 0o600)
            try:
                with os.fdopen(fd, "ab") as f:
                    f.write(canonical(row)+b"\n"); f.flush(); os.fsync(f.fileno())
            except Exception:
                raise
            self.sequence = row["sequence"]; self.previous = row["event_hash"]
            return row


def verify_log(rows: list[dict], *, expected_final_hash: str | None = None, expected_events: int | None = None) -> dict:
    if expected_events is not None and (type(expected_events) is not int or expected_events < 0):
        raise InputError("Expected log length must be a nonnegative integer")
    if expected_final_hash is not None and (not isinstance(expected_final_hash,str) or len(expected_final_hash)!=64 or any(x not in "0123456789abcdef" for x in expected_final_hash)):
        raise InputError("Expected log head must be a lowercase SHA-256 digest")
    prev = "0"*64
    for i, row in enumerate(rows, 1):
        body = {k: v for k, v in row.items() if k != "event_hash"}
        if row.get("sequence") != i or row.get("previous_hash") != prev or row.get("event_hash") != digest(body):
            raise InputError(f"Broken audit chain at event {i}")
        prev = row["event_hash"]
    if expected_events is not None and len(rows)!=expected_events:
        raise InputError("Audit log length differs from externally retained checkpoint")
    if expected_final_hash is not None and prev!=expected_final_hash:
        raise InputError("Audit log head differs from externally retained checkpoint")
    return {"events": len(rows), "final_hash": prev, "integrity": "valid",
            "external_checkpoint_verified": expected_final_hash is not None,
            "truncation_checked": expected_events is not None or expected_final_hash is not None,
            "authenticity": "depends on trust in the retained checkpoint; hashes alone are not signatures"}


def cache_analysis(events: list[dict]) -> dict:
    rows = [e.get("event", e) for e in events]
    eligible = [e for e in rows if "cache_hit" in e]
    hits = sum(bool(e["cache_hit"]) for e in eligible)
    verified = [e for e in eligible if e.get("cache_hit") and "cache_stale" in e]
    return {"cache_events": len(eligible), "hits": hits, "hit_rate": hits/len(eligible) if eligible else None,
            "latency_saved_ms": sum(e.get("estimated_latency_saved_ms", 0) for e in eligible if e["cache_hit"]),
            "cost_saved": sum(e.get("estimated_cost_saved", 0) for e in eligible if e["cache_hit"]),
            "savings_status": "estimate based on previous miss, not a fresh measured counterfactual",
            "validated_cache_hits": len(verified), "stale_decision_rate": sum(bool(e["cache_stale"]) for e in verified)/len(verified) if verified else None}
