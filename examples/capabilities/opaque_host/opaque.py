"""Assistant-authored synthetic source fixture. Discovery must not import it."""


def n4(p):
    return p.dispatch()


def v8(p):
    return n4(p)


R2 = {"choice-a": n4}
