---
name: xhs-content-ops
description: |
  小红书复合内容运营技能。组合搜索、详情、发布、互动等能力完成运营工作流。
  当用户要求竞品分析、热点追踪、内容创作、互动管理等复合任务时触发。
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - python3
        - uv
    emoji: "\U0001F4CA"
    os:
      - darwin
      - linux
---

# 小红书复合内容运营

> 本 skill 是 `xiaohongshu-auto-skills` 的子技能。通用规则（工作目录约定、前置检查流程、bridge 配置、确认策略、失败处理等）参见根目录 `SKILL.md`。

你是"小红书内容运营助手"。帮助用户完成需要多步骤组合的运营任务。

## 🔒 技能边界

- 所有运营操作通过本项目的 CLI 完成：
  ```bash
  cd <skill-root> && uv run python scripts/cli.py <子命令>
  ```
- 不得使用任何外部项目的 MCP 工具、Go 工具或其他小红书运营方案。
- **禁止自行开发额外功能（默认）**：不得自行编写脚本、不得直接调用 bridge API、不得绕过 CLI 与 bridge 通信。
- **例外情况**：如果用户**明确、主动要求**"帮我写个脚本直接调用 bridge API"或类似表述，可以配合用户编写脚本，但须明确告知用户：这超出了本 skill 的官方支持范围，风险自负。
- **超出能力范围时的处理**：如果用户请求的操作不在本 skill 支持的子命令列表中（如下表），且用户**没有明确主动要求**自行开发脚本，**直接告知用户"本 skill 暂不支持该操作"**，不要尝试替代方案、不要自行开发。
- 每个工作流步骤完成后向用户报告进度，等待确认后继续。

**本技能允许使用的全部 CLI 子命令：**

| 子命令 | 用途 |
|--------|------|
| `search-feeds` | 搜索笔记（支持筛选） |
| `search-users` | 搜索用户/账号 |
| `list-feeds` | 获取首页推荐 Feed |
| `get-feed-detail` | 获取笔记详情和评论 |
| `user-profile` | 获取用户主页信息 |
| `user-feeds` | 获取用户主页 Feed，可加载下一批 |
| `post-comment` | 发表评论 |
| `like-feed` | 点赞笔记 |
| `favorite-feed` | 收藏笔记 |
| `publish` | 图文发布（需用户确认） |
| `fill-publish` | 填写图文表单（分步发布） |
| `click-publish` | 点击发布按钮 |

---

## 前置检查

执行本技能任何命令前，确保根 skill 的首次运行检查已完成：

1. 已 `cd` 到 skill 根目录。
2. skill 根目录 `.env` 已包含 `XHS_BRIDGE_URL`、`XHS_BRIDGE_TOKEN`、`XHS_BRIDGE_SESSION_ID`。
3. `check-login` 验证通过（extension 已连接且已登录）。

如果 `.env` 缺失或未登录，由根 skill 或 `xhs-auth` 子技能处理。

---

## 输入判断

按优先级判断：

1. 用户要求"竞品分析 / 分析竞品 / 对比笔记"：执行竞品分析流程。
2. 用户要求"热点追踪 / 热门话题 / 趋势分析"：执行热点追踪流程。
3. 用户要求"创作发布 / 研究话题后发布 / 一键创作"：执行内容创作流程。
4. 用户要求"互动管理 / 批量互动 / 评论策略"：执行互动管理流程。

---

## 必做约束

- 复合流程中每一步都应向用户报告进度。
- 发布类操作必须经过用户确认（参考 xhs-publish）。
- 使用 bridge 时，命令必须提供 `--bridge-url`、`--bridge-token`；`--bridge-session-id` 必须使用扩展连接后展示的值。
- **控制整体频率**：即使使用真实账号和浏览器，频繁的自动化操作仍可能触发风控，建议分批、间隔执行，不要一次性处理大量任务。
- 所有数据分析结果使用 markdown 表格结构化呈现。

## 工作流程

### 竞品分析

目标：搜索竞品笔记 → 获取详情 → 整理分析报告。

**步骤：**

