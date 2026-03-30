# Bridge 运维与排障说明

本文记录中心 bridge 的部署、配置和排障要点。

## 1. 启动方式

推荐启动命令：

```bash
uv run python -m bridge.server --host 0.0.0.0 --port 9333 --token "<bridge-token>"
```

本地兼容入口：

```bash
uv run python scripts/bridge_server.py --host 0.0.0.0 --port 9333 --token "<bridge-token>"
```

## 2. 关键配置

### bridge 服务端

- `--host`
- `--port`
- `--token`

或环境变量：

- `XHS_BRIDGE_HOST`
- `XHS_BRIDGE_PORT`
- `XHS_BRIDGE_TOKEN`

### CLI

- `--bridge-url`
- `--bridge-session-id`
- `--bridge-token`

或环境变量：

- `XHS_BRIDGE_URL`
- `XHS_BRIDGE_SESSION_ID`
- `XHS_BRIDGE_TOKEN`

### extension

点击扩展图标打开 popup，配置：

- `Bridge URL`
- `Bridge Token`
- 连接后由 bridge 自动分配的 `Session ID`

## 3. Session 模型

一条浏览器连接对应一个 `session_id`。该值由 bridge 在扩展首次连接时分配，并由扩展持久化保存。

bridge 内部会记录：

- 当前是否在线
- extension 版本
- 最近一次心跳时间
- 最近一次命令时间
- 最近一次命令方法
- 最近一次错误
- 累计连接次数和断开次数

## 4. 错误码

bridge 当前统一返回：

| 错误码 | 含义 |
| --- | --- |
| `AUTH_FAILED` | token 错误或缺失 |
| `INVALID_JSON` | 握手或消息不是合法 JSON |
| `UNKNOWN_ROLE` | 不支持的连接角色 |
| `MISSING_SESSION_ID` | 请求缺少 session_id |
| `EXTENSION_NOT_CONNECTED` | 目标 session 没有在线浏览器 |
| `COMMAND_TIMEOUT` | 命令在 90 秒内未完成 |
| `EXTENSION_DISCONNECTED` | 执行过程中浏览器扩展断开 |

## 5. 排障顺序

### 5.1 CLI 报 bridge 无法连接

检查：

1. bridge 进程是否启动
2. `bridge-url` 是否可达
3. 反向代理是否正确放行 WebSocket

### 5.2 CLI 报 session 未连接

检查：

1. extension 是否已经打开并保存配置
2. extension 页面展示的 `session_id` 是否和 CLI 使用的一致
3. token 是否一致
4. popup 中的 bridge 地址是否指向正确环境

### 5.3 bridge 日志有命令超时

检查：

1. 用户浏览器页面是否卡住
2. 小红书页面结构是否变化
3. 是否存在网络资源下载慢导致上传未完成

### 5.4 媒体上传失败

检查：

1. `XHS_ASSET_UPLOAD_ENDPOINT` 是否已配置
2. 临时资源 URL 是否可访问
3. OSS 或临时资源服务是否允许浏览器读取
4. 远端资源的 `Content-Type` 是否合理

## 6. 当前已知限制

- bridge 的多用户能力已具备路由和状态基础，但仍需真实压测验证
- OSS 对象自动清理依赖外部临时资源服务或桶生命周期策略
- 视频和长文发布的真实浏览器集成回归仍需在目标环境验证
