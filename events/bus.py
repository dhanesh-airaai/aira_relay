"""In-process async event bus — concrete implementation of IEventBus."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from models.events import RelayEvent

if TYPE_CHECKING:
    from ports.event_bus import EventHandler

logger = logging.getLogger(__name__)


class EventBus:
    """Fanout event bus: publish() calls every registered handler concurrently."""

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: RelayEvent) -> None:
        if not self._handlers:
            return
        results = await asyncio.gather(
            *(h(event) for h in self._handlers), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Event handler error: %s", result, exc_info=result)
