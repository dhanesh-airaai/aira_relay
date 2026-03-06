"""Pure content-block builder for structured media events — no IO."""

from __future__ import annotations

from models.message import ContentBlock


def build_content_blocks(
    body: str | None,
    has_media: bool,
    media_url: str,
    media_mimetype: str,
) -> list[ContentBlock]:
    """Build typed MCP content blocks from raw message fields.

    One text block for the message body (when present) and one typed media
    block for the attachment (image / audio / video / resource).
    """
    blocks: list[ContentBlock] = []

    if body:
        blocks.append(ContentBlock(type="text", text=body))

    if has_media and media_url:
        if media_mimetype.startswith("image/"):
            blocks.append(ContentBlock(type="image", url=media_url, mime_type=media_mimetype))
        elif media_mimetype.startswith("audio/"):
            blocks.append(ContentBlock(type="audio", url=media_url, mime_type=media_mimetype))
        elif media_mimetype.startswith("video/"):
            blocks.append(ContentBlock(type="video", url=media_url, mime_type=media_mimetype))
        else:
            blocks.append(ContentBlock(type="resource", url=media_url, mime_type=media_mimetype))

    return blocks
