"""Relay-native settings module."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_DIR = Path(__file__).resolve().parents[1]
_ENV_FILE = _ROOT_DIR / ".env"

class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    # Security
    token_secret: str = ""
    """Base64-encoded secret used for HMAC-SHA256 phone number tokenization.
    Generate with: python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
    """

    # WAHA
    waha_base_url: str = ""
    waha_api_key: str = ""
    waha_webhook_secret: str | None = None

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "aira_relay"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None

    # Embeddings (shared for phonetic search)
    embedding_provider: Literal["openai", "azure"] = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    # Azure-specific embedding settings (if different from LLM)
    azure_embedding_endpoint: str | None = None
    azure_embedding_api_key: str | None = None
    azure_embedding_api_version: str = "2024-02-01"
    azure_embedding_deployment: str = "text-embedding-3-small"

    # Phonetic search concurrency
    contacts_embed_concurrency: int = 5
    contacts_search_concurrency: int = 5

    # OpenAI credentials (used by embeddings; azure_openai_* are fallbacks for azure embedding provider)
    openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None

    # OpenClaw agent webhook (optional)
    # If set, incoming events are forwarded to OpenClaw instead of MCP sessions.
    openclaw_url: str | None = None          # e.g. http://127.0.0.1:18789
    openclaw_token: str | None = None        # Bearer token
    openclaw_agent_name: str = "MCP"         # name field in the hook payload
    openclaw_gateway_token: str | None = None

    # Server ports
    mcp_port: int = 8000
    webhook_port: int = 8001
    debugpy_port: int = 5678

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        extra="ignore",
    )


settings = Settings()
