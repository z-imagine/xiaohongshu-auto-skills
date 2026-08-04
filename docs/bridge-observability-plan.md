# Bridge 与扩展可观测性计划

## 目标

当远端小红书浏览器执行异常、页面状态与预期不一致或 bridge 断连时，Agent 能通过现有 CLI 获取可核验的现场信息，而不是只能猜测错误原因。

本计划不改变现有根 skill 与五个子 skill 的结构，也不改变业务命令的执行语义。新增能力均为只读诊断命令；正常业务流程不自动采集截图或扩大日志。

## 当前事实与缺口

- 扩展已经实现 `screenshot_element`，但实际调用的是 `chrome.tabs.captureVisibleTab`：它抓取窗口当前可见 tab，忽略传入的 `selector` 和 `padding`。
- `BridgePage.screenshot_element()` 可拿到底层 PNG 字节，但 CLI 没有截图命令，因此远程 Agent 无法把图像落到 CLI 所在机器并展示。
- bridge 已维护 session 在线状态、心跳、最近命令、最近错误、重连次数；CLI 尚未提供读取该状态的诊断命令。
- NetLogger 已能记录脱敏网络元数据和风险信号，但默认关闭，且不能说明页面当前渲染内容、DOM 错误或 bridge 命令耗时。

## 设计原则

1. **目标 tab 精确性优先**：截图必须来自目标 XHS tab，不能依赖窗口当前前台 tab。
2. **诊断可部分成功**：截图失败时仍返回会话、页面和最近命令状态；单项失败不能掩盖其他信息。
3. **输出可被 Agent 消费**：截图由 CLI 写到 CLI 所在机器的文件，再输出绝对路径和图片元数据；不把大量 base64 直接打印到终端。
4. **不侵入正常操作**：截图、DOM 快照、网络追踪都由显式诊断命令或失败处理触发；不在每条业务命令后自动执行。
5. **保持现有协议兼容**：保留 `screenshot_element` 旧方法；新增明确命名的方法和 CLI 命令，不重构 WebSocket、HTTP 路由或五个子 skill。

## P0：远程截图与单次诊断

状态：已实现，等待真实远端浏览器回归。

### 1. 精确截图协议

新增 bridge 方法 `screenshot`，扩展使用 `chrome.debugger` 的 `Page.captureScreenshot` 对 `getOrOpenXhsTab()` 返回的具体 tab 截图。它不激活 tab、不改变页面导航。

返回：

```json
{
  "data": "<PNG base64>",
  "mime_type": "image/png",
  "width": 1280,
  "height": 720,
  "captured_at": "2026-08-04T12:00:00Z"
}
```

`screenshot_element` 暂时保留兼容；后续若需要元素截图，再以元素边界计算 `clip`，不能继续让名称与实际行为不一致。

### 2. CLI 截图命令

新增：

```bash
uv run python scripts/cli.py screenshot [--output /absolute/path/result.png]
```

- 未指定 `--output` 时，CLI 在本机临时诊断目录创建 PNG。
- 输出 JSON 含 `path`、`mime_type`、像素尺寸、捕获时间；Agent 可直接读取该本地路径并展示图片。
- 截图失败返回结构化错误码 `SCREENSHOT_FAILED`，不触发页面点击、刷新或重试导航。

### 3. 页面状态快照

新增扩展方法 `get_page_state`，一次返回：当前 URL、标题、`document.readyState`、viewport、滚动位置、当前聚焦元素摘要、页面是否存在 XHS 初始化状态，以及可见的错误/验证码/登录提示摘要。

新增 CLI：

```bash
uv run python scripts/cli.py inspect-page
```

它只读取状态，不返回完整 DOM 或页面正文。

### 4. 会话诊断入口

新增 CLI：

```bash
uv run python scripts/cli.py bridge-status
uv run python scripts/cli.py diagnose [--screenshot] [--output /absolute/path/result.png]
```

- `bridge-status` 输出已有的 session 快照：在线、扩展版本、心跳、连接/断开次数、最近命令、最近错误。
- `diagnose` 聚合 `bridge-status`、`inspect-page`；带 `--screenshot` 时再获取图片。
- 每个子项单独记录成功或错误，整体退出码仅在 bridge 完全不可达时失败。

### 5. Skill 接入

P0 完成后将 `screenshot`、`inspect-page`、`bridge-status`、`diagnose` 加入根 skill 的诊断白名单；只在用户要求查看现场或业务命令失败时使用，不进入成功路径。

## P1：命令链路与页面错误观测

### 1. Bridge 命令时间线

扩展 session 状态增加一个有界的最近命令环形缓冲：方法名、开始/结束时间、耗时、成功/失败、错误文本。bridge 服务端同步保留最近一次命令的耗时与状态，并通过 `bridge-status` 返回。

这解决“连接在线，但究竟卡在导航、DOM 查询、上传还是页面响应”的问题。

### 2. 页面错误与提示采集

新增可显式启用的短时 `page-trace`：

- `window.error` 与 `unhandledrejection`；
- 小红书页面可见 toast、验证码、登录失效、风控提示；
- 上限 100 条，按 session 保存，提供 `get-page-trace` 与 `clear-page-trace`。

默认不启用；`diagnose` 可以选择读取已存在的 trace，但不隐式开启长期采集。

## P2：网络与复现包

1. 保持 NetLogger 默认关闭；排障时使用现有 `enable-netlog` / `get-netlog` / `risk-report`。
2. `diagnose --with-netlog` 只汇总 NetLogger 的状态、最近错误和风险摘要，不自动启用它。
3. 新增 `diagnostic-bundle`，把截图路径、页面状态、session 状态、命令时间线、可选 NetLogger 摘要写成一个本地 JSON；不打包完整页面内容或原始网络请求。

## 实施顺序与验证

1. P0 精确截图：扩展 `Page.captureScreenshot`、`BridgePage` 方法、CLI `screenshot`，覆盖成功、扩展断连、解码失败和指定输出路径。
2. P0 状态：`get_page_state`、`bridge-status`、`diagnose`，验证部分失败仍输出其他子项。
3. 在真实远端浏览器验证：后台 XHS tab、弹窗/验证码、未登录页、扩展重连后截图。
4. P1 命令时间线与短时 page trace。
5. P2 复现包与使用文档。

每一阶段独立提交并可回滚；扩展改动后递增 manifest 版本，并要求在 Chrome 扩展页重新加载。
