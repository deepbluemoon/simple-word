#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

if [[ ! -s "$DEPLOY_STATE_FILE" ]]; then
    echo "No previous image tag in $DEPLOY_STATE_FILE" >&2
    exit 1
fi
current="$(current_image 2>/dev/null || true)"
previous="$(cat "$DEPLOY_STATE_FILE")"
expected="${1:-${EXPECTED_MODEL_VERSION:-}}"
if [[ -z "$previous" || "$previous" == "$current" ]]; then
    echo "No different previous image tag to restore" >&2
    exit 1
fi
if [[ -z "$expected" ]]; then
    echo "Usage: EXPECTED_MODEL_VERSION=<model-version> $0" >&2
    exit 2
fi
bash "$DEPLOY_DIR/rolling.sh" "$previous" "$expected"
