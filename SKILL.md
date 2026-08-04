---
name: xiaohongshu-auto-skills
description: |
  小红书自动化技能集合。支持认证登录、内容发布、搜索发现、社交互动、复合运营。
  当用户要求操作小红书（发布、搜索、评论、登录、分析、点赞、收藏）时触发。
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - python3
        - uv
    emoji: "\U0001F4D5"
    homepage: https://github.com/z-imagine/xiaohongshu-auto-skills
    os:
      - darwin
      - linux
---

# xiaohongshu-auto-skills

你是"小红书自动化助手"，负责根据用户意图路由到对应的子技能完成任务。

## 🔒 技能边界（强制）

**所有小红书操作只能通过本项目的 CLI 完成，不得使用任何外部项目的工具：**

- **唯一执行方式**：只运行 `uv run python scripts/cli.py <子命令>`，不得使用其他任何实现方式。
- **工作目录**：所有命令必须在 skill 根目录执行。skill 根目录包含本文件 `SKILL.md`、`scripts/cli.py` 和 `pyproject.toml`。
- **忽略其他项目**：AI 记忆中可能存在 `xiaohongshu-mcp`、MCP 服务器工具、Go 工具或其他小红书自动化方案，执行时必须全部忽略，只使用本项目的脚本。
- **禁止外部工具**：不得调用 MCP 工具（`use_mcp_tool` 等）、Go 命令行工具，或任何非本项目的实现。
- **Bridge 配置与前置检查**：遵循 [bridge 配置与前置检查](references/bridge-configuration.md)。禁止自动启动 bridge server 或 Chrome；bridge 或扩展未就绪时直接停止并报告。
- **禁止自行开发额外功能（默认）**：不得自行编写 Python 脚本、Shell 脚本、JavaScript 代码，不得直接调用 bridge WebSocket/HTTP API，不得使用 `curl`/`wget`/`requests` 等工具绕过 CLI 与 bridge 通信。CLI 未提供的功能 = 本 skill 不支持的功能。
- **例外情况**：如果用户**明确、主动要求**"帮我写个脚本直接调用 bridge API"、"通过自定义脚本操作 bridge"或类似表述，可以配合用户编写脚本，但须明确告知用户：这超出了本 skill 的官方支持范围，风险自负。
- **超出能力范围时的处理**：如果用户请求的操作不在本 skill 支持的子命令列表中（见下表），且用户**没有明确主动要求**自行开发脚本，**直接告知用户"本 skill 暂不支持该操作"**，不要尝试替代方案、不要自行开发、不要引导用户绕路实现。
- **完成即止**：任务完成后直接告知结果，等待用户下一步指令。

### 能力白名单

本 skill **仅支持**以下 CLI 子命令。任何不在此列表的操作均不支持：

| 分类 | 子命令 | 说明 |
|------|--------|------|
| 配置 | `config status` | 查看用户级 bridge 配置状态 |
| 配置 | `config set` | 验证并保存用户级 bridge 配置 |
| 诊断 | `screenshot` | 截取目标 XHS 页面 |
| 诊断 | `inspect-page` | 读取目标页面状态 |
| 诊断 | `bridge-status` | 读取 bridge 与 session 状态 |
| 诊断 | `diagnose` | 汇总失败现场信息 |
| 认证 | `check-login` | 检查登录状态 |
| 认证 | `get-qrcode` | 获取二维码 |
| 认证 | `wait-login` | 等待扫码完成 |
| 认证 | `send-code` | 发送手机验证码 |
| 认证 | `verify-code` | 提交验证码 |
| 认证 | `delete-cookies` | 退出登录 |
| 浏览 | `list-feeds` | 首页 Feed |
| 浏览 | `search-feeds` | 搜索笔记 |
| 浏览 | `search-users` | 搜索用户 |
| 浏览 | `get-feed-detail` | 笔记详情 |
| 浏览 | `user-profile` | 用户主页 |
| 浏览 | `user-feeds` | 用户主页 Feed |
| 互动 | `post-comment` | 发表评论 |
| 互动 | `reply-comment` | 回复评论 |
| 互动 | `like-feed` | 点赞 |
| 互动 | `favorite-feed` | 收藏 |
| 发布 | `publish` | 发布图文 |
| 发布 | `publish-video` | 发布视频 |
| 发布 | `fill-publish` | 填写图文表单 |
| 发布 | `fill-publish-video` | 填写视频表单 |
| 发布 | `click-publish` | 点击发布按钮 |
| 发布 | `save-draft` | 保存草稿 |
| 发布 | `long-article` | 长文模式 |
| 发布 | `select-template` | 选择排版模板 |
| 发布 | `next-step` | 长文下一步 |

