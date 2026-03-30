# Bridge Centralization + OSS Media Upload 改造方案

## 1. 背景与目标

当前项目的核心能力已经建立在 `bridge + browser extension` 之上，但发布链路仍然依赖“CLI 所在机器与浏览器所在机器是同一台”的前提：

- 搜索、详情、评论、点赞、收藏、登录这类无媒体文件操作，本质上只需要远程控制浏览器。
- 图文/视频/长文插图发布，当前仍然依赖本地文件路径，无法支持“OpenClaw/bridge 在中心服务端，浏览器在用户自己的电脑”。

本次改造目标：

1. 将 bridge 服务从本地模式升级为中心化部署模式。
2. 保留“用户各自在自己的浏览器中登录小红书”的使用方式。
3. 将发布媒体交付方式从“本地文件路径”改为“临时 OSS URL”。
4. 让 extension 在用户机器上自行拉取媒体内容，再构造浏览器可上传的 `File` 对象。
5. 在不重写现有业务模块的前提下，尽量复用 `BridgePage` 抽象和现有页面自动化逻辑。

非目标：

- 不改动当前搜索、互动、详情等业务逻辑的核心实现。
- 不引入浏览器原生客户端或本地守护进程。
- 不追求首版支持多浏览器标签协同，一个 session 对应一个活动浏览器即可。

## 2. 当前问题总结

### 2.1 当前架构

当前链路为：

`OpenClaw/CLI -> BridgePage -> bridge_server.py -> extension/background.js -> 用户本机 Chrome`

其中媒体上传走的是本地路径：

`CLI 读取本地文件 -> page.set_file_input(path) -> extension 使用 DOM.setFileInputFiles(path)`

这导致两个限制：

1. 浏览器如果不在 CLI 同一台机器，路径失效。
2. bridge 无法被中心化复用，只能与本地浏览器强耦合。

### 2.2 当前协议问题

当前 bridge 协议只适合单机本地使用：

- 只有一个 `_extension_ws`
- 没有 `session_id`
- 没有鉴权
- 没有中心化配置
- extension 端 bridge 地址硬编码

### 2.3 当前发布问题

发布链路的关键问题不是 bridge 本身，而是媒体交付方式：

- 图文/视频上传依赖本地文件路径
- 长文插图依赖 `file://` 路径
- 这两种方式都无法跨机器

## 3. 目标架构

改造后的目标链路：

`OpenClaw -> CLI/服务端逻辑 -> Central Bridge -> 用户浏览器 Extension -> 小红书页面`

媒体上传链路：

`OpenClaw/服务端 -> 上传媒体到 OSS -> 生成临时签名 URL -> 通过 bridge 下发 URL -> extension 拉取 URL -> 构造 File -> 页面上传 -> 发布成功后异步清理 OSS`

### 3.1 关键设计原则

1. bridge 只传控制命令和元数据，不传大文件 bytes。
2. 媒体内容通过 OSS 分发，不通过 WebSocket 透传。
3. extension 负责在用户机器侧下载媒体。
4. 页面上传仍然发生在用户浏览器里，保留真实登录态和真实浏览器环境。
5. 旧业务模块尽量不感知 bridge 是否中心化。

## 4. 核心改造点

## 4.1 Bridge 服务中心化

### 目标

将 `scripts/bridge_server.py` 从单连接本地 router 升级为可部署的中心 bridge。

### 改造内容

1. 引入 `session_id`
   - 每个用户浏览器连接时携带 `session_id`
   - CLI 发命令时也必须携带 `session_id`
   - bridge 按 `session_id` 进行路由

2. 引入鉴权
   - 建议最小实现：`bridge_token`
   - extension 握手和 CLI 请求都带 token
   - bridge 校验 token 后才允许接入

3. 支持多 extension 会话
   - `session_id -> extension_ws`
   - `request_id -> future`
   - 每个 session 独立管理在线状态

4. 支持中心化部署
   - 服务监听 `0.0.0.0`
   - 外层通过 Nginx / Caddy 暴露 `wss://`
   - 禁止直接暴露裸 `ws://` 到公网

### 建议数据结构

```python
extension_connections: dict[str, ServerConnection]
pending_requests: dict[str, asyncio.Future]
session_meta: dict[str, SessionState]
```

其中：

- `SessionState` 记录 `session_id`、最后心跳时间、extension 版本、最近错误等

## 4.2 Extension 配置化

### 目标

让 extension 能够连接任意指定 bridge 地址，而不是固定 `ws://localhost:9333`。

### 改造内容

1. 新增本地配置项
   - `bridge_url`
   - `session_id`
   - `bridge_token`

2. 增加配置 UI
   - 推荐实现一个简单的 options page
   - 用户首次安装后手动填写或扫码导入

3. background.js 启动时读取配置
   - 未配置时不自动连接
   - 配置完整后自动重连

