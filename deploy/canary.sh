#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

CANARY_IMAGE="${1:-${CANARY_IMAGE:-}}"
CANARY_PERCENT="${CANARY_PERCENT:-10}"
CANARY_SAMPLE_SIZE="${CANARY_SAMPLE_SIZE:-100}"
CANARY_SAMPLE_PATH="${CANARY_SAMPLE_PATH:-/}"
MAX_ERROR_RATE="${MAX_ERROR_RATE:-0.01}"
CANARY_MIN_REQUESTS="${CANARY_MIN_REQUESTS:-1}"
if [[ -z "$CANARY_IMAGE" || ! "$CANARY_PERCENT" =~ ^[1-9][0-9]?$ || "$CANARY_PERCENT" -gt 99 || ! "$CANARY_SAMPLE_SIZE" =~ ^[1-9][0-9]*$ || ! "$CANARY_MIN_REQUESTS" =~ ^[1-9][0-9]*$ || "$CANARY_SAMPLE_PATH" != /* ]] || ! awk -v rate="$MAX_ERROR_RATE" 'BEGIN { exit !(rate >= 0 && rate <= 1) }'; then
    echo "Usage: $0 <image:tag> (CANARY_PERCENT 1..99, positive sample size, MAX_ERROR_RATE 0..1)" >&2
    exit 2
fi
previous="$(current_image 2>/dev/null || true)"
if [[ -z "$previous" ]]; then
    echo "Deploy a healthy stable api before starting a canary" >&2
    exit 1
fi
CANARY_SPLIT_PERCENT="$CANARY_PERCENT"
CANARY_ENABLED=1
export CANARY_IMAGE CANARY_PERCENT CANARY_SPLIT_PERCENT CANARY_ENABLED

retract_on_failure() {
    local status=$?
    trap - EXIT
    if (( status != 0 )); then
        echo "Canary failed; restoring 0% traffic and removing it" >&2
        CANARY_ENABLED=0 CANARY_PERCENT=0 CANARY_SPLIT_PERCENT=1 compose up -d proxy >&2 || true
        compose --profile canary rm --stop --force canary >&2 || true
    fi
    exit "$status"
}
trap retract_on_failure EXIT

compose --profile canary up -d --no-build --pull missing canary
if ! wait_healthy canary 90; then
    echo "Canary health check failed" >&2
    exit 1
fi
CANARY_ENABLED=0 CANARY_PERCENT=0 CANARY_SPLIT_PERCENT=1 compose up -d proxy
CANARY_PERCENT="$CANARY_PERCENT" compose up -d proxy
if ! wait_healthy proxy 30; then
    echo "Proxy health check failed after traffic shift" >&2
    exit 1
fi

sample_count=0
error_count=0
canary_count=0
canary_errors=0
for ((i = 0; i < CANARY_SAMPLE_SIZE; i++)); do
    headers="$(mktemp)"
    status="$(curl --silent --show-error --max-time 10 --dump-header "$headers" --output /dev/null --write-out '%{http_code}' "http://$DEPLOY_HOST:$HOST_PORT$CANARY_SAMPLE_PATH" || printf '000')"
    upstream="$(awk 'tolower($1) == "x-simple-word-upstream:" { gsub("\\r", "", $2); print tolower($2) }' "$headers" | tail -n 1)"
    rm -f "$headers"
    sample_count=$((sample_count + 1))
    if [[ ! "$status" =~ ^2[0-9][0-9]$ ]]; then
        error_count=$((error_count + 1))
    fi
    if [[ "$upstream" == canary ]]; then
        canary_count=$((canary_count + 1))
        if [[ ! "$status" =~ ^2[0-9][0-9]$ ]]; then
            canary_errors=$((canary_errors + 1))
        fi
    fi
done

if (( canary_count < CANARY_MIN_REQUESTS )) || ! awk -v errors="$canary_errors" -v total="$canary_count" -v maximum="$MAX_ERROR_RATE" 'BEGIN { exit !(total > 0 && errors / total <= maximum) }'; then
    echo "Canary sample failed: $canary_errors/$canary_count canary errors across $sample_count requests ($error_count total errors)" >&2
    exit 1
fi

CANARY_ENABLED=0 CANARY_PERCENT=0 CANARY_SPLIT_PERCENT=1 compose up -d proxy
IMAGE="$CANARY_IMAGE" CANARY_ENABLED=0 CANARY_PERCENT=0 CANARY_SPLIT_PERCENT=1 compose up -d --no-build --pull missing api
if ! wait_healthy api 90 || ! wait_healthy proxy 30 || ! check_proxy_health; then
    echo "Promoted image failed health check" >&2
    IMAGE="$previous" CANARY_ENABLED=0 CANARY_PERCENT=0 CANARY_SPLIT_PERCENT=1 compose up -d --no-build --pull missing api proxy >&2 || true
    wait_healthy api 60 || true
    exit 1
fi
save_previous "$previous"
compose --profile canary rm --stop --force canary
trap - EXIT
echo "Promoted $CANARY_IMAGE after $canary_count canary requests; canary error rate $canary_errors/$canary_count"
