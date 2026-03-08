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

        endpoint = "hooks/wake"
        url = f"{self._url.rstrip('/')}/{endpoint}"
        text = data.get("body") or data.get("event") or data.get("type") or "event"
        payload = {
            "text": text,
            "name": self._agent_name,
            "wakeMode": "now",
            "context": data,
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
                    endpoint, resp.status_code, resp.text,
                )
            resp.raise_for_status()
            logger.debug("Forwarded event to OpenClaw (%s)", endpoint)
            return resp.json() if resp.content else None
        except Exception:
            logger.warning("Failed to forward event to OpenClaw", exc_info=True)
            return None

