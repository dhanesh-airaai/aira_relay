"""Local embedding adapter using FastEmbed — no API key required."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class FastEmbedAdapter:
    """Generates text embeddings locally via FastEmbed (no external API calls).

    Uses BAAI/bge-small-en-v1.5 by default (384 dimensions).
    The model is downloaded on first use and cached locally.
    Structurally satisfies IEmbeddingAdapter (embed_text / embed_batch).
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)
        logger.info("FastEmbed loaded model: %s", model_name)

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single string and return the vector."""
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, partial(self._embed_sync, [text])
        )
        return result[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple strings in a single call (order preserved)."""
        if not texts:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self._embed_sync, texts)
        )

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]
