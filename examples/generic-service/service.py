"""All exact operations. A correct no-JEV result is intentional."""
import hashlib
import hmac
import json


def total_with_tax(subtotal, tax_rate):
    return round(subtotal * (1 + tax_rate), 2)


def order_numbers(numbers):
    return sorted(numbers)


def payload_matches(payload, expected_digest):
    return hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected_digest)


def decode_payload(payload):
    return json.loads(payload)


def exact_permission(user_role, permitted_roles):
    return user_role in permitted_roles
