"""ILLMAdapter — abstract contract for LLM text completion.

Decouples core services from both MCP sampling (ctx.create_message) and the
OpenClaw chat-completions endpoint.  The correct implementation is chosen at
the transport boundary (tool call handler) and injected into the service.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ILLMAdapter(Protocol):
    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
    ) -> str: ...
