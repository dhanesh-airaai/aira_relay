"""ChatService — chat sync, retrieval, and AI description generation."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from helpers.jid import is_group_jid
from models.chat import WhatsappChatType
from models.responses import SyncResult

if TYPE_CHECKING:
    from core.contact_service import ContactService
    from core.lid_resolver import LidResolver
    from ports.event_bus import IEventBus
    from ports.llm import ILLMAdapter
    from ports.messaging import IMessagingPort
    from ports.repositories import IChatRepo

logger = logging.getLogger(__name__)

_DESCRIPTION_SYSTEM = (
    "You are a concise assistant. Generate a 1-2 sentence description of this WhatsApp chat "
    "based on the recent conversation. Describe who the chat is with or what the group is about, "
    "and the main topics or activities discussed. Be specific and useful. "
    "Return only the description, nothing else."
)
_DESCRIPTION_CONCURRENCY = 3
_DESCRIPTION_MESSAGES_LIMIT = 100


class ChatService:
    """Handles chat synchronisation, listing, and description generation."""

    def __init__(
        self,
        messaging: IMessagingPort,
        chat_repo: IChatRepo,
        lid_resolver: LidResolver,
        contact_svc: ContactService,
        event_bus: IEventBus,
    ) -> None:
        self._messaging = messaging
        self._chat_repo = chat_repo
        self._lid_resolver = lid_resolver
        self._contact_svc = contact_svc
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    async def sync_chats(self, *, session: str, user_id: str) -> SyncResult:
        """Fetch all WAHA chats and upsert them into MongoDB."""
        if not session:
            return SyncResult(success=False, message="No session provided.", total_synced=0)
        try:
            total = await self._sync_once(session=session, user_id=user_id)
            return SyncResult(success=True, message=f"Synced {total} chats.", total_synced=total)
        except Exception as exc:
            logger.exception("sync_chats error for user %s", user_id)
            return SyncResult(success=False, message=f"Sync failed: {exc}", total_synced=0)

    async def _sync_once(self, *, session: str, user_id: str) -> int:
        lid_result, all_chats, all_contacts = await asyncio.gather(
            self._messaging.get_all_lids(session=session),
            self._messaging.get_all_chats(
                session=session,
                sort_by="conversationTimestamp",
                sort_order="desc",
            ),
            self._messaging.get_all_contacts(session=session),
            return_exceptions=True,
        )

        if isinstance(lid_result, BaseException):
            logger.warning("get_all_lids failed (session may not be WORKING): %s", lid_result)
            lid_mappings: list = []
        else:
            lid_mappings = lid_result

        if isinstance(all_chats, BaseException):
            raise all_chats  # chats are required — propagate
        if isinstance(all_contacts, BaseException):
            logger.warning("get_all_contacts failed: %s", all_contacts)
            all_contacts = []

        lid_to_phone: dict[str, str] = {item.lid: item.pn for item in lid_mappings}

        # Build a JID → name lookup from the contacts list
        contact_name_map: dict[str, str] = {}
        for contact in all_contacts:
            cid = str(contact.get("id") or "")
            if not cid:
                continue
            name = (
                contact.get("name")
                or contact.get("pushname")
                or ""
            )
            if name:
                # Normalise: strip @c.us suffix for key lookup
                key = cid.split("@")[0]
                contact_name_map[key] = name
                contact_name_map[cid] = name

        groups = [c for c in all_chats if is_group_jid(str(c.get("id", "")))]
        dms = [c for c in all_chats if not is_group_jid(str(c.get("id", "")))]
        logger.info(
            "Fetched %d total chats, %d contacts for user %s (%d groups, %d DMs)",
            len(all_chats), len(all_contacts), user_id, len(groups), len(dms),
        )

        chats_to_store: list[dict[str, Any]] = []

        # Group chats
        for group in groups:
            chat_id = str(group.get("id", ""))
            if not chat_id:
                continue
            chats_to_store.append(
                {
                    "user_id": user_id,
                    "w_chat_id": chat_id,
                    "chat_name": str(group.get("name") or ""),
                    "type": WhatsappChatType.GROUP.value,
                    "w_lid": chat_id,
                    "conversation_timestamp": int(group.get("conversation_timestamp") or 0),
                }
            )

        # DM chats — resolve LIDs, fill names from contact map, then fetch stragglers
        dm_info: list[dict[str, Any]] = []
        needing_name: list[tuple[int, str]] = []

        for dm in dms:
            raw_id = str(dm.get("id", ""))
            if not raw_id:
                continue
            chat_id = lid_to_phone.get(raw_id, raw_id) if raw_id.endswith("@lid") else raw_id
            # Name from WAHA chat list, then fall back to contacts map
            chat_name = str(dm.get("name") or "")
            if not chat_name:
                chat_name = contact_name_map.get(chat_id) or contact_name_map.get(chat_id.split("@")[0]) or ""
            idx = len(dm_info)
            dm_info.append(
                {
                    "chat_id": chat_id,
                    "chat_name": chat_name,
                    "w_lid": raw_id,
                    "timestamp": int(dm.get("conversation_timestamp") or 0),
                }
            )
            if not chat_name:
                needing_name.append((idx, chat_id))

        if needing_name:
            results = await asyncio.gather(
                *[
                    self._messaging.get_contact_details(session=session, contact_id=cid)
                    for _, cid in needing_name
                ],
                return_exceptions=True,
            )
            for (idx, cid), detail in zip(needing_name, results, strict=True):
                if isinstance(detail, BaseException):
                    dm_info[idx]["chat_name"] = cid.split("@")[0]
                else:
                    dm_info[idx]["chat_name"] = (
                        detail.name
                        or detail.pushname
                        or detail.short_name
                        or cid.split("@")[0]
                    )

        chats_to_store.extend(
            {
                "user_id": user_id,
                "w_chat_id": str(info["chat_id"]),
                "chat_name": str(info["chat_name"]),
                "type": WhatsappChatType.CHAT.value,
                "w_lid": str(info["w_lid"]),
                "conversation_timestamp": int(info["timestamp"]),
            }
            for info in dm_info
        )

        if chats_to_store:
            await asyncio.gather(
                *[
                    self._chat_repo.upsert(
                        {"user_id": user_id, "w_chat_id": c["w_chat_id"]}, c
                    )
                    for c in chats_to_store
                ]
            )
            logger.info("Synced %d chats for user %s", len(chats_to_store), user_id)
            # Index all synced chats in the phonetic search
            contacts_for_index = [
                {"id": c["w_chat_id"], "name": c["chat_name"]}
                for c in chats_to_store
                if c.get("chat_name")
            ]
            if contacts_for_index:
                logger.info("Indexing %d chats in Qdrant for user %s", len(contacts_for_index), user_id)
                try:
                    await self._contact_svc.add_to_phonetic_index(
                        contacts_for_index, user_id=user_id
                    )
                except Exception:
                    logger.exception("Failed to index chats in Qdrant for user %s", user_id)

        return len(chats_to_store)

    # ------------------------------------------------------------------
    # On-demand chat creation (called from webhook processor)
    # ------------------------------------------------------------------

    async def get_or_create_chat(
        self,
        *,
        session: str,
        user_id: str,
        chat_id: str,
        w_lid: str,
        from_timestamp: int,
    ) -> dict[str, Any] | None:
        """Look up a chat by ID, creating it from WAHA data if not found."""
        doc = await self._chat_repo.find_by_chat_id(chat_id)
        if not doc:
            doc = await self._chat_repo.find_by_lid(w_lid)
        if doc:
            return doc
        return await self._create_on_demand(
            session=session,
            user_id=user_id,
            chat_id=chat_id,
            w_lid=w_lid,
            from_timestamp=from_timestamp,
        )

    async def _create_on_demand(
        self,
        *,
        session: str,
        user_id: str,
        chat_id: str,
        w_lid: str,
        from_timestamp: int,
    ) -> dict[str, Any] | None:
        try:
            if is_group_jid(chat_id):
                try:
                    group_data = await self._messaging.get_group(
                        session=session, group_id=chat_id
                    )
                    chat_name = group_data.get("name") or chat_id.split("@")[0]
                except Exception:
                    chat_name = chat_id.split("@")[0]
                chat_type = WhatsappChatType.GROUP.value
            elif chat_id.endswith("@c.us"):
                try:
                    contact = await self._messaging.get_contact_details(
                        contact_id=chat_id, session=session
                    )
                    chat_name = contact.name or contact.pushname or chat_id.split("@")[0]
                except Exception:
                    chat_name = chat_id.split("@")[0]
                chat_type = WhatsappChatType.CHAT.value
            else:
                return None

            doc: dict[str, Any] = {
                "user_id": user_id,
                "w_chat_id": chat_id,
                "w_lid": w_lid,
                "chat_name": chat_name,
                "type": chat_type,
                "conversation_timestamp": from_timestamp,
            }
            await self._chat_repo.upsert({"user_id": user_id, "w_chat_id": chat_id}, doc)
            try:
                await self._contact_svc.add_to_phonetic_index(
                    [{"id": chat_id, "name": chat_name}], user_id=user_id
                )
            except Exception:
                logger.exception("Failed to index chat %s in Qdrant for user %s", chat_id, user_id)
            logger.info("Created chat on demand: %s (%s) for user %s", chat_name, chat_id, user_id)
            return doc
        except Exception:
            logger.exception("Failed to create chat on demand for %s", chat_id)
            return None

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def get_chats(
        self,
        *,
        user_id: str,
        limit: int = 5000,
        offset: int = 0,
        chat_type: str | None = None,
        moderated_only: bool = False,
    ) -> list[dict[str, Any]]:
        filter_: dict[str, Any] = {"user_id": user_id}
        if chat_type:
            filter_["type"] = chat_type
        if moderated_only:
            filter_["moderation_status"] = True

        chats = await self._chat_repo.find_many(
            filter_,
            limit=limit,
            sort=[("conversation_timestamp", -1)],
        )
        if offset:
            chats = chats[offset:]
        return [{k: v for k, v in c.items() if k != "_id"} for c in chats]

    # ------------------------------------------------------------------
    # AI description generation
    # ------------------------------------------------------------------

    async def generate_descriptions(
        self,
        *,
        session: str,
        user_id: str,
        llm: ILLMAdapter,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Generate and persist AI descriptions for the most-recent chats."""
        chats = await self._chat_repo.find_many(
            {"user_id": user_id},
            limit=limit,
            sort=[("conversation_timestamp", -1)],
        )
        if not chats:
            return {"processed": 0, "skipped": 0}

        sem = asyncio.Semaphore(_DESCRIPTION_CONCURRENCY)
        descriptions: dict[str, str] = {}

        async def _describe(chat: dict[str, Any]) -> bool:
            async with sem:
                chat_id: str = chat.get("w_chat_id") or ""
                chat_name: str = chat.get("chat_name") or ""
                if not chat_id:
                    return False
                try:
                    messages = await self._messaging.get_messages(
                        session=session,
                        chat_id=chat_id,
                        limit=_DESCRIPTION_MESSAGES_LIMIT,
                        download_media=False,
                    )
                    if not messages:
                        return False
                    lines = [
                        ("[Me]" if m.get("fromMe") else "[Other]") + f": {t}"
                        for m in messages
                        if (t := m.get("body") or m.get("text"))
                    ]
                    if not lines:
                        return False

                    chat_type = "group" if is_group_jid(chat_id) else "direct message"
                    desc = await llm.complete(
                        f"Chat name: {chat_name}\nType: {chat_type}\n\nRecent messages:\n"
                        + "\n".join(lines),
                        system_prompt=_DESCRIPTION_SYSTEM,
                        max_tokens=200,
                        session=session,
                    )
                    if desc:
                        await self._chat_repo.upsert(
                            {"user_id": user_id, "w_chat_id": chat_id},
                            {"description": desc},
                        )
                        descriptions[chat_id] = desc
                    return bool(desc)
                except Exception:
                    logger.exception("Failed to describe chat %s (%s)", chat_name, chat_id)
                    return False

        results = await asyncio.gather(*[_describe(c) for c in chats])
        processed = sum(1 for r in results if r)
        return {"processed": processed, "skipped": len(chats) - processed, "descriptions": descriptions}
