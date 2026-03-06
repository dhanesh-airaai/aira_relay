"""IVectorStore — abstract contract for the vector database."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from models.vector import VectorPoint


@runtime_checkable
class IVectorStore(Protocol):
    async def upsert(self, collection_name: str, points: list[VectorPoint]) -> None: ...

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        with_payload: bool = True,
        score_threshold: float | None = None,
        filters: list[dict[str, Any]] | None = None,
    ) -> list[Any]: ...

    async def scroll(
        self,
        collection_name: str,
        filters: list[dict[str, Any]] | None = None,
        limit: int = 100,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> tuple[list[Any], Any]: ...

    async def delete_by_filter(self, collection_name: str, filters: list[dict[str, Any]]) -> None: ...
