"""Minimal TypeSafe HTTP adapter with explicit egress consent and strict response checking."""
from __future__ import annotations
import os
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol, Any
from .io import InputError, canonical, digest, finite, loads
from .questions import validate_questions

class EvaluationClient(Protocol):
    is_remote: bool
    def evaluate(self, state: Any, questions: dict, model: str, timeout_ms: int) -> dict: ...


def validate_response(response: dict, questions: dict, model: str | None = None) -> dict:
    validate_questions(questions)
    if not isinstance(response,dict) or not isinstance(response.get("model"),str): raise InputError("Response lacks a model ID")
    if model and response["model"]!=model: raise InputError("Resolved model differs from the pinned model")
    answers=response.get("answers")
    if not isinstance(answers,dict) or set(answers)!=set(questions): raise InputError("Response question keys do not match request")
    for key,q in questions.items():
        a=answers[key]
        if not isinstance(a,dict) or a.get("type")!=q["type"]: raise InputError("Response primitive does not match question")
        if q["type"]=="noul":
            finite(a.get("noul"),"Noul P(yes)",0,1)
            if "confidence" in a: raise InputError("Noul must not be interpreted as carrying Choice-style confidence")
            continue
        finite(a.get("confidence"),"provider confidence",0,1)
        probs=a.get("probabilities")
        if not isinstance(probs,dict): raise InputError("Missing probability distribution")
        labels=set(q["criteria"]) if q["type"]=="choice" else {str(i) for i in range(len(q["criteria"]))}
        if set(probs)!=labels: raise InputError("Response labels differ from request")
        for p in probs.values(): finite(p,"probability",0,1)
        if abs(sum(probs.values())-1)>1e-5: raise InputError("Probabilities do not sum to one")
        if q["type"]=="choice":
            if a.get("choice") not in labels: raise InputError("Invalid selected action")
            if probs[a["choice"]]+1e-6<max(probs.values()): raise InputError("Choice is not a maximum-probability label")
        else:
            score=finite(a.get("score"),"score",0,len(labels)-1)
            expected=sum(float(k)*v for k,v in probs.items())
            if abs(score-expected)>1e-4: raise InputError("Score is inconsistent with level probabilities")
            if not isinstance(a.get("legend"),dict) or set(a["legend"])!=labels: raise InputError("Score legend is invalid")
    usage=response.get("usage")
    if not isinstance(usage,dict): raise InputError("Usage metadata is required")
    for key in ("input_tokens","output_tokens"):
        if type(usage.get(key)) is not int or usage[key]<0: raise InputError("Token counts must be nonnegative integers")
    return response


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise InputError("Redirect refused: never forward API credentials to another endpoint")


class TypeSafeHTTPClient:
    is_remote=True
    order_sensitive=True
    def __init__(self, *, allow_network: bool = False, endpoint: str = "https://api.typesafe.ai/v1/systemone",
                 approved_endpoint: str | None = None, max_request_bytes: int = 96000):
        if allow_network is not True: raise InputError("Explicit network/data-egress authorization is required")
        url=urllib.parse.urlsplit(endpoint)
        if url.scheme!="https" or url.username or url.password or url.fragment or url.query:
            raise InputError("Endpoint must be an HTTPS URL without embedded credentials/query/fragment")
        if endpoint!="https://api.typesafe.ai/v1/systemone" and approved_endpoint!=endpoint:
            raise InputError("A custom endpoint requires exact endpoint approval")
        key=os.environ.get("TYPESAFE_API_KEY")
        if not key: raise InputError("Set TYPESAFE_API_KEY in the process environment")
        self.endpoint=endpoint; self._key=key; self.max_request_bytes=max_request_bytes
        self.opener=urllib.request.build_opener(NoRedirect)

    def credential_still_current(self) -> bool:
        """Reject use after process key rotation; never disclose the key."""
        current = os.environ.get('TYPESAFE_API_KEY')
        return isinstance(current, str) and hmac.compare_digest(current, self._key)

    def evaluate(self,state,questions,model,timeout_ms):
        validate_questions(questions)
        if model.endswith(("latest","preview")): raise InputError("Pin a versioned model for auditable evaluation")
        if type(timeout_ms) is not int or timeout_ms<=0: raise InputError("timeout_ms must be positive")
        payload=json.dumps({"state":state,"questions":questions,"model":model}, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(payload)>self.max_request_bytes: raise InputError("Request exceeds application byte budget; reduce evidence, never silently truncate")
        req=urllib.request.Request(self.endpoint,data=payload,method="POST",headers={"Authorization":"Bearer "+self._key,"Content-Type":"application/json","User-Agent":"jev-integration-evaluator/1.2"})
        started=time.monotonic()
        try:
            with self.opener.open(req,timeout=timeout_ms/1000) as response:
                raw=response.read(2_000_001)
        except urllib.error.HTTPError as exc:
            # No body/headers in error messages: they may contain sensitive request data.
            raise InputError(f"TypeSafe HTTP {exc.code}; single-attempt fallback, no automatic spending retry") from None
        except (urllib.error.URLError,TimeoutError,OSError):
            raise InputError("TypeSafe transport failed or timed out") from None
        if len(raw)>2_000_000: raise InputError("Response exceeds byte budget")
        if (time.monotonic()-started)*1000>timeout_ms: raise InputError("Evaluation exceeded latency budget; result discarded")
        result=loads(raw.decode("utf-8"))
        validate_response(result,questions,model)
        return result


class FixtureClient:
    """Offline exact-request fixture lookup; never fabricates live JEV behavior."""
    is_remote=False
    evidence_type="synthetic"
    def __init__(self, fixtures: dict, *, order_sensitive: bool = False):
        self.fixtures=fixtures; self.calls=0; self.order_sensitive=order_sensitive
    def evaluate(self,state,questions,model,timeout_ms):
        import copy
        self.calls+=1
        from .robustness import request_fingerprint
        key=request_fingerprint(state,questions,model) if self.order_sensitive else digest({"state":state,"questions":questions,"model":model})
        if key not in self.fixtures: raise InputError("No fixture for exact state/questions/model")
        response=copy.deepcopy(self.fixtures[key])
        return validate_response(response,questions,model)
