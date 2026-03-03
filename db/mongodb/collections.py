"""MongoDB collection names and index definitions for the relay."""

from typing import Any

# Collection name constants
WHATSAPP_CHATS = "whatsapp_chats"
CONTACT_PROFILES = "contact_profiles"
CHAT_MEMORY = "chat_memory"
USER_STATE = "user_state"

# Index definitions per collection
# Each entry: {"key": field_name, "unique": bool (optional)}
INDEXES: dict[str, list[dict[str, Any]]] = {
    WHATSAPP_CHATS: [
        {"key": [("user_id", 1)]},
        {"key": [("chat_id", 1)]},
        {"key": [("user_id", 1), ("moderation_status", 1)]},
        {"key": [("w_chat_id", 1)]},
        {"key": [("w_lid", 1)]},
    ],
    CONTACT_PROFILES: [
        {"key": [("user_id", 1)]},
        {"key": [("contact_id", 1)]},
        {"key": [("user_id", 1), ("contact_id", 1)], "unique": True},
    ],
    CHAT_MEMORY: [
        {"key": [("user_id", 1)]},
        {"key": [("chat_id", 1)]},
        {"key": [("timestamp", -1)]},
    ],
    USER_STATE: [
        {"key": [("user_id", 1)], "unique": True},
    ],
}
