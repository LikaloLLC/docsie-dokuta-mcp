"""
Docsie Video-to-Docs MCP Server

Remote MCP server for Anthropic's Connectors Directory.
Converts videos into structured documentation via Docsie's API.

Transport: Streamable HTTP at /mcp
Auth: OAuth2 via Docsie's /o2/ provider
"""
from __future__ import annotations

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
from app.tools import catalog, video

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="Docsie Video-to-Docs",
    version="0.2.0",
    description=(
        "Convert videos into structured documentation using AI. "
        "Submit a video URL and get back a user guide, SOP, product docs, "
        "policy document, or blog post. Requires a Docsie account."
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
        "authorization_endpoint": f"{base}/o2/mcp/authorize/",
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
    return JSONResponse({"status": "ok", "service": "docsie-mcp", "version": "0.2.0"})


# ---------------------------------------------------------------------------
# Auth Middleware — extract Bearer token for tool handlers
# ---------------------------------------------------------------------------
class AuthMiddleware:
    """
    ASGI middleware that extracts the Bearer token from MCP requests
    and stores it in contextvars for tool handlers to forward to Docsie.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                auth.set_current_token(auth_header[7:])
            else:
                auth.set_current_token(None)

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# ASGI App
# ---------------------------------------------------------------------------
mcp_asgi = mcp.streamable_http_app()

app = Starlette(
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