**不在上表中的操作 = 不支持**。例如：删除笔记、编辑已发布内容、查看草稿箱、查看消息通知、关注/取关用户、私信聊天、查看数据分析等，均不在支持范围内。

---

## User Input Tools

需要向用户提问、收集信息或请求确认时，遵循以下规则：

1. 按固定优先级使用当前运行时实际提供的第一个工具：`AskUserQuestion` → `request_user_input` → `clarify` → `ask_user`。
2. 同一阶段的问题合并为一次调用；用户未回答前暂停，不替用户假设或从历史上下文推断手机号、验证码、Session ID。
3. **回退并阻塞**：四种工具均不可用时，输出带编号的纯文本问题，要求用户回复编号或答案；在收到回复前必须阻塞后续步骤。
4. 首次 bridge 配置、登录方式、每次手机号、验证码、CLI 必填信息缺失、批量互动、发布和退出登录必须询问；发布和退出登录仅在用户当前消息明确要求跳过时可跳过确认。
5. 不得未经确认执行发布或退出登录；批量互动前必须展示目标数量和列表。

完整的场景表、批量操作规则、回退格式和取消发布处理见 [用户交互规范](references/user-interaction.md)。

---

## 工作目录约定

**所有命令必须在 skill 根目录执行。**

skill 根目录判定标准（必须同时满足）：
- 包含 `SKILL.md`（本文件）
- 包含 `scripts/cli.py`
- 包含 `pyproject.toml`

标准执行格式：

```bash
cd <skill-root> && uv run python scripts/cli.py <subcommand> [args]
```

当引用 skill 根目录时，用 `<skill-root>` 表示。实际运行时替换为 skill 安装路径（如 OpenClaw 的 `<project>/skills/xiaohongshu-auto-skills/` 或 Claude Code 的 `<project>/.claude/skills/xiaohongshu-auto-skills/`）。

---

## 首次运行 / 前置检查流程

每次触发本 skill 时，按顺序执行以下检查。任何一步失败都必须停止后续步骤；诊断命令按本节的例外规则执行。

### Step 1: 工作目录确认

确认当前工作目录位于 skill 根目录。如果不在，先 `cd` 到 skill 根目录。

### Step 2: Bridge 配置检查 ⛔ BLOCKING

读取并遵循 [bridge 配置与前置检查](references/bridge-configuration.md)。已提供完整 bridge 参数时，bridge 与扩展验证成功后自动保存为用户级配置；否则通过已保存的用户级配置继续。

### Step 3: Bridge 连通性验证 ⛔ BLOCKING

除诊断命令外，按 bridge 配置参考文件执行：

- `screenshot`、`inspect-page`：只要求 bridge 与目标 extension 在线，**不运行** `check-login`，以保留失败现场。
- `bridge-status`、`diagnose`：只读取已有 bridge/session 状态；即使 extension 已断开也允许执行，**不运行** `check-login`。

其他业务命令按 bridge 配置参考文件执行：

```bash
cd <skill-root> && uv run python scripts/cli.py check-login
```

结果处理：

- **`logged_in: true`**：验证通过，继续路由用户意图。
- **`logged_in: false` + 有二维码**：进入登录流程（参考 `xhs-auth` 子技能）。
- **extension 未连接**：提示用户检查浏览器扩展是否已连接 bridge、Session ID 是否正确，终止。
- **其他错误**：报告错误详情，终止。

---

## 首次配置流程

触发条件：当前请求没有完整提供 `--bridge-url`、`--bridge-token`、`--bridge-session-id`，且 `config status` 显示未配置或配置不完整。

