# 来源项目代码比对报告

> 比对日期：2026-08-02
>
> 本地项目：`z-imagine/xiaohongshu-auto-skills`
>
> 来源项目：`autoclaw-cc/xiaohongshu-skills`
>
> 来源临时 clone：`/tmp/xhs-upstream.qXDu5O`

## 结论摘要

来源项目当前 `main` 为 `b043748`（2026-05-24）。GitHub 页面确认本项目 fork 自该仓库，但双方当前已经是不同的提交历史，不能把来源项目 `main` 当作普通的“落后分支”直接 merge。

来源项目近期改动分成三类：

1. 发布页反爬兼容和结果判断修复：影响大，建议优先移植。
2. 点赞/收藏状态确认修复：改动小，建议部分移植。
3. NetLogger 风控监控：较大的新特性，建议独立设计、独立移植，不直接复制来源项目整套实现。

本报告只做代码比对和移植决策，未对业务代码执行 cherry-pick 或 merge。

## 分支和架构差异

本地项目相对来源项目新增或保留了以下能力：

- 配置化远端 Extension Bridge；
- `bridge/` 服务端和 HTTP API；
- Docker / Compose 部署；
- 远端媒体资源处理；
- `search-users`、`user-feeds` 等扩展命令；
- Session ID、Bridge Token 和远端浏览器配置流程。

来源项目当前版本则包含：

- 发布页新的反爬兼容逻辑；
- NetLogger、interceptor 和风险分析器；
- `check-risk`、`get-netlog`、`risk-report` 等诊断命令。

来源项目相对本地树会删除或替换 `bridge/`、Docker、HTTP API、远端媒体和部分测试文件。因此不接受整树覆盖，也不直接 merge 来源 `main`。

## 提交级比对

### A. 建议优先移植的 bug / 兼容性修复

| 提交 | 类型 | 代码变化 | 本地状态 | 决策 |
|---|---|---|---|---|
| [`951da5e`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/951da5e) | bug 修复 | 收藏状态兜底、等待按钮、点击后轮询状态、失败才重试 | `like_favorite.py` 仍是旧逻辑；Bridge/CDP 点击部分已有本地实现 | 只移植 `like_favorite.py` 部分 |
| [`319260c`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/319260c) | 兼容性修复 | 处理隐藏 Tab | 后续发现会误点 Honey Pot | 跳过 |
| [`a033b40`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/a033b40) | 反爬修复 | 排除 `data-hp-kind` / `button-hp-installed`，确认 active 切换 | 本地仍使用旧可见性判断 | 不单独移植，吸收最终逻辑 |
| [`51bcc75`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/51bcc75) | 反爬兼容 | `data-hp-bound` 真 Tab、`dispatchEvent('publish')`、发布业务错误码 | 本地发布按钮仍是 `button.bg-red.click()` | 高优先级重写移植 |
| [`6a25e29`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/6a25e29) | 结果判断修复 | XHR/fetch 内容捕获、console hook、DOM toast observer | 本地没有发布结果捕获 | 与 `51bcc75` 成套移植 |
| [`5c1ccce`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/5c1ccce) | 扩展稳定性 | 处理 `Extension context invalidated` | 本地没有对应 interceptor 消息链 | 随 NetLogger 一起移植 |

### B. NetLogger 监控特性提交链

这些提交共同构成一个 feature，不应逐个独立 cherry-pick。

| 提交 | 作用 | 决策 |
|---|---|---|
| [`8e1aef3`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/8e1aef3) | NetLogger 设计文档 | 参考，不直接复制 |
| [`0d0e8d2`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/0d0e8d2) | 实施计划 | 参考，按本地架构重写 |
| [`ba4b01e`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/ba4b01e) | 增加风控域名权限 | 需要重新审查权限范围 |
| [`e506e7d`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/e506e7d) | 环形缓冲、开关、Storage | 建议移植核心思路 |
| [`02ef6d1`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/02ef6d1) | 初始化失败日志 | 建议吸收 |
| [`ab96101`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/ab96101) | WebRequest 四阶段监听 | 建议移植，需测试权限 |
| [`63489f4`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/63489f4) | fetch/XHR 响应拦截 | 建议移植，需脱敏 |
| [`a86348f`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/a86348f) | 请求分类、cookieDiff | 建议移植核心分类，限制敏感数据 |
| [`512d960`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/512d960) | Popup 时序流 UI | 非必要，暂缓 |
| [`73d28fa`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/73d28fa) | 检测维度和 JSON 导出 UI | CLI 优先，UI 暂缓 |
| [`cddad91`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/cddad91) | CLI 字符串语法修复 | 仅作为代码参考 |
| [`f27e929`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/f27e929) | 修复响应体捕获链路 | 建议吸收 |
| [`801ae8c`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/801ae8c) | 绕过 XHS fetch wrapper | 建议吸收 |
| [`117a8c9`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/117a8c9) | 修复 interceptor 语法错误 | 随 interceptor 移植 |
| [`d575ca1`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/d575ca1) | 提取 `isRiskUser` | 建议移植到风险分析器 |
| [`fbd2df5`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/fbd2df5) | 新增 `get-netlog` / `risk-report` | 建议移植，但增加显式开关 |
| [`a273c38`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/a273c38) | 反爬分析附录 | 参考，不直接合并 |

来源 NetLogger 约包含：

- `extension/netlogger.js`：请求监听和 500 条环形缓存；
- `extension/interceptor.js`：页面 MAIN world 的 fetch/XHR 拦截；
- `scripts/xhs/risk_analyzer.py`：风险分析；
- CLI 和 Bridge 查询接口；
- Popup 隐藏激活和展示界面。

来源实现默认关闭，并依赖 Popup 连点标题 5 次激活；它提供的是“可查询的风控观测”，还不是完整的自动阻断机制。

### C. 不建议移植的其他提交

| 提交 | 内容 | 决策 |
|---|---|---|
| [`a4070f2`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/a4070f2) | 增加 `python-socks` 依赖 | 当前运行时无明确需求，暂缓 |
| [`4958dcf`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/4958dcf) | 合并 PR | 不移植 |
| [`b240ec9`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/b240ec9) | 忽略 JetBrains 文件 | 本地已处理 |
| [`3d783ae`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/3d783ae) | README 链接 | 不影响运行 |
| [`cc4f1b7`](https://github.com/autoclaw-cc/xiaohongshu-skills/commit/cc4f1b7) | README 链接 | 不影响运行 |

二维码、手机登录、Tab 隔离等更早提交，本地已经存在平行实现；除非回归测试发现缺失，不重复移植。

## 重点风险

### 发布结果 hook 需要清理

来源 `6a25e29` 会覆盖页面的 `XMLHttpRequest`、`fetch` 和 `console`，并创建 MutationObserver。原实现没有完整的 `finally` 清理机制。直接复制可能导致多次发布后 hook 叠加、重复捕获或性能下降。

移植时应封装为一次性 observer，并在成功、失败、超时三个出口都恢复原对象和断开 observer。

### NetLogger 会触碰敏感数据

请求头和请求体可能包含：

- `xs`、`xt`、`x-s-common` 等签名信息；
- cookie 变化；
- 业务请求体中的账号或内容信息。

移植时必须：

- 默认关闭原始日志；
- 明确启用；
- 对 token、cookie、请求体进行脱敏或截断；
- 不把原始 NetLog 写入普通日志或最终回复；
- 提供清空命令。

### 自动监控需要增加阻断点

来源项目只是让 Agent 查询 `risk-report`。如果目标是自动化监控，还需要在 CLI 操作前后检查风险状态，并在 `risk / limit / block` 时停止后续操作。

