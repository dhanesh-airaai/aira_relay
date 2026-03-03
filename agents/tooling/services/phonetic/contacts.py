"""WhatsApp phonetic contact search — ported from aira-api WhatsappPhoneticSearch."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

from pyphonetics import Metaphone  # type: ignore[reportMissingTypeStubs]
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue, PointStruct

from db.mongodb.collections import WHATSAPP_CHATS
from db.qdrant.collections import RAW_INFO

if TYPE_CHECKING:
    from adapters.embedding import EmbeddingsClass
    from db.mongodb.manager import MongoManager
    from db.qdrant.manager import QdrantManager

logger = logging.getLogger(__name__)

# Metaphone singleton — phonetic encoder (same as aira-api)
_metaphone: Metaphone = Metaphone()

# Similarity threshold — same as aira-api source default
_SCORE_THRESHOLD = 0.75

# ------------------------------------------------------------------
# Relay-native payload model (mirrors aira-api VectorModels.RawInfo)
# ------------------------------------------------------------------


class RawInfoPayload:
    """Qdrant payload for a phonetic contact key."""

    __slots__ = ("user_id", "key", "mongo_id", "source")

    def __init__(self, user_id: str, key: str, mongo_id: list[str], source: str = "whatsapp") -> None:
        self.user_id = user_id
        self.key = key
        self.mongo_id = mongo_id
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {"user_id": self.user_id, "key": self.key, "mongo_id": self.mongo_id, "source": self.source}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RawInfoPayload:
        return cls(
            user_id=str(d.get("user_id", "")),
            key=str(d.get("key", "")),
            mongo_id=list(d.get("mongo_id", [])),
            source=str(d.get("source", "whatsapp")),
        )


# ------------------------------------------------------------------
# Main service class
# ------------------------------------------------------------------


class WhatsappPhoneticSearch:
    """Phonetic + semantic contact search using Metaphone and Qdrant.

    Mirrors the logic of aira-api's WhatsappPhoneticSearch with relay-native
    dependencies (no app.* imports).
    """

    def __init__(
        self,
        qdrant: QdrantManager,
        mongo: MongoManager,
        embeddings: EmbeddingsClass,
        embed_concurrency: int = 5,
        search_concurrency: int = 5,
    ) -> None:
        self._qdrant = qdrant
        self._mongo = mongo
        self._embeddings = embeddings
        self._embed_concurrency = embed_concurrency
        self._search_concurrency = search_concurrency

    # ------------------------------------------------------------------
    # Embedding helpers (bounded fan-out)
    # ------------------------------------------------------------------

    async def _bounded_embed(self, tags: list[str]) -> list[list[float]]:
        """Compute embeddings in bounded parallel chunks."""
        if not tags:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(tags), self._embed_concurrency):
            chunk = tags[start : start + self._embed_concurrency]
            chunk_vectors = await asyncio.gather(*(self._embeddings.embed_text(t) for t in chunk))
            vectors.extend(chunk_vectors)
        return vectors

    async def _bounded_search(self, vectors: list[list[float]], user_id: str) -> list[list[RawInfoPayload]]:
        """Run similarity searches in bounded parallel chunks."""
        if not vectors:
            return []

        filters = [
            {"key": "user_id", "value": user_id},
            {"key": "source", "value": "whatsapp"},
        ]
        all_results: list[list[RawInfoPayload]] = []
        for start in range(0, len(vectors), self._search_concurrency):
            chunk = vectors[start : start + self._search_concurrency]
            chunk_results = await asyncio.gather(
                *(
                    self._qdrant.search(
                        collection_name=RAW_INFO,
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
                    RawInfoPayload.from_dict(sp.payload or {})
                    for sp in scored_points
                    if sp.payload
                ]
                all_results.append(payloads)
        return all_results

    # ------------------------------------------------------------------
    # Phonetic extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_phonetic_entries(
        contacts: list[dict[str, Any]],
    ) -> tuple[list[tuple[str, str, str]], list[str]]:
        """Extract (phonetic_tag, original_word, w_chat_id) from contact names.

        Returns:
            (phonetic_entries, key_words) — list of entries and all unique words.
        """
        phonetic_entries: list[tuple[str, str, str]] = []
        key_words: list[str] = []

        for contact in contacts:
            chat_name = contact.get("name") or contact.get("pushname") or ""
            w_chat_id = contact.get("id") or contact.get("w_chat_id") or ""
            if not chat_name or not w_chat_id:
                continue

            for word in chat_name.split():
                stripped = word.strip()
                if not stripped:
                    continue
                key_words.append(stripped)
                tag: str = _metaphone.phonetics(stripped)  # type: ignore[reportUnknownMemberType]
                if tag:
                    phonetic_entries.append((tag, stripped, w_chat_id))

        return phonetic_entries, key_words

    @staticmethod
    def _aggregate_by_key(
        phonetic_entries: list[tuple[str, str, str]],
    ) -> dict[str, tuple[str, set[str]]]:
        """Map each original_word → (phonetic_tag, set of w_chat_ids)."""
        key_to_data: dict[str, tuple[str, set[str]]] = {}
        for tag, word, w_chat_id in phonetic_entries:
            if word in key_to_data:
                key_to_data[word][1].add(w_chat_id)
            else:
                key_to_data[word] = (tag, {w_chat_id})
        return key_to_data

    # ------------------------------------------------------------------
    # Index contacts into Qdrant
    # ------------------------------------------------------------------

    async def add_contacts_to_qdrant(
        self,
        contacts: list[dict[str, Any]],
        user_id: str,
    ) -> dict[str, Any]:
        """Index a list of WhatsApp contacts in Qdrant for phonetic search.

        Args:
            contacts: List of contact dicts (from WAHA get_all_contacts).
                      Must have 'id' (w_chat_id) and 'name'/'pushname'.
            user_id: Relay user identifier.

        Returns:
            Status dict.
        """
        if not contacts:
            return {"status": "skipped", "reason": "no_contacts"}

        phonetic_entries, key_words = self._extract_phonetic_entries(contacts)
        if not phonetic_entries:
            return {"status": "skipped", "reason": "no_phonetic_entries"}

        # Fetch existing entries from Qdrant to avoid duplicates and to merge mongo_ids
        scroll_filter = Filter(
            must=[
                FieldCondition(key="key", match=MatchAny(any=key_words)),
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="source", match=MatchValue(value="whatsapp")),
            ]
        )
        existing_records, _ = await self._qdrant.scroll(
            collection_name=RAW_INFO,
            scroll_filter=scroll_filter,
            limit=1000,
        )

        existing_key_map: dict[str, RawInfoPayload] = {}
        existing_point_ids: dict[str, str] = {}
        for record in existing_records:
            if record.payload:
                payload = RawInfoPayload.from_dict(record.payload)
                existing_key_map[payload.key] = payload
                existing_point_ids[payload.key] = str(record.id)

        # Only process entries that are new or have new w_chat_ids
        filtered_entries: list[tuple[str, str, str]] = []
        for tag, word, w_chat_id in phonetic_entries:
            if word not in existing_key_map:
                filtered_entries.append((tag, word, w_chat_id))
            elif w_chat_id not in existing_key_map[word].mongo_id:
                filtered_entries.append((tag, word, w_chat_id))

        if not filtered_entries:
            return {"status": "skipped", "reason": "all_keys_exist"}

        # Embed unique phonetic tags
        unique_tags = list({entry[0] for entry in filtered_entries})
        vectors = await self._bounded_embed(unique_tags)
        tag_to_vector: dict[str, list[float]] = dict(zip(unique_tags, vectors, strict=False))

        # Build Qdrant upsert points
        key_to_data = self._aggregate_by_key(filtered_entries)
        points: list[PointStruct] = []

        for word, (tag, new_w_chat_ids) in key_to_data.items():
            merged_ids = set(new_w_chat_ids)
            point_id = str(uuid.uuid4())

            if word in existing_key_map:
                merged_ids.update(existing_key_map[word].mongo_id)
                point_id = existing_point_ids.get(word, point_id)

            if tag not in tag_to_vector:
                continue

            payload = RawInfoPayload(
                user_id=user_id,
                key=word,
                mongo_id=list(merged_ids),
                source="whatsapp",
            )
            points.append(
                PointStruct(
                    id=point_id,
                    vector=tag_to_vector[tag],
                    payload=payload.to_dict(),
                )
            )

        if points:
            await self._qdrant.upsert(RAW_INFO, points)

        logger.info("Indexed %d phonetic contact points for user %s", len(points), user_id)
        return {"status": "ok", "indexed_points": len(points)}

    # ------------------------------------------------------------------
    # Search contacts by name
    # ------------------------------------------------------------------

    @staticmethod
    def _get_phonetic_tags(query: str) -> list[str]:
        """Generate Metaphone phonetic tags for each word in the query."""
        tags: list[str] = []
        for word in query.split():
            stripped = word.strip()
            if not stripped:
                continue
            tag: str = _metaphone.phonetics(stripped)  # type: ignore[reportUnknownMemberType]
            if tag:
                tags.append(tag)
        return tags

    @staticmethod
    def _intersect_mongo_ids(search_results: list[list[RawInfoPayload]]) -> set[str]:
        """Intersect mongo_id sets from multi-word search results.

        Single-word query → union of all IDs from that word's results.
        Multi-word query → intersection across words (contact must match ALL words).
        """
        id_sets: list[set[str]] = []
        for word_results in search_results:
            word_ids: set[str] = {cid for raw in word_results for cid in raw.mongo_id}
            if word_ids:
                id_sets.append(word_ids)

        if not id_sets:
            return set()
        return id_sets[0] if len(id_sets) == 1 else id_sets[0].intersection(*id_sets[1:])

    async def search_contact_by_name(
        self,
        query: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Search for WhatsApp contacts by name using phonetic matching.

        Args:
            query: Name to search for (partial, fuzzy OK — e.g. 'Jon' matches 'John').
            user_id: Relay user identifier.

        Returns:
            List of contact dicts with w_chat_id, chat_name, description.
        """
        if not query:
            return []

        phonetic_tags = self._get_phonetic_tags(query)
        if not phonetic_tags:
            return []

        # Embed each phonetic tag and search Qdrant
        embedding_vectors = await self._bounded_embed(phonetic_tags)
        search_results = await self._bounded_search(embedding_vectors, user_id)

        # Intersect w_chat_ids across all query words
        matched_chat_ids = self._intersect_mongo_ids(search_results)
        if not matched_chat_ids:
            return []

        # Look up MongoDB whatsapp_chats for display names
        mongo_docs = await self._mongo.find_many(
            WHATSAPP_CHATS,
            {"user_id": user_id, "w_chat_id": {"$in": list(matched_chat_ids)}},
        )

        # Build result dicts — merge: MongoDB doc name > w_chat_id fallback
        doc_by_id: dict[str, dict[str, Any]] = {doc["w_chat_id"]: doc for doc in mongo_docs}
        results: list[dict[str, Any]] = []
        for w_chat_id in matched_chat_ids:
            doc = doc_by_id.get(w_chat_id)
            results.append(
                {
                    "w_chat_id": w_chat_id,
                    "chat_name": (doc.get("chat_name") or w_chat_id) if doc else w_chat_id,
                    "description": (doc.get("description") or "") if doc else "",
                }
            )

        return results
