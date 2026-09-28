"""Exact arithmetic is deliberately outside semantic placement scope."""


def invoice_total(cents, count):
    if not isinstance(cents, int) or not isinstance(count, int):
        raise TypeError("integer inputs required")
    return cents * count
