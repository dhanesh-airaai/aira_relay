"""Global MCP session registry — tracks active sessions for server-side notifications."""

from __future__ import annotations

import asyncio
import weakref
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.session import ServerSession

_sessions: weakref.WeakSet[ServerSession] = weakref.WeakSet()
_lock = asyncio.Lock()


async def register_session(session: ServerSession) -> None:
    """Register an active MCP session. Automatically removed when the session is GC'd."""
    async with _lock:
        _sessions.add(session)


async def get_all() -> list[ServerSession]:
    """Return all live sessions."""
    async with _lock:
        return list(_sessions)
