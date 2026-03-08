"""MCP service container — holds all injected service instances for MCP tools.

Populated once during application startup (lifespan.py) and injected into each
tool registration function.  No IO happens here; this is a plain data class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.chat_service import ChatService
    from core.connection_service import ConnectionService
    from core.contact_service import ContactService
    from core.message_service import MessageService
    from core.user_service import UserService
    from events.bus import EventBus
    from events.mcp_handler import McpEventHandler
    from ports.llm import ILLMAdapter
    from utils.concurrency import TaskRegistry


class McpContainer:
    """All services available to MCP tool handlers."""

    def __init__(
        self,
        user_service: UserService,
        chat_service: ChatService,
        message_service: MessageService,
        contact_service: ContactService,
        connection_service: ConnectionService,
        event_bus: EventBus,
        openclaw: ILLMAdapter,
        task_registry: TaskRegistry,
        mcp_handler: McpEventHandler,
    ) -> None:
        self.user_service = user_service
        self.chat_service = chat_service
        self.message_service = message_service
        self.contact_service = contact_service
        self.connection_service = connection_service
        self.event_bus = event_bus
        self.openclaw = openclaw
        self.tasks = task_registry
        self.mcp_handler = mcp_handler
