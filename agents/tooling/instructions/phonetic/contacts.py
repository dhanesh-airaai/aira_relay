"""Phonetic contact search MCP tool handlers — index_contacts and find_contact_by_name."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.embedding import EmbeddingsClass
from config.settings import settings
from db.mongodb.manager import mongo
from db.qdrant.manager import qdrant
from models.waha.args import FindContactByNameArgs
from adapters.waha import WahaClient
from agents.tooling.services.phonetic.contacts import WhatsappPhoneticSearch
from agents.tooling.services.waha.service import WahaService

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Module-level singletons — built once at import time
_waha_client = WahaClient(
    base_url=settings.waha_base_url,
    api_key=settings.waha_api_key,
    webhook_secret=settings.waha_webhook_secret,
)
_phonetic_search = WhatsappPhoneticSearch(
    qdrant=qdrant,
    mongo=mongo,
    embeddings=EmbeddingsClass(settings),
    embed_concurrency=settings.contacts_embed_concurrency,
    search_concurrency=settings.contacts_search_concurrency,
)
_service = WahaService(
    client=_waha_client,
    mongo=mongo,
    phonetic_search=_phonetic_search,
)


def register_contacts_tools(mcp: FastMCP) -> None:
    """Register phonetic contact search tools with a FastMCP server instance."""

    @mcp.tool()
    async def index_contacts(
        session: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Index WhatsApp contacts in Qdrant for phonetic name search.

        USE WHEN: Initial setup or after adding new contacts — must be called before
        find_contact_by_name can use phonetic matching.
        BEHAVIOR: Fetches all contacts from WAHA, encodes names with Metaphone,
        embeds phonetic keys, and upserts them into Qdrant. Skips already-indexed contacts.
        - session: WAHA session name.
        - user_id: Relay user identifier.
        OUTPUT: status — 'ok' with indexed_points count, or 'skipped' with reason.
        """
        return await _service.index_contacts(session=session, user_id=user_id)

    @mcp.tool()
    async def find_contact_by_name(
        query: str,
        session: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Find WhatsApp contacts by name using phonetic search (Metaphone + Qdrant).

        USE WHEN: Need to find a contact by name — supports fuzzy/phonetic matching
        (e.g. 'Jon' matches 'John', 'Smit' matches 'Smith').
        PREREQUISITE: Call index_contacts once before using this tool.
        WORKFLOW: Use returned w_chat_id with send_text_message to message them.
        - query: Contact name to search for (partial or phonetically similar OK).
        OUTPUT: contacts — list of matching contacts with w_chat_id and chat_name.
        """
        args = FindContactByNameArgs(
            query=query,
            session=session,
            user_id=user_id,
        )
        result = await _service.find_contact_by_name(args)
        return result.model_dump()
