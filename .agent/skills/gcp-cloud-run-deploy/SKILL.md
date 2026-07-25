---
name: gcp-cloud-run-deploy
description: Standard operating procedure (SOP) for containerizing, configuring, and deploying production-ready serverless microservices to Google Cloud Run using gcloud CLI, Terraform IaC, and Knative service definitions.
---

# Google Cloud Run Deployment Skill

This skill defines the mandatory standard operating procedure (SOP) for packaging applications into secure multi-stage Docker containers, generating declarative Knative service manifests (`CloudRunService.yaml`), and deploying scalable services to Google Cloud Run. All deployments must enforce least-privilege IAM, configure appropriate concurrency and resource limits, and disable unauthenticated public ingress unless explicitly required for external frontend endpoints.

## Prerequisites
- Google Cloud SDK (`gcloud`) CLI installed and authenticated (`gcloud auth login`).
- Docker engine or Google Cloud Build (`gcloud builds submit`) available for container image compilation.
- Target GCP Project ID configured (`gcloud config set project [PROJECT_ID]`).
- Cloud Run API (`run.googleapis.com`) and Artifact Registry API (`artifactregistry.googleapis.com`) enabled.

## Step-by-Step Procedure

### Step 1: Build and Push Multi-Stage Container Image
To minimize vulnerability surface area and image size, compile the backend or frontend application using a multi-stage Dockerfile and push to Google Artifact Registry (GAR).

```bash
# Set environment variables
export PROJECT_ID=$(gcloud config get-value project)
export REGION="us-central1"
export REPO_NAME="scrum-team-repo"
export IMAGE_NAME="backend-service"
export TAG="latest"

# Create Artifact Registry Docker repository if it does not exist
gcloud artifacts repositories create $REPO_NAME \
    --repository-format=docker \
    --location=$REGION \
    --description="Docker repository for multi-agent Scrum team microservices"

# Submit build to Google Cloud Build
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$TAG .
```

### Step 2: Deploy to Cloud Run via Declarative Manifest
Instead of passing ad-hoc CLI flags, maintain declarative infrastructure as code by deploying via Knative YAML manifests (`templates/CloudRunService.yaml`).

```bash
# Deploy or update the Cloud Run service using declarative YAML
gcloud run services replace .agent/skills/gcp-cloud-run-deploy/templates/CloudRunService.yaml \
    --region=$REGION
```

Alternatively, deploy directly via CLI for imperative pipeline testing:
```bash
gcloud run deploy backend-service \
    --image=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$TAG \
    --region=$REGION \
    --platform=managed \
    --service-account=cloud-run-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --memory=1024Mi \
    --cpu=1 \
    --min-instances=1 \
    --max-instances=10 \
    --concurrency=80 \
    --timeout=300s \
    --no-allow-unauthenticated
```

### Step 3: Configure IAM Ingress Permissions
If the service is an internal microservice or agent orchestrator, restrict invocation strictly to authorized service accounts or Vertex AI Agent Engine identities:

```bash
# Grant invoker role to specific internal service account
gcloud run services add-iam-policy-binding backend-service \
    --region=$REGION \
    --member="serviceAccount:orchestrator-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.invoker"
```

If the service serves public frontend traffic, enable unauthenticated invocation:
```bash
gcloud run services add-iam-policy-binding frontend-app \
    --region=$REGION \
    --member="allUsers" \
    --role="roles/run.invoker"
```

## Verification & Troubleshooting

### Verification Command
Verify service health, readiness status, and assigned HTTPS URL:

```bash
# Describe service status
gcloud run services describe backend-service --region=us-central1 --format="value(status.url, status.conditions[0].status)"

# Perform HTTP liveness check
curl -f -H "Authorization: Bearer $(gcloud auth print-identity-token)" $(gcloud run services describe backend-service --region=us-central1 --format="value(status.url)")/health || echo "Health check failed"
```

### Common Errors and Solutions
- **Error: `PermissionDenied: 403 Cloud Run Service Account lacks permission to pull image`**
  - *Solution*: Ensure the Cloud Run runtime service account has `roles/artifactregistry.reader` on the Artifact Registry repository.
- **Error: `Container failed to start. Failed to bind to port 8080`**
  - *Solution*: Cloud Run injects the `$PORT` environment variable (default 8080). Ensure your application listens on `0.0.0.0:$PORT` and not localhost or a hardcoded non-8080 port.
- **Error: `504 Gateway Timeout / Resource exhaustion`**
  - *Solution*: Check CPU/Memory allocation in your manifest and adjust concurrency limits or scale out `max-instances`.
