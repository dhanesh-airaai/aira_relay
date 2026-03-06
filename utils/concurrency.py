"""Global background task registry with graceful drain on shutdown."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class TaskRegistry:
    """Tracks live asyncio tasks and drains them gracefully on shutdown.

    Replaces scattered ``_background_tasks: set[asyncio.Task]`` sets across
    multiple modules.  A single instance is created at startup and injected
    wherever background work needs to be spawned.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def spawn(self, coro: object, *, name: str | None = None) -> asyncio.Task[None]:
        """Schedule *coro* as a background task and track it."""
        task: asyncio.Task[None] = asyncio.create_task(coro, name=name)  # type: ignore[arg-type]
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Background task %r raised an exception", task.get_name(), exc_info=task.exception())

    async def drain(self, timeout: float = 30.0) -> None:
        """Wait for all running tasks to finish (up to *timeout* seconds)."""
        pending = list(self._tasks)
        if not pending:
            return
        logger.info("Draining %d background task(s) (timeout=%.0fs)…", len(pending), timeout)
        done, still_running = await asyncio.wait(pending, timeout=timeout)
        if still_running:
            logger.warning("%d task(s) did not finish within shutdown timeout", len(still_running))

    @property
    def count(self) -> int:
        return len(self._tasks)
