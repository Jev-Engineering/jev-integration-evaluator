"""Independent finite-action host for the connected repository path corpus."""
from __future__ import annotations

from threading import RLock

LOCK = RLock()
EVENTS = []
ALLOWED = {"read", "summarize"}


def do_read(request):
    if not host_validate(request, "read"):
        return host_blocked(request, "host_policy")
    EVENTS.append(["read", request["item"]])
    return "read:" + request["item"]


def do_summarize(request):
    EVENTS.append(["summarize", request["item"]])
    return "summary:" + request["item"]


def original_dispatch(request):
    return do_read(request)


def reviewed_boundary(request):
    return original_dispatch(request)


def public_entry(request):
    return reviewed_boundary(request)


def host_runtime(request):
    raise RuntimeError("Explicit host startup must install the runtime owner")


def host_evidence(request, action):
    return {"item_kind": request.get("kind", "unknown"), "intent": request.get("intent", "read")}


def host_baseline_action(request):
    return "read"


def host_registry(request):
    return {"read": "read", "summarize": "summarize"}


def host_gate(request, action):
    from jev_integration_evaluator.runtime import HostGate
    return HostGate(tuple(sorted(ALLOWED)), hard_block=not request.get("permit", False),
                    approval_required=action == "summarize",
                    approval_granted=request.get("approved", False),
                    baseline_permitted=request.get("permit", False))


def host_validate(request, action):
    return (request.get("permit") is True and action in ALLOWED
            and isinstance(request.get("item"), str) and bool(request["item"]))


def host_blocked(request, reason):
    return "blocked"


def host_guard(request):
    return LOCK


def host_observe(request):
    return {"events": len(EVENTS)}


def host_postcondition(request, outcome, observations):
    return (observations["after"]["events"] == observations["before"]["events"] + 1
            and outcome == "read:" + request["item"])


def host_finish(request, outcome, disposition):
    return {"result": outcome, "action": disposition}
