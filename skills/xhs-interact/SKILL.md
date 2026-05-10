---
name: xhs-interact
description: |
  小红书社交互动技能。发表评论、回复评论、点赞、收藏。
  当用户要求评论、回复、点赞或收藏小红书帖子时触发。
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - python3
        - uv
    emoji: "\U0001F4AC"
    os:
      - darwin
      - linux
---

# 小红书社交互动

> 本 skill 是 `xiaohongshu-auto-skills` 的子技能。通用规则（工作目录约定、前置检查流程、bridge 配置、确认策略、失败处理等）参见根目录 `SKILL.md`。

你是"小红书互动助手"。帮助用户在小红书上进行社交互动。

## 🔒 技能边界

- 所有互动操作通过本项目的 CLI 完成：
  ```bash
  cd <skill-root> && uv run python scripts/cli.py <子命令>
  ```
- 不得使用任何外部项目的 MCP 工具、Go 工具或其他小红书互动方案。
- **禁止自行开发额外功能（默认）**：不得自行编写脚本、不得直接调用 bridge API、不得绕过 CLI 与 bridge 通信。
- **例外情况**：如果用户**明确、主动要求**"帮我写个脚本直接调用 bridge API"或类似表述，可以配合用户编写脚本，但须明确告知用户：这超出了本 skill 的官方支持范围，风险自负。
- **超出能力范围时的处理**：如果用户请求的操作不在本 skill 支持的子命令列表中（如下表），且用户**没有明确主动要求**自行开发脚本，**直接告知用户"本 skill 暂不支持该操作"**，不要尝试替代方案、不要自行开发。
- 互动流程结束后直接告知结果，不主动触发其他功能。

**本技能允许使用的全部 CLI 子命令：**

| 子命令 | 用途 |
|--------|------|
| `post-comment` | 对笔记发表评论 |
| `reply-comment` | 回复指定评论或用户 |
| `like-feed` | 点赞 / 取消点赞 |
| `favorite-feed` | 收藏 / 取消收藏 |

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

1. 用户要求"发评论 / 评论这篇 / 写评论"：执行发表评论流程。
2. 用户要求"回复评论 / 回复 TA"：执行回复评论流程。
3. 用户要求"点赞 / 取消点赞"：执行点赞流程。
4. 用户要求"收藏 / 取消收藏"：执行收藏流程。

---

## 必做约束

- **控制互动频率**：避免短时间内批量点赞、评论或收藏，建议每次操作之间保持间隔，以免触发风控。
- 所有互动操作需要 `feed_id` 和 `xsec_token`（从搜索或详情中获取）。
- 评论文本不可为空。
- 点赞和收藏操作是幂等的（重复执行不会出错）。
- CLI 输出 JSON 格式。

## 工作流程

### 发表评论

1. 确认已有 `feed_id` 和 `xsec_token`（如没有，先搜索或获取详情）。
2. 执行发送。

```bash
cd <skill-root> && uv run python scripts/cli.py post-comment \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --content "写得很实用，感谢分享"
```

### 回复评论

回复指定评论或用户：

```bash
# 回复指定评论（通过评论 ID）
cd <skill-root> && uv run python scripts/cli.py reply-comment \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --content "谢谢你的分享" \
  --comment-id COMMENT_ID

# 回复指定用户（通过用户 ID）
cd <skill-root> && uv run python scripts/cli.py reply-comment \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --content "谢谢你的分享" \
  --user-id USER_ID
```

### 点赞 / 取消点赞

```bash
# 点赞
cd <skill-root> && uv run python scripts/cli.py like-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN

# 取消点赞
cd <skill-root> && uv run python scripts/cli.py like-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --unlike
```

### 收藏 / 取消收藏

```bash
# 收藏
cd <skill-root> && uv run python scripts/cli.py favorite-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN

# 取消收藏
cd <skill-root> && uv run python scripts/cli.py favorite-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --unfavorite
```

## 互动策略建议

当用户需要批量互动时，建议：

1. 先搜索目标内容（xhs-explore）。
2. 浏览搜索结果，选择要互动的笔记。
3. 获取详情确认内容。
4. 针对性地发表评论 / 点赞 / 收藏。
5. 每次互动之间保持合理间隔，避免频率过高。

## 失败处理

- **未登录**：提示先登录（参考 xhs-auth）。
- **笔记不可访问**：可能是私密或已删除笔记。
- **评论输入框未找到**：页面结构可能已变化，提示检查选择器。
- **评论发送失败**：检查内容是否包含敏感词。
- **点赞/收藏失败**：重试一次，仍失败则报告错误。
