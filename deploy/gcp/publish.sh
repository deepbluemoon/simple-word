#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

gcloud_project auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build --platform linux/amd64 --tag "$IMAGE" "$ROOT"
docker push "$IMAGE"
printf '%s\n' "$IMAGE"
