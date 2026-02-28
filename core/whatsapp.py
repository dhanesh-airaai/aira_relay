from __future__ import annotations


async def send_message(contact: str, message: str) -> str:
    """Placeholder implementation for WhatsApp delivery."""
    raise NotImplementedError(
        "Implement WhatsApp sending logic in core/whatsapp.py "
        f"(contact={contact!r}, message_length={len(message)})"
    )
