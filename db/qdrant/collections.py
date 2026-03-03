"""Qdrant collection names and configuration for the relay.

Collection names intentionally match aira-api to allow shared Qdrant data.
"""

from qdrant_client.models import Distance

# Collection name constants
RAW_INFO = "raw_info"           # phonetic contact search index
MTM_CLUSTERS = "mtm_clusters"   # reserved for future COSMOS use
LTM_MEMORIES = "ltm_memories"  # reserved for future COSMOS use

# Per-collection vector config: (distance_metric,)
# Vector size is runtime-determined from settings.embedding_dimensions.
COLLECTION_CONFIGS: dict[str, dict] = {
    RAW_INFO: {
        "distance": Distance.COSINE,
        "payload_indexes": [
            {"field": "user_id", "schema": "keyword"},
            {"field": "source", "schema": "keyword"},
            {"field": "key", "schema": "keyword"},
        ],
    },
}
