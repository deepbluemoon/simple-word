#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
DEPLOY_DIR="$REPO_ROOT/deploy"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/simple-word-rolling.XXXXXX")"
COMPOSE_PROJECT_NAME="rolling-test-${$}"
GOOD_IMAGE="${1:-${IMAGE:-simple-word:qa-codex}}"
MODEL_SOURCE="${2:-}"
MODEL_VERSION="${3:-qa-dummy}"
IMAGE_PROVIDED=0
if [[ -n "${1:-${IMAGE:-}}" ]]; then IMAGE_PROVIDED=1; fi
BROKEN_IMAGE="simple-word:qa-broken-${$}"
PROXY_IMAGE="simple-word-proxy:qa-${$}"
ROLLBACK_IMAGE="simple-word:qa-rollback-${$}"
HOST_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
CADDY_HTTP_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
CADDY_HTTPS_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
mkdir -p "$WORK_DIR/models"
if [[ -n "$MODEL_SOURCE" ]]; then
    if [[ -z "${3:-}" || ! -f "$MODEL_SOURCE/registry.json" ]]; then
        echo "Usage: $0 <image:tag> <model-dir> <model-version>" >&2
        exit 2
    fi
    MODEL_SOURCE="$(cd -- "$MODEL_SOURCE" && pwd)"
    python3 - "$MODEL_SOURCE" "$MODEL_VERSION" <<'PY'
import json
from pathlib import Path
import sys

root, expected = Path(sys.argv[1]), sys.argv[2]
registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
if not isinstance(registry, dict):
    raise SystemExit("Model registry must be a JSON object")
roles = [registry.get(role) for role in ("champion", "canary", "shadow")]
if any(version is not None and (not isinstance(version, str) or not version) for version in roles):
    raise SystemExit("Model registry roles must be null or non-empty version strings")
if not registry.get("champion"):
    raise SystemExit("Model registry must define a champion")
versions = {version for version in roles if version}
if expected not in versions:
    raise SystemExit(f"Expected model {expected!r} is not loaded by registry roles: {sorted(versions)}")
weight = registry.get("canary_weight", 0)
if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1:
    raise SystemExit("Model registry canary_weight must be between 0 and 1")
for version in versions - {"dummy"}:
    if version in {".", ".."} or "/" in version or "\\" in version:
        raise SystemExit(f"Invalid model version in registry: {version!r}")
    artifact = root / version
    if not artifact.is_dir() or not ((artifact / "metadata.json").is_file() or (artifact / "encoder.onnx").is_file()):
        raise SystemExit(f"Model registry role {version!r} has no valid artifact")
PY
    MODEL_DIR="$MODEL_SOURCE"
else
    mkdir -p "$WORK_DIR/models/$MODEL_VERSION"
    printf '{"champion":"%s","canary":null,"canary_weight":0,"shadow":null}\n' "$MODEL_VERSION" > "$WORK_DIR/models/registry.json"
    printf '{"version":"%s"}\n' "$MODEL_VERSION" > "$WORK_DIR/models/$MODEL_VERSION/metadata.json"
    MODEL_DIR="$WORK_DIR/models"
fi
export COMPOSE_PROJECT_NAME HOST_PORT DEPLOY_HOST=127.0.0.1 MODEL_DIR
export DEPLOY_STATE_FILE="$WORK_DIR/previous-tag" PROXY_IMAGE
export EXPECTED_MODEL_VERSION="$MODEL_VERSION"
export NGINX_SIMPLIFY_RATE=1000r/s NGINX_SIMPLIFY_BURST=1000
export NGINX_FEEDBACK_RATE=1000r/s NGINX_FEEDBACK_BURST=1000 NGINX_CONNECTIONS_PER_IP=1000
unset DEPLOY_USER DOCKER_HOST WEIGHT_HOOK WEIGHT_HOOK_WAIT

