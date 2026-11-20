#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT=${PROJECT:-simple-word-515207}
REGION=asia-northeast3
REPOSITORY=simple-word
BUCKET=simple-word-515207-models
RUNTIME_SA=simple-word-runtime
DEPLOY_SA=simple-word-deployer
POOL=simple-word-github
PROVIDER=github-main
BILLING_ACCOUNT=01CD77-714EC7-529B5D
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPOSITORY}/api:${IMAGE_TAG:-latest}"

gcloud_project() { gcloud "$@" --project="$PROJECT"; }
