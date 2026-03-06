"""ContactService — contact lookup and phonetic indexing."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

from helpers.phonetic import (
    aggregate_by_key,
    extract_phonetic_entries,
    get_phonetic_tags,
    intersect_id_sets,
)
from models.responses import ContactSearchResult
from models.vector import VectorPoint

if TYPE_CHECKING:
    from ports.embedding import IEmbeddingAdapter
    from ports.messaging import IMessagingPort
    from ports.repositories import IChatRepo
    from ports.vector_store import IVectorStore

logger = logging.getLogger(__name__)

# Logical name of the phonetic-search vector collection (mirrors infra/qdrant/collections.py)
_PHONETIC_COLLECTION = "raw_info"

_SCORE_THRESHOLD = 0.75
_SEARCH_CONCURRENCY = 5


class ContactService:
    """Handles contact retrieval, phonetic indexing, and name-based search."""

    def __init__(
        self,
        messaging: IMessagingPort,
        chat_repo: IChatRepo,
        vector_store: IVectorStore | None = None,
        embedding: IEmbeddingAdapter | None = None,
    ) -> None:
        self._messaging = messaging
        self._chat_repo = chat_repo
        self._vector_store = vector_store
        self._embedding = embedding

    # ------------------------------------------------------------------
    # Contact retrieval
    # ------------------------------------------------------------------

    async def get_all_contacts(
        self,
        *,
        session: str,
        limit: int = 1000,
        offset: int = 0,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> dict[str, Any]:
        contacts = await self._messaging.get_all_contacts(
            session=session,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return {"success": True, "data": contacts}

    async def get_contact_details(
        self, *, session: str, contact_id: str
    ) -> dict[str, Any]:
        details = await self._messaging.get_contact_details(
            contact_id=contact_id, session=session
        )
        return {"success": True, "data": details.model_dump()}

    async def get_group(self, *, session: str, group_id: str) -> dict[str, Any]:
        data = await self._messaging.get_group(session=session, group_id=group_id)
        return {"success": True, "data": data}

    # ------------------------------------------------------------------
    # Phonetic indexing helpers
    # ------------------------------------------------------------------

    async def _bounded_embed(self, tags: list[str]) -> list[list[float]]:
        if not tags or self._embedding is None:
            return []
        return await self._embedding.embed_batch(tags)

    async def _bounded_search(
        self, vectors: list[list[float]], user_id: str
    ) -> list[list[dict[str, Any]]]:
        if not vectors or self._vector_store is None:
            return []
        filters = [
            {"key": "user_id", "value": user_id},
            {"key": "source", "value": "whatsapp"},
        ]
        all_results: list[list[dict[str, Any]]] = []
        for start in range(0, len(vectors), _SEARCH_CONCURRENCY):
            chunk = vectors[start : start + _SEARCH_CONCURRENCY]
            chunk_results = await asyncio.gather(
                *(
                    self._vector_store.search(
                        collection_name=_PHONETIC_COLLECTION,
                        query_vector=v,
                        limit=10,
                        with_payload=True,
                        score_threshold=_SCORE_THRESHOLD,
                        filters=filters,
                    )
                    for v in chunk
                )
            )
            for scored_points in chunk_results:
                payloads = [
                    sp.payload
                    for sp in scored_points
                    if sp.payload
                ]
                all_results.append(payloads)
        return all_results

    # ------------------------------------------------------------------
    # Index contacts into Qdrant
    # ------------------------------------------------------------------

    async def add_to_phonetic_index(
        self,
        contacts: list[dict[str, Any]],
        user_id: str,
    ) -> dict[str, Any]:
        """Index a list of contacts for phonetic name search (idempotent)."""
        if not contacts or self._vector_store is None or self._embedding is None:
            return {"status": "skipped", "reason": "not_configured"}

        phonetic_entries, key_words = extract_phonetic_entries(contacts)
        if not phonetic_entries:
            return {"status": "skipped", "reason": "no_phonetic_entries"}

        scroll_filters = [
            {"key": "key", "any": key_words},
            {"key": "user_id", "value": user_id},
            {"key": "source", "value": "whatsapp"},
        ]
        existing_records, _ = await self._vector_store.scroll(
            collection_name=_PHONETIC_COLLECTION,
            filters=scroll_filters,
            limit=1000,
        )

        existing_key_map: dict[str, dict[str, Any]] = {}
        existing_point_ids: dict[str, str] = {}
        for record in existing_records:
            if record.payload:
                payload = record.payload
                existing_key_map[payload.get("key", "")] = payload
                existing_point_ids[payload.get("key", "")] = str(record.id)

        filtered_entries: list[tuple[str, str, str]] = []
        for tag, word, w_chat_id in phonetic_entries:
            if word not in existing_key_map:
                filtered_entries.append((tag, word, w_chat_id))
            elif w_chat_id not in existing_key_map[word].get("mongo_id", []):
                filtered_entries.append((tag, word, w_chat_id))

        if not filtered_entries:
            return {"status": "skipped", "reason": "all_keys_exist"}

        unique_tags = list({entry[0] for entry in filtered_entries})
        vectors = await self._bounded_embed(unique_tags)
        tag_to_vector: dict[str, list[float]] = dict(
            zip(unique_tags, vectors, strict=False)
        )

        key_to_data = aggregate_by_key(filtered_entries)
        points: list[VectorPoint] = []

        for word, (tag, new_w_chat_ids) in key_to_data.items():
            merged_ids = set(new_w_chat_ids)
            point_id = str(uuid.uuid4())

            if word in existing_key_map:
                merged_ids.update(existing_key_map[word].get("mongo_id", []))
                point_id = existing_point_ids.get(word, point_id)

            if tag not in tag_to_vector:
                continue

            points.append(
                VectorPoint(
                    id=point_id,
                    vector=tag_to_vector[tag],
                    payload={
                        "user_id": user_id,
                        "key": word,
                        "mongo_id": list(merged_ids),
                        "source": "whatsapp",
                    },
                )
            )
            logger.debug("Prepared vector point for word '%s' (chat IDs: %s)", word, merged_ids)

        if points:
            await self._vector_store.upsert(_PHONETIC_COLLECTION, points)

        logger.info(
            "Indexed %d phonetic contact points for user %s", len(points), user_id
        )
        return {"status": "ok", "indexed_points": len(points)}

    # ------------------------------------------------------------------
    # Search contacts by name
    # ------------------------------------------------------------------

    async def find_contact_by_name(
        self,
        *,
        query: str,
        user_id: str,
        session: str,
    ) -> list[ContactSearchResult]:
        """Find contacts by name using phonetic search with Qdrant fallback."""
        if not query:
            return []

        phonetic_tags = get_phonetic_tags(query)
        if not phonetic_tags:
            return []

        # Phonetic + semantic search via Qdrant
        if self._vector_store is not None and self._embedding is not None:
            embedding_vectors = await self._bounded_embed(phonetic_tags)
            raw_results = await self._bounded_search(embedding_vectors, user_id)

            # Intersect w_chat_ids across all query words
            id_sets: list[set[str]] = []
            for word_results in raw_results:
                word_ids: set[str] = {
                    cid
                    for payload in word_results
                    for cid in payload.get("mongo_id", [])
                }
                if word_ids:
                    id_sets.append(word_ids)
            matched_ids = intersect_id_sets(id_sets)

            if matched_ids:
                docs = await self._chat_repo.find_many(
                    {"user_id": user_id, "w_chat_id": {"$in": list(matched_ids)}}
                )
                doc_by_id: dict[str, dict[str, Any]] = {
                    d["w_chat_id"]: d for d in docs
                }
                return [
                    ContactSearchResult(
                        w_chat_id=cid,
                        chat_name=(
                            (doc_by_id[cid].get("chat_name") or cid)
                            if cid in doc_by_id
                            else cid
                        ),
                        description=(
                            (doc_by_id[cid].get("description") or "")
                            if cid in doc_by_id
                            else ""
                        ),
                    )
                    for cid in matched_ids
                ]

        # Fallback: substring match via WAHA contacts API
        contacts = await self._messaging.get_all_contacts(session=session)
        query_lower = query.lower()
        return [
            ContactSearchResult(
                w_chat_id=c.get("id", ""),
                chat_name=c.get("name") or c.get("pushname") or "",
                description=c.get("status") or "",
            )
            for c in contacts
            if query_lower in (c.get("name") or c.get("pushname") or "").lower()
        ]

    async def index_all_contacts(self, *, session: str, user_id: str) -> dict[str, Any]:
        """Fetch all WAHA contacts and index them for phonetic search."""
        if self._vector_store is None or self._embedding is None:
            return {"status": "skipped", "reason": "not_configured"}
        contacts = await self._messaging.get_all_contacts(session=session)
        return await self.add_to_phonetic_index(contacts, user_id)
