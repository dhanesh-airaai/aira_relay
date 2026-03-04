"""WAHA service — business logic layer for all 13 MCP tools."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from db.mongodb.collections import CONTACT_PROFILES, USER_STATE, USERS, WHATSAPP_CHATS
from models.user import User
from models.waha.args import (
    ConnectWhatsappArgs,
    DeleteMessageArgs,
    EditMessageArgs,
    FindContactByNameArgs,
    GetAllContactsArgs,
    GetContactDetailsArgs,
    GetGroupArgs,
    GetMessagesArgs,
    ScanUnrepliedMessagesArgs,
    SendFileMessageArgs,
    SendImageMessageArgs,
    SendTextMessageArgs,
    SendVideoMessageArgs,
    SendVoiceMessageArgs,
)
from models.waha.entities import WhatsappChatType
from models.waha.responses import (
    ConnectWhatsappResponse,
    FindContactByNameResponse,
    MessagesSummaryResponse,
    ScanUnrepliedResponse,
    SyncChatsJobResult,
    SyncChatsStartResponse,
    WahaDataResponse,
    WahaListResponse,
    WahaMessageResponse,
)
from utils.crypto import tokenize

if TYPE_CHECKING:
    from adapters.waha import WahaClient
    from agents.tooling.services.phonetic.contacts import WhatsappPhoneticSearch
    from db.mongodb.manager import MongoManager
    from mcp.server.fastmcp import Context

logger = logging.getLogger(__name__)

_WAHA_CONCURRENCY_LIMIT = 10
_WHATSAPP_NOT_CONNECTED_MSG = (
    "Your WhatsApp is not connected. Ensure phone_number is provided."
)

# ── LLM prompts ────────────────────────────────────────────────────────────────

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

_DESCRIPTION_SYSTEM = (
    "You are a concise assistant. Generate a 1-2 sentence description of this WhatsApp chat "
    "based on the recent conversation. Describe who the chat is with or what the group is about, "
    "and the main topics or activities discussed. Be specific and useful. "
    "Return only the description, nothing else."
)

_DESCRIPTION_CONCURRENCY = 3
_DESCRIPTION_MESSAGES_LIMIT = 100


class WahaService:
    """Business logic layer for WAHA MCP tools."""

    def __init__(
        self,
        client: WahaClient,
        mongo: MongoManager,
        phonetic_search: WhatsappPhoneticSearch | None = None,
    ) -> None:
        self._client = client
        self._mongo = mongo
        self._phonetic_search = phonetic_search
        self._sem = asyncio.Semaphore(_WAHA_CONCURRENCY_LIMIT)
        self._sync_job_owners: dict[str, str] = {}
        self._sync_job_results: dict[str, asyncio.Queue[SyncChatsJobResult]] = {}
        self._sync_job_tasks: dict[str, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_phone(phone_number: str | None) -> str:
        if not phone_number:
            raise ValueError(_WHATSAPP_NOT_CONNECTED_MSG)
        return phone_number

    async def _resolve_sender_name(
        self,
        raw_jid: str,
        session: str,
        cache: dict[str, str],
    ) -> str:
        """Resolve a sender JID to a display name.

        Resolution chain: in-memory cache → MongoDB contact_profiles → WAHA API → raw phone.
        """
        if not raw_jid:
            return ""
        if raw_jid in cache:
            return cache[raw_jid]

        resolved: str | None = None

        if "@lid" not in raw_jid:
            with contextlib.suppress(Exception):
                doc = await self._mongo.find_one(
                    CONTACT_PROFILES,
                    {"contact_id": raw_jid},
                )
                if doc and doc.get("name"):
                    resolved = doc["name"]
            resolved = resolved or self._client.normalize_wa_id(raw_jid)
        else:
            # LID resolution — try MongoDB w_lid field, then WAHA API
            with contextlib.suppress(Exception):
                doc = await self._mongo.find_one(
                    WHATSAPP_CHATS,
                    {"w_lid": raw_jid},
                )
                if doc:
                    resolved = doc.get("chat_name") or self._client.normalize_wa_id(doc.get("w_chat_id", ""))
            if not resolved and session:
                with contextlib.suppress(Exception):
                    lid_resp = await self._client.get_chat_id_by_lids(
                        session=session,
                        lid=raw_jid.split("@")[0],
                    )
                    resolved = self._client.normalize_wa_id(lid_resp.pn)
            resolved = resolved or raw_jid.split("@")[0]

        cache[raw_jid] = resolved or ""
        return cache[raw_jid]

    async def _build_conversation_text(
        self,
        messages: list[dict[str, Any]],
        is_group: bool,
        session: str,
    ) -> str:
        """Build a readable conversation text from raw WAHA messages."""
        lines: list[str] = []
        cache: dict[str, str] = {}
        for msg in messages:
            text = msg.get("body") or msg.get("text")
            if not text:
                continue
            if msg.get("fromMe"):
                prefix = "[Me]"
            else:
                sender_id = (msg.get("participant") if is_group else msg.get("from")) or ""
                sender_name = await self._resolve_sender_name(sender_id, session, cache)
                prefix = f"[{sender_name or 'Unknown'}]"
            lines.append(f"{prefix}: {text}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    async def get_or_create_user(self, phone_number: str) -> User:
        """Return the existing user for this phone number, or create one."""
        from config.settings import settings

        token = tokenize(phone_number, settings.token_secret)

        doc = await self._mongo.find_one(USERS, {"phone_number_token": token})
        if doc:
            return User(
                id=str(doc["_id"]),
                phone_number=doc["phone_number"],
                phone_number_token=doc["phone_number_token"],
                created_at=doc["created_at"],
            )

        now = datetime.now(UTC)
        user_id = await self._mongo.insert_one(
            USERS,
            {"phone_number": phone_number, "phone_number_token": token, "created_at": now},
        )
        return User(
            id=user_id,
            phone_number=phone_number,
            phone_number_token=token,
            created_at=now,
        )

    # ------------------------------------------------------------------
    # Session / connection
    # ------------------------------------------------------------------

    async def connect_whatsapp(self, args: ConnectWhatsappArgs) -> ConnectWhatsappResponse:
        """Connect a WhatsApp account by requesting a phone-number pairing code."""
        import httpx

        phone_number = args.phone_number

        # Ensure user exists (create if first time)
        user = await self.get_or_create_user(phone_number)

        try:
            # Clean up any stale session — ignore errors if none exists
            with contextlib.suppress(Exception):
                await self._client.delete_session(phone_number)

            created_session = await self._client.create_session(name=phone_number)
            session_name: str = created_session["name"]

            start_result = await self._client.start_session(session_name)
            if not start_result:
                return ConnectWhatsappResponse(
                    success=False,
                    user_id=user.id,
                    code=None,
                    message="Failed to start WhatsApp session.",
                    error="Something went wrong. Please try again after some time.",
                )

            # Poll until SCAN_QR_CODE status (3 attempts × 2 s)
            session_details = await self._client.get_session(session_name)
            for _ in range(3):
                if session_details.get("status") == "SCAN_QR_CODE":
                    break
                await asyncio.sleep(2)
                session_details = await self._client.get_session(session_name)
            else:
                return ConnectWhatsappResponse(
                    success=False,
                    user_id=user.id,
                    code=None,
                    message="WhatsApp session is not ready for QR code scanning.",
                    error=(
                        f"Session status: {session_details.get('status')}."
                        " Please try again after some time."
                    ),
                )

            auth_code_response = await self._client.request_auth_code(
                session=session_name,
                phone_number=phone_number,
            )
            verification_code: str = auth_code_response["code"]

            return ConnectWhatsappResponse(
                success=True,
                user_id=user.id,
                code=verification_code,
                message=f"Verification code sent to {phone_number} WhatsApp number.",
                error=None,
            )

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                error = (
                    "WAHA API authentication failed (401). "
                    "Ensure WAHA_API_KEY in .env matches the key the WAHA container was "
                    "started with, then rebuild: docker-compose down && docker-compose up --build."
                )
            else:
                error = f"WAHA returned HTTP {status}: {exc.response.text[:200]}"
            logger.error("connect_whatsapp HTTP error for %s: %s", phone_number, error)
            return ConnectWhatsappResponse(
                success=False,
                user_id=user.id,
                code=None,
                message="Unable to connect WhatsApp at this time.",
                error=error,
            )
        except httpx.NetworkError as exc:
            error = f"Cannot reach WAHA at {self._client._base}: {exc}"
            logger.error("connect_whatsapp network error for %s: %s", phone_number, error)
            return ConnectWhatsappResponse(
                success=False,
                user_id=user.id,
                code=None,
                message="Unable to connect WhatsApp at this time.",
                error=error,
            )

    # ------------------------------------------------------------------
    # Send operations
    # ------------------------------------------------------------------

    async def send_text_message(self, args: SendTextMessageArgs) -> WahaMessageResponse:
        """Send a plain text message."""
        data = await self._client.send_text(
            session=args.session,
            chat_id=args.chat_id,
            text=args.text,
            reply_to=args.reply_to,
            mentions=args.mentions,
            link_preview=args.link_preview,
            link_preview_high_quality=args.link_preview_high_quality,
        )
        return WahaMessageResponse(success=True, message_id=data.get("id"), data=data)

    async def send_image_message(self, args: SendImageMessageArgs) -> WahaMessageResponse:
        """Send an image message."""
        data = await self._client.send_image(
            session=args.session,
            chat_id=args.chat_id,
            caption=args.caption,
            file_url=args.image_url,
            file_data=args.image_base64,
            file_mimetype=args.image_mimetype,
            file_name=args.image_filename,
            reply_to=args.reply_to,
        )
        return WahaMessageResponse(success=True, message_id=data.get("id"), data=data)

    async def send_file_message(self, args: SendFileMessageArgs) -> WahaMessageResponse:
        """Send a file/document message."""
        data = await self._client.send_file(
            session=args.session,
            chat_id=args.chat_id,
            caption=args.caption,
            file_url=args.file_url,
            file_data=args.file_base64,
            file_mimetype=args.file_mimetype,
            file_name=args.file_filename,
            reply_to=args.reply_to,
        )
        return WahaMessageResponse(success=True, message_id=data.get("id"), data=data)

    async def send_voice_message(self, args: SendVoiceMessageArgs) -> WahaMessageResponse:
        """Send a voice message."""
        data = await self._client.send_voice(
            session=args.session,
            chat_id=args.chat_id,
            voice_url=args.voice_url,
            voice_base64=args.voice_base64,
            reply_to=args.reply_to,
        )
        return WahaMessageResponse(success=True, message_id=data.get("id"), data=data)

    async def send_video_message(self, args: SendVideoMessageArgs) -> WahaMessageResponse:
        """Send a video message."""
        data = await self._client.send_video(
            session=args.session,
            chat_id=args.chat_id,
            caption=args.caption,
            video_url=args.video_url,
            video_base64=args.video_base64,
            reply_to=args.reply_to,
        )
        return WahaMessageResponse(success=True, message_id=data.get("id"), data=data)

    async def delete_message(self, args: DeleteMessageArgs) -> WahaDataResponse:
        """Delete a message."""
        await self._client.delete_message(
            session=args.session,
            chat_id=args.chat_id,
            message_id=args.message_id,
        )
        return WahaDataResponse(success=True, data={})

    async def edit_message(self, args: EditMessageArgs) -> WahaMessageResponse:
        """Edit a text message."""
        data = await self._client.edit_message(
            session=args.session,
            chat_id=args.chat_id,
            message_id=args.message_id,
            new_text=args.new_text,
            link_preview=args.link_preview,
        )
        return WahaMessageResponse(success=True, message_id=data.get("id"), data=data)

    # ------------------------------------------------------------------
    # Retrieval operations
    # ------------------------------------------------------------------

    async def get_messages(self, args: GetMessagesArgs, ctx: Context) -> MessagesSummaryResponse:
        """Fetch messages and summarize them via MCP sampling."""
        raw_messages = await self._client.get_messages(
            session=args.session,
            chat_id=args.chat_id,
            limit=args.limit,
            offset=args.offset,
            from_timestamp=args.from_timestamp,
            to_timestamp=args.to_timestamp,
            download_media=args.download_media,
        )

        is_group = args.chat_type.value == "g"
        conversation_text = await self._build_conversation_text(raw_messages, is_group, args.session)

        if not conversation_text:
            return MessagesSummaryResponse(summary="No messages found in this chat.")

        query_context = f"\n\nFocus your summary on: {args.query}" if args.query else ""
        user_prompt = f"Conversation:\n{conversation_text}{query_context}"

        result = await ctx.sample(
            user_prompt,
            system_prompt=_MESSAGES_SUMMARY_SYSTEM,
            max_tokens=1024,
        )
        return MessagesSummaryResponse(summary=result.text)

    async def get_all_contacts(self, args: GetAllContactsArgs) -> WahaListResponse:
        """Get all contacts."""
        contacts = await self._client.get_all_contacts(
            session=args.session,
            limit=args.limit,
            offset=args.offset,
            sort_by=args.sort_by,
            sort_order=args.sort_order,
        )
        return WahaListResponse(success=True, data=contacts)

    async def get_contact_details(self, args: GetContactDetailsArgs) -> WahaDataResponse:
        """Get details of a single contact."""
        details = await self._client.get_contact_details(
            contact_id=args.contact_id,
            session=args.session,
        )
        return WahaDataResponse(success=True, data=details.model_dump())

    async def get_group(self, args: GetGroupArgs) -> WahaDataResponse:
        """Get details of a single group."""
        data = await self._client.get_group(session=args.session, group_id=args.group_id)
        return WahaDataResponse(success=True, data=data)

    async def find_contact_by_name(self, args: FindContactByNameArgs) -> FindContactByNameResponse:
        """Find contacts matching a name query using phonetic search (Metaphone + Qdrant).

        Falls back to case-insensitive substring match if phonetic search is not configured.
        """
        if not args.query:
            return FindContactByNameResponse(
                success=False,
                contacts=[],
                message="Query string is required.",
            )

        if self._phonetic_search is not None:
            matches = await self._phonetic_search.search_contact_by_name(
                query=args.query,
                user_id=args.user_id,
            )
        else:
            # Fallback: simple case-insensitive substring match via WAHA contacts API
            contacts = await self._client.get_all_contacts(session=args.session)
            query_lower = args.query.lower()
            matches = [
                {
                    "w_chat_id": c.get("id", ""),
                    "chat_name": c.get("name") or c.get("pushname") or "",
                    "description": c.get("status") or "",
                }
                for c in contacts
                if query_lower in (c.get("name") or c.get("pushname") or "").lower()
            ]

        if not matches:
            return FindContactByNameResponse(
                success=True,
                contacts=[],
                message=f"No contacts found matching '{args.query}'.",
            )

        return FindContactByNameResponse(
            success=True,
            contacts=matches,
            message=f"Found {len(matches)} contact(s) matching '{args.query}'.",
        )

    async def index_contacts(self, session: str, user_id: str) -> dict[str, Any]:
        """Fetch all WAHA contacts and index them in Qdrant for phonetic search.

        Should be called once after initial setup, and whenever new contacts are added.
        """
        if self._phonetic_search is None:
            return {"status": "skipped", "reason": "phonetic_search_not_configured"}

        contacts = await self._client.get_all_contacts(session=session)
        result = await self._phonetic_search.add_contacts_to_qdrant(
            contacts=contacts,
            user_id=user_id,
        )
        logger.info("index_contacts: %s for user %s", result, user_id)
        return result

    async def _sync_chats_once(self, *, session: str, user_id: str) -> int:
        """Run one full WhatsApp chat sync and return total chats upserted."""
        lid_mappings = await self._client.get_all_lids(session=session)
        lid_to_chat_id: dict[str, str] = {item.lid: item.pn for item in lid_mappings}

        all_chats = await self._client.get_all_chats(
            session=session,
            sort_by="conversationTimestamp",
            sort_order="desc",
        )

        groups = [chat for chat in all_chats if str(chat.get("id", "")).endswith("@g.us")]
        dms = [chat for chat in all_chats if not str(chat.get("id", "")).endswith("@g.us")]

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

        # DMs with LID handling
        dms_needing_contact_fetch: list[tuple[int, str]] = []
        dm_chat_info: list[dict[str, Any]] = []

        for dm in dms:
            chat_id = str(dm.get("id", ""))
            if not chat_id:
                continue
            raw_chat_id = chat_id
            if chat_id.endswith("@lid"):
                chat_id = lid_to_chat_id.get(chat_id) or chat_id

            chat_name = str(dm.get("name") or "")
            dm_chat_info.append(
                {
                    "chat_id": chat_id,
                    "chat_name": chat_name,
                    "w_lid": raw_chat_id,
                    "timestamp": int(dm.get("conversation_timestamp") or 0),
                }
            )
            dm_index = len(dm_chat_info) - 1
            if chat_name == "":
                dms_needing_contact_fetch.append((dm_index, chat_id))

        if dms_needing_contact_fetch:
            contact_details_results = await asyncio.gather(
                *[
                    self._client.get_contact_details(session=session, contact_id=chat_id)
                    for _, chat_id in dms_needing_contact_fetch
                ],
                return_exceptions=True,
            )
            for (idx, chat_id), contact_details in zip(
                dms_needing_contact_fetch,
                contact_details_results,
                strict=True,
            ):
                if isinstance(contact_details, BaseException):
                    dm_chat_info[idx]["chat_name"] = chat_id.split("@")[0]
                else:
                    fallback_name = contact_details.id.split("@")[0]
                    dm_chat_info[idx]["chat_name"] = (
                        contact_details.name
                        or contact_details.pushname
                        or contact_details.short_name
                        or fallback_name
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
            for info in dm_chat_info
        )

        if chats_to_store:
            await asyncio.gather(
                *[
                    self._mongo.upsert_one(
                        WHATSAPP_CHATS,
                        {"user_id": user_id, "w_chat_id": chat["w_chat_id"]},
                        chat,
                    )
                    for chat in chats_to_store
                ]
            )

            if self._phonetic_search is not None:
                contacts_for_index = [
                    {"id": chat["w_chat_id"], "name": chat["chat_name"]}
                    for chat in chats_to_store
                    if chat.get("chat_name")
                ]
                if contacts_for_index:
                    with contextlib.suppress(Exception):
                        await self._phonetic_search.add_contacts_to_qdrant(
                            contacts=contacts_for_index,
                            user_id=user_id,
                        )

        return len(chats_to_store)

    async def sync_chats_stream(
        self,
        *,
        session: str,
        user_id: str,
    ) -> AsyncGenerator[dict[str, Any]]:
        """Stream sync progress events (pending -> complete/error)."""
        yield {
            "event": "waha_sync_pending",
            "data": {"message": "Starting chat sync...", "step": "init"},
        }
        try:
            total_synced = await self._sync_chats_once(session=session, user_id=user_id)
            yield {
                "event": "complete",
                "data": {
                    "success": True,
                    "message": f"Synced {total_synced} chats.",
                    "total_synced": total_synced,
                },
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("sync_chats_stream error for user %s", user_id)
            yield {
                "event": "error",
                "data": {"message": f"Sync failed due to an error: {exc}"},
            }

    async def start_sync_chats(
        self,
        *,
        session: str,
        user_id: str,
    ) -> SyncChatsStartResponse:
        """Start WhatsApp chat sync in the background and return a job id."""
        if not session:
            return SyncChatsStartResponse(
                success=False,
                message="No WhatsApp session found.",
                job_id=None,
            )

        job_id = uuid4().hex
        self._sync_job_owners[job_id] = user_id
        self._sync_job_results[job_id] = asyncio.Queue(maxsize=1)

        task = asyncio.create_task(
            self._run_sync_chats_pipeline(session=session, user_id=user_id, job_id=job_id)
        )
        self._sync_job_tasks[job_id] = task
        task.add_done_callback(lambda _: self._sync_job_tasks.pop(job_id, None))

        return SyncChatsStartResponse(
            success=True,
            message="Sync started. Poll the job_id for completion.",
            job_id=job_id,
        )

    async def _run_sync_chats_pipeline(
        self,
        *,
        session: str,
        user_id: str,
        job_id: str,
    ) -> None:
        """Background task: run sync stream and enqueue final job result."""
        queue = self._sync_job_results.get(job_id)
        if queue is None:
            return

        try:
            total_synced = 0
            last_event: dict[str, Any] = {}

            async for event in self.sync_chats_stream(session=session, user_id=user_id):
                last_event = event
                if event.get("event") == "complete":
                    data = event.get("data", {})
                    if isinstance(data, dict):
                        total_synced = int(data.get("total_synced") or 0)

            is_complete = last_event.get("event") == "complete"
            event_data = last_event.get("data") or {}
            if isinstance(event_data, dict):
                message = str(
                    event_data.get("message")
                    or ("Sync completed." if is_complete else "Sync failed due to an error.")
                )
            else:
                message = "Sync completed." if is_complete else "Sync failed due to an error."

            await queue.put(
                SyncChatsJobResult(
                    success=is_complete,
                    message=message,
                    total_synced=total_synced,
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception("Sync pipeline failed for job %s", job_id)
            await queue.put(
                SyncChatsJobResult(
                    success=False,
                    message="Sync failed due to an error.",
                    total_synced=0,
                )
            )

    async def get_sync_chats_job_result(
        self,
        *,
        job_id: str,
        user_id: str,
        timeout: float = 30.0,
    ) -> SyncChatsJobResult | None:
        """Poll for a sync job result. Returns None on timeout."""
        job_owner = self._sync_job_owners.get(job_id)
        if job_owner is None:
            msg = "Job not found or expired."
            raise ValueError(msg)
        if job_owner != user_id:
            msg = "You do not have permission to access this job."
            raise PermissionError(msg)

        queue = self._sync_job_results.get(job_id)
        if queue is None:
            msg = "Job queue not found."
            raise ValueError(msg)

        try:
            result = await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            return None

        self._sync_job_owners.pop(job_id, None)
        self._sync_job_results.pop(job_id, None)
        self._sync_job_tasks.pop(job_id, None)
        return result

    # ------------------------------------------------------------------
    # Scan unreplied messages
    # ------------------------------------------------------------------

    @staticmethod
    def _get_mentioned_jids(msg: dict[str, Any]) -> list[str]:
        """Extract mentioned JIDs from WAHA message extended data."""
        return (
            msg.get("_data", {})
            .get("Message", {})
            .get("extendedTextMessage", {})
            .get("contextInfo", {})
            .get("mentionedJID")
            or []
        )

    async def _resolve_jid_to_cus(
        self,
        jid: str,
        session: str,
        moderated_chat_map: dict[str, dict[str, Any]],
        cache: dict[str, str],
    ) -> str:
        """Resolve a JID (possibly LID) to @c.us format."""
        if jid in cache:
            return cache[jid]
        if "@lid" not in jid:
            cache[jid] = jid
            return jid

        resolved: str | None = None
        # 1. moderated_chat_map (keyed by both w_chat_id and w_lid)
        if jid in moderated_chat_map and moderated_chat_map[jid].get("w_chat_id"):
            resolved = moderated_chat_map[jid]["w_chat_id"]
        # 2. MongoDB lookup by w_lid
        if not resolved:
            with contextlib.suppress(Exception):
                doc = await self._mongo.find_one(WHATSAPP_CHATS, {"w_lid": jid})
                if doc and doc.get("w_chat_id"):
                    resolved = doc["w_chat_id"]
        # 3. WAHA API fallback
        if not resolved:
            with contextlib.suppress(Exception):
                lid_resp = await self._client.get_chat_id_by_lids(
                    session=session,
                    lid=jid.split("@")[0],
                )
                resolved = lid_resp.pn

        result = resolved or jid
        cache[jid] = result
        return result

    async def _fetch_dm_conversations(
        self,
        session: str,
        dm_chats: list[dict[str, Any]],
        from_ts: int,
        moderated_chat_map: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        """Fetch unreplied DM conversations concurrently."""
        results: dict[str, str] = {}

        async def _process(chat: dict[str, Any]) -> tuple[str, str] | None:
            async with self._sem:
                doc = moderated_chat_map[chat["id"]]
                resolved_id = doc.get("w_chat_id") or chat["id"]
                messages = await self._client.get_chat_messages(
                    session=session,
                    chat_id=resolved_id,
                    limit=1000,
                    from_timestamp=from_ts,
                    download_media=False,
                    sort_by="timestamp",
                    sort_order="asc",
                )
                if not messages or messages[-1].get("fromMe"):
                    return None
                text = await self._build_conversation_text(messages, is_group=False, session=session)
                return (doc.get("w_chat_id", chat["id"]), text) if text else None

        gathered = await asyncio.gather(*[_process(c) for c in dm_chats], return_exceptions=True)
        for item in gathered:
            if isinstance(item, BaseException):
                logger.warning("DM fetch error: %s", item)
                continue
            if item:
                chat_id, text = item
                results[chat_id] = text
        return results

    async def _fetch_group_conversations(
        self,
        session: str,
        group_chats: list[dict[str, Any]],
        from_ts: int,
        moderated_chat_map: dict[str, dict[str, Any]],
        user_cid: str,
    ) -> dict[str, str]:
        """Fetch group messages since first mention of the user."""
        results: dict[str, str] = {}
        lid_cache: dict[str, str] = {}

        for chat in group_chats:
            doc = moderated_chat_map[chat["id"]]
            resolved_id = doc.get("w_chat_id") or chat["id"]
            try:
                messages = await self._client.get_chat_messages(
                    session=session,
                    chat_id=resolved_id,
                    limit=1000,
                    from_timestamp=from_ts,
                    download_media=False,
                    sort_by="timestamp",
                    sort_order="asc",
                )
                if not messages:
                    continue
                first_mention_idx: int | None = None
                for i, msg in enumerate(messages):
                    mentioned_jids = self._get_mentioned_jids(msg)
                    for jid in mentioned_jids:
                        resolved = await self._resolve_jid_to_cus(jid, session, moderated_chat_map, lid_cache)
                        if resolved == user_cid:
                            first_mention_idx = i
                            break
                    if first_mention_idx is not None:
                        break
                if first_mention_idx is None:
                    continue
                relevant = messages[first_mention_idx:]
                text = await self._build_conversation_text(relevant, is_group=True, session=session)
                if text:
                    results[doc.get("w_chat_id", chat["id"])] = text
            except Exception as e:  # noqa: BLE001
                logger.warning("Group fetch error for %s: %s", resolved_id, e)

        return results

    async def scan_unreplied_messages(
        self, args: ScanUnrepliedMessagesArgs, ctx: Context
    ) -> ScanUnrepliedResponse:
        """Scan moderated chats for unreplied DMs and group mentions."""
        session = self._validate_phone(args.phone_number)

        # Get or seed the user state (last_checkin_at, user_w_lid)
        user_state = await self._mongo.find_one(USER_STATE, {"user_id": args.user_id})
        last_checked: datetime
        if user_state and user_state.get("last_checkin_at"):
            raw_ts = user_state["last_checkin_at"]
            last_checked = raw_ts if isinstance(raw_ts, datetime) else datetime.fromisoformat(str(raw_ts))
        else:
            last_checked = datetime.now(UTC) - timedelta(hours=24)

        # Resolve user's LID if not cached
        user_w_lid: str = (user_state or {}).get("user_w_lid", "")
        if not user_w_lid:
            with contextlib.suppress(Exception):
                lid_resp = await self._client.get_lid_by_phone(session=session, phone=session)
                user_w_lid = lid_resp.lid
                await self._mongo.upsert_one(
                    USER_STATE,
                    {"user_id": args.user_id},
                    {"user_w_lid": user_w_lid, "user_id": args.user_id},
                )

        # Fetch all recent chats (top 100 by recency)
        all_chats = await self._client.get_all_chats(
            session=session,
            sort_by="conversationTimestamp",
            sort_order="desc",
            total_limit=100,
        )

        # Load chats with moderation enabled from MongoDB
        moderated_docs = await self._mongo.find_many(
            WHATSAPP_CHATS,
            {"user_id": args.user_id, "moderation_status": True},
        )

        moderated_chat_map: dict[str, dict[str, Any]] = {}
        for doc in moderated_docs:
            if doc.get("w_chat_id"):
                moderated_chat_map[doc["w_chat_id"]] = doc
            if doc.get("w_lid"):
                moderated_chat_map[doc["w_lid"]] = doc

        # Filter to moderated chats only
        moderated_chats = [c for c in all_chats if c.get("id") in moderated_chat_map]

        dm_chats = [
            c for c in moderated_chats
            if (moderated_chat_map.get(c["id"]) or {}).get("type") != WhatsappChatType.GROUP.value
        ]
        group_chats = [
            c for c in moderated_chats
            if (moderated_chat_map.get(c["id"]) or {}).get("type") == WhatsappChatType.GROUP.value
        ]

        from_ts = int(last_checked.timestamp())
        user_cid = f"{session}@c.us"

        dm_conversations = await self._fetch_dm_conversations(session, dm_chats, from_ts, moderated_chat_map)
        group_conversations = await self._fetch_group_conversations(
            session, group_chats, from_ts, moderated_chat_map, user_cid
        )

        if not dm_conversations and not group_conversations:
            return ScanUnrepliedResponse(
                summary="No unreplied messages found.",
                dm_count=0,
                group_count=0,
            )

        # Build combined text for LLM
        parts: list[str] = []
        for chat_id, text in dm_conversations.items():
            parts.append(f"[DM from {chat_id}]\n{text}")
        for chat_id, text in group_conversations.items():
            parts.append(f"[Group {chat_id} — you were mentioned]\n{text}")

        combined = "\n\n---\n\n".join(parts)
        result = await ctx.sample(
            f"Unreplied messages:\n\n{combined}",
            system_prompt=_SCAN_SUMMARY_SYSTEM,
            max_tokens=1024,
        )

        return ScanUnrepliedResponse(
            summary=result.text,
            dm_count=len(dm_conversations),
            group_count=len(group_conversations),
        )

    # ------------------------------------------------------------------
    # Chat description generation
    # ------------------------------------------------------------------

    async def generate_chat_descriptions(
        self,
        session: str,
        user_id: str,
        ctx: Context,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Generate and store descriptions for the most-recent chats via MCP sampling."""
        chats = await self._mongo.find_many(
            WHATSAPP_CHATS,
            {"user_id": user_id},
            limit=limit,
            sort=[("conversation_timestamp", -1)],
        )

        if not chats:
            return {"processed": 0, "skipped": 0, "message": "No chats found."}

        sem = asyncio.Semaphore(_DESCRIPTION_CONCURRENCY)

        async def _describe_one(chat: dict[str, Any]) -> bool:
            async with sem:
                chat_id: str = chat.get("w_chat_id") or ""
                chat_name: str = chat.get("chat_name") or ""
                if not chat_id:
                    return False
                try:
                    messages = await self._client.get_messages(
                        session=session,
                        chat_id=chat_id,
                        limit=_DESCRIPTION_MESSAGES_LIMIT,
                        download_media=False,
                    )
                    if not messages:
                        return False

                    lines: list[str] = []
                    for msg in messages:
                        text = msg.get("body") or msg.get("text")
                        if not text:
                            continue
                        prefix = "[Me]" if msg.get("fromMe") else "[Other]"
                        lines.append(f"{prefix}: {text}")

                    if not lines:
                        return False

                    chat_type = "group" if chat_id.endswith("@g.us") else "direct message"
                    user_prompt = (
                        f"Chat name: {chat_name}\n"
                        f"Type: {chat_type}\n\n"
                        f"Recent messages:\n" + "\n".join(lines)
                    )

                    result = await ctx.sample(
                        user_prompt,
                        system_prompt=_DESCRIPTION_SYSTEM,
                        max_tokens=200,
                    )
                    if result.text:
                        await self._mongo.upsert_one(
                            WHATSAPP_CHATS,
                            {"user_id": user_id, "w_chat_id": chat_id},
                            {"description": result.text},
                        )
                    return bool(result.text)
                except Exception:
                    logger.exception("Failed to describe chat %s (%s)", chat_name, chat_id)
                    return False

        results = await asyncio.gather(*[_describe_one(chat) for chat in chats])
        processed = sum(1 for r in results if r)
        return {"processed": processed, "skipped": len(chats) - processed}
