<div align="center">

<h2><b>hoseki: Give Free Web Chat Models Hands on Your Local Machine</b></h2>

</div>

<div align="center">

[![License](https://img.shields.io/github/license/mufasa-noir/hoseki?color=green)](https://github.com/mufasa-noir/hoseki/blob/main/LICENSE)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![No API Keys](https://img.shields.io/badge/API_Keys-none_required-brightgreen)

</div>

<div align="center">

[English](README.md) | [日本語](README_ja.md)

</div>

<div align="center">
  <img src="figures/logo.png" alt="hoseki logo" width="300">
</div>

> hoseki is a **local bridge** that lets free web chat UIs (Kimi, GLM, and friends) read, search, and edit files in your project folder, and run commands with your approval. **No LLM API keys, no paid plans.**

## 📜 Introduction

Top-tier models are often free in a browser tab but locked behind paid API keys the moment you want them to touch your files. **hoseki** closes that gap. It sits between a chat page and your filesystem so the model you're already talking to can help with software development and security code review.

It is made of three small pieces:

1. A **local daemon** that exposes filesystem and command tools over HTTP on `127.0.0.1`, with a path jail, token auth, and a human approval gate.
2. A **browser extension (Manifest V3)** that watches the chat page, detects tool-call blocks in the model's reply, sends them to the daemon, and drops the results back into the chat input.
3. A **prompt preamble** you paste at the start of a chat that teaches the model the tool-call protocol.

> **Status:** hoseki is under active development and being built in phases (see the [Roadmap](#️-roadmap)). Treat anything not marked as done there as a design target, not a shipped feature.

## 🏗️ Architecture

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

| Module        | Role                                                                    |
| ------------- | ----------------------------------------------------------------------- |
| `auth.py`     | Bearer token check plus `Origin`/`Host` validation (DNS-rebinding defense) |
| `jail.py`     | Resolves every path and enforces containment inside the workspace root  |
| `secrets.py`  | Deny-list for sensitive files (`.env`, keys, and similar)               |
| `approval.py` | Terminal prompt that shows the diff or command and waits for your y/n   |
| `tools/`      | Tool registry (`read_file`, `grep`, `apply_patch`, `run_cmd`, ...)      |
| `audit.py`    | Append-only JSONL log of every call and approval decision               |

The extension is the only thing that talks to the daemon, over `POST /v1/call` with a bearer token. `hoseki mcp` is a stdio (JSON-RPC) adapter that reuses the same tool context, so MCP-capable clients get the same jail, approval gate, and audit log as the browser path.

## 🧰 Toolset

All paths are relative to the configured workspace root.

| Tool          | What it does                                                          | Approval  |
| ------------- | --------------------------------------------------------------------- | --------- |
| `list_dir`    | List a directory, optionally to a given depth                         | automatic |
| `read_file`   | Read numbered lines with a range, truncation flag, and total line count | automatic |
| `grep`        | Regex search (uses `ripgrep` if installed, Python fallback otherwise) | automatic |
| `find_files`  | Glob for files                                                        | automatic |
| `write_file`  | Write a file, shows a diff first                                      | **you approve** |
| `apply_patch` | Apply a unified diff, fails cleanly if it doesn't apply               | **you approve** |
| `run_cmd`     | Run a command (allowlist and/or Docker sandbox)                       | **you approve** |

Reads are auto-approved. Writes and commands **never** are.

## 🔒 Security Model

hoseki is meant to be pointed at **untrusted code**, so it assumes file contents are hostile and may contain prompt injection.

- **Path jail**: every path is resolved and verified to sit inside the workspace root. `..` escapes, absolute paths outside the root, and symlinks that resolve outside it are rejected.
- **Localhost only**: the daemon binds to `127.0.0.1`, requires a random bearer token (stored with `0600` permissions), and validates `Origin`/`Host` headers to defend against DNS rebinding.
- **Human approval gate**: writes and commands pause for a local y/n prompt showing the full diff or command. Nothing in the model's output or a file's contents can pre-approve or bypass it.
- **Command sandbox**: `run_cmd` is deny-by-default. It can run inside a Docker container with no network and the workspace mounted read-only. If Docker is unavailable, hoseki refuses to run commands unless you explicitly set `unsafe_host_exec = true`.
- **Secrets denylist**: `.env`, `*.pem`, `id_rsa*`, and similar files are unreadable by default.
- **Limits**: max read size, max output size, max calls per minute, and max command runtime are all configurable.
- **Audit log**: every tool call, its arguments, the approval decision, and a result summary are appended to a local JSONL log.
- **Untrusted-data framing**: file contents in tool results are wrapped in delimiters, and the preamble tells the model that anything inside them is data, never instructions.

> **Honest caveat:** delimiters and instructions reduce prompt-injection risk, they do not eliminate it. The approval gate and the no-network sandbox are what actually limit the damage.

## 🚀 Getting Started

### Installation

1. Install Python 3.11+, then clone the repo and install the dependencies:

````
git clone https://github.com/mufasa-noir/hoseki.git
cd hoseki
pip install -r requirements.txt
````

2. (Optional) Install [`ripgrep`](https://github.com/BurntSushi/ripgrep) for faster `grep`, and [Docker](https://www.docker.com/) if you want sandboxed command execution.

### Step 1: Configure

All settings live in `config.toml`. At minimum, set the workspace root to the project you want the model to see:

````toml
[workspace]
root = "/home/you/projects/target"

[server]
host = "127.0.0.1"
port = 8765

[limits]
max_read_lines = 400
max_output_bytes = 60000
max_calls_per_minute = 30
cmd_timeout_seconds = 60

[exec]
mode = "docker"            # "docker" | "allowlist" | "off"
allowlist = ["git status", "git diff", "pytest"]
docker_network = "none"
workspace_mount = "ro"

[secrets]
deny_globs = [".env", "*.pem", "id_rsa*"]
````

### Step 2: Start the Daemon

````
python -m hoseki --config config.toml
````

On first start, hoseki generates a random auth token and prints where it was saved. You'll paste this token into the extension once.

### Step 3: Install the Extension

1. Open `chrome://extensions` in a Chromium-based browser and enable **Developer mode**.
2. Click **Load unpacked** and select the `extension/` folder.
3. Open the extension popup, paste your token, and confirm the status shows **connected**.

### Step 4: Paste the Preamble

Start a new chat on a supported site and paste the contents of [`preamble.md`](preamble.md) (or use the **Copy preamble** button in the popup). It's under ~600 words so it fits comfortably in free-tier context limits.

### Step 5: Ask Away

Try something small first:

> List the top-level files in the project, then read the main entry point.

The model will emit a tool block, the extension will run it through the daemon, and the result lands in the chat input for you to review and send.

## 🔌 Tool-Call Protocol

The model emits tool calls as fenced blocks tagged `tool`, one JSON object each:

````
```tool
{"id": "c1", "name": "read_file", "args": {"path": "src/auth.php", "start_line": 1, "end_line": 200}}
```
````

Results come back as a single `tool_result` block:

````
```tool_result
{"id": "c1", "ok": true, "output": "...", "truncated": false}
```
````

A few rules keep this reliable:

- The model may emit several blocks in one message, then **must stop** and wait for results.
- Errors return `{"id": "...", "ok": false, "error": "..."}` so the model can retry.
- The parser tolerates common sloppiness (extra whitespace, trailing commas, a missing `id`), but anything that fails strict schema validation is **never executed**.
- The extension only parses the **latest** assistant message, ignores echoed or quoted text, and dedupes by `(message id, call id)` so nothing runs twice.
- Long results are split across messages with `part 1/3` markers to stay under chat length caps.

## 🌐 Site Adapters

Each chat site gets an adapter in config (not hardcoded) providing CSS selectors for the assistant message container, the "finished streaming" signal, the input element, and the send button.

| Site                  | Status                                      |
| --------------------- | ------------------------------------------- |
| `chat.z.ai` (GLM)     | Best-effort starting point, **verify selectors** |
| `kimi.com`            | Best-effort starting point, **verify selectors** |
| Anything else         | Use the template in `extension/adapters/`   |

Chat UIs change their DOM without notice, so expect to maintain these. If one breaks, grab the relevant HTML from your browser's dev tools and update the selectors.

By default the flow is **semi-automatic**: results are inserted into the input box and **you** press send. An optional auto-send toggle exists, off by default.

## 🧪 Testing

````
pytest tests/
````

The test suite covers path-jail escapes (`..`, absolute paths, symlinks), auth and origin checks, tool schema validation, and diff-application failures. Please read the path-jail tests before trusting hoseki with code you care about.

## 💡 Important Considerations

- **Terms of service**: automating a consumer chat UI may violate a provider's terms, and some sites detect it. The default semi-automatic flow (you read and click send) is lower risk than auto-submit loops. Check each site's terms yourself.
- **Free tiers have limits**: message length caps and rate limits will bite on big files. Prefer `grep` and line ranges over reading whole files, and ask for small patches instead of rewrites.
- **Model quality varies**: not every free model emits clean tool blocks. If one keeps producing malformed JSON, try another or tighten the preamble.
- **Don't expose the daemon to the internet**: if you tunnel it for a remote connector, you're publishing a tool server that can touch your files. Use a strong token and a locked-down root.
- **Hostile repos**: only run hoseki against untrusted code with `exec.mode = "docker"` or `"off"`.

> **Disclaimer:** hoseki is a tool for your own machine and your own projects. You are responsible for what you point it at and what you approve. Only test code you are authorized to test.

## 🗺️ Roadmap

- [ ] **Phase 1**: Daemon with read-only tools, auth, path jail, and jail-escape tests
- [ ] **Phase 2**: Write tools with terminal diff approval and the audit log
- [ ] **Phase 3**: `run_cmd` with allowlist and Docker sandbox
- [ ] **Phase 4**: Browser extension (background worker, content script, popup, two site adapters)
- [ ] **Phase 5**: Preamble, full docs, and end-to-end test checklist
- [ ] **Phase 6 (optional)**: `hoseki mcp` stdio (JSON-RPC) adapter reusing the same context, for clients that support MCP natively

## 📜 License

This project is licensed under the [MIT License](LICENSE).