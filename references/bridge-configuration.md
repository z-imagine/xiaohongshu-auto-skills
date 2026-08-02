# Bridge 配置与前置检查

在执行任意小红书 CLI 命令前读取本文件。

## 配置来源

仅允许以下两种来源，优先级从高到低：

1. 本次命令同时提供 `--bridge-url`、`--bridge-token`、`--bridge-session-id`；
2. 用户级配置文件 `~/.xiaohongshu-auto-skills/config.json`。

除此之外的配置来源一律不支持。显式提供完整参数后，CLI 在 bridge server 和扩展验证成功时自动写入用户配置；验证失败时不保存。

## 首次配置完整流程

先执行：

```bash
uv run python scripts/cli.py config status
```

`configured: true` 时使用已保存配置继续；未配置或配置不完整时，按 [用户交互规范](user-interaction.md) 一次收集以下三项信息：

1. **Bridge URL**：Bridge 服务地址，例如 `ws://localhost:9333/ws` 或 `wss://your-bridge.example.com/ws`；
2. **Bridge Token**：部署 bridge 时设置的认证 token；
3. **Session ID**：浏览器扩展连接 bridge 后显示的 Session ID。获取方式：打开 Chrome → 扩展 XHS Bridge → 点击连接 → 复制显示的 Session ID。

用户未完整回答前暂停；不得从历史对话、记忆或上下文补全任一项。

使用用户提供的三项信息执行：

```bash
uv run python scripts/cli.py config set \
  --bridge-url "<bridge-url>" \
  --bridge-token "<bridge-token>" \
  --bridge-session-id "<session-id>"
```

`config set` 只有在 bridge server 和目标浏览器扩展已连接时才会保存配置。配置目录权限为 `0700`，配置文件权限为 `0600`。

- **验证成功**：告知用户配置已保存，运行 `check-login`，然后继续原请求。
- **验证失败**：不保存配置；仅报告可安全披露的错误，保留本轮已收集的信息，询问用户是否修正后重试。

## 连接与登录检查

- bridge server 和 Chrome 必须由用户预先启动并连接；CLI 禁止自动启动本地 bridge 或 Chrome。
- 每次执行非认证类账号操作前，都先运行 `check-login`；不缓存“已验证会话”。
- `check-login`、登录、退出登录使用认证流程自身处理，不递归检查。
- bridge 不可用、扩展未连接、Session ID 不匹配或用户未登录时，停止后续账号操作并报告原因。
