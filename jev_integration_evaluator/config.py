"""Documented defaults, strict overrides, and no implicit network authorization."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import yaml
from .io import InputError, finite

WEIGHTS = {
    "semantic_uncertainty": 1.6, "decision_boundedness": 1.5,
    "downstream_consequence": 1.6, "decision_frequency": 0.5,
    "cost_of_wrong_decision": 1.2, "recoverability_value": 1.0,
    "observability": 0.5, "deterministic_alternative_quality": -2.4,
    "current_failure_rate": 0.9, "current_llm_dependency": 0.8,
    "latency_sensitivity": -1.2, "cost_sensitivity": -0.7,
    "implementation_complexity": -0.8, "testability": 1.0,
    "expected_reuse": 0.5, "confidence_calibration_value": 0.7,
}
DEFAULT = {
    "mode": "analysis", "depth": "STANDARD",
    "repository": {"root": ".", "exclude": [], "max_files": 20000,
                   "max_file_bytes": 1_000_000, "typescript_ast": True},
    "scoring": WEIGHTS,
    "thresholds": {"strong_candidate": 0.55, "high_leverage": 0.75},
    "constraints": {"max_added_latency_ms": 250.0, "max_cost_per_task": 0.01,
                    "max_calls_per_task": 5.0, "max_complexity": 5.0,
                    "max_risk": 0.5, "required_throughput": 0.0},
    "validation": {"paired_replay": True, "bootstrap_samples": 2000,
                   "bayesian_samples": 5000, "confidence_level": 0.95,
                   "minimum_useful_effect": 0.02, "min_pairs": 30, "seed": 731,
                   "shadow_mode": True},
    "runtime": {"mode": "off", "model": "jev-1.13.0", "timeout_ms": 2000,
                "canary_fraction": 0.05, "max_calls_per_task": 5,
                "max_cost_per_task": 0.01, "circuit_failures": 3,
                "circuit_cooldown_s": 30, "cache_ttl_s": 0,
                "max_cache_entries": 1000, "input_usd_per_million": None,
                "output_usd_per_million": None},
    "branding": {"profile": "CompleteTech provider-starter", "unbranded": False},
}

class UniqueSafeLoader(yaml.SafeLoader):
    pass

def _mapping(loader, node, deep=False):
    result = {}
    for k, v in node.value:
        key = loader.construct_object(k, deep=deep)
        if key in result:
            raise InputError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(v, deep=deep)
    return result
UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)

def _merge(base, changes, path=""):
    if not isinstance(changes, dict):
        raise InputError(f"{path or 'config'} must be a mapping")
    for k, v in changes.items():
        if k not in base:
            raise InputError(f"Unknown configuration key: {path}{k}")
        if isinstance(base[k], dict):
            _merge(base[k], v, path + k + ".")
        else:
            base[k] = v

def load_config(path: str | Path | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULT)
    if path:
        p = Path(path)
        if p.stat().st_size > 1_000_000:
            raise InputError("Configuration exceeds 1 MB")
        data = yaml.load(p.read_text(encoding="utf-8"), Loader=UniqueSafeLoader)
        if data is None:
            data = {}
        if isinstance(data, dict) and "jev_analysis" in data:
            if len(data) != 1:
                raise InputError("Only jev_analysis is allowed at the outer level")
            data = data["jev_analysis"]
        _merge(cfg, data)
    validate_config(cfg)
    return cfg

def validate_config(cfg: dict) -> None:
    if cfg["mode"] not in ("analysis", "implementation") or cfg["depth"] not in ("QUICK", "STANDARD", "RESEARCH"):
        raise InputError("Invalid mode or depth")
    if cfg["runtime"]["mode"] not in ("off", "shadow", "canary", "active"):
        raise InputError("Invalid runtime mode")
    for k, w in cfg["scoring"].items():
        finite(w, "weight " + k)
        if w * WEIGHTS[k] < 0:
            raise InputError(f"Weight {k} may be zero, but its sign cannot reverse")
    if sum(max(0, x) for x in cfg["scoring"].values()) <= 0:
        raise InputError("At least one positive scoring weight is required")
    for k, v in cfg["constraints"].items():
        finite(v, k, 0)
    for k in ("strong_candidate", "high_leverage"):
        finite(cfg["thresholds"][k], k, 0, 1)
    if cfg["thresholds"]["strong_candidate"] > cfg["thresholds"]["high_leverage"]:
        raise InputError("Candidate thresholds are out of order")
    finite(cfg["runtime"]["canary_fraction"], "canary_fraction", 0, 1)
    for k in ("timeout_ms", "max_calls_per_task", "circuit_failures", "max_cache_entries"):
        n = cfg["runtime"][k]
        if type(n) is not int or n <= 0:
            raise InputError(f"{k} must be a positive integer")
    for k in ("max_cost_per_task", "circuit_cooldown_s", "cache_ttl_s"):
        finite(cfg["runtime"][k], k, 0)
    for k in ("input_usd_per_million", "output_usd_per_million"):
        if cfg["runtime"][k] is not None:
            finite(cfg["runtime"][k], k, 0)
    for k in ("bootstrap_samples", "bayesian_samples", "min_pairs", "seed"):
        if type(cfg["validation"][k]) is not int or cfg["validation"][k] < (0 if k == "seed" else 1):
            raise InputError(f"{k} must be a valid integer")
    finite(cfg["validation"]["confidence_level"], "confidence_level", 0.5, 0.999)
    finite(cfg["validation"]["minimum_useful_effect"], "minimum_useful_effect", 0, 1)
    for k in ("max_files", "max_file_bytes"):
        if type(cfg["repository"][k]) is not int or cfg["repository"][k] <= 0:
            raise InputError(f"{k} must be a positive integer")
    if not isinstance(cfg["repository"]["exclude"], list) or not all(isinstance(x, str) for x in cfg["repository"]["exclude"]):
        raise InputError("repository.exclude must be a list of glob strings")
    for section, keys in (("repository", ["typescript_ast"]), ("validation", ["paired_replay", "shadow_mode"]), ("branding", ["unbranded"])):
        for k in keys:
            if type(cfg[section][k]) is not bool:
                raise InputError(f"{section}.{k} must be a boolean")
    if not isinstance(cfg["runtime"]["model"], str) or not cfg["runtime"]["model"]:
        raise InputError("A model ID is required")
