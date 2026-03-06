"""Pure WAHA HTTP client — implements IMessagingPort with no business logic."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from typing import Any
from urllib.parse import quote

import httpx

from infra.waha.wire_models import ChatIdByLidResponse, ChatItem, ContactDetails
from models.exceptions import WhatsAppAuthError, WhatsAppError, WhatsAppNetworkError

logger = logging.getLogger(__name__)

_MIN_TYPING_DELAY = 1.0
_MAX_TYPING_DELAY = 5.0


class WahaClient:
    """Async HTTP client for the WAHA WhatsApp API.

    Structurally satisfies ``IMessagingPort`` — no explicit declaration needed
    because we use Protocol-based structural subtyping.
    """

    def __init__(self, base_url: str, api_key: str, webhook_secret: str | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._webhook_secret = webhook_secret or ""
        self._http = httpx.AsyncClient(timeout=30.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "X-Api-Key": self._api_key}

    @staticmethod
    def normalize_wa_id(wa_id: str | None) -> str:
        if not wa_id:
            return ""
        return wa_id.replace("@c.us", "").replace("@g.us", "").strip()

    async def _apply_typing_delay(self, text: str) -> None:
        delay = max(_MIN_TYPING_DELAY, min(len(text) * 0.05, _MAX_TYPING_DELAY))
        await asyncio.sleep(delay)

    @staticmethod
    def _translate_error(exc: httpx.HTTPStatusError) -> WhatsAppError:
        status = exc.response.status_code
        if status == 401:
            return WhatsAppAuthError(
                "WAHA API authentication failed (401). "
                "Ensure WAHA_API_KEY in .env matches the key the WAHA container was "
                "started with, then rebuild: docker-compose down && docker-compose up --build.",
                status_code=status,
            )
        return WhatsAppError(
            f"WAHA returned HTTP {status}: {exc.response.text[:200]}",
            status_code=status,
        )

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        try:
            resp = await self._http.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise self._translate_error(exc) from exc
        except httpx.NetworkError as exc:
            raise WhatsAppNetworkError(f"Cannot reach WAHA: {exc}") from exc

    async def _post(self, url: str, payload: dict[str, Any]) -> Any:
        try:
            resp = await self._http.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise self._translate_error(exc) from exc
        except httpx.NetworkError as exc:
            raise WhatsAppNetworkError(f"Cannot reach WAHA: {exc}") from exc

    async def _put(self, url: str, payload: dict[str, Any]) -> Any:
        try:
            resp = await self._http.put(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise self._translate_error(exc) from exc
        except httpx.NetworkError as exc:
            raise WhatsAppNetworkError(f"Cannot reach WAHA: {exc}") from exc

    async def _delete(self, url: str) -> None:
        try:
            resp = await self._http.delete(url, headers=self._headers())
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._translate_error(exc) from exc
        except httpx.NetworkError as exc:
            raise WhatsAppNetworkError(f"Cannot reach WAHA: {exc}") from exc

    # ------------------------------------------------------------------
    # Presence / typing
    # ------------------------------------------------------------------

    async def send_seen(self, *, chat_id: str, session: str) -> None:
        try:
            await self._post(f"{self._base}/sendSeen", {"chatId": chat_id, "session": session})
        except Exception as e:
            logger.debug("send_seen error (non-fatal): %s", e)

    async def start_typing(self, *, chat_id: str, session: str) -> None:
        try:
            await self._post(
                f"{self._base}/{quote(session, safe='')}/presence",
                {"chatId": chat_id, "presence": "typing"},
            )
        except Exception as e:
            logger.debug("start_typing error (non-fatal): %s", e)

    async def stop_typing(self, *, chat_id: str, session: str) -> None:
        try:
            await self._post(f"{self._base}/stopTyping", {"chatId": chat_id, "session": session})
        except Exception as e:
            logger.debug("stop_typing error (non-fatal): %s", e)

    # ------------------------------------------------------------------
    # LID resolution
    # ------------------------------------------------------------------

    async def get_chat_id_by_lids(self, *, session: str, lid: str) -> ChatIdByLidResponse:
        safe_lid = quote(lid, safe="")
        data = await self._get(f"{self._base}/{session}/lids/{safe_lid}")
        return ChatIdByLidResponse(**data)

    async def get_lid_by_phone(self, *, session: str, phone: str) -> ChatIdByLidResponse:
        safe_phone = quote(phone, safe="")
        data = await self._get(f"{self._base}/{session}/lids/pn/{safe_phone}")
        return ChatIdByLidResponse(**data)

    async def get_all_lids(self, *, session: str, page_size: int = 100) -> list[ChatIdByLidResponse]:
        all_lids: list[ChatIdByLidResponse] = []
        offset = 0
        while True:
            data = await self._get(
                f"{self._base}/{session}/lids",
                params={"limit": page_size, "offset": offset},
            )
            if not isinstance(data, list) or not data:
                break
            all_lids.extend(ChatIdByLidResponse(**item) for item in data)
            offset += page_size
        return all_lids

    async def _resolve_lid(self, session: str, chat_id: str) -> str:
        """Inline LID → phone JID; used only within client send methods."""
        if "@lid" in chat_id:
            resp = await self.get_chat_id_by_lids(session=session, lid=chat_id.split("@")[0])
            return resp.pn
        return chat_id

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
        chat_id = await self._resolve_lid(session, chat_id)
        await self.send_seen(chat_id=chat_id, session=session)
        await self.start_typing(chat_id=chat_id, session=session)
        await self._apply_typing_delay(text)

        payload: dict[str, Any] = {
            "session": session,
            "chatId": chat_id,
            "text": text,
            "linkPreview": link_preview,
        }
        if link_preview_high_quality:
            payload["linkPreviewHighQuality"] = True
        if mentions:
            payload["mentions"] = mentions
        if reply_to:
            payload["reply_to"] = reply_to
        return await self._post(f"{self._base}/sendText", payload)

    async def send_image(
        self,
        *,
        session: str,
        chat_id: str,
        file_name: str,
        file_mimetype: str,
        caption: str | None = None,
        file_url: str | None = None,
        file_data: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        chat_id = await self._resolve_lid(session, chat_id)
        payload: dict[str, Any] = {
            "session": session,
            "chatId": chat_id,
            "file": {"filename": file_name, "mimetype": file_mimetype},
        }
        if file_data:
            payload["file"]["data"] = file_data
        elif file_url:
            payload["file"]["url"] = file_url
        if caption:
            payload["caption"] = caption
        if reply_to:
            payload["reply_to"] = reply_to
        return await self._post(f"{self._base}/sendImage", payload)

    async def send_file(
        self,
        *,
        session: str,
        chat_id: str,
        file_name: str,
        file_mimetype: str,
        caption: str | None = None,
        file_url: str | None = None,
        file_data: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        chat_id = await self._resolve_lid(session, chat_id)
        payload: dict[str, Any] = {
            "session": session,
            "chatId": chat_id,
            "file": {"filename": file_name, "mimetype": file_mimetype},
        }
        if file_url:
            payload["file"]["url"] = file_url
        elif file_data:
            payload["file"]["data"] = file_data
        if caption:
            payload["caption"] = caption
        if reply_to:
            payload["reply_to"] = reply_to
        return await self._post(f"{self._base}/sendFile", payload)

    async def send_voice(
        self,
        *,
        session: str,
        chat_id: str,
        voice_url: str | None = None,
        voice_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        chat_id = await self._resolve_lid(session, chat_id)
        payload: dict[str, Any] = {"chatId": chat_id, "session": session}
        if voice_url:
            payload["url"] = voice_url
        elif voice_base64:
            payload["file"] = {"data": voice_base64}
        if reply_to:
            payload["reply_to"] = reply_to
        return await self._post(f"{self._base}/sendVoice", payload)

    async def send_video(
        self,
        *,
        session: str,
        chat_id: str,
        video_url: str | None = None,
        video_base64: str | None = None,
        caption: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        chat_id = await self._resolve_lid(session, chat_id)
        payload: dict[str, Any] = {"chatId": chat_id, "session": session}
        if video_url:
            payload["url"] = video_url
        elif video_base64:
            payload["file"] = {"data": video_base64}
        if caption:
            payload["caption"] = caption
        if reply_to:
            payload["reply_to"] = reply_to
        return await self._post(f"{self._base}/sendVideo", payload)

    async def delete_message(self, *, session: str, chat_id: str, message_id: str) -> None:
        chat_id = await self._resolve_lid(session, chat_id)
        url = (
            f"{self._base}/{quote(session, safe='')}"
            f"/chats/{quote(chat_id, safe='')}"
            f"/messages/{quote(message_id, safe='')}"
        )
        await self._delete(url)

    async def edit_message(
        self,
        *,
        session: str,
        chat_id: str,
        message_id: str,
        new_text: str,
        link_preview: bool = True,
    ) -> dict[str, Any]:
        chat_id = await self._resolve_lid(session, chat_id)
        url = (
            f"{self._base}/{quote(session, safe='')}"
            f"/chats/{quote(chat_id, safe='')}"
            f"/messages/{quote(message_id, safe='')}"
        )
        return await self._put(url, {"text": new_text, "linkPreview": link_preview})

    # ------------------------------------------------------------------
    # Message retrieval
    # ------------------------------------------------------------------

    async def get_messages(
        self,
        *,
        session: str,
        chat_id: str,
        limit: int = 100,
        offset: int | None = None,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        download_media: bool = False,
    ) -> list[dict[str, Any]]:
        if "@lid" in chat_id:
            chat_id = await self._resolve_lid(session, chat_id)
        url = f"{self._base}/{session}/chats/{quote(chat_id, safe='')}/messages"
        params: dict[str, Any] = {"limit": limit, "downloadMedia": download_media}
        if offset is not None:
            params["offset"] = offset
        if from_timestamp is not None:
            params["filter.timestamp.gte"] = from_timestamp
        if to_timestamp is not None:
            params["filter.timestamp.lte"] = to_timestamp
        return await self._get(url, params)

    async def get_chat_messages(
        self,
        *,
        session: str,
        chat_id: str,
        limit: int | None = None,
        offset: int | None = None,
        download_media: bool | None = None,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self._base}/{session}/chats/{quote(chat_id, safe='')}/messages"
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if download_media is not None:
            params["downloadMedia"] = download_media
        if from_timestamp is not None:
            params["filter.timestamp.gte"] = from_timestamp
        if to_timestamp is not None:
            params["filter.timestamp.lte"] = to_timestamp
        if sort_by is not None:
            params["sortBy"] = sort_by
        if sort_order is not None:
            params["sortOrder"] = sort_order
        return await self._get(url, params)

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    async def get_all_contacts(
        self,
        *,
        session: str,
        limit: int | None = None,
        offset: int | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"session": session}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if sort_by is not None:
            params["sortBy"] = sort_by
        if sort_order is not None:
            params["sortOrder"] = sort_order

        contacts: list[dict[str, Any]] = await self._get(f"{self._base}/contacts/all", params)

        # Resolve LIDs in the id field
        lid_mappings = await self.get_all_lids(session=session)
        lid_to_phone = {m.lid: m.pn for m in lid_mappings}
        for contact in contacts:
            cid = str(contact.get("id", ""))
            if "@lid" in cid and cid in lid_to_phone:
                contact["id"] = lid_to_phone[cid]
        return contacts

    async def get_contact_details(self, *, contact_id: str, session: str) -> ContactDetails:
        params = {"contactId": contact_id, "session": session}
        data = await self._get(f"{self._base}/contacts", params)
        if isinstance(data, dict) and "id" not in data:
            data["id"] = contact_id
        return ContactDetails.model_validate(data)

    async def check_number_status(self, *, phone: str, session: str) -> dict[str, Any]:
        return await self._post(
            f"{self._base}/checkNumberStatus", {"phone": phone, "session": session}
        )

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    async def get_group(self, *, session: str, group_id: str) -> dict[str, Any]:
        return await self._get(f"{self._base}/{session}/groups/{group_id}")

    async def get_group_participants(self, *, session: str, group_id: str) -> list[dict[str, Any]]:
        return await self._get(f"{self._base}/{session}/groups/{group_id}/participants")

    async def get_groups(self, *, session: str) -> list[dict[str, Any]]:
        return await self._get(f"{self._base}/{session}/groups")

    # ------------------------------------------------------------------
    # Chats
    # ------------------------------------------------------------------

    async def get_all_chats(
        self,
        *,
        session: str,
        page_size: int = 10000,
        sort_by: str | None = None,
        sort_order: str | None = None,
        total_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        all_chats: list[dict[str, Any]] = []
        offset = 0

        while True:
            remaining = total_limit - len(all_chats) if total_limit is not None else None
            fetch_size = min(page_size, remaining) if remaining is not None else page_size

            params: dict[str, Any] = {"limit": fetch_size, "offset": offset}
            if sort_by:
                params["sortBy"] = sort_by
            if sort_order:
                params["sortOrder"] = sort_order

            data = await self._get(f"{self._base}/{session}/chats", params)
            if not isinstance(data, list) or not data:
                break

            for item in data:
                chat = ChatItem.model_validate(item)
                all_chats.append(chat.model_dump())

            offset += len(data)
            if total_limit is not None and len(all_chats) >= total_limit:
                break

        return all_chats

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def create_session(self, name: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name:
            payload["name"] = name
        return await self._post(f"{self._base}/sessions/", payload)

    async def start_session(self, session: str) -> dict[str, Any]:
        return await self._post(f"{self._base}/sessions/{quote(session, safe='')}/start", {})

    async def stop_session(self, session: str) -> dict[str, Any]:
        return await self._post(f"{self._base}/sessions/{quote(session, safe='')}/stop", {})

    async def logout_session(self, session: str) -> dict[str, Any]:
        return await self._post(f"{self._base}/sessions/{quote(session, safe='')}/logout", {})

    async def delete_session(self, session: str) -> None:
        await self._delete(f"{self._base}/sessions/{quote(session, safe='')}")

    async def list_sessions(self) -> list[dict[str, Any]]:
        return await self._get(f"{self._base}/sessions/")

    async def get_session(self, name: str) -> dict[str, Any]:
        return await self._get(f"{self._base}/sessions/{name}")

    async def request_auth_code(self, *, session: str, phone_number: str) -> dict[str, Any]:
        return await self._post(
            f"{self._base}/{quote(session, safe='')}/auth/request-code",
            {"phoneNumber": phone_number},
        )

    # ------------------------------------------------------------------
    # Media download
    # ------------------------------------------------------------------

    async def download_media(self, url: str) -> tuple[str, bytes]:
        """Download media from a WAHA URL. Returns (content_type, bytes)."""
        try:
            resp = await self._http.get(
                url,
                headers={"Content-Type": "application/json", "X-Api-Key": self._api_key},
            )
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            return content_type, resp.content
        except httpx.HTTPStatusError as exc:
            raise self._translate_error(exc) from exc
        except httpx.NetworkError as exc:
            raise WhatsAppNetworkError(f"Cannot reach WAHA media: {exc}") from exc

    # ------------------------------------------------------------------
    # Webhook signature verification
    # ------------------------------------------------------------------

    def verify_signature(self, raw_body: bytes, received_signature: str) -> bool:
        computed = hmac.new(
            self._webhook_secret.encode(),
            raw_body,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(computed, received_signature)
