## AiRA Relay

AiRA Relay is a Python MCP server and webhook receiver that sits in front of WAHA
(WhatsApp HTTP API). It exposes WhatsApp operations as MCP tools, persists state
in MongoDB, and optionally uses Qdrant plus embeddings for contact indexing and
phonetic search.

This repository runs four services through `docker-compose`:

- `relay`: the Python MCP server and WAHA webhook receiver
- `waha`: the WhatsApp HTTP API container
- `mongodb`: persistent storage for users, chats, and session state
- `qdrant`: vector storage used for contact indexing and phonetic search

## Before You Start

- Docker and Docker Compose v2
- All of these ports free on your machine: `3002`, `8000`, `8001`, `27017`, `6333`, `6334`
- A WhatsApp number you want to link through WAHA

Optional for local host development:

- Python `3.13`
- `uv`

Use the Docker flow unless you specifically want to run the Python app directly
on your machine. The Docker flow is the default setup for this repository.

## Run With Docker

### Step 1: Create the `.env` file

Copy the example file:

```bash
cp .env.example .env
```

Do not use `.env.example` as-is. You need to edit a few values before the app
will start correctly.

Generate a fresh `TOKEN_SECRET`:

```bash
openssl rand -hex 32
```

### Step 2: Edit the required `.env` values

Open `.env` and set these values.

You must replace the placeholder secrets with your own values:

```dotenv
TOKEN_SECRET=replace-with-a-new-base64-secret

WAHA_API_KEY=replace-with-a-random-shared-api-key
WAHA_WEBHOOK_SECRET=replace-with-a-random-shared-webhook-secret
WAHA_DASHBOARD_PASSWORD=replace-with-a-random-shared-webhook-secret
WHATSAPP_HOOK_HMAC_KEY=replace-with-the-same-value-as-WAHA_WEBHOOK_SECRET
```

For Docker Compose, these service URLs must be set exactly like this:

```dotenv
WAHA_BASE_URL=http://waha:3000/api
WHATSAPP_HOOK_URL=http://relay:<WEBHOOK_PORT>/webhook/waha

MONGO_URI=mongodb://mongodb:27017
WHATSAPP_SESSIONS_MONGO_URL=mongodb://mongodb:27017
MONGO_DB_NAME=aira_relay
```

You usually do not need to change these unless you have a port conflict:

```dotenv
MCP_PORT=8000
WEBHOOK_PORT=8001
DEBUGPY_PORT=5678
```

Important rules:

- `WAHA_BASE_URL` should include `/api`.
- `WAHA_WEBHOOK_SECRET` and `WHATSAPP_HOOK_HMAC_KEY` must be identical.
- In Docker Compose, the `relay` service is forced to use the internal Qdrant service URL `http://qdrant:6333`, so the `.env` value is only relevant for host-mode runs.

### Step 3: Build and start the services

```bash
docker compose up --build
```

This starts all four containers:

- MongoDB on `127.0.0.1:27017`
- Qdrant on `127.0.0.1:6333` and `127.0.0.1:6334`
- WAHA on `127.0.0.1:3002`
- Relay MCP HTTP on `127.0.0.1:${MCP_PORT}`
- Relay webhook receiver on `127.0.0.1:${WEBHOOK_PORT}`

### Step 4: Verify the containers are healthy

Check container status:

```bash
docker compose ps
```

Then verify the relay health endpoint:

```bash
curl http://localhost:8001/health
```

Expected response:

```bash
{"status":"ok"}
```

Useful local URLs after startup:

- WAHA dashboard / Swagger: `http://localhost:3002/`
- Relay webhook health: `http://localhost:8001/health`
- Relay MCP HTTP server: `http://localhost:8000`
- Qdrant: `http://localhost:6333`

### Step 5: Use the app

After the stack is up, follow these steps in order.

#### 5a — Connect your MCP client

Connect your MCP client to the relay MCP HTTP endpoint:

```
http://localhost:8000/mcp
```

#### 5b — Connect WhatsApp

Ask the agent to connect WhatsApp and send you the pairing code. Use this exact prompt:

```
Connect WhatsApp and send me the request code.
```

The agent will call the `connect_whatsapp` tool, which creates a new WAHA session and returns a pairing code.

#### 5c — Pair your phone

