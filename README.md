# AiRA Relay — Setup Guide

## What Is This

AiRA Relay is a Python server that puts WhatsApp capabilities inside an AI agent.
It exposes WhatsApp operations as MCP tools (send messages, read chats, search contacts)
and listens for incoming WhatsApp events to route them back to your agent in real time.

**What you will end up with after this guide:**

```
┌─────────────────┐        MCP tools         ┌──────────────────────┐
│   Your AI Agent │ ◄──────────────────────► │   AiRA Relay (8000)  │
│ (Claude / MCP)  │                           │   MCP HTTP server    │
└─────────────────┘                           └──────────┬───────────┘
                                                         │ webhooks + API
                                              ┌──────────▼───────────┐
                                              │   WAHA (3002)        │
                                              │   WhatsApp HTTP API  │
                                              └──────────┬───────────┘
                                                         │
                                              ┌──────────▼───────────┐
                                              │   Your WhatsApp      │
                                              │   (linked phone)     │
                                              └──────────────────────┘

Supporting services: MongoDB (27017) · Qdrant (6333)
```

---

## Prerequisites

- Docker and Docker Compose v2
- These ports free on your machine: `3002`, `8000`, `8001`, `27017`, `6333`, `6334`
- A WhatsApp number you want to link

> **Local development only (optional):** Python 3.13 and `uv`. Use Docker unless you specifically need to run the relay directly on your machine.

---

## Docker Setup

### Step 1 — Create the `.env` file

```bash
cp .env.example .env
```

Then generate a fresh `TOKEN_SECRET`:

```bash
openssl rand -hex 32
```

### Step 2 — Set the required secrets

Open `.env` and replace these four placeholder values. Everything else can stay as-is for a standard Docker setup.

```dotenv
TOKEN_SECRET=<output from openssl rand -hex 32>

WAHA_API_KEY=<any random string>
WAHA_WEBHOOK_SECRET=<any random string>
WAHA_DASHBOARD_PASSWORD=<any random string>

# Must be identical to WAHA_WEBHOOK_SECRET
WHATSAPP_HOOK_HMAC_KEY=<same value as WAHA_WEBHOOK_SECRET>
```

The service URLs below are pre-configured for Docker Compose. **Do not change them** unless you have a port conflict:

```dotenv
WAHA_BASE_URL=http://waha:3000/api
WHATSAPP_HOOK_URL=http://relay:8001/webhook/waha
MONGO_URI=mongodb://mongodb:27017
WHATSAPP_SESSIONS_MONGO_URL=mongodb://mongodb:27017
```

### Step 3 — Build and start the stack

```bash
docker compose up --build
```

This starts four containers:

| Service | Port |
| --- | --- |
| Relay MCP server | `localhost:8000` |
| Relay webhook receiver | `localhost:8001` |
| WAHA (WhatsApp HTTP API) | `localhost:3002` |
| MongoDB | `localhost:27017` |
| Qdrant | `localhost:6333` |

### Step 4 — Verify everything is running

```bash
docker compose ps
```

Then hit the health endpoint:

```bash
curl http://localhost:8001/health
```

Expected response: `{"status":"ok"}`

Useful URLs once the stack is up:

- Relay MCP server: `http://localhost:8000/mcp`
- WAHA dashboard + Swagger: `http://localhost:3002/`
- Qdrant: `http://localhost:6333`

---

## Connect WhatsApp

### 1 — Connect the session

Ask your AI agent:

```
Connect WhatsApp and send me the request code.
```

The agent calls `connect_whatsapp`, creates a WAHA session, and returns a pairing code (e.g. `ABC1-2345`).

### 2 — Pair your phone

1. Open WhatsApp on your phone.
2. Go to **Settings → Linked Devices → Link a Device**.
3. Tap **Link with phone number instead**.
4. Enter the pairing code.

Your phone confirms the link within a few seconds.

### 3 — Wait for the session to become active

Ask your agent:

```
Is the WhatsApp session connected and working?
```

Wait until the agent reports `WORKING`. If it reports a transitional state (`SCAN_QR_CODE`, `CONNECTING`), wait a moment and ask again.

### 4 — Start using WhatsApp tools

Once the session is `WORKING`:

```
Sync my chats.
```

```
Show me my recent chats.
```

```
Send a WhatsApp message to +1234567890 saying "Hello".
```

