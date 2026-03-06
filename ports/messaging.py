"""IMessagingPort — abstract contract for the WhatsApp messaging backend."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IMessagingPort(Protocol):
    """Everything the relay needs to interact with the WAHA HTTP API."""

    # ------------------------------------------------------------------
    # Presence / typing
    # ------------------------------------------------------------------

    async def send_seen(self, *, chat_id: str, session: str) -> None: ...

    async def start_typing(self, *, chat_id: str, session: str) -> None: ...

    async def stop_typing(self, *, chat_id: str, session: str) -> None: ...

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
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

    async def send_voice(
        self,
        *,
        session: str,
        chat_id: str,
        voice_url: str | None = None,
        voice_base64: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]: ...

    async def send_video(
        self,
        *,
        session: str,
        chat_id: str,
        video_url: str | None = None,
        video_base64: str | None = None,
        caption: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]: ...

    async def delete_message(self, *, session: str, chat_id: str, message_id: str) -> None: ...

    async def edit_message(
        self,
        *,
        session: str,
        chat_id: str,
        message_id: str,
        new_text: str,
        link_preview: bool = True,
    ) -> dict[str, Any]: ...

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
    ) -> list[dict[str, Any]]: ...

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
    ) -> list[dict[str, Any]]: ...

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
    ) -> list[dict[str, Any]]: ...

    async def get_contact_details(self, *, contact_id: str, session: str) -> Any: ...

    async def check_number_status(self, *, phone: str, session: str) -> dict[str, Any]: ...

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    async def get_group(self, *, session: str, group_id: str) -> dict[str, Any]: ...

    async def get_group_participants(self, *, session: str, group_id: str) -> list[dict[str, Any]]: ...

    async def get_groups(self, *, session: str) -> list[dict[str, Any]]: ...

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
    ) -> list[dict[str, Any]]: ...

    # ------------------------------------------------------------------
    # LID resolution
    # ------------------------------------------------------------------

    async def get_chat_id_by_lids(self, *, session: str, lid: str) -> Any: ...

    async def get_lid_by_phone(self, *, session: str, phone: str) -> Any: ...

    async def get_all_lids(self, *, session: str, page_size: int = 100) -> list[Any]: ...

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def create_session(self, name: str | None = None) -> dict[str, Any]: ...

    async def start_session(self, session: str) -> dict[str, Any]: ...

    async def stop_session(self, session: str) -> dict[str, Any]: ...

    async def logout_session(self, session: str) -> dict[str, Any]: ...

    async def delete_session(self, session: str) -> None: ...

    async def list_sessions(self) -> list[dict[str, Any]]: ...

    async def get_session(self, name: str) -> dict[str, Any]: ...

    async def request_auth_code(self, *, session: str, phone_number: str) -> dict[str, Any]: ...

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    def verify_signature(self, raw_body: bytes, received_signature: str) -> bool: ...
