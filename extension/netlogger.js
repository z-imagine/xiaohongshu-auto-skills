/* 全程只记录脱敏网络元数据；默认关闭。 */
(() => {
  const STORAGE_KEY = "netlogEntries";
  const ENABLED_KEY = "netlogEnabled";
  const MAX_ENTRIES = 500;
  const pending = new Map();
  let enabled = false;
  let entries = [];
  let initialized = false;

  const isXhsUrl = (url) => {
    try {
      const host = new URL(url).hostname;
      return host === "xiaohongshu.com" || host.endsWith(".xiaohongshu.com");
    } catch (_) {
      return false;
    }
  };

  const sanitize = (details, patch = {}) => {
    const parsed = new URL(details.url);
    const path = parsed.pathname;
    let category = "other";
    if (/risk|captcha|verify|security/i.test(path)) category = "risk_signal";
    else if (/\/api\//i.test(path)) category = "business_api";
    else if (/\/collect|\/report|\/track/i.test(path)) category = "behavior_tracking";
    return {
      at: Date.now(),
      host: parsed.hostname,
      path,
      method: details.method || "GET",
      type: details.type || "other",
      category,
      ...patch,
    };
  };

  async function persist() {
    await chrome.storage.local.set({ [STORAGE_KEY]: entries });
  }

  async function append(entry) {
    entries.push(entry);
    if (entries.length > MAX_ENTRIES) entries = entries.slice(-MAX_ENTRIES);
    await persist();
  }

  async function init() {
    if (initialized) return;
    const stored = await chrome.storage.local.get({ [ENABLED_KEY]: false, [STORAGE_KEY]: [] });
    enabled = stored[ENABLED_KEY] === true;
    entries = Array.isArray(stored[STORAGE_KEY]) ? stored[STORAGE_KEY].slice(-MAX_ENTRIES) : [];
    initialized = true;
  }

  chrome.webRequest.onBeforeRequest.addListener(
    (details) => {
      if (!enabled || !isXhsUrl(details.url)) return;
      pending.set(details.requestId, details);
    },
    { urls: ["*://*.xiaohongshu.com/*"] },
  );
  chrome.webRequest.onCompleted.addListener(
    (details) => {
      if (!enabled || !isXhsUrl(details.url)) return;
      pending.delete(details.requestId);
      void append(sanitize(details, { status: details.statusCode }));
    },
    { urls: ["*://*.xiaohongshu.com/*"] },
  );
  chrome.webRequest.onErrorOccurred.addListener(
    (details) => {
      if (!enabled || !isXhsUrl(details.url)) return;
      pending.delete(details.requestId);
      void append(sanitize(details, { status: 0, error: details.error || "network_error" }));
    },
    { urls: ["*://*.xiaohongshu.com/*"] },
  );
  chrome.webRequest.onBeforeRedirect.addListener(
    (details) => {
      if (!enabled || !isXhsUrl(details.url)) return;
      void append(sanitize(details, { status: details.statusCode, category: "risk_redirect" }));
    },
    { urls: ["*://*.xiaohongshu.com/*"] },
  );

  self.NetLogger = {
    init,
    async getState() {
      await init();
      return { enabled, total: entries.length, maxEntries: MAX_ENTRIES };
    },
    async setEnabled(value) {
      await init();
      enabled = value === true;
      await chrome.storage.local.set({ [ENABLED_KEY]: enabled });
      return this.getState();
    },
    async getEntries() {
      await init();
      return entries.slice();
    },
    async clear() {
      await init();
      entries = [];
      pending.clear();
      await persist();
      return this.getState();
    },
  };

  void init();
})();
