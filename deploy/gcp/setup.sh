#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"

gcloud_project services enable run.googleapis.com artifactregistry.googleapis.com storage.googleapis.com monitoring.googleapis.com logging.googleapis.com iamcredentials.googleapis.com iam.googleapis.com sts.googleapis.com billingbudgets.googleapis.com

if ! gcloud_project artifacts repositories describe "$REPOSITORY" --location="$REGION" >/dev/null 2>&1; then
  gcloud_project artifacts repositories create "$REPOSITORY" --location="$REGION" --repository-format=docker --description='simple-word service images'
fi

if ! gcloud_project storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcloud_project storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access --public-access-prevention
fi
gcloud_project storage buckets update "gs://$BUCKET" --lifecycle-file="$(dirname -- "$0")/lifecycle.json"

for account in "$RUNTIME_SA" "$DEPLOY_SA"; do
  if ! gcloud_project iam service-accounts describe "$account@$PROJECT.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud_project iam service-accounts create "$account" --display-name="simple-word ${account#simple-word-}"
  fi
done
gcloud_project storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$RUNTIME_SA@$PROJECT.iam.gserviceaccount.com" --role=roles/storage.objectViewer
gcloud_project projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --role=roles/run.developer --condition=None
gcloud_project artifacts repositories add-iam-policy-binding "$REPOSITORY" --location="$REGION" --member="serviceAccount:$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --role=roles/artifactregistry.writer
gcloud_project iam service-accounts add-iam-policy-binding "$RUNTIME_SA@$PROJECT.iam.gserviceaccount.com" --member="serviceAccount:$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --role=roles/iam.serviceAccountUser

if ! gcloud_project iam workload-identity-pools describe "$POOL" --location=global >/dev/null 2>&1; then
  gcloud_project iam workload-identity-pools create "$POOL" --location=global --display-name='GitHub Actions'
fi
if ! gcloud_project iam workload-identity-pools providers describe "$PROVIDER" --location=global --workload-identity-pool="$POOL" >/dev/null 2>&1; then
  gcloud_project iam workload-identity-pools providers create-oidc "$PROVIDER" --location=global --workload-identity-pool="$POOL" --display-name='simple-word main' --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping='google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref' --attribute-condition="assertion.repository == 'deepbluemoon/simple-word' && assertion.ref == 'refs/heads/main'"
fi
gcloud_project iam service-accounts add-iam-policy-binding "$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --member="principalSet://iam.googleapis.com/projects/$(gcloud_project projects describe "$PROJECT" --format='value(projectNumber)')/locations/global/workloadIdentityPools/$POOL/attribute.repository/deepbluemoon/simple-word" --role=roles/iam.workloadIdentityUser

if ! gcloud_project billing budgets list --billing-account="$BILLING_ACCOUNT" --format='value(displayName)' | grep -Fxq 'simple-word monthly $5'; then
  gcloud_project billing budgets create --billing-account="$BILLING_ACCOUNT" --display-name='simple-word monthly $5' --budget-amount=6660KRW --calendar-period=month --filter-projects="projects/$PROJECT" --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
fi
