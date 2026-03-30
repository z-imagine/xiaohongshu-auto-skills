"""Bridge authentication helpers."""

from __future__ import annotations


def is_token_allowed(expected_token: str, provided_token: str | None) -> bool:
    """Return True when bridge access is allowed for the supplied token."""
    if not expected_token:
        return True
    return expected_token == (provided_token or "")

