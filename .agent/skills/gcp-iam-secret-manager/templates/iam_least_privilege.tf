# Least Privilege IAM and Secret Manager Terraform Configuration
# Reference: https://registry.terraform.io/providers/hashicorp/google/latest/docs

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.38.0"
    }
  }
}

variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID where resources will be provisioned."
}

variable "region" {
  type        = string
  description = "The target GCP region (e.g., europe-west2 / London)."
  default     = "europe-west2"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev, staging, production)."
  default     = "production"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ------------------------------------------------------------------------------
# 1. Dedicated Least-Privilege Runtime Service Account
# ------------------------------------------------------------------------------
resource "google_service_account" "agent_runtime_sa" {
  account_id   = "scrum-agent-runtime-sa"
  display_name = "Scrum Team Multi-Agent Runtime Service Account"
  description  = "Least-privilege service account used by ADK agents and Cloud Run microservices."
}

# Grant Vertex AI user role for Gemini LLM execution inside Agent Engine
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

# Grant Cloud Trace and Logging writer roles for observability
resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

resource "google_project_iam_member" "trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

# ------------------------------------------------------------------------------
# 2. Secret Manager Container Provisioning
# ------------------------------------------------------------------------------
resource "google_secret_manager_secret" "github_app_key" {
  secret_id = "github-app-private-key"
  
  replication {
    auto {}
  }

  labels = {
    env        = var.environment
    managed-by = "terraform-scrum-team"
  }
}

resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key"
  
  replication {
    auto {}
  }

  labels = {
    env        = var.environment
    managed-by = "terraform-scrum-team"
  }
}

# ------------------------------------------------------------------------------
# 3. Granular IAM Secret Accessor Bindings (Resource Scoped)
# ------------------------------------------------------------------------------
resource "google_secret_manager_secret_iam_member" "github_key_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.github_app_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "gemini_key_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.gemini_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

# ------------------------------------------------------------------------------
# 4. Outputs
# ------------------------------------------------------------------------------
output "runtime_service_account_email" {
  description = "Email address of the least-privilege runtime service account."
  value       = google_service_account.agent_runtime_sa.email
}

output "github_app_secret_id" {
  description = "Resource ID of the GitHub App private key secret."
  value       = google_secret_manager_secret.github_app_key.id
}
