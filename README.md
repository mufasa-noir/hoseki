# Hoseki

> A local tool bridge that lets free web chat UIs (Kimi, GLM/z.ai, …) read
> and — with your approval — edit files and run commands on your machine.
> No paid APIs. No LLM API keys. One local bearer token.

Hoseki is three pieces:

1. **`hoseki` daemon** — a small FastAPI/uvicorn server on `127.0.0.1` that
   exposes filesystem and command tools behind a bearer token and a path jail.
2. **Browser extension (MV3)** — watches a chat tab, detects `tool` blocks,
   forwards them to the daemon, and inserts `tool_result` blocks back into
   the chat input.
3. **Prompt preamble** — teaches the model the `tool` / `tool_result`
   protocol.

An optional fourth piece, `hoseki mcp`, exposes the same tool core over
stdio for MCP-native clients.

---

## Install

Requires Python 3.11+ (uses stdlib `tomllib`).

```bash
git clone <this repo> hoseki
cd hoseki
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'      # omit [dev] for a minimal install