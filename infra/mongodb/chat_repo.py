"""MongoDB implementations of IChatRepo and IContactProfileRepo."""

from __future__ import annotations

from typing import Any

from infra.mongodb.collections import CONTACT_PROFILES, WHATSAPP_CHATS
from infra.mongodb.manager import MongoManager


class MongoChatRepo:
    """Implements ports.repositories.IChatRepo against 'whatsapp_chats'."""

    def __init__(self, mongo: MongoManager) -> None:
        self._mongo = mongo

    async def find_by_chat_id(self, chat_id: str) -> dict[str, Any] | None:
        return await self._mongo.find_one(WHATSAPP_CHATS, {"w_chat_id": chat_id})

    async def find_by_lid(self, lid: str) -> dict[str, Any] | None:
        return await self._mongo.find_one(WHATSAPP_CHATS, {"w_lid": lid})

    async def find_many(
        self,
        filter_: dict[str, Any],
        limit: int = 0,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._mongo.find_many(WHATSAPP_CHATS, filter_, limit=limit, sort=sort)

    async def upsert(self, filter_: dict[str, Any], document: dict[str, Any]) -> None:
        await self._mongo.upsert_one(WHATSAPP_CHATS, filter_, document)


class MongoContactProfileRepo:
    """Implements ports.repositories.IContactProfileRepo against 'contact_profiles'."""

    def __init__(self, mongo: MongoManager) -> None:
        self._mongo = mongo

    async def find_by_contact_id(self, contact_id: str) -> dict[str, Any] | None:
        return await self._mongo.find_one(CONTACT_PROFILES, {"contact_id": contact_id})
