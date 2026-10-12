# Architecture

Hoseki has three cooperating parts, plus an optional MCP adapter.

````
┌──────────────────────────────┐
│         Chat web UI          │
│         (Kimi, z.ai)         │
└──────────────────────────────┘
                ▲
                │ DOM adapters
                ▼
┌──────────────────────────────┐
│      Browser extension       │
│    MV3, background worker    │
└──────────────────────────────┘
                │ POST /v1/call
                │ HTTP 127.0.0.1
                │ Authorization: Bearer …
                ▼
┌──────────────────────────────┐
│        Hoseki daemon         │
│      FastAPI + uvicorn       │
│                              │
│  auth.py      Origin/Host    │
│  jail.py      path jail      │
│  secrets.py   deny-list      │
│  approval.py  terminal       │
│  tools/       registry       │
│  audit.py     JSONL          │
└──────────────────────────────┘
                │ reused by
                ▼
┌──────────────────────────────┐
│      hoseki mcp (stdio)      │
│      JSON-RPC, same ctx      │
└──────────────────────────────┘
````
## The daemon

- FastAPI + uvicorn, single app factory in `src/hoseki/app.py`.
- Middleware order (outer → inner):
  1. `Host` header check — rejects anything that isn't `127.0.0.1` / `localhost` / `[::1]` with the configured port.
  2. `Origin` header check — rejects anything that doesn't match `[extension].allowed_origins` unless the request has no `Origin` **and** `allow_missing_origin = true`.
  3. CORS headers added for accepted origins.
  4. Bearer token check (per-endpoint dependency).
  5. Rate limit (sliding-window, in-memory).
- Tool execution goes through a registry (`hoseki.tools.TOOLS`). Each tool has
  a Pydantic `args_model` used for strict validation (`extra="forbid"`), and a
  handler `(Args, ToolContext) -> ToolResult`.
- `ToolContext` bundles `PathJail`, limits, secrets policy, audit logger,
  approval gate, command config, and sandbox config.
- Handlers run via `asyncio.to_thread` so blocking terminal approvals do not
  stall the event loop.

## The approval gate

`ApprovalGate` serialises prompts on a lock and reads from the daemon's
`stdin`, writing the body to `stderr`. It records decisions to the audit log.
Test-only bypass (`set_auto_for_tests`) is unreachable from HTTP, config, or
file content.

## The extension (MV3)

- `background.js` — makes all localhost fetches (page CSP / mixed-content
  safe), stores the token, exposes a small message API to the content script.
- `content.js` — per-site adapters (selectors configured, not hardcoded),
  DOM-mutation debounce, completion detector, tool-block scanner,
  `tool_result` insertion into `<textarea>` and `contenteditable`.
- `popup.html/.js` — daemon status, workspace root, "copy preamble",
  auto-send toggle with an explicit acknowledgement.

## The MCP adapter

`hoseki mcp` runs a newline-delimited JSON-RPC server over stdio. It rebuilds
a `ToolContext` with the same jail, secrets policy, limits, audit log, and
approval gate as the daemon, and reuses the same `TOOLS` registry. Writes and
commands still block on the terminal.

## The preamble

A <600-word system-style prompt that teaches the protocol, the tool list,
and the untrusted-content rule. Shipped at the repo root and bundled with the
extension for the popup's "copy preamble" button.