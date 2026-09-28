"""A plausible finite seam with no host observation or policy callbacks."""


def q8(value):
    return "accept" if "?" in value else "review"


def entry(value):
    return q8(value)
