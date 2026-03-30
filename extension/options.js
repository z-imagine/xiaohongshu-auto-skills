const DEFAULT_SETTINGS = {
  bridgeUrl: "",
  sessionId: "",
  bridgeToken: "",
};

const form = document.getElementById("settings-form");
const bridgeUrlInput = document.getElementById("bridge-url");
const sessionIdInput = document.getElementById("session-id");
const bridgeTokenInput = document.getElementById("bridge-token");
const statusEl = document.getElementById("status");

async function loadSettings() {
  const stored = await chrome.storage.local.get(DEFAULT_SETTINGS);
  bridgeUrlInput.value = stored.bridgeUrl || DEFAULT_SETTINGS.bridgeUrl;
  sessionIdInput.value = stored.sessionId || "";
  bridgeTokenInput.value = stored.bridgeToken || DEFAULT_SETTINGS.bridgeToken;
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#a62828" : "#6a6156";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const current = await chrome.storage.local.get(DEFAULT_SETTINGS);
  const bridgeUrl = bridgeUrlInput.value.trim();
  const bridgeToken = bridgeTokenInput.value.trim();

  if (!bridgeUrl || !bridgeToken) {
    setStatus("Bridge URL 和 Bridge Token 为必填项", true);
    return;
  }

  const keepSessionId = current.bridgeUrl === bridgeUrl && current.bridgeToken === bridgeToken;
  await chrome.storage.local.set({
    bridgeUrl,
    bridgeToken,
    sessionId: keepSessionId ? (current.sessionId || "") : "",
  });
  sessionIdInput.value = keepSessionId ? (current.sessionId || "") : "";
  setStatus(keepSessionId ? "配置已保存，扩展将自动重连。" : "配置已保存，扩展将重连并向 bridge 申请新的 Session ID。");
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  if ("sessionId" in changes) {
    sessionIdInput.value = changes.sessionId.newValue || "";
    if (changes.sessionId.newValue) {
      setStatus("已从 bridge 获取 Session ID，可复制到 OpenClaw 使用。");
    }
  }
});

void loadSettings();
