#!/usr/bin/env bash
# 对远端 Bridge + 浏览器扩展执行低风险 CLI 冒烟测试。
# 不会执行点赞、收藏、评论、填写或发布；结束时会清空并关闭 NetLogger。
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "缺少 ${name}；请先在环境变量或 .env 中配置。" >&2
    exit 2
  fi
}

load_env_file() {
  if [[ -f ".env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source ".env"
    set +a
  fi
}

load_env_file
require_env "XHS_BRIDGE_URL"
require_env "XHS_BRIDGE_TOKEN"
require_env "XHS_BRIDGE_SESSION_ID"

if [[ -x ".venv/bin/python" ]]; then
  CLI=(".venv/bin/python" "scripts/cli.py")
else
  CLI=("uv" "run" "python" "scripts/cli.py")
fi

cleanup_netlog() {
  "${CLI[@]}" disable-netlog >/dev/null 2>&1 || true
  "${CLI[@]}" clear-netlog >/dev/null 2>&1 || true
}

trap cleanup_netlog EXIT

run_step() {
  local label="$1"
  shift
  echo "==> ${label}"
  "${CLI[@]}" "$@"
}

check_login() {
  echo "==> 检查登录与远端 Bridge 连通"
  set +e
  "${CLI[@]}" check-login
  local exit_code=$?
  set -e
  if [[ ${exit_code} -eq 0 ]]; then
    LOGGED_IN=true
    return
  fi
  if [[ ${exit_code} -eq 1 ]]; then
    LOGGED_IN=false
    echo "==> 目标 Session 未登录；继续验证 NetLogger 链路。"
    return
  fi
  echo "check-login 执行失败（exit=${exit_code}）。" >&2
  exit "${exit_code}"
}

probe_readonly_feed() {
  if [[ "${LOGGED_IN}" != true ]]; then
    echo "==> 目标 Session 未登录，跳过首页 Feed 查询。"
    return
  fi
  echo "==> 读取首页 Feed 以产生可观测网络请求"
  "${CLI[@]}" list-feeds >/dev/null
  echo "==> 首页 Feed 查询完成"
}

LOGGED_IN=false
echo "CLI 集成冒烟测试（不会执行互动或发布）"
echo "Bridge: ${XHS_BRIDGE_URL}"
echo "Session: ${XHS_BRIDGE_SESSION_ID}"

run_step "确认 NetLogger 命令已注册" --help
check_login
run_step "启用 NetLogger" enable-netlog
run_step "清空历史 NetLogger 缓存" clear-netlog
probe_readonly_feed
run_step "读取最近 NetLogger 记录" get-netlog --limit 20
run_step "生成风险报告" risk-report
run_step "清空 NetLogger 缓存" clear-netlog
run_step "关闭 NetLogger" disable-netlog

trap - EXIT
echo "==> 通过：CLI、远端 Bridge、扩展 NetLogger 链路可用。"
