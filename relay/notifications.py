"""Global notification bus — bridges incoming webhook events to MCP sessions."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Fallback queue: webhook handler pushes, get_incoming_message tool pops.
_incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()


def _build_content_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Build MCP content blocks for a message event.

    Text body and media (image/audio/video/file) are each represented as a
    typed content block so the receiving agent can render or process them
    directly rather than handling raw URL strings.
    """
    blocks: list[dict[str, Any]] = []

    if event.get("body"):
        blocks.append({"type": "text", "text": event["body"]})

    if event.get("has_media") and event.get("media_url"):
        url: str = event["media_url"]
        mimetype: str = event.get("media_mimetype", "")

        if mimetype.startswith("image/"):
            blocks.append({"type": "image", "url": url, "mime_type": mimetype})
        elif mimetype.startswith("audio/"):
            blocks.append({"type": "audio", "url": url, "mime_type": mimetype})
        elif mimetype.startswith("video/"):
            blocks.append({"type": "video", "url": url, "mime_type": mimetype})
        else:
            # Generic file — surface as a resource link the agent can reference
            blocks.append({"type": "resource", "url": url, "mime_type": mimetype})

    return blocks


async def _push_to_openclaw(
    data: dict[str, Any], openclaw_url: str, *, use_agent_hook: bool
) -> dict[str, Any] | None:
    """Forward event to the OpenClaw agent webhook and return the parsed response.

    use_agent_hook=True  → POST /hooks/agent  (LLM sampling / agentic processing)
    use_agent_hook=False → POST /hooks/wake   (lightweight wake / notification)
    """
    import urllib.request

    from config.settings import settings

    endpoint = "hooks/agent" if use_agent_hook else "hooks/wake"
    url = f"{openclaw_url.rstrip('/')}/{endpoint}"
    payload = json.dumps(
        {
            "message": json.dumps(data),
            "name": settings.openclaw_agent_name,
            "wakeMode": "now",
        }
    ).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.openclaw_token or ''}",
        },
        method="POST",
    )
    try:
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=10))
        body = resp.read()
        logger.debug("Forwarded event to OpenClaw (%s): %s", endpoint, url)
        return json.loads(body) if body else None
    except Exception:
        logger.warning("Failed to forward event to OpenClaw", exc_info=True)
        return None


async def push_incoming_event(
    event: dict[str, Any],
    hook_type: str | None = None,
) -> None:
    """Send event to OpenClaw (if configured) or all registered MCP sessions.

    hook_type: "agent" | "wake" | None
        Override which OpenClaw hook to use. When None, defaults to "agent"
        for message events and "wake" for everything else.
    """
    from config.settings import settings

    # For incoming messages, attach structured content blocks so the agent
    # receives image/audio as typed content rather than bare URL strings.
    is_message = event.get("event") == "message"
    if is_message:
        content = _build_content_blocks(event)
        data = {**event, "content": content}
    else:
        data = event

    if settings.openclaw_url:
        use_agent = (hook_type == "agent") if hook_type is not None else is_message
        await _push_to_openclaw(data, settings.openclaw_url, use_agent_hook=use_agent)
        return

    from relay.session_registry import get_all

    for session in await get_all():
        try:
            await session.send_log_message(level="info", data=data, logger="waha")
        except Exception:
            logger.debug("Failed to send notification to session", exc_info=True)

    await _incoming.put(data)


async def pop_incoming_event(timeout: float = 30.0) -> dict[str, Any] | None:
    """Wait up to *timeout* seconds for the next event. Returns None on timeout."""
    try:
        return await asyncio.wait_for(_incoming.get(), timeout=timeout)
    except TimeoutError:
        return None
