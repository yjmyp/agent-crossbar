from __future__ import annotations

import secrets


def has_valid_bearer_token(header_value: str | None, expected_token: str) -> bool:
    if not header_value or not expected_token:
        return False
    scheme, separator, token = header_value.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        return False
    return secrets.compare_digest(token, expected_token)
