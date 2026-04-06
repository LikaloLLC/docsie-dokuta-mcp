"""
Docsie Video-to-Docs MCP Server

Remote MCP server for Anthropic's Connectors Directory.
Converts videos into structured documentation using Dokuta AI.

Transport: Streamable HTTP at /mcp
Auth: OAuth2 via Docsie's /o2/ provider (proxied metadata)
"""
from __future__ import annotations

import asyncio
import json
import logging

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from app import auth
from app.config import settings
from app.rate_limit import periodic_cleanup
from app.tools import catalog, video

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="Docsie Video-to-Docs",
    version="0.1.0",
    description=(
        "Convert videos into structured documentation using AI. "
        "Submit a video URL and get back a user guide, SOP, product docs, "
        "policy document, or blog post. Videos up to 10 minutes are free. "
        "Sign in with Docsie for unlimited length."
    ),
)

# Register tools
catalog.register(mcp)
video.register(mcp)


# ---------------------------------------------------------------------------
# OAuth2 Authorization Server Metadata
# ---------------------------------------------------------------------------
async def well_known_oauth(request: Request) -> JSONResponse:
    """
    GET /.well-known/oauth-authorization-server

    Returns OAuth2 metadata pointing to Docsie's existing OAuth provider.
    Claude uses this to discover the authorize/token endpoints.
    """
    base = settings.docsie_base_url.rstrip("/")
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/o2/authorize/",
        "token_endpoint": f"{base}/o2/token/",
        "revocation_endpoint": f"{base}/o2/revoke_token/",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_basic"],
        "scopes_supported": ["read", "write"],
    })


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "docsie-mcp"})


# ---------------------------------------------------------------------------
# MCP Auth Hook — extract Bearer token before each tool call
# ---------------------------------------------------------------------------
# The MCP SDK's streamable HTTP transport receives the Authorization header.
# We intercept it in the ASGI middleware below to resolve the user context.


class AuthMiddleware:
    """
    ASGI middleware that extracts the Bearer token from MCP requests
    and sets the current user context for tool handlers.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))

            # Extract Bearer token
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                user = await auth.resolve_user_from_token(token)
                auth.set_current_user(user)
            else:
                auth.set_current_user(None)

            # Extract client IP (X-Forwarded-For from ingress, or direct)
            xff = headers.get(b"x-forwarded-for", b"").decode()
            if xff:
                # Take the first (leftmost) IP — the original client
                client_ip = xff.split(",")[0].strip()
            else:
                client_ip = scope.get("client", ("",))[0] if scope.get("client") else None
            auth.set_client_ip(client_ip)

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Background cleanup for rate limiter
# ---------------------------------------------------------------------------
async def _rate_limit_cleanup_loop():
    """Periodically clean up stale rate limit entries."""
    while True:
        await asyncio.sleep(1800)  # Every 30 minutes
        periodic_cleanup()


async def on_startup():
    asyncio.create_task(_rate_limit_cleanup_loop())


# ---------------------------------------------------------------------------
# ASGI App
# ---------------------------------------------------------------------------
mcp_asgi = mcp.streamable_http_app()

app = Starlette(
    on_startup=[on_startup],
    routes=[
        Route("/.well-known/oauth-authorization-server", well_known_oauth),
        Route("/health", health),
        Mount("/mcp", app=mcp_asgi),
    ],
    middleware=[
        Middleware(AuthMiddleware),
        Middleware(
            CORSMiddleware,
            allow_origins=[
                "https://claude.ai",
                "https://api.anthropic.com",
            ],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        ),
    ],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
