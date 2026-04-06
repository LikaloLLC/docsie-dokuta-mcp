"""
Configuration loaded from environment variables.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Docsie Django monolith (for token validation and credit deduction)
    docsie_base_url: str = "https://app.docsie.io"
    docsie_internal_url: str = "http://docsie-web:8080"

    # Dokuta video analysis service
    dokuta_api_url: str = "https://app.videodokuta.com/api/v1"
    dokuta_api_key: str = ""

    # Internal API key (shared secret between MCP server and Django)
    mcp_internal_api_key: str = ""

    # OAuth2 — Docsie's OAuth provider handles auth, we just proxy metadata
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""

    # Free tier: videos up to this many seconds are free
    free_tier_max_seconds: int = 600  # 10 minutes

    # Rate limiting
    free_tier_hourly_limit: int = 5
    authenticated_hourly_limit: int = 20

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    model_config = {"env_prefix": "MCP_", "env_file": ".env"}


settings = Settings()
