# Bridge HTTP API

本文只描述 **bridge 基础设施层 HTTP 接口**。
小红书业务接口请看 [xhs-http-api.md](/Users/samuel/Projects/SkillProjects/xiaohongshu-auto-skills/docs/xhs-http-api.md)。

## 基础说明

- 原有 WebSocket 地址保持不变：
  - `ws://<host>:<port>`
  - `ws://<host>:<port>/ws`
- 新增的 HTTP 接口统一使用 `/bridge/*` 前缀：
  - `GET /bridge/health`
  - `POST /bridge/rpc`
  - `GET /bridge/sessions/{session_id}`

Bridge 启动示例：

```bash
uv run python -m bridge.server --host 0.0.0.0 --port 9333 --token "<bridge-token>"
```

## 认证规则

- `POST /bridge/rpc`：`token` 放在 JSON body
- `GET /bridge/sessions/{session_id}`：`token` 放在 query string
- `GET /bridge/health`：无需 token

认证失败返回：

```json
{
  "error": "Bridge 鉴权失败",
  "error_code": "AUTH_FAILED"
}
```

HTTP 状态码：

```text
401 Unauthorized
```

## 1. `GET /bridge/health`

用途：

- 检查 bridge 进程是否存活
- 查看当前在线 session 数量

示例：

```bash
curl http://127.0.0.1:9333/bridge/health
```

响应：

```json
{
  "ok": true,
  "server_running": true,
  "active_sessions": 1
}
```

## 2. `POST /bridge/rpc`

用途：

- 与现有 CLI 短 WebSocket 调用完全对等
- 面向底层浏览器自动化转发，不直接暴露小红书业务语义

请求体通用结构：

```json
{
  "role": "cli",
  "method": "ping_server",
  "session_id": "session-xxx",
  "token": "bridge-token",
  "params": {}
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `role` | 否 | 建议固定传 `"cli"`；不传时服务端会自动补成 `"cli"` |
| `method` | 是 | bridge 底层方法名 |
| `session_id` | 视方法而定 | 目标浏览器 session |
| `token` | 是 | bridge 鉴权 token |
| `params` | 否 | 方法参数对象 |

成功返回：

```json
{
  "result": { ... }
}
```

失败返回：

```json
{
  "error": "错误描述",
  "error_code": "错误码"
}
```

### 2.1 `ping_server`

请求：

```bash
curl -X POST http://127.0.0.1:9333/bridge/rpc \
  -H 'Content-Type: application/json' \
  -d '{
    "role": "cli",
    "method": "ping_server",
    "session_id": "session-xxx",
    "token": "bridge-token"
  }'
```

响应：

```json
{
  "result": {
    "server_running": true,
    "session_id": "session-xxx",
    "extension_connected": true,
    "session": {
      "session_id": "session-xxx",
      "connected": true,
      "extension_version": "0.1.0",
      "last_seen": "2026-04-26T12:00:00+00:00",
      "last_heartbeat_at": "2026-04-26T12:00:00+00:00",
      "connected_at": "2026-04-26T11:58:00+00:00",
      "disconnected_at": null,
      "connect_count": 3,
      "disconnect_count": 2,
      "last_command_at": "2026-04-26T12:00:00+00:00",
      "last_method": "navigate",
      "last_error": ""
    },
    "active_sessions": 1
  }
}
```

### 2.2 `get_session_state`

请求：

```bash
curl -X POST http://127.0.0.1:9333/bridge/rpc \
  -H 'Content-Type: application/json' \
  -d '{
    "role": "cli",
    "method": "get_session_state",
    "session_id": "session-xxx",
    "token": "bridge-token"
  }'
```

### 2.3 常见底层方法

除 `ping_server` / `get_session_state` 外，`/bridge/rpc` 还可直接调用现有 bridge 底层方法，例如：

- `navigate`
- `wait_for_load`
- `evaluate`
- `has_element`
- `click_element`
- `input_text`
- `input_content_editable`
- `set_file_input`
- `set_file_input_from_url`

示例：

```bash
curl -X POST http://127.0.0.1:9333/bridge/rpc \
  -H 'Content-Type: application/json' \
  -d '{
    "role": "cli",
    "method": "navigate",
    "session_id": "session-xxx",
    "token": "bridge-token",
    "params": {
      "url": "https://www.xiaohongshu.com/"
    }
  }'
```

## 3. `GET /bridge/sessions/{session_id}`

用途：

- 查询指定 session 的状态快照
- 做接入方自检或排障

示例：

```bash
curl "http://127.0.0.1:9333/bridge/sessions/session-xxx?token=bridge-token"
```

响应：

```json
{
  "result": {
    "session_id": "session-xxx",
    "connected": true,
    "extension_version": "0.1.0",
    "last_seen": "2026-04-26T12:00:00+00:00",
    "last_heartbeat_at": "2026-04-26T12:00:00+00:00",
    "connected_at": "2026-04-26T11:58:00+00:00",
    "disconnected_at": null,
    "connect_count": 3,
    "disconnect_count": 2,
    "last_command_at": "2026-04-26T12:00:00+00:00",
    "last_method": "navigate",
    "last_error": ""
  }
}
```

## 错误码

| `error_code` | HTTP 状态码 | 含义 |
| --- | --- | --- |
| `INVALID_JSON` | `400` | 请求体不是合法 JSON |
| `INVALID_ARGUMENT` | `400` | 请求字段不合法 |
| `UNKNOWN_ROLE` | `400` | role 非法 |
| `MISSING_SESSION_ID` | `400` | 缺少 `session_id` |
| `AUTH_FAILED` | `401` | token 错误或缺失 |
| `EXTENSION_NOT_CONNECTED` | `409` | 目标浏览器未连接 |
| `EXTENSION_DISCONNECTED` | `409` | 执行过程中浏览器断开 |
| `COMMAND_TIMEOUT` | `504` | 命令执行超时 |

## 对接建议

- 需要直接驱动底层浏览器能力时，使用 `/bridge/rpc`
- 需要调用小红书业务能力时，不要再拼 `method + params`，直接使用 `/xhs/*`
- 接入前建议先调用：
  - `GET /bridge/health`
  - `POST /bridge/rpc` 的 `ping_server`
