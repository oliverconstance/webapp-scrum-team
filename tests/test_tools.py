"""Unit and integration tests for Python ADK tools in tools/.

Verifies git branch/atomic commit creation, pull request generation, Secret Manager credential resolution,
and CI status checking using mock objects and pytest fixtures.
"""
import os
from unittest.mock import MagicMock, patch
import pytest

from tools.ci_tools import check_ci_status
from tools.git_tools import create_feature_branch_and_commit, create_pull_request
from tools.secret_tools import get_gcp_secret


@pytest.mark.unit
def test_get_gcp_secret_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test secret retrieval using environment variable mock override."""
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("MOCK_SECRET_GITHUB_APP_KEY", "mocked-private-key-data")

    result = get_gcp_secret("github-app-key", project_id="test-project")
    assert result == "mocked-private-key-data"


@pytest.mark.unit
@patch("tools.secret_tools.secretmanager.SecretManagerServiceClient")
def test_get_gcp_secret_api_call(mock_client_cls: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test secret retrieval via Google Cloud Secret Manager SDK client."""
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.delenv("MOCK_SECRET_API_KEY", raising=False)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.payload.data = b"super-secret-api-token"
    mock_client.access_secret_version.return_value = mock_response
    mock_client_cls.return_value = mock_client

    result = get_gcp_secret("api-key", project_id="test-project", version_id="1")
    assert result == "super-secret-api-token"
    mock_client.access_secret_version.assert_called_once_with(
        request={"name": "projects/test-project/secrets/api-key/versions/1"}
    )


@pytest.mark.unit
@patch("tools.git_tools._get_github_client")
def test_create_feature_branch_and_commit_atomic(mock_get_client: MagicMock) -> None:
    """Test creating a feature branch and committing files ATOMICALLY via PyGithub Git Data Tree mock."""
    mock_g = MagicMock()
    mock_repo = MagicMock()
    mock_get_client.return_value = mock_g
    mock_g.get_repo.return_value = mock_repo

    # Mock base ref and SHA
    mock_ref = MagicMock()
    mock_ref.object.sha = "base_sha_12345"
    mock_repo.get_git_ref.return_value = mock_ref
    mock_repo.create_git_ref.return_value = mock_ref

    # Mock Git Blob, Tree, and Commit objects
    mock_blob = MagicMock(sha="blob_sha_1")
    mock_repo.create_git_blob.return_value = mock_blob

    mock_tree = MagicMock(sha="tree_sha_1")
    mock_repo.get_git_tree.return_value = mock_tree
    mock_repo.create_git_tree.return_value = mock_tree

    mock_commit = MagicMock(sha="atomic_commit_sha_999")
    mock_repo.get_git_commit.return_value = mock_commit
    mock_repo.create_git_commit.return_value = mock_commit

    res = create_feature_branch_and_commit(
        repo_name="owner/repo",
        branch_name="feature/test-branch",
        files={"src/main.py": "print('hello')", "src/config.py": "PORT=8080"},
        commit_message="Atomic commit main and config",
        token="test_token",
    )

    assert res["status"] == "SUCCESS"
    assert res["commit_sha"] == "atomic_commit_sha_999"
    assert res["committed_files_count"] == 2
    assert res["atomic"] is True
    mock_repo.create_git_tree.assert_called_once()
    mock_repo.create_git_commit.assert_called_once()


@pytest.mark.unit
@patch("tools.git_tools._get_github_client")
def test_create_pull_request(mock_get_client: MagicMock) -> None:
    """Test opening a GitHub Pull Request via PyGithub mock."""
    mock_g = MagicMock()
    mock_repo = MagicMock()
    mock_get_client.return_value = mock_g
    mock_g.get_repo.return_value = mock_repo
    mock_repo.owner.login = "owner"

    # Simulate no existing PRs
    mock_repo.get_pulls.return_value = []

    mock_pr = MagicMock(number=42, html_url="https://github.com/owner/repo/pull/42")
    mock_repo.create_pull.return_value = mock_pr

    res = create_pull_request(
        repo_name="owner/repo",
        branch_name="feature/test-branch",
        title="New Feature PR",
        body="PR body",
        token="test_token",
    )

    assert res["status"] == "SUCCESS"
    assert res["pr_number"] == 42
    assert res["pr_url"] == "https://github.com/owner/repo/pull/42"
    assert res["already_existed"] is False


@pytest.mark.unit
@patch("tools.ci_tools._get_github_client")
def test_check_ci_status_with_skipped_checks(mock_get_client: MagicMock) -> None:
    """Test checking CI status when check runs include skipped/neutral steps without false negatives."""
    mock_g = MagicMock()
    mock_repo = MagicMock()
    mock_pr = MagicMock()
    mock_commit = MagicMock()

    mock_get_client.return_value = mock_g
    mock_g.get_repo.return_value = mock_repo
    mock_repo.get_pull.return_value = mock_pr
    mock_pr.head.sha = "head_sha_abc"
    mock_repo.get_commit.return_value = mock_commit

    mock_commit.get_combined_status().state = "success"

    mock_check_1 = MagicMock(name="Unit Tests", status="completed", conclusion="success", html_url="url1")
    mock_check_2 = MagicMock(name="Optional Integration", status="completed", conclusion="skipped", html_url="url2")
    mock_commit.get_check_runs.return_value = [mock_check_1, mock_check_2]

    res = check_ci_status("owner/repo", pr_number=42, token="test_token")

    assert res["status"] == "SUCCESS"
    assert res["ci_passed"] is True
    assert res["failed_checks"] == 0
    assert res["passed_checks"] == 2
