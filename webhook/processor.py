"""WebhookProcessor — parses WAHA events and publishes typed RelayEvents."""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

from helpers.content_blocks import build_content_blocks
from infra.waha.wire_models import (
    IncomingMessagePayload,
    SessionStatusPayload,
)
from models.events import IncomingMessageEvent, SessionStatusEvent, SyncChatsEvent

if TYPE_CHECKING:
    from core.chat_service import ChatService
    from core.user_service import UserService
    from ports.event_bus import IEventBus
    from ports.llm import ILLMAdapter
    from ports.messaging import IMessagingPort
    from utils.concurrency import TaskRegistry

logger = logging.getLogger(__name__)


class WebhookProcessor:
    """Processes raw WAHA webhook events and dispatches typed RelayEvents."""

    def __init__(
        self,
        messaging: IMessagingPort,
        user_service: UserService,
        chat_service: ChatService,
        event_bus: IEventBus,
        task_registry: TaskRegistry,
        llm: ILLMAdapter | None = None,
    ) -> None:
        self._messaging = messaging
        self._user_service = user_service
        self._chat_service = chat_service
        self._event_bus = event_bus
        self._tasks = task_registry
        self._llm = llm

    # ------------------------------------------------------------------
    # Incoming message
    # ------------------------------------------------------------------

    async def process_message(
        self,
        session: str,
        payload: IncomingMessagePayload,
    ) -> None:
        """Enrich an incoming message and publish an IncomingMessageEvent."""
        if payload.from_me:
            return

        # Resolve LID → phone JID for the chat
        chat_id = payload.from_
        if "@lid" in chat_id:
            try:
                resp = await self._messaging.get_chat_id_by_lids(
                    session=session, lid=chat_id.split("@")[0]
                )
                chat_id = resp.pn
            except Exception as exc:
                logger.warning("LID resolution failed for %s: %s", chat_id, exc)
                return

        # Resolve group-sender LID
        sender_jid = payload.participant or chat_id
        if "@lid" in sender_jid:
            try:
                resp = await self._messaging.get_chat_id_by_lids(
                    session=session, lid=sender_jid.split("@")[0]
                )
                sender_jid = resp.pn
            except Exception:
                sender_jid = chat_id

        sender_phone = sender_jid.split("@")[0]

        # Ensure user record exists and look up (or create on demand) the chat
        user = await self._user_service.get_or_create(session)
        chat_doc = await self._chat_service.get_or_create_chat(
            session=session,
            chat_id=chat_id,
            w_lid=payload.from_,
            user_id=user.id,
            from_timestamp=payload.timestamp or 0,
        )
        if not chat_doc:
            return

        chat_name = chat_doc.get("chat_name", "")
        chat_type = "group" if chat_id.endswith("@g.us") else "dm"

        media_url = payload.media.url if payload.has_media and payload.media else ""
        media_mimetype = (
            payload.media.mimetype if payload.has_media and payload.media else ""
        )

        media_base64 = ""
        if media_url:
            try:
                mime_type, media_bytes = await self._messaging.download_media(media_url)
                # Use actual content-type from response (more reliable than payload field)
                media_mimetype = mime_type
                if mime_type.startswith("video/"):
                    pass  # skip — LLM doesn't support video
                else:
                    media_base64 = base64.b64encode(media_bytes).decode()
            except Exception:
                logger.warning("Failed to download media from %s", media_url)

        content = build_content_blocks(
            body=payload.body or "",
            has_media=payload.has_media,
            media_url=media_url,
            media_mimetype=media_mimetype,
        )

        event = IncomingMessageEvent(
            session=session,
            chat_id=chat_id,
            chat_name=chat_name,
            chat_type=chat_type,
            user_id=user.id,
            sender_phone=sender_phone,
            body=payload.body or "",
            timestamp=payload.timestamp,
            message_id=payload.id,
            has_media=payload.has_media,
            media_url=media_url,
            media_mimetype=media_mimetype,
            media_base64=media_base64,
            content=content,
        )
        await self._event_bus.publish(event)

    # ------------------------------------------------------------------
    # Session status
    # ------------------------------------------------------------------

    async def process_session_status(
        self,
        session: str,
        payload: SessionStatusPayload,
        event_timestamp: int | None = None,
    ) -> None:
        """Handle a WAHA session.status event and publish a SessionStatusEvent."""
        if payload.status in {"FAILED", "STOPPED"}:
            logger.warning("WAHA session %s → %s", session, payload.status)
        else:
            logger.info("WAHA session %s → %s", session, payload.status)

        timeline = (
            [item.model_dump() for item in payload.statuses] if payload.statuses else []
        )
        effective_ts = timeline[-1]["timestamp"] if timeline else event_timestamp

        event = SessionStatusEvent(
            session=session,
            status=payload.status,
            name=payload.name,
            timestamp=effective_ts,
            statuses=timeline,
        )
        await self._event_bus.publish(event)

        if payload.status == "WORKING":
            self._tasks.spawn(
                self._session_working_pipeline(session),
                name=f"session_working_{session}",
            )

    async def _session_working_pipeline(self, session: str) -> None:
        """Background: sync chats when a session reaches WORKING state."""
        logger.info("Session WORKING: starting chat sync for %s", session)
        try:
            user = await self._user_service.get_or_create(session)
            result = await self._chat_service.sync_chats(
                session=session, user_id=user.id
            )
            descriptions: dict = {}
            if self._llm:
                desc_result = await self._chat_service.generate_descriptions(
                    session=session, user_id=user.id, llm=self._llm, limit=50
                )
                descriptions = desc_result.get("descriptions", {})
            sync_event = SyncChatsEvent(
                success=result.success,
                message=result.message,
                total_synced=result.total_synced,
                session=session,
                descriptions=descriptions,
            )
            await self._event_bus.publish(sync_event)
            logger.info("Chat sync complete for session %s", session)
        except Exception:
            logger.exception("Chat sync failed for session %s", session)
