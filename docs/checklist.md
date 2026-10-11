# End-to-end test checklist

Run through this before trusting Hoseki with a real project.

## Prereqs

- [ ] `pip install -e '.[dev]'`
- [ ] `cp config.example.toml config.toml` and set `[workspace].root`
- [ ] `pytest` passes

## Daemon

- [ ] `hoseki serve` prints "listening on http://127.0.0.1:8765"
- [ ] `~/.hoseki/token` exists with mode `0600` (`stat -c %a ~/.hoseki/token`)
- [ ] `curl /v1/health` returns `{"ok": true, ...}`
- [ ] `curl /v1/status` **without** a token returns 401
- [ ] `curl /v1/status` **with** the token returns the workspace root
- [ ] A request with `Origin: https://evil.example` is rejected (403)
- [ ] A request with `Host: evil.example` is rejected (400)

## Path jail

- [ ] `read_file` with `path: "../../etc/passwd"` returns an error, not data
- [ ] A symlink inside the workspace pointing to `/etc/passwd` is rejected
- [ ] `.env`, `*.pem`, `id_rsa` return a `SecretDenied` error

## Read tools

- [ ] `list_dir` returns the expected tree
- [ ] `read_file` with `start_line`/`end_line` returns numbered lines
- [ ] `read_file` on a binary file returns "binary file refused"
- [ ] `grep` returns matches with `file:line:` prefix
- [ ] `find_files` with `**/*.py` returns Python files

## Write tools (Phase 2)

- [ ] `write_file` on a new path prints a diff to the daemon terminal
- [ ] Answering `n` leaves no file on disk
- [ ] Answering `y` writes the file
- [ ] `apply_patch` with a valid diff applies cleanly
- [ ] `apply_patch` with a bad diff fails and leaves the file unchanged
- [ ] `write_file` on `.env` is refused (secrets policy)

## Command tools (Phase 3)

- [ ] `run_cmd` with a non-allowlisted command is refused
- [ ] `run_cmd` with a chained command (`echo a; echo b`) is refused
- [ ] `run_cmd` with an allow-listed command shows an approval prompt
- [ ] With Docker available: the command runs inside the container
- [ ] With Docker unavailable and `unsafe_host_exec = false`: refused
- [ ] With `sandbox.mode = "refuse"`: refused

## Extension (Phase 4)

- [ ] Load unpacked, popup opens, **Check health** returns `ok: true`
- [ ] Open a chat on chat.z.ai, send a message that asks for `list_dir`
- [ ] The model emits a `tool` block; Hoseki overlay appears with results
- [ ] `tool_result` block is inserted into the chat input
- [ ] Pressing send delivers the result to the model
- [ ] Reload the extension — no stale tool calls run
- [ ] Turning on auto-send without the acknowledgement is refused

## Audit log

- [ ] `~/.hoseki/audit.jsonl` contains one line per tool call
- [ ] Each line has `ts`, `event`, `name`, `args`, `result`

## Threats to re-check after config changes

- [ ] Changing `[extension].allowed_origins` to a specific extension ID
      still lets the extension call the daemon
- [ ] Adding a secret path to `[secrets].deny_globs` immediately applies
- [ ] `[limits].max_calls_per_minute = 3` starts returning rate-limit errors