# Bridge + OSS 改造开发任务表

本文用于后续开发跟踪，配套设计文档见 [bridge-oss-migration-plan.md](/Users/samuel/Projects/SkillProjects/xiaohongshu-auto-skills/docs/bridge-oss-migration-plan.md)。

## 使用说明

- `状态` 建议使用：`todo` / `doing` / `blocked` / `done`
- `优先级` 建议使用：`P0` / `P1` / `P2`
- `负责人`、`计划时间`、`实际完成时间` 可在执行时补充
- 每个阶段结束前，必须完成对应的验收项

## 目标目录调整

本次改造要求将 bridge server 从 `scripts/` 中拆出，避免继续与 CLI 和业务脚本混放。

建议目标结构：

```text
xiaohongshu-auto-skills/
├── bridge/
│   ├── __init__.py
│   ├── server.py
│   ├── auth.py
│   ├── config.py
│   ├── router.py
│   ├── session_store.py
│   └── types.py
├── extension/
├── scripts/
│   ├── cli.py
│   └── xhs/
└── docs/
```

目录职责约束：

- `bridge/` 只放中心 bridge 服务端代码
- `scripts/` 只保留 CLI、业务编排和页面自动化逻辑
- extension 不直接依赖 `scripts/bridge_server.py` 这类旧路径

## 阶段总览

| 阶段 | 目标 | 验收结果 |
| --- | --- | --- |
| Phase 0 | 明确协议和目录拆分方案，完成上传方式 PoC | 图片 URL 上传 PoC 可跑通 |
| Phase 1 | bridge 中心化、extension 配置化、单 session 闭环 | 搜索/互动/登录可远程运行 |
| Phase 2 | 图文发布改造为 OSS URL 上传 | 图文发布跨机器可用 |
| Phase 3 | 视频发布和长文插图改造 | 视频/长文发布跨机器可用 |
| Phase 4 | 多用户、运维和稳定性完善 | 支持并发、多 session 和线上治理 |

## Phase 0: 预研与目录拆分设计

### 阶段目标

- 确认 bridge 拆目录后的代码边界
- 验证 `URL -> Blob -> File -> input.files` 是否能驱动小红书上传
- 确定首版协议字段

### 任务表

| ID | 优先级 | 任务 | 说明 | 依赖 | 产出 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| P0-01 | P0 | 梳理 bridge 代码边界 | 识别 `scripts/bridge_server.py` 中可迁出的模块 | 无 | bridge 模块边界说明 | done |
| P0-02 | P0 | 设计 bridge 新目录结构 | 明确 `bridge/` 下文件划分和职责 | P0-01 | 目录结构草案 | done |
| P0-03 | P0 | 设计 session/token 协议 | 定义 extension 握手和 CLI 请求公共字段 | P0-01 | 协议草案 | done |
| P0-04 | P0 | 图片上传 PoC | 验证 extension 能否从 OSS URL 拉图并构造 `File` | P0-03 | PoC 结论 | todo |
| P0-05 | P0 | 视频上传 PoC | 验证视频 URL 拉取和上传可行性 | P0-03 | PoC 结论 | todo |
| P0-06 | P1 | 长文插图 PoC | 验证长文图片插入是否需单独协议 | P0-04 | PoC 结论 | todo |
| P0-07 | P1 | OSS 临时对象规范设计 | 命名、过期、清理策略、签名 URL 时效 | P0-03 | OSS 规范文档 | todo |

### 阶段验收

- bridge 目录拆分方案确定
- 图片上传 PoC 成功
- 发布上传协议字段定稿

## Phase 1: Bridge 中心化与单 Session 闭环

### 阶段目标

- bridge 从 `scripts/` 拆出
- extension 能配置并连接远端 bridge
- CLI 能通过 `session_id` 精确路由到目标浏览器
- 无媒体操作全链路可用

### 任务表

