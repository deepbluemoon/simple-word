#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

IMAGE="${1:-${IMAGE:-}}"
if [[ -z "$IMAGE" ]]; then
    echo "Usage: $0 <image:tag>" >&2
    exit 2
fi
export IMAGE
previous="$(current_image 2>/dev/null || true)"

rollback_on_failure() {
    local status=$?
    trap - EXIT
    if (( status != 0 )) && [[ -n "$previous" ]]; then
        echo "Deployment failed; restoring $previous" >&2
        IMAGE="$previous" CANARY_ENABLED=0 CANARY_PERCENT=0 CANARY_SPLIT_PERCENT=1 compose up -d --no-build --pull missing api proxy >&2 || true
        wait_healthy api 60 || true
    fi
    exit "$status"
}
trap rollback_on_failure EXIT

compose build proxy
CANARY_ENABLED=0 CANARY_PERCENT=0 CANARY_SPLIT_PERCENT=1 compose up -d --no-build --pull missing api proxy
if ! wait_healthy api 90 || ! wait_healthy proxy 30 || ! check_proxy_health; then
    echo "Deployment health check failed" >&2
    compose logs --no-color --tail 30 api proxy >&2 || true
    exit 1
fi
if [[ -n "$previous" && "$previous" != "$IMAGE" ]]; then
    save_previous "$previous"
fi
trap - EXIT
echo "Deployed $IMAGE on $DEPLOY_HOST"
