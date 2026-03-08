"""OpenRouter adapter — implements ILLMAdapter using the OpenRouter chat completions API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from config.settings import Settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterAdapter:
    """Calls OpenRouter's OpenAI-compatible chat completions endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.openrouter_api_key or ""
        self._model = settings.openrouter_model
        self._http = httpx.AsyncClient(timeout=60.0)

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        session: str = "",
    ) -> str:
        if not self._api_key:
            raise RuntimeError("OpenRouter API key is not configured")

        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self._http.post(_BASE_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except Exception:
            logger.exception("OpenRouter completion failed")
            return ""
