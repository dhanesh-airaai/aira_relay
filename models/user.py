"""Relay user model — phone-number-based identity."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    """A Relay user identified by phone number."""

    id: str
    """MongoDB _id as string — used as user_id throughout the system."""

    phone_number: str
    """Phone number with country code, no + (e.g. '919876543210').
    Also used as the WAHA session name."""

    phone_number_token: str
    """HMAC-SHA256 token derived from phone_number.
    Used as the unique lookup key — never expose the plaintext in queries."""

    created_at: datetime
    """When the user was first registered."""