4. 更新 manifest 权限
   - 加入 bridge 域名 host permissions
   - 如需直接拉取 OSS URL，也加入 OSS 域名权限

### 建议连接握手

extension 建立 WebSocket 后首包：

```json
{
  "role": "extension",
  "session_id": "user-123",
  "token": "bridge-token",
  "extension_version": "1.1.0"
}
```

CLI/服务端请求：

```json
{
  "role": "cli",
  "session_id": "user-123",
  "token": "bridge-token",
  "method": "navigate",
  "params": {
    "url": "https://www.xiaohongshu.com/"
  }
}
```

## 4.3 发布媒体协议升级

### 目标

将当前“本地文件路径上传”改为“OSS URL 上传”。

### 核心思路

服务端在发布前将图片或视频上传到临时 OSS，生成短时效签名 URL，并把如下元数据发给 extension：

```json
{
  "url": "https://oss.example.com/tmp/abc.jpg?sign=...",
  "name": "cover.jpg",
  "type": "image/jpeg",
  "size": 123456
}
```

extension 拿到 URL 后执行：

1. `fetch(url)`
2. `Blob/ArrayBuffer -> File`
3. `DataTransfer -> input.files`
4. 触发 `change/input/drop`

### 新增 bridge 命令

建议新增：

- `set_file_input_from_url`
- `set_multiple_files_from_url`
- `insert_image_from_url`（长文场景可选）

参数结构建议：

```json
{
  "selector": "input[type=file]",
  "files": [
    {
      "url": "https://...",
      "name": "1.jpg",
      "type": "image/jpeg",
      "size": 123456,
      "sha256": "..."
    }
  ]
}
```

### 为什么不用继续走 `DOM.setFileInputFiles`

因为该接口依赖浏览器所在机器上的本地路径，不适合中心化方案。

### 推荐实现方式

首版优先采用“在页面 MAIN world 中 `fetch + File + DataTransfer`”方案，而不是“下载到本地磁盘再上传”，原因：

- 不需要浏览器本地文件系统权限
- 不需要知道下载后的绝对路径
- 与现有 DOM 模拟上传实现兼容
- 已有代码中存在相近逻辑，可复用

## 4.4 OSS 临时文件管理

### 目标

保证媒体分发安全、可控、可清理。

### 要求

1. 使用短时效签名 URL
   - 推荐 10 到 30 分钟有效期

2. 文件上传使用临时命名空间
   - 如：`tmp/xhs-publish/{session_id}/{request_id}/...`

3. 发布完成后不立即删除
   - 使用异步延迟清理
   - 推荐保留 30 分钟到 2 小时

4. 增加兜底生命周期策略
   - OSS 桶策略自动清理超时对象

### 删除策略建议

- 发布成功：延迟清理
- 发布失败：延迟清理
- 用户取消：延迟清理
- 服务异常：依赖桶生命周期兜底

原因：

- 浏览器下载、页面预处理、上传重试都可能存在延迟
- “成功回执后立刻删除”容易删早

## 5. 代码改造范围

## 5.1 需要修改的文件

### bridge 服务端

- `scripts/bridge_server.py`
  - 支持 session 路由
  - 支持 token 鉴权
  - 支持多 extension
  - 支持更清晰的错误码和状态查询

### CLI / Bridge 客户端

- `scripts/xhs/bridge.py`
  - 请求带 `session_id` / `token`
  - 新增 URL 上传相关方法
  - 调整 `ping_server` 语义为按 session 查询

- `scripts/cli.py`
  - bridge 配置从默认本地模式改为可注入
  - 去除或降级“自动拉起本地 bridge server”逻辑
  - 去除或降级“自动打开本地 Chrome”逻辑

### extension

- `extension/manifest.json`
  - 调整 bridge / OSS 相关权限

- `extension/background.js`
  - 从 storage 读取配置
  - 建立中心 bridge 连接
  - 增加 `set_file_input_from_url`
  - 增加 session/token 握手
  - 增强连接状态和错误日志

- `extension/content.js`
  - 根据实现路径决定是否保留
  - 若主逻辑全部迁到 MAIN world，可进一步弱化或删除

### 发布业务

- `scripts/xhs/publish.py`
  - `_upload_images` 改为走 URL 上传

- `scripts/xhs/publish_video.py`
  - `_upload_video` 改为走 URL 上传

- `scripts/xhs/publish_long_article.py`
  - 图片插入方式从 `file://` 改为 URL/Blob 模式

- `scripts/image_downloader.py`
  - 职责需要重定义
  - 不再以“下载到 CLI 本地路径”为最终目标
  - 可以保留为“OSS 上传前的预处理模块”

## 5.2 尽量不改的文件

以下业务模块原则上不需要感知此次架构变化：

