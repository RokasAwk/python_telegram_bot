#!/usr/bin/env bash
# Rebuild the image, then stop/remove the old container and start a fresh one.
set -euo pipefail

IMAGE_NAME="python-tg-bot"
CONTAINER_NAME="python-tg-bot"
ENV_FILE=".env"

echo "==> Building image ${IMAGE_NAME}:latest"
docker build -t "${IMAGE_NAME}:latest" .

if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    echo "==> Stopping container ${CONTAINER_NAME}"
    docker stop "${CONTAINER_NAME}" >/dev/null

    echo "==> Removing container ${CONTAINER_NAME}"
    docker rm "${CONTAINER_NAME}" >/dev/null
fi

echo "==> Starting new container ${CONTAINER_NAME}"
docker run -d \
    --name "${CONTAINER_NAME}" \
    --env-file "${ENV_FILE}" \
    --restart unless-stopped \
    "${IMAGE_NAME}:latest"

echo "==> Done. Current status:"
docker ps -a --filter "name=${CONTAINER_NAME}" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
