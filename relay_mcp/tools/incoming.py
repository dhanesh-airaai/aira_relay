"""MCP tool — get_incoming_message: poll for real-time WhatsApp events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context, FastMCP

    from relay_mcp.container import McpContainer


def register_incoming_tool(mcp: FastMCP, c: McpContainer) -> None:

    @mcp.tool()
    async def get_incoming_message(
        ctx: Context,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Wait for and return the next incoming WhatsApp message event.

        USE WHEN: You need to receive incoming WhatsApp messages in real time.
        Call this tool in a continuous loop to act as a live message listener.

        BEHAVIOR:
        - Blocks for up to `timeout` seconds waiting for the next queued message.
        - Returns {"event": "timeout"} if nothing arrives within the window.
        - Registers the current MCP session so the relay can push MCP log
          notifications to it for ALL event types (session.status, sync_chats,
          message) — but this tool's return value only carries message events.
        - Call in a loop: process event, then immediately call again.

        PARAMETERS:
        - timeout: Maximum seconds to wait (default 30).

        OUTPUT (one of):

        Incoming message (event = 'message'):
        - session, chat_id, chat_name, chat_type, user_id, sender_phone,
          body, timestamp, message_id, has_media, media_url, media_mimetype, content

        Timeout: {"event": "timeout", "message": "No new messages in Xs"}

        NOTE: session.status and sync_chats events are delivered as MCP log
        notifications to the registered session, not via this tool's return value.
        """
        await c.mcp_handler.register_session(ctx.request_context.session)
        event = await c.mcp_handler.pop_incoming(timeout=float(timeout))
        if event is None:
            return {"event": "timeout", "message": f"No new messages in {timeout}s"}
        return event
