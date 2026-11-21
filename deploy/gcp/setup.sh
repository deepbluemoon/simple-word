#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/common.sh"
CONFIGURED_PROJECT=$PROJECT
BUDGET_ONLY=false
while (($#)); do
  case "$1" in
    --project) PROJECT=${2:?--project requires an ID}; shift 2 ;;
    --project=*) PROJECT=${1#*=}; shift ;;
    --budget-only) BUDGET_ONLY=true; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
if [[ "$PROJECT" != "$CONFIGURED_PROJECT" ]]; then
  echo "This setup is scoped to project $CONFIGURED_PROJECT" >&2
  exit 2
fi

if [[ "$BUDGET_ONLY" == true ]]; then
  gcloud_project services enable billingbudgets.googleapis.com
else
  gcloud_project services enable run.googleapis.com artifactregistry.googleapis.com storage.googleapis.com monitoring.googleapis.com logging.googleapis.com iamcredentials.googleapis.com iam.googleapis.com sts.googleapis.com billingbudgets.googleapis.com
fi

BUDGET_ID=1cdd521d-0564-4c7b-9591-589b5bc7fd77
gcloud_project billing budgets update "$BUDGET_ID" --billing-account="$BILLING_ACCOUNT" --display-name='simple-word monthly $30' --budget-amount=39937KRW
if [[ "$BUDGET_ONLY" == true ]]; then
  exit 0
fi

if ! gcloud_project artifacts repositories describe "$REPOSITORY" --location="$REGION" >/dev/null 2>&1; then
  gcloud_project artifacts repositories create "$REPOSITORY" --location="$REGION" --repository-format=docker --description='simple-word service images'
fi

if ! gcloud_project storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcloud_project storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access --public-access-prevention
fi
tmp_lifecycle="$(mktemp -d)"
trap 'rm -rf "$tmp_lifecycle"' EXIT
gcloud_project storage buckets describe "gs://$BUCKET" --format=json >"$tmp_lifecycle/current.json"
python3 "$(dirname -- "$0")/merge_lifecycle.py" "$tmp_lifecycle/current.json" "$(dirname -- "$0")/lifecycle.json" "$tmp_lifecycle/merged.json"
gcloud_project storage buckets update "gs://$BUCKET" --public-access-prevention --lifecycle-file="$tmp_lifecycle/merged.json"

for account in "$RUNTIME_SA" "$DEPLOY_SA"; do
  if ! gcloud_project iam service-accounts describe "$account@$PROJECT.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud_project iam service-accounts create "$account" --display-name="simple-word ${account#simple-word-}"
  fi
done
gcloud_project storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$RUNTIME_SA@$PROJECT.iam.gserviceaccount.com" --role=roles/storage.objectViewer
RUN_PUBLIC_ROLE=simpleWordPublicServiceIam
if gcloud_project iam roles describe "$RUN_PUBLIC_ROLE" >/dev/null 2>&1; then
  gcloud_project iam roles update "$RUN_PUBLIC_ROLE" --title='simple-word public service IAM' --description='Allows the deployer to set Cloud Run service IAM policies for the public service' --permissions=run.services.setIamPolicy --stage=GA
else
  gcloud_project iam roles create "$RUN_PUBLIC_ROLE" --title='simple-word public service IAM' --description='Allows the deployer to set Cloud Run service IAM policies for the public service' --permissions=run.services.setIamPolicy --stage=GA
fi
gcloud_project projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --role=roles/run.developer --condition=None
gcloud_project projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --role="projects/$PROJECT/roles/$RUN_PUBLIC_ROLE" --condition=None
gcloud_project artifacts repositories add-iam-policy-binding "$REPOSITORY" --location="$REGION" --member="serviceAccount:$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --role=roles/artifactregistry.writer
gcloud_project iam service-accounts add-iam-policy-binding "$RUNTIME_SA@$PROJECT.iam.gserviceaccount.com" --member="serviceAccount:$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --role=roles/iam.serviceAccountUser

if ! gcloud_project iam workload-identity-pools describe "$POOL" --location=global >/dev/null 2>&1; then
  gcloud_project iam workload-identity-pools create "$POOL" --location=global --display-name='GitHub Actions'
fi
if gcloud_project iam workload-identity-pools providers describe "$PROVIDER" --location=global --workload-identity-pool="$POOL" >/dev/null 2>&1; then
  provider_verb=update-oidc
else
  provider_verb=create-oidc
fi
gcloud_project iam workload-identity-pools providers "$provider_verb" "$PROVIDER" --location=global --workload-identity-pool="$POOL" --display-name='simple-word main' --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping='google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref' --attribute-condition="assertion.repository == 'deepbluemoon/simple-word' && assertion.repository_owner_id == '105283439' && assertion.ref == 'refs/heads/main'"
gcloud_project iam service-accounts add-iam-policy-binding "$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --member="principalSet://iam.googleapis.com/projects/$(gcloud_project projects describe "$PROJECT" --format='value(projectNumber)')/locations/global/workloadIdentityPools/$POOL/attribute.repository/deepbluemoon/simple-word" --role=roles/iam.workloadIdentityUser
gcloud_project storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com" --role=roles/storage.objectViewer
