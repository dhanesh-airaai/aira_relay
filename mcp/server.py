import os
import sys

from mcp.server.fastmcp import FastMCP

from core.whatsapp import send_message

mcp = FastMCP("aira-relay")


@mcp.tool()
async def whatsapp_send(contact: str, message: str) -> str:
    """
    Send a WhatsApp message to a contact.

    Args:
        contact: Name or phone number
        message: Message content
    """
    return await send_message(contact, message)


def main():
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
