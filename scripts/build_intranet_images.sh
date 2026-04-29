#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAMESPACE="${UIX_IMAGE_NAMESPACE:-uix-graph}"
TAG="${UIX_IMAGE_TAG:-$(date +%Y%m%d%H%M%S)}"
PUSH="${PUSH:-0}"

BACKEND_IMAGE="${IMAGE_NAMESPACE}/uix-graph-backend:${TAG}"
FRONTEND_IMAGE="${IMAGE_NAMESPACE}/uix-graph-frontend:${TAG}"

cd "${ROOT_DIR}"

echo "[build_intranet_images] root=${ROOT_DIR}"
echo "[build_intranet_images] backend=${BACKEND_IMAGE}"
echo "[build_intranet_images] frontend=${FRONTEND_IMAGE}"

docker build \
  -f docker/intranet/backend.Dockerfile \
  -t "${BACKEND_IMAGE}" \
  .

docker build \
  -f docker/intranet/frontend.Dockerfile \
  -t "${FRONTEND_IMAGE}" \
  .

if [[ "${PUSH}" == "1" ]]; then
  docker push "${BACKEND_IMAGE}"
  docker push "${FRONTEND_IMAGE}"
fi

cat <<EOF

Build completed.

Use these values in Portainer Stack environment:
  UIX_IMAGE_NAMESPACE=${IMAGE_NAMESPACE}
  UIX_IMAGE_TAG=${TAG}
  UIX_PROJECT_DIR=${ROOT_DIR}

Images:
  ${BACKEND_IMAGE}
  ${FRONTEND_IMAGE}
EOF
