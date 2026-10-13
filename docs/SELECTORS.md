<div align="center">

<h2><b>Finding and Configuring Selectors</b></h2>

[English](SELECTORS.md) | [日本語](SELECTORS_ja.md)

</div>

Hoseki can't know how a chat site is built, so each site gets an **adapter**: a handful of CSS selectors that point at the parts of the page Hoseki needs. Chat sites change their page structure without notice, so every adapter needs a refresh now and then. This guide shows how to find correct selectors with your browser's developer tools, and where to put them.

## Where Selectors Live

Each adapter is an entry in the `ADAPTERS` object near the top of `content.js`, in **both** build folders:

- `extension/chrome/content.js`
- `extension/firefox/content.js`

Keep the two in sync, or the two browsers will behave differently. (If you've moved the adapters into their own file, edit them there instead.)

An entry is keyed by **hostname** (`chat.z.ai`, with no `https://` and no path). A key also matches its subdomains, so `kimi.com` covers `www.kimi.com` too.

```js
"example.ai": {
  name: "Example AI (verified 2026-10-13)",
  assistantMessage: "[data-role='assistant']",
  messageIdAttr: "data-message-id",
  streamingIndicator: "[data-streaming='true']",
  input: "textarea, [contenteditable='true'][role='textbox']",
  sendButton: "button[type='submit'], button[aria-label*='send' i]",
  stopButton: "button[aria-label*='stop' i]"
},
```

## What Each Field Does

| Field                | What it must match                                                                 | How Hoseki uses it                                                      |
| -------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `assistantMessage`   | **One element per assistant reply**: the whole reply, not a paragraph or code block inside it | Hoseki reads the **last** match as the newest reply and looks for `tool` blocks in it |
| `messageIdAttr`      | The name of an attribute that holds a unique id per message (e.g. `data-message-id`) | Stops the same reply from being processed twice. Optional: if the attribute is missing, Hoseki falls back to a text hash |
| `streamingIndicator` | An element that exists **only while the model is generating**                      | Hoseki waits until it's gone before acting on a reply                   |
| `stopButton`         | The "Stop generating" button, which exists **only while the model is generating**  | Same as above; either one matching means "still streaming"              |
| `input`              | The chat box you type in (a `textarea` or a `contenteditable` element)             | Where Hoseki inserts the `tool_result` block                            |
| `sendButton`         | The send button                                                                    | Only used by the optional auto-send feature                             |

Every selector can be a comma-separated list (`"a, b, c"`), which is handy for covering small differences between page versions. If you see any `PUT_SELECTOR_HERE` placeholders, replace them with real selectors.

## Step by Step

Open the chat site, send a message or two so there are at least two assistant replies on screen, then open DevTools: **F12** (or **Ctrl+Shift+I**, **Cmd+Option+I** on macOS). Click the **element picker** (**Ctrl+Shift+C**) to point at things on the page, and use the **Console** tab to test selectors with `$$("...")`, which returns every match.

### 1. `assistantMessage`

Use the picker on an assistant reply, then walk up the tree in the Elements panel until the highlighted box covers the **whole reply** (text and code blocks) but **not** your own message. Look for a stable attribute on that element, then test it:

```js
$$("YOUR_SELECTOR").length
// should equal the number of assistant replies on screen

$$("YOUR_SELECTOR").at(-1).innerText.slice(0, 200)
// should be the start of the newest reply
```

If the count is higher than the number of replies, the selector is also matching inner pieces (paragraphs, code blocks). Make it more specific, or pick the parent. Hoseki only looks at the last match, so a selector that matches fragments would make it read just the last fragment.

### 2. `messageIdAttr`

```js
$$("YOUR_ASSISTANT_SELECTOR").map(e => e.getAttribute("data-message-id"))
```

You want a different value for each reply. If every value is `null`, that's fine: leave the field as it is and Hoseki will use its fallback.

### 3. `input`

Click into the chat box, pick it with the element picker, and test:

```js
const el = document.querySelector("YOUR_SELECTOR");
el.tagName                 // "TEXTAREA" or "DIV"
el.value ?? el.textContent // should show whatever you typed in the box
```

### 4. `streamingIndicator` and `stopButton`

These are the trickiest because they only exist briefly. Run this in the Console, then send a long prompt and watch the output:

```js
const t = setInterval(() => console.log(!!document.querySelector("YOUR_SELECTOR")), 500);
// when you're done: clearInterval(t)
```

It must print `true` **while the model is generating** and `false` once it has finished.

- A selector that **matches something that's always there** (a "Stop reading aloud" button, say) makes Hoseki wait forever.
- A selector that **never matches** lets Hoseki act on half-written replies.

### 5. `sendButton`

Type a few characters so the button is enabled, then check that `document.querySelector("YOUR_SELECTOR")` returns the send button. It's often disabled when the box is empty.

### 6. Reload and verify

1. Save `content.js` (in both folders).
2. Reload the extension: `chrome://extensions` (reload icon) or `about:debugging#/runtime/this-firefox` (**Reload**).
3. Reload the chat tab.
4. Open the Console. You should see:

```text
[Hoseki] content script active for <host> adapter: <name>
```

Then ask the model to list your workspace and check that the overlay appears and the `tool_result` block lands in the input box.

## Picking Selectors That Last

- **Prefer stable hooks**: `data-*` attributes, `role`, `aria-label`, and meaningful tag names. Avoid auto-generated class names like `css-1k3x9a` or `_7436101`, which tend to change on every site update.
- **Match loosely on wording**: `[aria-label*='stop' i]` matches "Stop", "Stop generating", and "stop response" (the `i` makes it case-insensitive).
- **Mind the UI language.** `aria-label` text follows the site's language. Set the site to English, or list both variants.
- **Keep them short.** Long chains like `div > div > div > span` break the moment the layout shifts.
- **Cover variants** with a comma list: `"[data-role='assistant'], .message-assistant"`.
- **Date your adapter.** Put "verified YYYY-MM-DD" in the `name` so you know how stale it is.

## Adding a New Site

1. Add an entry to `ADAPTERS` in `content.js`, in **both** `extension/chrome/` and `extension/firefox/`, using the hostname as the key.
2. Add the site's URL pattern (for example `https://chat.example.ai/*`) to `content_scripts[0].matches` in **both** `manifest.json` files. If your Firefox manifest also lists sites under host permissions, add it there too.
3. Reload the extension and the chat tab, then work through the steps above.

## Troubleshooting

| Symptom                                              | What to check                                                                              |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| No `[Hoseki] content script active` line in the Console | The site's hostname doesn't match an adapter key, or its URL isn't in the manifest's `matches` |
| Line appears, but nothing happens when the model emits a tool block | Re-run step 1: `assistantMessage` probably doesn't match the newest reply. Then step 4: a stuck streaming selector keeps Hoseki waiting |
| `assistantMessage` looks right, but still nothing    | Run `$$("YOUR_SELECTOR").at(-1).innerText` and make sure it contains the tool block as text. Hoseki looks for a fenced `tool` block in the reply's text, and some UIs render code blocks in a way that hides the fences |
| Overlay says it couldn't find the chat input         | Fix `input` (step 3)                                                                       |
| Results land in the box but aren't sent              | Expected: the default mode is semi-automatic, so you press send yourself                   |
| Need to re-run the completion check right now        | In the page's Console: `window.dispatchEvent(new Event("hoseki:trigger"))` (it still waits while the model is streaming) |
