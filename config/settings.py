"""Relay-native settings module."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    # WAHA
    waha_base_url: str = "http://localhost:3000"
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

    # Server ports
    mcp_port: int = 8000
    webhook_port: int = 8001

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
