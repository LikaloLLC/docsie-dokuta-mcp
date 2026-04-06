"""
Configuration loaded from environment variables.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Docsie instance
    docsie_base_url: str = "https://app.docsie.io"
    docsie_internal_url: str = "http://docsie-web:8080"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    model_config = {"env_prefix": "MCP_", "env_file": ".env"}


settings = Settings()
