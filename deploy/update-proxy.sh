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
mkdir -p "$work/new-config" "$work/old-config" "$work/new-templates/snippets" "$work/old-templates/snippets"
proxy_image_ref="$(docker inspect --format '{{.Config.Image}}' "$proxy_id")"
proxy_image_id="$(docker inspect --format '{{.Image}}' "$proxy_id")"
config_changed=0
restore_old() {
    docker exec "$proxy_id" sh -c 'rm -rf /etc/nginx/conf.d/*' || return
    docker cp "$work/old-config/." "$proxy_id:/etc/nginx/conf.d/" || return
    docker cp "$work/old-templates/default.conf.template" "$proxy_id:/etc/nginx/templates/default.conf.template" || return
    docker cp "$work/old-templates/snippets/simple-word-routes.conf.template" "$proxy_id:/etc/nginx/templates/snippets/simple-word-routes.conf.template" || return
    docker exec "$proxy_id" nginx -t || return
    docker exec "$proxy_id" nginx -s reload
    wait_proxy_health
}
wait_proxy_health() {
    for _ in {1..10}; do
        if check_proxy_health; then
            return 0
        fi
        sleep 1
    done
    return 1
}
finish() {
    local status=$?
    trap - EXIT
    if (( status != 0 )); then
        if (( config_changed )); then
            echo "Proxy configuration update failed; restoring previous config" >&2
            restore_old || echo "Failed to restore previous proxy configuration" >&2
        fi
        docker tag "$proxy_image_id" "$proxy_image_ref" || echo "Failed to restore previous proxy image tag" >&2
    fi
    docker rm -f "$config_container" >/dev/null 2>&1 || true
    rm -rf "$work"
    exit "$status"
}
trap finish EXIT

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

docker cp "$config_container:/etc/nginx/conf.d/." "$work/new-config/"
docker cp "$config_container:/etc/nginx/templates/default.conf.template" "$work/new-templates/default.conf.template"
docker cp "$config_container:/etc/nginx/templates/snippets/simple-word-routes.conf.template" "$work/new-templates/snippets/simple-word-routes.conf.template"
docker cp "$proxy_id:/etc/nginx/conf.d/." "$work/old-config/"
docker cp "$proxy_id:/etc/nginx/templates/default.conf.template" "$work/old-templates/default.conf.template"
docker cp "$proxy_id:/etc/nginx/templates/snippets/simple-word-routes.conf.template" "$work/old-templates/snippets/simple-word-routes.conf.template"
config_changed=1
docker exec "$proxy_id" sh -c 'rm -rf /etc/nginx/conf.d/*'
docker cp "$work/new-config/." "$proxy_id:/etc/nginx/conf.d/"
docker cp "$work/new-templates/default.conf.template" "$proxy_id:/etc/nginx/templates/default.conf.template"
docker cp "$work/new-templates/snippets/simple-word-routes.conf.template" "$proxy_id:/etc/nginx/templates/snippets/simple-word-routes.conf.template"
docker exec "$proxy_id" nginx -t
docker exec "$proxy_id" nginx -s reload
if ! wait_proxy_health; then
    echo "Proxy health check failed after reloading the new configuration" >&2
    exit 1
fi
config_changed=0
