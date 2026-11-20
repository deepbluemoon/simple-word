#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

proxy_id="$(compose ps --all --quiet proxy)"
if [[ -z "$proxy_id" ]]; then
    echo "Proxy must already be running before its configuration can be reloaded" >&2
    exit 1
fi
config_container="${COMPOSE_PROJECT_NAME}-proxy-config-$$"
work="$(mktemp -d "${TMPDIR:-/tmp}/simple-word-proxy.XXXXXX")"
cleanup() {
    docker rm -f "$config_container" >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT

compose build proxy
compose run --detach --no-deps --name "$config_container" proxy >/dev/null
docker cp "$config_container:/etc/nginx/conf.d/default.conf" "$work/new.conf"
docker cp "$proxy_id:/etc/nginx/conf.d/default.conf" "$work/old.conf"
docker cp "$work/new.conf" "$proxy_id:/etc/nginx/conf.d/default.conf"
if ! docker exec "$proxy_id" nginx -t; then
    docker cp "$work/old.conf" "$proxy_id:/etc/nginx/conf.d/default.conf"
    exit 1
fi
if ! docker exec "$proxy_id" nginx -s reload; then
    docker cp "$work/old.conf" "$proxy_id:/etc/nginx/conf.d/default.conf"
    docker exec "$proxy_id" nginx -s reload || true
    exit 1
fi
if ! compose exec -T proxy wget -q -O /dev/null http://127.0.0.1/health; then
    echo "Proxy health check failed after reloading the new configuration" >&2
    exit 1
fi
