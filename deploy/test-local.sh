#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
DEPLOY_DIR="$REPO_ROOT/deploy"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/simple-word-rolling.XXXXXX")"
COMPOSE_PROJECT_NAME="rolling-test-${$}"
GOOD_IMAGE="${1:-${IMAGE:-simple-word:qa-codex}}"
MODEL_SOURCE="${2:-}"
MODEL_VERSION="${3:-qa-dummy}"
IMAGE_PROVIDED=0
if [[ -n "${1:-${IMAGE:-}}" ]]; then IMAGE_PROVIDED=1; fi
BROKEN_IMAGE="simple-word:qa-broken-${$}"
PROXY_IMAGE="simple-word-proxy:qa-${$}"
HOST_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
mkdir -p "$WORK_DIR/models"
if [[ -n "$MODEL_SOURCE" ]]; then
    if [[ -z "${3:-}" || ! -f "$MODEL_SOURCE/registry.json" ]]; then
        echo "Usage: $0 <image:tag> <model-dir> <model-version>" >&2
        exit 2
    fi
    MODEL_SOURCE="$(cd -- "$MODEL_SOURCE" && pwd)"
    python3 - "$MODEL_SOURCE" "$MODEL_VERSION" <<'PY'
import json
from pathlib import Path
import sys

root, expected = Path(sys.argv[1]), sys.argv[2]
registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
if not isinstance(registry, dict):
    raise SystemExit("Model registry must be a JSON object")
roles = [registry.get(role) for role in ("champion", "canary", "shadow")]
if any(version is not None and (not isinstance(version, str) or not version) for version in roles):
    raise SystemExit("Model registry roles must be null or non-empty version strings")
if not registry.get("champion"):
    raise SystemExit("Model registry must define a champion")
versions = {version for version in roles if version}
if expected not in versions:
    raise SystemExit(f"Expected model {expected!r} is not loaded by registry roles: {sorted(versions)}")
weight = registry.get("canary_weight", 0)
if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1:
    raise SystemExit("Model registry canary_weight must be between 0 and 1")
for version in versions - {"dummy"}:
    if version in {".", ".."} or "/" in version or "\\" in version:
        raise SystemExit(f"Invalid model version in registry: {version!r}")
    artifact = root / version
    if not artifact.is_dir() or not ((artifact / "metadata.json").is_file() or (artifact / "encoder.onnx").is_file()):
        raise SystemExit(f"Model registry role {version!r} has no valid artifact")
PY
    MODEL_DIR="$MODEL_SOURCE"
else
    mkdir -p "$WORK_DIR/models/$MODEL_VERSION"
    printf '{"champion":"%s","canary":null,"canary_weight":0,"shadow":null}\n' "$MODEL_VERSION" > "$WORK_DIR/models/registry.json"
    printf '{"version":"%s"}\n' "$MODEL_VERSION" > "$WORK_DIR/models/$MODEL_VERSION/metadata.json"
    MODEL_DIR="$WORK_DIR/models"
fi
export COMPOSE_PROJECT_NAME HOST_PORT DEPLOY_HOST=127.0.0.1 MODEL_DIR
export DEPLOY_STATE_FILE="$WORK_DIR/previous-tag" PROXY_IMAGE
export EXPECTED_MODEL_VERSION="$MODEL_VERSION"
export NGINX_SIMPLIFY_RATE=1000r/s NGINX_SIMPLIFY_BURST=1000
export NGINX_FEEDBACK_RATE=1000r/s NGINX_FEEDBACK_BURST=1000 NGINX_CONNECTIONS_PER_IP=1000
unset DEPLOY_USER DOCKER_HOST WEIGHT_HOOK WEIGHT_HOOK_WAIT

compose() { docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" "$@"; }
cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
    docker image rm "$BROKEN_IMAGE" "$PROXY_IMAGE" >/dev/null 2>&1 || true
    (( IMAGE_PROVIDED )) || docker image rm "$GOOD_IMAGE" >/dev/null 2>&1 || true
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

if (( IMAGE_PROVIDED )); then docker image inspect "$GOOD_IMAGE" >/dev/null 2>&1 || docker pull "$GOOD_IMAGE"; else IMAGE="$GOOD_IMAGE" compose build api-1 api-2; fi
export IMAGE="$GOOD_IMAGE"
compose build proxy
IMAGE="$GOOD_IMAGE" compose up -d --no-build --wait --wait-timeout 180 api-1 api-2 proxy
python3 "$REPO_ROOT/scripts/smoke.py" "http://127.0.0.1:$HOST_PORT" --expected-model-version "$MODEL_VERSION"

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
bash "$DEPLOY_DIR/rolling.sh" "$GOOD_IMAGE" "$MODEL_VERSION"
touch "$WORK_DIR/stop-requests"
wait "$request_pid"
if ! awk '$1 !~ /^2/ { failed=1 } END { exit failed }' "$WORK_DIR/statuses"; then
    echo "Requests failed during successful rolling replacement" >&2
    exit 1
fi

if bash "$DEPLOY_DIR/rolling.sh" "$BROKEN_IMAGE" "$MODEL_VERSION"; then
    echo "Expected unhealthy rolling deployment to fail" >&2
    exit 1
fi
for service in api-1 api-2; do
    container="$(compose ps --all --quiet "$service")"
    [[ "$(docker inspect --format '{{.Config.Image}}' "$container")" == "$GOOD_IMAGE" ]]
done
curl --fail --silent "http://127.0.0.1:$HOST_PORT/health" >/dev/null
echo "Rolling replacement kept requests healthy and restored both containers after failure."