Available tools include `connect_whatsapp`, `sync_chats`, `get_chats`, `get_messages`, `send_text_message`, and more.

---

## Connect to an AI Agent

### Any MCP client

Point your MCP client at:

```
http://localhost:8000/mcp
```

That's it. All relay tools will be available to your agent.

---

### OpenClaw (optional)

> **Skip this section** if you are not using OpenClaw. The relay works with any MCP client.

This walks you through making OpenClaw aware of all AiRA Relay tools via a local plugin called `mcp-bridge`.

**Before you start:**
- OpenClaw is installed and the gateway can be started.
- The relay stack is running (`docker compose up`).
- `curl http://localhost:8001/health` returns `{"status":"ok"}`.

---

#### Step 1 — Configure the relay for OpenClaw

Open `.env` and set these four values. Find the token values in `~/.openclaw/openclaw.json` (see the table below).

```dotenv
OPENCLAW_URL=http://localhost:18789
OPENCLAW_TOKEN=<hooks.token from openclaw.json>
OPENCLAW_AGENT_NAME=MCP
OPENCLAW_GATEWAY_TOKEN=<gateway.auth.token from openclaw.json>
```

Token locations in `~/.openclaw/openclaw.json`:

| Variable | Key path |
| --- | --- |
| `OPENCLAW_TOKEN` | `hooks.token` |
| `OPENCLAW_GATEWAY_TOKEN` | `gateway.auth.token` |

Example `~/.openclaw/openclaw.json`:

```json
{
  "hooks": {
    "enabled": true,
    "path": "/hooks",
    "token": "YOUR_WEBHOOK_TOKEN"
  },
  "gateway": {
    "auth": {
      "mode": "token",
      "token": "YOUR_GATEWAY_TOKEN"
    }
  }
}
```

Restart the relay after editing `.env`:

```bash
docker compose down && docker compose up
```

---

#### Step 2 — Create the plugin folder

```bash
mkdir -p ~/.openclaw/extensions/mcp-bridge
```

---

#### Step 3 — Create the plugin manifest

Create `~/.openclaw/extensions/mcp-bridge/openclaw.plugin.json`:

```json
{
  "id": "mcp-bridge",
  "name": "MCP Bridge",
  "description": "Connects to an external MCP server and registers its tools inside OpenClaw.",
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "url": {
        "type": "string",
        "description": "MCP server URL (e.g. http://127.0.0.1:8000/mcp)"
      },
      "optional": {
        "type": "boolean",
        "description": "If true, tools require explicit allow to be used. Default: true."
      }
    }
  }
}
```

---

#### Step 4 — Create the plugin code

Create `~/.openclaw/extensions/mcp-bridge/index.ts`:

