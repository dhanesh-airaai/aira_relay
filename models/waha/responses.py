"""WAHA MCP tool output / response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WahaMessageResponse(BaseModel):
    """Generic response for message-send operations."""

    success: bool
    message_id: str | None = None
    data: dict[str, Any] = {}


# Alias used by send_text_message for clarity
SendTextMessageResponse = WahaMessageResponse


class WahaDataResponse(BaseModel):
    """Generic response carrying a single data payload."""

    success: bool
    data: Any = None


class WahaListResponse(BaseModel):
    """Generic response carrying a list payload."""

    success: bool
    data: list[Any] = []


class ContactSearchResult(BaseModel):
    """A single contact match returned by find_contact_by_name."""

    w_chat_id: str
    chat_name: str
    description: str = ""


class FindContactByNameResponse(BaseModel):
    """Response for find_contact_by_name tool."""

    success: bool
    contacts: list[ContactSearchResult | dict[str, Any]] = []
    message: str = ""


class MessagesSummaryResponse(BaseModel):
    """Response for get_messages tool — LLM-generated conversation summary."""

    summary: str


class ScanUnrepliedResponse(BaseModel):
    """Response for scan_unreplied_messages tool — LLM summary of pending messages."""

    summary: str
    dm_count: int = 0
    group_count: int = 0


class SyncChatsStartResponse(BaseModel):
    """Response for starting an async chat sync job."""

    success: bool
    message: str
    job_id: str | None = None


class SyncChatsJobResult(BaseModel):
    """Final result payload of a chat sync job."""

    success: bool
    message: str
    total_synced: int = 0
