"""Lightweight service-layer response models.

These are the typed return values from core services — separate from the raw
wire models in infra/waha/wire_models.py and from the relay event models in
models/events.py.
"""

from __future__ import annotations

from pydantic import BaseModel


class ConnectResult(BaseModel):
    """Result of connect_whatsapp."""

    success: bool
    user_id: str | None = None
    code: str | None = None
    message: str
    error: str | None = None


class SyncResult(BaseModel):
    """Result of a chat-sync operation."""

    success: bool
    message: str
    total_synced: int = 0


class ScanResult(BaseModel):
    """Result of scan_unreplied_messages."""

    summary: str
    dm_count: int = 0
    group_count: int = 0


class ContactSearchResult(BaseModel):
    """A single match returned by find_contact_by_name."""

    w_chat_id: str
    chat_name: str
    description: str = ""
