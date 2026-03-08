"""MCP tools — chat retrieval, sync, descriptions, and message history."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context

from models.events import SyncChatsEvent
from relay_mcp.llm_adapter import McpLLMAdapter

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from relay_mcp.container import McpContainer

logger = logging.getLogger(__name__)


def register_chat_tools(mcp: FastMCP, c: McpContainer) -> None:  # noqa: C901

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
        recent messages, or needs to review a chat before replying.

        PARAMETERS:
        - chat_id: WhatsApp chat ID. For DMs: 'phone@c.us'. For groups: 'groupid@g.us'.
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - limit: Maximum messages to fetch, newest first (default 100).
        - offset: Messages to skip from newest (pagination).
        - from_timestamp: Only include messages after this Unix timestamp.
        - to_timestamp: Only include messages before this Unix timestamp.
        - download_media: Fetch media URLs (slower but richer).
        - query: Focus topic for the LLM summary.
        - chat_type: 'c' for DM, 'g' for group.

        OUTPUT: summary, message_count.
        """
        is_group = chat_type == "g"
        llm = McpLLMAdapter(ctx)
        return await c.message_service.get_messages_summary(
            session=phone_number,
            chat_id=chat_id,
            is_group=is_group,
            llm=llm,
            limit=limit,
            offset=offset,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            download_media=download_media,
            query=query,
        )

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
        """Fetch raw message history and a readable conversation transcript.

        USE WHEN: The user wants to read messages from a conversation, check what was
        said, or look up a specific message.

        PARAMETERS:
        - chat_id: WhatsApp chat ID. For DMs: 'phone@c.us'. For groups: 'groupid@g.us'.
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - limit: Maximum messages to fetch (default 100).
        - offset: Messages to skip from newest (pagination).
        - from_timestamp: Only return messages after this Unix timestamp.
        - to_timestamp: Only return messages before this Unix timestamp.
        - download_media: Include media URLs (default False).
        - chat_type: 'c' for DM (default), 'g' for group.

        OUTPUT: raw_messages, conversation_text.
        """
        is_group = chat_type == "g"
        return await c.message_service.get_messages_with_id(
            session=phone_number,
            chat_id=chat_id,
            is_group=is_group,
            limit=limit,
            offset=offset,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            download_media=download_media,
        )

    @mcp.tool()
    async def scan_unreplied_messages(
        phone_number: str,
        ctx: Context,
    ) -> dict[str, Any]:
        """Scan monitored WhatsApp chats for messages that need a reply.

        USE WHEN: The user asks "what messages do I need to reply to?", "what did I miss?",
        or "do I have any pending conversations?".

        BEHAVIOR:
        - Incremental: only looks at messages since the last scan (24 h on first call).
        - DMs: unreplied if the contact's message is newest.
        - Groups: only if the user was @mentioned since last check.
        - Returns an LLM-generated summary of what needs attention.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).

        OUTPUT: summary, dm_count, group_count.
        """
        user = await c.user_service.get_or_create(phone_number)
        llm = McpLLMAdapter(ctx)
        result = await c.message_service.scan_unreplied(
            session=phone_number,
            user_id=user.id,
            llm=llm,
        )
        return result.model_dump()

    @mcp.tool()
    async def get_chats(
        phone_number: str,
        limit: int = 5000,
        offset: int = 0,
        chat_type: str | None = None,
        moderated_only: bool = False,
    ) -> dict[str, Any]:
        """Retrieve WhatsApp chats stored in the local database.

        USE WHEN: The user asks to list their chats, find a specific conversation, or
        pick a chat before fetching messages.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - limit: Maximum chats to return (default 5000).
        - offset: Chats to skip for pagination.
        - chat_type: 'chat' for DMs, 'group' for groups, None for all.
        - moderated_only: Only return monitored chats.

        OUTPUT: data (list of chat objects), success.
        """
        user = await c.user_service.get_or_create(phone_number)
        chats = await c.chat_service.get_chats(
            user_id=user.id,
            limit=limit,
            offset=offset,
            chat_type=chat_type,
            moderated_only=moderated_only,
        )
        return {"success": True, "data": chats}

    @mcp.tool()
    async def sync_chats(
        phone_number: str,
    ) -> dict[str, Any]:
        """Sync all WhatsApp chats from WAHA into the local database (runs in background).

        USE WHEN: The user connects WhatsApp for the first time, asks to refresh their
        chat list, or after a long period of inactivity.

        BEHAVIOR:
        - Runs in the background; returns immediately with a confirmation message.
        - After syncing, automatically generates AI descriptions for up to 50 chats.
        - Pushes a 'sync_chats' event via get_incoming_message when done.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).

        OUTPUT (immediate): message confirming background start.
        ASYNC RESULT (via get_incoming_message): event='sync_chats', success, total_synced, descriptions.
        """
        user = await c.user_service.get_or_create(phone_number)

        async def _run() -> None:
            result = await c.chat_service.sync_chats(
                session=phone_number, user_id=user.id
            )
            desc_result = await c.chat_service.generate_descriptions(
                session=phone_number, user_id=user.id, llm=c.openclaw, limit=50
            )
            event = SyncChatsEvent(
                success=result.success,
                message=result.message,
                total_synced=result.total_synced,
                session=phone_number,
                descriptions=desc_result.get("descriptions", {}),
            )
            await c.event_bus.publish(event)

        c.tasks.spawn(_run(), name=f"sync_chats_{phone_number}")
        return {"message": "Syncing chats in background. I'll notify you when done."}

    @mcp.tool()
    async def generate_chat_descriptions(
        phone_number: str,
        ctx: Context,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Generate and persist AI descriptions for the most recent WhatsApp chats.

        USE WHEN: You want to enrich stored chats with natural-language descriptions.
        Normally called automatically by sync_chats; invoke manually if descriptions
        are missing or stale.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - limit: Maximum chats to describe (default 50).

        OUTPUT: processed (count), skipped (count).
        """
        user = await c.user_service.get_or_create(phone_number)
        llm = McpLLMAdapter(ctx)
        return await c.chat_service.generate_descriptions(
            session=phone_number, user_id=user.id, llm=llm, limit=limit
        )
