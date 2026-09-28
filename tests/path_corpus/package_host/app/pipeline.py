"""Finite host-owned policy and effects; no evaluator imports."""

ALLOWED = frozenset({"read", "summarize"})


def records_for(request):
    return (request["item"], request["action"])


def approved(request, action):
    return action in ALLOWED and request.get("permit") is True


def dispatch(request):
    item, action = records_for(request)
    if not approved(request, action):
        return {"result": "denied", "events": []}
    events = [(action, item)]
    return {"result": f"done:{action}:{item}", "events": events}


def entry(request):
    return dispatch(request)
