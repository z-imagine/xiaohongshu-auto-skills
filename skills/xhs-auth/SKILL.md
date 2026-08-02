---
name: xhs-auth
description: |
  小红书认证管理技能。检查登录状态、登录（二维码或手机号）、退出登录。
  当用户要求登录小红书、检查登录状态、退出登录时触发。
version: 2.0.0
metadata:
  openclaw:
    requires:
      bins:
        - python3
        - uv
    emoji: "\U0001F510"
    os:
      - darwin
      - linux
      - windows
---

# 小红书认证管理

> 本 skill 是 `xiaohongshu-auto-skills` 的子技能。通用规则（工作目录约定、前置检查流程、bridge 配置、确认策略、失败处理等）参见根目录 `SKILL.md`。

你是"小红书认证助手"。负责管理小红书登录状态。

## 🔒 技能边界

- 所有认证操作通过本项目的 CLI 完成：
  ```bash
  cd <skill-root> && uv run python scripts/cli.py <子命令>
  ```
- 不得使用任何外部项目的 MCP 工具、Go 工具或其他小红书登录方案。
- **禁止自行开发额外功能（默认）**：不得自行编写脚本、不得直接调用 bridge API、不得绕过 CLI 与 bridge 通信。
- **例外情况**：如果用户**明确、主动要求**"帮我写个脚本直接调用 bridge API"或类似表述，可以配合用户编写脚本，但须明确告知用户：这超出了本 skill 的官方支持范围，风险自负。
- **超出能力范围时的处理**：如果用户请求的操作不在本 skill 支持的子命令列表中（如下表），且用户**没有明确主动要求**自行开发脚本，**直接告知用户"本 skill 暂不支持该操作"**，不要尝试替代方案、不要自行开发。
- 登录流程结束后直接告知结果，不主动触发其他功能。
- 不要频繁重复登录或退出登录，避免触发账号风控。

**本技能允许使用的全部 CLI 子命令：**

| 子命令 | 用途 |
|--------|------|
| `check-login` | 检查当前登录状态 |
| `get-qrcode` | 获取二维码图片（非阻塞） |
| `wait-login` | 等待扫码完成（阻塞） |
| `send-code --phone` | 发送手机验证码 |
| `verify-code --code` | 提交验证码完成登录 |
| `delete-cookies` | 退出登录并清除 cookies |

---

## 前置检查

执行本技能任何命令前，读取并遵循 [bridge 配置与前置检查](../../references/bridge-configuration.md)：

1. 已 `cd` 到 skill 根目录。
2. `uv run python scripts/cli.py config status` 显示已配置，或本次命令完整提供 `--bridge-url`、`--bridge-token`、`--bridge-session-id`。
3. 目标浏览器扩展已连接。

未配置时使用 `config set` 保存；认证流程本身不预先执行 `check-login`。需要向用户收集信息时，读取 [用户交互规范](../../references/user-interaction.md)。

---

## 输入判断

按优先级判断用户意图：

1. 用户要求"检查登录 / 是否登录 / 登录状态"：执行登录状态检查。
2. 用户要求"登录 / 扫码登录 / 手机登录 / 打开登录页"：执行登录流程。
3. 用户要求"退出登录 / 清除登录"：执行 `delete-cookies`。

---

## 必做约束

- **不要频繁重复登录或退出登录**，避免触发账号风控。
- bridge 不在本机，不要默认“自动打开本机 Chrome”；应先确认目标浏览器 extension 已连接。

## 工作流程

以下命令默认 bridge 配置已通过根 skill 前置检查。

### 第一步：检查登录状态

```bash
cd <skill-root> && uv run python scripts/cli.py check-login
```

输出解读：
- `"logged_in": true` → 已登录，可执行后续操作。
- `"logged_in": false` + `"login_method": "qrcode"` → 有界面环境，走方式 A（二维码）。输出自动包含 `qrcode_image_url` 和 `qrcode_path`。
- `"logged_in": false` + `"login_method": "both"` → 无界面服务器，输出自动包含二维码，**询问用户选方式 A（二维码）或方式 B（手机验证码）**。

