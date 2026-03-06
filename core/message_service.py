"""MessageService — all messaging operations and conversation scanning."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from helpers.conversation import build_conversation_text
from helpers.jid import is_lid_jid, to_c_us
from models.responses import ScanResult

if TYPE_CHECKING:
    from core.lid_resolver import LidResolver
    from ports.llm import ILLMAdapter
    from ports.messaging import IMessagingPort
    from ports.repositories import IChatRepo, IStateRepo

logger = logging.getLogger(__name__)

_MESSAGES_SUMMARY_SYSTEM = (
    "You are a concise assistant summarizing WhatsApp conversation history. "
    "Summarize the key points, decisions, and action items from the conversation. "
    "Be factual and concise."
)
_SCAN_SUMMARY_SYSTEM = (
    "You are a WhatsApp assistant. The user has unreplied messages from their contacts. "
    "Summarize what needs attention: who messaged, what they said, and any required actions. "
    "Be concise and actionable."
)

_WAHA_CONCURRENCY = 10


class MessageService:
    """Handles all send/receive/scan operations for WhatsApp messages."""

    def __init__(
        self,
        messaging: IMessagingPort,
        chat_repo: IChatRepo,
        state_repo: IStateRepo,
        lid_resolver: LidResolver,
    ) -> None:
        self._messaging = messaging
        self._chat_repo = chat_repo
        self._state_repo = state_repo
        self._lid_resolver = lid_resolver
        self._sem = asyncio.Semaphore(_WAHA_CONCURRENCY)

    # ------------------------------------------------------------------
    # Send operations
    # ------------------------------------------------------------------

    async def send_text(
        self,
        *,
        session: str,
        chat_id: str,
        text: str,
        reply_to: str | None = None,
        mentions: list[str] | None = None,
        link_preview: bool = True,
        link_preview_high_quality: bool = False,
    ) -> dict[str, Any]:
        data = await self._messaging.send_text(
            session=session,
            chat_id=chat_id,
            text=text,
            reply_to=reply_to,
            mentions=mentions,
            link_preview=link_preview,
            link_preview_high_quality=link_preview_high_quality,
        )
        return {"success": True, "message_id": data.get("id"), "data": data}

    async def send_image(
        self,
        *,
        session: str,
        chat_id: str,
        file_name: str = "image.jpg",
        file_mimetype: str = "image/jpeg",
        caption: str | None = None,
        file_url: str | None = None,
        file_data: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        data = await self._messaging.send_image(
            session=session,
            chat_id=chat_id,
            file_name=file_name,
            file_mimetype=file_mimetype,
            caption=caption,
            file_url=file_url,
            file_data=file_data,
            reply_to=reply_to,
        )
        return {"success": True, "message_id": data.get("id"), "data": data}

    async def send_file(
        self,
        *,
        session: str,
        chat_id: str,
        file_name: str = "file",
        file_mimetype: str = "application/octet-stream",
        caption: str | None = None,
        file_url: str | None = None,
        file_data: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        data = await self._messaging.send_file(
            session=session,
            chat_id=chat_id,
            file_name=file_name,
            file_mimetype=file_mimetype,
            caption=caption,
            file_url=file_url,
            file_data=file_data,
            reply_to=reply_to,
        )
        return {"success": True, "message_id": data.get("id"), "data": data}

    async def send_voice(
        self,
        *,
        session: str,
        chat_id: str,
        voice_url: str | None = None,
        voice_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        data = await self._messaging.send_voice(
            session=session,
            chat_id=chat_id,
            voice_url=voice_url,
            voice_base64=voice_base64,
            reply_to=reply_to,
        )
        return {"success": True, "message_id": data.get("id"), "data": data}

    async def send_video(
        self,
        *,
        session: str,
        chat_id: str,
        caption: str | None = None,
        video_url: str | None = None,
        video_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        data = await self._messaging.send_video(
            session=session,
            chat_id=chat_id,
            caption=caption,
            video_url=video_url,
            video_base64=video_base64,
            reply_to=reply_to,
        )
        return {"success": True, "message_id": data.get("id"), "data": data}

    async def delete_message(
        self, *, session: str, chat_id: str, message_id: str
    ) -> dict[str, Any]:
        await self._messaging.delete_message(
            session=session, chat_id=chat_id, message_id=message_id
        )
        return {"success": True}

    async def edit_message(
        self,
        *,
        session: str,
        chat_id: str,
        message_id: str,
        new_text: str,
        link_preview: bool = True,
    ) -> dict[str, Any]:
        data = await self._messaging.edit_message(
            session=session,
            chat_id=chat_id,
            message_id=message_id,
            new_text=new_text,
            link_preview=link_preview,
        )
        return {"success": True, "message_id": data.get("id"), "data": data}

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def get_messages_summary(
        self,
        *,
        session: str,
        chat_id: str,
        is_group: bool,
        llm: ILLMAdapter,
        limit: int = 100,
        offset: int | None = None,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        download_media: bool = False,
        query: str | None = None,
    ) -> dict[str, Any]:
        raw = await self._messaging.get_messages(
            session=session,
            chat_id=chat_id,
            limit=limit,
            offset=offset,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            download_media=download_media,
        )
        sender_map = await self._lid_resolver.build_sender_map(raw, is_group, session)
        text = build_conversation_text(raw, is_group, sender_map)
        if not text:
            return {"summary": "No messages found in this chat.", "message_count": 0}

        query_ctx = f"\n\nFocus your summary on: {query}" if query else ""
        summary = await llm.complete(
            f"Conversation:\n{text}{query_ctx}",
            system_prompt=_MESSAGES_SUMMARY_SYSTEM,
            max_tokens=1024,
        )
        return {"summary": summary, "message_count": len(raw)}

    async def get_messages_with_id(
        self,
        *,
        session: str,
        chat_id: str,
        is_group: bool,
        limit: int = 100,
        offset: int | None = None,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        download_media: bool = False,
    ) -> dict[str, Any]:
        raw = await self._messaging.get_messages(
            session=session,
            chat_id=chat_id,
            limit=limit,
            offset=offset,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            download_media=download_media,
        )
        sender_map = await self._lid_resolver.build_sender_map(raw, is_group, session)
        text = build_conversation_text(raw, is_group, sender_map)
        return {"raw_messages": raw, "conversation_text": text}

    # ------------------------------------------------------------------
    # Scan unreplied messages
    # ------------------------------------------------------------------

    @staticmethod
    def _get_mentioned_jids(msg: dict[str, Any]) -> list[str]:
        return (
            msg.get("_data", {})
            .get("Message", {})
            .get("extendedTextMessage", {})
            .get("contextInfo", {})
            .get("mentionedJID")
            or []
        )

    async def _resolve_jid_to_cus(
        self, jid: str, session: str, cache: dict[str, str]
    ) -> str:
        if jid in cache:
            return cache[jid]
        if not is_lid_jid(jid):
            cache[jid] = jid
            return jid

        resolved: str | None = None
        with contextlib.suppress(Exception):
            doc = await self._chat_repo.find_by_lid(jid)
            if doc and doc.get("w_chat_id"):
                resolved = doc["w_chat_id"]
        if not resolved:
            with contextlib.suppress(Exception):
                resp = await self._messaging.get_chat_id_by_lids(
                    session=session, lid=jid.split("@")[0]
                )
                resolved = resp.pn

        result = resolved or jid
        cache[jid] = result
        return result

    async def _fetch_dm_convos(
        self,
        session: str,
        dm_chats: list[dict[str, Any]],
        from_ts: int,
    ) -> dict[str, str]:
        results: dict[str, str] = {}

        async def _process(chat: dict[str, Any]) -> tuple[str, str] | None:
            async with self._sem:
                chat_id = chat["id"]
                msgs = await self._messaging.get_chat_messages(
                    session=session,
                    chat_id=chat_id,
                    limit=1000,
                    from_timestamp=from_ts,
                    download_media=False,
                    sort_by="timestamp",
                    sort_order="asc",
                )
                if not msgs or msgs[-1].get("fromMe"):
                    return None
                sender_map = await self._lid_resolver.build_sender_map(msgs, False, session)
                text = build_conversation_text(msgs, False, sender_map)
                return (chat_id, text) if text else None

        gathered = await asyncio.gather(*[_process(c) for c in dm_chats], return_exceptions=True)
        for item in gathered:
            if isinstance(item, BaseException):
                logger.warning("DM fetch error: %s", item)
            elif item:
                results[item[0]] = item[1]
        return results

    async def _fetch_group_convos(
        self,
        session: str,
        group_chats: list[dict[str, Any]],
        from_ts: int,
        user_cid: str,
    ) -> dict[str, str]:
        results: dict[str, str] = {}
        lid_cache: dict[str, str] = {}

        for chat in group_chats:
            chat_id = chat["id"]
            try:
                msgs = await self._messaging.get_chat_messages(
                    session=session,
                    chat_id=chat_id,
                    limit=1000,
                    from_timestamp=from_ts,
                    download_media=False,
                    sort_by="timestamp",
                    sort_order="asc",
                )
                if not msgs:
                    continue

                first_mention: int | None = None
                for i, msg in enumerate(msgs):
                    for jid in self._get_mentioned_jids(msg):
                        resolved = await self._resolve_jid_to_cus(jid, session, lid_cache)
                        if resolved == user_cid:
                            first_mention = i
                            break
                    if first_mention is not None:
                        break

                if first_mention is None:
                    continue

                relevant = msgs[first_mention:]
                sender_map = await self._lid_resolver.build_sender_map(relevant, True, session)
                text = build_conversation_text(relevant, True, sender_map)
                if text:
                    results[chat_id] = text
            except Exception as exc:
                logger.warning("Group fetch error for %s: %s", chat_id, exc)

        return results

    async def scan_unreplied(
        self,
        *,
        session: str,
        user_id: str,
        llm: ILLMAdapter,
    ) -> ScanResult:
        """Scan recent chats for unreplied DMs and @mention-containing groups."""
        state = await self._state_repo.find_by_user_id(user_id)
        if state and state.get("last_checkin_at"):
            raw_ts = state["last_checkin_at"]
            last_checked = (
                raw_ts
                if isinstance(raw_ts, datetime)
                else datetime.fromisoformat(str(raw_ts))
            )
        else:
            last_checked = datetime.now(UTC) - timedelta(hours=24)

        user_w_lid: str = (state or {}).get("user_w_lid", "")
        if not user_w_lid:
            with contextlib.suppress(Exception):
                resp = await self._messaging.get_lid_by_phone(session=session, phone=session)
                user_w_lid = resp.lid
                await self._state_repo.upsert(user_id, {"user_w_lid": user_w_lid})

        all_chats = await self._messaging.get_all_chats(
            session=session,
            sort_by="conversationTimestamp",
            sort_order="desc",
            total_limit=100,
        )

        dm_chats = [c for c in all_chats if not str(c.get("id", "")).endswith("@g.us")]
        group_chats = [c for c in all_chats if str(c.get("id", "")).endswith("@g.us")]
        from_ts = int(last_checked.timestamp())
        user_cid = to_c_us(session)

        dm_convos = await self._fetch_dm_convos(session, dm_chats, from_ts)
        group_convos = await self._fetch_group_convos(session, group_chats, from_ts, user_cid)

        await self._state_repo.upsert(user_id, {"last_checkin_at": datetime.now(UTC)})

        if not dm_convos and not group_convos:
            return ScanResult(summary="No unreplied messages found.", dm_count=0, group_count=0)

        parts: list[str] = []
        for cid, text in dm_convos.items():
            parts.append(f"[DM from {cid}]\n{text}")
        for cid, text in group_convos.items():
            parts.append(f"[Group {cid} — you were mentioned]\n{text}")

        summary = await llm.complete(
            f"Unreplied messages:\n\n" + "\n\n---\n\n".join(parts),
            system_prompt=_SCAN_SUMMARY_SYSTEM,
            max_tokens=1024,
        )
        return ScanResult(
            summary=summary,
            dm_count=len(dm_convos),
            group_count=len(group_convos),
        )
