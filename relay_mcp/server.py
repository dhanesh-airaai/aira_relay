"""MCP server factory — creates the FastMCP instance and registers all tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from relay_mcp.container import McpContainer


def build_mcp_server(container: McpContainer) -> FastMCP:
    """Create and return a fully-wired FastMCP server.

    All tool registrations receive the shared *container* so they depend on
    injected services, not module-level singletons.
    """
    from relay_mcp.tools.chats import register_chat_tools
    from relay_mcp.tools.connection import register_connection_tools
    from relay_mcp.tools.contacts import register_contact_tools
    from relay_mcp.tools.incoming import register_incoming_tool
    from relay_mcp.tools.messaging import register_messaging_tools

    server = FastMCP("aira-relay")

    register_connection_tools(server, container)
    register_messaging_tools(server, container)
    register_chat_tools(server, container)
    register_contact_tools(server, container)
    register_incoming_tool(server, container)

    return server