1. Open WhatsApp on your phone.
2. Go to **Settings → Linked Devices → Link a Device**.
3. When prompted, tap **Link with phone number instead**.
4. Enter the pairing code that the agent returned.

Your phone will confirm the link. This usually takes a few seconds.

#### 5d — Wait for the session to become active

After pairing, WAHA exchanges credentials with WhatsApp in the background. Ask the agent to confirm when the session is ready:

```
Is the WhatsApp session connected and working?
```

The agent will check the session status. Wait until it reports `WORKING` before sending any messages. If it reports `SCAN_QR_CODE` or another transitional state, wait a moment and ask again.

#### 5e — Start using WhatsApp tools

Once the session is `WORKING`, you can use all available tools:

```
Sync my chats.
```

```
Show me my recent chats.
```

```
Send a WhatsApp message to +1234567890 saying "Hello".
```

Available tools include `sync_chats`, `get_chats`, `get_messages`, and `send_text_message`.

If you only want to confirm the infrastructure is running, Step 4 is enough.

### Step 6: Stop the stack

```bash
docker compose down
```

## Local Host Development

Use this only if you want to run the Python relay directly on your machine.

### Step 1: Start external services

Start these services first:

1. MongoDB on `localhost:27017`
2. Qdrant on `localhost:6333`
3. WAHA on `localhost:3002`

### Step 2: Update `.env` for host mode

Set these values:

```dotenv
WAHA_BASE_URL=http://localhost:3002/api
WHATSAPP_HOOK_URL=http://localhost:8001/webhook/waha
MONGO_URI=mongodb://localhost:27017
WHATSAPP_SESSIONS_MONGO_URL=mongodb://localhost:27017
QDRANT_URL=http://localhost:6333
```

### Step 3: Install dependencies

```bash
uv sync
```

### Step 4: Run the relay in HTTP mode

```bash
MCP_TRANSPORT=http uv run python main.py
```

### Step 5: Verify the relay

```bash
curl http://localhost:8001/health
```

### Step 6: Optional stdio mode

If you want MCP over stdio while still keeping the webhook receiver running:

```bash
MCP_TRANSPORT=stdio uv run python main.py
```

## Environment Variables

This project uses one `.env` file for both WAHA and the Python relay. Some
variables are consumed by both, some only by WAHA, and some only by the relay.

### Required and commonly edited

| Variable | Used by | What it does | What you can set |
| --- | --- | --- | --- |
| `TOKEN_SECRET` | Relay | HMAC secret for phone-number tokenization | Any new base64-url-safe 32-byte secret. Change this for every deployment. |
| `WAHA_API_KEY` | WAHA, Relay | Authenticates relay requests to WAHA | Any random string. Must match between relay and WAHA. |
| `WAHA_WEBHOOK_SECRET` | WAHA, Relay | Secret used to verify WAHA webhook signatures | Any random string. Must equal `WHATSAPP_HOOK_HMAC_KEY`. |
| `WHATSAPP_HOOK_HMAC_KEY` | WAHA | Secret WAHA uses to sign webhook payloads | Same exact value as `WAHA_WEBHOOK_SECRET`. |
| `WAHA_BASE_URL` | Relay | Base URL for WAHA API | Docker: `http://waha:3000/api`. Host mode: `http://localhost:3002/api`. |
| `WHATSAPP_HOOK_URL` | WAHA | Where WAHA sends webhook events | Docker: `http://relay:8001/webhook/waha`. Host mode: `http://localhost:8001/webhook/waha`. |
| `MONGO_URI` | Relay | MongoDB connection string for relay data | Docker: `mongodb://mongodb:27017`. Host mode: `mongodb://localhost:27017`. |
| `WHATSAPP_SESSIONS_MONGO_URL` | WAHA | MongoDB connection string for WAHA session storage | Usually same host as `MONGO_URI`. |
| `MONGO_DB_NAME` | Relay | Mongo database name | Any DB name. Default `aira_relay`. |
| `QDRANT_URL` | Relay | Qdrant endpoint used during startup and for contact indexing | In Docker Compose this is overridden to `http://qdrant:6333`. For host mode use `http://localhost:6333`. |
| `QDRANT_API_KEY` | Relay | Auth for protected Qdrant servers | Leave empty unless your Qdrant instance requires it. |
| `MCP_PORT` | Relay, Compose | Host port for MCP HTTP | Any free port. Default `8000`. |
| `WEBHOOK_PORT` | Relay, Compose | Host port for webhook receiver | Any free port. Default `8001`. |
| `DEBUGPY_PORT` | Relay, Compose | Debugpy attach port | Any free port. Default `5678`. |

