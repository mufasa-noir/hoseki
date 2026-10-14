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

function send(msg) {
  return new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
}

async function load() {
  const s = { ...DEFAULTS, ...(await send({ type: "hoseki:getSettings" })) };
  document.getElementById("daemonUrl").value = s.daemonUrl;
  document.getElementById("token").value = s.token;
  document.getElementById("autoSend").checked = s.autoSend;
  document.getElementById("ack").checked = s.autoSendAcknowledged;
  document.getElementById("maxMessageChars").value = s.maxMessageChars;
  renderSite();
}

async function renderSite() {
  const el = document.getElementById("site");
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab || !tab.url) {
    el.textContent = "no active tab";
    return;
  }
  let host;
  try { host = new URL(tab.url).hostname; } catch { host = ""; }
  const supported = SUPPORTED_HOSTS.some(
    (h) => host === h || host.endsWith("." + h)
  );
  el.textContent = supported
    ? `✓ adapter available for ${host}`
    : `— no adapter for ${host || "(unknown)"}`;
  el.style.color = supported ? "#0a6b2c" : "#555";
  el.style.background = supported ? "#e8f8ec" : "#f3f3f3";
}

function setState(text) {
  document.getElementById("state").textContent = text;
}

document.getElementById("save").addEventListener("click", async () => {
  const patch = {
    daemonUrl: document.getElementById("daemonUrl").value.trim(),
    token: document.getElementById("token").value.trim(),
    autoSend: document.getElementById("autoSend").checked,
    autoSendAcknowledged: document.getElementById("ack").checked,
    maxMessageChars: parseInt(
      document.getElementById("maxMessageChars").value, 10
    ) || 3500
  };
  if (patch.autoSend && !patch.autoSendAcknowledged) {
    setState("auto-send requires the acknowledgement checkbox");
    return;
  }
  await send({ type: "hoseki:setSettings", patch });
  setState("saved");
});

document.getElementById("health").addEventListener("click", async () => {
  setState("checking…");
  const r = await send({ type: "hoseki:health" });
  setState(JSON.stringify(r, null, 2));
});

document.getElementById("status").addEventListener("click", async () => {
  setState("checking…");
  const r = await send({ type: "hoseki:status" });
  setState(JSON.stringify(r, null, 2));
});

document.getElementById("copyPreamble").addEventListener("click", async () => {
  const url = chrome.runtime.getURL("../preamble.md");
  const text = await (await fetch(url)).text();
  await navigator.clipboard.writeText(text);
  setState("preamble copied");
});

load();