# AiRA Relay — Architecture

## What the App Does

AiRA Relay is a Python server with two responsibilities:

1. **MCP server** — exposes WhatsApp capabilities as MCP tools an AI agent can call.
2. **Webhook receiver** — listens for real-time events from WAHA, transforms them into typed internal events, and routes them to connected MCP clients or OpenClaw.

Both responsibilities share the same business logic, database connections, and service instances.

---

## The Three Core Principles

| Principle | What it means here |
|---|---|
| **Hexagonal Architecture** | `core/` never imports from `infra/` or `relay_mcp/`. It only knows about `ports/` (abstract interfaces). |
| **Dependency Inversion (DIP)** | High-level modules (`core/`) depend on abstractions (`ports/`). Low-level modules (`infra/`) implement those abstractions. |
| **Dependency Injection (DI)** | All concrete instances are created once in `lifespan.py` and passed into constructors. Nothing is instantiated at module load time. |

DIP defines *what* the contracts look like. Hexagonal Architecture defines *where* the code lives. DI defines *how* concrete implementations reach the code that needs them.

---

## Layered Architecture

```
┌──────────────────────────────────────────────────┐
│  Transport (relay_mcp/, webhook/)                │
│  MCP tools and webhook endpoint                  │
├──────────────────────────────────────────────────┤
│  Events (events/)                                │
│  Async pub/sub bus, MCP push, OpenClaw relay     │
├──────────────────────────────────────────────────┤
│  Core (core/)                                    │
│  All business logic — depends only on ports/     │
├──────────────────────────────────────────────────┤
│  Ports (ports/)                                  │
│  Abstract Protocol interfaces — no implementation│
├──────────────────────────────────────────────────┤
│  Infrastructure (infra/)                         │
│  WAHA client, MongoDB repos, Qdrant, OpenClaw    │
├──────────────────────────────────────────────────┤
│  Models (models/)                                │
│  Pydantic data classes — no external imports     │
└──────────────────────────────────────────────────┘
              ▲
         lifespan.py  (Composition Root — wires everything)
```

**The rule:** imports only flow downward. Nothing at a lower level imports from a higher level.

---

## Directory Structure

```
aira_Relay/
├── lifespan.py              # Composition root — builds the entire object graph
├── main.py                  # Entry point
│
├── models/                  # Pure domain models (Pydantic, no app imports)
│   ├── events.py            # IncomingMessageEvent, SessionStatusEvent, SyncChatsEvent
│   ├── responses.py         # ConnectResult, SyncResult, ScanResult
│   └── exceptions.py        # WhatsAppError hierarchy
│
├── ports/                   # Abstract interfaces (Python Protocol)
│   ├── messaging.py         # IMessagingPort — all WAHA operations
│   ├── repositories.py      # IUserRepo, IChatRepo, IStateRepo
│   ├── llm.py               # ILLMAdapter — text completion
│   ├── event_bus.py         # IEventBus — pub/sub contract
│   ├── embedding.py         # IEmbeddingAdapter
│   └── vector_store.py      # IVectorStore
│
├── core/                    # Business logic — imports only ports/
│   ├── user_service.py
│   ├── chat_service.py
│   ├── message_service.py
│   ├── contact_service.py
│   ├── connection_service.py
│   └── lid_resolver.py      # WhatsApp LID-to-phone JID resolution
│
├── infra/                   # Concrete implementations of ports
│   ├── waha/client.py       # WahaClient — implements IMessagingPort
│   ├── mongodb/             # MongoUserRepo, MongoChatRepo, MongoStateRepo
│   ├── qdrant/manager.py    # QdrantManager — implements IVectorStore
│   ├── openclaw.py          # OpenClawAdapter — implements ILLMAdapter
│   └── embedding.py         # EmbeddingAdapter
│
├── events/                  # Async event pub/sub
│   ├── bus.py               # EventBus — implements IEventBus
│   ├── mcp_handler.py       # Pushes events to MCP sessions + incoming queue
│   └── openclaw_handler.py  # Forwards events to OpenClaw
│
├── relay_mcp/               # MCP transport layer
│   ├── container.py         # McpContainer — holds all injected services
│   ├── server.py            # build_mcp_server() — registers all tools
│   ├── llm_adapter.py       # McpLLMAdapter — ILLMAdapter via MCP sampling
│   └── tools/               # One file per domain (messaging, chats, contacts, ...)
│
├── webhook/                 # Webhook transport layer
│   ├── app.py               # Starlette ASGI app
│   └── processor.py         # Parses WAHA events, publishes RelayEvents
│
└── utils/
    └── concurrency.py       # TaskRegistry — background asyncio tasks
```

