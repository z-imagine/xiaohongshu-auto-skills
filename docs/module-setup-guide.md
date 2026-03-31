# 模块搭建与安装指南

本文说明当前项目在新架构下的模块搭建方式，包括 bridge、CLI、extension 和临时资源服务。

## 1. 模块拆分

当前系统建议按以下模块理解和部署：

1. `bridge/`
   - 中心 WebSocket 路由服务
   - 负责 CLI 与浏览器 extension 的会话转发

2. `scripts/cli.py`
   - Skill 与 Agent 唯一执行入口
   - 搜索、登录、发布、互动全部走 CLI

3. `extension/`
   - 用户浏览器中的 Chrome 扩展
   - 负责操作小红书页面，并维持登录态

4. 临时资源服务
   - 图文、视频、长文插图在远端 bridge 场景下的媒体分发服务
   - 本地文件会先上传到这里，再由 extension 使用 URL 拉取

## 2. 前置依赖

### 服务端 / 开发机

- Python `>= 3.11`
- `uv`
- 能访问 bridge 地址
- 能访问临时资源服务地址

### 用户浏览器机器

- Google Chrome
- 已安装本项目的 `extension/`
- 能访问 bridge 地址
- 能访问临时资源 URL
- 已登录小红书

## 3. 安装项目

```bash
git clone <repo>
cd xiaohongshu-auto-skills
uv sync
```

建议基本校验：

```bash
uv run pytest
python3 -m compileall bridge scripts tests
```

## 4. bridge 模块安装与启动

bridge 正式入口：

```bash
uv run python -m bridge.server --host 0.0.0.0 --port 9333 --token "<bridge-token>"
```

Docker 入口：

```bash
docker compose up -d --build
```

远端部署脚本：

```bash
cp .env.example .env
# 编辑本地 .env，填入 DEPLOY_*
./deploy_bridge_docker.sh
```

兼容入口：

```bash
uv run python scripts/bridge_server.py --host 0.0.0.0 --port 9333 --token "<bridge-token>"
```

### 推荐部署方式

- 外层使用 Nginx / Caddy 做 WebSocket 反向代理
- 对外暴露时优先使用 `wss://`
- 每个环境使用单独 token

### Docker 部署

项目根目录已提供：

- `Dockerfile`
- `docker-compose.yml`

最小启动方式：

```bash
docker compose up -d --build
```

如果你本地有 `ssh` / `scp`，也可以直接用仓库自带脚本打包上传并远端启动：

```bash
cp .env.example .env
# 编辑本地 .env，填入 DEPLOY_*
./deploy_bridge_docker.sh
```

远端目录结构约定为：

- `DEPLOY_REMOTE_DIR/runtime`：当前运行目录
- `DEPLOY_REMOTE_DIR/backups`：每次部署前的代码备份目录

脚本在二次部署时会先把当前 `runtime` 目录压缩到 `backups/runtime-时间戳.tar.gz`，再清空 `runtime` 并解压新包。

查看日志：

```bash
docker compose logs -f xhs-bridge
```

停止：

```bash
docker compose down
```

当前 Docker 方式下，bridge 运行配置以远端 [docker-compose.yml](/Users/samuel/Projects/SkillProjects/xiaohongshu-auto-skills/docker-compose.yml) 为准。

## 5. extension 安装与配置

### 安装

1. 打开 `chrome://extensions/`
2. 开启开发者模式
3. 选择“加载已解压的扩展程序”
4. 选择项目里的 `extension/` 目录

### 配置

点击浏览器工具栏里的扩展图标，在 popup 中填写：

- `Bridge URL`
- `Bridge Token`
- 保存后等待扩展连接 bridge，bridge 会自动分配并展示 `Session ID`
- 如需排障，也可打开扩展详情页中的 options 页面查看相同状态

### 推荐规则

- `Bridge URL` 和 `Bridge Token` 为必填项
- 每个用户浏览器连接成功后会获得唯一 `session_id`
- CLI 传入的 `--bridge-session-id` 必须使用扩展页面当前展示的值

## 6. CLI / Skill 调用配置

所有 CLI 子命令都支持：

```bash
--bridge-url
--bridge-session-id
--bridge-token
```

示例：

```bash
python scripts/cli.py check-login \
  --bridge-url wss://bridge.example.com/ws \
  --bridge-session-id <SESSION_ID_FROM_EXTENSION> \
  --bridge-token "<bridge-token>"
```

也可以统一使用环境变量：

```bash
export XHS_BRIDGE_URL=wss://bridge.example.com/ws
export XHS_BRIDGE_SESSION_ID=<SESSION_ID_FROM_EXTENSION>
export XHS_BRIDGE_TOKEN=<bridge-token>
```

## 7. 临时资源服务接入

远端 bridge 场景下，图文、视频和长文插图依赖临时资源服务。

### CLI 读取的环境变量

```bash
export XHS_ASSET_UPLOAD_ENDPOINT=https://asset.example.com/upload
export XHS_ASSET_UPLOAD_TOKEN=<asset-token>
export XHS_ASSET_UPLOAD_TIMEOUT=120
```

### 返回结构要求

上传本地文件后，服务端响应中至少要包含以下字段之一：

- `asset.url`
- `asset.download_url`
- `asset.signed_url`

或直接平铺：

```json
{
  "url": "https://asset.example.com/tmp/abc.jpg?sign=...",
  "name": "abc.jpg",
  "type": "image/jpeg",
  "size": 123456,
  "sha256": "..."
}
```

## 8. 登录与发布链路

### 登录

登录始终发生在用户自己的浏览器中：

1. CLI 发出登录命令
2. bridge 按 `session_id` 路由
3. extension 在用户浏览器里打开并操作小红书页面

其中 `session_id` 由扩展首次连接 bridge 后自动获取，用户将该值填入 OpenClaw 或 CLI。

### 图文 / 视频发布

远端 bridge 模式下：

- 直接传 HTTP/HTTPS 媒体 URL 最简单
- 如果用户提供本地路径，则 CLI 会先上传到临时资源服务，再由 extension 拉取 URL

### 长文插图

长文插图已支持 URL 资源，不再只依赖 `file://`

## 9. 推荐联调顺序

1. 启动 bridge
2. 配置并连接 extension
3. `check-login`
4. `search-feeds`
5. 图文 URL 发布
6. 视频 URL 发布
7. 长文插图链路

## 10. 当前已知外部依赖项

以下项仍需外部环境配合，不在仓库内闭环：

- 临时资源删除与生命周期治理
- 多用户并发压测
- 真实小红书页面下的视频与长文联调回归
