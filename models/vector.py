"""Domain model for vector database points.

Keeps qdrant_client types out of the core layer — IVectorStore and all core
services use VectorPoint; infra/qdrant/manager.py converts to PointStruct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorPoint:
    """A single point to upsert into the vector store."""

    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)
