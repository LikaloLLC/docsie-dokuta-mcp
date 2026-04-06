"""
Pydantic models for MCP server data structures.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class DocType(str, Enum):
    USER_GUIDE = "user-guide"
    SOP = "sop"
    PRODUCT_DOCS = "product-docs"
    POLICY = "policy"
    BLOG = "blog"


DOC_TYPE_INFO = {
    DocType.USER_GUIDE: {
        "name": "User Guide",
        "description": "Step-by-step user guide with screenshots extracted from the video",
    },
    DocType.SOP: {
        "name": "Standard Operating Procedure",
        "description": "Formal SOP document with numbered steps and compliance-ready formatting",
    },
    DocType.PRODUCT_DOCS: {
        "name": "Product Documentation",
        "description": "Product feature documentation suitable for a knowledge base",
    },
    DocType.POLICY: {
        "name": "Policy Document",
        "description": "Formal policy document derived from video training content",
    },
    DocType.BLOG: {
        "name": "Blog Post",
        "description": "Blog-style content summarizing the video for marketing or education",
    },
}
