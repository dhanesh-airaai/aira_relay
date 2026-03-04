"""MCP server — registers all relay tools and exposes them via FastMCP."""

import os
import sys

from mcp.server.fastmcp import FastMCP

from agents.tooling.instructions.phonetic.contacts import register_contacts_tools
from agents.tooling.instructions.waha.tools import register_waha_tools

mcp = FastMCP("aira-relay")

# Register WAHA messaging/contact/group tools (12 tools)
register_waha_tools(mcp)

# Register phonetic contact search tools (2 tools)
register_contacts_tools(mcp)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "http":
        print("Starting HTTP MCP server...", file=sys.stderr)
        mcp.run(
            transport="http",
            host="0.0.0.0",  # pyright: ignore[reportCallIssue]
            port=8000,  # pyright: ignore[reportCallIssue]
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