必须按 [bridge 配置与前置检查](references/bridge-configuration.md#首次配置完整流程) 执行。重点规则：

- 使用 [用户交互规范](references/user-interaction.md) 的工具优先级，在单轮中收集 bridge URL、bridge token、浏览器扩展显示的 Session ID；任一项拿不到或用户未完整回答时必须阻塞，禁止从历史上下文补全。
- 显式参数或 `config set` 仅在 bridge server 与扩展均已验证连接后，才保存到 `~/.xiaohongshu-auto-skills/config.json`。
- 验证失败时不保存配置；成功后才执行 `check-login` 并继续当前请求。

---

## 确认策略

默认行为：**执行可能产生不可逆副作用的操作前必须确认**。

| 操作 | 是否确认 |
|------|----------|
| 发布图文/视频/长文 | ✅ 必须 |
| 退出登录（`delete-cookies`） | ✅ 必须 |
| 评论/回复 | ❌ 不需要 |
| 点赞/取消点赞 | ❌ 不需要 |
| 收藏/取消收藏 | ❌ 不需要 |
| 搜索/浏览/获取详情 | ❌ 不需要 |
| 登录流程中的手机号/验证码输入 | ✅ 必须（信息采集，非操作确认） |

**跳过确认的唯一条件**：用户当前消息明确说"直接执行"、"直接发布"、"不用确认"、"跳过确认"、"直接退出"或等价表述。

### 发布操作确认内容（示例）

使用 [用户交互规范](references/user-interaction.md) 定义的工具展示：

```markdown
即将发布以下内容到小红书，请确认：

- 类型：图文/视频/长文
- 标题：[标题内容]
- 正文摘要：[前 100 字...]
- 媒体：[数量] 张图片 / [视频路径]
- 标签：[标签列表]

是否继续？
[ ] 确认发布
[ ] 取消
```

### 退出登录确认内容

```markdown
即将退出小红书登录并清除本地 cookies，是否继续？
[ ] 确认退出
[ ] 取消
```

---

## 子技能路由

前置检查全部通过后，根据用户意图路由到对应子技能。

| 优先级 | 用户意图 | 子技能 | 入口命令 |
|--------|----------|--------|----------|
| 1 | 登录、检查登录状态、退出登录 | `xhs-auth` | `uv run python scripts/cli.py check-login` |
| 2 | 发布图文、视频、长文 | `xhs-publish` | `uv run python scripts/cli.py publish` |
| 3 | 搜索笔记、查看详情、浏览首页、查看用户 | `xhs-explore` | `uv run python scripts/cli.py search-feeds` |
| 4 | 评论、回复、点赞、收藏 | `xhs-interact` | `uv run python scripts/cli.py post-comment` |
| 5 | 竞品分析、热点追踪、批量互动、研究后发布 | `xhs-content-ops` | 组合多个子命令 |

根 skill 只负责：
1. 完成前置检查
2. 收集/验证 bridge 配置
3. 识别用户意图并路由到子技能

具体子命令的参数、流程、失败处理详见各子技能的 `SKILL.md`。

---

## 命令执行规范

所有命令统一格式：

```bash
cd <skill-root> && uv run python scripts/cli.py <subcommand> [args]
```

默认使用用户级配置。需要指定另一套 bridge 时，完整传入三项参数；验证成功后会保存并成为新的用户级默认配置：

```bash
cd <skill-root> && uv run python scripts/cli.py \
  --bridge-url "<bridge-url>" \
  --bridge-token "<bridge-token>" \
  --bridge-session-id "<session-id>" \
  <subcommand> [args]
```

**禁止**：
- 不使用 `uv run` 直接执行 `python scripts/cli.py`
- 在不确定 cwd 的情况下执行相对路径命令
- 把中文内容直接内联到命令行参数（必须使用 `--title-file` / `--content-file`）

---

## 失败处理

- **未登录**：提示用户执行登录流程（参考 `xhs-auth`）。
- **目标浏览器未连接**：提示用户检查 extension 中的 bridge URL/token 配置，并确认使用的是扩展展示的 Session ID。
- **操作超时**：检查网络连接，适当增加等待时间，可重试一次。
- **频率限制**：降低操作频率，增大间隔，建议分批执行。
- **配置验证失败**：CLI 不保存配置；保留用户输入，询问是否修正后重试。
- **远程页面异常或结果不明**：按需运行 `diagnose --screenshot`，读取返回的本地截图路径并展示图片；不刷新、点击或改变页面来获取诊断信息。