compose() { docker compose --project-name "$COMPOSE_PROJECT_NAME" --file "$DEPLOY_DIR/compose.yaml" "$@"; }
test_caddy() (
    local project="${COMPOSE_PROJECT_NAME}-caddy" blocklist="$WORK_DIR/caddy-blocklist.conf"
    local caddyfile="$WORK_DIR/Caddyfile" override="$WORK_DIR/caddy-compose.yaml"
    local envfile="$WORK_DIR/no-deploy.env" ca_file="$WORK_DIR/caddy-root.crt"
    export COMPOSE_PROJECT_NAME="$project" COMPOSE_FILES="$DEPLOY_DIR/compose.yaml:$DEPLOY_DIR/compose.lightsail.yaml:$override"
    export DEPLOY_ENV_FILE="$envfile" BLOCKLIST_FILE="$blocklist" SIMPLE_WORD_DOMAIN=localhost
    export CADDY_HTTP_PORT CADDY_HTTPS_PORT NGINX_SIMPLIFY_RATE=1r/m NGINX_SIMPLIFY_BURST=1
    printf '# empty test blocklist\n' > "$blocklist"
    : > "$envfile"
    : > "$ca_file"
    python3 - "$DEPLOY_DIR/Caddyfile" "$caddyfile" <<'PY'
from pathlib import Path
import sys
source, target = map(Path, sys.argv[1:])
target.write_text(source.read_text().replace("moon.eta.pyhub.kr {", "localhost {\n\ttls internal"), encoding="utf-8")
PY
    cat > "$override" <<EOF
services:
  api-1:
    volumes:
      - $WORK_DIR/models:/app/models:ro
      - $WORK_DIR/logs:/app/logs
  api-2:
    volumes:
      - $WORK_DIR/models:/app/models:ro
      - $WORK_DIR/logs:/app/logs
  proxy:
    volumes:
      - $blocklist:/etc/nginx/conf.d/snippets/blocklist.conf:ro
  caddy:
    ports: !override ["127.0.0.1:$CADDY_HTTP_PORT:80", "127.0.0.1:$CADDY_HTTPS_PORT:443"]
    volumes:
      - $caddyfile:/etc/caddy/Caddyfile:ro
  client1:
    image: curlimages/curl:8.12.1
    entrypoint: ["/bin/sh", "-c"]
    command: ["while true; do sleep 3600; done"]
    networks:
      caddy_edge:
        ipv4_address: 10.203.0.10
    volumes:
      - $ca_file:/ca/root.crt:ro
  client2:
    image: curlimages/curl:8.12.1
    entrypoint: ["/bin/sh", "-c"]
    command: ["while true; do sleep 3600; done"]
    networks:
      caddy_edge:
        ipv4_address: 10.203.0.11
    volumes:
      - $ca_file:/ca/root.crt:ro
EOF
    caddy_compose() {
        docker compose --project-name "$project" --file "$DEPLOY_DIR/compose.yaml" \
            --file "$DEPLOY_DIR/compose.lightsail.yaml" --file "$override" "$@"
    }
    trap 'caddy_compose down --volumes --remove-orphans >/dev/null 2>&1 || true' EXIT

    caddy_compose config --format json | python3 -c '
import json, sys
services = json.load(sys.stdin)["services"]
assert not services["proxy"].get("ports"), services["proxy"].get("ports")
assert not services["api-1"].get("ports") and not services["api-2"].get("ports")
assert {port["target"] for port in services["caddy"]["ports"]} == {80, 443}
assert set(services["api-1"]["networks"]) == {"api_backend"}
assert set(services["api-2"]["networks"]) == {"api_backend"}
assert set(services["proxy"]["networks"]) == {"api_backend", "caddy_edge"}
assert set(services["caddy"]["networks"]) == {"caddy_edge"}
assert services["caddy"]["networks"]["caddy_edge"]["ipv4_address"] == "10.203.0.254"
'
    if ! IMAGE="$GOOD_IMAGE" caddy_compose up -d --build --wait --wait-timeout 180 \
        api-1 api-2 proxy caddy client1 client2; then
        caddy_compose logs --no-color proxy caddy >&2 || true
        return 1
    fi
    source "$DEPLOY_DIR/common.sh"

    local caddy_ready=0
    for _ in {1..45}; do
        if caddy_compose exec -T caddy cat /data/caddy/pki/authorities/local/root.crt > "$ca_file" 2>/dev/null; then
            chmod 644 "$ca_file"
        fi
        if [[ -s "$ca_file" ]] && caddy_compose exec -T client1 curl --silent --fail --cacert /ca/root.crt \
            --connect-to localhost:443:caddy:443 https://localhost/health >/dev/null 2>&1; then caddy_ready=1; break; fi
        sleep 1
    done
    (( caddy_ready )) || { echo "Caddy internal TLS did not become ready" >&2; return 1; }
    smoke_check "$(smoke_url)"
    local redirect first1 first2 repeat1 repeat2 limited1 limited2 blocked restored
    redirect="$(caddy_compose exec -T client1 curl --silent --output /dev/null --write-out '%{http_code}' \
        --connect-to localhost:80:caddy:80 http://localhost/health)"
    [[ "$redirect" == 308 ]]
    request() {
        local client="$1" forged="$2"
        printf '테스트 요청입니다.\n' | caddy_compose exec -T "$client" curl --silent --show-error \
            --output /dev/null --write-out '%{http_code}' --cacert /ca/root.crt \
            --connect-to localhost:443:caddy:443 -H "X-Forwarded-For: $forged" \
            -F 'file=@-;filename=rate.txt' https://localhost/simplify
    }
    first1="$(request client1 198.51.100.10)"
    first2="$(request client2 198.51.100.10)"
    repeat1="$(request client1 198.51.100.11)"
    repeat2="$(request client2 198.51.100.12)"
    limited1="$(request client1 198.51.100.13)"
    limited2="$(request client2 198.51.100.14)"
    [[ "$first1" != 429 && "$first2" != 429 && "$repeat1" != 429 && "$repeat2" != 429 && "$limited1" == 429 && "$limited2" == 429 ]]

    bash "$DEPLOY_DIR/blocklist.sh" add 10.203.0.10
    blocked=""
    for _ in {1..25}; do
        blocked="$(caddy_compose exec -T client1 curl --silent --output /dev/null --write-out '%{http_code}' \
            --cacert /ca/root.crt --connect-to localhost:443:caddy:443 https://localhost/health)"
        [[ "$blocked" == 403 ]] && break
        sleep 0.2
    done
    [[ "$blocked" == 403 ]]
    bash "$DEPLOY_DIR/blocklist.sh" remove 10.203.0.10
    restored=""
    for _ in {1..25}; do
        restored="$(caddy_compose exec -T client1 curl --silent --output /dev/null --write-out '%{http_code}' \
            --cacert /ca/root.crt --connect-to localhost:443:caddy:443 https://localhost/health)"
        [[ "$restored" == 200 ]] && break
        sleep 0.2
    done
    [[ "$restored" == 200 ]]
    caddy_compose cp caddy:/data/access.json "$WORK_DIR/caddy-access.json"
    python3 - "$WORK_DIR/caddy-access.json" <<'PY'
import json
from pathlib import Path
import sys
entries = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines()]
clients = {entry["request"]["remote_ip"] for entry in entries if entry.get("request", {}).get("remote_ip")}
assert {"10.203.0.10", "10.203.0.11"} <= clients, clients
assert any(entry.get("path") == "/health" and "status" in entry and "duration" in entry and "ts" in entry for entry in entries)
PY
    echo "Caddy internal TLS, per-client limits, XFF spoof rejection, blocklist, and access logs passed."
)
cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
    docker image rm "$BROKEN_IMAGE" "$PROXY_IMAGE" "$ROLLBACK_IMAGE" >/dev/null 2>&1 || true
    (( IMAGE_PROVIDED )) || docker image rm "$GOOD_IMAGE" >/dev/null 2>&1 || true
    [[ ! -e "$WORK_DIR/nginx-routes.conf.original" ]] || cp "$WORK_DIR/nginx-routes.conf.original" "$DEPLOY_DIR/nginx-routes.conf"
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

