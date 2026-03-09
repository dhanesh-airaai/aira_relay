"""OpenClaw adapter — HTTP client for the OpenClaw agent service.

Handles event forwarding: POST /hooks/wake
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from config.settings import Settings

logger = logging.getLogger(__name__)


class OpenClawAdapter:
    """Forwards relay events to OpenClaw via /hooks/wake."""

    def __init__(self, settings: Settings) -> None:
        self._url = settings.openclaw_url
        self._token = settings.openclaw_token or ""
        self._agent_name = settings.openclaw_agent_name
        self._deliver_channel = settings.openclaw_deliver_channel

        self._http = httpx.AsyncClient(timeout=30.0)

    @property
    def is_configured(self) -> bool:
        return bool(self._url)

    # ------------------------------------------------------------------
    # Event forwarding
    # ------------------------------------------------------------------

    async def push_event(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Forward a relay event to OpenClaw via /hooks/wake."""
        if not self._url:
            return None

        endpoint = "hooks/waha"
        url = f"{self._url.rstrip('/')}/{endpoint}"
        event_type = data.get("event")
        if event_type == "message":
            sender = data.get("sender_phone", "unknown")
            chat = data.get("chat_name", data.get("chat_id", "unknown"))
            chat_type = data.get("chat_type", "dm")
            body = data.get("body", "") or "(media)"
            is_group = chat_type == "group"
            kind = "group" if is_group else "DM"
            text = (
                f"New WhatsApp {kind} message from {sender} in '{chat}': \"{body}\". "
                f"Notify the user right now with a one-line summary."
            )
        elif event_type == "session.status":
            session = data.get("session", "unknown")
            status = data.get("status", "unknown")
            text = (
                f"WhatsApp session '{session}' changed status to '{status}'. "
                f"Notify the user right now: "
                f"one line with the status change, one line suggesting action if needed "
                f"(e.g. re-scan QR)."
            )
        elif event_type == "sync_chats":
            success = data.get("success", False)
            total = data.get("total_synced", 0)
            text = (
                f"Chat sync {'succeeded' if success else 'failed'}: {total} chats synced. "
                f"Notify the user with a one-line summary."
            )
        else:
            text = data.get("body") or data.get("event") or data.get("type") or "event"

        payload: dict[str, Any] = {
            "message": text,
            "wakeMode": "now"
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }
        try:
            resp = await self._http.post(url, json=payload, headers=headers, timeout=10.0)
            if not resp.is_success:
                logger.warning(
                    "OpenClaw %s returned %s: %s",
                    endpoint,
                    resp.status_code,
                    resp.text,
                )
            resp.raise_for_status()
            logger.debug("Forwarded event to OpenClaw (%s)", endpoint)
            return resp.json() if resp.content else None
        except Exception:
            logger.warning("Failed to forward event to OpenClaw", exc_info=True)
            return None
