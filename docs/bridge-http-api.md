# Bridge HTTP API

本文面向需要通过 HTTP 对接 bridge 的外部系统，例如：

- n8n
- curl / shell 脚本
- 你自己的后端服务
- 其他编排系统

当前 bridge 为**单进程单端口**服务，同一端口同时提供：

- WebSocket：给浏览器 extension 和现有 CLI 使用
- HTTP：给工作流系统和外部服务使用

HTTP 与现有 CLI 短 WebSocket 的**数据协议完全对等**：

- 请求字段一致
- `result` 返回结构一致
- `error` / `error_code` 一致

## 1. 基础信息

默认地址示例：

```text
http://127.0.0.1:9333
```

如果走反向代理，则按你的域名为准，例如：

```text
https://xhs-bridge.example.com
```

公共要求：

- `Content-Type: application/json`
- 所有 CLI 风格 RPC 都通过 `POST /rpc`
- `token` 放在 JSON body 中

## 2. 认证

bridge 启动时要求配置：

```bash
uv run python -m bridge.server --host 0.0.0.0 --port 9333 --token "<bridge-token>"
```

调用方必须在请求体中传：

```json
{
  "token": "<bridge-token>"
}
```

认证失败时返回：

HTTP 状态码：

```text
401 Unauthorized
```

响应体：

```json
{
  "error": "Bridge 鉴权失败",
  "error_code": "AUTH_FAILED"
}
```

## 3. 接口列表

### 3.1 `GET /health`

用途：

- 健康检查
- 查看 bridge 进程是否存活
- 查看当前在线 session 数量

请求示例：

```bash
curl http://127.0.0.1:9333/health
```

成功响应：

```json
{
  "ok": true,
  "server_running": true,
  "active_sessions": 1
}
```

### 3.2 `POST /rpc`

用途：

- 调用所有 CLI 同等能力
- 与现有短 WebSocket RPC 对等

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
| `role` | 否 | 建议固定传 `"cli"`；不传时服务端会默认补成 `"cli"` |
| `method` | 是 | 要调用的 bridge 方法 |
| `session_id` | 视方法而定 | 目标浏览器 session |
| `token` | 是 | bridge 鉴权 token |
| `params` | 否 | 方法参数对象 |

返回结构：

成功时：

```json
{
  "result": { ... }
}
```

失败时：

```json
{
  "error": "错误描述",
  "error_code": "错误码"
}
```

### 3.3 `GET /sessions/{session_id}`

用途：

- 查询指定 session 的状态快照
- 便于排障和接入方自检

请求示例：

```bash
curl "http://127.0.0.1:9333/sessions/session-xxx?token=bridge-token"
```

成功响应：

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

## 4. 常用 RPC 示例

以下示例全部走 `POST /rpc`。

### 4.1 `ping_server`

用途：

- 检查 bridge 是否在线
- 检查目标 session 是否有浏览器在线

请求：

```bash
curl -X POST http://127.0.0.1:9333/rpc \
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

### 4.2 `get_session_state`

请求：

```bash
curl -X POST http://127.0.0.1:9333/rpc \
  -H 'Content-Type: application/json' \
  -d '{
    "role": "cli",
    "method": "get_session_state",
    "session_id": "session-xxx",
    "token": "bridge-token"
  }'
```

### 4.3 `navigate`

请求：

```bash
curl -X POST http://127.0.0.1:9333/rpc \
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

响应：

```json
{
  "result": null
}
```

### 4.4 `evaluate`

请求：

```bash
curl -X POST http://127.0.0.1:9333/rpc \
  -H 'Content-Type: application/json' \
  -d '{
    "role": "cli",
    "method": "evaluate",
    "session_id": "session-xxx",
    "token": "bridge-token",
    "params": {
      "expression": "location.href"
    }
  }'
```

### 4.5 `click_element`

请求：

```bash
curl -X POST http://127.0.0.1:9333/rpc \
  -H 'Content-Type: application/json' \
  -d '{
    "role": "cli",
    "method": "click_element",
    "session_id": "session-xxx",
    "token": "bridge-token",
    "params": {
      "selector": "button.submit"
    }
  }'
```

## 5. 错误码与 HTTP 状态码

| `error_code` | HTTP 状态码 | 含义 |
| --- | --- | --- |
| `INVALID_JSON` | `400` | 请求体不是合法 JSON，或不是 JSON 对象 |
| `UNKNOWN_ROLE` | `400` | role 非法 |
| `MISSING_SESSION_ID` | `400` | 当前方法要求 `session_id`，但请求没传 |
| `AUTH_FAILED` | `401` | token 错误或缺失 |
| `EXTENSION_NOT_CONNECTED` | `409` | 目标浏览器未连接 |
| `EXTENSION_DISCONNECTED` | `409` | 执行过程中浏览器断开 |
| `COMMAND_TIMEOUT` | `504` | 命令执行超时 |

错误响应示例：

```json
{
  "error": "Extension 未连接: session=session-xxx",
  "error_code": "EXTENSION_NOT_CONNECTED"
}
```

## 6. 对接建议

### n8n

推荐用 HTTP Request 节点：

- Method: `POST`
- URL: `http://bridge-host:9333/rpc`
- Body Content Type: `JSON`
- Body:

```json
{
  "role": "cli",
  "method": "ping_server",
  "session_id": "session-xxx",
  "token": "bridge-token"
}
```

后续节点统一从：

- `result`
- `error`
- `error_code`

这三个顶层字段解析。

### 自有服务

建议把：

- `bridge_base_url`
- `bridge_token`
- `session_id`

作为配置项持久化，并在每次调用前先用：

- `GET /health`
- `POST /rpc` 的 `ping_server`

做可用性检查。

## 7. 兼容性说明

当前 HTTP RPC 与短 WebSocket CLI 使用同一套路由逻辑，因此：

- 方法名一致
- `params` 结构一致
- 成功结果一致
- 错误码一致

如果后续新增 bridge 方法，应该同步满足：

1. WebSocket 可调用
2. HTTP `/rpc` 可调用
3. 数据协议保持一致
