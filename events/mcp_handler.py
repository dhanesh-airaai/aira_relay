"""McpEventHandler — broadcasts relay events to live MCP sessions and the
incoming-message queue consumed by the get_incoming_message tool.

Replaces the previous module-level singletons (_incoming, _sessions, _lock)
with a proper injectable class so each instance owns its own state.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from typing import TYPE_CHECKING

from models.events import IncomingMessageEvent, RelayEvent

if TYPE_CHECKING:
    from mcp.server.session import ServerSession

logger = logging.getLogger(__name__)


class McpEventHandler:
    """Owns the incoming-message queue and the set of live MCP sessions.

    Instantiated once in lifespan.py and injected into McpContainer so MCP
    tools can access it without importing module-level state.
    """

    def __init__(self) -> None:
        self._incoming: asyncio.Queue[dict] = asyncio.Queue()
        self._sessions: weakref.WeakSet[ServerSession] = weakref.WeakSet()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Session registration
    # ------------------------------------------------------------------

    async def register_session(self, session: ServerSession) -> None:
        """Register an active MCP session (auto-removed when GC'd)."""
        async with self._lock:
            self._sessions.add(session)

    # ------------------------------------------------------------------
    # IEventBus handler
    # ------------------------------------------------------------------

    async def handle(self, event: RelayEvent) -> None:
        """Broadcast *event* to all live MCP sessions; queue IncomingMessageEvents."""
        data = event.model_dump()

        async with self._lock:
            sessions = list(self._sessions)

        for session in sessions:
            try:
                await session.send_log_message(level="info", data=data, logger="waha")
            except Exception:
                logger.debug("Failed to push event to MCP session", exc_info=True)

        if isinstance(event, IncomingMessageEvent):
            await self._incoming.put(data)

    # ------------------------------------------------------------------
    # Polling helper (used by get_incoming_message tool)
    # ------------------------------------------------------------------

    async def pop_incoming(self, timeout: float = 30.0) -> dict | None:
        """Wait up to *timeout* seconds for the next incoming message event."""
        try:
            return await asyncio.wait_for(self._incoming.get(), timeout=timeout)
        except TimeoutError:
            return None
