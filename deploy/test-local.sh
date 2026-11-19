#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
DEPLOY_DIR="$REPO_ROOT/deploy"
mkdir -p "$REPO_ROOT/.tmp"
WORK_DIR="$(mktemp -d "$REPO_ROOT/.tmp/deploy-test.XXXXXX")"
COMPOSE_PROJECT_NAME="codex6-local-${$}"
GOOD_IMAGE="simple-word-test:good-${$}"
BROKEN_IMAGE="simple-word-test:broken-${$}"
ERROR_IMAGE="simple-word-test:error-${$}"
CANARY_IMAGE="simple-word-test:canary-${$}"
read -r HOST_PORT CANARY_PORT < <(python3 -c 'import socket; ports=[]
while len(ports) < 2:
 s=socket.socket(); s.bind(("0.0.0.0", 0)); port=s.getsockname()[1]; s.close()
 if port != 8000 and port not in ports: ports.append(port)
print(*ports)')
mkdir -p "$WORK_DIR/models"
export COMPOSE_PROJECT_NAME DEPLOY_HOST=127.0.0.1 HOST_PORT CANARY_PORT
export MODEL_DIR="$WORK_DIR/models" PROXY_IMAGE="simple-word-proxy:test-${$}"
export DEPLOY_STATE_FILE="$WORK_DIR/previous-tag"
unset DEPLOY_USER DOCKER_HOST CANARY_ENABLED CANARY_PERCENT CANARY_SPLIT_PERCENT

cleanup() {
    docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" --profile canary down --volumes --remove-orphans >/dev/null 2>&1 || true
    docker image rm "$GOOD_IMAGE" "$BROKEN_IMAGE" "$ERROR_IMAGE" "$CANARY_IMAGE" "$PROXY_IMAGE" >/dev/null 2>&1 || true
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

IMAGE="$GOOD_IMAGE" docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" build api
"$DEPLOY_DIR/deploy.sh" "$GOOD_IMAGE"

cat > "$WORK_DIR/Dockerfile.broken" <<EOF
FROM $GOOD_IMAGE
CMD ["python", "-c", "import time; time.sleep(3600)"]
EOF
docker build --tag "$BROKEN_IMAGE" --file "$WORK_DIR/Dockerfile.broken" "$REPO_ROOT"
cat > "$WORK_DIR/server.py" <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        code = 200 if self.path == "/health" else 500
        self.send_response(code)
        self.end_headers()

HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
PY
cat > "$WORK_DIR/Dockerfile.error" <<EOF
FROM python:3.11-slim
COPY server.py /server.py
CMD ["python", "/server.py"]
EOF
docker build --tag "$ERROR_IMAGE" --file "$WORK_DIR/Dockerfile.error" "$WORK_DIR"
if "$DEPLOY_DIR/deploy.sh" "$BROKEN_IMAGE"; then
    echo "Expected unhealthy deployment to fail" >&2
    exit 1
fi
[[ "$(docker inspect --format '{{.Config.Image}}' "$(docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" ps --quiet api)")" == "$GOOD_IMAGE" ]]
curl --fail --silent "http://127.0.0.1:$HOST_PORT/health" >/dev/null

if MAX_ERROR_RATE=0 CANARY_PERCENT=99 CANARY_SAMPLE_SIZE=20 "$DEPLOY_DIR/canary.sh" "$ERROR_IMAGE"; then
    echo "Expected canary error rate to fail" >&2
    exit 1
fi
[[ -z "$(docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" --profile canary ps --quiet canary)" ]]
curl --fail --silent "http://127.0.0.1:$HOST_PORT/health" >/dev/null

if CANARY_SAMPLE_SIZE=1 "$DEPLOY_DIR/canary.sh" "$BROKEN_IMAGE"; then
    echo "Expected unhealthy canary to be rejected" >&2
    exit 1
fi
[[ -z "$(docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" --profile canary ps --quiet canary)" ]]
curl --fail --silent "http://127.0.0.1:$HOST_PORT/health" >/dev/null

docker image tag "$GOOD_IMAGE" "$CANARY_IMAGE"
CANARY_SAMPLE_SIZE=100 "$DEPLOY_DIR/canary.sh" "$CANARY_IMAGE"
current="$(docker inspect --format '{{.Config.Image}}' "$(docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" ps --quiet api)")"
[[ "$current" == "$CANARY_IMAGE" ]]

printf '%s\n' "$BROKEN_IMAGE" > "$DEPLOY_STATE_FILE"
if "$DEPLOY_DIR/rollback.sh"; then
    echo "Expected unhealthy rollback target to fail" >&2
    exit 1
fi
current="$(docker inspect --format '{{.Config.Image}}' "$(docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" ps --quiet api)")"
[[ "$current" == "$CANARY_IMAGE" ]]

printf '%s\n' "$GOOD_IMAGE" > "$DEPLOY_STATE_FILE"
"$DEPLOY_DIR/rollback.sh"
current="$(docker inspect --format '{{.Config.Image}}' "$(docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" ps --quiet api)")"
[[ "$current" == "$GOOD_IMAGE" ]]
echo "Local deploy, automatic rollback, canary retraction, promotion, and rollback recovery passed."
