def b(x):
    return x["operation"](x)

def q(x):
    return b(x)

raise RuntimeError("This synthetic host must not be imported by preparation")
