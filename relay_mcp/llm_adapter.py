"""McpLLMAdapter — implements ILLMAdapter using MCP sampling (ctx.create_message)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import mcp.types as mcp_types

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

logger = logging.getLogger(__name__)


class McpLLMAdapter:
    """Wraps the FastMCP Context sampling API to satisfy ILLMAdapter."""

    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        session: str = "",
    ) -> str:
        result = await self._ctx.request_context.session.create_message(
            messages=[
                mcp_types.SamplingMessage(
                    role="user",
                    content=mcp_types.TextContent(type="text", text=prompt),
                )
            ],
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        return result.content.text
