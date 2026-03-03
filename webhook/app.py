"""Minimal async webhook receiver using Python's built-in asyncio.start_server."""

from __future__ import annotations

import asyncio
import logging

from adapters.waha import WahaClient
from agents.tooling.services.waha.service import WahaService
from config.settings import settings
from db.mongodb.manager import mongo
from mcp.notifications import push_incoming_event
from webhook.models import (
    IncomingMessagePayload,
    SessionStatusPayload,
    WahaEventType,
    WahaWebhookEvent,
)
from webhook.processor import WebhookProcessor

logger = logging.getLogger(__name__)

_waha_client = WahaClient(
    base_url=settings.waha_base_url,
    api_key=settings.waha_api_key,
    webhook_secret=settings.waha_webhook_secret,
)
_waha_service = WahaService(client=_waha_client, mongo=mongo)
_processor = WebhookProcessor(
    client=_waha_client,
    mongo=mongo,
    waha_service=_waha_service,
)


async def _handle_waha_webhook(raw_body: bytes, headers: dict[str, str]) -> None:
    """Verify, parse and enqueue a WAHA webhook event."""
    if settings.waha_webhook_secret:
        hmac_header = headers.get("x-webhook-hmac", "")
        algorithm = headers.get("x-webhook-hmac-algorithm", "")
        if algorithm != "sha512" or not _waha_client.verify_signature(raw_body, hmac_header):
            logger.warning("Invalid WAHA webhook signature — request rejected")
            return

    try:
        event = WahaWebhookEvent.model_validate_json(raw_body)
    except Exception as exc:
        logger.warning("Malformed webhook payload: %s", exc)
        return

    if (
        event.event == WahaEventType.SESSION_STATUS
        and isinstance(event.payload, SessionStatusPayload)
    ):
        try:
            processed = await _processor.handle_session_status(
                session=event.session,
                payload=event.payload,
                event_timestamp=event.timestamp,
            )
        except Exception:
            logger.exception("Error processing webhook session.status event")
        return

    if event.event == WahaEventType.MESSAGE and isinstance(event.payload, IncomingMessagePayload):
        try:
            processed = await _processor.process_message_event(
                session=event.session,
                payload=event.payload,
            )
            if processed:
                await push_incoming_event(processed)
                logger.debug(
                    "Queued message event from %s in session %s",
                    processed.get("sender_phone"),
                    event.session,
                )
        except Exception:
            logger.exception("Error processing webhook message event")


async def _handle_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Parse a single HTTP request and dispatch it."""
    try:
        request_line = await reader.readline()
        if not request_line:
            return

        parts = request_line.decode(errors="replace").split()
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1]

        # Read headers
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            if b":" in line:
                key, _, value = line.decode(errors="replace").partition(":")
                headers[key.strip().lower()] = value.strip()

        content_length = int(headers.get("content-length", 0))
        raw_body = await reader.readexactly(content_length) if content_length else b""

        # Route
        if method == "POST" and path == "/webhook/waha":
            await _handle_waha_webhook(raw_body, headers)
            status, body = 200, b"ok"
        else:
            status, body = 404, b"not found"

        response = (
            f"HTTP/1.1 {status} OK\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + body

        writer.write(response)
        await writer.drain()
    except Exception:
        logger.exception("Error handling webhook connection")
    finally:
        writer.close()
        await writer.wait_closed()


async def serve_webhook(host: str = "0.0.0.0", port: int = 8001) -> None:
    """Start the asyncio webhook HTTP server and run until cancelled."""
    server = await asyncio.start_server(_handle_connection, host, port)
    logger.info("Webhook receiver listening on %s:%d", host, port)
    async with server:
        await server.serve_forever()
