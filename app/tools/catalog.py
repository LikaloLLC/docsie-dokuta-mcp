"""
MCP tool: list_doc_types

Returns available documentation types and quality tiers.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.models import DOC_TYPE_INFO, QUALITY_TIERS, DocType


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_doc_types() -> str:
        """
        List available documentation types and quality tiers for video-to-docs conversion.

        Returns a description of each doc type and quality tier so you can help
        the user pick the right options before calling analyze_video.
        """
        lines = ["## Available Documentation Types\n"]

        for dt in DocType:
            info = DOC_TYPE_INFO[dt]
            lines.append(f"- **{info['name']}** (`{dt.value}`): {info['description']}")

        lines.append("\n## Quality Tiers\n")
        for tier_name, tier in QUALITY_TIERS.items():
            lines.append(
                f"- **{tier_name}**: {tier['description']} "
                f"({tier['credits_per_minute']} credits/min)"
            )

        lines.append("\n## Free Tier")
        lines.append("Videos up to 5 minutes are processed **free**. Longer videos require a Docsie account with credits.")
        lines.append("Sign up or manage credits at https://www.docsie.io/pricing/")

        return "\n".join(lines)