---

## Layer Walkthrough

### models/ — Pure Domain

Pydantic data classes with zero application imports. Safe to import from any layer.

```python
# models/events.py
class IncomingMessageEvent(BaseModel):
    event: Literal["message"] = "message"
    session: str
    chat_id: str
    body: str = ""

RelayEvent = IncomingMessageEvent | SessionStatusEvent | SyncChatsEvent
```

---

### ports/ — Abstract Contracts

Python `Protocol` classes that define *what* a capability must do, not *how*.

```python
# ports/messaging.py
class IMessagingPort(Protocol):
    async def send_text(self, *, session: str, chat_id: str, text: str, ...) -> dict[str, Any]: ...
    async def get_messages(self, *, session: str, chat_id: str, ...) -> list[dict[str, Any]]: ...

# ports/llm.py
class ILLMAdapter(Protocol):
    async def complete(self, prompt: str, *, system_prompt: str | None = None, max_tokens: int = 1024) -> str: ...
```

---

### core/ — Business Logic

Services only accept and call port interfaces. They never import concrete classes.

```python
# core/chat_service.py
class ChatService:
    def __init__(
        self,
        messaging: IMessagingPort,   # not WahaClient
        chat_repo: IChatRepo,         # not MongoChatRepo
        event_bus: IEventBus,         # not EventBus
    ) -> None:
        ...
```

| Service | Ports injected |
|---|---|
| `UserService` | `IUserRepo` |
| `ChatService` | `IMessagingPort`, `IChatRepo`, `IEventBus` |
| `MessageService` | `IMessagingPort`, `IChatRepo`, `IStateRepo` |
| `ContactService` | `IMessagingPort`, `IChatRepo`, `IVectorStore`, `IEmbeddingAdapter` |
| `ConnectionService` | `IMessagingPort` |

---

### infra/ — Concrete Adapters

Each adapter implements a port using Python's structural subtyping (no explicit `implements` needed — just match the method signatures).

```python
# infra/waha/client.py — satisfies IMessagingPort
class WahaClient:
    async def send_text(self, *, session, chat_id, text, ...) -> dict:
        return await self._post(f"{self._base}/sendText", payload)

# infra/openclaw.py — satisfies ILLMAdapter
class OpenClawAdapter:
    async def complete(self, prompt, *, system_prompt=None, max_tokens=1024) -> str:
        # POST to OpenClaw /v1/chat/completions
```

`infra/` imports from `ports/` and `models/` but is **never imported by `core/`**.

---

### events/ — Async Pub/Sub

Decouples event producers (webhook, background tasks) from consumers (MCP sessions, OpenClaw).

```python
# events/bus.py
class EventBus:
    async def publish(self, event: RelayEvent) -> None:
        await asyncio.gather(*(h(event) for h in self._handlers))
```

At startup, two handlers are subscribed:

- **McpEventHandler** — queues `IncomingMessageEvent` for the `get_incoming_message` poll tool; pushes all events as log notifications to live MCP sessions.
- **OpenClawHandler** — forwards events to OpenClaw (only when `OPENCLAW_URL` is set).

---

### relay_mcp/ — MCP Transport

`McpContainer` is a plain data class holding all services. It is passed into every tool registration function.

```python
# relay_mcp/container.py
class McpContainer:
    def __init__(self, user_service, chat_service, message_service, ...) -> None:
        ...
```

Tools are thin: they translate parameters and delegate to core services.