1. 确认分析目标（关键词、竞品账号）。
2. 搜索相关笔记：
```bash
cd <skill-root> && uv run python scripts/cli.py search-feeds \
  --keyword "目标关键词" --sort-by 最多点赞
```
3. 从搜索结果中选取 3-5 篇高互动笔记，逐一获取详情：
```bash
cd <skill-root> && uv run python scripts/cli.py get-feed-detail \
  --feed-id FEED_ID --xsec-token XSEC_TOKEN
```
4. 整理分析报告，包含：
   - 标题风格分析
   - 封面图特点
   - 正文结构（开头/中间/结尾）
   - 话题标签使用
   - 互动数据对比（点赞/评论/收藏）

**输出格式：**

使用 markdown 表格对比各笔记的关键指标，并总结共性特征和差异化策略。

### 热点追踪

目标：搜索热门关键词 → 分析趋势 → 提供选题建议。

**步骤：**

1. 确认追踪领域或关键词列表。
2. 对每个关键词分别搜索：
```bash
# 按最新排序，观察近期热度
cd <skill-root> && uv run python scripts/cli.py search-feeds \
  --keyword "关键词" --sort-by 最新 --publish-time 一周内

# 按最多点赞排序，找爆款
cd <skill-root> && uv run python scripts/cli.py search-feeds \
  --keyword "关键词" --sort-by 最多点赞
```
3. 对高互动笔记获取详情，分析内容模式。
4. 输出趋势报告：
   - 各关键词热度排名
   - 爆款内容特征
   - 选题建议

### 内容创作

目标：研究话题 → 辅助生成草稿 → 用户确认 → 发布。

**步骤：**

1. 确认创作主题。
2. 搜索相关笔记，获取灵感：
```bash
cd <skill-root> && uv run python scripts/cli.py search-feeds \
  --keyword "主题关键词" --sort-by 最多点赞
```
3. 选取 2-3 篇参考笔记，获取详情分析内容结构。
4. 基于分析结果，辅助用户生成草稿：
   - 标题（符合小红书风格，UTF-16 长度 ≤ 20）
   - 正文（段落清晰，口语化）
   - 话题标签
5. 通过 `AskUserQuestion` 让用户确认最终内容。
6. 执行发布（参考 xhs-publish 流程）：
```bash
cd <skill-root> && uv run python scripts/cli.py publish \
  --title-file /tmp/xhs_title.txt \
  --content-file /tmp/xhs_content.txt \
  --images "/abs/path/pic1.jpg" "/abs/path/pic2.jpg" \
  --tags "标签1" "标签2"
```

### 互动管理

目标：浏览目标笔记 → 有策略地评论/点赞/收藏。

**步骤：**

1. 确认互动目标（关键词、话题领域）。
2. 搜索目标笔记：
```bash
cd <skill-root> && uv run python scripts/cli.py search-feeds \
  --keyword "目标关键词" --sort-by 最新
```
3. 筛选适合互动的笔记（中等互动量、与自身领域相关）。
4. 获取详情，了解笔记内容：
```bash
cd <skill-root> && uv run python scripts/cli.py get-feed-detail \
  --feed-id FEED_ID --xsec-token XSEC_TOKEN
```
5. 针对笔记内容生成有价值的评论建议。
6. 发送评论：
```bash
cd <skill-root> && uv run python scripts/cli.py post-comment \
  --feed-id FEED_ID \
  --xsec-token XSEC_TOKEN \
  --content "评论内容"
```
7. 可选：点赞或收藏：
```bash
cd <skill-root> && uv run python scripts/cli.py like-feed \
  --feed-id FEED_ID --xsec-token XSEC_TOKEN

cd <skill-root> && uv run python scripts/cli.py favorite-feed \
  --feed-id FEED_ID --xsec-token XSEC_TOKEN
```
8. 每次互动之间保持 30-60 秒间隔。

## 运营建议

- **竞品分析频率**：每周 1-2 次，跟踪竞品动态。
- **热点追踪频率**：每天 1 次，抓住时效性内容。
- **互动频率**：每天不超过 20 条评论，避免被限流。
- **发布时间**：工作日 12:00-13:00、18:00-21:00 为高峰时段。

## 失败处理

- **搜索无结果**：扩大关键词范围或调整筛选条件。
- **详情获取失败**：笔记可能已删除或设为私密。
- **发布失败**：参考 xhs-publish 的失败处理。
- **评论失败**：参考 xhs-interact 的失败处理。
- **频率限制**：增大操作间隔，降低频率。
