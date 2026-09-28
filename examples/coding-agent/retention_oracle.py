"""Independent raw-memory and later-recall checks for a synthetic fixture."""

from __future__ import annotations

import hashlib
import re


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def raw_postconditions(case, retained, committed, mode, token_budget):
    """Inspect raw readback, not a success-shaped fake-memory return value."""
    originals = {item["id"]: item for item in case["items"]}
    ids = [item["id"] for item in retained]
    unique_known = len(ids) == len(set(ids)) and set(ids) <= set(originals)
    byte_and_provenance_loss = False
    if unique_known:
        for item in retained:
            source = originals[item["id"]]
            if (item != source or digest(item["text"]) != source["byte_sha256"]
                    or len(item["text"].split()) != source["token_count"]):
                byte_and_provenance_loss = True
    else:
        byte_and_provenance_loss = True
    pinned_ids = {pin["id"] for pin in case["pins"]}
    pin_loss = not pinned_ids <= set(ids)
    tokens = sum(item["token_count"] for item in retained)
    over_budget_commit = bool(committed) and tokens > token_budget
    wrong_mode_mutation = mode != "/prune" and retained != case["items"]
    return {
        "pin_loss": pin_loss,
        "byte_or_provenance_loss": byte_and_provenance_loss,
        "over_budget_commit": over_budget_commit,
        "wrong_mode_mutation": wrong_mode_mutation,
        "retained_tokens": tokens,
        "retained_ids": ids,
    }


def reader_projection(question, retained):
    """Construct a new allowlisted object; scorer and chooser objects are absent."""
    if type(question) is not str or not question:
        raise ValueError("reader question missing")
    allowed = ("id", "text", "byte_sha256", "source_kind", "source_ref", "capture_revision")
    return {"question": question, "retained_items": [
        {key: item[key] for key in allowed} for item in retained
    ]}


def read_later(projection):
    if set(projection) != {"question", "retained_items"}:
        raise ValueError("reader projection shape")
    match = re.search(r"(?:authoritative|verified) ([a-z_]+) (?:sources|value)", projection["question"])
    if match is None:
        return {"answer": None, "citation_ids": []}
    field = match.group(1)
    sources = [item for item in projection["retained_items"] if item["text"].startswith(field + " ")]
    if not sources:
        return {"answer": None, "citation_ids": []}
    verified = [item for item in sources if item["source_kind"] == "verified_source"]
    if verified:
        source = verified[-1]
        return {"answer": source["text"].split(" ", 1)[1], "citation_ids": [source["id"]]}
    values = {item["text"].split(" ", 1)[1] for item in sources}
    if len(values) > 1:
        return {"answer": "unresolved", "citation_ids": [item["id"] for item in sources]}
    source = sources[-1]
    return {"answer": source["text"].split(" ", 1)[1], "citation_ids": [source["id"]]}


def score_recall(question, scorer, retained, *, missing_reader=False):
    if not scorer["applicable"]:
        return {"applicable": False, "success": None, "missing": False, "citation_ids": []}
    if missing_reader:
        return {"applicable": True, "success": False, "missing": True, "citation_ids": []}
    projection = reader_projection(question, retained)
    result = read_later(projection)
    original_digests = {item["id"]: item["byte_sha256"] for item in retained}
    required = set(scorer["required_source_ids"])
    citations = set(result["citation_ids"])
    success = (result["answer"] == scorer["expected_answer"] and required <= citations
               and all(original_digests.get(item_id) == digest_value
                       for item_id, digest_value in scorer["required_source_sha256"].items()))
    return {"applicable": True, "success": success, "missing": False,
            "citation_ids": result["citation_ids"]}
