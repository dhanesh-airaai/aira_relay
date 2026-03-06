"""MongoDB async connection manager using motor."""

from __future__ import annotations

import logging
from typing import Any

import motor.motor_asyncio

from infra.mongodb.collections import INDEXES

logger = logging.getLogger(__name__)


class MongoManager:
    """Async MongoDB manager.

    Owns the motor client lifecycle (connect / disconnect) and exposes
    generic CRUD helpers that the repository implementations delegate to.
    """

    def __init__(self) -> None:
        self._client: motor.motor_asyncio.AsyncIOMotorClient | None = None  # type: ignore[type-arg]
        self._db: motor.motor_asyncio.AsyncIOMotorDatabase | None = None  # type: ignore[type-arg]

    async def connect(self, uri: str, db_name: str) -> None:
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self._db = self._client[db_name]
        logger.info("MongoDB connected to database '%s'", db_name)

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB disconnected")

    def get_collection(
        self, name: str
    ) -> motor.motor_asyncio.AsyncIOMotorCollection:  # type: ignore[type-arg]
        if self._db is None:
            raise RuntimeError("MongoManager is not connected. Call connect() first.")
        return self._db[name]

    async def ensure_indexes(self) -> None:
        if self._db is None:
            raise RuntimeError("MongoManager is not connected. Call connect() first.")
        for collection_name, index_specs in INDEXES.items():
            collection = self._db[collection_name]
            for spec in index_specs:
                key = spec["key"]
                kwargs: dict[str, Any] = {}
                if spec.get("unique"):
                    kwargs["unique"] = True
                try:
                    await collection.create_index(key, **kwargs)
                except Exception as e:
                    logger.warning(
                        "Index creation warning for %s %s: %s", collection_name, key, e
                    )
        logger.info("MongoDB indexes ensured")

    # ------------------------------------------------------------------
    # Generic CRUD
    # ------------------------------------------------------------------

    async def find_one(
        self, collection_name: str, filter_: dict[str, Any]
    ) -> dict[str, Any] | None:
        result = await self.get_collection(collection_name).find_one(filter_)
        return dict(result) if result else None

    async def find_many(
        self,
        collection_name: str,
        filter_: dict[str, Any],
        limit: int = 0,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        cursor = self.get_collection(collection_name).find(filter_)
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        return [dict(doc) async for doc in cursor]

    async def upsert_one(
        self,
        collection_name: str,
        filter_: dict[str, Any],
        update: dict[str, Any],
    ) -> None:
        await self.get_collection(collection_name).update_one(
            filter_, {"$set": update}, upsert=True
        )

    async def insert_one(self, collection_name: str, document: dict[str, Any]) -> str:
        result = await self.get_collection(collection_name).insert_one(document)
        return str(result.inserted_id)

    async def delete_one(self, collection_name: str, filter_: dict[str, Any]) -> int:
        result = await self.get_collection(collection_name).delete_one(filter_)
        return result.deleted_count
