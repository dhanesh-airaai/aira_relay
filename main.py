"""Relay entry point — initialises databases then starts the MCP + webhook servers."""

from __future__ import annotations

import logging
import os
import sys

import anyio
import uvicorn

logging.basicConfig(level=logging.INFO)

if os.getenv("DEBUGPY_ENABLE") == "true":
    import debugpy
    debugpy.listen(("0.0.0.0", 5678))
    if os.getenv("DEBUGPY_WAIT_FOR_CLIENT") == "true":
        print("Waiting for debugger to attach on port 5678...", file=sys.stderr, flush=True)
        debugpy.wait_for_client()


async def _main_async() -> None:
    from db.init import initialize_databases

    await initialize_databases()

    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "http":
        await _run_http_servers()
    else:
        # Stdio mode: MCP on stdio, webhook receiver on a separate port
        await _run_stdio_with_webhook()


async def _run_http_servers() -> None:
    """Run the MCP HTTP server (uvicorn) and the webhook receiver concurrently."""
    from config.settings import settings
    from relay.server import mcp
    from webhook.app import serve_webhook
    print("Settings:", settings)  # Log settings at startup for debugging

    mcp_app = mcp.streamable_http_app()
    mcp_config = uvicorn.Config(
        mcp_app,
        host="0.0.0.0",
        port=settings.mcp_port,
        log_level="info",
    )

    async with anyio.create_task_group() as tg:
        tg.start_soon(uvicorn.Server(mcp_config).serve)
        tg.start_soon(serve_webhook, "0.0.0.0", settings.webhook_port)


async def _run_stdio_with_webhook() -> None:
    """Run the MCP stdio server alongside the webhook receiver on a background port."""
    from config.settings import settings
    from relay.server import mcp
    from webhook.app import serve_webhook

    print(
        f"Starting MCP stdio server + webhook receiver on :{settings.webhook_port}",
        file=sys.stderr,
    )

    async with anyio.create_task_group() as tg:
        tg.start_soon(serve_webhook, "0.0.0.0", settings.webhook_port)
        tg.start_soon(mcp.run_stdio_async)


def main() -> None:
    anyio.run(_main_async)


if __name__ == "__main__":
    main()