| ID | 优先级 | 任务 | 说明 | 依赖 | 产出 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| P1-01 | P0 | 新建 `bridge/` 目录 | 创建基础模块骨架和入口文件 | P0-02 | `bridge/` 基础结构 | done |
| P1-02 | P0 | 迁移旧 bridge server 代码 | 将 `scripts/bridge_server.py` 迁移到 `bridge/server.py` | P1-01 | 新 bridge 入口 | done |
| P1-03 | P0 | bridge 配置模块化 | 提取监听地址、端口、token、日志配置 | P1-02 | `bridge/config.py` | done |
| P1-04 | P0 | bridge 引入 session 路由 | 支持 `session_id -> extension_ws` | P0-03, P1-02 | 多 session 路由能力 | done |
| P1-05 | P0 | bridge 引入 token 鉴权 | 拒绝匿名或错误 token 连接 | P0-03, P1-02 | 鉴权能力 | done |
| P1-06 | P0 | bridge 状态查询接口改造 | `ping_server` 改为按 session 查询在线状态 | P1-04 | session 状态接口 | done |
| P1-07 | P0 | extension 配置存储实现 | 保存 `bridge_url` / `token`，并持久化 bridge 回传的 `session_id` | P0-03 | storage 读写能力 | done |
| P1-08 | P0 | extension 设置页实现 | 提供用户可配置 UI | P1-07 | options page | done |
| P1-09 | P0 | extension 改为远端连接 | 用配置项替代硬编码 `localhost` | P1-07 | 可配置连接能力 | done |
| P1-10 | P0 | extension 握手协议改造 | 首包带 session/token/version | P1-09, P1-05 | 新握手协议 | done |
| P1-11 | P0 | manifest 权限调整 | bridge 域名、必要权限补齐 | P1-09 | manifest 更新 | done |
| P1-12 | P0 | `BridgePage` 透传 session/token | 所有 CLI 请求带公共认证字段 | P1-04, P1-05 | `scripts/xhs/bridge.py` 改造 | done |
| P1-13 | P1 | CLI bridge 配置改造 | 支持从参数或环境变量注入 bridge 信息 | P1-12 | CLI 配置入口 | done |
| P1-14 | P1 | 去除本地自动拉起假设 | 远端模式下不再自动起本地 bridge/chrome | P1-13 | CLI 行为修正 | done |
| P1-15 | P0 | 单 session 集成测试 | 搜索、详情、评论、点赞、登录全链路验证 | P1-14 | 集成测试记录 | done |

### 阶段验收

- `scripts/bridge_server.py` 不再作为主入口
- bridge 可独立启动运行
- extension 可连接远端 bridge
- 无媒体操作全链路跑通

## Phase 2: 图文发布改造

### 阶段目标

- 图文发布脱离本地文件路径
- 服务端改为 OSS URL 下发
- extension 能从 URL 构造上传文件

### 任务表

| ID | 优先级 | 任务 | 说明 | 依赖 | 产出 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| P2-01 | P0 | 定义图文上传命令协议 | 确定 `set_file_input_from_url` 参数结构 | P0-04, P0-07 | 协议定稿 | done |
| P2-02 | P0 | extension 实现 URL 文件拉取 | `fetch -> Blob -> File -> DataTransfer` | P2-01 | URL 上传能力 | done |
| P2-03 | P0 | extension 实现多图上传 | 支持一次上传多图片 | P2-02 | 多图上传能力 | done |
| P2-04 | P0 | `BridgePage` 增加 URL 上传接口 | 增加新的 page 方法供发布模块调用 | P2-01 | bridge client 新接口 | done |
| P2-05 | P0 | 服务端 OSS 上传封装 | 发布前上传图片并生成签名 URL | P0-07 | OSS 上传模块 | done |
| P2-06 | P0 | `publish.py` 图文上传改造 | 从本地路径方案切换到 URL 方案 | P2-04, P2-05 | 图文发布新链路 | done |
| P2-07 | P1 | `image_downloader.py` 职责重构 | 从本地落盘导向改为上传前预处理导向 | P2-05 | 模块职责重定义 | done |
| P2-08 | P0 | 图文发布集成测试 | 单图、多图、URL 图片、失败回滚 | P2-06 | 测试记录 | done |
| P2-09 | P1 | OSS 延迟清理任务 | 发布后异步清理临时对象 | P2-05 | 清理任务 | blocked |

### 阶段验收

- 图文发布不再依赖用户本地绝对路径
- 用户浏览器在异地机器上也能完成图文发布

