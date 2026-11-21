#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

if [[ $# != 2 || ( "$1" != add && "$1" != remove ) ]]; then
    echo "Usage: $0 add|remove <IP-or-CIDR>" >&2
    exit 2
fi
BLOCKLIST_FILE="${BLOCKLIST_FILE:-$DEPLOY_DIR/blocklist.conf}"
[[ -f "$BLOCKLIST_FILE" && -w "$BLOCKLIST_FILE" ]] || { echo "Blocklist is not writable: $BLOCKLIST_FILE" >&2; exit 1; }
backup="$(mktemp)"
cp "$BLOCKLIST_FILE" "$backup"
cleanup() { rm -f "$backup"; }
trap cleanup EXIT

python3 - "$BLOCKLIST_FILE" "$1" "$2" <<'PY'
from ipaddress import ip_network
from pathlib import Path
import sys

path = Path(sys.argv[1])
action, network = sys.argv[2:]
entry = str(ip_network(network, strict=False))
lines = path.read_text(encoding="utf-8").splitlines()
entries = [line.partition("#")[0].strip().removeprefix("deny ").removesuffix(";").strip()
           for line in lines if line.partition("#")[0].strip().startswith("deny ")]
if action == "add":
    if entry not in entries:
        lines.append(f"deny {entry};")
elif entry not in entries:
    raise SystemExit(f"Blocklist entry not found: {entry}")
else:
    removed = False
    kept = []
    for line in lines:
        code = line.partition("#")[0].strip()
        if not removed and code.startswith("deny ") and code[5:].removesuffix(";").strip() == entry:
            removed = True
        else:
            kept.append(line)
    lines = kept
path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
PY

if ! compose exec -T proxy nginx -t || ! compose exec -T proxy nginx -s reload; then
    cat "$backup" > "$BLOCKLIST_FILE"
    compose exec -T proxy nginx -t && compose exec -T proxy nginx -s reload || true
    exit 1
fi
