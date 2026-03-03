"""WAHA webhook response models — LID resolution, contacts, groups."""

from __future__ import annotations

from pydantic import BaseModel


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


class SyncChatsResponse(BaseModel):
    """Response model for WAHA chat sync operations."""

    success: bool = True
    message: str = "Chats synced successfully"
