const DEFAULTS = {
  daemonUrl: "http://127.0.0.1:8765",
  token: "",
  autoSend: false,
  autoSendAcknowledged: false,
  maxMessageChars: 3500
};

const SUPPORTED_HOSTS = [
  "chat.z.ai", "z.ai",
  "kimi.com",
  "chat.deepseek.com", "deepseek.com"
];

const $ = (id) => document.getElementById(id);

function send(msg) {
  return new Promise((resolve) =>
    chrome.runtime.sendMessage(msg, (r) => {
      void chrome.runtime.lastError; // swallow "no receiver" noise
      resolve(r);
    })
  );
}

/* ---------- connection stamp ---------- */

function setLink(kind, label) {
  $("link").className = "stamp " + kind; // checking | online | offline
  $("linkText").textContent = label;
}

async function refreshLink() {
  setLink("checking", "checking…");
  const r = await send({ type: "hoseki:health" });
  const up = !!r && !r.error && r.ok !== false;
  setLink(up ? "online" : "offline", up ? "daemon online" : "daemon offline");
  return r;
}

/* ---------- output box ---------- */

function setState(text, isError = false) {
  const el = $("state");
  el.textContent = text;
  el.classList.toggle("err", isError);
}

function showResult(r) {
  if (r === undefined) {
    setState("no response from the background script", true);
    return;
  }
  const flat = JSON.stringify(r);
  const text = flat.length <= 60 ? flat : JSON.stringify(r, null, 2);
  setState(text, !!r.error || r.ok === false);
}

function flash(btn, text, ms = 1200) {
  const old = btn.textContent;
  btn.textContent = text;
  setTimeout(() => { btn.textContent = old; }, ms);
}

/* ---------- active tab ---------- */

async function renderSite() {
  const el = $("site");
  const label = $("siteText");
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab || !tab.url) {
    label.textContent = "can't read this tab's address";
    el.className = "site";
    return;
  }
  let host;
  try { host = new URL(tab.url).hostname; } catch { host = ""; }
  const supported = SUPPORTED_HOSTS.some(
    (h) => host === h || host.endsWith("." + h)
  );
  label.textContent = supported
    ? `Adapter ready on ${host}`
    : `No adapter for ${host || "this page"}`;
  el.className = "site " + (supported ? "ok" : "");
}

/* ---------- settings ---------- */

function syncAckBlock() {
  $("ackBlock").hidden = !$("autoSend").checked;
}

async function load() {
  const s = { ...DEFAULTS, ...(await send({ type: "hoseki:getSettings" })) };
  $("daemonUrl").value = s.daemonUrl;
  $("token").value = s.token;
  $("autoSend").checked = s.autoSend;
  $("ack").checked = s.autoSendAcknowledged;
  $("maxMessageChars").value = s.maxMessageChars;
  $("version").textContent = "v" + chrome.runtime.getManifest().version;
  syncAckBlock();
  renderSite();
  refreshLink();
}

$("autoSend").addEventListener("change", syncAckBlock);

$("toggleToken").addEventListener("click", () => {
  const input = $("token");
  const reveal = input.type === "password";
  input.type = reveal ? "text" : "password";
  const btn = $("toggleToken");
  btn.textContent = reveal ? "Hide" : "Show";
  btn.setAttribute("aria-pressed", String(reveal));
  btn.setAttribute("aria-label", reveal ? "Hide token" : "Show token");
});

$("save").addEventListener("click", async () => {
  const patch = {
    daemonUrl: $("daemonUrl").value.trim(),
    token: $("token").value.trim(),
    autoSend: $("autoSend").checked,
    autoSendAcknowledged: $("ack").checked,
    maxMessageChars: parseInt($("maxMessageChars").value, 10) || 3500
  };
  if (patch.autoSend && !patch.autoSendAcknowledged) {
    setState("Tick the acknowledgement to turn on auto-send.", true);
    const warn = document.querySelector(".warn");
    warn.classList.remove("flag");
    void warn.offsetWidth; // restart the nudge animation
    warn.classList.add("flag");
    $("ack").focus();
    return;
  }
  await send({ type: "hoseki:setSettings", patch });
  setState("Saved.");
  flash($("save"), "Saved ✓");
  refreshLink(); // the daemon URL may have changed
});

$("health").addEventListener("click", async () => {
  setState("checking…");
  showResult(await refreshLink());
});

$("status").addEventListener("click", async () => {
  setState("checking…");
  showResult(await send({ type: "hoseki:status" }));
});

$("copyPreamble").addEventListener("click", async () => {
  try {
    const url = chrome.runtime.getURL("preamble.md");
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    await navigator.clipboard.writeText(await resp.text());
    setState("Preamble copied.");
    flash($("copyPreamble"), "Copied ✓");
  } catch (e) {
    setState("Couldn't copy preamble.md: " + String(e), true);
  }
});

load();