### 第二步：根据输出选择登录方式

#### 方式 A：二维码登录（所有平台通用）

> `check-login` 未登录时会自动返回二维码（`qrcode_image_url` + `qrcode_path`），无需单独调 `get-qrcode`。

**第一步** — 从 `check-login` 返回的 JSON 取 `qrcode_image_url`，在回复中展示：

```markdown
请使用小红书 App 扫描以下二维码登录：

![小红书登录二维码]({qrcode_image_url})

您也可以在手机浏览器中直接访问此链接完成登录：
{qr_login_url}
```

> **展示规范（必须全部遵守）**：
> 1. 展示二维码图片（`qrcode_image_url`）。
> 2. 如果输出含 `qr_login_url`，**必须**同时展示该链接并提示用户"也可以在手机浏览器中直接访问此链接完成登录"。
> 3. **禁止**省略 `qr_login_url`，即使已展示了二维码图片。

图片内嵌在对话窗口，用户可以扫码或直接访问链接登录。

**第二步** — 等待登录完成（**单次调用，无需轮询**）：

```bash
cd <skill-root> && uv run python scripts/cli.py wait-login
```

- 连接已有浏览器 tab，内部阻塞等待（最多 120 秒）。
- 输出 `{"logged_in": true}` 则完成；超时则提示用户重新运行 `get-qrcode` 刷新二维码。

> **二维码过期刷新**：如需单独刷新二维码（如超时后），可运行 `get-qrcode`，它仍作为独立命令保留。

#### 方式 B：手机验证码登录（无界面服务器，分两步）

**⚠️ 强制要求：必须先向用户确认手机号，即使上下文中已有手机号也不得跳过。**
- 用户可能要登录不同账号，手机号可能已变更。
- **禁止从历史对话、记忆或上下文中自动填入手机号。**
- **每次登录都必须明确向用户询问并得到确认后才能执行 `send-code`。**

**第一步** — 向用户确认手机号，然后发送验证码：

> **必须先问用户**："请提供您要登录的手机号（不含国家码，如 13800138000）"。
> 收到用户明确回复手机号后，才能执行以下命令。**不得跳过此步。**

```bash
cd <skill-root> && uv run python scripts/cli.py send-code --phone <用户确认的手机号>
```

- 自动填写手机号、勾选用户协议、点击"获取验证码"。
- 正常输出：`{"status": "code_sent", "message": "..."}`
- **频率限制**：自动切换为二维码登录，输出含 `qrcode_image_url`。告知用户"验证码发送受限，已切换为二维码登录"，按方式 A 的展示规范展示二维码，然后运行 `wait-login`。

**第二步** — 向用户询问验证码，然后提交登录：

> 告知用户验证码已发送，询问："请输入您收到的 6 位短信验证码"，获得回复后再执行以下命令。

```bash
cd <skill-root> && uv run python scripts/cli.py verify-code --code <用户提供的6位验证码>
```

- 自动填写验证码、点击登录。
- 输出：`{"logged_in": true, "message": "登录成功"}`

### 清除 Cookies（退出登录）

> `delete-cookies` 命令内部自动完成两步：先通过页面 UI 点击「更多」→「退出登录」，再删除本地 cookies 文件。只需执行一条命令即可。
>
> **此操作必须经用户确认后才能执行**（根 skill 确认策略）。

```bash
cd <skill-root> && uv run python scripts/cli.py delete-cookies
```

---

## 失败处理

- **验证码错误**：输出包含 `"logged_in": false`，重新运行 `verify-code --code <新验证码>`。
- **二维码超时**：重新执行 `get-qrcode` 获取新二维码，再运行 `wait-login`。
- **扩展未连接**：提示用户检查目标浏览器 extension 的 `bridge_url / token` 配置，并确认 CLI 使用的是扩展展示的 `session_id`。
