"""Startup-safe database initialization for the relay."""

import logging

from config.settings import settings
from db.mongodb.manager import mongo
from db.qdrant.collections import COLLECTION_CONFIGS
from db.qdrant.manager import qdrant

logger = logging.getLogger(__name__)


async def initialize_databases() -> None:
    """Initialize all database connections and ensure indexes/collections exist.

    This function is idempotent — safe to call on every startup.
    No destructive operations are performed.
    """
    logger.info("Initializing relay databases...")

    # MongoDB
    await mongo.connect(settings.mongo_uri, settings.mongo_db_name)
    await mongo.ensure_indexes()

    # Qdrant
    await qdrant.connect(settings.qdrant_url, settings.qdrant_api_key)
    for collection_name, cfg in COLLECTION_CONFIGS.items():
        await qdrant.ensure_collection(
            name=collection_name,
            size=settings.embedding_dimensions,
            distance=cfg["distance"],
        )
        for idx in cfg.get("payload_indexes", []):
            await qdrant.ensure_payload_index(
                collection_name=collection_name,
                field_name=idx["field"],
                field_schema=idx["schema"],
            )

    logger.info("Relay databases initialized successfully")
