"""MCP tools — WhatsApp connection management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from relay_mcp.container import McpContainer


def register_connection_tools(mcp: FastMCP, c: McpContainer) -> None:

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
        - user_id: Relay internal user ID.
        - code: 8-digit pairing code (e.g. 'ABCD-1234'). Show this to the user and
          instruct them to open WhatsApp → Settings → Linked Devices → Link with phone
          number → enter this code. The code expires in ~60 seconds.
        - message: Human-readable status message.
        - error: Present only on failure.

        AFTER SUCCESS: Wait for a 'session.status' event via get_incoming_message with
        status='WORKING' to confirm the device is fully linked before proceeding.
        """
        result = await c.connection_service.connect_whatsapp(phone_number=phone_number)
        return result.model_dump()
