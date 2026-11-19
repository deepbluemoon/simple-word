#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

if [[ ! -s "$DEPLOY_STATE_FILE" ]]; then
    echo "No previous image tag in $DEPLOY_STATE_FILE" >&2
    exit 1
fi
current="$(current_image 2>/dev/null || true)"
previous="$(cat "$DEPLOY_STATE_FILE")"
if [[ -z "$previous" || "$previous" == "$current" ]]; then
    echo "No different previous image tag to restore" >&2
    exit 1
fi

restore_current_on_failure() {
    local status=$?
    trap - EXIT
    if (( status != 0 )) && [[ -n "$current" ]]; then
        echo "Rollback health check failed; restoring $current" >&2
        IMAGE="$current" CANARY_ENABLED=0 CANARY_PERCENT=0 CANARY_SPLIT_PERCENT=1 compose up -d --no-build --pull missing api proxy >&2 || true
        wait_healthy api 60 || true
    fi
    exit "$status"
}
trap restore_current_on_failure EXIT

IMAGE="$previous" CANARY_ENABLED=0 CANARY_PERCENT=0 CANARY_SPLIT_PERCENT=1 compose up -d --no-build --pull missing api proxy
if ! wait_healthy api 90 || ! wait_healthy proxy 30 || ! check_proxy_health; then
    echo "Rollback health check failed" >&2
    exit 1
fi
save_previous "$current"
trap - EXIT
echo "Restored $previous on $DEPLOY_HOST"
