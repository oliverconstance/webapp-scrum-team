---
name: gcp-iam-secret-manager
description: Standard operating procedure (SOP) for configuring least-privilege IAM service accounts, managing sensitive credentials in Google Cloud Secret Manager, and securely binding secrets to runtime agents and Cloud Run services.
---

# GCP IAM & Secret Manager Skill

This skill defines the mandatory standard operating procedure (SOP) for managing authentication, authorization, and sensitive secrets within Google Cloud Platform (GCP). Never hardcode API keys, database passwords, or private keys in source code or unencrypted environment variables. All credentials must reside in Google Cloud Secret Manager and be accessed at runtime via dedicated least-privilege IAM Service Accounts using Workload Identity Federation (WIF) or Cloud Run runtime service accounts.

## Prerequisites
- Google Cloud SDK (`gcloud`) CLI installed and authenticated.
- Secret Manager API (`secretmanager.googleapis.com`) and IAM API (`iam.googleapis.com`) enabled.
- Terraform CLI installed for infrastructure as code (IaC) provisioning.
- Project Owner or Security Admin permissions to create IAM service accounts and assign policy bindings.

## Step-by-Step Procedure

### Step 1: Create Least-Privilege Runtime Service Account
Create dedicated runtime service accounts for each persona or service layer instead of using the default Compute Engine service account.

```bash
export PROJECT_ID=$(gcloud config get-value project)
export SA_NAME="cloud-run-runtime-sa"

# Create Service Account
gcloud iam service-accounts create $SA_NAME \
    --display-name="Least Privilege Runtime SA for Cloud Run & ADK Agents" \
    --description="Used by backend services and ADK orchestration to access required GCP APIs without over-privileging."
```

### Step 2: Provision Secrets in GCP Secret Manager
Create secrets in Secret Manager and populate them with initial payload data.

```bash
export SECRET_ID="github-app-private-key"

# Create Secret container
gcloud secrets create $SECRET_ID \
    --replication-policy="automatic" \
    --labels=env=production,managed-by=scrum-team

# Add secret version from a local secure file
gcloud secrets versions add $SECRET_ID --data-file=/path/to/private-key.pem
```

### Step 3: Bind IAM Secret Access Policies (Least Privilege)
Grant access strictly to the runtime service account using the granular `roles/secretmanager.secretAccessor` role scoped to the specific secret resource (never at the project root level if avoidable).

```bash
# Grant Secret Accessor role on the specific secret resource
gcloud secrets add-iam-policy-binding $SECRET_ID \
    --member="serviceAccount:$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

### Step 4: Access Secrets at Runtime in Python ADK
Within Python application code or custom ADK tools, use the official `google-cloud-secretmanager` SDK to access payloads dynamically at runtime:

```python
from google.cloud import secretmanager

def access_secret_version(project_id: str, secret_id: str, version_id: str = "latest") -> str:
    """Access the payload of the given secret version in GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
```

## Verification & Troubleshooting

### Verification Command
Test whether a service account has permission to access a secret payload using `gcloud` identity simulation or direct invocation:

```bash
# Check IAM policy binding on the secret
gcloud secrets get-iam-policy $SECRET_ID

# Test secret access (if running under authorized credentials)
gcloud secrets versions access latest --secret=$SECRET_ID
```

### Common Errors and Solutions
- **Error: `403 Permission 'secretmanager.versions.access' denied on resource`**
  - *Solution*: Verify that the executing runtime service account matches the account bound to `roles/secretmanager.secretAccessor`. In Cloud Run, ensure `serviceAccountName` in manifest matches `$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com`.
- **Error: `404 Secret [secret-id] not found or has no versions`**
  - *Solution*: Ensure you created at least one version (`gcloud secrets versions add`) and that you are querying the correct project ID and region.
- **Error: `Default credentials cannot be found`**
  - *Solution*: When running locally outside GCP, execute `gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS` to a valid Workload Identity credential configuration.
