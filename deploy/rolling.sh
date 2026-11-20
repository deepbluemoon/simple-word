#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

IMAGE="${1:-${IMAGE:-}}"
if [[ -z "$IMAGE" ]]; then
    echo "Usage: $0 <image:tag>" >&2
    exit 2
fi
previous1="$(compose ps --all --quiet api-1 | xargs -r docker inspect --format '{{.Config.Image}}' 2>/dev/null || true)"
previous2="$(compose ps --all --quiet api-2 | xargs -r docker inspect --format '{{.Config.Image}}' 2>/dev/null || true)"
if [[ -z "$previous1" || -z "$previous2" ]]; then
    echo "Both API containers must already be running before a rolling deployment" >&2
    exit 1
fi

changed=()
weight_changed=0
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
        for service in "${changed[@]}"; do
            old="$previous1"
            [[ "$service" == api-2 ]] && old="$previous2"
            IMAGE="$old" compose up -d --no-deps --no-build --pull missing "$service" >&2 || true
            wait_healthy "$service" 90 || true
        done
        restore_weight || true
    fi
    exit "$status"
}
trap rollback_on_failure EXIT

if [[ -n "${WEIGHT_HOOK:-}" ]]; then
    weight_changed=1
    bash -c "$WEIGHT_HOOK" -- up
    sleep "${WEIGHT_HOOK_WAIT:-30}"
fi

bash "$DEPLOY_DIR/update-proxy.sh"

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
