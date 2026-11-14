"""Security review errors."""

from __future__ import annotations


class SecurityReviewError(RuntimeError):
    """Raised when a security review cannot be completed."""


class SecurityReviewNotFoundError(Exception):
    """Raised when a review id does not exist."""


class SecurityWaiverNotFoundError(Exception):
    """Raised when a waiver id does not exist."""