### WAHA behavior and operational settings

| Variable | What it does | What you can set |
| --- | --- | --- |
| `WAHA_DASHBOARD_USERNAME` | WAHA dashboard auth username | Any username you want. |
| `WAHA_DASHBOARD_PASSWORD` | WAHA dashboard auth password | Set a strong password. |
| `WHATSAPP_SWAGGER_USERNAME` | WAHA Swagger auth username | Any username you want. |
| `WHATSAPP_SWAGGER_PASSWORD` | WAHA Swagger auth password | Set a strong password. |
| `WAHA_DASHBOARD_ENABLED` | Enables WAHA dashboard UI | `True` or `False`. |
| `WHATSAPP_SWAGGER_ENABLED` | Enables WAHA Swagger UI | `True` or `False`. |
| `WHATSAPP_HOOK_EVENTS` | WAHA events sent to relay | Keep at least `session.status,message`. `message.reaction` is optional and currently ignored by relay. |
| `WHATSAPP_DEFAULT_ENGINE` | WAHA backend engine | `GOWS`, `NOWEB`, or `WEBJS`. This repo is set up around `GOWS`. |
| `WAHA_PUBLIC_URL` | External WAHA URL shown in WAHA-generated links | Set to the public URL users or tools should reach. |
| `WAHA_LOG_FORMAT` | WAHA log style | Common values: `PRETTY`, `JSON`. |
| `WAHA_LOG_LEVEL` | WAHA log verbosity | Common values: `debug`, `info`, `warn`, `error`. |
| `WAHA_PRINT_QR` | Whether WAHA prints QR output in logs | `True` or `False`. Usually `False` here. |
| `WAHA_MEDIA_STORAGE` | WAHA media storage backend | `LOCAL` is the value used here. |
| `WHATSAPP_FILES_LIFETIME` | Lifetime of stored media files in seconds | Increase if media URLs expire too quickly. |
| `WHATSAPP_FILES_FOLDER` | Media storage path inside WAHA container | Usually leave as `/app/.media`. |



### Message filtering

| Variable | What it does | What you can set |
| --- | --- | --- |
| `IGNORED_NUMBERS` | Comma-separated phone numbers (digits only, no `+` or spaces). Messages from these numbers are silently dropped before any processing. | e.g. `14155552671,918123941616`. Leave empty to disable. Include the number you logged into OpenClaw with to avoid circular notifications. |

### Optional OpenClaw integration

| Variable | What it does | What you can set |
| --- | --- | --- |
| `OPENCLAW_URL` | Enables forwarding relay events to OpenClaw and uses OpenClaw for LLM completion | Leave empty to disable. |
| `OPENCLAW_TOKEN` | Bearer token used when sending webhook events to OpenClaw hook endpoints | You can find this in `~/.openclaw/openclaw.json` under `hooks.token`. |
| `OPENCLAW_AGENT_NAME` | Name sent in OpenClaw hook payloads | Any label. Default is `MCP`. |
| `OPENCLAW_GATEWAY_TOKEN` | Bearer token used when calling OpenClaw chat completion APIs | You can find this in `~/.openclaw/openclaw.json` under `gateway.auth.token`. |

OpenClaw stores these values in `~/.openclaw/openclaw.json`.

Example:

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

Token locations:

| Token | Location in `~/.openclaw/openclaw.json` |
| --- | --- |
| Webhook Token | `hooks.token` |
| Gateway Token | `gateway.auth.token` |

Example `.env` values:

```dotenv
OPENCLAW_URL=http://localhost:18789
OPENCLAW_TOKEN=YOUR_WEBHOOK_TOKEN
OPENCLAW_AGENT_NAME=MCP
OPENCLAW_GATEWAY_TOKEN=YOUR_GATEWAY_TOKEN
```

Important:

- Never commit `~/.openclaw/openclaw.json` or `.env` files that contain real tokens.
- Leave `OPENCLAW_URL` empty if you do not want Relay to forward events to OpenClaw or use OpenClaw as the LLM backend.

### Debugging and transport

