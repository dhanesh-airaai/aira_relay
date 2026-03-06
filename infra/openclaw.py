"""OpenClaw adapter — HTTP client for the OpenClaw agent service.

Handles two responsibilities:
  1. Event forwarding  — POST /hooks/agent or /hooks/wake
  2. LLM completion   — POST /v1/chat/completions (implements ILLMAdapter)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from config.settings import Settings

logger = logging.getLogger(__name__)


class OpenClawAdapter:
    """Concrete adapter for the OpenClaw service.

    Structurally satisfies ``ILLMAdapter`` via the ``complete()`` method.
    """

    def __init__(self, settings: Settings) -> None:
        self._url = settings.openclaw_url
        self._token = settings.openclaw_token or ""
        self._agent_name = settings.openclaw_agent_name
        self._gateway_token = settings.openclaw_gateway_token or ""
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
        *,
        use_agent_hook: bool = True,
    ) -> dict[str, Any] | None:
        """Forward a relay event to OpenClaw.

        use_agent_hook=True  → POST /hooks/agent  (LLM processing)
        use_agent_hook=False → POST /hooks/wake   (lightweight notification)
        """
        if not self._url:
            return None

        endpoint = "hooks/agent" if use_agent_hook else "hooks/wake"
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

    # ------------------------------------------------------------------
    # ILLMAdapter implementation
    # ------------------------------------------------------------------

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Generate text via OpenClaw's /v1/chat/completions endpoint."""
        if not self._url:
            raise RuntimeError("OpenClaw URL is not configured")

        url = f"{self._url.rstrip('/')}/v1/chat/completions"
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._gateway_token}",
        }
        resp = await self._http.post(
            url,
            json={"model": "openclaw", "messages": messages},
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