```typescript
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";

const DEFAULT_URL = "http://127.0.0.1:8000/mcp";

type McpTool = {
  name: string;
  description?: string;
  inputSchema: {
    type?: string;
    properties?: Record<string, unknown>;
    required?: string[];
  };
};

type McpState = {
  url: string;
  sessionId: string | undefined;
};

function parseSseData(text: string): unknown {
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith("data:")) {
      const json = trimmed.slice(5).trim();
      if (json && json !== "[DONE]") {
        return JSON.parse(json);
      }
    }
  }
  throw new Error("No data line found in SSE response");
}

async function mcpRequest(
  state: McpState,
  method: string,
  params: unknown,
  hasResponse: boolean,
): Promise<unknown> {
  const id = hasResponse ? 1 : undefined;
  const body: Record<string, unknown> = { jsonrpc: "2.0", method };
  if (id !== undefined) body.id = id;
  if (params !== undefined && params !== null) body.params = params;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
  };
  if (state.sessionId) {
    headers["mcp-session-id"] = state.sessionId;
  }

  const res = await fetch(state.url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  const newSession = res.headers.get("mcp-session-id");
  if (newSession) {
    state.sessionId = newSession;
  }

  if (!hasResponse || res.status === 202) {
    return undefined;
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`MCP HTTP ${res.status}: ${text.slice(0, 200)}`);
  }

  const contentType = res.headers.get("content-type") ?? "";
  let data: { result?: unknown; error?: { message?: string } };

  if (contentType.includes("text/event-stream")) {
    const text = await res.text();
    data = parseSseData(text) as typeof data;
  } else {
    data = (await res.json()) as typeof data;
  }

  if (data.error) {
    throw new Error(data.error.message ?? "MCP error");
  }

  return data.result;
}

async function initSession(state: McpState): Promise<void> {
  await mcpRequest(
    state,
    "initialize",
    {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "openclaw-mcp-bridge", version: "1.0.0" },
    },
    true,
  );
  await mcpRequest(state, "notifications/initialized", {}, false);
}

async function listTools(state: McpState): Promise<McpTool[]> {
  const result = (await mcpRequest(state, "tools/list", {}, true)) as {
    tools?: McpTool[];
  };
  return result?.tools ?? [];
}

async function callTool(
  state: McpState,
  name: string,
  args: unknown,
): Promise<string> {
  const result = (await mcpRequest(state, "tools/call", { name, arguments: args }, true)) as {
    content?: Array<{ type: string; text?: string }>;
    isError?: boolean;
  };

  const text = (result?.content ?? [])
    .filter((c) => c.type === "text" && typeof c.text === "string")
    .map((c) => c.text ?? "")
    .join("\n");

  if (result?.isError) {
    throw new Error(text || "MCP tool returned an error");
  }

  return text;
}

export default async function (api: OpenClawPluginApi) {
  const cfg = (api.pluginConfig ?? {}) as { url?: string; optional?: boolean };
  const url = (cfg.url ?? DEFAULT_URL).trim();
  const isOptional = cfg.optional !== false;

  const state: McpState = { url, sessionId: undefined };

  let tools: McpTool[];
  try {
    await initSession(state);
    tools = await listTools(state);
  } catch (err) {
    api.logger.warn(`mcp-bridge: failed to connect to ${url}: ${String(err)}`);
    return;
  }

  if (tools.length === 0) {
    api.logger.warn(`mcp-bridge: no tools found at ${url}`);
    return;
  }

  for (const tool of tools) {
    const schema = tool.inputSchema ?? {};
    api.registerTool(
      {
        name: tool.name,
        description: tool.description ?? tool.name,
        parameters: {
          type: "object",
          properties: (schema.properties as Record<string, unknown>) ?? {},
          required: schema.required ?? [],
        },
        async execute(_id: string, params: Record<string, unknown>) {
          const text = await callTool(state, tool.name, params);
          return { content: [{ type: "text", text }] };
        },
      },
      { optional: isOptional },
    );
  }

  api.logger.info(`mcp-bridge: registered ${tools.length} tools from ${url}`);
}
```

---

#### Step 5 — Update your OpenClaw config

Open `~/.openclaw/openclaw.json` and add or update the `tools`, `plugins`, and `hooks` sections. Keep any existing plugins alongside these new entries.

```json
{
  "tools": {
    "profile": "full",
    "allow": ["mcp-bridge"]
  },
  "plugins": {
    "allow": ["mcp-bridge"],
    "entries": {
      "mcp-bridge": {
        "enabled": true,
        "config": {
          "url": "http://127.0.0.1:8000/mcp"
        }
      }
    }
  },
  "hooks": {
    "mappings": [
      {
        "match": { "path": "/waha" },
        "action": "agent",
        "wakeMode": "now",
        "name": "WhatsApp",
        "deliver": true,
        "to": "+917995154159",
        "channel": "whatsapp",
        "allowUnsafeExternalContent": true,
        "messageTemplate": "{{payload.message}}"
      }
    ]
  }
}
```

| Config key | What it does |
| --- | --- |
| `tools.profile: "full"` | Enables built-in OpenClaw tools. Must be `"full"` — `"all"` is not valid. |
| `tools.allow: ["mcp-bridge"]` | Lets the agent use the bridge's tools. Without this, tools are registered but blocked. |
| `plugins.allow: ["mcp-bridge"]` | Marks the plugin as trusted local code. Suppresses the "unverified" warning. |
| `plugins.entries.mcp-bridge.enabled` | Tells OpenClaw to load the plugin at startup. |
| `plugins.entries.mcp-bridge.config.url` | The MCP server URL. Change if your relay runs on a different port. |
| `hooks.mappings` | Routes incoming WhatsApp events to the OpenClaw agent. |

---

#### Step 6 — Restart the OpenClaw gateway

```bash
openclaw gateway restart
```

#### Step 7 — Verify the plugin loaded

```bash
openclaw channels status
```

Look for:

