"""Project-owned opaque host fixture; no evaluator imports."""

ALLOWED = frozenset({"read", "summarize"})


class Store:
    def __init__(self):
        self.events = []

    def perform(self, action, item):
        self.events.append((action, item))
        return f"done:{action}:{item}"


def q7(value, action, store):
    """Opaque policy seam: validate before the only effect."""
    if action not in ALLOWED:
        return "denied"
    return store.perform(action, value)


def serve(value, action, store):
    result = q7(value, action, store)
    return {"result": result, "event_count": len(store.events)}
