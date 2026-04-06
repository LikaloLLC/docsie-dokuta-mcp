"""
Async HTTP client for the Dokuta video analysis API.

Handles video submission, status polling, and result fetching.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

import httpx

from app.config import settings
from app.models import JobStatus

logger = logging.getLogger(__name__)


async def submit_video(
    video_url: str,
    doc_type: str = "user-guide",
    language: str = "English",
    seconds_per_frame: int = 10,
    context: str = "",
) -> dict:
    """
    Submit a video to Dokuta for analysis.

    Returns dict with task_id and session_id on success,
    or error info on failure.
    """
    base = settings.dokuta_api_url.rstrip("/")
    url = f"{base}/generation/{doc_type}/"
    session_id = str(uuid.uuid4())

    form_data = {
        "video_url": video_url,
        "language": language,
        "seconds_per_frame": str(seconds_per_frame),
        "session_id": session_id,
        "mode": "Relaxed",
        "save_images": "true",
    }
    if context:
        form_data["context"] = context

    headers = {"X-API-Key": settings.dokuta_api_key}

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, data=form_data, headers=headers)
    except httpx.RequestError as exc:
        logger.error("Failed to submit video to Dokuta: %s", exc)
        return {"error": f"Failed to connect to video analysis service: {exc}"}

    if resp.status_code not in (200, 201, 202):
        logger.warning("Dokuta submission failed: %s %s", resp.status_code, resp.text[:500])
        return {"error": f"Video analysis service returned {resp.status_code}"}

    data = resp.json()
    return {
        "task_id": data.get("task_id", ""),
        "session_id": session_id,
        "status": data.get("status", "processing"),
        "message": data.get("message", "Video submitted for analysis"),
        "estimated_duration": data.get("estimated_duration"),
    }


async def get_job_status(session_id: str) -> JobStatus:
    """
    Poll Dokuta for the status of a video analysis job.
    """
    base = settings.dokuta_api_url.rstrip("/")
    url = f"{base}/generation/by-session/{session_id}"
    headers = {"X-API-Key": settings.dokuta_api_key}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        logger.error("Failed to query Dokuta status: %s", exc)
        return JobStatus(found=False, error=str(exc))

    if resp.status_code == 404:
        return JobStatus(found=False)

    if resp.status_code != 200:
        return JobStatus(found=False, error=f"Dokuta returned {resp.status_code}")

    data = resp.json()
    if data.get("status") == "not_found":
        return JobStatus(found=False)

    return JobStatus(
        found=True,
        status=data.get("status"),
        progress=data.get("progress"),
        task_id=data.get("task_id"),
        result_url=data.get("result_url") or data.get("response"),
        duration_minutes=data.get("duration_minutes"),
        duration_seconds=data.get("duration_seconds"),
        message=data.get("message"),
        error=data.get("error"),
    )


def _is_trusted_result_url(url: str) -> bool:
    """Validate that result_url points to a trusted storage domain."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme != "https":
        return False

    trusted_domains = (
        ".supabase.co",
        ".supabase.in",
        ".amazonaws.com",
        ".s3.amazonaws.com",
        ".cloudfront.net",
        ".docsie.io",
        ".videodokuta.com",
    )
    hostname = (parsed.hostname or "").lower()
    return any(hostname.endswith(d) for d in trusted_domains)


async def fetch_result_content(result_url: str) -> Optional[str]:
    """
    Download the markdown result from Dokuta's storage (Supabase signed URL).

    Returns the markdown content string, or None on failure.
    Only fetches from trusted storage domains to prevent SSRF.
    """
    if not result_url:
        return None

    if not _is_trusted_result_url(result_url):
        logger.warning("Untrusted result_url rejected: %s", result_url[:200])
        return None

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(result_url)
    except httpx.RequestError as exc:
        logger.error("Failed to fetch Dokuta result: %s", exc)
        return None

    if resp.status_code != 200:
        logger.warning("Dokuta result fetch failed: %s", resp.status_code)
        return None

    return resp.text
