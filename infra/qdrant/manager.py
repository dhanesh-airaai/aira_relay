"""Async Qdrant client manager — implements IVectorStore."""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Condition,
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Record,
    ScoredPoint,
    VectorParams,
)

from models.vector import VectorPoint

logger = logging.getLogger(__name__)


class QdrantManager:
    """Async Qdrant manager.

    Structurally satisfies ``IVectorStore`` — no explicit declaration needed.
    """

    def __init__(self) -> None:
        self._client: AsyncQdrantClient | None = None

    async def connect(self, url: str, api_key: str | None = None) -> None:
        self._client = AsyncQdrantClient(url=url, api_key=api_key)
        logger.info("Qdrant connected to %s", url)

    def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            raise RuntimeError("QdrantManager is not connected. Call connect() first.")
        return self._client

    # ------------------------------------------------------------------
    # Collection / index management
    # ------------------------------------------------------------------

    async def ensure_collection(
        self, name: str, size: int, distance: Distance = Distance.COSINE
    ) -> None:
        client = self._get_client()
        if not await client.collection_exists(name):
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
        client = self._get_client()
        try:
            await client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,  # type: ignore[arg-type]
            )
        except Exception as e:
            logger.debug(
                "Payload index %s.%s: %s (likely already exists)",
                collection_name,
                field_name,
                e,
            )

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    async def upsert(self, collection_name: str, points: list[VectorPoint]) -> None:
        if not points:
            return
        qdrant_points = [
            PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points
        ]
        await self._get_client().upsert(collection_name=collection_name, points=qdrant_points)

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filter(filters: list[dict[str, Any]]) -> Filter:
        conditions: list[Condition] = []
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
        qdrant_filter: Filter | None = self._build_filter(filters) if filters else None
        result = await self._get_client().query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            with_payload=with_payload,
            score_threshold=score_threshold,
            query_filter=qdrant_filter,
        )
        return result.points

    async def scroll(
        self,
        collection_name: str,
        filters: list[dict[str, Any]] | None = None,
        limit: int = 100,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> tuple[list[Record], Any]:
        qdrant_filter: Filter | None = self._build_filter(filters) if filters else None
        return await self._get_client().scroll(
            collection_name=collection_name,
            scroll_filter=qdrant_filter,
            limit=limit,
            with_payload=with_payload,
            with_vectors=with_vectors,
        )

    async def delete_by_filter(self, collection_name: str, filters: list[dict[str, Any]]) -> None:
        qdrant_filter = self._build_filter(filters)
        await self._get_client().delete(
            collection_name=collection_name,
            points_selector=FilterSelector(filter=qdrant_filter),
        )
