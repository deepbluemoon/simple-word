#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
gcloud_project storage cp "gs://$BUCKET/registry.json" "$tmp/registry.json"
python3 - "$tmp/registry.json" <<'PY'
import json, sys
registry = json.load(open(sys.argv[1], encoding="utf-8"))
if registry.get("champion") != "v2" or registry.get("canary") is not None or registry.get("shadow") is not None:
    raise SystemExit("Refusing deployment: registry must contain only champion=v2")
PY
for artifact in metadata.json encoder.onnx decoder.onnx; do
  gcloud_project storage ls "gs://$BUCKET/v2/$artifact" >/dev/null
done

gcloud_project run deploy simple-word --image="$IMAGE" --region="$REGION" --min=0 --max=2 --memory=1Gi --port=8000 --concurrency=2 --allow-unauthenticated --service-account="$RUNTIME_SA@$PROJECT.iam.gserviceaccount.com" --add-volume="mount-path=/app/models,type=cloud-storage,bucket=$BUCKET,readonly=true" --set-env-vars=MAX_CONCURRENT_SIMPLIFY=2
gcloud_project run services describe simple-word --region="$REGION" --format='value(status.url)'
