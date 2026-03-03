"""WAHA MCP tool input argument models.

All models replace aira-api's UserModels.User with flat
session / user_id / phone_number parameters.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from models.waha.entities import ChatType


class SendTextMessageArgs(BaseModel):
    """Arguments for send_text_message tool."""

    chat_id: str = Field(..., description="WhatsApp chat ID of the recipient (contact or group).")
    text: str = Field(..., description="Text to send. Supports WhatsApp formatting: *bold*, _italic_, ~strikethrough~.")
    session: str = Field(..., description="WAHA session name (usually the connected phone number).")
    user_id: str = Field(..., description="Relay user identifier.")
    reply_to: str | None = Field(None, description="Message ID to reply to.")
    mentions: list[str] | None = Field(None, description="List of phone JIDs to mention (e.g. ['919876543210@c.us']).")
    link_preview: bool = Field(True, description="Generate a link preview if the message contains a URL.")
    link_preview_high_quality: bool = Field(False, description="Use high-quality link preview.")


class SendImageMessageArgs(BaseModel):
    """Arguments for send_image_message tool."""

    chat_id: str
    session: str
    user_id: str
    chat_type: ChatType = ChatType.CONTACT
    caption: str | None = None
    reply_to: str | None = None
    image_url: str | None = None
    image_base64: str | None = None
    image_mimetype: str = "image/jpeg"
    image_filename: str = "image.jpg"


class SendFileMessageArgs(BaseModel):
    """Arguments for send_file_message tool."""

    chat_id: str
    session: str
    user_id: str
    chat_type: ChatType = ChatType.CONTACT
    caption: str | None = None
    reply_to: str | None = None
    file_url: str | None = None
    file_base64: str | None = None
    file_mimetype: str = "application/octet-stream"
    file_filename: str = "file"


class SendVoiceMessageArgs(BaseModel):
    """Arguments for send_voice_message tool."""

    chat_id: str
    session: str
    user_id: str
    chat_type: ChatType = ChatType.CONTACT
    voice_url: str | None = None
    voice_base64: str | None = None
    reply_to: str | None = None


class SendVideoMessageArgs(BaseModel):
    """Arguments for send_video_message tool."""

    chat_id: str
    session: str
    user_id: str
    chat_type: ChatType = ChatType.CONTACT
    caption: str | None = None
    video_url: str | None = None
    video_base64: str | None = None
    reply_to: str | None = None


class DeleteMessageArgs(BaseModel):
    """Arguments for delete_message tool."""

    chat_id: str
    message_id: str
    session: str
    user_id: str
    chat_type: ChatType = ChatType.CONTACT


class EditMessageArgs(BaseModel):
    """Arguments for edit_message tool."""

    chat_id: str
    message_id: str
    new_text: str
    session: str
    user_id: str
    chat_type: ChatType = ChatType.CONTACT
    link_preview: bool = True


class GetMessagesArgs(BaseModel):
    """Arguments for get_messages tool."""

    chat_id: str
    session: str
    user_id: str
    chat_type: ChatType = ChatType.CONTACT
    limit: int = 100
    offset: int | None = None
    from_timestamp: int | None = None
    to_timestamp: int | None = None
    download_media: bool = False
    query: str | None = Field(None, description="Optional query to focus the LLM summary on a specific topic.")


class GetAllContactsArgs(BaseModel):
    """Arguments for get_all_contacts tool."""

    session: str
    user_id: str
    limit: int | None = None
    offset: int | None = None
    sort_by: str | None = None
    sort_order: str | None = None


class GetContactDetailsArgs(BaseModel):
    """Arguments for get_contact_details tool."""

    contact_id: str = Field(..., description="WhatsApp contact ID (e.g. '919876543210@c.us').")
    session: str
    user_id: str


class GetGroupArgs(BaseModel):
    """Arguments for get_group tool."""

    group_id: str = Field(..., description="WhatsApp group ID (e.g. '123456789@g.us').")
    session: str
    user_id: str


class FindContactByNameArgs(BaseModel):
    """Arguments for find_contact_by_name tool."""

    query: str = Field(..., description="Contact name to search for. Supports partial matching.")
    session: str
    user_id: str


class ScanUnrepliedMessagesArgs(BaseModel):
    """Arguments for scan_unreplied_messages tool."""

    session: str = Field(..., description="WAHA session name (phone number of the connected WhatsApp account).")
    user_id: str
    phone_number: str = Field(..., description="Phone number of the connected WhatsApp account (with country code, no +).")
