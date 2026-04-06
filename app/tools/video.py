"""
MCP tools: analyze_video, check_job_status

Forwards requests to Docsie's v3 video-to-docs API.
Docsie handles auth, credits, and Dokuta interaction.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import FastMCP

from app.auth import get_current_token
from app.models import DocType
from app.services import docsie_client

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

VALID_QUALITIES = ("draft", "standard", "detailed", "ultra")


def _is_safe_url(url: str) -> bool:
    """SSRF prevention — block private/internal URLs."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    blocked = {"localhost", "metadata.google.internal", "metadata.internal"}
    if hostname.lower() in blocked:
        return False

    if "." not in hostname:
        return False
    for suffix in (".svc", ".local", ".internal", ".cluster", ".pod"):
        if hostname.lower().endswith(suffix):
            return False

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass

    return True


def _require_auth() -> str | None:
    """Return an error message if user is not authenticated, else None."""
    token = get_current_token()
    if not token:
        return (
            "You need to sign in with your Docsie account to use this tool. "
            "Connect your account in Claude's connector settings at "
            "https://claude.ai/settings/connectors"
        )
    return None


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def analyze_video(
        video_url: str,
        quality: str = "standard",
        language: str = "english",
    ) -> str:
        """
        Submit a video URL for AI-powered documentation generation.

        Analyzes the video (screen recording, training video, demo, etc.) and
        generates structured documentation. Processing takes 2-15 minutes
        depending on video length. Requires a Docsie account with AI credits.

        Args:
            video_url: URL of the video (YouTube, Loom, Vimeo, direct MP4 link, etc.)
            quality: Quality tier - "draft" (fast), "standard" (balanced), "detailed" (thorough), "ultra" (maximum)
            language: Output language (default: "english")

        Returns:
            A job ID and instructions for checking status.
        """
        auth_err = _require_auth()
        if auth_err:
            return auth_err

        if quality not in VALID_QUALITIES:
            return f"Invalid quality '{quality}'. Valid options: {', '.join(VALID_QUALITIES)}"

        if not _is_safe_url(video_url):
            return (
                "Invalid video URL. Please provide a public HTTP/HTTPS URL. "
                "Internal, private, or localhost URLs are not allowed."
            )

        token = get_current_token()
        try:
            result = await docsie_client.submit_video(
                bearer_token=token,
                video_url=video_url,
                quality=quality,
                language=language,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 402:
                data = exc.response.json()
                return (
                    f"**Insufficient AI credits.**\n\n"
                    f"Estimated minimum cost: {data.get('estimated_minimum_cost', '?'):,} credits\n"
                    f"Your balance: {data.get('total_available', '?'):,} credits\n\n"
                    f"Purchase credits at https://www.docsie.io/pricing/"
                )
            if exc.response.status_code == 401:
                return "Your Docsie session has expired. Please reconnect in Claude's connector settings."
            return f"Failed to submit video: {exc.response.text[:200]}"
        except httpx.RequestError as exc:
            return f"Failed to connect to Docsie: {exc}"

        job_id = result.get("job_id", "unknown")
        return (
            f"Video submitted for documentation generation.\n\n"
            f"**Job ID**: `{job_id}`\n"
            f"**Quality**: {result.get('quality', quality)}\n"
            f"**Credits/min**: {result.get('credits_per_minute', '?')}\n"
            f"**Status**: {result.get('status', 'started')}\n\n"
            f"Use `check_job_status` with job_id=\"{job_id}\" to monitor progress."
        )

    @mcp.tool()
    async def check_job_status(job_id: str) -> str:
        """
        Check the status of a video-to-docs job and retrieve results.

        Call this after analyze_video to poll for progress and retrieve
        the completed documentation when ready.

        Args:
            job_id: The job ID returned by analyze_video.

        Returns:
            Progress info if still processing, or the full documentation if complete.
        """
        auth_err = _require_auth()
        if auth_err:
            return auth_err

        if not _UUID_RE.match(job_id):
            return "Invalid job_id format. Please provide the UUID returned by analyze_video."

        token = get_current_token()

        # First check status
        try:
            status_data = await docsie_client.get_job_status(token, job_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return f"Job `{job_id}` not found. It may not have started yet — try again in 30 seconds."
            return f"Error checking status: {exc.response.text[:200]}"
        except httpx.RequestError as exc:
            return f"Failed to connect to Docsie: {exc}"

        normalized = status_data.get("normalized_status", status_data.get("status", "unknown"))

        if status_data.get("can_poll", False):
            return (
                f"**Status**: Processing\n"
                f"**Details**: Job is still running.\n\n"
                f"Try again in 30-60 seconds."
            )

        if normalized == "failed":
            error = status_data.get("error", "Unknown error")
            return f"**Status**: Failed\n**Error**: {error}"

        if normalized == "canceled":
            return f"**Status**: Canceled\nThe job was canceled."

        if normalized == "done":
            # Fetch full result
            try:
                result = await docsie_client.get_job_result(token, job_id)
            except httpx.HTTPStatusError as exc:
                return f"Job completed but failed to retrieve result: {exc.response.text[:200]}"
            except httpx.RequestError as exc:
                return f"Job completed but failed to connect: {exc}"

            markdown = result.get("markdown", "")
            duration = result.get("duration_minutes") or 0
            credits = result.get("credits_charged") or 0
            quality = result.get("quality", "unknown")

            header = (
                f"**Status**: Complete ({duration:.1f} minutes of video)\n"
                f"**Quality**: {quality}\n"
                f"**Credits charged**: {credits:,}\n\n"
                f"---\n\n"
            )
            return header + markdown

        return f"**Status**: {normalized}\nTry again in 30 seconds."
