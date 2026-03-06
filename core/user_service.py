"""UserService — user CRUD with HMAC-token-based lookup."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from models.user import User
from utils.crypto import tokenize

if TYPE_CHECKING:
    from ports.repositories import IUserRepo

logger = logging.getLogger(__name__)


class UserService:
    """Creates and retrieves Relay user accounts by phone number.

    Phone numbers are never stored in plaintext as lookup keys — only the
    HMAC-SHA256 token is used for queries (see utils.crypto.tokenize).
    """

    def __init__(self, user_repo: IUserRepo, token_secret: str) -> None:
        self._repo = user_repo
        self._token_secret = token_secret

    async def get_or_create(self, phone_number: str) -> User:
        """Return the existing user for *phone_number*, or create one."""
        token = tokenize(phone_number, self._token_secret)
        doc = await self._repo.find_by_token(token)
        if doc:
            return User(
                id=str(doc["_id"]),
                phone_number=doc["phone_number"],
                phone_number_token=doc["phone_number_token"],
                created_at=doc["created_at"],
            )

        now = datetime.now(UTC)
        user_id = await self._repo.insert(
            {
                "phone_number": phone_number,
                "phone_number_token": token,
                "created_at": now,
            }
        )
        return User(
            id=user_id,
            phone_number=phone_number,
            phone_number_token=token,
            created_at=now,
        )
