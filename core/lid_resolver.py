"""LidResolver — single, cached LID → JID resolution used throughout the codebase.

Previously duplicated six times across adapters, services, and webhook processor.
Now one class, one cache, one fallback chain, injected everywhere.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from helpers.jid import is_lid_jid, strip_suffix

if TYPE_CHECKING:
    from ports.messaging import IMessagingPort
    from ports.repositories import IChatRepo, IContactProfileRepo

logger = logging.getLogger(__name__)


class LidResolver:
    """Resolves WhatsApp LID identifiers to phone JIDs.

    Fallback chain for each LID:
      1. In-memory cache (process-local, keyed by raw LID string)
      2. MongoDB ``whatsapp_chats.w_lid`` lookup
      3. WAHA ``GET /{session}/lids/{lid}`` API call
      4. Raw LID string as last resort

    Also provides ``build_sender_map()`` which pre-resolves all senders in a
    message list so the pure ``helpers.conversation.build_conversation_text``
    can be called synchronously.
    """

    def __init__(
        self,
        messaging: IMessagingPort,
        chat_repo: IChatRepo,
        contact_profile_repo: IContactProfileRepo | None = None,
    ) -> None:
        self._messaging = messaging
        self._chat_repo = chat_repo
        self._contact_profile_repo = contact_profile_repo
        self._cache: dict[str, str] = {}

    async def resolve(self, jid: str, session: str) -> str:
        """Resolve *jid* to a phone JID.  Returns *jid* unchanged if not a LID."""
        if not is_lid_jid(jid):
            return jid
        if jid in self._cache:
            return self._cache[jid]

        resolved: str | None = None

        with contextlib.suppress(Exception):
            doc = await self._chat_repo.find_by_lid(jid)
            if doc and doc.get("w_chat_id"):
                resolved = doc["w_chat_id"]

        if not resolved and session:
            with contextlib.suppress(Exception):
                resp = await self._messaging.get_chat_id_by_lids(
                    session=session, lid=jid.split("@")[0]
                )
                resolved = resp.pn

        result = resolved or jid
        self._cache[jid] = result
        return result

    async def resolve_sender_name(
        self,
        raw_jid: str,
        session: str,
        name_cache: dict[str, str],
    ) -> str:
        """Resolve a sender JID to a human-readable display name.

        Resolution chain:
          - Non-LID JIDs: name_cache → contact_profiles → stripped phone number
          - LID JIDs:     name_cache → whatsapp_chats.chat_name → WAHA API → stripped LID
        """
        if not raw_jid:
            return ""
        if raw_jid in name_cache:
            return name_cache[raw_jid]

        resolved: str | None = None

        if not is_lid_jid(raw_jid):
            if self._contact_profile_repo:
                with contextlib.suppress(Exception):
                    doc = await self._contact_profile_repo.find_by_contact_id(raw_jid)
                    if doc and doc.get("name"):
                        resolved = doc["name"]
            resolved = resolved or strip_suffix(raw_jid)
        else:
            with contextlib.suppress(Exception):
                doc = await self._chat_repo.find_by_lid(raw_jid)
                if doc:
                    resolved = doc.get("chat_name") or strip_suffix(
                        doc.get("w_chat_id", "")
                    )
            if not resolved and session:
                with contextlib.suppress(Exception):
                    lid_resp = await self._messaging.get_chat_id_by_lids(
                        session=session, lid=raw_jid.split("@")[0]
                    )
                    resolved = strip_suffix(lid_resp.pn)
            resolved = resolved or raw_jid.split("@")[0]

        name_cache[raw_jid] = resolved or ""
        return name_cache[raw_jid]

    async def build_sender_map(
        self,
        messages: list[dict[str, Any]],
        is_group: bool,
        session: str,
    ) -> dict[str, str]:
        """Pre-resolve all unique sender JIDs in *messages* to display names.

        Returns a mapping suitable for passing to
        ``helpers.conversation.build_conversation_text``.
        """
        jids: set[str] = set()
        for msg in messages:
            if not msg.get("fromMe"):
                jid = (msg.get("participant") if is_group else msg.get("from")) or ""
                if jid:
                    jids.add(jid)

        name_cache: dict[str, str] = {}
        for jid in jids:
            await self.resolve_sender_name(jid, session, name_cache)
        return name_cache
