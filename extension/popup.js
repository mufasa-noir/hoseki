const DEFAULTS = {
  daemonUrl: "http://127.0.0.1:8765",
  token: "",
  autoSend: false,
  autoSendAcknowledged: false,
  maxMessageChars: 3500
};

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
  const url = chrome.runtime.getURL("preamble.md");
  const text = await (await fetch(url)).text();
  await navigator.clipboard.writeText(text);
  setState("preamble copied");
});

load();