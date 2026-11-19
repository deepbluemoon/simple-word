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
"$DEPLOY_DIR/rolling.sh" "$previous"
