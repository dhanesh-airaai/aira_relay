"""Chat domain models."""

from __future__ import annotations

from enum import Enum


class ChatType(str, Enum):
    """Short identifier used in tool arguments ('c' = contact, 'g' = group)."""

    CONTACT = "c"
    GROUP = "g"


class WhatsappChatType(str, Enum):
    """Full chat category stored in MongoDB."""

    CHAT = "chat"
    GROUP = "group"
