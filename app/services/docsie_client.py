"""
Async HTTP client for Docsie API.

Forwards the user's Bearer token to Docsie's v3 API.
Docsie handles auth, org resolution, credits, and Dokuta interaction.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.docsie_internal_url.rstrip("/"),
            timeout=60.0,
        )
    return _client


def _auth_headers(bearer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {bearer_token}"}


async def submit_video(
    bearer_token: str,
    video_url: str,
    quality: str = "standard",
    language: str = "english",
) -> dict[str, Any]:
    """Submit a video for documentation generation via Docsie's v3 API."""
    client = _get_client()
    resp = await client.post(
        "/api_v2/v3/video-to-docs/submit/",
        headers=_auth_headers(bearer_token),
        json={
            "video_url": video_url,
            "quality": quality,
            "language": language,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def get_job_status(bearer_token: str, job_id: str) -> dict[str, Any]:
    """Poll job status via Docsie's v3 API."""
    client = _get_client()
    resp = await client.get(
        f"/api_v2/v3/video-to-docs/{job_id}/status/",
        headers=_auth_headers(bearer_token),
    )
    resp.raise_for_status()
    return resp.json()


async def get_job_result(bearer_token: str, job_id: str) -> dict[str, Any]:
    """Get completed job result via Docsie's v3 API."""
    client = _get_client()
    resp = await client.get(
        f"/api_v2/v3/video-to-docs/{job_id}/result/",
        headers=_auth_headers(bearer_token),
    )
    resp.raise_for_status()
    return resp.json()


async def estimate_cost(
    bearer_token: str,
    quality: str = "standard",
    duration_minutes: float | None = None,
) -> dict[str, Any]:
    """Estimate credit cost for a video-to-docs job."""
    client = _get_client()
    body: dict[str, Any] = {"quality": quality}
    if duration_minutes is not None:
        body["duration_minutes"] = duration_minutes
    resp = await client.post(
        "/api_v2/v3/video-to-docs/estimate/",
        headers=_auth_headers(bearer_token),
        json=body,
    )
    resp.raise_for_status()
    return resp.json()


async def list_jobs(bearer_token: str) -> list[dict[str, Any]]:
    """List the user's video-to-docs jobs."""
    client = _get_client()
    resp = await client.get(
        "/api_v2/v3/video-to-docs/",
        headers=_auth_headers(bearer_token),
    )
    resp.raise_for_status()
    return resp.json()
