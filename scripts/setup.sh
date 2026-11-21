#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== OpenSight 初始化 =="

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[ok] 已生成 .env"
fi

mkdir -p data/gallery data/snapshots
echo "[ok] 已创建 data 目录"

if ! command -v docker >/dev/null 2>&1; then
  echo "[error] 未检测到 docker，请先安装 Docker" >&2
  exit 1
fi

echo "[info] 启动服务（首次构建需要几分钟）..."
docker compose up -d --build

echo ""
echo "完成。访问 http://localhost:8080"
echo "查看日志: docker compose logs -f worker"
