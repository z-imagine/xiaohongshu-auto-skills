# CLI 集成测试计划

## 目的

验证当前客户端代码、远端 Bridge 与重新加载后的浏览器扩展能够协同工作，覆盖本次主要改动：NetLogger 命令链路与风险报告。测试不对真实账号执行互动或发布。

## 自动化冒烟脚本

运行前准备：

- 浏览器扩展已重新加载并显示已连接；
- 已在环境变量或仓库根目录 `.env` 中配置 `XHS_BRIDGE_URL`、`XHS_BRIDGE_TOKEN`、`XHS_BRIDGE_SESSION_ID`；
- 当前目录使用本分支的客户端代码。

执行：

```bash
bash scripts/test_cli_integration.sh
```

脚本顺序：

1. 确认 CLI 注册了 NetLogger 命令；
2. 通过 `check-login` 验证远端 Bridge 与目标浏览器 session；
3. 启用并清空 NetLogger；
4. 再次执行只读的 `check-login`，读取最近记录并生成风险报告；
5. 清空并关闭 NetLogger。

脚本不会执行点赞、收藏、评论、填写表单或发布。即使中间步骤失败，退出 trap 也会尝试关闭和清空 NetLogger。

## 通过标准

- 每一个 CLI 子命令返回成功 JSON；
- `get-netlog` 能返回脱敏记录，字段中没有 Cookie、签名、请求体或 URL query；
- `risk-report` 可以返回 `safe`、`low`、`medium` 或 `high` 的结构化报告；
- 执行结束后 `get-netlog` 不再采集新记录（NetLogger 已关闭）。

## 需要人工确认的业务项

这些项不应由默认脚本自动执行，需使用测试账号或草稿环境手工验证：

| 场景 | 操作 | 预期 |
| --- | --- | --- |
| 已收藏笔记 | 执行一次收藏 | 不重复点击，返回“已收藏” |
| 收藏失败 | 选择可安全验证的异常页面 | 不再误报成功，返回“状态未变化”或“未找到收藏按钮” |
| 图文草稿 | `fill-publish` 后人工检查页面 | 不会误点 Honey Pot Tab |
| 确认发布 | 使用测试账号或可撤销内容 | 成功、普通失败、风控提示被明确区分；无法确认不报成功 |
| 风险门禁 | NetLogger 已出现中高风险信号时再尝试操作 | 在操作前停止，不自动重试或绕过 |

## 已有离线覆盖

本地测试已覆盖收藏状态确认、发布结果分类、NetLogger 风险报告与风险门禁逻辑。运行：

```bash
.venv/bin/python -m pytest -q
```
