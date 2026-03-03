"""Webhook processing logic — resolves chat identifiers, checks moderation, stores messages."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from db.mongodb.collections import WHATSAPP_CHATS
from webhook.models import IncomingMessagePayload, SessionStatusPayload

if TYPE_CHECKING:
    from adapters.waha import WahaClient
    from agents.tooling.services.waha.service import WahaService
    from db.mongodb.manager import MongoManager

logger = logging.getLogger(__name__)

# Keep strong references to background tasks to prevent GC
_background_tasks: set[asyncio.Task[None]] = set()


class WebhookProcessor:
    """Processes raw WAHA webhook message events."""

    def __init__(
        self,
        client: WahaClient,
        mongo: MongoManager,
        waha_service: WahaService | None = None,
    ) -> None:
        self._client = client
        self._mongo = mongo
        self._waha_service = waha_service

    async def process_message_event(
        self,
        session: str,
        payload: IncomingMessagePayload,
    ) -> dict[str, Any] | None:
        """Parse, validate and enrich an incoming message event.

        Returns a processed event dict ready for the notification queue,
        or None if the message should be discarded.
        """
        # Never process outbound messages
        if payload.from_me:
            return None

        # Resolve LID → phone JID when needed
        chat_id = payload.from_
        if "@lid" in chat_id:
            try:
                resp = await self._client.get_chat_id_by_lids(
                    session=session,
                    lid=chat_id.split("@")[0],
                )
                chat_id = resp.pn
            except Exception as exc:
                logger.warning("LID resolution failed for %s: %s", chat_id, exc)
                return None

        # Resolve group-sender LID (participant field)
        sender_jid = payload.participant or chat_id
        if "@lid" in sender_jid:
            try:
                resp = await self._client.get_chat_id_by_lids(
                    session=session,
                    lid=sender_jid.split("@")[0],
                )
                sender_jid = resp.pn
            except Exception:
                sender_jid = chat_id  # fall back to chat id

        sender_phone = sender_jid.split("@")[0]

        # Look up the chat document in MongoDB (by w_chat_id or w_lid)
        chat_doc = await self._mongo.find_one(
            WHATSAPP_CHATS, {"w_chat_id": chat_id}
        )
        if not chat_doc:
            chat_doc = await self._mongo.find_one(
                WHATSAPP_CHATS, {"w_lid": payload.from_}
            )

        if not chat_doc or not chat_doc.get("moderation_status"):
            return None

        user_id = str(chat_doc.get("user_id", ""))
        chat_name = chat_doc.get("chat_name", "")
        chat_type = "group" if chat_id.endswith("@g.us") else "dm"

        # Extract media metadata (url + mimetype) when present
        media_url = payload.media.url if payload.has_media and payload.media else ""
        media_mimetype = payload.media.mimetype if payload.has_media and payload.media else ""

        return {
            "event": "message",
            "session": session,
            "chat_id": chat_id,
            "chat_name": chat_name,
            "chat_type": chat_type,
            "user_id": user_id,
            "sender_phone": sender_phone,
            "body": payload.body or "",
            "timestamp": payload.timestamp,
            "message_id": payload.id,
            "has_media": payload.has_media,
            "media_url": media_url,
            "media_mimetype": media_mimetype,
        }

    async def handle_session_status(
        self,
        session: str,
        payload: SessionStatusPayload,
        event_timestamp: int | None = None,
    ) -> dict[str, Any] | None:
        """Handle and normalize a WAHA session.status webhook event."""
        if payload.status in {"FAILED", "STOPPED"}:
            logger.warning("WAHA session %s changed to %s", session, payload.status)
        else:
            logger.info("WAHA session %s changed to %s", session, payload.status)

        # When session becomes active, trigger a full chat sync
        if payload.status == "WORKING" and self._waha_service is not None:
            task: asyncio.Task[None] = asyncio.create_task(
                self._run_session_working_pipeline(session),
                name=f"session_working_{session}",
            )
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

        timeline = [item.model_dump() for item in payload.statuses] if payload.statuses else []
        effective_timestamp = timeline[-1]["timestamp"] if timeline else event_timestamp

        return {
            "event": "session.status",
            "session": session,
            "status": payload.status,
            "name": payload.name,
            "timestamp": effective_timestamp,
            "statuses": timeline,
        }

    # ------------------------------------------------------------------
    # Session WORKING pipeline
    # ------------------------------------------------------------------

    async def _run_session_working_pipeline(self, session: str) -> None:
        """Background task: sync all chats into MongoDB."""
        logger.info("Session WORKING: starting chat sync for %s", session)
        try:
            total = await self._waha_service._sync_chats_once(  # type: ignore[union-attr]
                session=session, user_id=session
            )
            logger.info("Synced %d chats for session %s", total, session)
        except Exception:
            logger.exception("Chat sync failed for session %s", session)