```python
# relay_mcp/tools/messaging.py
def register_messaging_tools(mcp: FastMCP, c: McpContainer) -> None:
    @mcp.tool()
    async def send_text_message(chat_id: str, text: str, phone_number: str, ...) -> dict:
        await c.user_service.get_or_create(phone_number)
        return await c.message_service.send_text(session=phone_number, chat_id=chat_id, text=text, ...)
```

LLM selection happens at the tool boundary — OpenClaw if configured, otherwise the MCP-connected model via `McpLLMAdapter`. Both satisfy `ILLMAdapter`, so core services are unaware of the difference.

```python
llm = c.openclaw if c.openclaw.is_configured else McpLLMAdapter(ctx)
await c.message_service.get_messages_summary(..., llm=llm)
```

---

### lifespan.py — Composition Root

The only file that instantiates concrete classes. Everything is built once, wired together, and shared.

```python
async def lifespan():
    # Infrastructure
    waha_client = WahaClient(...)
    chat_repo   = MongoChatRepo(mongo)

    # Core services (receive ports, not concrete classes)
    chat_service    = ChatService(messaging=waha_client, chat_repo=chat_repo, ...)
    message_service = MessageService(messaging=waha_client, ...)

    # Events
    event_bus = EventBus()
    event_bus.subscribe(McpEventHandler().handle)

    # Transport — both share the same service instances
    mcp_server   = build_mcp_server(McpContainer(chat_service=chat_service, ...))
    webhook_app  = build_webhook_app(WebhookProcessor(messaging=waha_client, ...))

    yield AppComponents(mcp_server, webhook_app)
```

---

## Why These Patterns

### Hexagonal Architecture

Without it, HTTP calls and DB queries leak into business logic. With it, `core/` describes *what* needs to happen; `infra/` describes *how*. Swapping WAHA for a different WhatsApp API means writing a new `IMessagingPort` implementation — zero changes to `core/`.

### Dependency Inversion

`core/` imports abstractions (`IMessagingPort`), not concrete classes (`WahaClient`). The import arrow points from `infra/` toward `ports/`, never the other way. This keeps the dependency graph acyclic and makes each layer independently testable.

### Dependency Injection

No module-level singletons. `lifespan.py` creates each instance once and passes it through constructors. This guarantees:
- The MCP server and webhook receiver share the same `EventBus`, `WahaClient`, and service instances.
- Configuration is loaded before any service is built.
- Circular imports cannot happen because no module imports a live object from another — only type annotations (under `TYPE_CHECKING`) at static analysis time.

---

## Circular Import Prevention

Two techniques keep imports acyclic:

**`TYPE_CHECKING` guard** — cross-layer type references are placed inside `if TYPE_CHECKING:`, which is `False` at runtime:

```python
from __future__ import annotations   # annotations are strings, not evaluated

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ports.messaging import IMessagingPort   # never runs at runtime
```

The actual object arrives via constructor injection, so the runtime import is unnecessary.

**Strict layering** — the import DAG:

```
models/     →  (nothing)
ports/      →  models/
core/       →  ports/, models/
infra/      →  ports/, models/
events/     →  models/, ports/
relay_mcp/  →  core/ (TYPE_CHECKING only)
lifespan.py →  everything (once, at startup)
```

---

## Data Flows

### Incoming message

```
WAHA  →  POST /webhook/waha
         webhook/app.py (verifies HMAC)
         WebhookProcessor.process_message()
           resolves LID, looks up user + chat
           publishes IncomingMessageEvent via EventBus
                    │
           ┌────────┴────────┐
    McpEventHandler    OpenClawHandler
    queues event        POSTs to OpenClaw
    pushes to sessions
           │
    get_incoming_message tool
    pops from queue → returns to AI agent
```

### Outgoing tool call

```
AI agent  →  send_text_message MCP tool
             relay_mcp/tools/messaging.py
             MessageService.send_text()
             WahaClient.send_text()
               mark seen → start typing → delay → POST /sendText
             ← {"success": true, "message_id": "..."}
```
