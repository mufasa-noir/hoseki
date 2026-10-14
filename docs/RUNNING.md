<div align="center">

<h2><b>Running Hoseki: Step-by-Step</b></h2>

[English](RUNNING.md) | [日本語](RUNNING_ja.md)

</div>

Follow these steps in order. Each step ends with a **checkpoint**, so don't move on until it passes. Do all of this on a **throwaway folder** first, and only point Hoseki at real code once everything below works.

You'll use two terminals:

- **Terminal #1**: runs the daemon and shows approval prompts. Keep it open.
- **Terminal #2**: everything else (`curl` checks, editing the config, and so on).

## Step 0: Prerequisites

Install these first and verify:

```bash
python3 --version          # need 3.11 or newer
git --version              # any recent version
```

> **Checkpoint:** `python3 --version` prints `Python 3.11.x` or higher.

The verification steps below also use `curl` and `jq`. Optional but recommended for the sandbox:

```bash
docker info                # if this errors, Docker isn't installed — fine, skip it
```

## Step 1: Get the Code

```bash
git clone https://github.com/mufasa-noir/hoseki.git hoseki
cd hoseki
```

> **Checkpoint:** `ls` shows `pyproject.toml`, `src/`, `extension/`, `docs/`, `README.md`.

## Step 2: Create a Virtual Environment and Install

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
```

> **Checkpoint:** `hoseki --version` prints `hoseki 0.2.1`. If `hoseki` isn't found, you're not in the venv. Run `source .venv/bin/activate` again.

## Step 3: Configure

```bash
cp config.example.toml config.toml
```

Open `config.toml` in your editor and set only this one line to start:

```toml
[workspace]
root = "/absolute/path/to/a/throwaway/folder"
```

Use a throwaway folder for now: a directory with one or two text files. **Do not point it at real code yet.**

> **Checkpoint:** `config.toml` exists and `[workspace].root` is a real, absolute path. Verify with:
>
> ```bash
> ls "$(grep '^root' config.toml | cut -d'"' -f2)"
> ```
>
> That should list the folder's contents. If it errors, fix the path.

## Step 4: Start the Daemon

In **terminal #1**:

```bash
hoseki serve --config ./config.toml
```

> **Checkpoint:** you see this line and the process stays running (no exit):
>
> ```text
> Hoseki 0.2.1 listening on http://127.0.0.1:8765  workspace=/abs/path/to/folder
> ```

**Keep this terminal open.** Approval prompts will appear here later. Do the rest of the steps in a second terminal.

## Step 5: Verify the Daemon Works

In **terminal #2**:

```bash
export TOKEN=$(cat ~/.hoseki/token)
export HOSEKI=http://127.0.0.1:8765
```

First, check health (no auth needed):

```bash
curl -s $HOSEKI/v1/health | jq
```

> **Checkpoint:** prints `{"ok": true, "service": "hoseki", "version": "0.2.1"}`.

Now list the workspace:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name":"list_dir","args":{"path":".","depth":1}}' \
     $HOSEKI/v1/call | jq -r .output
```

> **Checkpoint:** prints the file tree of your throwaway folder.

Now confirm the path jail works. **This must fail:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name":"read_file","args":{"path":"../../etc/passwd"}}' \
     $HOSEKI/v1/call | jq
```

> **Checkpoint:** prints `{"id": null, "ok": false, "error": "path ... resolves outside the workspace root"}`.
>
> **If it prints file contents instead, stop.** The jail is broken and you must not proceed.

## Step 6: Load the Browser Extension

There's one build per browser: `extension/chrome/` (Chrome, Edge, Brave, and other Chromium browsers) and `extension/firefox/` (Firefox).

### Chrome (or Edge/Brave)

1. Open `chrome://extensions`.
2. Toggle **Developer mode** on (top-right).
3. Click **Load unpacked**.
4. Select the `extension/chrome/` folder inside your Hoseki clone.
5. Click the Hoseki icon in the toolbar to open the popup.

### Firefox

