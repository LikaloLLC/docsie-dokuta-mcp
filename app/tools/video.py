"""
MCP tools: analyze_video, check_job_status

Core video-to-docs tools that submit videos to Dokuta and return results.
"""
from __future__ import annotations

import math
import re
import ipaddress
from typing import Optional
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

from app.auth import get_current_user, get_client_ip
from app.config import settings
from app.models import QUALITY_TIERS, DocType
from app.rate_limit import check_rate_limit
from app.services import dokuta_client, docsie_client

# Track which session_ids have already been charged (idempotency guard)
# In production, use Redis. For now, in-memory set is acceptable for a
# stateless service with few replicas (worst case: double-charge across pods,
# which the Django side's idempotency in _deduct_video_credits also catches).
_charged_sessions: set[str] = set()

# UUID v4 pattern for job_id validation
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def _is_safe_url(url: str) -> bool:
    """
    Check that a URL is not targeting internal/private networks (SSRF prevention).

    Blocks:
    - Private IP ranges (10.x, 172.16-31.x, 192.168.x)
    - Link-local (169.254.x)
    - Loopback (127.x, localhost)
    - IPv6 loopback/link-local
    - Non-HTTP schemes
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Block obvious internal hostnames
    blocked_hostnames = {
        "localhost",
        "metadata.google.internal",
        "metadata.internal",
    }
    if hostname.lower() in blocked_hostnames:
        return False

    # Block kubernetes service names (contains no dots, or ends in .svc, .local, .internal)
    if "." not in hostname:
        return False
    for suffix in (".svc", ".local", ".internal", ".cluster", ".pod"):
        if hostname.lower().endswith(suffix):
            return False

    # Block private/reserved IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        # hostname is a domain name, not IP — that's fine
        pass

    return True


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def analyze_video(
        video_url: str,
        doc_type: str = "user-guide",
        language: str = "English",
        quality: str = "standard",
        context: str = "",
    ) -> str:
        """
        Submit a video URL for AI-powered documentation generation.

        Analyzes the video (screen recording, training video, demo, etc.) and
        generates structured documentation. Processing takes 2-15 minutes
        depending on video length.

        Videos up to 10 minutes are FREE for anonymous users. Signed-in users
        with AI credits can process videos of any length.

        Args:
            video_url: URL of the video (YouTube, Loom, Vimeo, direct MP4 link, etc.)
            doc_type: Type of documentation to generate. One of:
                - "user-guide" (default): Step-by-step guide with screenshots
                - "sop": Standard Operating Procedure
                - "product-docs": Product documentation
                - "policy": Policy document
                - "blog": Blog post from video content
            language: Output language (default: "English")
            quality: Quality tier - "draft" (fast), "standard" (balanced), "detailed" (thorough)
            context: Optional context about the video to improve output quality

        Returns:
            A job ID and instructions for checking status.
        """
        # Rate limit check
        user = get_current_user()
        allowed, rate_msg = check_rate_limit(
            user_id=user.user_id if user else None,
            ip_address=get_client_ip(),
        )
        if not allowed:
            return rate_msg

        # Validate doc_type
        valid_types = [dt.value for dt in DocType]
        if doc_type not in valid_types:
            return f"Invalid doc_type '{doc_type}'. Valid options: {', '.join(valid_types)}"

        # Validate quality
        if quality not in QUALITY_TIERS:
            return f"Invalid quality '{quality}'. Valid options: draft, standard, detailed"

        # Validate URL — SSRF prevention
        if not _is_safe_url(video_url):
            return (
                "Invalid video URL. Please provide a public HTTP/HTTPS URL. "
                "Internal, private, or localhost URLs are not allowed."
            )

        # Sanitize context input (limit length to prevent abuse)
        if len(context) > 2000:
            context = context[:2000]

        tier = QUALITY_TIERS[quality]
        spf = tier["seconds_per_frame"]

        result = await dokuta_client.submit_video(
            video_url=video_url,
            doc_type=doc_type,
            language=language,
            seconds_per_frame=spf,
            context=context,
        )

        if "error" in result:
            return f"Failed to submit video: {result['error']}"

        session_id = result["session_id"]
        status = result.get("status", "processing")

        user = get_current_user()
        auth_note = ""
        if not user:
            auth_note = (
                "\n\nNote: You are not signed in to Docsie. Videos over 5 minutes "
                "will require a Docsie account. Connect your account in Claude's "
                "connector settings."
            )

        return (
            f"Video submitted for {doc_type.replace('-', ' ')} generation.\n\n"
            f"**Job ID**: `{session_id}`\n"
            f"**Quality**: {quality} ({spf} seconds per frame)\n"
            f"**Status**: {status}\n"
            f"**Estimated time**: 2-15 minutes depending on video length\n\n"
            f"Use `check_job_status` with job_id=\"{session_id}\" to monitor progress "
            f"and retrieve the result when complete."
            f"{auth_note}"
        )

    @mcp.tool()
    async def check_job_status(job_id: str) -> str:
        """
        Check the status of a video-to-docs analysis job.

        Call this after analyze_video to poll for progress and retrieve
        the completed documentation.

        Args:
            job_id: The job/session ID returned by analyze_video.

        Returns:
            Progress info if still processing, or the full documentation
            if complete. For videos over 5 minutes, a Docsie account with
            credits is required to access the full result. Signed-in users
            can process any length.
        """
        # Validate job_id is a UUID to prevent path traversal
        if not _UUID_RE.match(job_id):
            return "Invalid job_id format. Please provide the UUID returned by analyze_video."

        status = await dokuta_client.get_job_status(job_id)

        if not status.found:
            return (
                f"Job `{job_id}` not found. It may not have started yet — "
                f"try again in 30 seconds. If the issue persists, the job ID "
                f"may be incorrect."
            )

        # Still processing
        if status.status == "processing":
            pct = f"{status.progress * 100:.0f}%" if status.progress else "unknown"
            msg = status.message or "Analyzing video..."
            return (
                f"**Status**: Processing ({pct} complete)\n"
                f"**Details**: {msg}\n\n"
                f"Try again in 30-60 seconds."
            )

        # Failed
        if status.status == "failed":
            err = status.error or "Unknown error"
            return f"**Status**: Failed\n**Error**: {err}"

        # Completed — apply 5-minute free tier gate
        if status.status == "completed":
            return await _handle_completed(job_id, status)

        # Unknown status
        return f"**Status**: {status.status}\nTry again in 30 seconds."


async def _handle_completed(job_id: str, status) -> str:
    """Handle a completed job — deduct credits for authenticated users, free tier for anonymous."""
    duration_seconds = status.duration_seconds or (
        (status.duration_minutes or 0) * 60
    )
    duration_minutes = (status.duration_minutes or 0) if status.duration_minutes else (
        duration_seconds / 60
    )

    # Fetch the markdown content
    content = await dokuta_client.fetch_result_content(status.result_url)
    if not content:
        return (
            "**Status**: Completed but unable to retrieve the result. "
            "The result URL may have expired. Please try submitting the video again."
        )

    user = get_current_user()

    # ── Authenticated users: unlimited length, pay credits ───────────
    if user:
        # Idempotency: don't charge twice for the same session
        if job_id in _charged_sessions:
            return (
                f"**Status**: Complete ({duration_minutes:.1f} minutes of video)\n"
                f"**Credits**: Already charged for this job\n\n"
                f"---\n\n"
                f"{content}"
            )

        # Default to "standard" tier cost (500 credits/min) since we don't
        # track which quality was used in this stateless flow
        credits_per_min = 500
        capped_minutes = min(math.ceil(duration_minutes), 600)
        cost = capped_minutes * credits_per_min

        if user.credits_available < cost:
            preview = _truncate(content, 500)
            return (
                f"**Status**: Complete ({duration_minutes:.1f} minutes of video)\n\n"
                f"**Credits required**: {cost:,} (you have {user.credits_available:,})\n\n"
                f"You need more credits to access the full documentation for this "
                f"{duration_minutes:.1f}-minute video.\n\n"
                f"**Preview** (first 500 words):\n\n---\n\n{preview}\n\n---\n\n"
                f"Purchase credits at https://www.docsie.io/pricing/"
            )

        success = await docsie_client.deduct_credits(
            organization_id=user.organization_id,
            amount=cost,
            duration_minutes=duration_minutes,
            session_id=job_id,
        )

        if not success:
            preview = _truncate(content, 500)
            return (
                f"**Status**: Complete ({duration_minutes:.1f} minutes of video)\n\n"
                f"Credit deduction failed. Please try again or contact support.\n\n"
                f"**Preview** (first 500 words):\n\n---\n\n{preview}\n\n---\n\n"
            )

        _charged_sessions.add(job_id)
        if len(_charged_sessions) > 10000:
            to_remove = list(_charged_sessions)[:5000]
            for sid in to_remove:
                _charged_sessions.discard(sid)

        return (
            f"**Status**: Complete ({duration_minutes:.1f} minutes of video)\n"
            f"**Credits used**: {cost:,}\n\n"
            f"---\n\n"
            f"{content}"
        )

    # ── Anonymous users: free tier gate ──────────────────────────────
    is_free = duration_seconds <= settings.free_tier_max_seconds

    if is_free:
        return (
            f"**Status**: Complete ({duration_minutes:.1f} minutes of video)\n"
            f"**Cost**: Free (under {settings.free_tier_max_seconds // 60} minutes)\n\n"
            f"---\n\n"
            f"{content}"
        )

    preview = _truncate(content, 500)
    return (
        f"**Status**: Complete ({duration_minutes:.1f} minutes of video)\n\n"
        f"This video is over {settings.free_tier_max_seconds // 60} minutes. "
        f"To access the full documentation, connect your Docsie account "
        f"in Claude's connector settings.\n\n"
        f"**Preview** (first 500 words):\n\n---\n\n{preview}\n\n---\n\n"
        f"Sign up at https://www.docsie.io/pricing/ to get started."
    )


def _truncate(text: str, max_words: int) -> str:
    """Truncate text to approximately max_words words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "\n\n[... truncated ...]"