if (( IMAGE_PROVIDED )); then docker image inspect "$GOOD_IMAGE" >/dev/null 2>&1 || docker pull "$GOOD_IMAGE"; else IMAGE="$GOOD_IMAGE" compose build api-1 api-2; fi
export IMAGE="$GOOD_IMAGE"
compose build proxy
test_caddy
IMAGE="$GOOD_IMAGE" compose up -d --no-build --wait --wait-timeout 180 api-1 api-2 proxy
python3 "$REPO_ROOT/scripts/smoke.py" "http://127.0.0.1:$HOST_PORT" --expected-model-version "$MODEL_VERSION"

cat > "$WORK_DIR/Dockerfile.broken" <<EOF
FROM $GOOD_IMAGE
CMD ["python", "-c", "import time; time.sleep(3600)"]
EOF
docker build --tag "$BROKEN_IMAGE" --file "$WORK_DIR/Dockerfile.broken" "$REPO_ROOT"

: > "$WORK_DIR/statuses"
(while [[ ! -e "$WORK_DIR/stop-requests" ]]; do
    curl --silent --output /dev/null --max-time 2 --write-out '%{http_code}\n' "http://127.0.0.1:$HOST_PORT/health" >> "$WORK_DIR/statuses" || echo 000 >> "$WORK_DIR/statuses"
    sleep 0.1
done) &
request_pid=$!
trap 'touch "$WORK_DIR/stop-requests"; wait "$request_pid" 2>/dev/null || true; cleanup' EXIT
bash "$DEPLOY_DIR/rolling.sh" "$GOOD_IMAGE" "$MODEL_VERSION"
touch "$WORK_DIR/stop-requests"
wait "$request_pid"
if ! awk '$1 !~ /^2/ { failed=1 } END { exit failed }' "$WORK_DIR/statuses"; then
    echo "Requests failed during successful rolling replacement" >&2
    exit 1
