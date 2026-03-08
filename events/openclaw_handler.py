"""OpenClaw event handler — forwards relay events to the OpenClaw agent service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.events import RelayEvent

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
        await self._adapter.push_event(event.model_dump())
