"""OpenClaw event handler — forwards relay events to the OpenClaw agent service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.events import IncomingMessageEvent, RelayEvent

if TYPE_CHECKING:
    from infra.openclaw import OpenClawAdapter

logger = logging.getLogger(__name__)


class OpenClawHandler:
    """Forwards relay events to OpenClaw via the injected adapter."""

    def __init__(self, adapter: OpenClawAdapter) -> None:
        self._adapter = adapter

    async def handle(self, event: RelayEvent) -> None:
        if not self._adapter.is_configured:
            return
        # Incoming messages → agent hook (LLM processing)
        # All other events → wake hook (lightweight notification)
        use_agent = isinstance(event, IncomingMessageEvent)
        await self._adapter.push_event(event.model_dump(), use_agent_hook=use_agent)