| Variable | What it does | What you can set |
| --- | --- | --- |
| `MCP_TRANSPORT` | Chooses how MCP is exposed | `http` or `stdio`. Dockerfile defaults to `http`. |
| `DEBUGPY_ENABLE` | Enables debugpy listener | `true` or `false`. |
| `DEBUGPY_WAIT_FOR_CLIENT` | Blocks startup until debugger attaches | `true` or `false`. |

## Common Misconfigurations

- `WAHA_BASE_URL` missing `/api`
- `WAHA_WEBHOOK_SECRET` and `WHATSAPP_HOOK_HMAC_KEY` set to different values
- `WHATSAPP_HOOK_URL` pointing to `localhost` while WAHA itself runs inside Docker
- Reusing placeholder credentials from `.env.example` instead of replacing them

## Notes

- The Docker setup in this repository uses `MCP_TRANSPORT=http` by default.
- The webhook receiver is always started, even in `stdio` mode.

---

## Connecting OpenClaw to AiRA Relay

This guide walks you through making OpenClaw aware of the tools exposed by the AiRA Relay MCP server.

**What you will end up with:** OpenClaw will be able to use all AiRA Relay tools (like `send_text_message`, `get_chats`, `sync_chats`, etc.) directly from the agent, the same way it uses any of its built-in tools.

**Why this is needed:** OpenClaw does not automatically discover external MCP servers. You need to create a small local plugin called `mcp-bridge` that acts as a connector — it fetches the tool list from the relay and registers each tool inside OpenClaw so the agent can use them.

### Before you start

Make sure all of these are true before continuing:

- OpenClaw is installed and the gateway can be started.
- The AiRA Relay stack is running (`docker compose up`).
- You can reach the relay at `http://127.0.0.1:8000/mcp` (check with `curl http://127.0.0.1:8001/health`).

---

### Step 1 — Configure the relay `.env` for OpenClaw

> Skip this step if you only want the MCP tools available in OpenClaw and do not need the relay to forward incoming WhatsApp events to OpenClaw or use OpenClaw as the LLM backend.

Open your `.env` file and set these four values:

```dotenv
OPENCLAW_URL=http://localhost:18789
OPENCLAW_TOKEN=YOUR_WEBHOOK_TOKEN
OPENCLAW_AGENT_NAME=MCP
OPENCLAW_GATEWAY_TOKEN=YOUR_GATEWAY_TOKEN
```

Where to find the token values — open `~/.openclaw/openclaw.json` and look here:

| Variable | Location in `~/.openclaw/openclaw.json` |
| --- | --- |
| `OPENCLAW_TOKEN` | `hooks.token` |
| `OPENCLAW_GATEWAY_TOKEN` | `gateway.auth.token` |

Example `~/.openclaw/openclaw.json`:

```json
{
  "hooks": {
    "enabled": true,
    "path": "/hooks",
    "token": "YOUR_WEBHOOK_TOKEN" // genereate the token if not present
  },
  "gateway": {
    "auth": {
      "mode": "token",
      "token": "YOUR_GATEWAY_TOKEN"
    }
  }
}
```

What each variable does:

| Variable | What it does |
| --- | --- |
| `OPENCLAW_URL` | Tells the relay where OpenClaw is running. Setting this enables event forwarding and LLM routing through OpenClaw. Leave empty to disable. |
| `OPENCLAW_TOKEN` | Used by the relay to authenticate when posting webhook events to OpenClaw. |
| `OPENCLAW_AGENT_NAME` | Label sent in event payloads so OpenClaw knows which agent sent them. |
| `OPENCLAW_GATEWAY_TOKEN` | Used by the relay when calling OpenClaw's chat completion API. |

After editing `.env`, restart the relay stack so the values take effect:

```bash
docker compose down && docker compose up
```

---

### Step 2 — Create the plugin folder

Create this directory on your machine:

```bash
mkdir -p ~/.openclaw/extensions/mcp-bridge
```

You will put two files inside it in the next two steps.

---

### Step 3 — Create the plugin manifest

Create the file `~/.openclaw/extensions/mcp-bridge/openclaw.plugin.json` with this content:

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

This file tells OpenClaw that the folder is a plugin and describes what configuration it accepts.

---

### Step 4 — Create the plugin code

Create the file `~/.openclaw/extensions/mcp-bridge/index.ts` with this content:

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

