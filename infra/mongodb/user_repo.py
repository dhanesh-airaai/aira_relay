"""MongoDB implementation of IUserRepo."""

from __future__ import annotations

from typing import Any

from infra.mongodb.collections import USERS
from infra.mongodb.manager import MongoManager


class MongoUserRepo:
    """Implements ports.repositories.IUserRepo against the 'users' collection."""

    def __init__(self, mongo: MongoManager) -> None:
        self._mongo = mongo

    async def find_by_token(self, token: str) -> dict[str, Any] | None:
        return await self._mongo.find_one(USERS, {"phone_number_token": token})

    async def insert(self, document: dict[str, Any]) -> str:
        return await self._mongo.insert_one(USERS, document)
