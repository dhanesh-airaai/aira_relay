"""MCP tools — contact lookup and phonetic search."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from relay_mcp.container import McpContainer


def register_contact_tools(mcp: FastMCP, c: McpContainer) -> None:

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
        by name, or needs to pick a recipient before sending a message.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).
        - limit: Maximum contacts to return (None = all).
        - offset: Contacts to skip for pagination.
        - sort_by: Field to sort by (e.g. 'name').
        - sort_order: 'asc' or 'desc'.

        OUTPUT: success, data (list of contact objects with id, name, pushname, number).
        """
        await c.user_service.get_or_create(phone_number)
        return await c.contact_service.get_all_contacts(
            session=phone_number,
            limit=limit or 1000,
            offset=offset or 0,
            sort_by=sort_by or "name",
            sort_order=sort_order or "asc",
        )

    @mcp.tool()
    async def get_contact_details(
        contact_id: str,
        phone_number: str,
    ) -> dict[str, Any]:
        """Get detailed profile information for a specific WhatsApp contact.

        USE WHEN: The user asks about a specific contact's profile, or when you need to
        confirm the correct chat_id for a person before messaging them.

        PARAMETERS:
        - contact_id: WhatsApp JID of the contact (e.g. '919876543210@c.us').
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).

        OUTPUT: success, data (id, name, pushname, short_name, number, is_business, profile_pic_url).
        """
        await c.user_service.get_or_create(phone_number)
        return await c.contact_service.get_contact_details(
            session=phone_number, contact_id=contact_id
        )

    @mcp.tool()
    async def get_group(
        group_id: str,
        phone_number: str,
    ) -> dict[str, Any]:
        """Get metadata and participant list for a specific WhatsApp group.

        USE WHEN: The user asks about a group (who's in it, admins, description, etc.),
        or when you need group details before sending a message.

        PARAMETERS:
        - group_id: WhatsApp group JID (e.g. '1234567890-1234567890@g.us').
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).

        OUTPUT: success, data (id, name, description, participants, size).
        """
        await c.user_service.get_or_create(phone_number)
        return await c.contact_service.get_group(
            session=phone_number, group_id=group_id
        )

    @mcp.tool()
    async def search_contact_by_name(
        query: str,
        phone_number: str,
    ) -> dict[str, Any]:
        """Search WhatsApp contacts by name using fuzzy phonetic matching.

        USE WHEN: The user asks to message someone by name (e.g. "message John") but
        you don't have their chat_id. Uses Metaphone phonetic matching and semantic
        search via Qdrant for fuzzy, typo-tolerant name lookup.

        PARAMETERS:
        - query: Name to search for (partial or phonetic OK — 'Jon' matches 'John').
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).

        OUTPUT: success, contacts (list of w_chat_id, chat_name, description), message.
        """
        user = await c.user_service.get_or_create(phone_number)
        if not query:
            return {
                "success": False,
                "contacts": [],
                "message": "Query string is required.",
            }
        matches = await c.contact_service.find_contact_by_name(
            query=query,
            user_id=user.id,
            session=phone_number,
        )
        if not matches:
            return {
                "success": True,
                "contacts": [],
                "message": f"No contacts found matching '{query}'.",
            }
        return {
            "success": True,
            "contacts": [m.model_dump() for m in matches],
            "message": f"Found {len(matches)} contact(s) matching '{query}'.",
        }

    @mcp.tool()
    async def sync_contacts(
        phone_number: str,
    ) -> dict[str, Any]:
        """Fetch all WhatsApp contacts and rebuild the phonetic search index.

        USE WHEN: Called once after initial setup, or when new contacts have been added
        and phonetic search results seem outdated.

        PARAMETERS:
        - phone_number: Connected WhatsApp phone number — country code followed by number,
          no spaces or symbols (e.g. 917995154159).

        OUTPUT: status, indexed_points (number of Qdrant points written).
        """
        user = await c.user_service.get_or_create(phone_number)
        return await c.contact_service.index_all_contacts(
            session=phone_number, user_id=user.id
        )
