"""MCP tools — send/delete/edit WhatsApp messages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from relay_mcp.container import McpContainer


def register_messaging_tools(mcp: FastMCP, c: McpContainer) -> None:  # noqa: C901

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
        with a contact or group via WhatsApp.

        PARAMETERS:
        - chat_id: WhatsApp chat ID (w_chat_id). For DMs: '919876543210@c.us' (country code
          + number + '@c.us'). For groups: '1234567890-1234567890@g.us'. Use the exact
          w_chat_id value returned by get_chats or find_contact_by_name.
        - text: The message body. Supports WhatsApp markdown: *bold*, _italic_,
          ~strikethrough~, ```monospace```.
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - reply_to: Optional message ID to quote-reply to.
        - mentions: Optional list of WhatsApp JIDs to @mention.
        - link_preview: Generate URL preview card (default True).
        - link_preview_high_quality: Higher-resolution preview image.

        OUTPUT: success, message_id, data.
        """
        await c.user_service.get_or_create(phone_number)
        return await c.message_service.send_text(
            session=phone_number,
            chat_id=chat_id,
            text=text,
            reply_to=reply_to,
            mentions=mentions,
            link_preview=link_preview,
            link_preview_high_quality=link_preview_high_quality,
        )

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

        PARAMETERS:
        - chat_id: WhatsApp chat ID (w_chat_id). For DMs: '919876543210@c.us'.
          For groups: '1234567890-1234567890@g.us'. Use the exact w_chat_id
          returned by get_chats or find_contact_by_name.
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - image_mimetype: MIME type (default 'image/jpeg').
        - image_filename: Filename shown to recipient.
        - caption: Optional text caption.
        - image_url: Public URL of the image (provide this OR image_base64).
        - image_base64: Base64-encoded image data (provide this OR image_url).
        - reply_to: Optional message ID to quote-reply to.

        OUTPUT: success, message_id, data.
        """
        await c.user_service.get_or_create(phone_number)
        return await c.message_service.send_image(
            session=phone_number,
            chat_id=chat_id,
            file_name=image_filename,
            file_mimetype=image_mimetype,
            caption=caption,
            file_url=image_url,
            file_data=image_base64,
            reply_to=reply_to,
        )

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

        PARAMETERS:
        - chat_id: WhatsApp chat ID (w_chat_id). For DMs: '919876543210@c.us'.
          For groups: '1234567890-1234567890@g.us'. Use the exact w_chat_id
          returned by get_chats or find_contact_by_name.
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - file_mimetype: MIME type (e.g. 'application/pdf').
        - file_filename: Filename the recipient sees.
        - caption: Optional text caption.
        - file_url: Public URL of the file (provide this OR file_base64).
        - file_base64: Base64-encoded file content (provide this OR file_url).
        - reply_to: Optional message ID to quote-reply to.

        OUTPUT: success, message_id, data.
        """
        await c.user_service.get_or_create(phone_number)
        return await c.message_service.send_file(
            session=phone_number,
            chat_id=chat_id,
            file_name=file_filename,
            file_mimetype=file_mimetype,
            caption=caption,
            file_url=file_url,
            file_data=file_base64,
            reply_to=reply_to,
        )

    @mcp.tool()
    async def send_voice_message(
        chat_id: str,
        phone_number: str,
        voice_url: str | None = None,
        voice_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send a voice note (audio message) to a WhatsApp contact or group.

        PARAMETERS:
        - chat_id: WhatsApp chat ID (w_chat_id). For DMs: '919876543210@c.us'.
          For groups: '1234567890-1234567890@g.us'. Use the exact w_chat_id
          returned by get_chats or find_contact_by_name.
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - voice_url: Public URL of the audio file (provide this OR voice_base64).
        - voice_base64: Base64-encoded audio data (provide this OR voice_url).
        - reply_to: Optional message ID to quote-reply to.

        OUTPUT: success, message_id, data.
        """
        await c.user_service.get_or_create(phone_number)
        return await c.message_service.send_voice(
            session=phone_number,
            chat_id=chat_id,
            voice_url=voice_url,
            voice_base64=voice_base64,
            reply_to=reply_to,
        )

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

        PARAMETERS:
        - chat_id: WhatsApp chat ID (w_chat_id). For DMs: '919876543210@c.us'.
          For groups: '1234567890-1234567890@g.us'. Use the exact w_chat_id
          returned by get_chats or find_contact_by_name.
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - caption: Optional text caption below the video.
        - video_url: Public URL of the video (provide this OR video_base64).
        - video_base64: Base64-encoded video data (provide this OR video_url).
        - reply_to: Optional message ID to quote-reply to.

        OUTPUT: success, message_id, data.
        """
        await c.user_service.get_or_create(phone_number)
        return await c.message_service.send_video(
            session=phone_number,
            chat_id=chat_id,
            caption=caption,
            video_url=video_url,
            video_base64=video_base64,
            reply_to=reply_to,
        )

    @mcp.tool()
    async def delete_message(
        chat_id: str,
        message_id: str,
        phone_number: str,
    ) -> dict[str, Any]:
        """Delete a previously sent WhatsApp message (unsend for everyone).

        PARAMETERS:
        - chat_id: WhatsApp chat ID containing the message.
        - message_id: ID of the message to delete.
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).

        OUTPUT: success.
        """
        await c.user_service.get_or_create(phone_number)
        return await c.message_service.delete_message(
            session=phone_number, chat_id=chat_id, message_id=message_id
        )

    @mcp.tool()
    async def edit_message(
        chat_id: str,
        message_id: str,
        new_text: str,
        phone_number: str,
        link_preview: bool = True,
    ) -> dict[str, Any]:
        """Edit the text of a previously sent WhatsApp message.

        PARAMETERS:
        - chat_id: WhatsApp chat ID containing the message.
        - message_id: ID of the message to edit.
        - new_text: Replacement text content.
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - link_preview: Regenerate URL preview if a link is present (default True).

        OUTPUT: success, message_id, data.
        """
        await c.user_service.get_or_create(phone_number)
        return await c.message_service.edit_message(
            session=phone_number,
            chat_id=chat_id,
            message_id=message_id,
            new_text=new_text,
            link_preview=link_preview,
        )
