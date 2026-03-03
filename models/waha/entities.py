"""WAHA entity models — chat, message, contact, session structures."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ChatType(str, Enum):
    """WhatsApp chat type identifier."""

    CONTACT = "c"
    GROUP = "g"


class WhatsappChatType(str, Enum):
    """WhatsApp chat category."""

    CHAT = "CHAT"
    GROUP = "GROUP"


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


class Chat(BaseModel):
    """Minimal chat reference used in sync requests."""

    chat_id: str
    type: WhatsappChatType = WhatsappChatType.CHAT
