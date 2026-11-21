#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-/etc/simple-word/deploy.env}"
if [[ -d /srv/simple-word && ! -r "$DEPLOY_ENV_FILE" ]]; then
    echo "Deployment settings are required but unreadable: $DEPLOY_ENV_FILE" >&2
    exit 1
fi
if [[ -r "$DEPLOY_ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$DEPLOY_ENV_FILE"
fi
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-simple-word}"
COMPOSE_FILES="${COMPOSE_FILES:-$DEPLOY_DIR/compose.yaml}"
SIMPLE_WORD_DOMAIN="${SIMPLE_WORD_DOMAIN:-}"
DEPLOY_HOST="${DEPLOY_HOST:-127.0.0.1}"
HOST_PORT="${HOST_PORT:-8000}"
DEPLOY_STATE_DIR="${DEPLOY_STATE_DIR:-${HOME}/.simple-word}"
DEPLOY_STATE_FILE="${DEPLOY_STATE_FILE:-$DEPLOY_STATE_DIR/$(printf '%s' "$COMPOSE_PROJECT_NAME-$DEPLOY_HOST" | tr '/:@' '---').previous}"

if [[ -n "${DEPLOY_USER:-}" && -z "${DOCKER_HOST:-}" ]]; then
    export DOCKER_HOST="ssh://${DEPLOY_USER}@${DEPLOY_HOST}"
fi
export COMPOSE_PROJECT_NAME HOST_PORT

compose() {
    local files=() file
    IFS=: read -r -a files <<< "$COMPOSE_FILES"
    local args=()
    for file in "${files[@]}"; do args+=(--file "$file"); done
    if [[ -r "$DEPLOY_ENV_FILE" ]]; then
        docker compose --env-file "$DEPLOY_ENV_FILE" --project-name "$COMPOSE_PROJECT_NAME" "${args[@]}" "$@"
    else
        docker compose --project-name "$COMPOSE_PROJECT_NAME" "${args[@]}" "$@"
    fi
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
    if [[ "$COMPOSE_FILES" == *compose.lightsail.yaml* && -n "$SIMPLE_WORD_DOMAIN" ]]; then
        printf 'https://%s/health' "$SIMPLE_WORD_DOMAIN"
    else
        printf 'http://%s:%s/health' "$DEPLOY_HOST" "$HOST_PORT"
    fi
}

smoke_url() {
    if [[ "$COMPOSE_FILES" == *compose.lightsail.yaml* && -n "$SIMPLE_WORD_DOMAIN" ]]; then
        printf 'http://proxy:80'
    else
        printf 'http://%s:%s' "$DEPLOY_HOST" "$HOST_PORT"
    fi
}

check_proxy_health() {
    if [[ "$COMPOSE_FILES" == *compose.lightsail.yaml* && -n "$SIMPLE_WORD_DOMAIN" ]]; then
        curl --fail --silent --show-error --max-time 5 --resolve "$SIMPLE_WORD_DOMAIN:443:127.0.0.1" \
            "https://$SIMPLE_WORD_DOMAIN/health" >/dev/null
        return
    fi
    curl --fail --silent --show-error --max-time 5 "$(health_url)" >/dev/null
}

smoke_check() {
    if [[ "$COMPOSE_FILES" == *compose.lightsail.yaml* ]]; then
        local api_id
        api_id="$(compose ps --all --quiet api-1)"
        if [[ -n "${EXPECTED_MODEL_VERSION:-}" ]]; then
            docker exec -i "$api_id" python - "$1" --expected-model-version "$EXPECTED_MODEL_VERSION" < "$DEPLOY_DIR/../scripts/smoke.py"
        else
            docker exec -i "$api_id" python - "$1" < "$DEPLOY_DIR/../scripts/smoke.py"
        fi
        return
    fi
    if [[ -n "${EXPECTED_MODEL_VERSION:-}" ]]; then
        python3 "$DEPLOY_DIR/../scripts/smoke.py" "$1" --expected-model-version "$EXPECTED_MODEL_VERSION"
    else
        python3 "$DEPLOY_DIR/../scripts/smoke.py" "$1"
    fi
}
