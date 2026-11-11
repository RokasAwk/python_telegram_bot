#!/usr/bin/env bash
# Rebuild the image, then stop/remove the old container and start a fresh one.
set -euo pipefail

IMAGE_NAME="python-tg-bot"
CONTAINER_NAME="python-tg-bot"
ENV_FILE=".env"
# 記事本 SQLite 放在主機上的這個資料夾，容器刪掉重建也不會清掉
DATA_DIR="$(pwd)/data"

echo "==> Building image ${IMAGE_NAME}:latest"
docker build -t "${IMAGE_NAME}:latest" .

if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    echo "==> Stopping container ${CONTAINER_NAME}"
    docker stop "${CONTAINER_NAME}" >/dev/null

    echo "==> Removing container ${CONTAINER_NAME}"
    docker rm "${CONTAINER_NAME}" >/dev/null
fi

mkdir -p "${DATA_DIR}"

echo "==> Starting new container ${CONTAINER_NAME}"
docker run -d \
    --name "${CONTAINER_NAME}" \
    --env-file "${ENV_FILE}" \
    -v "${DATA_DIR}:/app/data" \
    --restart unless-stopped \
    "${IMAGE_NAME}:latest"

echo "==> Done. Current status:"
docker ps -a --filter "name=${CONTAINER_NAME}" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
