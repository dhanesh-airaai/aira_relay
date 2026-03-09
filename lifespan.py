"""Application assembly — builds the complete object graph.

Use ``lifespan()`` as an async context manager at startup.  It yields the
fully-wired MCP FastMCP server and Starlette webhook application, sharing a
single set of service instances (no duplicate clients, no module-level
singletons).  On exit it drains background tasks and disconnects from MongoDB.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.applications import Starlette

logger = logging.getLogger(__name__)


@dataclass
class AppComponents:
    mcp_server: FastMCP
    webhook_app: Starlette


@contextlib.asynccontextmanager
async def lifespan() -> AsyncIterator[AppComponents]:
    """Async context manager that builds, yields, and tears down all app components."""
    from config.settings import settings

    # ------------------------------------------------------------------
    # Layer 4 — infra
    # ------------------------------------------------------------------
    from infra.fastembed_adapter import FastEmbedAdapter
    from infra.mongodb.manager import MongoManager
    from infra.openclaw import OpenClawAdapter
    from infra.openrouter import OpenRouterAdapter
    from infra.qdrant.manager import QdrantManager
    from infra.waha.client import WahaClient

    mongo = MongoManager()
    await mongo.connect(settings.mongo_uri, settings.mongo_db_name)
    await mongo.ensure_indexes()

    qdrant = QdrantManager()
    await qdrant.connect(settings.qdrant_url, api_key=settings.qdrant_api_key)

    # Ensure Qdrant collections exist
    from infra.qdrant.collections import COLLECTION_CONFIGS
    from qdrant_client.models import Distance

    for coll_name, cfg in COLLECTION_CONFIGS.items():
        with contextlib.suppress(Exception):
            await qdrant.ensure_collection(
                coll_name,
                size=settings.embedding_dimensions,
                distance=cfg.get("distance", Distance.COSINE),
            )
        for idx in cfg.get("payload_indexes", []):
            with contextlib.suppress(Exception):
                await qdrant.ensure_payload_index(
                    coll_name,
                    field_name=idx["field"],
                    field_schema=idx["schema"],
                )

    waha_client = WahaClient(
        base_url=settings.waha_base_url,
        api_key=settings.waha_api_key,
        webhook_secret=settings.waha_webhook_secret,
    )

    embedding = FastEmbedAdapter()

    openclaw = OpenClawAdapter(settings)
    openrouter = OpenRouterAdapter(settings)

    # ------------------------------------------------------------------
    # Repositories
    # ------------------------------------------------------------------
    from infra.mongodb.chat_repo import MongoChatRepo, MongoContactProfileRepo
    from infra.mongodb.state_repo import MongoStateRepo
    from infra.mongodb.user_repo import MongoUserRepo

    user_repo = MongoUserRepo(mongo)
    chat_repo = MongoChatRepo(mongo)
    contact_profile_repo = MongoContactProfileRepo(mongo)
    state_repo = MongoStateRepo(mongo)

    # ------------------------------------------------------------------
    # Background task registry
    # ------------------------------------------------------------------
    from utils.concurrency import TaskRegistry

    task_registry = TaskRegistry()

    # ------------------------------------------------------------------
    # Layer 5 — core services
    # ------------------------------------------------------------------
    from core.chat_service import ChatService
    from core.connection_service import ConnectionService
    from core.contact_service import ContactService
    from core.lid_resolver import LidResolver
    from core.message_service import MessageService
    from core.user_service import UserService

    # EventBus is needed by ChatService, so build it first
    from events.bus import EventBus

    event_bus = EventBus()

    lid_resolver = LidResolver(
        messaging=waha_client,
        chat_repo=chat_repo,
        contact_profile_repo=contact_profile_repo,
    )

    user_service = UserService(
        user_repo=user_repo,
        token_secret=settings.token_secret,
    )

    contact_service = ContactService(
        messaging=waha_client,
        chat_repo=chat_repo,
        vector_store=qdrant,
        embedding=embedding,
    )

    chat_service = ChatService(
        messaging=waha_client,
        chat_repo=chat_repo,
        lid_resolver=lid_resolver,
        contact_svc=contact_service,
        event_bus=event_bus,
    )

    message_service = MessageService(
        messaging=waha_client,
        chat_repo=chat_repo,
        state_repo=state_repo,
        lid_resolver=lid_resolver,
    )

    connection_service = ConnectionService(
        messaging=waha_client,
        user_service=user_service,
    )

    # ------------------------------------------------------------------
    # Layer 6 — event handlers
    #
    # McpEventHandler: broadcasts all events to live MCP sessions and queues
    #   IncomingMessageEvents for the get_incoming_message tool.
    #
    # OpenClawHandler: forwards session.status and sync_chats events to OpenClaw
    #   via HTTP.  IncomingMessageEvents are NOT forwarded here — they are pushed
    #   directly (fire-and-forget) inside WebhookProcessor before media download,
    #   so the notification is immediate rather than waiting for enrichment.
    # ------------------------------------------------------------------
    from events.mcp_handler import McpEventHandler
    from events.openclaw_handler import OpenClawHandler

    mcp_event_handler = McpEventHandler()
    event_bus.subscribe(mcp_event_handler.handle)
    if openclaw.is_configured:
        openclaw_handler = OpenClawHandler(openclaw)
        event_bus.subscribe(openclaw_handler.handle)

    # ------------------------------------------------------------------
    # Layer 7a — MCP
    # ------------------------------------------------------------------
    from relay_mcp.container import McpContainer
    from relay_mcp.server import build_mcp_server

    container = McpContainer(
        user_service=user_service,
        chat_service=chat_service,
        message_service=message_service,
        contact_service=contact_service,
        connection_service=connection_service,
        event_bus=event_bus,
        openclaw=openrouter,
        task_registry=task_registry,
        mcp_handler=mcp_event_handler,
    )

    mcp_server = build_mcp_server(container)

    # ------------------------------------------------------------------
    # Layer 7b — webhook
    # ------------------------------------------------------------------
    from webhook.app import build_webhook_app
    from webhook.processor import WebhookProcessor

    processor = WebhookProcessor(
        messaging=waha_client,
        user_service=user_service,
        chat_service=chat_service,
        event_bus=event_bus,
        task_registry=task_registry,
        llm=openrouter if openrouter.is_configured else None,
        ignored_numbers=settings.ignored_numbers_set,
        openclaw=openclaw if openclaw.is_configured else None,
    )

    webhook_app = build_webhook_app(
        processor=processor,
        waha_client=waha_client,
        webhook_secret=settings.waha_webhook_secret,
    )

    logger.info("All application components initialised")

    try:
        yield AppComponents(mcp_server=mcp_server, webhook_app=webhook_app)
    finally:
        await task_registry.drain()
        await mongo.disconnect()
        logger.info("MongoDB disconnected — shutdown complete")
