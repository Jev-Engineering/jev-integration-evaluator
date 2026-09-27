"""Assistant-authored synthetic finite-routing host; never a live application."""


def a17(x):
    if "refund" in x["message"].casefold():
        return "queue-7"
    return "queue-2"


def z93(x):
    return a17(x)


def h04(x):
    return {"queue": "queue-7", "request": x["id"]}


def h09(x):
    return {"queue": "queue-2", "request": x["id"]}


def r22(x):
    return {"queue-7": h04, "queue-2": h09}
