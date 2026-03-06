"""Pure conversation-text builder — no IO.

Accepts pre-resolved sender names so that all async DB/HTTP work is done
upstream (in services) before calling this helper.
"""

from __future__ import annotations

from typing import Any


def build_conversation_text(
    messages: list[dict[str, Any]],
    is_group: bool,
    sender_map: dict[str, str],
) -> str:
    """Build a human-readable transcript from raw WAHA message dicts.

    Args:
        messages:   Raw WAHA message objects (newest-first or oldest-first).
        is_group:   True when the chat is a group (uses 'participant' field for sender).
        sender_map: Pre-resolved mapping of JID → display name.  Missing JIDs
                    fall back to the bare phone number extracted from the JID.

    Returns:
        Newline-joined transcript, e.g. ``[msg_id:xxx] [Alice]: Hello``.
        Empty string when no text messages are present.
    """
    lines: list[str] = []
    for msg in messages:
        text: str | None = msg.get("body") or msg.get("text")
        if not text:
            continue

        if msg.get("fromMe"):
            prefix = "[Me]"
        else:
            sender_id: str = (msg.get("participant") if is_group else msg.get("from")) or ""
            name = sender_map.get(sender_id) or sender_id.split("@")[0] or "Unknown"
            prefix = f"[{name}]"

        msg_id: str = msg.get("id") or ""
        lines.append(f"[msg_id:{msg_id}] {prefix}: {text}")

    return "\n".join(lines)