```
mcp-bridge: registered 18 tools from http://127.0.0.1:8000/mcp
```

---

## Local Development

Use this only if you want to run the Python relay directly on your machine instead of Docker.

### Step 1 — Start external services

Start these three services first (however you prefer — Docker, Homebrew, etc.):

1. MongoDB on `localhost:27017`
2. Qdrant on `localhost:6333`
3. WAHA on `localhost:3002`

### Step 2 — Update `.env` for host mode

Change the service URLs to point at localhost:

```dotenv
WAHA_BASE_URL=http://localhost:3002/api
WHATSAPP_HOOK_URL=http://localhost:8001/webhook/waha
MONGO_URI=mongodb://localhost:27017
WHATSAPP_SESSIONS_MONGO_URL=mongodb://localhost:27017
QDRANT_URL=http://localhost:6333
```

### Step 3 — Install dependencies

```bash
uv sync
```

### Step 4 — Run the relay

```bash
MCP_TRANSPORT=http uv run python main.py
```

Verify:

```bash
curl http://localhost:8001/health
```

**Optional — stdio mode:** If you want MCP over stdio while keeping the webhook receiver running:

```bash
MCP_TRANSPORT=stdio uv run python main.py
```

---

## Environment Variables Reference

### Secrets and service URLs

| Variable | Used by | Description |
| --- | --- | --- |
| `TOKEN_SECRET` | Relay | HMAC key for phone number tokenization. Generate with `openssl rand -hex 32`. Change for every deployment. |
| `WAHA_API_KEY` | WAHA, Relay | Authenticates relay requests to WAHA. Any random string. Must match between relay and WAHA. |
| `WAHA_WEBHOOK_SECRET` | WAHA, Relay | Relay uses this to verify incoming webhook signatures. Must equal `WHATSAPP_HOOK_HMAC_KEY`. |
| `WHATSAPP_HOOK_HMAC_KEY` | WAHA | WAHA uses this to sign webhook payloads. Same exact value as `WAHA_WEBHOOK_SECRET`. |
| `WAHA_BASE_URL` | Relay | Base URL for WAHA API. Docker: `http://waha:3000/api`. Host mode: `http://localhost:3002/api`. |
| `WHATSAPP_HOOK_URL` | WAHA | Where WAHA sends webhook events. Docker: `http://relay:8001/webhook/waha`. Host mode: `http://localhost:8001/webhook/waha`. |
| `MONGO_URI` | Relay | MongoDB connection string. Docker: `mongodb://mongodb:27017`. Host mode: `mongodb://localhost:27017`. |
| `WHATSAPP_SESSIONS_MONGO_URL` | WAHA | MongoDB for WAHA session storage. Usually same host as `MONGO_URI`. |
| `MONGO_DB_NAME` | Relay | Mongo database name. Default: `aira_relay`. |
| `QDRANT_URL` | Relay | Qdrant endpoint. Docker Compose overrides this to `http://qdrant:6333`. Host mode: `http://localhost:6333`. |
| `QDRANT_API_KEY` | Relay | Auth for protected Qdrant instances. Leave empty for local Qdrant. |

### Ports

| Variable | Default | Description |
| --- | --- | --- |
| `MCP_PORT` | `8000` | Host port for the MCP HTTP server. |
| `WEBHOOK_PORT` | `8001` | Host port for the webhook receiver. |
| `DEBUGPY_PORT` | `5678` | Debugpy attach port. |

### OpenClaw integration (optional)

| Variable | Description |
| --- | --- |
| `OPENCLAW_URL` | Where OpenClaw is running. Setting this enables event forwarding and LLM routing. Leave empty to disable. |
| `OPENCLAW_TOKEN` | Bearer token for posting webhook events to OpenClaw. Maps to `hooks.token` in `openclaw.json`. |
| `OPENCLAW_AGENT_NAME` | Label sent in event payloads. Default: `MCP`. |
| `OPENCLAW_GATEWAY_TOKEN` | Bearer token for calling OpenClaw's chat completion API. Maps to `gateway.auth.token` in `openclaw.json`. |

### OpenRouter LLM (optional)

| Variable | Description |
| --- | --- |
| `OPENROUTER_API_KEY` | API key for OpenRouter. Used as an alternative LLM backend. Leave empty to disable. |
| `OPENROUTER_MODEL` | Model to use via OpenRouter (e.g. `openai/gpt-4o-mini`). |

