"""MongoDB implementation of IStateRepo."""

from __future__ import annotations

from typing import Any

from infra.mongodb.collections import USER_STATE
from infra.mongodb.manager import MongoManager


class MongoStateRepo:
    """Implements ports.repositories.IStateRepo against the 'user_state' collection."""

    def __init__(self, mongo: MongoManager) -> None:
        self._mongo = mongo

    async def find_by_user_id(self, user_id: str) -> dict[str, Any] | None:
        return await self._mongo.find_one(USER_STATE, {"user_id": user_id})

    async def upsert(self, user_id: str, update: dict[str, Any]) -> None:
        await self._mongo.upsert_one(
            USER_STATE,
            {"user_id": user_id},
            {"user_id": user_id, **update},
        )
