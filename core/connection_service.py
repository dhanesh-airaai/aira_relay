"""ConnectionService — WhatsApp session lifecycle (connect / pairing code)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from models.exceptions import WhatsAppError
from models.responses import ConnectResult

if TYPE_CHECKING:
    from core.user_service import UserService
    from ports.messaging import IMessagingPort

logger = logging.getLogger(__name__)


class ConnectionService:
    """Handles WhatsApp session creation and phone-number pairing code flow."""

    def __init__(
        self,
        messaging: IMessagingPort,
        user_service: UserService,
    ) -> None:
        self._messaging = messaging
        self._user_service = user_service

    async def connect_whatsapp(self, *, phone_number: str) -> ConnectResult:
        """Request a WhatsApp pairing code for *phone_number*.

        Steps:
          1. Get or create a relay User record.
          2. Delete any stale WAHA session.
          3. Create + start a fresh session.
          4. Poll until SCAN_QR_CODE status (max 3 × 2 s).
          5. Request auth code and return it.
        """
        user = await self._user_service.get_or_create(phone_number)

        try:
            with contextlib.suppress(Exception):
                await self._messaging.delete_session(phone_number)

            created = await self._messaging.create_session(name=phone_number)
            session_name: str = created["name"]

            start_result = await self._messaging.start_session(session_name)
            if not start_result:
                return ConnectResult(
                    success=False,
                    user_id=user.id,
                    code=None,
                    message="Failed to start WhatsApp session.",
                    error="Something went wrong. Please try again after some time.",
                )

            session_details = await self._messaging.get_session(session_name)
            for _ in range(3):
                if session_details.get("status") == "SCAN_QR_CODE":
                    break
                await asyncio.sleep(2)
                session_details = await self._messaging.get_session(session_name)
            else:
                return ConnectResult(
                    success=False,
                    user_id=user.id,
                    code=None,
                    message="WhatsApp session is not ready for QR code scanning.",
                    error=(
                        f"Session status: {session_details.get('status')}."
                        " Please try again after some time."
                    ),
                )

            auth_resp = await self._messaging.request_auth_code(
                session=session_name,
                phone_number=phone_number,
            )
            code: str = auth_resp["code"]

            return ConnectResult(
                success=True,
                user_id=user.id,
                code=code,
                message=f"Verification code sent to {phone_number} WhatsApp number.",
                error=None,
            )

        except WhatsAppError as exc:
            # Covers WhatsAppAuthError, WhatsAppNetworkError, and any other WAHA error
            error = str(exc)
            logger.error("connect_whatsapp error for %s: %s", phone_number, error)
            return ConnectResult(
                success=False,
                user_id=user.id,
                code=None,
                message="Unable to connect WhatsApp at this time.",
                error=error,
            )
