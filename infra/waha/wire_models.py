"""WAHA-specific wire models — everything the WAHA HTTP API sends or receives.

Merged from:
  - models/waha/webhook.py   (LID, contact, group models)
  - webhook/models.py        (incoming webhook event models)
  - models/waha/entities.py  (ChatItem, FileType used by the client)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# LID / contact resolution models
# ---------------------------------------------------------------------------


class ChatIdByLidResponse(BaseModel):
    """Maps a LID (local identifier) to a phone JID."""

    lid: str
    pn: str  # phone JID, e.g. "919876543210@c.us"


class ContactDetails(BaseModel):
    """Detailed information about a single WhatsApp contact."""

    id: str
    number: str | None = None
    name: str | None = None
    pushname: str | None = None
    short_name: str | None = None
    is_me: bool | None = None
    is_group: bool | None = None
    is_wa_contact: bool | None = None
    is_my_contact: bool | None = None
    is_blocked: bool | None = None

    model_config = {"populate_by_name": True}


class GroupParticipant(BaseModel):
    """A participant entry inside a WhatsApp group."""

    jid: str | None = None
    phone_number: str | None = None
    lid: str | None = None
    is_admin: bool | None = None
    is_super_admin: bool | None = None
    display_name: str | None = None
    error: str | None = None

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Chat-list entity models
# ---------------------------------------------------------------------------


class FileType(BaseModel):
    """Generic file metadata for WAHA media messages."""

    mimetype: str | None = None
    filename: str | None = None
    url: str | None = None
    data: str | None = None  # base64 encoded


class ChatItem(BaseModel):
    """A chat entry returned by the list-chats endpoint."""

    id: str
    name: str | None = None
    conversation_timestamp: int | None = Field(None, alias="conversationTimestamp")
    unread_count: int | None = Field(None, alias="unreadCount")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Incoming webhook event models
# ---------------------------------------------------------------------------


class WahaEventType(StrEnum):
    """WAHA webhook event types handled by the relay."""

    MESSAGE = "message"
    SESSION_STATUS = "session.status"


class WahaMedia(BaseModel):
    """Media attachment metadata from a WAHA message."""

    url: str
    mimetype: str


class IncomingMessagePayload(BaseModel):
    """Payload for WAHA 'message' events."""

    id: str
    from_: str = Field(alias="from")
    to: str | None = None
    body: str | None = None
    timestamp: int
    from_me: bool = Field(alias="fromMe")
    has_media: bool = Field(alias="hasMedia", default=False)
    media: WahaMedia | None = None
    participant: str | None = None  # sender JID inside a group

    model_config = {"populate_by_name": True, "extra": "ignore"}


class SessionStatusItem(BaseModel):
    """A single WAHA session status timeline entry."""

    status: Literal["STOPPED", "STARTING", "SCAN_QR_CODE", "WORKING", "FAILED"]
    timestamp: int

    model_config = {"populate_by_name": True, "extra": "ignore"}


class SessionStatusPayload(BaseModel):
    """Payload for WAHA 'session.status' events."""

    status: Literal["STOPPED", "STARTING", "SCAN_QR_CODE", "WORKING", "FAILED"]
    name: str
    statuses: list[SessionStatusItem] | None = None

    model_config = {"populate_by_name": True, "extra": "ignore"}


WahaWebhookPayload = IncomingMessagePayload | SessionStatusPayload | dict[str, Any]


class WahaWebhookEvent(BaseModel):
    """Top-level WAHA webhook payload — all event types."""

    id: str
    timestamp: int
    event: str
    session: str
    payload: WahaWebhookPayload = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _parse_payload_by_event(cls, data: Any) -> Any:
        """Parse payload into the correct typed model based on the event field."""
        if not isinstance(data, dict):
            return data
        event_type = data.get("event")
        raw_payload = data.get("payload")
        if not isinstance(raw_payload, dict):
            return data
        try:
            if event_type == WahaEventType.MESSAGE:
                data = {**data, "payload": IncomingMessagePayload.model_validate(raw_payload)}
            elif event_type == WahaEventType.SESSION_STATUS:
                data = {**data, "payload": SessionStatusPayload.model_validate(raw_payload)}
        except Exception:
            pass  # leave payload as raw dict — webhook handler will ignore unknown types
        return data
