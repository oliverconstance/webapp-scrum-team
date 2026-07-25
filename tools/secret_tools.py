"""Google Cloud Secret Manager runtime tool for ADK Agents.

Provides secure, typed resolution of sensitive runtime secrets (e.g., GitHub App private keys,
API tokens, database credentials) using least-privilege IAM Workload Identity Federation.
"""
import logging
import os
from typing import Optional

from google.api_core.exceptions import GoogleAPICallError, PermissionDenied
from google.cloud import secretmanager

logger = logging.getLogger(__name__)


def get_gcp_secret(secret_id: str, project_id: Optional[str] = None, version_id: str = "latest") -> str:
    """Retrieve a secret payload from Google Cloud Secret Manager.

    Args:
        secret_id: The resource identifier of the secret (e.g., 'github-app-private-key').
        project_id: The GCP Project ID. Defaults to GCP_PROJECT_ID environment variable.
        version_id: The secret version to fetch (defaults to 'latest').

    Returns:
        The decrypted secret payload as a UTF-8 string.

    Raises:
        ValueError: If project_id cannot be resolved.
        RuntimeError: If secret resolution fails due to permission or API errors.
    """
    target_project = project_id or os.environ.get("GCP_PROJECT_ID")
    if not target_project:
        raise ValueError(
            "GCP Project ID must be provided explicitly or configured via GCP_PROJECT_ID env var."
        )

    # Allow local override via environment variable for unit testing outside GCP
    env_override_key = f"MOCK_SECRET_{secret_id.upper().replace('-', '_')}"
    if env_override_key in os.environ:
        logger.warning(f"Returning mocked environment override for secret '{secret_id}'.")
        return os.environ[env_override_key]

    try:
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{target_project}/secrets/{secret_id}/versions/{version_id}"
        
        logger.info(f"Accessing Secret Manager payload for '{secret_id}' (version: {version_id})...")
        response = client.access_secret_version(request={"name": secret_name})
        payload_bytes: bytes = response.payload.data
        return payload_bytes.decode("utf-8")
    except PermissionDenied as e:
        logger.error(f"Permission denied accessing secret '{secret_id}'. Verify IAM least-privilege role binding.")
        raise RuntimeError(
            f"IAM PermissionDenied accessing secret '{secret_id}' in project '{target_project}'. "
            "Ensure the runtime service account has 'roles/secretmanager.secretAccessor'."
        ) from e
    except GoogleAPICallError as e:
        logger.error(f"GCP API error accessing secret '{secret_id}': {e}")
        raise RuntimeError(f"GCP SecretManager API failure for '{secret_id}': {e.message}") from e
    except Exception as e:
        logger.exception(f"Unexpected error retrieving GCP secret '{secret_id}': {e}")
        raise RuntimeError(f"Failed to retrieve secret '{secret_id}': {str(e)}") from e
