"""Validate bounded probe data before it can contribute behavioral assertions."""
from __future__ import annotations

from ..contracts import validate_contract
from ..io import InputError, canonical
from .recipes import RECIPES


def validate_observation(observation: object, spec: dict) -> None:
    """Structural validity is not execution authenticity or deployment authority."""
    try:
        if len(canonical(observation)) > 2_000_000:
            raise InputError('Implementation observation exceeds the local byte limit')
    except (TypeError, ValueError, RecursionError):
        raise InputError('Invalid implementation observation serialization') from None
    validate_contract(observation, 'implementation-observation')
    arities = RECIPES[spec['recipe']['id']].bindings
    for row in observation['trace']:
        role = row['role']
        if role not in spec['bindings'] or role not in arities:
            raise InputError('Observation role is not bound by this recipe')
        if row['event'] == 'call' and len(row['args']) != arities[role]:
            raise InputError('Observation arguments differ from the bound role')
