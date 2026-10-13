// Content script. Watches the active chat page, parses `tool` blocks from
// the latest assistant message, forwards them to the background worker,
// shows results in a floating panel, and inserts the `tool_result` block
// into the chat input.
//
// Deliberately conservative: on parse error or ambiguity, do nothing.
//
// Supported sites: chat.z.ai (GLM), kimi.com, chat.deepseek.com.
// Selector verification status is noted per-adapter below. If selectors
// have drifted, run `hosekiDiagnose()` in the console to find new ones.

(function () {
  "use strict";

  // ------------------------------------------------------------------------
  // Adapters. Selectors are best-effort and MUST be verified after every
  // site UI change. If an adapter's selectors stop matching, the content
  // script does nothing on that site — it never runs stale tool calls.
  //
  // `verified` is the ISO date someone last confirmed the selectors against
  // a live page. "never" means unverified best-effort guess. If this is a
  // site you use, verify it and update this field.
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
      verified: "never",
      assistantMessage: [
        "[data-message-author-role='assistant']",
        "[data-role='assistant']",
        ".ds-markdown",
        "div[class*='ds-markdown']"
      ].join(", "),
      messageIdAttr: "data-message-id",
      streamingIndicator: "[class*='thinking'], [class*='streaming']",
      input: "textarea#chat-input, textarea[placeholder*='Message' i], textarea",
      sendButton: [
        "button[type='submit']",
        "div[role='button'][aria-disabled]",
        "div[role='button'][class*='send' i]",
        "[data-testid='send-button']"
      ].join(", "),
      stopButton: [
        "button[aria-label*='Stop' i]",
        "div[role='button'][aria-label*='Stop' i]",
        "[data-testid='stop-button']"
      ].join(", ")
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

  function extractToolBlocks(text) {
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
    if (document.querySelector(ADAPTER.streamingIndicator)) return true;
    if (document.querySelector(ADAPTER.stopButton)) return true;
    return false;
  }

  // Return the latest assistant message element that contains a ```tool
  // fence, or null. This differs from "just take the last match" because on
  // some sites the assistantMessage selector matches multiple nested nodes;
  // we want the outermost one that carries the tool block.
  function latestAssistantMessage() {
    const els = document.querySelectorAll(ADAPTER.assistantMessage);
    if (!els.length) return null;
    // Walk backwards; return the first element whose text contains a
    // ```tool fence. If none do, return the last one anyway (caller checks).
    for (let i = els.length - 1; i >= 0; i--) {
      const t = els[i].innerText || els[i].textContent || "";
      if (/```tool\b/.test(t)) return els[i];
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
    const text = msgEl.innerText || msgEl.textContent || "";
    const blocks = extractToolBlocks(text);
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
    const text = el.innerText || el.textContent || "";
    if (!/```tool\b/.test(text)) return;
    lastProcessedMessageId = msgId;
    handleCompletedMessage(el).catch((e) => {
      showOverlay("error: " + String(e));
    });
  }

  const mo = new MutationObserver(onMutations);
  mo.observe(document.body, { childList: true, subtree: true, characterData: true });
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
      stopButton: ADAPTER.stopButton
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