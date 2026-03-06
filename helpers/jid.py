"""Pure WhatsApp JID / identifier utilities — no IO, no external imports."""

from __future__ import annotations


def strip_suffix(jid: str) -> str:
    """Remove @c.us, @g.us, or @lid suffix from a JID."""
    return jid.replace("@c.us", "").replace("@g.us", "").replace("@lid", "").strip()


def is_group_jid(jid: str) -> bool:
    return jid.endswith("@g.us")


def is_lid_jid(jid: str) -> bool:
    return "@lid" in jid


def to_c_us(phone: str) -> str:
    """Convert a bare phone number (or already-suffixed JID) to @c.us format."""
    phone = phone.replace("@c.us", "").replace("@g.us", "").strip()
    return f"{phone}@c.us"
