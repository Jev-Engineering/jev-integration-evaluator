"""Attach exact, source-matched artifacts without turning a receipt into authority."""
from pathlib import Path
from .io import InputError,read_json,file_hash,digest


def link_artifact(scan: dict, candidate_id: str, kind: str, artifact_path: str | Path) -> dict:
    if kind not in ("implementation","test","outcome"): raise InputError("Unsupported traceability kind")
    candidates={c["candidate_id"]:c for c in scan["candidates"]}
    if candidate_id not in candidates: raise InputError("Unknown opportunity")
    candidate=candidates[candidate_id]
    path=Path(artifact_path)
    document=read_json(path)
    if document.get("candidate_id")!=candidate_id: raise InputError("Artifact belongs to a different opportunity")
    source_hash=document.get("source_sha256",document.get("source",{}).get("source_sha256"))
    if source_hash!=candidate["source"]["source_sha256"]: raise InputError("Stale artifact source hash")
    if document.get("experiment_id")!=candidate["recommended_experiment"]["id"]:
        raise InputError("Artifact must identify the exact experiment")
    if kind=="test" and (document.get("status") not in ("passed","failed","timeout","not_run") or not document.get("test_id")):
        raise InputError("Test receipt needs a test ID and explicit execution status")
    if kind=="outcome" and (not isinstance(document.get("result"),dict) or document["result"].get("recommendation") not in ("keep","modify","disable","needs_more_evidence")):
        raise InputError("Outcome receipt must embed an evaluation result with a valid disposition")
    ref={"artifact":path.name,"sha256":file_hash(path),"kind":kind,"source_sha256":source_hash,"experiment_id":document["experiment_id"]}
    evidence_id=candidate_id+":"+kind+":"+ref["sha256"][:12]
    ref["evidence_id"]=evidence_id
    if kind=="outcome": candidate["traceability"]["outcome"]=ref
    else:
        key="tests" if kind=="test" else "implementation"
        if ref not in candidate["traceability"][key]: candidate["traceability"][key].append(ref)
    if not any(x["id"]==evidence_id for x in candidate["evidence"]):
        candidate["evidence"].append({"id":evidence_id,"kind":"artifact_receipt","source":candidate["source"],"artifact":ref})
    # No automatic promotion or deployment: a receipt's claims still require independent review.
    return scan