This is the plugin logic. When OpenClaw loads it, the plugin connects to the relay, fetches all available tools, and registers them so the agent can use them.

---

### Step 5 — Update your OpenClaw config

Open `~/.openclaw/openclaw.json` and add or update the `tools` and `plugins` sections as shown below.

> If you already have other plugins like `telegram` or `whatsapp`, keep them — just add the `mcp-bridge` entries alongside them.

```json
{
  "tools": {
    "profile": "full",
    "allow": [
      "mcp-bridge"
    ]
  },
  "plugins": {
    "allow": [
      "mcp-bridge"
    ],
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
        "match": {
          "path": "/waha"
        },
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

Here is what each part does:

| Key | What it does |
| --- | --- |
| `tools.profile: "full"` | Enables the full set of built-in OpenClaw tools. Must be `"full"` — `"all"` is not a valid value. |
| `tools.allow: ["mcp-bridge"]` | Grants the bridge plugin's tools access to the agent. Without this, the tools are registered but the agent cannot use them. |
| `plugins.allow: ["mcp-bridge"]` | Marks the plugin as trusted local code. Without this, OpenClaw will warn that the plugin is unverified. |
| `plugins.entries.mcp-bridge.enabled: true` | Tells OpenClaw to load and run the plugin when it starts. |
| `plugins.entries.mcp-bridge.config.url` | The MCP server URL the plugin should connect to. Change this if your relay runs on a different port. |
| `hooks.mappings` | Routes incoming webhook events to the OpenClaw agent. The entry shown matches all requests to `/wake` and wakes the agent immediately. |

---

### Step 6 — Restart the OpenClaw gateway

```bash
openclaw gateway restart
```

OpenClaw reads plugin and config changes only at startup, so a restart is required.

---

### Step 7 — Verify it worked

```bash
openclaw channels status
```

Look for a line like this in the output:

```
mcp-bridge: registered 18 tools from http://127.0.0.1:8000/mcp
```

That means:

- The plugin loaded successfully.
- It connected to the AiRA Relay MCP server.
- It discovered tools from the relay.
- Those tools are now registered and available to the OpenClaw agent.

---

### Step 8 — Connect WhatsApp through the agent

Once the tools are registered and the relay is running, you need to pair a WhatsApp account before any messaging tools will work.

#### 8a — Ask the agent to connect WhatsApp

In the OpenClaw agent chat, type exactly:

```
Connect WhatsApp and send me the request code.
```

The agent will call the `connect_whatsapp` tool. It will return a **pairing code** (e.g. `ABC1-2345`).

#### 8b — Pair your phone

1. Open WhatsApp on your phone.
2. Go to **Settings → Linked Devices → Link a Device**.
3. Tap **Link with phone number instead** when prompted.
4. Enter the pairing code the agent gave you.

Your phone will confirm the link within a few seconds.

#### 8c — Confirm the session is active

Ask the agent:

```
Is the WhatsApp session connected and working?
```

The agent will check the session status. Wait until it reports `WORKING`. If it reports a transitional state like `SCAN_QR_CODE` or `CONNECTING`, wait a moment and ask again.

#### 8d — Start using WhatsApp

Once the session is `WORKING`, all WhatsApp tools are available. For example:

```
Sync my chats and show me the most recent ones.
```

```
Send a WhatsApp message to +1234567890 saying "Hello from AiRA".
```

---

### Troubleshooting

| Problem | Cause | Fix |
| --- | --- | --- |
| `failed to connect to http://127.0.0.1:8000/mcp` | Relay is not running or wrong port | Run `docker compose up` and confirm `curl http://localhost:8001/health` returns `{"status":"ok"}` |
| `no tools found at URL` | Relay returned an empty tool list | Check relay container logs with `docker compose logs relay` |
| Plugin loads but shows "without provenance" warning | Plugin is local code not installed via the store | Add `"mcp-bridge"` to `plugins.allow` in your config |
| MCP tools are registered but agent cannot use them | `tools.allow` is missing the plugin | Add `"mcp-bridge"` to the `tools.allow` list |
| OpenClaw fails to start after config change | JSON syntax error in `openclaw.json` | Validate your JSON with `cat ~/.openclaw/openclaw.json \| python3 -m json.tool` |
| `tools.profile` shows an error | `"all"` is not a valid value | Change it to `"full"` |
