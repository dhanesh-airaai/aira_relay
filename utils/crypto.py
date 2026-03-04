"""Cryptographic utilities for the Relay."""

from __future__ import annotations

import base64
import hashlib
import hmac


def tokenize(value: str, secret: str) -> str:
    """Create a deterministic HMAC-SHA256 token from a string.

    The token is opaque and non-reversible. Two calls with the same
    value + secret always produce the same hex digest, making it safe
    to use as a lookup key without storing plaintext.

    Args:
        value: The plaintext string to tokenize (e.g. a phone number).
        secret: Base64-encoded HMAC key (from settings.token_secret).
                Falls back to raw SHA-256 if empty (dev/test only).

    Returns:
        64-character lowercase hex string.

    """
    normalized = value.lower().strip().encode("utf-8")
    if secret:
        key = base64.urlsafe_b64decode(secret + "==")  # tolerant padding
        return hmac.new(key, normalized, hashlib.sha256).hexdigest()
    # Dev fallback — no secret set, plain SHA-256
    return hashlib.sha256(normalized).hexdigest()
