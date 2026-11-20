#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$DEPLOY_DIR/compose.yaml"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-simple-word}"
DEPLOY_HOST="${DEPLOY_HOST:-127.0.0.1}"
HOST_PORT="${HOST_PORT:-8000}"
DEPLOY_STATE_DIR="${DEPLOY_STATE_DIR:-${HOME}/.simple-word}"
DEPLOY_STATE_FILE="${DEPLOY_STATE_FILE:-$DEPLOY_STATE_DIR/$(printf '%s' "$COMPOSE_PROJECT_NAME-$DEPLOY_HOST" | tr '/:@' '---').previous}"

if [[ -n "${DEPLOY_USER:-}" && -z "${DOCKER_HOST:-}" ]]; then
    export DOCKER_HOST="ssh://${DEPLOY_USER}@${DEPLOY_HOST}"
fi
export COMPOSE_PROJECT_NAME HOST_PORT

compose() {
    docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$COMPOSE_FILE" "$@"
}

current_image() {
    local container_id
    container_id="$(compose ps --all --quiet api-1)"
    [[ -n "$container_id" ]] || return 1
    docker inspect --format '{{.Config.Image}}' "$container_id"
}

wait_healthy() {
    local service="$1" timeout="${2:-60}" container_id state elapsed=0
    while (( elapsed < timeout )); do
        container_id="$(compose --profile canary ps --all --quiet "$service" 2>/dev/null || true)"
        if [[ -n "$container_id" ]]; then
            state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
            case "$state" in
                healthy) return 0 ;;
                unhealthy|exited|dead) return 1 ;;
            esac
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

save_previous() {
    local tag="$1"
    mkdir -p "$(dirname -- "$DEPLOY_STATE_FILE")"
    printf '%s\n' "$tag" > "$DEPLOY_STATE_FILE.tmp"
    mv "$DEPLOY_STATE_FILE.tmp" "$DEPLOY_STATE_FILE"
}

health_url() {
    printf 'http://%s:%s/health' "$DEPLOY_HOST" "$HOST_PORT"
}

check_proxy_health() {
    curl --fail --silent --show-error --max-time 5 "$(health_url)" >/dev/null
}

smoke_check() {
    local args=()
    [[ -n "${EXPECTED_MODEL_VERSION:-}" ]] && args+=(--expected-model-version "$EXPECTED_MODEL_VERSION")
    python3 "$DEPLOY_DIR/../scripts/smoke.py" "$1" "${args[@]}"
}