fi
proxy_id="$(compose ps --all --quiet proxy)"
docker exec "$proxy_id" grep -q 'limit_conn_status 429' /etc/nginx/templates/default.conf.template
compose restart proxy >/dev/null
for _ in {1..30}; do
    if curl --fail --silent --max-time 2 "http://127.0.0.1:$HOST_PORT/health" >/dev/null; then break; fi
    sleep 1
done
docker exec "$proxy_id" grep -q 'limit_conn_status 429' /etc/nginx/conf.d/default.conf
docker tag "$GOOD_IMAGE" "$ROLLBACK_IMAGE"
docker exec "$proxy_id" sh -c 'echo "# rollback-skip-marker" >> /etc/nginx/templates/default.conf.template'
printf '%s\n' "$ROLLBACK_IMAGE" > "$DEPLOY_STATE_FILE"
"$DEPLOY_DIR/rollback.sh" "$MODEL_VERSION"
docker exec "$proxy_id" grep -q 'rollback-skip-marker' /etc/nginx/templates/default.conf.template

docker image inspect "$PROXY_IMAGE" --format '{{.Id}}' > "$WORK_DIR/proxy-image-before-failure"
api1_before_failure="$(compose ps --all --quiet api-1 | xargs -r docker inspect --format '{{.Config.Image}}')"
api2_before_failure="$(compose ps --all --quiet api-2 | xargs -r docker inspect --format '{{.Config.Image}}')"
cp "$DEPLOY_DIR/nginx-routes.conf" "$WORK_DIR/nginx-routes.conf.original"
printf '\n# test-only proxy image change\n' >> "$DEPLOY_DIR/nginx-routes.conf"
if bash "$DEPLOY_DIR/rolling.sh" "$BROKEN_IMAGE" "$MODEL_VERSION"; then
    echo "Expected unhealthy rolling deployment to fail" >&2
    exit 1
fi
cp "$WORK_DIR/nginx-routes.conf.original" "$DEPLOY_DIR/nginx-routes.conf"
docker image inspect "$PROXY_IMAGE" --format '{{.Id}}' > "$WORK_DIR/proxy-image-after-failure"
if [[ "$(cat "$WORK_DIR/proxy-image-before-failure")" != "$(cat "$WORK_DIR/proxy-image-after-failure")" ]]; then
    echo "Proxy image was not restored after the failed deployment" >&2
    exit 1
fi
for service in api-1 api-2; do
    container="$(compose ps --all --quiet "$service")"
    expected="$api1_before_failure"
    [[ "$service" == api-2 ]] && expected="$api2_before_failure"
    actual="$(docker inspect --format '{{.Config.Image}}' "$container")"
    if [[ "$actual" != "$expected" ]]; then
        echo "$service image was not restored: expected $expected, got $actual" >&2
        exit 1
    fi
done
curl --fail --silent "http://127.0.0.1:$HOST_PORT/health" >/dev/null || {
    echo "Health check failed after rolling rollback" >&2
    exit 1
}
echo "Rolling replacement kept requests healthy and restored both containers after failure."
