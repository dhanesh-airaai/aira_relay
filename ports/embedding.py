"""IEmbeddingAdapter — abstract contract for text embedding."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IEmbeddingAdapter(Protocol):
    async def embed_text(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
