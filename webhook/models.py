"""Pydantic models for incoming WAHA webhook events."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class WahaEventType(StrEnum):
    """WAHA webhook event types handled by relay."""

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
