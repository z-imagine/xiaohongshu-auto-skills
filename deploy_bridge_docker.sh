#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

DEPLOY_BASE_DIR="${ROOT_DIR}/tmp/deploy-bridge"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
STAGING_DIR="${DEPLOY_BASE_DIR}/staging-${TIMESTAMP}"
ARTIFACT_PATH="${DEPLOY_BASE_DIR}/xhs-bridge-${TIMESTAMP}.tar.gz"

SSH_TARGET="${DEPLOY_SSH_TARGET:-}"
REMOTE_DIR="${DEPLOY_REMOTE_DIR:-}"
SSH_PORT="${DEPLOY_SSH_PORT:-22}"
SSH_IDENTITY="${DEPLOY_IDENTITY_FILE:-}"

usage() {
  cat <<'EOF'
用法:
  1. 复制 .env.example 为 .env
  2. 填写本地部署所需的 DEPLOY_*
  3. 运行 ./deploy_bridge_docker.sh

也可通过环境变量传入:
  DEPLOY_SSH_TARGET
  DEPLOY_REMOTE_DIR
  DEPLOY_SSH_PORT
  DEPLOY_IDENTITY_FILE

脚本会优先读取仓库根目录的 .env。
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 0 ]]; then
  echo "deploy_bridge_docker.sh 不再接收命令行参数，请改为配置根目录 .env" >&2
  usage
  exit 1
fi

if [[ -z "${SSH_TARGET}" ]]; then
  echo "缺少 DEPLOY_SSH_TARGET，请在 .env 中配置" >&2
  usage
  exit 1
fi

if [[ -z "${REMOTE_DIR}" ]]; then
  echo "缺少 DEPLOY_REMOTE_DIR，请在 .env 中配置" >&2
  usage
  exit 1
fi

REMOTE_RUNTIME_DIR="${REMOTE_DIR}/runtime"
REMOTE_BACKUP_DIR="${REMOTE_DIR}/backups"

mkdir -p "${STAGING_DIR}/bridge" "${DEPLOY_BASE_DIR}"

cp "${ROOT_DIR}/Dockerfile" "${STAGING_DIR}/"
cp "${ROOT_DIR}/docker-compose.yml" "${STAGING_DIR}/"
cp "${ROOT_DIR}/.dockerignore" "${STAGING_DIR}/"
cp "${ROOT_DIR}/.env.example" "${STAGING_DIR}/"
cp "${ROOT_DIR}/pyproject.toml" "${STAGING_DIR}/"
cp "${ROOT_DIR}/uv.lock" "${STAGING_DIR}/"
cp "${ROOT_DIR}/README.md" "${STAGING_DIR}/"
cp -R "${ROOT_DIR}/bridge/." "${STAGING_DIR}/bridge/"

tar -C "${STAGING_DIR}" -czf "${ARTIFACT_PATH}" .

SSH_OPTS=(-p "${SSH_PORT}")
SCP_OPTS=(-P "${SSH_PORT}")
if [[ -n "${SSH_IDENTITY}" ]]; then
  SSH_OPTS+=(-i "${SSH_IDENTITY}")
  SCP_OPTS+=(-i "${SSH_IDENTITY}")
fi

ARTIFACT_NAME="$(basename "${ARTIFACT_PATH}")"

echo "==> 打包完成: ${ARTIFACT_PATH}"
echo "==> 上传到: ${SSH_TARGET}:${REMOTE_DIR}/${ARTIFACT_NAME}"

ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "mkdir -p '${REMOTE_DIR}' '${REMOTE_RUNTIME_DIR}' '${REMOTE_BACKUP_DIR}'"
scp "${SCP_OPTS[@]}" "${ARTIFACT_PATH}" "${SSH_TARGET}:${REMOTE_DIR}/${ARTIFACT_NAME}"

ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "
  set -euo pipefail
  cd '${REMOTE_DIR}'
  if find '${REMOTE_RUNTIME_DIR}' -mindepth 1 -print -quit | grep -q .; then
    tar -C '${REMOTE_RUNTIME_DIR}' -czf '${REMOTE_BACKUP_DIR}/runtime-${TIMESTAMP}.tar.gz' .
  fi
  find '${REMOTE_RUNTIME_DIR}' -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  tar -xzf '${ARTIFACT_NAME}' -C '${REMOTE_RUNTIME_DIR}'
  rm -f '${ARTIFACT_NAME}'
  cd '${REMOTE_RUNTIME_DIR}'
  docker compose up -d --build
  docker compose ps
"

echo "==> 部署完成"
echo "==> 远端根目录: ${REMOTE_DIR}"
echo "==> 运行目录: ${REMOTE_RUNTIME_DIR}"
echo "==> 备份目录: ${REMOTE_BACKUP_DIR}"
