"""Webhook processing logic — resolves chat identifiers, checks moderation, stores messages."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from db.mongodb.collections import WHATSAPP_CHATS
from relay.notifications import push_incoming_event
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
        waha_service: WahaService,
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
        chat_doc = await self._mongo.find_one(WHATSAPP_CHATS, {"w_chat_id": chat_id})
        if not chat_doc:
            chat_doc = await self._mongo.find_one(WHATSAPP_CHATS, {"w_lid": payload.from_})

        if not chat_doc:
            chat_doc = await self._create_chat_on_demand(
                session=session, payload=payload, chat_id=chat_id
            )
            if not chat_doc:
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

    async def _create_chat_on_demand(
        self,
        session: str,
        payload: IncomingMessagePayload,
        chat_id: str,
    ) -> dict[str, Any] | None:
        """Fetch chat metadata from WAHA and persist in MongoDB when a first message arrives."""
        try:
            user = await self._waha_service.get_or_create_user(session)
            user_id = user.id

            if chat_id.endswith("@g.us"):
                try:
                    group_data = await self._client.get_group(session=session, group_id=chat_id)
                    chat_name = group_data.get("name") or chat_id.split("@")[0]
                except Exception:
                    chat_name = chat_id.split("@")[0]
                chat_type = "group"
                w_lid = chat_id
            elif chat_id.endswith("@c.us"):
                try:
                    contact = await self._client.get_contact_details(
                        contact_id=chat_id, session=session
                    )
                    chat_name = contact.name or contact.pushname or chat_id.split("@")[0]
                except Exception:
                    chat_name = chat_id.split("@")[0]
                chat_type = "chat"
                w_lid = payload.from_
            else:
                return None

            doc: dict[str, Any] = {
                "user_id": user_id,
                "w_chat_id": chat_id,
                "w_lid": w_lid,
                "chat_name": chat_name,
                "type": chat_type,
                "conversation_timestamp": payload.timestamp or 0,
            }
            await self._mongo.upsert_one(
                WHATSAPP_CHATS,
                {"user_id": user_id, "w_chat_id": chat_id},
                doc,
            )
            await self._waha_service.add_chat_to_phonetic_index(chat_id, chat_name, user_id)
            logger.info("Created chat on demand: %s (%s) for user %s", chat_name, chat_id, user_id)
            return doc
        except Exception:
            logger.exception("Failed to create chat on demand for %s", chat_id)
            return None

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
        """Background task: sync all chats into MongoDB and push notification."""
        logger.info("Session WORKING: starting chat sync for %s", session)
        try:
            user = await self._waha_service.get_or_create_user(session)
            result = await self._waha_service.sync_chats(session=session, user_id=user.id)
            await push_incoming_event(
                {
                    "event": "sync_chats",
                    **result.model_dump(),
                },
                hook_type="agent",
            )
            logger.info("Chat sync complete for session %s", session)
        except Exception:
            logger.exception("Chat sync failed for session %s", session)
