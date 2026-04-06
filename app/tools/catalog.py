"""
MCP tool: list_doc_types

Returns available documentation types and quality tiers.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.models import DOC_TYPE_INFO, DocType


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_doc_types() -> str:
        """
        List available documentation types for video-to-docs conversion.

        Returns a description of each doc type so you can help the user
        pick the right option before calling analyze_video.
        """
        lines = ["## Available Documentation Types\n"]

        for dt in DocType:
            info = DOC_TYPE_INFO[dt]
            lines.append(f"- **{info['name']}** (`{dt.value}`): {info['description']}")

        lines.append("\n## Quality Tiers\n")
        lines.append("- **draft**: Fast, lower detail — good for quick overviews")
        lines.append("- **standard**: Balanced quality and speed")
        lines.append("- **detailed**: High detail — captures most on-screen changes")
        lines.append("- **ultra**: Maximum detail — every frame analyzed")

        lines.append("\n## Pricing")
        lines.append("Credits are charged based on video length and quality tier.")
        lines.append("Use `analyze_video` with `quality=\"draft\"` for the most affordable option.")
        lines.append("Manage credits at https://www.docsie.io/pricing/")

        return "\n".join(lines)
