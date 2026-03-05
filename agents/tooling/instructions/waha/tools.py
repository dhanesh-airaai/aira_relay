"""WAHA MCP tool handlers for Relay WhatsApp tools."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context

from adapters.waha import WahaClient
from agents.tooling.services.waha.service import WahaService
from config.settings import settings
from db.mongodb.manager import mongo
from models.waha.args import (
    ConnectWhatsappArgs,
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
from relay.notifications import push_incoming_event

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

# Keep strong references to background tasks to prevent GC
_background_tasks: set[asyncio.Task[None]] = set()


def register_waha_tools(mcp: FastMCP) -> None:
    """Register WAHA tools with a FastMCP server instance."""

    @mcp.tool()
    async def send_text_message(
        chat_id: str,
        text: str,
        phone_number: str,
        reply_to: str | None = None,
        mentions: list[str] | None = None,
        link_preview: bool = True,
        link_preview_high_quality: bool = False,
    ) -> dict[str, Any]:
        """Send a plain text message to a WhatsApp contact or group.

        USE WHEN: The user wants to send a text reply, start a conversation, or follow up
        with a contact or group via WhatsApp. This is the primary tool for all text-based
        communication — use it for greetings, answers, follow-ups, and any message that
        does not require media.

        PARAMETERS:
        - chat_id: WhatsApp chat identifier. For individual contacts use the format
          '919876543210@c.us' (country code + number, no +, suffix @c.us). For groups
          use '1234567890-1234567890@g.us'. Obtain this from get_all_contacts,
          get_contact_details, or from an incoming message event.
        - text: The message body. Supports WhatsApp markdown: *bold*, _italic_,
          ~strikethrough~, ```monospace```. Newlines are preserved.
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616'). Obtained from connect_whatsapp.
        - reply_to: Optional. Message ID of the message to quote-reply to. If set, the
          sent message will appear as a reply to that specific message in WhatsApp.
        - mentions: Optional list of WhatsApp JIDs (e.g. ['919876543210@c.us']) to @mention
          in the message. The mentioned text must also appear in the `text` field.
        - link_preview: When True (default), WhatsApp will generate a preview card for
          any URL present in the message.
        - link_preview_high_quality: When True, fetches a higher-resolution preview image.
          Only relevant if link_preview is True.

        OUTPUT:
        - success: bool — whether the message was sent successfully.
        - message_id: The WhatsApp message ID of the sent message (use for reply_to or delete).
        - error: Present only on failure, describes what went wrong.
        """
        user = await _service.get_or_create_user(phone_number)
        args = SendTextMessageArgs(
            chat_id=chat_id,
            text=text,
            session=phone_number,
            user_id=user.id,
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
        phone_number: str,
        image_mimetype: str = "image/jpeg",
        image_filename: str = "image.jpg",
        caption: str | None = None,
        image_url: str | None = None,
        image_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send an image or photo to a WhatsApp contact or group.

        USE WHEN: The user wants to share a photo, screenshot, chart, or any image file
        via WhatsApp. Supports JPEG, PNG, GIF, and WebP formats.

        PARAMETERS:
        - chat_id: WhatsApp chat ID (phone@c.us for DMs, group-id@g.us for groups).
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').
        - image_mimetype: MIME type of the image. Common values: 'image/jpeg', 'image/png',
          'image/gif', 'image/webp'. Defaults to 'image/jpeg'.
        - image_filename: File name shown to the recipient (e.g. 'photo.jpg', 'chart.png').
          Include the correct extension so WhatsApp renders it properly.
        - caption: Optional text caption displayed below the image. Supports WhatsApp
          markdown formatting (*bold*, _italic_, etc.).
        - image_url: Public URL of the image to send. Provide either this OR image_base64,
          not both. The URL must be publicly accessible by the WAHA server.
        - image_base64: Base64-encoded image data (without data URI prefix). Provide either
          this OR image_url, not both.
        - reply_to: Optional message ID to quote-reply to.

        OUTPUT:
        - success: bool — whether the image was sent.
        - message_id: WhatsApp message ID of the sent image message.
        - error: Present only on failure.
        """
        user = await _service.get_or_create_user(phone_number)
        args = SendImageMessageArgs(
            chat_id=chat_id,
            session=phone_number,
            user_id=user.id,
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
        phone_number: str,
        file_mimetype: str = "application/octet-stream",
        file_filename: str = "file",
        caption: str | None = None,
        file_url: str | None = None,
        file_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send a document or file attachment to a WhatsApp contact or group.

        USE WHEN: The user wants to share a document (PDF, Word, Excel, CSV, ZIP, etc.)
        or any non-image, non-video, non-audio file. The recipient sees it as a downloadable
        attachment in WhatsApp.

        PARAMETERS:
        - chat_id: WhatsApp chat ID (phone@c.us for DMs, group-id@g.us for groups).
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').
        - file_mimetype: MIME type of the file. Examples: 'application/pdf',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document' (docx),
          'text/csv', 'application/zip'. Defaults to 'application/octet-stream'.
        - file_filename: The filename the recipient sees (e.g. 'report.pdf', 'data.csv').
          Always include the correct extension — WhatsApp uses this to display the file icon.
        - caption: Optional text caption shown with the file. Supports WhatsApp formatting.
        - file_url: Public URL of the file. Provide either this OR file_base64, not both.
        - file_base64: Base64-encoded file content. Provide either this OR file_url, not both.
        - reply_to: Optional message ID to quote-reply to.

        OUTPUT:
        - success: bool — whether the file was sent.
        - message_id: WhatsApp message ID of the sent file message.
        - error: Present only on failure.
        """
        user = await _service.get_or_create_user(phone_number)
        args = SendFileMessageArgs(
            chat_id=chat_id,
            session=phone_number,
            user_id=user.id,
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
        phone_number: str,
        voice_url: str | None = None,
        voice_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send a voice note (audio message) to a WhatsApp contact or group.

        USE WHEN: The user wants to send a voice note or audio clip. WhatsApp renders this
        as a waveform audio player (the familiar microphone-style bubble), not as a generic
        file attachment. Use OGG/Opus audio for best compatibility; MP3 also works.

        PARAMETERS:
        - chat_id: WhatsApp chat ID (phone@c.us for DMs, group-id@g.us for groups).
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').
        - voice_url: Public URL of the audio file (OGG/Opus or MP3 preferred). Provide
          either this OR voice_base64, not both.
        - voice_base64: Base64-encoded audio data. Provide either this OR voice_url, not both.
        - reply_to: Optional message ID to quote-reply to.

        OUTPUT:
        - success: bool — whether the voice note was sent.
        - message_id: WhatsApp message ID of the sent voice message.
        - error: Present only on failure.
        """
        user = await _service.get_or_create_user(phone_number)
        args = SendVoiceMessageArgs(
            chat_id=chat_id,
            session=phone_number,
            user_id=user.id,
            voice_url=voice_url,
            voice_base64=voice_base64,
            reply_to=reply_to,
        )
        result = await _service.send_voice_message(args)
        return result.model_dump()

    @mcp.tool()
    async def send_video_message(
        chat_id: str,
        phone_number: str,
        caption: str | None = None,
        video_url: str | None = None,
        video_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send a video to a WhatsApp contact or group.

        USE WHEN: The user wants to share a video clip. WhatsApp renders this as an
        inline video player (not a file download). MP4 is the recommended format.

        PARAMETERS:
        - chat_id: WhatsApp chat ID (phone@c.us for DMs, group-id@g.us for groups).
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').
        - caption: Optional text caption shown below the video. Supports WhatsApp formatting.
        - video_url: Public URL of the video file (MP4 recommended). Provide either this
          OR video_base64, not both.
        - video_base64: Base64-encoded video data. Provide either this OR video_url, not both.
        - reply_to: Optional message ID to quote-reply to.

        OUTPUT:
        - success: bool — whether the video was sent.
        - message_id: WhatsApp message ID of the sent video.
        - error: Present only on failure.
        """
        user = await _service.get_or_create_user(phone_number)
        args = SendVideoMessageArgs(
            chat_id=chat_id,
            session=phone_number,
            user_id=user.id,
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
        phone_number: str,
    ) -> dict[str, Any]:
        """Delete a previously sent WhatsApp message (unsend for everyone).

        USE WHEN: The user wants to retract or undo a message they sent. This deletes
        the message for all participants in the chat (equivalent to WhatsApp's "Delete for
        Everyone"). Only works on messages sent by the connected account; cannot delete
        messages sent by other people.

        PARAMETERS:
        - chat_id: WhatsApp chat ID of the conversation containing the message.
        - message_id: The unique WhatsApp message ID to delete. Obtain this from the
          message_id field returned by send_text_message, send_image_message, or
          from an incoming message event.
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').

        OUTPUT:
        - success: bool — whether the deletion was successful.
        - error: Present only on failure (e.g. message too old, not sent by this account).
        """
        user = await _service.get_or_create_user(phone_number)
        args = DeleteMessageArgs(
            chat_id=chat_id,
            message_id=message_id,
            session=phone_number,
            user_id=user.id,
        )
        result = await _service.delete_message(args)
        return result.model_dump()

    @mcp.tool()
    async def edit_message(
        chat_id: str,
        message_id: str,
        new_text: str,
        phone_number: str,
        link_preview: bool = True,
    ) -> dict[str, Any]:
        """Edit the text of a previously sent WhatsApp message.

        USE WHEN: The user wants to correct or update a message they already sent.
        WhatsApp shows an "Edited" label on the message after editing. Only text messages
        can be edited — media captions and non-text messages cannot be changed this way.
        Only works on messages sent by the connected account.

        PARAMETERS:
        - chat_id: WhatsApp chat ID of the conversation containing the message.
        - message_id: The unique WhatsApp message ID to edit. Obtain from the message_id
          returned when the message was sent.
        - new_text: The replacement text content. The old text is fully replaced.
          Supports WhatsApp markdown: *bold*, _italic_, ~strikethrough~, ```monospace```.
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').
        - link_preview: When True (default), regenerates URL preview if a link is present
          in new_text.

        OUTPUT:
        - success: bool — whether the edit was applied.
        - error: Present only on failure.
        """
        user = await _service.get_or_create_user(phone_number)
        args = EditMessageArgs(
            chat_id=chat_id,
            message_id=message_id,
            new_text=new_text,
            session=phone_number,
            user_id=user.id,
            link_preview=link_preview,
        )
        result = await _service.edit_message(args)
        return result.model_dump()

    @mcp.tool()
    async def get_messages(
        chat_id: str,
        phone_number: str,
        ctx: Context,
        limit: int = 100,
        offset: int | None = None,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        download_media: bool = False,
        query: str | None = None,
        chat_type: str = "c",
    ) -> dict[str, Any]:
        """Retrieve and summarize message history from a WhatsApp chat.

        USE WHEN: The user asks what was discussed in a conversation, wants a summary of
        recent messages, needs to review a chat before replying, or asks questions about
        the content of a specific conversation. This tool fetches raw messages from WAHA
        and uses the LLM (via MCP sampling) to produce a human-readable summary.

        PARAMETERS:
        - chat_id: WhatsApp chat ID. For DMs: 'phone@c.us'. For groups: 'groupid@g.us'.
          If you don't have the chat_id, use get_all_contacts or get_contact_details first.
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').
        - ctx: MCP context (injected automatically — do not pass manually).
        - limit: Maximum number of messages to fetch, newest first (default 100, max ~1000).
          Increase for longer history; decrease for faster responses.
        - offset: Number of messages to skip from the newest (for pagination). Leave None
          to start from the most recent message.
        - from_timestamp: Unix timestamp (seconds) — only include messages after this time.
          Use to scope the summary to a specific time window (e.g. last 24 hours).
        - to_timestamp: Unix timestamp (seconds) — only include messages before this time.
        - download_media: When True, fetches media URLs for images/files in the chat.
          Slower but provides richer context. Default False.
        - query: Optional focus topic for the LLM summary (e.g. 'delivery status', 'price
          negotiation'). When provided, the summary prioritises messages relevant to this topic.
        - chat_type: 'c' for individual contact (DM), 'g' for group. Affects how sender
          names are resolved in the summary. Defaults to 'c'.

        OUTPUT:
        - summary: LLM-generated natural-language summary of the conversation.
        - message_count: Number of messages retrieved from WAHA.
        - error: Present only on failure.
        """
        user = await _service.get_or_create_user(phone_number)
        args = GetMessagesArgs(
            chat_id=chat_id,
            session=phone_number,
            user_id=user.id,
            limit=limit,
            offset=offset,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            download_media=download_media,
            query=query,
            chat_type=ChatType(chat_type),
        )
        result = await _service.get_messages_summary(args, ctx)
        return result.model_dump()
    @mcp.tool()
    async def get_messages_with_id(
        chat_id: str,
        phone_number: str,
        ctx: Context,
        limit: int = 100,
        offset: int | None = None,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        download_media: bool = False,
        chat_type: str = "c",
    ) -> dict[str, Any]:
        """Fetch raw message history and a readable conversation transcript from a WhatsApp chat.

        USE WHEN: The user wants to read messages from a conversation — e.g. to check
        what was said, look up a specific message, or read chat history before replying.
        Returns both the raw WAHA message objects and a formatted transcript with sender
        names resolved; use the transcript for quick reading and raw_messages for detailed
        inspection.

        PARAMETERS:
        - chat_id: WhatsApp chat identifier. For individual contacts: '919876543210@c.us'
          (country code + number, no +, suffix @c.us). For groups: 'groupid@g.us'.
          Obtain from get_all_contacts or get_contact_details if unknown.
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616'). Obtained from connect_whatsapp.
        - limit: Maximum number of messages to fetch, newest first (default 100, max ~1000).
          Increase for longer history; decrease for faster responses.
        - offset: Number of messages to skip from the newest (for pagination). Leave None
          to start from the most recent message.
        - from_timestamp: Unix timestamp (seconds) — only return messages after this time.
          Use to scope the fetch to a specific window (e.g. last 24 hours).
        - to_timestamp: Unix timestamp (seconds) — only return messages before this time.
        - download_media: When True, includes media URLs for images and files in the chat.
          Slower but provides richer content. Default False.
        - chat_type: 'c' for individual contact DM (default), 'g' for group. Used to
          resolve sender names correctly in the conversation transcript.

        OUTPUT:
        - raw_messages: List of raw WAHA message objects, newest first. Each object
          contains message ID, sender, timestamp, text body, and media metadata.
        - conversation_text: Formatted transcript with sender names and message bodies,
          ready to read. Format: '[Name]: message'.
        - error: Present only on failure, describes what went wrong.
        """
        user = await _service.get_or_create_user(phone_number)
        args = GetMessagesArgs(
            chat_id=chat_id,
            session=phone_number,
            user_id=user.id,
            limit=limit,
            offset=offset,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            download_media=download_media,
            query=None,
            chat_type=ChatType(chat_type),
        )
        result = await _service.get_messages_with_id(args, ctx)
        return result.model_dump()

    @mcp.tool()
    async def get_all_contacts(
        phone_number: str,
        limit: int | None = None,
        offset: int | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve the full WhatsApp contact list for the connected account.

        USE WHEN: The user asks to see their contacts, wants to find someone's chat ID
        by name, or needs to pick a recipient before sending a message. Also useful for
        building an overview of who the user communicates with on WhatsApp.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').
        - limit: Maximum number of contacts to return. Leave None to return all contacts.
        - offset: Number of contacts to skip (for pagination with limit).
        - sort_by: Field to sort by (e.g. 'name', 'id'). Leave None for default order.
        - sort_order: 'asc' or 'desc'. Only relevant when sort_by is set.

        OUTPUT:
        - data: List of contact objects. Each object includes:
            - id: WhatsApp JID (use as chat_id in send/get tools), e.g. '919876543210@c.us'
            - name: Contact's saved name in the phone book (may be empty)
            - pushname: The name the contact set in their WhatsApp profile
            - number: Phone number without country code
        - total: Total number of contacts returned.
        """
        user = await _service.get_or_create_user(phone_number)
        args = GetAllContactsArgs(
            session=phone_number,
            user_id=user.id,
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
        phone_number: str,
    ) -> dict[str, Any]:
        """Get detailed profile information for a specific WhatsApp contact.

        USE WHEN: The user asks about a specific contact (who they are, their profile name,
        etc.), or when you need to confirm the correct chat_id for a person before messaging
        them. More detailed than the entries in get_all_contacts.

        PARAMETERS:
        - contact_id: WhatsApp JID of the contact to look up, in the format
          '919876543210@c.us'. If you only have a name, use get_all_contacts first to
          find the JID.
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').

        OUTPUT:
        - data: Contact profile object including:
            - id: WhatsApp JID (same as contact_id)
            - name: Saved contact name (from phone book)
            - pushname: Name set by the contact in their WhatsApp profile
            - short_name: Short version of the pushname
            - number: Phone number
            - is_business: Whether this is a WhatsApp Business account
            - profile_pic_url: URL of the contact's profile picture (if available)
        """
        user = await _service.get_or_create_user(phone_number)
        args = GetContactDetailsArgs(
            contact_id=contact_id,
            session=phone_number,
            user_id=user.id,
        )
        result = await _service.get_contact_details(args)
        return result.model_dump()

    @mcp.tool()
    async def get_group(
        group_id: str,
        phone_number: str,
    ) -> dict[str, Any]:
        """Get metadata and participant list for a specific WhatsApp group.

        USE WHEN: The user asks about a group (who's in it, who the admins are, the group
        description, etc.), or when you need group details before sending a message or
        scanning for mentions.

        PARAMETERS:
        - group_id: WhatsApp group JID in the format '1234567890-1234567890@g.us'.
          Obtain from get_all_contacts (groups appear alongside DMs) or from an incoming
          message event where chat_type is 'group'.
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').

        OUTPUT:
        - data: Group metadata object including:
            - id: Group JID
            - name: Group name
            - description: Group description text
            - participants: List of participant objects, each with:
                - id: Participant JID (phone@c.us)
                - isAdmin: Whether this participant is a group admin
                - isSuperAdmin: Whether this participant created the group
            - size: Total number of participants
        """
        user = await _service.get_or_create_user(phone_number)
        args = GetGroupArgs(
            group_id=group_id,
            session=phone_number,
            user_id=user.id,
        )
        result = await _service.get_group(args)
        return result.model_dump()

    @mcp.tool()
    async def scan_unreplied_messages(
        phone_number: str,
        ctx: Context,
    ) -> dict[str, Any]:
        """Scan moderated WhatsApp chats for messages that need a reply.

        USE WHEN: The user asks "what messages do I need to reply to?", "what did I miss?",
        or "do I have any pending conversations?". This tool is the primary way to surface
        actionable, unreplied messages across all monitored chats.

        BEHAVIOR:
        - Only scans chats that have moderation_status=True in the database (chats the user
          has explicitly opted in to monitor). Ignores all other chats.
        - Incremental: only looks at messages received since the last time this tool was
          called (tracked per user in MongoDB). On first call, looks back 24 hours.
        - DMs: A DM is considered "unreplied" if the most recent message in the conversation
          was sent by the contact (not by the user). If the user already replied last, the
          DM is skipped.
        - Groups: Only included if the user's phone number was @mentioned in the group
          since the last check. Scans from the first mention forward so context is preserved.
        - Uses the LLM (via MCP sampling) to produce a concise, actionable summary of what
          needs attention — who messaged, what they said, and any actions required.
        - After scanning, updates last_checkin_at in MongoDB so the next call is incremental.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616'). Used to identify the user and as the WAHA session.
        - ctx: MCP context (injected automatically — do not pass manually).

        OUTPUT:
        - summary: LLM-generated natural-language summary of unreplied messages and
          group mentions, with enough context for the user to decide how to respond.
        - dm_count: Number of DM conversations with unreplied messages found.
        - group_count: Number of groups where the user was mentioned.
        - error: Present only on failure.
        """
        user = await _service.get_or_create_user(phone_number)
        args = ScanUnrepliedMessagesArgs(
            session=phone_number,
            user_id=user.id,
        )
        result = await _service.scan_unreplied_messages(args, ctx)
        return result.model_dump()

    @mcp.tool()
    async def sync_chats(
        phone_number: str,
        ctx: Context,
    ) -> dict[str, Any]:
        """Sync all WhatsApp chats from WAHA into the local database (runs in background).

        USE WHEN: The user connects WhatsApp for the first time, asks to refresh their
        chat list, or after a long period of inactivity. This tool fetches all DM and group
        chats from WAHA, upserts them into MongoDB, indexes contact names for phonetic search,
        and then automatically runs generate_chat_descriptions to enrich each chat with an
        AI-generated description. The result is delivered back via a push notification event
        ('sync_chats') rather than as a direct return value — the agent will receive it
        through get_incoming_message.

        BEHAVIOR:
        - Runs entirely in the background; returns immediately with a confirmation message.
        - Fetches both DM chats (@c.us) and group chats (@g.us).
        - For contacts with no saved name, resolves the display name from WAHA profile data.
        - Stores/updates each chat in the whatsapp_chats MongoDB collection, keyed by
          (user_id, w_chat_id). Existing chats are updated, new ones are inserted.
        - After syncing, automatically calls generate_chat_descriptions (up to 50 chats).
        - Pushes a 'sync_chats' event with total_synced count and descriptions when done.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616'). Used as both the WAHA session name and to look up the user.
        - ctx: MCP context (injected automatically — do not pass manually).

        OUTPUT (immediate):
        - message: Confirmation that sync has started in the background.

        ASYNC RESULT (delivered via get_incoming_message):
        - event: 'sync_chats'
        - success: bool
        - total_synced: number of chats written to the database
        - descriptions: dict mapping chat_id → AI-generated description string
        """
        user = await _service.get_or_create_user(phone_number)

        async def _run() -> None:
            result = await _service.sync_chats(session=phone_number, user_id=user.id)
            desc = await _service.generate_chat_descriptions(
                session=phone_number, user_id=user.id, ctx=ctx, limit=50
            )
            # send the result and descriptions back to the agent via push notification
            await push_incoming_event(
                {
                    "event": "sync_chats",
                    **result.model_dump(),
                    "descriptions": desc,
                },
                hook_type="agent",
            )

        task = asyncio.create_task(_run(), name=f"sync_chats_{phone_number}")
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        return {"message": "Syncing chats in background. I'll notify you when done."}

    @mcp.tool()
    async def generate_chat_descriptions(
        phone_number: str,
        ctx: Context,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Generate and persist AI descriptions for the most recent WhatsApp chats.

        USE WHEN: You want to enrich stored chats with natural-language descriptions that
        explain who each chat is with and what it is about — making it easier to identify
        chats by topic or relationship in future interactions. Normally called automatically
        by sync_chats; invoke manually only if descriptions are missing or stale.

        BEHAVIOR:
        - Fetches the `limit` most-recently active chats for the user from MongoDB
          (ordered by conversation_timestamp descending).
        - For each chat, retrieves the last 100 messages from WAHA.
        - Calls the LLM (via MCP sampling) with a system prompt instructing it to write a
          1-2 sentence description: who the chat is with or what the group is about, and
          the main topics discussed.
        - Persists the description back into the whatsapp_chats document (description field).
        - Processes up to 3 chats concurrently to respect WAHA rate limits.
        - Chats with no messages are skipped and counted in the 'skipped' output.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').
        - ctx: MCP context (injected automatically — do not pass manually).
        - limit: Maximum number of chats to describe (default 50). Reduce to speed up
          the process; increase to cover more chat history.

        OUTPUT:
        - processed: Number of chats that were successfully described and saved.
        - skipped: Number of chats skipped (no messages found or LLM call failed).
        """
        user = await _service.get_or_create_user(phone_number)
        return await _service.generate_chat_descriptions(
            session=phone_number,
            user_id=user.id,
            ctx=ctx,
            limit=limit,
        )

    @mcp.tool()
    async def get_chats(
        phone_number: str,
        limit: int = 5000,
        offset: int = 0,
        chat_type: str | None = None,
        moderated_only: bool = False,
    ) -> dict[str, Any]:
        """Retrieve WhatsApp chats stored in the local database for the connected account.

        USE WHEN: The user asks to list their chats, wants to find a specific conversation,
        or you need to pick a chat before fetching messages or scanning for unreplied messages.
        Returns chats from MongoDB (populated by sync_chats), sorted by most recently active.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number with country code, no +
          (e.g. '918123941616').
        - limit: Maximum number of chats to return (default 50).
        - offset: Number of chats to skip for pagination (default 0).
        - chat_type: Filter by chat type. Use 'chat' for DMs or 'group' for group chats.
          Leave None to return all types.
        - moderated_only: When True, only return chats with moderation enabled.

        OUTPUT:
        - data: List of chat objects, each including:
            - w_chat_id: WhatsApp chat ID (use as chat_id in other tools)
            - chat_name: Display name of the contact or group
            - type: 'chat' for DMs, 'group' for groups
            - description: AI-generated description (if generated via sync_chats)
            - moderation_status: Whether this chat is being monitored for unreplied messages
            - conversation_timestamp: Unix timestamp of the last message
        - total: Number of chats returned.
        """
        user = await _service.get_or_create_user(phone_number)
        result = await _service.get_chats(
            user_id=user.id,
            limit=limit,
            offset=offset,
            chat_type=chat_type,
            moderated_only=moderated_only,
        )
        return result.model_dump()

    # @mcp.tool()
    # async def get_or_create_user(phone_number: str) -> dict[str, Any]:
    #     """Look up or create a Relay user account by WhatsApp phone number.

    #     USE WHEN: This must be called at the start of every session before using any other
    #     tool. It returns the user_id that all other tools require. If no user exists for
    #     this phone number, a new one is created automatically.

    #     PARAMETERS:
    #     - phone_number: The WhatsApp phone number with country code, no + or spaces
    #       (e.g. '919876543210' for India, '14155552671' for US). This is also the WAHA
    #       session name used in all subsequent calls.

    #     OUTPUT:
    #     - id: The Relay internal user ID (UUID string). Pass this as user_id to every
    #       other tool in this session.
    #     - phone_number: Normalised phone number stored in the database.
    #     - created_at: ISO timestamp of when the user was first registered.
    #     """
    #     user = await _service.get_or_create_user(phone_number)
    #     return user.model_dump()

    @mcp.tool()
    async def connect_whatsapp(phone_number: str) -> dict[str, Any]:
        """Connect a WhatsApp account to AiRA Relay via phone number pairing code.

        USE WHEN: The user wants to link their WhatsApp account for the first time, or
        reconnect after being logged out. This is the onboarding flow — it does not use
        a QR code; instead it generates an 8-digit pairing code the user enters in the
        WhatsApp app on their phone.

        BEHAVIOR (step by step):
        1. Calls get_or_create_user to ensure the user record exists in MongoDB.
        2. Deletes any existing stale WAHA session for this phone number to start clean.
        3. Creates a new WAHA session and waits for it to reach SCAN_QR_CODE status
           (meaning WAHA is ready to pair).
        4. Requests an 8-digit alphanumeric pairing code from WAHA for this phone number.
        5. Returns the code immediately — the user must enter it in WhatsApp within ~60s.

        PARAMETERS:
        - phone_number: The WhatsApp phone number to connect, with country code, no +
          (e.g. '919876543210'). Must be the number of the physical device the user
          will approve the pairing on.

        OUTPUT:
        - success: bool — True if pairing code was obtained successfully.
        - user_id: Relay internal user ID. Use as session name for all subsequent calls.
        - code: 8-digit pairing code (e.g. 'ABCD-1234'). Show this to the user and
          instruct them to open WhatsApp → Settings → Linked Devices → Link with phone
          number → enter this code. The code expires in ~60 seconds.
        - message: Human-readable status message.
        - error: Present only on failure (e.g. session creation timed out, WAHA error).

        AFTER SUCCESS: Wait for a 'session.status' event via get_incoming_message with
        status='WORKING' to confirm the device is fully linked before proceeding.
        """
        print(f"Connecting WhatsApp for {phone_number}...")
        args = ConnectWhatsappArgs(phone_number=phone_number)
        result = await _service.connect_whatsapp(args)
        return result.model_dump()

    # @mcp.tool()
    # async def get_incoming_message(ctx: Context, timeout: int = 30) -> dict[str, Any]:
    #     """Wait for and return the next real-time event from WhatsApp.

    #     Events include incoming messages, session status changes, and sync results.

    #     USE WHEN: You need to receive incoming WhatsApp messages or system events in real
    #     time. Call this tool in a continuous loop to act as a live WhatsApp listener. Every
    #     event WAHA delivers via webhook (incoming messages, session status changes, chat sync
    #     completions) is queued and returned one at a time by this tool.

    #     BEHAVIOR:
    #     - Blocks (suspends) for up to `timeout` seconds waiting for the next queued event.
    #     - Events are queued by the webhook receiver as they arrive from WAHA; this tool
    #       dequeues one event per call.
    #     - If no event arrives within the timeout window, returns {"event": "timeout"}.
    #     - Automatically registers the current MCP session so the relay can route events
    #       to the right agent instance.
    #     - Call this in a loop: process the returned event, then immediately call again
    #       to wait for the next one. Do not delay between calls or events will queue up.

    #     PARAMETERS:
    #     - ctx: MCP context (injected automatically — do not pass manually).
    #     - timeout: Maximum seconds to wait before returning a timeout response.
    #       Default 30. Increase for low-traffic scenarios; decrease for more responsive loops.

    #     OUTPUT (one of the following event shapes):

    #     Incoming message (event = 'message'):
    #     - event: 'message'
    #     - session: WAHA session name (connected phone number)
    #     - chat_id: WhatsApp chat ID of the conversation (phone@c.us or group@g.us)
    #     - chat_name: Display name of the contact or group
    #     - chat_type: 'dm' for direct messages, 'group' for group chats
    #     - user_id: Relay internal user ID
    #     - sender_phone: Phone number of the person who sent the message (without @c.us)
    #     - body: Text content of the message
    #     - timestamp: Unix timestamp (seconds) when the message was sent
    #     - message_id: Unique WhatsApp message ID (use for reply_to or delete_message)
    #     - has_media: True if the message contains an image, file, audio, or video
    #     - media_url: URL to download the media (only present when has_media=True)
    #     - media_mimetype: MIME type of the media (e.g. 'image/jpeg', 'audio/ogg')

    #     Session status change (event = 'session.status'):
    #     - event: 'session.status'
    #     - session: WAHA session name
    #     - status: New status — 'WORKING' (connected), 'FAILED', 'STOPPED', 'SCAN_QR_CODE'
    #     - name: Session display name
    #     - timestamp: Unix timestamp of the status change
    #     - statuses: List of status transition objects with timestamps

    #     Chat sync completed (event = 'sync_chats'):
    #     - event: 'sync_chats'
    #     - success: bool
    #     - total_synced: Number of chats written to MongoDB
    #     - descriptions: Dict mapping chat_id → AI-generated description string

    #     Timeout (no event arrived):
    #     - event: 'timeout'
    #     - message: 'No new messages in {timeout}s'
    #     """
    #     await register_session(ctx.session)
    #     event = await pop_incoming_event(timeout=float(timeout))
    #     if event is None:
    #         return {"event": "timeout", "message": f"No new messages in {timeout}s"}
    #     return event