- `scripts/xhs/search.py`
- `scripts/xhs/feed_detail.py`
- `scripts/xhs/comment.py`
- `scripts/xhs/like_favorite.py`
- `scripts/xhs/feeds.py`
- `scripts/xhs/user_profile.py`
- `scripts/xhs/login.py`

这些模块继续通过 `page` 抽象调用浏览器能力即可。

## 6. 分阶段实施计划

## Phase 0: 方案预研

目标：

- 验证小红书发布页是否接受 `fetch(url) -> File -> input.files` 的方式
- 验证图片与视频都能稳定触发上传

任务：

1. 在 extension 中写一个最小实验命令
2. 针对图文上传页验证图片
3. 针对视频上传页验证视频
4. 验证长文编辑器插图可行性

产出：

- 技术结论
- 失败场景清单
- 最终上传方式定稿

## Phase 1: Bridge 中心化改造

目标：

- bridge 可部署到服务端
- extension 可配置远端连接
- 支持单用户单 session 闭环

任务：

1. bridge 增加 `session_id`
2. bridge 增加 `token`
3. extension 增加配置页
4. extension 使用配置连接远端 bridge
5. CLI 请求带 session 信息

验收：

- 用户浏览器可连远端 bridge
- 搜索、详情、评论、点赞、收藏、登录可用

## Phase 2: OSS 媒体协议改造

目标：

- 图文发布、视频发布、长文插图支持跨机器

任务：

1. 设计 OSS 临时对象规范
2. 服务端增加媒体上传到 OSS 的逻辑
3. `BridgePage` 增加 URL 上传能力
4. extension 增加 URL -> File -> input.files 能力
5. 发布模块改造为使用 URL 上传

验收：

- 图文发布可用
- 视频发布可用
- 长文插图可用

## Phase 3: 多用户与运维完善

目标：

- 支持多用户并发接入
- 降低生产运维风险

任务：

1. session 生命周期管理
2. 在线状态管理
3. 日志与审计
4. 错误码规范
5. OSS 清理任务
6. 连接超时和重试策略

验收：

- 多个用户可同时在线
- 命令路由无串线
- 临时对象无长期堆积

## 7. 推荐任务拆分

建议按以下顺序拆研发任务：

1. 扩展配置化
2. bridge session 化
3. CLI 透传 session/token
4. 上传协议 PoC
5. 图文发布改造
6. 视频发布改造
7. 长文插图改造
8. OSS 生命周期治理
9. 多用户并发支持

## 8. 技术风险与应对

### 风险 1：页面不接受合成的 FileList

现象：

- 页面不响应 `input.files` 赋值
- 上传区域只认真实拖拽

应对：

- 同时保留 `change/input/drop` 三种触发路径
- 优先复用现有拖拽模拟逻辑
- 必要时补充更贴近真实交互的事件序列

### 风险 2：大视频内存压力过高

现象：

- 浏览器进程内存升高
- 下载或构造 `Blob` 时卡顿

应对：

- 首版限制最大视频体积
- 使用短时 URL，避免 base64
- 对视频发布单独增加更严格的超时和错误提示

### 风险 3：OSS CORS 或访问权限问题

现象：

- URL 能打开但 `fetch` 失败
- 浏览器控制台报 CORS 错误

应对：

- 提前配置 OSS CORS
- 使用签名 URL
- 统一返回标准 `Content-Type`

### 风险 4：多用户串线

现象：

- 一个用户命令打到另一用户浏览器

应对：

- session 路由强制化
- token 与 session 绑定
- bridge 不允许匿名连接

## 9. 测试计划

### 9.1 功能测试

1. 单用户远端桥接登录
2. 搜索结果获取
3. 笔记详情获取
4. 点赞/收藏/评论
5. 图文发布
6. 视频发布
7. 长文插图与模板流程

### 9.2 稳定性测试

1. extension 断线重连
2. bridge 重启后恢复
3. OSS URL 过期后的错误提示
4. 大文件上传超时
5. 多 session 并发

### 9.3 安全测试

1. 无 token 连接被拒绝
2. 错误 session 无法操作他人浏览器
3. OSS 临时对象按时清理

## 10. 里程碑建议

### M1

- 远端 bridge 可连接
- 单 session 搜索/互动闭环

### M2

- 图文发布跨机器闭环

### M3

- 视频发布与长文插图闭环

### M4

- 多用户并发和生产运维能力完善

## 11. 最终建议

首版务必先做一个小范围闭环，而不是一次性重写所有发布逻辑。

推荐优先级：

1. 先完成 bridge 中心化和 extension 配置化。
2. 用最小 PoC 验证“URL -> File -> input.files”是否能稳定驱动小红书上传。
3. PoC 通过后，再改图文发布。
4. 视频和长文单独处理，不要和图文混在一个迭代里。

这条路线的关键价值在于：

- bridge 可以中心化部署
- 用户仍使用自己的浏览器和自己的登录态
- 上传问题不再依赖本地路径
- 现有绝大多数业务模块可以继续复用
