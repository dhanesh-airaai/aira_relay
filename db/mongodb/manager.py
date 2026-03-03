"""MongoDB async manager for the relay."""

from __future__ import annotations

import logging
from typing import Any

import motor.motor_asyncio

from db.mongodb.collections import INDEXES

logger = logging.getLogger(__name__)


class MongoManager:
    """Async MongoDB manager using motor."""

    def __init__(self) -> None:
        self._client: motor.motor_asyncio.AsyncIOMotorClient | None = None  # type: ignore[type-arg]
        self._db: motor.motor_asyncio.AsyncIOMotorDatabase | None = None  # type: ignore[type-arg]

    async def connect(self, uri: str, db_name: str) -> None:
        """Initialize the motor client and select the database."""
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self._db = self._client[db_name]
        logger.info("MongoDB connected to database '%s'", db_name)

    async def disconnect(self) -> None:
        """Close the motor client."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB disconnected")

    def get_collection(self, name: str) -> motor.motor_asyncio.AsyncIOMotorCollection:  # type: ignore[type-arg]
        """Return a collection by name. Raises RuntimeError if not connected."""
        if self._db is None:
            msg = "MongoManager is not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._db[name]

    async def ensure_indexes(self) -> None:
        """Idempotently create all defined collection indexes."""
        if self._db is None:
            msg = "MongoManager is not connected. Call connect() first."
            raise RuntimeError(msg)
        for collection_name, index_specs in INDEXES.items():
            collection = self._db[collection_name]
            for spec in index_specs:
                key = spec["key"]
                kwargs: dict[str, Any] = {}
                if spec.get("unique"):
                    kwargs["unique"] = True
                try:
                    await collection.create_index(key, **kwargs)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Index creation warning for %s %s: %s", collection_name, key, e)
        logger.info("MongoDB indexes ensured")

    async def find_one(self, collection_name: str, filter_: dict[str, Any]) -> dict[str, Any] | None:
        """Find a single document matching the filter."""
        collection = self.get_collection(collection_name)
        result = await collection.find_one(filter_)
        return dict(result) if result else None

    async def find_many(
        self,
        collection_name: str,
        filter_: dict[str, Any],
        limit: int = 0,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        """Find multiple documents matching the filter."""
        collection = self.get_collection(collection_name)
        cursor = collection.find(filter_)
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
        """Upsert a document — insert if missing, update if found."""
        collection = self.get_collection(collection_name)
        await collection.update_one(filter_, {"$set": update}, upsert=True)

    async def insert_one(self, collection_name: str, document: dict[str, Any]) -> str:
        """Insert a document and return the inserted _id as string."""
        collection = self.get_collection(collection_name)
        result = await collection.insert_one(document)
        return str(result.inserted_id)

    async def delete_one(self, collection_name: str, filter_: dict[str, Any]) -> int:
        """Delete a single document matching the filter. Returns deleted count."""
        collection = self.get_collection(collection_name)
        result = await collection.delete_one(filter_)
        return result.deleted_count


# Module-level singleton
mongo = MongoManager()