## Phase 3: 视频发布与长文插图改造

### 阶段目标

- 视频发布支持 OSS URL 上传
- 长文插图去掉 `file://` 依赖

### 任务表

| ID | 优先级 | 任务 | 说明 | 依赖 | 产出 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| P3-01 | P0 | 定义视频上传协议限制 | 确定视频大小、超时、失败提示策略 | P0-05, P2-01 | 视频上传约束说明 | done |
| P3-02 | P0 | extension 视频 URL 上传验证 | 验证大文件上传稳定性 | P3-01, P2-02 | 视频上传能力 | done |
| P3-03 | P0 | `publish_video.py` 改造 | 切换到 URL 上传链路 | P3-02, P2-04, P2-05 | 视频发布新链路 | done |
| P3-04 | P1 | 长文插图协议设计 | 定义 `insert_image_from_url` 或统一文件协议 | P0-06 | 长文协议设计 | done |
| P3-05 | P1 | 长文插图实现改造 | 去掉 `file://` 路径依赖 | P3-04, P2-02 | 长文图片插入新链路 | done |
| P3-06 | P0 | 视频发布集成测试 | 正常上传、超时、重试、清理验证 | P3-03 | 测试记录 | blocked |
| P3-07 | P1 | 长文流程集成测试 | 插图、模板、下一步、发布前验证 | P3-05 | 测试记录 | blocked |

### 阶段验收

- 视频发布跨机器可用
- 长文插图跨机器可用

## Phase 4: 多用户、运维与稳定性

### 阶段目标

- 支持中心 bridge 多 session 并发
- 补齐线上治理能力
- 降低串线、泄漏、清理失败风险

### 任务表

| ID | 优先级 | 任务 | 说明 | 依赖 | 产出 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| P4-01 | P0 | session 生命周期管理 | 在线、离线、重连、过期状态管理 | P1-04 | session 管理能力 | done |
| P4-02 | P0 | bridge 心跳与断线重连 | 增加心跳和掉线恢复策略 | P1-04, P1-09 | 连接稳定性增强 | done |
| P4-03 | P0 | 命令审计日志 | 记录 session、method、结果、耗时 | P1-05 | 审计日志 | done |
| P4-04 | P1 | 错误码规范化 | 统一 bridge、extension、CLI 错误语义 | P1-15, P2-08 | 错误码文档 | done |
| P4-05 | P1 | OSS 对象生命周期治理 | 桶级 TTL、异步清理、补偿机制 | P2-09 | 生命周期策略 | blocked |
| P4-06 | P1 | 多 session 并发测试 | 多用户同时搜索、互动、发布验证 | P4-01, P4-02, P3-06 | 压测与并发测试报告 | blocked |
| P4-07 | P1 | 安全测试 | 错 token、错 session、过期 URL 等场景验证 | P4-04, P4-05 | 安全测试记录 | blocked |
| P4-08 | P2 | 运维文档编写 | bridge 部署、extension 配置、排障说明 | P4-03 | 运维手册 | done |

### 阶段验收

- 中心 bridge 支持多用户并发连接
- 无明显串线风险
- 临时媒体对象可自动治理

## 里程碑建议

| 里程碑 | 范围 | 通过标准 |
| --- | --- | --- |
| M1 | Phase 0 + Phase 1 | bridge 远端化，单 session 搜索/互动可用 |
| M2 | Phase 2 | 图文发布跨机器可用 |
| M3 | Phase 3 | 视频和长文插图跨机器可用 |
| M4 | Phase 4 | 多用户并发和线上治理完成 |

## 建议开发顺序

1. 先做 bridge 目录拆分和协议定稿，不要一开始就改发布模块。
2. 先打通单 session 远端控制，再碰媒体上传。
3. 先完成图文发布，再做视频和长文。
4. 多用户并发和运维治理放在功能闭环之后。

## 执行时建议补充的字段

可以在每个任务后续补充以下字段用于项目管理：

| 字段 | 用途 |
| --- | --- |
| 负责人 | 明确任务归属 |
| 计划开始 | 排期 |
| 计划完成 | 排期 |
| 实际完成 | 复盘 |
| 风险 | 标记阻塞点 |
| 备注 | 记录方案变更 |
