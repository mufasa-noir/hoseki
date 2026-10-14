// Content script. Watches the active chat page, parses `tool` blocks from
// the latest assistant message, forwards them to the background worker,
// shows results in a floating panel, and inserts the `tool_result` block
// into the chat input.
//
// Deliberately conservative: on parse error or ambiguity, do nothing.
//
// Supported sites:
//   - chat.z.ai       (GLM)      — selectors best-effort, unverified
//   - kimi.com        (Kimi)     — selectors best-effort, unverified
//   - chat.deepseek.com (DeepSeek) — selectors verified 2026-10-14
//
// IMPORTANT — DeepSeek renders ```tool fences as structured code blocks
// (`.md-code-block` with the language label in a banner span, JSON in a
// <pre>). The literal ```tool fence is NOT present in the DOM, so the
// text-regex path will find nothing there. The adapter declares three
// extra fields (`toolBlockSelector`, `toolBlockLangSelector`,
// `toolBlockBodySelector`) that trigger a DOM-aware extraction path.
// Other sites that leave fences in the DOM still work via the fallback.

(function () {
  "use strict";

  // ------------------------------------------------------------------------
  // Adapters. Selectors are best-effort and MUST be verified after every
  // site UI change. If an adapter's selectors stop matching, the content
  // script does nothing on that site — it never runs stale tool calls.
  //
  // `verified` is the ISO date someone last confirmed the selectors against
  // a live page. "never" means unverified best-effort guess.
  // ------------------------------------------------------------------------
  const ADAPTERS = {
    "chat.z.ai": {
      name: "GLM / z.ai",
      verified: "never",
      assistantMessage:
        "[data-message-role='assistant'], .chat-assistant, .message-assistant",
      messageIdAttr: "data-message-id",
      streamingIndicator:
        "[data-streaming='true'], .streaming, .is-streaming",
      input: "textarea, [contenteditable='true'][role='textbox']",
      sendButton: "button[type='submit'], button[aria-label*='Send' i]",
      stopButton:
        "button[aria-label*='Stop' i], button[data-stop='true']"
    },

    "kimi.com": {
      name: "Kimi",
      verified: "never",
      assistantMessage:
        ".segment-assistant, [data-role='assistant'], .chat-message.assistant",
      messageIdAttr: "data-message-id",
      streamingIndicator: ".is-streaming, [data-streaming='true']",
      input: "textarea, [contenteditable='true'][role='textbox']",
      sendButton: "button[type='submit'], .send-button",
      stopButton: "button[aria-label*='Stop' i], .stop-button"
    },

    "chat.deepseek.com": {
      name: "DeepSeek",
      verified: "2026-10-14",

      // Outer wrapper for an assistant reply. `:has()` requires Chrome 105+
      // / Firefox 121+; both are well past that.
      assistantMessage:
        "[data-virtual-list-item-key]:has(.ds-assistant-message-main-content)",

      messageIdAttr: "data-virtual-list-item-key",

      // DOM-aware extraction: DeepSeek renders code fences as
      // `.md-code-block` containers with the language in a banner span and
      // the body inside a <pre>. The literal ```tool fence is stripped by
      // the markdown renderer, so we read structure instead of text.
      toolBlockSelector: ".md-code-block",
      toolBlockLangSelector: ".md-code-block-banner span",
      toolBlockBodySelector: "pre",

      // Unverified — no streaming class visible in the completed-reply DOM.
      // isStreaming() falls through to stopButton, which reuses the send
      // button's primary/circle classes. Confirm by inspecting during a
      // live reply; if the classes differ, update stopButton.
      streamingIndicator: "",
      stopButton:
        "div[role='button'].ds-button--primary.ds-button--circle",

      input:
        "textarea[placeholder='Message DeepSeek'], textarea[placeholder*='Message' i]",

      sendButton:
        "div[role='button'].ds-button--primary.ds-button--circle:not(.ds-button--disabled)"
    }
  };

  function adapterForHost(host) {
    if (ADAPTERS[host]) return ADAPTERS[host];
    for (const key of Object.keys(ADAPTERS)) {
      if (host === key || host.endsWith("." + key)) return ADAPTERS[key];
    }
    return null;
  }

  const ADAPTER = adapterForHost(location.hostname);
  if (!ADAPTER) {
    console.log("[Hoseki] no adapter for", location.hostname,
                "— supported:", Object.keys(ADAPTERS).join(", "));
    return;
  }

  // Dedup set of `messageId::callId` we have already processed.
  const seenCalls = new Set();
  // Debounce timer for DOM mutations.
  let debounceTimer = null;
  // ID of the assistant message we last completed & processed.
  let lastProcessedMessageId = null;

  // ---------------------------------------------------------------- parsing

  // Try DOM-aware extraction first (used by DeepSeek and any site that
  // renders code fences as structured elements). Falls back to a regex on
  // the raw text for sites that leave ```tool fences in the DOM.
  function extractToolBlocks(msgEl) {
    if (ADAPTER.toolBlockSelector) {
      const blocks = [];
      const codeBlocks = msgEl.querySelectorAll(ADAPTER.toolBlockSelector);
      codeBlocks.forEach((block, i) => {
        const lang = readCodeBlockLanguage(block);
        if (lang !== "tool") return;
        const preEl = block.querySelector(
          ADAPTER.toolBlockBodySelector || "pre"
        );
        if (!preEl) return;
        const parsed = tryParseSloppy(preEl.textContent.trim(), i);
        if (parsed) blocks.push(parsed);
      });
      if (blocks.length) return blocks;
    }
    const text = msgEl.innerText || msgEl.textContent || "";
    return extractToolBlocksFromText(text);
  }

  // Regex over raw text. Works when ```tool fences survive in the DOM.
  function extractToolBlocksFromText(text) {
    const out = [];
    const re = /```tool\s*\n([\s\S]*?)(?:```|$)/g;
    let m;
    let i = 0;
    while ((m = re.exec(text)) !== null) {
      const raw = m[1].trim();
      if (!raw) continue;
      const parsed = tryParseSloppy(raw, i);
      if (parsed) {
        out.push(parsed);
        i += 1;
      }
    }
    return out;
  }

  // Read the language label from a code block. DeepSeek puts it in the
  // first short, identifier-shaped span inside the banner. We filter out
  // "Copy", "Download", and other button labels by requiring the token to
  // be a single alphanumeric word.
  function readCodeBlockLanguage(block) {
    if (!ADAPTER.toolBlockLangSelector) return "";
    const spans = block.querySelectorAll(ADAPTER.toolBlockLangSelector);
    for (const s of spans) {
      const t = s.textContent.trim();
      if (/^[a-zA-Z][a-zA-Z0-9_+-]{0,19}$/.test(t)) return t;
    }
    return "";
  }

  // Fast check: does this message contain at least one tool block?
  // Uses the DOM path when available, then falls back to the text regex.
  function hasToolBlock(el) {
    if (ADAPTER.toolBlockSelector) {
      const blocks = el.querySelectorAll(ADAPTER.toolBlockSelector);
      for (const b of blocks) {
        if (readCodeBlockLanguage(b) === "tool") return true;
      }
    }
    const text = el.innerText || el.textContent || "";
    return /```tool\b/.test(text);
  }

  function stripTrailingCommas(s) {
    return s.replace(/,(\s*[}\]])/g, "$1");
  }

  function tryParseSloppy(raw, index) {
    let obj = null;
    const attempts = [raw, stripTrailingCommas(raw)];
    for (const attempt of attempts) {
      try {
        obj = JSON.parse(attempt);
        break;
      } catch (_) { /* try next */ }
    }
    if (!obj || typeof obj !== "object") return null;
    const name = obj.name;
    const args = obj.args;
    if (typeof name !== "string" || !name) return null;
    if (args === null || typeof args !== "object") return null;
    let id = obj.id;
    if (typeof id !== "string" || !id) id = `auto-${index}`;
    return { id, name, args };
  }

  function messageIdOf(el) {
    const attr = ADAPTER.messageIdAttr;
    if (attr && el.getAttribute) {
      const v = el.getAttribute(attr);
      if (v) return v;
    }
    const t = (el.textContent || "").slice(0, 200);
    let h = 0;
    for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) | 0;
    return `h${h}:${(el.textContent || "").length}`;
  }

  // ------------------------------------------------------------- completion

  function isStreaming() {
    if (ADAPTER.streamingIndicator &&
        document.querySelector(ADAPTER.streamingIndicator)) {
      return true;
    }
    if (ADAPTER.stopButton &&
        document.querySelector(ADAPTER.stopButton)) {
      return true;
    }
    return false;
  }

  // Return the latest assistant message element that contains a tool block,
  // or the latest assistant message if none do (caller checks). Preferring
  // the one with the tool block guards against sites whose selector matches
  // multiple nested nodes per reply.
  function latestAssistantMessage() {
    const els = document.querySelectorAll(ADAPTER.assistantMessage);
    if (!els.length) return null;
    for (let i = els.length - 1; i >= 0; i--) {
      if (hasToolBlock(els[i])) return els[i];
    }
    return els[els.length - 1];
  }

  // -------------------------------------------------------------- overlay UI

  let overlayEl = null;

  function ensureOverlay() {
    if (overlayEl) return overlayEl;
    overlayEl = document.createElement("div");
    overlayEl.id = "hoseki-overlay";
    overlayEl.innerHTML = `
      <div class="hoseki-head">
        <span class="hoseki-title">Hoseki</span>
        <button class="hoseki-close" title="Close">×</button>
      </div>
      <div class="hoseki-body"></div>
      <div class="hoseki-foot">
        <span class="hoseki-hint"></span>
      </div>
    `;
    overlayEl.querySelector(".hoseki-close")
      .addEventListener("click", () => hideOverlay());
    document.body.appendChild(overlayEl);
    return overlayEl;
  }

  function showOverlay(text) {
    const o = ensureOverlay();
    o.querySelector(".hoseki-body").textContent = text;
    o.style.display = "block";
  }

  function hideOverlay() {
    if (overlayEl) overlayEl.style.display = "none";
  }

  function setOverlayHint(text) {
    const o = ensureOverlay();
    o.querySelector(".hoseki-hint").textContent = text || "";
  }

  // -------------------------------------------------------- input insertion

  function findInput() {
    return document.querySelector(ADAPTER.input);
  }

  function setNativeValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function insertIntoInput(text) {
    const el = findInput();
    if (!el) {
      setOverlayHint("could not find chat input; copy manually");
      return false;
    }
    el.focus();
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      const cur = el.value || "";
      const sep = cur && !cur.endsWith("\n") ? "\n\n" : "";
      setNativeValue(el, cur + sep + text);
      return true;
    }
    // contenteditable path
    let ok = false;
    try {
      ok = document.execCommand("insertText", false, text);
    } catch (_) { ok = false; }
    if (!ok) {
      const sel = window.getSelection();
      if (sel && sel.rangeCount) {
        const range = sel.getRangeAt(0);
        range.deleteContents();
        const node = document.createTextNode(text);
        range.insertNode(node);
        range.setStartAfter(node);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
      } else {
        el.appendChild(document.createTextNode(text));
      }
      el.dispatchEvent(new InputEvent("input", { bubbles: true }));
    }
    return true;
  }

  // ---------------------------------------------------------------- run flow

  async function processToolBlocks(blocks) {
    const results = [];
    for (const b of blocks) {
      const resp = await new Promise((resolve) => {
        chrome.runtime.sendMessage(
          { type: "hoseki:call", payload: b },
          (r) => resolve(r || { ok: false, error: "no response" })
        );
      });
      results.push({ id: b.id, ...resp });
    }
    return results;
  }

  function wrapResultForModel(resp) {
    if (resp && resp.ok) {
      return {
        id: resp.id,
        ok: true,
        output: String(resp.output ?? ""),
        truncated: Boolean(resp.truncated)
      };
    }
    return {
      id: resp.id,
      ok: false,
      error: String((resp && resp.error) || "unknown error")
    };
  }

  async function splitAndFormat(results, maxChars) {
    const lines = results.map((r) => JSON.stringify(wrapResultForModel(r)));
    const chunks = [];
    let cur = "";
    for (const line of lines) {
      const block = "```tool_result\n" + line + "\n```";
      if (cur && cur.length + 2 + block.length > maxChars) {
        chunks.push(cur);
        cur = block;
      } else {
        cur = cur ? cur + "\n\n" + block : block;
      }
    }
    if (cur) chunks.push(cur);
    if (chunks.length <= 1) return chunks;
    return chunks.map((c, i) => `[part ${i + 1}/${chunks.length}]\n${c}`);
  }

  async function handleCompletedMessage(msgEl) {
    const blocks = extractToolBlocks(msgEl);
    if (!blocks.length) return;

    const msgId = messageIdOf(msgEl);

    const fresh = blocks.filter((b) => {
      const key = `${msgId}::${b.id}`;
      if (seenCalls.has(key)) return false;
      seenCalls.add(key);
      return true;
    });
    if (!fresh.length) return;

    showOverlay(`Running ${fresh.length} tool call(s)…`);
    const results = await processToolBlocks(fresh);

    const settings = await new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: "hoseki:getSettings" }, resolve);
    });
    const maxChars = settings?.maxMessageChars || 3500;
    const chunks = await splitAndFormat(results, maxChars);

    const summaryLines = results.map((r) =>
      r.ok
        ? `✓ ${r.id}: ${String(r.output || "").slice(0, 120)}`
        : `✗ ${r.id}: ${r.error}`
    );
    showOverlay(summaryLines.join("\n"));
    setOverlayHint(
      settings?.autoSend && settings?.autoSendAcknowledged
        ? "auto-send is ON — review the warning"
        : "review, then press send"
    );

    for (let i = 0; i < chunks.length; i++) {
      insertIntoInput(chunks[i]);
      if (i < chunks.length - 1) {
        await new Promise((r) => setTimeout(r, 50));
      }
    }

    if (settings?.autoSend && settings?.autoSendAcknowledged) {
      const btn = document.querySelector(ADAPTER.sendButton);
      if (btn) btn.click();
    }
  }

  // --------------------------------------------------------------- observers

  function onMutations() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      checkForCompletedAssistantMessage();
    }, 900);
  }

  function checkForCompletedAssistantMessage() {
    const el = latestAssistantMessage();
    if (!el) return;
    if (isStreaming()) return;
    const msgId = messageIdOf(el);
    if (msgId === lastProcessedMessageId) return;
    if (!hasToolBlock(el)) return;
    lastProcessedMessageId = msgId;
    handleCompletedMessage(el).catch((e) => {
      showOverlay("error: " + String(e));
    });
  }

  const mo = new MutationObserver(onMutations);
  mo.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true
  });
  setInterval(checkForCompletedAssistantMessage, 2000);

  // -------------------------------------------------------------- diagnostic

  // Paste `hosekiDiagnose()` in the console on any chat page. It reports
  // which selectors in the current adapter match, and dumps the outerHTML
  // of the first match for each so you can find replacements.
  window.hosekiDiagnose = function () {
    const report = {
      host: location.hostname,
      adapter: ADAPTER.name,
      verified: ADAPTER.verified,
      selectors: {}
    };
    for (const [key, sel] of Object.entries({
      assistantMessage: ADAPTER.assistantMessage,
      streamingIndicator: ADAPTER.streamingIndicator,
      input: ADAPTER.input,
      sendButton: ADAPTER.sendButton,
      stopButton: ADAPTER.stopButton,
      toolBlockSelector: ADAPTER.toolBlockSelector || ""
    })) {
      let el = null;
      let count = 0;
      try {
        count = document.querySelectorAll(sel).length;
        el = document.querySelector(sel);
      } catch (e) {
        report.selectors[key] = { selector: sel, error: String(e) };
        continue;
      }
      report.selectors[key] = {
        selector: sel,
        matches: count,
        sample: el ? el.outerHTML.slice(0, 240) : null
      };
    }

    // If the adapter uses the DOM extraction path, also report what it sees
    // on the latest assistant message.
    const latest = latestAssistantMessage();
    if (latest && ADAPTER.toolBlockSelector) {
      const blocks = latest.querySelectorAll(ADAPTER.toolBlockSelector);
      report.codeBlocks = Array.from(blocks).map((b) => ({
        lang: readCodeBlockLanguage(b),
        preview: (b.querySelector(ADAPTER.toolBlockBodySelector || "pre")
          ?.textContent || "").slice(0, 120)
      }));
    }
    report.toolBlocksInLatest = latest ? extractToolBlocks(latest) : [];

    console.log("%c[Hoseki] diagnostic", "font-weight:bold");
    console.table(Object.fromEntries(
      Object.entries(report.selectors).map(([k, v]) => [
        k, { matches: v.matches ?? "(error)", selector: v.selector }
      ])
    ));
    console.log("full report:", report);
    return report;
  };

  console.log(
    "[Hoseki] content script active on", location.hostname,
    "— adapter:", ADAPTER.name,
    "(verified:", ADAPTER.verified + ")",
    "— run hosekiDiagnose() to check selectors"
  );
})();