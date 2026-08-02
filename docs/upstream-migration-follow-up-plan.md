# 来源改造跟进计划

> 建立日期：2026-08-02
>
> 依据：[来源项目代码比对报告](./upstream-code-comparison-report.md)

## 总体目标

在保留当前远端 Extension Bridge、HTTP API、Docker 部署和 Session ID 体系的前提下，选择性吸收来源项目的高价值修复，并新增可控、可脱敏、可自动停止的风控监控能力。

禁止整树 merge、整树覆盖和直接 cherry-pick 来源 `main`。

## 改造原则

- 每个改造都以本地当前代码为基线；
- 只移植必要函数和数据结构，不移植来源项目的架构删除；
- bug 修复和 NetLogger 特性分开提交；
- 先有离线测试，再接真实浏览器手工验证；
- 监控默认关闭，敏感数据默认脱敏；
- 风控信号优先触发停止，不自动尝试绕过平台限制。

## Phase 0：建立基线

- [ ] 保存当前工作树状态和本地 HEAD。
- [ ] 记录来源版本 `b043748`。
- [ ] 确认当前发布、点赞、收藏的已知行为。
- [ ] 为发布和互动模块补充可 mock 的 Page 测试边界。
- [ ] 确认 Bridge Token、Session ID 不进入 diff、日志和测试输出。

验收：可以在不连接真实小红书的情况下运行现有单元测试，并能明确区分“当前行为”和“来源行为”。

## Phase 1：移植互动状态修复

目标：吸收来源 `951da5e` 中对收藏状态确认的改进。

### 修改范围

- `scripts/xhs/like_favorite.py`
- 对应测试文件，例如新增 `tests/test_like_favorite.py`

### 实施内容

- 当详情映射只有一条记录时增加安全兜底；
- 点击前等待收藏按钮出现；
- 点击后短轮询目标状态；
- 只有状态确认失败时才重试；
- 状态仍未变化时返回失败，不返回“已执行成功”；
- 保持本地 Extension Bridge 的点击实现，不覆盖 `bridge.py` 的现有逻辑。

### 验收标准

- 已收藏时不会重复点击；
- 未收藏时点击成功并能确认状态；
- 点击失败会返回失败结果；
- 状态接口暂时不可读时不会误报成功；
- 点赞和收藏的行为不会互相影响。

## Phase 2：移植发布页兼容修复

目标：吸收 `51bcc75` 和 `6a25e29` 的有效逻辑，修复发布页反爬 Tab 和发布结果判断。

### 修改范围

- `scripts/xhs/publish.py`
- `scripts/xhs/errors.py`
- 可能涉及 `extension/background.js` 的少量 evaluate 支持
- 新增发布流程单测和浏览器手工冒烟记录

### 实施内容

#### 2.1 发布 Tab 定位

- 优先匹配 `data-hp-bound="1"` 的真实 Tab；
- 排除 `data-hp-kind`、`button-hp-installed` 等 Honey Pot 属性；
- 不因为 `left/top` 为负数就直接判定无效；
- 点击后确认目标 Tab 的 active 状态发生变化；
- 对未来没有 `data-hp-bound` 的版本保留安全 fallback。

#### 2.2 发布按钮触发

- 优先定位 `xhs-publish-btn[is-publish="true"]`；
- 检查 `submit-disabled`；
- 使用自定义 `publish` 事件触发；
- 保留旧 DOM 点击作为兼容 fallback，但必须验证结果。

#### 2.3 发布结果捕获

- 支持 XHR、fetch、console 和 DOM toast 四类反馈；
- 识别成功、普通业务失败和风控错误；
- 增加 `AccountRiskControlError`；
- 所有 hook 和 MutationObserver 在流程结束后清理；
- 超时只能返回“无法确认”，不能自动报告发布成功。

### 验收标准

- 图文和视频的 fill 流程不受影响；
- 发布 Tab 不会误点 Honey Pot；
- 成功发布能被识别；
- 风控错误能明确返回；
- 普通失败不会被误判为风控；
- 连续执行两次发布不会出现 hook 叠加；
- 旧页面结构仍能使用 fallback。

## Phase 3：NetLogger 最小可用版本

目标：引入风控观测能力，但不复制来源项目的完整 Popup 和架构。

### 第一批文件

- `extension/netlogger.js`
- `extension/interceptor.js`
- `extension/content.js`
- `extension/background.js`
- `extension/manifest.json`
- `scripts/xhs/bridge.py`
- `scripts/xhs/risk_analyzer.py`
- `scripts/cli.py`

### 第一批能力

- 默认关闭 NetLogger；
- 显式启用和关闭；
- 500 条环形缓存；
- 监听 XHS 业务请求和关键响应；
- 获取风险摘要；
- 获取最近 NetLog；
- 清空 NetLog；
- 高风险信号包含 `risk_redirect`、业务错误码、`isRiskUser`、cookie 变化等。

### 与来源实现的差异要求

- 不依赖“Popup 标题连点 5 次”作为唯一激活方式；
- 不直接使用来源项目硬编码 localhost WebSocket；
- 保留本地 Bridge URL、Token、Session ID 和心跳逻辑；
- 不覆盖本地 `background.js` 的连接配置和命令路由；
- 不默认保存原始 cookie、签名和完整请求体；
- `risk_analyzer.py` 设计为纯函数，方便单测。

### 监控策略

建议暴露以下 CLI：

```text
enable-netlog
disable-netlog
get-netlog --limit N
risk-report
clear-netlog
```

## Phase 4：自动风险门禁

目标：让监控真正影响自动化流程，而不是只提供事后报告。

### 建议行为

- 操作前读取当前风险状态；
- 操作中只关注新增高风险事件；
- 操作后再次读取风险状态；
- 出现 `risk`、`limit`、`block`、风险跳转或关键业务错误时停止后续动作；
- 返回“已停止，原因是风险信号”，不自动重试或继续降速绕过。

### 适用范围

第一阶段只接入：

- 批量搜索/详情读取；
- 批量点赞、收藏、评论；
- 连续发布。

单次普通查询不必增加额外延迟。

## Phase 5：可选 UI 和文档

- [ ] Popup 增加 NetLog 状态卡片；
- [ ] 支持 JSON 导出；
- [ ] 增加风险维度说明；
- [ ] 增加故障排查文档；
- [ ] 不引入来源项目与当前项目无关的 README 内容。

## 提交拆分建议

每个阶段独立提交，建议使用以下提交边界：

1. `fix(interact): confirm favorite state before success`
2. `fix(publish): locate real creator tab safely`
3. `fix(publish): dispatch publish and capture business result`
4. `feat(monitor): add redacted netlog collector`
5. `feat(monitor): expose risk report through cli`
6. `feat(monitor): stop automation on high-risk signal`
7. `test: add offline fixtures for publish and risk analyzer`

不把来源项目 hash 写入业务逻辑；在提交说明中保留来源 commit 链接即可。

## 回滚边界

- Phase 1 可单独回滚，不影响发布和 Bridge；
- Phase 2 可单独回滚，不影响 NetLogger；
- Phase 3 只涉及扩展和诊断接口，必须能关闭并清空缓存；
- Phase 4 若出现误报，应能通过配置关闭风险门禁，但不能绕过明确的 `block` 信号；
- 任一阶段失败，不回退整个项目到来源版本。

## 当前建议

建议先执行 Phase 1 和 Phase 2。NetLogger 作为 Phase 3 单独开发，确认数据脱敏、权限和测试方案后再接入 Phase 4 自动风险门禁。
