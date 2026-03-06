"""Relay entry point — builds the complete object graph then starts the servers."""

from __future__ import annotations

import logging
import os
import sys

import anyio
import uvicorn

from config.constants import SERVER_BIND_HOST

logging.basicConfig(level=logging.INFO)

if os.getenv("DEBUGPY_ENABLE") == "true":
    import debugpy
    _debugpy_port = int(os.getenv("DEBUGPY_PORT", "5678"))
    debugpy.listen((SERVER_BIND_HOST, _debugpy_port))
    if os.getenv("DEBUGPY_WAIT_FOR_CLIENT") == "true":
        print(
            f"Waiting for debugger to attach on port {_debugpy_port}...",
            file=sys.stderr,
            flush=True,
        )
        debugpy.wait_for_client()


async def _main_async() -> None:
    from config.settings import settings
    from lifespan import lifespan

    transport = os.getenv("MCP_TRANSPORT", "stdio")

    async with lifespan() as app:
        if transport == "http":
            await _run_http(app, settings)
        else:
            await _run_stdio(app, settings)


async def _run_http(app, settings) -> None:  # type: ignore[no-untyped-def]
    """Run the MCP HTTP server (uvicorn) and webhook receiver concurrently."""
    mcp_app = app.mcp_server.streamable_http_app()
    mcp_config = uvicorn.Config(
        mcp_app,
        host=SERVER_BIND_HOST,
        port=settings.mcp_port,
        log_level="info",
    )
    webhook_config = uvicorn.Config(
        app.webhook_app,
        host=SERVER_BIND_HOST,
        port=settings.webhook_port,
        log_level="info",
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(uvicorn.Server(mcp_config).serve)
        tg.start_soon(uvicorn.Server(webhook_config).serve)


async def _run_stdio(app, settings) -> None:  # type: ignore[no-untyped-def]
    """Run the MCP stdio server and the webhook receiver concurrently."""
    print(
        f"Starting MCP stdio + webhook on :{settings.webhook_port}",
        file=sys.stderr,
    )
    webhook_config = uvicorn.Config(
        app.webhook_app,
        host=SERVER_BIND_HOST,
        port=settings.webhook_port,
        log_level="info",
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(uvicorn.Server(webhook_config).serve)
        tg.start_soon(app.mcp_server.run_stdio_async)


def main() -> None:
    anyio.run(_main_async)


if __name__ == "__main__":
    main()
