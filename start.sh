#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Check prerequisites ──
if ! command -v docker &>/dev/null; then
    echo "错误: Docker 未安装，请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker compose &>/dev/null && ! docker compose version &>/dev/null; then
    echo "错误: Docker Compose 未安装"
    exit 1
fi

# ── Prepare env file ──
if [ ! -f .env ]; then
    echo "未找到 .env 文件，从 .env.example 创建。"
    cp .env.example .env
    echo ""
    echo "============================================="
    echo "请编辑 .env 文件设置初始管理员账号后再启动："
    echo "  nano .env    (Linux)"
    echo "  notepad .env (Windows)"
    echo "============================================="
    echo ""
    exit 1
fi

# ── Ensure data directory exists ──
mkdir -p backend/data

# ── Build and start ──
echo "正在构建容器镜像..."
docker compose build

echo "正在启动企业售后工单系统..."
docker compose up -d

echo ""
echo "============================================="
echo "系统已启动，访问 http://localhost:8000"
echo ""
echo "查看日志:  docker compose logs -f"
echo "停止系统:  docker compose down"
echo "============================================="
