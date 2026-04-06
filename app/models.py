"""
Pydantic models for MCP server data structures.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

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

QUALITY_TIERS = {
    "draft": {
        "description": "Fast, lower detail — good for quick overviews",
        "seconds_per_frame": 20,
        "credits_per_minute": 250,
    },
    "standard": {
        "description": "Balanced quality and speed",
        "seconds_per_frame": 10,
        "credits_per_minute": 500,
    },
    "detailed": {
        "description": "High detail — captures most on-screen changes",
        "seconds_per_frame": 5,
        "credits_per_minute": 1000,
    },
}


class UserContext(BaseModel):
    user_id: int
    username: str
    email: str
    organization_id: str
    organization_slug: str
    organization_name: str
    workspace_id: Optional[str] = None
    plan: str = "startup"
    is_paid: bool = False
    credits_available: int = 0
    scope: str = ""


class JobStatus(BaseModel):
    found: bool = False
    status: Optional[str] = None  # processing, completed, failed
    progress: Optional[float] = None
    task_id: Optional[str] = None
    result_url: Optional[str] = None
    duration_minutes: Optional[float] = None
    duration_seconds: Optional[float] = None
    message: Optional[str] = None
    error: Optional[str] = None
