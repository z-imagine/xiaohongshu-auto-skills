const DEFAULT_SETTINGS = {
  bridgeUrl: "",
  sessionId: "",
  bridgeToken: "",
  bridgeStatus: {
    phase: "idle",
    label: "未配置",
    detail: "请先填写 Bridge URL 和 Bridge Token。",
    updatedAt: 0,
  },
};

const form = document.getElementById("settings-form");
const bridgeUrlInput = document.getElementById("bridge-url");
const bridgeTokenInput = document.getElementById("bridge-token");
const statusChip = document.getElementById("status-chip");
const statusDetail = document.getElementById("status-detail");
const sessionValue = document.getElementById("session-value");
const formStatus = document.getElementById("form-status");
const reconnectBtn = document.getElementById("reconnect-btn");
const copySessionBtn = document.getElementById("copy-session-btn");

function setFormStatus(message, isError = false) {
  formStatus.textContent = message;
  formStatus.style.color = isError ? "#b33a2d" : "#6f665b";
}

function renderBridgeState(stored) {
  const bridgeStatus = {
    ...DEFAULT_SETTINGS.bridgeStatus,
    ...(stored.bridgeStatus || {}),
  };
  const sessionId = (stored.sessionId || "").trim();

  bridgeUrlInput.value = stored.bridgeUrl || "";
  bridgeTokenInput.value = stored.bridgeToken || "";

  statusChip.textContent = bridgeStatus.label || "未配置";
  statusChip.className = `status-chip ${bridgeStatus.phase || "idle"}`;
  statusDetail.textContent = bridgeStatus.detail || "请先填写 Bridge URL 和 Bridge Token。";
  sessionValue.textContent = sessionId || "尚未获取";
  copySessionBtn.disabled = !sessionId;
}

async function refresh() {
  const stored = await chrome.storage.local.get(DEFAULT_SETTINGS);
  renderBridgeState(stored);
  const runtime = await chrome.runtime.sendMessage({ type: "bridge:get-state" }).catch(() => null);
  if (runtime?.ok) {
    renderBridgeState({
      ...stored,
      sessionId: runtime.settings?.sessionId || stored.sessionId,
      bridgeStatus: runtime.bridgeStatus || stored.bridgeStatus,
    });
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const bridgeUrl = bridgeUrlInput.value.trim();
  const bridgeToken = bridgeTokenInput.value.trim();

  if (!bridgeUrl || !bridgeToken) {
    setFormStatus("Bridge URL 和 Bridge Token 为必填项。", true);
    return;
  }

  const current = await chrome.storage.local.get(DEFAULT_SETTINGS);
  const keepSessionId = current.bridgeUrl === bridgeUrl && current.bridgeToken === bridgeToken;
  await chrome.storage.local.set({
    bridgeUrl,
    bridgeToken,
    sessionId: keepSessionId ? (current.sessionId || "") : "",
  });
  setFormStatus(keepSessionId ? "配置已保存，扩展正在重连。" : "配置已保存，扩展将申请新的 Session ID。");
});

reconnectBtn.addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "bridge:reconnect" }).catch(() => null);
  setFormStatus("已触发重连。");
});

copySessionBtn.addEventListener("click", async () => {
  const sessionId = sessionValue.textContent.trim();
  if (!sessionId || sessionId === "尚未获取") return;
  await navigator.clipboard.writeText(sessionId);
  setFormStatus("Session ID 已复制。");
});

chrome.storage.onChanged.addListener((_changes, areaName) => {
  if (areaName !== "local") return;
  void refresh();
});

void refresh();
