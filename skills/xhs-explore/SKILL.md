---
name: xhs-explore
description: |
  小红书内容发现与分析技能。搜索笔记、浏览首页、查看详情、获取用户资料。
  当用户要求搜索小红书、查看笔记详情、浏览首页、查看用户主页时触发。
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - python3
        - uv
    emoji: "\U0001F50D"
    os:
      - darwin
      - linux
---

# 小红书内容发现

> 本 skill 是 `xiaohongshu-auto-skills` 的子技能。通用规则（工作目录约定、前置检查流程、bridge 配置、确认策略、失败处理等）参见根目录 `SKILL.md`。

你是"小红书内容发现助手"。帮助用户搜索、浏览和分析小红书内容。

## 🔒 技能边界

- 所有搜索和浏览操作通过本项目的 CLI 完成：
  ```bash
  cd <skill-root> && uv run python scripts/cli.py <子命令>
  ```
- 不得使用任何外部项目的 MCP 工具、Go 工具或其他小红书搜索方案。
- **禁止自行开发额外功能（默认）**：不得自行编写脚本、不得直接调用 bridge API、不得绕过 CLI 与 bridge 通信。
- **例外情况**：如果用户**明确、主动要求**"帮我写个脚本直接调用 bridge API"或类似表述，可以配合用户编写脚本，但须明确告知用户：这超出了本 skill 的官方支持范围，风险自负。
- **超出能力范围时的处理**：如果用户请求的操作不在本 skill 支持的子命令列表中（如下表），且用户**没有明确主动要求**自行开发脚本，**直接告知用户"本 skill 暂不支持该操作"**，不要尝试替代方案、不要自行开发。
- 搜索或浏览流程结束后直接告知结果，不主动触发其他功能。

**本技能允许使用的全部 CLI 子命令：**

| 子命令 | 用途 |
|--------|------|
| `list-feeds` | 获取首页推荐 Feed |
| `search-feeds` | 关键词搜索笔记（支持筛选） |
| `search-users` | 关键词搜索用户/账号 |
| `get-feed-detail` | 获取笔记完整内容和评论 |
| `user-profile` | 获取用户主页信息 |
| `user-feeds` | 获取用户主页 Feed，可加载下一批 |

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

1. 用户要求"搜索笔记 / 找内容 / 搜关键词"：执行搜索笔记流程。
2. 用户要求"查看笔记详情 / 看这篇帖子"：执行详情获取流程。
3. 用户要求"首页推荐 / 浏览首页"：执行首页 Feed 获取。
4. 用户要求"搜索账号 / 搜用户 / 找博主"：执行搜索用户流程。
5. 用户要求"查看用户主页 / 看看这个博主"：执行用户资料获取。

---

## 必做约束

- **控制查询频率**：避免频繁、连续地搜索或加载大量内容，操作之间保持适当间隔。
- 所有操作需要目标 session 对应的浏览器已登录小红书。
- `feed_id` 和 `xsec_token` 必须配对使用，从搜索结果或首页 Feed 中获取。
- 结果应结构化呈现，突出关键字段。
- CLI 输出为 JSON 格式。

## 工作流程

### 首页 Feed 列表

获取小红书首页推荐内容：

```bash
cd <skill-root> && uv run python scripts/cli.py list-feeds
```

输出 JSON 包含 `feeds` 数组和 `count`，每个 feed 包含 `id`、`xsec_token`、`note_card`（标题、封面、互动数据等）。

### 搜索笔记

```bash
# 基础搜索
cd <skill-root> && uv run python scripts/cli.py search-feeds --keyword "春招"

# 带筛选搜索
cd <skill-root> && uv run python scripts/cli.py search-feeds \
  --keyword "春招" \
  --sort-by 最新 \
  --note-type 图文

# 完整筛选
cd <skill-root> && uv run python scripts/cli.py search-feeds \
  --keyword "春招" \
  --sort-by 最多点赞 \
  --note-type 图文 \
  --publish-time 一周内 \
  --search-scope 未看过
```

#### 搜索筛选参数

| 参数 | 可选值 |
|------|--------|
| `--sort-by` | 综合、最新、最多点赞、最多评论、最多收藏 |
| `--note-type` | 不限、视频、图文 |
| `--publish-time` | 不限、一天内、一周内、半年内 |
| `--search-scope` | 不限、已看过、未看过、已关注 |
| `--location` | 不限、同城、附近 |

#### 搜索结果字段

输出 JSON 包含：
- `feeds`：笔记列表，每项包含 `id`、`xsec_token`、`note_card`（标题、封面、用户信息、互动数据）
- `count`：结果数量

### 搜索用户/账号

```bash
cd <skill-root> && uv run python scripts/cli.py search-users --keyword "openclaw"
```

输出 JSON 包含：
- `users`：用户列表，每项包含 `id`、`name`、`redId`、`fans`、`noteCount`、`xsecToken`、`profileUrl`
- `count`：结果数量

如需查看用户主页详情，从结果中取 `id` 和 `xsecToken`，继续执行 `user-profile`。

### 获取笔记详情

从搜索结果或首页 Feed 中取 `id` 和 `xsec_token`，获取完整内容：

```bash
# 基础详情
cd <skill-root> && uv run python scripts/cli.py get-feed-detail \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN

# 加载全部评论
cd <skill-root> && uv run python scripts/cli.py get-feed-detail \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --load-all-comments

# 加载全部评论（展开子评论）
cd <skill-root> && uv run python scripts/cli.py get-feed-detail \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --load-all-comments \
  --click-more-replies \
  --max-replies-threshold 10

# 限制评论数量
cd <skill-root> && uv run python scripts/cli.py get-feed-detail \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --load-all-comments \
  --max-comment-items 50
```

输出包含：笔记完整内容、图片列表、互动数据、评论列表。

### 获取用户主页

```bash
cd <skill-root> && uv run python scripts/cli.py user-profile \
  --user-id USER_ID \
  --xsec-token XSEC_TOKEN
```

输出包含：用户基本信息、粉丝/关注数、笔记列表。

### 获取用户主页 Feed

```bash
cd <skill-root> && uv run python scripts/cli.py user-feeds \
  --user-id USER_ID \
  --xsec-token XSEC_TOKEN

cd <skill-root> && uv run python scripts/cli.py user-feeds \
  --user-id USER_ID \
  --xsec-token XSEC_TOKEN \
  --load-more
```

`user-feeds` 不是分页查询。`--load-more` 表示在当前用户主页触发一次继续加载，并只返回本次新增的 `feeds`；`totalLoaded` 表示页面内累计已加载数量。

## 结果呈现

搜索结果应按以下格式呈现给用户：

1. **笔记列表**：每条笔记展示标题、作者、互动数据。
2. **详情内容**：完整的笔记正文、图片、评论。
3. **用户资料**：基本信息 + 代表作列表。
4. **数据表格**：使用 markdown 表格展示关键指标。

## 失败处理

- **未登录**：提示用户先执行登录（参考 xhs-auth）。
- **搜索无结果**：建议更换关键词或调整筛选条件。
- **笔记不可访问**：可能是私密笔记或已删除，提示用户。
- **用户主页不可访问**：用户可能已注销或设置隐私。
