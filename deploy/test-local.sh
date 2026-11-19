#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
DEPLOY_DIR="$REPO_ROOT/deploy"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/simple-word-rolling.XXXXXX")"
COMPOSE_PROJECT_NAME="rolling-test-${$}"
GOOD_IMAGE=simple-word:qa-codex
BROKEN_IMAGE="simple-word:qa-broken-${$}"
PROXY_IMAGE="simple-word-proxy:qa-${$}"
HOST_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
mkdir -p "$WORK_DIR/models"
export COMPOSE_PROJECT_NAME HOST_PORT DEPLOY_HOST=127.0.0.1 MODEL_DIR="$WORK_DIR/models"
export DEPLOY_STATE_FILE="$WORK_DIR/previous-tag" PROXY_IMAGE
unset DEPLOY_USER DOCKER_HOST WEIGHT_HOOK WEIGHT_HOOK_WAIT

compose() { docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" "$@"; }
cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
    docker image rm "$GOOD_IMAGE" "$BROKEN_IMAGE" "$PROXY_IMAGE" >/dev/null 2>&1 || true
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

IMAGE="$GOOD_IMAGE" compose build api-1 api-2
compose build proxy
IMAGE="$GOOD_IMAGE" compose up -d --no-build --wait --wait-timeout 180 api-1 api-2 proxy
python3 "$REPO_ROOT/scripts/smoke.py" "http://127.0.0.1:$HOST_PORT"

cat > "$WORK_DIR/Dockerfile.broken" <<EOF
FROM $GOOD_IMAGE
CMD ["python", "-c", "import time; time.sleep(3600)"]
EOF
docker build --tag "$BROKEN_IMAGE" --file "$WORK_DIR/Dockerfile.broken" "$REPO_ROOT"

: > "$WORK_DIR/statuses"
(while [[ ! -e "$WORK_DIR/stop-requests" ]]; do
    curl --silent --output /dev/null --max-time 2 --write-out '%{http_code}\n' "http://127.0.0.1:$HOST_PORT/health" >> "$WORK_DIR/statuses" || echo 000 >> "$WORK_DIR/statuses"
    sleep 0.1
done) &
request_pid=$!
trap 'touch "$WORK_DIR/stop-requests"; wait "$request_pid" 2>/dev/null || true; cleanup' EXIT
"$DEPLOY_DIR/rolling.sh" "$GOOD_IMAGE"
touch "$WORK_DIR/stop-requests"
wait "$request_pid"
if ! awk '$1 !~ /^2/ { failed=1 } END { exit failed }' "$WORK_DIR/statuses"; then
    echo "Requests failed during successful rolling replacement" >&2
    exit 1
fi

if "$DEPLOY_DIR/rolling.sh" "$BROKEN_IMAGE"; then
    echo "Expected unhealthy rolling deployment to fail" >&2
    exit 1
fi
for service in api-1 api-2; do
    container="$(compose ps --all --quiet "$service")"
    [[ "$(docker inspect --format '{{.Config.Image}}' "$container")" == "$GOOD_IMAGE" ]]
done
curl --fail --silent "http://127.0.0.1:$HOST_PORT/health" >/dev/null
echo "Rolling replacement kept requests healthy and restored both containers after failure."
