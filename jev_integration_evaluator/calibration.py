"""Probability calibration is separate from provider confidence diagnostics."""
from __future__ import annotations
import math
from collections import defaultdict
from .io import InputError, finite


def calibration(rows: list[dict], bins: int = 10) -> dict:
    if type(bins) is not int or not 2 <= bins <= 100: raise InputError("bins must be 2..100")
    if not rows: raise InputError("Calibration needs labeled held-out observations")
    for field in ("kind", "split", "model_id", "policy_version", "rubric_hash", "subgroup"):
        values = {str(row.get(field, "noul" if field == "kind" else "unspecified")) for row in rows}
        if len(values) > 1: raise InputError("Mixed calibration " + field + "; stratify before analysis")
    observations = []; multiclass_scores = []; provider_confidence = []
    for row in rows:
        kind = row.get("kind", "noul")
        if row.get("split") not in ("calibration", "test"):
            raise InputError("Calibration records must identify a calibration/test split")
        if kind == "noul":
            p = finite(row["probability_yes"], "P(yes)", 0, 1)
            y = row["label"]
            if type(y) is not bool: raise InputError("Noul ground truth must be boolean")
            observations.append((p,float(y)))
        elif kind == "choice":
            probs = row["probabilities"]; truth = row["label"]
            if truth not in probs or len(probs)<2: raise InputError("Ground-truth choice must be in the candidate set")
            for v in probs.values(): finite(v,"class probability",0,1)
            if abs(sum(probs.values())-1)>1e-5: raise InputError("Class probabilities must sum to one")
            choice = row.get("choice", max(probs, key=probs.get))
            if choice not in probs or probs[choice] < max(probs.values()) - 1e-5: raise InputError("Selected label must have maximal probability")
            p = probs[choice]; y = float(choice == truth)
            observations.append((p,y))
            multiclass_scores.append(sum((v-float(k==truth))**2 for k,v in probs.items()))
            if "confidence" in row:
                provider_confidence.append((finite(row["confidence"],"provider confidence",0,1),y))
        else: raise InputError("Calibration supports Noul probabilities and Choice distributions, not treating Score levels as success probabilities")
    def reliability(obs):
        groups = defaultdict(list)
        for p,y in obs: groups[min(bins-1,int(p*bins))].append((p,y))
        out=[]; ece=0.0
        for i in range(bins):
            bucket = groups[i]; count=len(bucket)
            mp=sum(p for p,y in bucket)/count if count else None
            accuracy=sum(y for p,y in bucket)/count if count else None
            if count: ece+=count/len(obs)*abs(mp-accuracy)
            out.append({"bin":i,"lower":i/bins,"upper":(i+1)/bins,"count":count,"mean_probability":mp,"empirical_rate":accuracy})
        return out,ece
    diag,ece=reliability(observations)
    # Coverage-risk curve uses label probability, never the provider's distribution statistic.
    coverage=[]
    for threshold in (0.5,0.6,0.7,0.8,0.9,0.95,0.99):
        if all(r.get("kind","noul")=="noul" for r in rows):
            selected=[(p,y) for p,y in observations if max(p,1-p)>=threshold]
            errors=sum((p>=0.5)!=bool(y) for p,y in selected)
        else:
            selected=[(p,y) for p,y in observations if p>=threshold]; errors=sum(1-y for p,y in selected)
        coverage.append({"threshold":threshold,"coverage":len(selected)/len(observations),"selective_error":errors/len(selected) if selected else None,"accepted":len(selected)})
    return {"count":len(rows),"binary_or_top_label_brier":sum((p-y)**2 for p,y in observations)/len(observations),
            "multiclass_brier_sum_convention":sum(multiclass_scores)/len(multiclass_scores) if multiclass_scores else None,
            "ece":ece,"bins":diag,"coverage_risk":coverage,
            "provider_confidence_diagnostic_bins":reliability(provider_confidence)[0] if provider_confidence else [],
            "provider_confidence_is_probability":False,
            "limitations":["Brier/ECE use probabilities; provider confidence is a distribution statistic and is reported diagnostically only.",
                           "ECE is bin-dependent and sample-dependent; examine subgroup reliability and bin counts.",
                           "Thresholds must be selected on calibration data and frozen before held-out test evaluation.",
                           "No finite calibration sample proves a security boundary safe."]}


def select_threshold(rows: list[dict], maximum_error: float = 0.05, minimum_count: int = 30) -> dict:
    """Choose coverage using a Wilson upper error bound; all selection data must be calibration."""
    finite(maximum_error,"maximum_error",0,1)
    if type(minimum_count) is not int or minimum_count<1: raise InputError("minimum_count must be positive")
    if any(r.get("split") != "calibration" or r.get("kind") != "choice" for r in rows):
        raise InputError("Threshold selection requires Choice calibration-split rows only")
    calibration(rows)
    z=1.959963984540054
    options=[]
    for threshold in sorted({max(r["probabilities"].values()) for r in rows}):
        accepted=[r for r in rows if max(r["probabilities"].values())>=threshold]
        n=len(accepted)
        if n<minimum_count: continue
        errors=sum(max(r["probabilities"],key=r["probabilities"].get)!=r["label"] for r in accepted)
        p=errors/n
        upper=(p+z*z/(2*n)+z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)
        if upper<=maximum_error: options.append({"threshold":threshold,"coverage":n/len(rows),"n":n,"errors":errors,"wilson_error_upper_95":upper})
    return {"selected":max(options,key=lambda x:x["coverage"]) if options else None,
            "status":"validate_on_frozen_holdout" if options else "no_threshold_meets_constraints",
            "warning":"Wilson bound is pointwise; searching thresholds is adaptive. The selected threshold is not certified without untouched holdout validation."}
