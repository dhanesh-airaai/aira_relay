"""WAHA MCP tool handlers — registers 12 core messaging/contact/group tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from services.waha.service import WahaService

from adapters.waha import WahaClient
from config.settings import settings
from db.mongodb.manager import mongo
from mcp.notifications import pop_incoming_event
from mcp.server.fastmcp import Context
from models.waha.args import (
    DeleteMessageArgs,
    EditMessageArgs,
    GetAllContactsArgs,
    GetContactDetailsArgs,
    GetGroupArgs,
    GetMessagesArgs,
    ScanUnrepliedMessagesArgs,
    SendFileMessageArgs,
    SendImageMessageArgs,
    SendTextMessageArgs,
    SendVideoMessageArgs,
    SendVoiceMessageArgs,
)
from models.waha.entities import ChatType

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Module-level service singleton — built once at import time
_waha_client = WahaClient(
    base_url=settings.waha_base_url,
    api_key=settings.waha_api_key,
    webhook_secret=settings.waha_webhook_secret,
)
_service = WahaService(
    client=_waha_client,
    mongo=mongo,
)


def register_waha_tools(mcp: FastMCP) -> None:
    """Register 12 core WAHA tools with a FastMCP server instance."""

    @mcp.tool()
    async def send_text_message(
        chat_id: str,
        text: str,
        session: str,
        user_id: str,
        reply_to: str | None = None,
        mentions: list[str] | None = None,
        link_preview: bool = True,
        link_preview_high_quality: bool = False,
    ) -> dict[str, Any]:
        """Send a plain text message via WhatsApp.

        USE WHEN: Need to send plain text to a contact or group.
        - chat_id: WhatsApp chat ID (phone@c.us or group@g.us).
        - text: Text content. Supports *bold*, _italic_, ~strikethrough~.
        - session: WAHA session name (connected phone number).
        - user_id: Relay user identifier.
        - reply_to: Optional message ID to reply to.
        - mentions: Optional list of phone JIDs to mention.
        - link_preview: Whether to generate URL link preview.
        - link_preview_high_quality: Use high-quality link preview.
        """
        args = SendTextMessageArgs(
            chat_id=chat_id,
            text=text,
            session=session,
            user_id=user_id,
            reply_to=reply_to,
            mentions=mentions,
            link_preview=link_preview,
            link_preview_high_quality=link_preview_high_quality,
        )
        result = await _service.send_text_message(args)
        return result.model_dump()

    @mcp.tool()
    async def send_image_message(
        chat_id: str,
        session: str,
        user_id: str,
        image_mimetype: str = "image/jpeg",
        image_filename: str = "image.jpg",
        caption: str | None = None,
        image_url: str | None = None,
        image_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send an image message via WhatsApp.

        USE WHEN: Need to send an image/photo.
        - chat_id: WhatsApp chat ID.
        - image_filename: File name with extension (e.g. 'photo.jpg').
        - image_mimetype: MIME type (e.g. 'image/jpeg').
        - image_url: URL of the image (provide one of url or base64).
        - image_base64: Base64-encoded image data.
        """
        args = SendImageMessageArgs(
            chat_id=chat_id,
            session=session,
            user_id=user_id,
            caption=caption,
            image_url=image_url,
            image_base64=image_base64,
            image_mimetype=image_mimetype,
            image_filename=image_filename,
            reply_to=reply_to,
        )
        result = await _service.send_image_message(args)
        return result.model_dump()

    @mcp.tool()
    async def send_file_message(
        chat_id: str,
        session: str,
        user_id: str,
        file_mimetype: str = "application/octet-stream",
        file_filename: str = "file",
        caption: str | None = None,
        file_url: str | None = None,
        file_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send a file/document via WhatsApp.

        USE WHEN: Need to send documents, PDFs, or any file type.
        - file_filename: File name with extension (e.g. 'document.pdf').
        - file_mimetype: MIME type (e.g. 'application/pdf').
        - file_url / file_base64: Provide one of these.
        """
        args = SendFileMessageArgs(
            chat_id=chat_id,
            session=session,
            user_id=user_id,
            caption=caption,
            file_url=file_url,
            file_base64=file_base64,
            file_mimetype=file_mimetype,
            file_filename=file_filename,
            reply_to=reply_to,
        )
        result = await _service.send_file_message(args)
        return result.model_dump()

    @mcp.tool()
    async def send_voice_message(
        chat_id: str,
        session: str,
        user_id: str,
        voice_url: str | None = None,
        voice_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send a voice/audio message via WhatsApp.

        USE WHEN: Need to send voice notes or audio files.
        - voice_url / voice_base64: Provide one of these.
        """
        args = SendVoiceMessageArgs(
            chat_id=chat_id,
            session=session,
            user_id=user_id,
            voice_url=voice_url,
            voice_base64=voice_base64,
            reply_to=reply_to,
        )
        result = await _service.send_voice_message(args)
        return result.model_dump()

    @mcp.tool()
    async def send_video_message(
        chat_id: str,
        session: str,
        user_id: str,
        caption: str | None = None,
        video_url: str | None = None,
        video_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send a video message via WhatsApp.

        USE WHEN: Need to send video files.
        - video_url / video_base64: Provide one of these.
        """
        args = SendVideoMessageArgs(
            chat_id=chat_id,
            session=session,
            user_id=user_id,
            caption=caption,
            video_url=video_url,
            video_base64=video_base64,
            reply_to=reply_to,
        )
        result = await _service.send_video_message(args)
        return result.model_dump()

    @mcp.tool()
    async def delete_message(
        chat_id: str,
        message_id: str,
        session: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Delete a sent WhatsApp message.

        USE WHEN: Need to delete/remove a previously sent message.
        - chat_id: WhatsApp chat ID.
        - message_id: Unique message ID to delete.
        """
        args = DeleteMessageArgs(
            chat_id=chat_id,
            message_id=message_id,
            session=session,
            user_id=user_id,
        )
        result = await _service.delete_message(args)
        return result.model_dump()

    @mcp.tool()
    async def edit_message(
        chat_id: str,
        message_id: str,
        new_text: str,
        session: str,
        user_id: str,
        link_preview: bool = True,
    ) -> dict[str, Any]:
        """Edit a previously sent WhatsApp message.

        USE WHEN: Need to modify the text of a previously sent message.
        - chat_id: WhatsApp chat ID.
        - message_id: Unique message ID to edit.
        - new_text: The replacement text. Supports WhatsApp formatting.
        """
        args = EditMessageArgs(
            chat_id=chat_id,
            message_id=message_id,
            new_text=new_text,
            session=session,
            user_id=user_id,
            link_preview=link_preview,
        )
        result = await _service.edit_message(args)
        return result.model_dump()

    @mcp.tool()
    async def get_messages(
        chat_id: str,
        session: str,
        user_id: str,
        ctx: Context,
        limit: int = 100,
        offset: int | None = None,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        download_media: bool = False,
        query: str | None = None,
        chat_type: str = "c",
    ) -> dict[str, Any]:
        """Get and summarize messages from a WhatsApp chat.

        USE WHEN: Need to retrieve message history from a contact or group.
        - chat_id: WhatsApp chat ID.
        - limit: Max messages to retrieve (default 100).
        - from_timestamp / to_timestamp: Unix timestamps for time filtering.
        - query: Optional topic to focus the summary on.
        - chat_type: 'c' for contact, 'g' for group.
        OUTPUT: summary — LLM-generated summary of the conversation.
        """
        args = GetMessagesArgs(
            chat_id=chat_id,
            session=session,
            user_id=user_id,
            limit=limit,
            offset=offset,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            download_media=download_media,
            query=query,
            chat_type=ChatType(chat_type),
        )
        result = await _service.get_messages(args, ctx)
        return result.model_dump()

    @mcp.tool()
    async def get_all_contacts(
        session: str,
        user_id: str,
        limit: int | None = None,
        offset: int | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> dict[str, Any]:
        """Get all WhatsApp contacts.

        USE WHEN: Need to retrieve the user's WhatsApp contact list.
        OUTPUT: data — list of contact objects with id, name, pushname.
        """
        args = GetAllContactsArgs(
            session=session,
            user_id=user_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        result = await _service.get_all_contacts(args)
        return result.model_dump()

    @mcp.tool()
    async def get_contact_details(
        contact_id: str,
        session: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Get details of a specific WhatsApp contact.

        USE WHEN: Need detailed info about a particular contact.
        - contact_id: WhatsApp contact ID (e.g. '919876543210@c.us').
        OUTPUT: data — contact details including name, number, profile info.
        """
        args = GetContactDetailsArgs(
            contact_id=contact_id,
            session=session,
            user_id=user_id,
        )
        result = await _service.get_contact_details(args)
        return result.model_dump()

    @mcp.tool()
    async def get_group(
        group_id: str,
        session: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Get details of a specific WhatsApp group.

        USE WHEN: Need info about a particular group.
        - group_id: WhatsApp group ID (e.g. '123456789@g.us').
        OUTPUT: data — group details including name, participants, admins.
        """
        args = GetGroupArgs(
            group_id=group_id,
            session=session,
            user_id=user_id,
        )
        result = await _service.get_group(args)
        return result.model_dump()

    @mcp.tool()
    async def scan_unreplied_messages(
        session: str,
        user_id: str,
        phone_number: str,
        ctx: Context,
    ) -> dict[str, Any]:
        """Scan moderated WhatsApp chats for unreplied messages.

        USE WHEN: Need to check for messages the user hasn't responded to.
        BEHAVIOR:
        - DMs: Fetches messages since last check. Skips chats where the user already replied last.
        - Groups: Only includes groups where the user was @mentioned.
        - Only processes chats with moderation_status=True in MongoDB.
        - session: WAHA session name.
        - phone_number: Connected WhatsApp phone number (with country code, no +).
        OUTPUT: summary — LLM summary of what needs attention.
        """
        args = ScanUnrepliedMessagesArgs(
            session=session,
            user_id=user_id,
            phone_number=phone_number,
        )
        result = await _service.scan_unreplied_messages(args, ctx)
        return result.model_dump()

    @mcp.tool()
    async def start_sync_chats(
        session: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Start WhatsApp chat sync in background and return a job_id.

        USE WHEN: Need to refresh whatsapp_chats from WAHA without blocking.
        OUTPUT: success/message and job_id.
        """
        result = await _service.start_sync_chats(session=session, user_id=user_id)
        return result.model_dump()

    @mcp.tool()
    async def get_sync_chats_job_result(
        job_id: str,
        user_id: str,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Poll for sync job completion using the job_id from start_sync_chats.

        USE WHEN: Need final sync result (success/message/total_synced).
        - timeout: Max seconds to wait before returning a pending event.
        """
        try:
            result = await _service.get_sync_chats_job_result(
                job_id=job_id,
                user_id=user_id,
                timeout=float(timeout),
            )
        except PermissionError as exc:
            return {"event": "error", "message": str(exc)}
        except ValueError as exc:
            return {"event": "error", "message": str(exc)}

        if result is None:
            return {
                "event": "pending",
                "message": f"No sync result in {timeout}s. Keep polling.",
            }

        return {"event": "complete", "data": result.model_dump()}

    @mcp.tool()
    async def generate_chat_descriptions(
        session: str,
        user_id: str,
        ctx: Context,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Generate and store AI descriptions for the most-recent WhatsApp chats.

        USE WHEN: After start_sync_chats completes, to enrich chats with natural-language
        descriptions that summarise who each chat is with and what it is about.
        BEHAVIOR: Fetches up to `limit` most-recent chats for the user from MongoDB,
        retrieves their last 100 messages from WAHA, and uses MCP sampling to write
        a 1-2 sentence description for each. Descriptions are persisted in whatsapp_chats.
        - session: WAHA session name.
        - user_id: Relay user identifier.
        - limit: Max number of chats to describe (default 50).
        OUTPUT: processed — number of chats successfully described; skipped — chats with
        no messages or that failed.
        """
        return await _service.generate_chat_descriptions(
            session=session,
            user_id=user_id,
            ctx=ctx,
            limit=limit,
        )

    @mcp.tool()
    async def get_incoming_message(timeout: int = 30) -> dict[str, Any]:
        """Wait for and return the next incoming WhatsApp message delivered via webhook.

        USE WHEN: Need to receive new incoming WhatsApp messages in real-time.
        BEHAVIOR: Blocks until a message arrives from WAHA or the timeout elapses.
        Call this tool in a loop to continuously receive new messages.
        - timeout: Max seconds to wait before returning a timeout response (default 30).
        OUTPUT: Processed webhook event with fields:
          - event: 'message', 'session.status', or 'timeout'
          - session, chat_id, chat_name, chat_type ('dm' | 'group')
          - user_id, sender_phone, body, timestamp, message_id
          - has_media, media_url, media_mimetype
          - for session.status: status, name, statuses
        """
        event = await pop_incoming_event(timeout=float(timeout))
        if event is None:
            return {"event": "timeout", "message": f"No new messages in {timeout}s"}
        return event
