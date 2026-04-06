"""
OAuth2 token handling using async-safe contextvars.

The Bearer token from Claude is forwarded to Docsie's API on every request.
Docsie validates the token and resolves the user/org context.
"""
from __future__ import annotations

import contextvars
import logging

logger = logging.getLogger(__name__)

_current_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_token", default=None
)


def get_current_token() -> str | None:
    """Get the Bearer token for this request."""
    return _current_token.get()


def set_current_token(token: str | None) -> None:
    """Set the Bearer token for this request."""
    _current_token.set(token)
