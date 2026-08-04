# XHS HTTP API

业务接口统一使用 `/xhs/*` 前缀。

每个接口都要求：

- `session_id`
- `token`

认证方式与 `/bridge/*` 相同，`token` 放在 JSON body。

## 认证与通用错误

认证失败：

```json
{
  "error": "Bridge 鉴权失败",
  "error_code": "AUTH_FAILED"
}
```

缺少业务字段：

```json
{
  "error": "缺少必填字段: session_id",
  "error_code": "INVALID_ARGUMENT"
}
```

## 认证类

### `POST /xhs/check-login`

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token"
}
```

未登录响应：

```json
{
  "logged_in": false,
  "login_method": "qrcode",
  "qrcode_image_url": "...",
  "qrcode_base64": "...",
  "hint": "未登录，请扫码后调用 /xhs/wait-login"
}
```

### `POST /xhs/login`

阻塞等待扫码登录完成。

### `POST /xhs/get-qrcode`

获取二维码，不阻塞等待。

### `POST /xhs/wait-login`

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "timeout": 120
}
```

### `POST /xhs/send-code`

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "phone": "13800138000"
}
```

### `POST /xhs/verify-code`

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "code": "123456"
}
```

### `POST /xhs/delete-cookies`

退出登录。

## 浏览类

### `POST /xhs/list-feeds`

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token"
}
```

### `POST /xhs/search-feeds`

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "keyword": "openclaw",
  "sort_by": "最多点赞",
  "note_type": "图文",
  "publish_time": "一天内",
  "search_scope": "不限",
  "location": "不限"
}
```

### `POST /xhs/search-users`

搜索用户/账号。该接口通过浏览器打开搜索页并切换到“用户”tab，从页面状态读取结果。

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "keyword": "openclaw"
}
```

响应：

```json
{
  "users": [
    {
      "id": "USER_ID",
      "name": "OpenClaw大模型",
      "redId": "178548264",
      "fans": "606",
      "noteCount": 37,
      "xsecToken": "XSEC_TOKEN",
      "avatar": "https://...",
      "profileUrl": "https://www.xiaohongshu.com/user/profile/...",
      "updateTime": "1天前更新"
    }
  ],
  "count": 1
}
```

### `POST /xhs/get-feed-detail`

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "feed_id": "FEED_ID",
  "xsec_token": "XSEC_TOKEN",
  "load_all_comments": true,
  "click_more_replies": true,
  "max_replies_threshold": 20,
  "max_comment_items": 0,
  "scroll_speed": "normal"
}
```

### `POST /xhs/current-user`

查询当前登录账号的基本信息。无需传 `user_id` 或 `xsec_token`；未登录时返回 `NOT_LOGGED_IN`。

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token"
}
```

响应包含 `userId`、`nickname`、`redId`、`avatar`、`description`、`profileUrl` 与互动统计；不会返回 Cookie 或 `xsec_token`。

### `POST /xhs/user-profile`

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "user_id": "USER_ID",
  "xsec_token": "XSEC_TOKEN"
}
```

### `POST /xhs/user-feeds`

查询用户笔记第一页；传 `load_more: true` 时触发一次“加载更多”并只返回本次新增内容。默认响应包含 `userId`、`page: 1`、`notes`、`count` 与 `hasMore`。

请求：

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "user_id": "USER_ID",
  "xsec_token": "XSEC_TOKEN",
  "load_more": false
}
```

响应：

```json
{
  "feeds": [],
  "count": 30,
  "totalLoaded": 30,
  "hasMore": true
}
```

说明：

- `load_more=false`：`feeds` 返回当前页面已加载的用户 Feed，通常是首屏。
- `load_more=true`：`feeds` 只返回本次加载新增的 Feed，避免重复回传历史数据。
- `totalLoaded` 是当前浏览器页面内累计已加载数量。
- `hasMore=false` 表示用户主页已触底或当前 tab 无更多内容。
- 该接口不是分页查询，不提供 `page/page_size`。

## 互动类

### `POST /xhs/post-comment`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "feed_id": "FEED_ID",
  "xsec_token": "XSEC_TOKEN",
  "content": "评论内容"
}
```

### `POST /xhs/reply-comment`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "feed_id": "FEED_ID",
  "xsec_token": "XSEC_TOKEN",
  "content": "回复内容",
  "comment_id": "COMMENT_ID",
  "user_id": ""
}
```

### `POST /xhs/like-feed`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "feed_id": "FEED_ID",
  "xsec_token": "XSEC_TOKEN",
  "unlike": false
}
```

### `POST /xhs/favorite-feed`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "feed_id": "FEED_ID",
  "xsec_token": "XSEC_TOKEN",
  "unfavorite": false
}
```

## 发布类

说明：

- 发布类接口直接收业务字段，不再要求 `title_file` / `content_file`
- `images` / `video` 支持 HTTP(S) URL
- 如传本地路径，当前 `/xhs/*` 接口统一按远端模式处理，需要已配置临时资源服务

### `POST /xhs/publish`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "title": "标题",
  "content": "正文",
  "images": ["https://example.com/a.jpg"],
  "tags": ["标签1", "标签2"],
  "schedule_at": "",
  "original": false,
  "visibility": ""
}
```

### `POST /xhs/fill-publish`

与 `/xhs/publish` 请求体相同，但只填表单不发布。

### `POST /xhs/fill-publish-video`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "title": "标题",
  "content": "正文",
  "video": "https://example.com/a.mp4",
  "tags": ["标签1"],
  "schedule_at": "",
  "visibility": ""
}
```

### `POST /xhs/publish-video`

与 `/xhs/fill-publish-video` 请求体相同，但会直接发布。

### `POST /xhs/click-publish`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token"
}
```

### `POST /xhs/save-draft`

保存当前页面内容到草稿箱。

### `POST /xhs/long-article`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "title": "标题",
  "content": "正文",
  "images": ["https://example.com/a.jpg"]
}
```

### `POST /xhs/select-template`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "name": "模板名"
}
```

### `POST /xhs/next-step`

```json
{
  "session_id": "session-xxx",
  "token": "bridge-token",
  "content": "发布描述"
}
```

## 返回结构

业务接口优先复用现有 CLI 输出结构：

- 搜索：`feeds` + `count`
- 详情：返回完整详情对象
- 互动：返回 `success` / 点赞收藏结果
- 发布：返回 `success` + `status`

## 设计边界

- `/bridge/*` 只负责底层转发与 session 管理
- `/xhs/*` 只负责小红书业务语义
- 两层前缀绝对分离，不混用 `method + params` 风格
