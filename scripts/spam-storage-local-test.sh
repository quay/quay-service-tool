#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_TOOL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-${DOCKER:-podman}}"
QUAY_NETWORK_NAME="${QUAY_NETWORK_NAME:-quay_default}"
STATE_DB_PORT="${SERVICE_TOOL_STATE_DB_PORT:-55432}"
S3_PORT="${SERVICE_TOOL_S3_PORT:-9002}"
COMMAND="${1:-test}"

compose() {
  (
    cd "$SERVICE_TOOL_DIR"
    QUAY_NETWORK_NAME="$QUAY_NETWORK_NAME" \
      SERVICE_TOOL_STATE_DB_PORT="$STATE_DB_PORT" \
      SERVICE_TOOL_S3_PORT="$S3_PORT" \
      "$CONTAINER_RUNTIME" compose "$@"
  )
}

case "$COMMAND" in
  down)
    compose stop quay-service-tool-state-db quay-service-tool-s3
    exit 0
    ;;
  clean)
    compose down --volumes --remove-orphans
    exit 0
    ;;
  up|test)
    ;;
  *)
    printf 'Usage: %s [up|test|down|clean]\n' "$0" >&2
    exit 2
    ;;
esac

if ! "$CONTAINER_RUNTIME" network inspect "$QUAY_NETWORK_NAME" >/dev/null 2>&1; then
  "$CONTAINER_RUNTIME" network create "$QUAY_NETWORK_NAME" >/dev/null
fi

# The full demo may already have API/frontend containers depending on these
# services. Reuse the storage containers so Podman Compose does not try to
# replace them underneath those dependents; a clean CI runner still creates
# them normally.
compose up -d --no-recreate quay-service-tool-state-db quay-service-tool-s3

for _ in {1..60}; do
  if compose exec -T quay-service-tool-state-db \
      pg_isready -U spam -d service_tool_spam >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
compose exec -T quay-service-tool-state-db pg_isready -U spam -d service_tool_spam

for _ in {1..60}; do
  if curl -fsS "http://localhost:${S3_PORT}/minio/health/live" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "http://localhost:${S3_PORT}/minio/health/live" >/dev/null

if [[ "$COMMAND" == "up" ]]; then
  printf 'PostgreSQL: localhost:%s\n' "$STATE_DB_PORT"
  printf 'S3 API: http://localhost:%s\n' "$S3_PORT"
  printf 'MinIO console: http://localhost:%s\n' "${SERVICE_TOOL_S3_CONSOLE_PORT:-9003}"
  exit 0
fi

(
  cd "$SERVICE_TOOL_DIR/backend"
  AWS_ACCESS_KEY_ID=minioadmin \
    AWS_SECRET_ACCESS_KEY=minioadmin \
    CONFIG_PATH=config \
    SPAM_DETECTION_TEST_STATE_DB_URI="postgresql://spam:spam-local@localhost:${STATE_DB_PORT}/service_tool_spam" \
    SPAM_DETECTION_TEST_S3_ENDPOINT_URL="http://localhost:${S3_PORT}" \
    uv run --frozen pytest -q
)
