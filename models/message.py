"""Message domain models."""

from __future__ import annotations

from pydantic import BaseModel


class MediaInfo(BaseModel):
    """Media attachment metadata attached to a message."""

    url: str
    mimetype: str


class ContentBlock(BaseModel):
    """A typed content block for structured message payloads sent to agents.

    One block per logical content unit: text body, image, audio, video, or
    generic resource.  Agents can render or process each block independently.
    """

    type: str
    text: str | None = None
    url: str | None = None
    mime_type: str | None = None
