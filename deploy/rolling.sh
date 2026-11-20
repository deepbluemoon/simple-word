#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

IMAGE="${1:-${IMAGE:-}}"
EXPECTED_MODEL_VERSION="${2:-${EXPECTED_MODEL_VERSION:-}}"
if [[ -z "$IMAGE" ]]; then
    echo "Usage: $0 <image:tag> <model-version>" >&2
    exit 2
fi
if [[ -z "$EXPECTED_MODEL_VERSION" ]]; then
    echo "A model version is required for the deployment smoke check" >&2
    exit 2
fi
export EXPECTED_MODEL_VERSION
previous1="$(compose ps --all --quiet api-1 | xargs -r docker inspect --format '{{.Config.Image}}' 2>/dev/null || true)"
previous2="$(compose ps --all --quiet api-2 | xargs -r docker inspect --format '{{.Config.Image}}' 2>/dev/null || true)"
if [[ -z "$previous1" || -z "$previous2" ]]; then
    echo "Both API containers must already be running before a rolling deployment" >&2
    exit 1
fi

changed=()
weight_changed=0
proxy_updated=0
skip_proxy_update="${SKIP_PROXY_UPDATE:-0}"
proxy_id="$(compose ps --all --quiet proxy)"
if [[ -z "$proxy_id" ]]; then
    echo "Proxy must already be running before a rolling deployment" >&2
    exit 1
fi
proxy_backup="$(mktemp -d "${TMPDIR:-/tmp}/simple-word-proxy-rollback.XXXXXX")"
proxy_image_ref="$(docker inspect --format '{{.Config.Image}}' "$proxy_id")"
proxy_image_id="$(docker inspect --format '{{.Image}}' "$proxy_id")"
mkdir -p "$proxy_backup/config" "$proxy_backup/templates/snippets"
restore_weight() {
    if (( weight_changed )) && [[ -n "${WEIGHT_HOOK:-}" ]]; then
        bash -c "$WEIGHT_HOOK" -- restore >&2
        weight_changed=0
    fi
}
rollback_on_failure() {
    local status=$?
    trap - EXIT
    if (( status != 0 )); then
        echo "Rolling deployment failed; restoring prior containers" >&2
        for service in ${changed[@]+"${changed[@]}"}; do
            old="$previous1"
            [[ "$service" == api-2 ]] && old="$previous2"
            IMAGE="$old" compose up -d --no-deps --no-build --pull missing "$service" >&2 || true
            wait_healthy "$service" 90 || true
        done
        if (( proxy_updated )); then
            docker exec "$proxy_id" sh -c 'rm -rf /etc/nginx/conf.d/*' || true
            docker cp "$proxy_backup/config/." "$proxy_id:/etc/nginx/conf.d/" || true
            docker cp "$proxy_backup/templates/default.conf.template" "$proxy_id:/etc/nginx/templates/default.conf.template" || true
            docker cp "$proxy_backup/templates/snippets/simple-word-routes.conf.template" "$proxy_id:/etc/nginx/templates/snippets/simple-word-routes.conf.template" || true
            docker exec "$proxy_id" nginx -t && docker exec "$proxy_id" nginx -s reload || true
            docker tag "$proxy_image_id" "$proxy_image_ref" || true
            for _ in {1..10}; do
                check_proxy_health && break
                sleep 1
            done
        fi
        restore_weight || true
    fi
    rm -rf "$proxy_backup"
    exit "$status"
}
trap rollback_on_failure EXIT
if [[ "$skip_proxy_update" != 1 ]]; then
    docker cp "$proxy_id:/etc/nginx/conf.d/." "$proxy_backup/config/"
    docker cp "$proxy_id:/etc/nginx/templates/default.conf.template" "$proxy_backup/templates/default.conf.template"
    docker cp "$proxy_id:/etc/nginx/templates/snippets/simple-word-routes.conf.template" "$proxy_backup/templates/snippets/simple-word-routes.conf.template"
fi

if [[ -n "${WEIGHT_HOOK:-}" ]]; then
    weight_changed=1
    bash -c "$WEIGHT_HOOK" -- up
    sleep "${WEIGHT_HOOK_WAIT:-30}"
fi

if [[ "$skip_proxy_update" != 1 ]]; then
    bash "$DEPLOY_DIR/update-proxy.sh"
    proxy_updated=1
fi

for service in api-1 api-2; do
    changed+=("$service")
    IMAGE="$IMAGE" compose up -d --no-deps --no-build --pull missing "$service"
    if ! wait_healthy "$service" 90 || ! check_proxy_health || ! smoke_check "http://$DEPLOY_HOST:$HOST_PORT"; then
        echo "$service health or smoke check failed" >&2
        compose logs --no-color --tail 30 "$service" proxy >&2 || true
        exit 1
    fi
done

restore_weight
if [[ "$previous1" != "$IMAGE" ]]; then save_previous "$previous1"; fi
trap - EXIT
echo "Deployed $IMAGE to both API containers on $DEPLOY_HOST"
