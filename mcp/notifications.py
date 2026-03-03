"""Global notification bus — bridges incoming webhook events to MCP tool responses."""

from __future__ import annotations

import asyncio
from typing import Any

# Unbounded queue: webhook handler pushes, get_incoming_message tool pops.
# Both run in the same event loop (anyio task group in main.py).
_incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()


async def push_incoming_event(event: dict[str, Any]) -> None:
    """Enqueue a processed webhook event for the next tool poll."""
    await _incoming.put(event)


async def pop_incoming_event(timeout: float = 30.0) -> dict[str, Any] | None:
    """Wait up to *timeout* seconds for the next event. Returns None on timeout."""
    try:
        return await asyncio.wait_for(_incoming.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
