const DEFAULT_SETTINGS = {
  bridgeUrl: "ws://localhost:9333",
  sessionId: "default",
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
  sessionIdInput.value = stored.sessionId || DEFAULT_SETTINGS.sessionId;
  bridgeTokenInput.value = stored.bridgeToken || DEFAULT_SETTINGS.bridgeToken;
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#a62828" : "#6a6156";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const bridgeUrl = bridgeUrlInput.value.trim();
  const sessionId = sessionIdInput.value.trim();
  const bridgeToken = bridgeTokenInput.value;

  if (!bridgeUrl || !sessionId) {
    setStatus("Bridge URL 和 Session ID 不能为空", true);
    return;
  }

  await chrome.storage.local.set({ bridgeUrl, sessionId, bridgeToken });
  setStatus("配置已保存，扩展将自动重连。");
});

void loadSettings();
