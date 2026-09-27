"""Explicit plan outcomes. These errors never authorize a mutation or execution."""
from ..io import InputError


class UnsupportedShape(InputError):
    implementation_status = 'unsupported'


class MissingBinding(InputError):
    implementation_status = 'blocked'