1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on…** and select `extension/firefox/manifest.json` inside your Hoseki clone. Temporary add-ons are removed when Firefox closes, so repeat this next session.
3. Open the Hoseki popup from the toolbar (use the puzzle-piece Extensions menu if you don't see it).

### Then, in either browser

Fill in:

- **Daemon URL:** `http://127.0.0.1:8765`
- **Bearer token:** run `cat ~/.hoseki/token` in terminal #2 and paste the output.

Click **Save**.

> **Checkpoint:** click **Check health**. It must print `{"ok": true, ...}`. If it doesn't:
>
> - `network error`: the daemon isn't running (go back to Step 4).
> - `unauthorized`: the token was pasted wrong; re-run `cat ~/.hoseki/token`.

Then click **Status**.

> **Checkpoint:** prints your workspace root and the list of tools.

## Step 7: Open a Chat

Open a new tab to a supported chat:

- <https://chat.z.ai> (GLM)
- <https://kimi.com>
- <https://chat.deepseek.com> (DeepSeek)

Other chats need an adapter first (see the README).

Open DevTools (F12) → **Console**. Look for:

```text
[Hoseki] content script active for chat.z.ai adapter: GLM / z.ai (best-effort)
```

> **Checkpoint:** that line appears. If it doesn't, the content script didn't load. Reload the tab, or reload the extension at `chrome://extensions` (Firefox: `about:debugging`).
>
> If the line appears but nothing happens once the model emits a tool block, the site's selectors probably need refreshing. See [SELECTORS.md](SELECTORS.md).

## Step 8: Paste the Preamble

In the Hoseki popup, click **Copy preamble**. Then paste it into the chat as your first message and send it.

> **Checkpoint:** the chat has the preamble as message #1. The model may reply "understood" or just acknowledge.

## Step 9: Try the First Tool Call

Still in the chat, send this:

> List the files in my workspace and read the first 20 lines of the only file you find.

What should happen:

1. The model replies with a fenced `tool` block, e.g. `` ```tool {"id":"c1","name":"list_dir",...} ``.
2. Within a second or two, a floating Hoseki overlay appears at the bottom right of the chat, showing `✓ c1: ...`.
3. A `tool_result` block is inserted into the chat input box.

> **Checkpoint:** the overlay shows a green check and the input box is populated with a `tool_result` block.

**You press send yourself.** This is the default semi-automatic mode. Nothing is sent automatically.

The model then reads the result and continues. If it needs a second file, it emits another tool block, and the loop repeats.

## Step 10: Try a Write (Approval Flow)

In the chat, send:

> Create a file called HELLO.txt with the content "it works".

What should happen:

1. The model emits a `write_file` tool block.
2. Your **daemon terminal** (Step 4) prints:

   ```text
   ========================================================================
   HOSEKI APPROVAL REQUIRED — write_file
     write HELLO.txt (8 bytes, new file)
   ------------------------------------------------------------------------
   --- /dev/null
   +++ b/HELLO.txt
   @@ -0,0 +1,1 @@
   +it works
   ------------------------------------------------------------------------
   Approve? [y/N]
   ```

3. The daemon is now blocked, waiting for you. Type `y` and press Enter.

> **Checkpoint:** the daemon prints `-> APPROVED` and resumes. The overlay in the chat shows ✓, and the input box gets a success `tool_result`.

Verify the file exists:

```bash
ls "$(grep '^root' config.toml | cut -d'"' -f2)/HELLO.txt"
```

> **Checkpoint:** the file exists with content `it works`.

Now deny one on purpose. Send:

> Overwrite HELLO.txt with "second try".

When the approval prompt appears, type `n` and Enter.

> **Checkpoint:** the overlay shows `✗ ... denied by operator`, and `cat HELLO.txt` still shows `it works`.

## Step 11: Try a Command (Optional)

This requires a change to `config.toml`. In terminal #2:

```bash
# add "ls" to the allowlist (or "git status" if your workspace is a git repo)
nano config.toml
```

Find `[commands]` and uncomment one prefix, e.g.:

```toml
allowlist = [ "ls" ]
```

Save, then restart the daemon (Ctrl-C in terminal #1, then `hoseki serve --config ./config.toml` again).

In the chat, send:

> Run ls in the workspace and show me the output.

The approval prompt appears in the daemon terminal. Read the argv it shows, then type `y`.

> **Checkpoint:** the overlay shows the directory listing.

Try something that should be refused:

> Run rm -rf / in the workspace.

> **Checkpoint:** it fails immediately (not in the approval prompt) with `command not in allow-list` or `contains shell operator`. This is correct: the allow-list rejected it before it ever reached you.

## Step 12: Daily Use

Once Steps 1 to 11 have all passed on the throwaway folder, daily use is just:

1. Terminal #1: `cd hoseki && source .venv/bin/activate && hoseki serve --config ./config.toml`
2. Open a chat tab, paste the preamble, work.
3. Watch the daemon terminal for approval prompts.
4. Press send in the chat when the overlay populates the input.

You do not need to redo Steps 3 to 6 unless you change project folders or reinstall.

## Quick Troubleshooting

| Symptom                                           | Likely cause and fix                                                          |
| ------------------------------------------------- | ----------------------------------------------------------------------------- |
| `hoseki: command not found`                       | You're not in the venv. Run `source .venv/bin/activate`.                      |
| Popup says `network error`                        | The daemon isn't running. Start it (Step 4).                                  |
| Popup says `unauthorized`                         | Token pasted wrong. Re-run `cat ~/.hoseki/token` and paste it again.          |
| No `[Hoseki] content script active` console line  | Reload the chat tab, or reload the extension at `chrome://extensions`.        |
| Jail check prints file contents                   | **Stop.** The path jail is broken. Do not point Hoseki at real code.          |
| Commands fail with `command not in allow-list`    | Expected for anything not on the allow-list. Add a prefix in `[commands]` (Step 11). |
| Nothing happens after the model emits a tool block | The site's selectors are probably out of date. See [SELECTORS.md](SELECTORS.md). |
| Popup or overlay says `origin not allowed by daemon` | The daemon rejected your browser's extension origin (`chrome-extension://<id>` or `moz-extension://<uuid>`). Add it to the daemon's allowed origins. |
| Firefox: no `[Hoseki] content script active` line | Site access may not be granted: open `about:addons` → Hoseki → **Permissions**. Also check the temporary add-on is still loaded. |
