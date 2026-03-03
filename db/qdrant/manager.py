"""Async Qdrant client manager for the relay."""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Record,
    ScoredPoint,
    VectorParams,
)

logger = logging.getLogger(__name__)


class QdrantManager:
    """Async Qdrant manager using qdrant-client."""

    def __init__(self) -> None:
        self._client: AsyncQdrantClient | None = None

    async def connect(self, url: str, api_key: str | None = None) -> None:
        """Initialise the async Qdrant client."""
        self._client = AsyncQdrantClient(url=url, api_key=api_key)
        logger.info("Qdrant connected to %s", url)

    def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            msg = "QdrantManager is not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._client

    # ------------------------------------------------------------------
    # Collection / index management
    # ------------------------------------------------------------------

    async def ensure_collection(self, name: str, size: int, distance: Distance = Distance.COSINE) -> None:
        """Create a collection if it does not already exist (idempotent)."""
        client = self._get_client()
        exists = await client.collection_exists(name)
        if not exists:
            await client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=size, distance=distance),
            )
            logger.info("Qdrant collection created: %s (dim=%d)", name, size)
        else:
            logger.debug("Qdrant collection already exists: %s", name)

    async def ensure_payload_index(
        self,
        collection_name: str,
        field_name: str,
        field_schema: PayloadSchemaType | str,
    ) -> None:
        """Create a payload index if it does not already exist (idempotent)."""
        client = self._get_client()
        try:
            await client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,  # type: ignore[arg-type]
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("Payload index %s.%s: %s (likely already exists)", collection_name, field_name, e)

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    async def upsert(self, collection_name: str, points: list[PointStruct]) -> None:
        """Batch upsert points into a collection."""
        if not points:
            return
        client = self._get_client()
        await client.upsert(collection_name=collection_name, points=points)

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filter(filters: list[dict[str, Any]]) -> Filter:
        """Convert a list of {key, value} or {key, any} dicts to a Qdrant Filter.

        Supported formats:
            {"key": "user_id", "value": "abc"}   → MatchValue
            {"key": "source", "any": ["a", "b"]} → MatchAny
        """
        conditions: list[FieldCondition] = []
        for f in filters:
            key = f["key"]
            if "any" in f:
                conditions.append(FieldCondition(key=key, match=MatchAny(any=f["any"])))
            else:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=f["value"])))
        return Filter(must=conditions)

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        with_payload: bool = True,
        score_threshold: float | None = None,
        filters: list[dict[str, Any]] | None = None,
    ) -> list[ScoredPoint]:
        """Semantic similarity search with optional payload filtering."""
        client = self._get_client()
        qdrant_filter: Filter | None = self._build_filter(filters) if filters else None
        return await client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            with_payload=with_payload,
            score_threshold=score_threshold,
            query_filter=qdrant_filter,
        )

    async def scroll(
        self,
        collection_name: str,
        scroll_filter: Filter | None = None,
        limit: int = 100,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> tuple[list[Record], Any]:
        """Scroll through points matching a filter without vector scoring."""
        client = self._get_client()
        return await client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=with_payload,
            with_vectors=with_vectors,
        )

    async def delete_by_filter(self, collection_name: str, filters: list[dict[str, Any]]) -> None:
        """Delete points matching a filter."""
        from qdrant_client.models import FilterSelector

        client = self._get_client()
        qdrant_filter = self._build_filter(filters)
        await client.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(filter=qdrant_filter),
        )


# Module-level singleton
qdrant = QdrantManager()
