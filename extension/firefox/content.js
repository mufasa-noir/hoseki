// Content script. Watches the active chat page, parses `tool` blocks from
// the latest assistant message, forwards them to the background worker,
// shows results in a floating panel, and inserts the `tool_result` block
// into the chat input.
//
// Deliberately conservative: on parse error or ambiguity, do nothing.
//
// Debugging: run `window.__hosekiDebug = true` in the console to get
// verbose logs from the mutation/completion checks.
//
// Supported sites:
//   - chat.z.ai         (GLM)      — selectors verified 2026-10-15
//   - kimi.com / kimi.ai (Kimi)    — selectors verified 2026-10-15
//   - chat.deepseek.com (DeepSeek) — selectors verified 2026-10-14
//
// IMPORTANT — DeepSeek renders ```tool fences as structured code blocks
// (`.md-code-block` with the language label in a banner span, JSON in a
// <pre>). The literal ```tool fence is NOT present in the DOM, so the
// text-regex path finds nothing there. The adapter declares three extra
// fields (`toolBlockSelector`, `toolBlockLangSelector`,
// `toolBlockBodySelector`) that trigger a DOM-aware extraction path.
// Other sites that leave fences in the DOM still work via the fallback.
//
// DeepSeek stopButton is deliberately disabled — the classes on the send
// button are shared with the stop slot and can't distinguish idle from
// streaming, so isStreaming() would always return true. Rely on the
// 900 ms mutation debounce instead.

(function () {
  "use strict";

  // ------------------------------------------------------------------------
  // Adapters.
  // ------------------------------------------------------------------------
  const ADAPTERS = {
    "chat.z.ai": {
      name: "GLM / z.ai",
      verified: "2026-10-15",
      assistantMessage:
        "div[id^='message-']:not(.user-message):not([id$='-start'])",
      messageIdAttr: "id",
      toolBlockSelector: ".language-tool:not(.thinking-chain-container *)",
      toolBlockBodySelector: ".cm-content",
      streamingIndicator: "",
      stopButton: "",
      input: "textarea#chat-input",
      sendButton: "#send-message-button:not([disabled])"
    },

    "kimi.com": {
      name: "Kimi",
      verified: "2026-10-15",
      assistantMessage: ".chat-content-item-assistant",
      messageIdAttr: "data-archer-id",
      toolBlockSelector: ".segment-code",
      toolBlockLangSelector: ".segment-code-lang",
      toolBlockBodySelector: "pre",
      streamingIndicator: "",
      stopButton: "",
      input: "textarea, [contenteditable='true'][role='textbox']",
      sendButton: ".send-button-container:not(.disabled)"
    },

    "chat.deepseek.com": {
      name: "DeepSeek",
      verified: "2026-10-14",

      assistantMessage:
        "[data-virtual-list-item-key]:has(.ds-assistant-message-main-content)",

      messageIdAttr: "data-virtual-list-item-key",

      toolBlockSelector: ".md-code-block",
      toolBlockLangSelector: ".md-code-block-banner span",
      toolBlockBodySelector: "pre",
      streamingIndicator: "",
      stopButton: "",

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

  // Debug flag. Set `window.__hosekiDebug = true` in the console to enable.
  const dbg = (...args) => {
    if (window.__hosekiDebug) console.log("[Hoseki]", ...args);
  };

  const seenCalls = new Set();
  let debounceTimer = null;
  let lastProcessedMessageId = null;

  // ---------------------------------------------------------------- parsing

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

  function readCodeBlockLanguage(block) {
    if (ADAPTER.toolBlockLangSelector) {
      const spans = block.querySelectorAll(ADAPTER.toolBlockLangSelector);
      for (const s of spans) {
        const t = s.textContent.trim();
        if (/^[a-zA-Z][a-zA-Z0-9_+-]{0,19}$/.test(t)) return t;
      }
    }
    // Fallback: some sites put the language on the block itself as a
    // "language-xxx" class (GLM / z.ai).
    const m = /(?:^|\s)language-([a-zA-Z][a-zA-Z0-9_+-]{0,19})(?:\s|$)/
      .exec(block.className || "");
    return m ? m[1] : "";
  }

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
    if (ADAPTER.streamingIndicator) {
      const el = document.querySelector(ADAPTER.streamingIndicator);
      if (el) { dbg("isStreaming: indicator matched", el); return true; }
    }
    if (ADAPTER.stopButton) {
      const el = document.querySelector(ADAPTER.stopButton);
      if (el) { dbg("isStreaming: stopButton matched", el); return true; }
    }
    return false;
  }

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
    dbg("handleCompletedMessage: entered");
    const blocks = extractToolBlocks(msgEl);
    dbg("handleCompletedMessage: extracted", blocks);
    if (!blocks.length) return;

    const msgId = messageIdOf(msgEl);

    const fresh = blocks.filter((b) => {
      const key = `${msgId}::${b.id}`;
      if (seenCalls.has(key)) return false;
      seenCalls.add(key);
      return true;
    });
    dbg("handleCompletedMessage: fresh after dedup", fresh);
    if (!fresh.length) return;

    showOverlay(`Running ${fresh.length} tool call(s)…`);
    const results = await processToolBlocks(fresh);
    dbg("handleCompletedMessage: results", results);

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
    if (!el) { dbg("check: no assistant message found"); return; }
    if (isStreaming()) { dbg("check: streaming, skip"); return; }
    const msgId = messageIdOf(el);
    if (msgId === lastProcessedMessageId) {
      dbg("check: already processed", msgId);
      return;
    }
    if (!hasToolBlock(el)) {
      dbg("check: no tool block in", msgId);
      return;
    }
    dbg("check: firing for", msgId);
    lastProcessedMessageId = msgId;
    handleCompletedMessage(el).catch((e) => {
      console.error("[Hoseki] handle error:", e);
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
    "— run window.__hosekiDebug = true for verbose logs"
  );
})();
