"""IEventBus — abstract contract for the async event bus."""

from __future__ import annotations

from typing import Awaitable, Callable, Protocol, runtime_checkable

from models.events import RelayEvent

EventHandler = Callable[[RelayEvent], Awaitable[None]]


@runtime_checkable
class IEventBus(Protocol):
    async def publish(self, event: RelayEvent) -> None: ...

    def subscribe(self, handler: EventHandler) -> None: ...
