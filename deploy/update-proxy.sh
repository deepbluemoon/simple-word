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
mkdir "$work/new" "$work/old"
cleanup() {
    docker rm -f "$config_container" >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT

restore_old() {
    docker exec "$proxy_id" sh -c 'rm -rf /etc/nginx/conf.d/*'
    docker cp "$work/old/." "$proxy_id:/etc/nginx/conf.d/"
    docker exec "$proxy_id" nginx -t
    docker exec "$proxy_id" nginx -s reload
}

compose build proxy
compose run --detach --no-deps --name "$config_container" proxy >/dev/null
rendered=0
for _ in {1..30}; do
    if docker exec "$config_container" sh -c \
        'test -s /etc/nginx/conf.d/default.conf && grep -q "limit_req_zone" /etc/nginx/conf.d/default.conf && ! grep -q "\${NGINX_" /etc/nginx/conf.d/default.conf' \
        && docker exec "$config_container" nginx -t >/dev/null 2>&1; then
        rendered=1
        break
    fi
    sleep 1
done
if (( ! rendered )); then
    echo "Rendered proxy configuration did not become valid" >&2
    exit 1
fi

docker cp "$config_container:/etc/nginx/conf.d/." "$work/new/"
docker cp "$proxy_id:/etc/nginx/conf.d/." "$work/old/"
docker exec "$proxy_id" sh -c 'rm -rf /etc/nginx/conf.d/*'
docker cp "$work/new/." "$proxy_id:/etc/nginx/conf.d/"
if ! docker exec "$proxy_id" nginx -t; then
    restore_old
    exit 1
fi
if ! docker exec "$proxy_id" nginx -s reload; then
    restore_old
    exit 1
fi
if ! compose exec -T proxy wget -q --header="Host: ${SIMPLE_WORD_DOMAIN:-localhost}" -O /dev/null http://127.0.0.1/health; then
    echo "Proxy health check failed after reloading the new configuration; restoring previous config" >&2
    restore_old
    exit 1
fi
