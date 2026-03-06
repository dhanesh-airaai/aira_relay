"""Typed relay event models — replaces dict[str, Any] event payloads throughout."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from models.message import ContentBlock


class IncomingMessageEvent(BaseModel):
    """Emitted when WAHA delivers an inbound WhatsApp message."""

    event: Literal["message"] = "message"
    session: str
    chat_id: str
    chat_name: str = ""
    chat_type: Literal["dm", "group"] = "dm"
    user_id: str = ""
    sender_phone: str = ""
    body: str = ""
    timestamp: int = 0
    message_id: str = ""
    has_media: bool = False
    media_url: str = ""
    media_mimetype: str = ""
    content: list[ContentBlock] = []


class SessionStatusEvent(BaseModel):
    """Emitted when a WAHA session changes state."""

    event: Literal["session.status"] = "session.status"
    session: str
    status: str
    name: str = ""
    timestamp: int | None = None
    statuses: list[dict[str, Any]] = []


class SyncChatsEvent(BaseModel):
    """Emitted when a background chat-sync job completes."""

    event: Literal["sync_chats"] = "sync_chats"
    success: bool
    message: str = ""
    total_synced: int = 0
    session: str = ""
    descriptions: dict[str, str] = {}


# Discriminated union of all relay events
RelayEvent = IncomingMessageEvent | SessionStatusEvent | SyncChatsEvent
