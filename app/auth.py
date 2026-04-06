"""
OAuth2 token validation for MCP requests.

Extracts Bearer token from the MCP request context and resolves it
to a UserContext via the Docsie internal API.

Uses contextvars for async-safe per-request user context (not globals).
"""
from __future__ import annotations

import contextvars
import logging
from typing import Optional

from app.models import UserContext
from app.services.docsie_client import get_user_context

logger = logging.getLogger(__name__)

# Async-safe per-request storage (NOT a global variable)
_current_user_var: contextvars.ContextVar[Optional[UserContext]] = contextvars.ContextVar(
    "_current_user_var", default=None
)
_current_ip_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_ip_var", default=None
)


async def resolve_user_from_token(token: str) -> Optional[UserContext]:
    """Validate a Bearer token and return the user context."""
    if not token:
        return None
    return await get_user_context(token)


def get_current_user() -> Optional[UserContext]:
    """Get the current authenticated user (set per-request by middleware)."""
    return _current_user_var.get()


def set_current_user(user: Optional[UserContext]) -> None:
    """Set the current user for this async context."""
    _current_user_var.set(user)


def get_client_ip() -> Optional[str]:
    """Get the client IP for the current request."""
    return _current_ip_var.get()


def set_client_ip(ip: Optional[str]) -> None:
    """Set the client IP for this async context."""
    _current_ip_var.set(ip)