### Message filtering

| Variable | Description |
| --- | --- |
| `IGNORED_NUMBERS` | Comma-separated phone numbers (digits only, no `+` or spaces). Messages from these numbers are silently dropped. Include the number you logged into OpenClaw with to prevent circular notifications. |

### WAHA behavior

| Variable | Description |
| --- | --- |
| `WAHA_DASHBOARD_USERNAME` | WAHA dashboard login username. |
| `WAHA_DASHBOARD_PASSWORD` | WAHA dashboard login password. |
| `WHATSAPP_SWAGGER_USERNAME` | WAHA Swagger UI username. |
| `WHATSAPP_SWAGGER_PASSWORD` | WAHA Swagger UI password. |
| `WAHA_DASHBOARD_ENABLED` | Enables the WAHA dashboard. `True` or `False`. |
| `WHATSAPP_SWAGGER_ENABLED` | Enables the WAHA Swagger UI. `True` or `False`. |
| `WHATSAPP_HOOK_EVENTS` | WAHA events forwarded to the relay. Keep at least `session.status,message`. |
| `WHATSAPP_DEFAULT_ENGINE` | WAHA backend engine. `GOWS` (default), `NOWEB`, or `WEBJS`. |
| `WAHA_PUBLIC_URL` | External WAHA URL used in WAHA-generated links. |
| `WAHA_LOG_FORMAT` | WAHA log style. `PRETTY` or `JSON`. |
| `WAHA_LOG_LEVEL` | WAHA log verbosity. `debug`, `info`, `warn`, or `error`. |
| `WAHA_PRINT_QR` | Whether WAHA prints QR output in logs. Usually `False`. |
| `WAHA_MEDIA_STORAGE` | WAHA media storage backend. `LOCAL` is the value used here. |
| `WHATSAPP_FILES_LIFETIME` | Lifetime of stored media files in seconds. Increase if media URLs expire too quickly. |
| `WHATSAPP_FILES_FOLDER` | Media storage path inside the WAHA container. Default: `/app/.media`. |

### Debugging and transport

| Variable | Description |
| --- | --- |
| `MCP_TRANSPORT` | `http` (default in Docker) or `stdio`. |
| `DEBUGPY_ENABLE` | Enables debugpy listener. `true` or `false`. |
| `DEBUGPY_WAIT_FOR_CLIENT` | Blocks startup until a debugger attaches. `true` or `false`. |

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Relay can't reach WAHA | `WAHA_BASE_URL` missing `/api` | Set `WAHA_BASE_URL=http://waha:3000/api` |
| Webhook signature verification fails | `WAHA_WEBHOOK_SECRET` and `WHATSAPP_HOOK_HMAC_KEY` are different | Set both to the same random string |
| WAHA can't send events to relay | `WHATSAPP_HOOK_URL` points to `localhost` while WAHA runs in Docker | Use `http://relay:8001/webhook/waha` in Docker Compose |
| Stack starts but nothing works | Placeholder credentials from `.env.example` still in use | Replace all four secrets in Step 2 |
| `tools.profile` error in OpenClaw | `"all"` is not a valid value | Change to `"full"` |
| MCP tools registered but agent can't use them | `tools.allow` missing the plugin | Add `"mcp-bridge"` to `tools.allow` |
| Plugin loads with "without provenance" warning | Local plugin not marked as trusted | Add `"mcp-bridge"` to `plugins.allow` |
| `failed to connect to http://127.0.0.1:8000/mcp` | Relay not running or wrong port | Run `docker compose up` and confirm health returns `{"status":"ok"}` |
| `no tools found at URL` | Relay returned an empty tool list | Check logs: `docker compose logs relay` |
| OpenClaw fails to start after config change | JSON syntax error in `openclaw.json` | Validate: `cat ~/.openclaw/openclaw.json \| python3 -m json.tool` |

### Checking logs

```bash
# All services
docker compose logs -f

# Relay only
docker compose logs -f relay

# WAHA only
docker compose logs -f waha
```

### Stop the stack

```bash
docker compose down
```

---

## Contributors

| Name | LinkedIn |
| --- | --- |
| Dhanesh Pottekula | [linkedin.com/in/dhanesh-pottekula-a40900230](https://www.linkedin.com/in/dhanesh-pottekula-a40900230/) |
