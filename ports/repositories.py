"""Repository port interfaces — abstract contracts for all DB access."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IUserRepo(Protocol):
    async def find_by_token(self, token: str) -> dict[str, Any] | None: ...

    async def insert(self, document: dict[str, Any]) -> str: ...


@runtime_checkable
class IChatRepo(Protocol):
    async def find_by_chat_id(self, chat_id: str) -> dict[str, Any] | None: ...

    async def find_by_lid(self, lid: str) -> dict[str, Any] | None: ...

    async def find_many(
        self,
        filter_: dict[str, Any],
        limit: int = 0,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]: ...

    async def upsert(self, filter_: dict[str, Any], document: dict[str, Any]) -> None: ...


@runtime_checkable
class IContactProfileRepo(Protocol):
    async def find_by_contact_id(self, contact_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class IStateRepo(Protocol):
    async def find_by_user_id(self, user_id: str) -> dict[str, Any] | None: ...

    async def upsert(self, user_id: str, update: dict[str, Any]) -> None: ...
