// Background service worker. All localhost fetches go through here because
// page-level fetch to localhost is unreliable under site CSP and mixed
// content rules.

const DEFAULT_SETTINGS = {
  daemonUrl: "http://127.0.0.1:8765",
  token: "",
  autoSend: false,
  autoSendAcknowledged: false,
  maxMessageChars: 3500
};

async function getSettings() {
  const stored = await chrome.storage.local.get(DEFAULT_SETTINGS);
  return { ...DEFAULT_SETTINGS, ...stored };
}

async function setSettings(patch) {
  await chrome.storage.local.set(patch);
}

async function callDaemon(payload) {
  const { daemonUrl, token } = await getSettings();
  if (!token) {
    return { ok: false, error: "no token configured (open the Hoseki popup)" };
  }
  const url = daemonUrl.replace(/\/+$/, "") + "/v1/call";
  let resp;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
  } catch (e) {
    return { ok: false, error: "network error: " + String(e) };
  }
  if (resp.status === 401) return { ok: false, error: "unauthorized (bad token)" };
  if (resp.status === 403) return { ok: false, error: "origin not allowed by daemon" };
  if (!resp.ok) return { ok: false, error: `daemon HTTP ${resp.status}` };
  try {
    return await resp.json();
  } catch (e) {
    return { ok: false, error: "invalid JSON from daemon" };
  }
}

async function checkHealth() {
  const { daemonUrl } = await getSettings();
  const url = daemonUrl.replace(/\/+$/, "") + "/v1/health";
  try {
    const resp = await fetch(url);
    if (!resp.ok) return { ok: false, error: `HTTP ${resp.status}` };
    return await resp.json();
  } catch (e) {
    return { ok: false, error: "network error: " + String(e) };
  }
}

async function status() {
  const { daemonUrl, token } = await getSettings();
  if (!token) return { ok: false, error: "no token" };
  const url = daemonUrl.replace(/\/+$/, "") + "/v1/status";
  try {
    const resp = await fetch(url, {
      headers: { "Authorization": "Bearer " + token }
    });
    if (!resp.ok) return { ok: false, error: `HTTP ${resp.status}` };
    return await resp.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    switch (msg.type) {
      case "hoseki:call":
        sendResponse(await callDaemon(msg.payload));
        return;
      case "hoseki:health":
        sendResponse(await checkHealth());
        return;
      case "hoseki:status":
        sendResponse(await status());
        return;
      case "hoseki:getSettings":
        sendResponse(await getSettings());
        return;
      case "hoseki:setSettings":
        await setSettings(msg.patch || {});
        sendResponse({ ok: true });
        return;
      default:
        sendResponse({ ok: false, error: "unknown message type" });
    }
  })();
  return true; // keep channel open for async sendResponse
});