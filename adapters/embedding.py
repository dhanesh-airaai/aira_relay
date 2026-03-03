"""Provider-agnostic embedding adapter for the relay."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import Settings

logger = logging.getLogger(__name__)


class EmbeddingsClass:
    """Generates text embeddings via OpenAI or Azure OpenAI."""

    def __init__(self, settings: Settings) -> None:
        if settings.embedding_provider == "azure":
            from openai import AsyncAzureOpenAI

            self._client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_embedding_endpoint or settings.azure_openai_endpoint or "",
                api_key=settings.azure_embedding_api_key or settings.azure_openai_api_key or "",
                api_version=settings.azure_embedding_api_version,
            )
            self._model = settings.azure_embedding_deployment
        else:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=settings.openai_api_key or "")
            self._model = settings.embedding_model

        self._dimensions = settings.embedding_dimensions

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string and return the vector."""
        response = await self._client.embeddings.create(
            input=text,
            model=self._model,
            dimensions=self._dimensions,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single API call."""
        if not texts:
            return []
        response = await self._client.embeddings.create(
            input=texts,
            model=self._model,
            dimensions=self._dimensions,
        )
        # Sort by index to preserve order
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
