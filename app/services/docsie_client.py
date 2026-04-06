"""
Async HTTP client for Docsie Django internal API.

Handles token validation and credit deduction.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings
from app.models import UserContext

logger = logging.getLogger(__name__)

# Simple in-memory cache for token → UserContext (TTL managed by caller)
_token_cache: dict[str, tuple[float, UserContext]] = {}
_CACHE_TTL = 30  # seconds


async def get_user_context(bearer_token: str) -> Optional[UserContext]:
    """
    Validate an OAuth2 Bearer token against Docsie and return user context.

    Caches results for 30 seconds to avoid hammering the introspect endpoint.
    """
    import time

    now = time.time()

    # Check cache
    if bearer_token in _token_cache:
        cached_at, ctx = _token_cache[bearer_token]
        if now - cached_at < _CACHE_TTL:
            return ctx
        del _token_cache[bearer_token]

    base = settings.docsie_internal_url.rstrip("/")
    url = f"{base}/api/internal/mcp/user-context/"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
    except httpx.RequestError as exc:
        logger.error("Failed to reach Docsie for token validation: %s", exc)
        return None

    if resp.status_code != 200:
        logger.debug("Token validation failed: %s %s", resp.status_code, resp.text[:200])
        return None

    data = resp.json()
    ctx = UserContext(
        user_id=data["user_id"],
        username=data["username"],
        email=data.get("email", ""),
        organization_id=data["organization_id"],
        organization_slug=data["organization_slug"],
        organization_name=data.get("organization_name", ""),
        workspace_id=data.get("workspace_id"),
        plan=data.get("plan", "startup"),
        is_paid=data.get("is_paid", False),
        credits_available=data.get("credits", {}).get("total_available", 0),
        scope=data.get("scope", ""),
    )

    _token_cache[bearer_token] = (now, ctx)
    return ctx


async def deduct_credits(
    organization_id: str,
    amount: int,
    duration_minutes: float,
    session_id: str = "",
) -> bool:
    """
    Deduct credits from an organization via Docsie internal API.

    Returns True if deduction succeeded, False if insufficient credits.
    """
    base = settings.docsie_internal_url.rstrip("/")
    url = f"{base}/api/internal/mcp/deduct-credits/"

    body = {
        "organization_id": organization_id,
        "amount": amount,
        "transaction_type": "deduct_video",
        "metadata": {
            "source": "mcp_server",
            "duration_minutes": duration_minutes,
            "session_id": session_id,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json=body,
                headers={"X-Internal-Key": settings.mcp_internal_api_key},
            )
    except httpx.RequestError as exc:
        logger.error("Failed to reach Docsie for credit deduction: %s", exc)
        return False

    if resp.status_code != 200:
        logger.warning("Credit deduction failed: %s %s", resp.status_code, resp.text[:200])
        return False

    data = resp.json()
    return data.get("success", False)
