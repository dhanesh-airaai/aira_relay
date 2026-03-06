"""Domain-level exceptions for the WhatsApp messaging layer.

These are raised by IMessagingPort implementations (e.g. WahaClient) so that
core services can handle messaging errors without importing any transport library.
"""

from __future__ import annotations


class WhatsAppError(Exception):
    """Base class for all WhatsApp/WAHA errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class WhatsAppAuthError(WhatsAppError):
    """Raised when WAHA returns 401 — API key mismatch or session not authorised."""


class WhatsAppNetworkError(WhatsAppError):
    """Raised when the WAHA host is unreachable."""
