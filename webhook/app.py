"""Starlette webhook application — receives WAHA HTTP callbacks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from infra.waha.wire_models import (
    IncomingMessagePayload,
    SessionStatusPayload,
    WahaEventType,
    WahaWebhookEvent,
)

if TYPE_CHECKING:
    from infra.waha.client import WahaClient
    from webhook.processor import WebhookProcessor

logger = logging.getLogger(__name__)


def build_webhook_app(
    processor: WebhookProcessor,
    waha_client: WahaClient,
    webhook_secret: str | None = None,
) -> Starlette:
    """Create and return the Starlette webhook application."""

    async def waha_webhook(request: Request) -> Response:
        raw_body = await request.body()

        # Verify HMAC signature when a secret is configured
        if webhook_secret:
            hmac_header = request.headers.get("x-webhook-hmac", "")
            algorithm = request.headers.get("x-webhook-hmac-algorithm", "")
            if algorithm != "sha512" or not waha_client.verify_signature(
                raw_body, hmac_header
            ):
                logger.warning("Invalid WAHA webhook signature — request rejected")
                return Response(status_code=401)

        try:
            event = WahaWebhookEvent.model_validate_json(raw_body)
        except Exception as exc:
            logger.warning("Malformed webhook payload: %s", exc)
            return Response(status_code=400)

        if event.event == WahaEventType.MESSAGE and isinstance(
            event.payload, IncomingMessagePayload
        ):
            try:
                await processor.process_message(
                    session=event.session, payload=event.payload
                )
            except Exception:
                logger.exception("Error processing message event")

        elif event.event == WahaEventType.SESSION_STATUS and isinstance(
            event.payload, SessionStatusPayload
        ):
            try:
                await processor.process_session_status(
                    session=event.session,
                    payload=event.payload,
                    event_timestamp=event.timestamp,
                )
            except Exception:
                logger.exception("Error processing session.status event")

        return JSONResponse({"ok": True})

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/webhook/waha", waha_webhook, methods=["POST"]),
            Route("/health", health, methods=["GET"]),
        ],
    )
