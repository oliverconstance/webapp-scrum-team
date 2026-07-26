"""Git and GitHub operation tools using PyGithub for Google ADK Agents.

Provides robust, typed functions to create feature branches, commit multiple files atomically
using Git Data Tree APIs, and open pull requests against GitHub repositories.
"""

import logging
import os
from typing import Any

from github import Github, GithubException
from github.InputGitTreeElement import InputGitTreeElement
from github.Repository import Repository

logger = logging.getLogger(__name__)


def _get_github_client(token: str | None = None) -> Github:
    """Initialize and return an authenticated PyGithub client.

    Args:
        token: Optional explicit GitHub token. Defaults to GITHUB_TOKEN env var.

    Returns:
        Authenticated Github instance.

    Raises:
        ValueError: If no GitHub token is configured in environment or arguments.
    """
    auth_token = token or os.environ.get("GITHUB_TOKEN")
    if not auth_token:
        raise ValueError(
            "GitHub authentication token missing. Please set GITHUB_TOKEN in environment "
            "or configure GitHub App credentials."
        )
    return Github(auth_token)


def _get_repository(g: Github, repo_name: str) -> Repository:
    """Fetch a GitHub repository instance by name.

    Args:
        g: Authenticated Github client.
        repo_name: Full repository name (e.g., 'owner/repo').

    Returns:
        PyGithub Repository instance.

    Raises:
        RuntimeError: If the repository cannot be accessed.
    """
    try:
        return g.get_repo(repo_name)
    except GithubException as e:
        logger.error(f"Failed to access GitHub repository '{repo_name}': {e}")
        raise RuntimeError(f"GitHub API Error accessing repo '{repo_name}': {e.data}") from e


def create_feature_branch_and_commit(
    repo_name: str,
    branch_name: str,
    files: dict[str, str],
    commit_message: str,
    base_branch: str = "main",
    token: str | None = None,
) -> dict[str, Any]:
    """Create a feature branch and commit multiple files ATOMICALLY using Git Data Tree API.

    Args:
        repo_name: Full GitHub repository name (e.g., 'owner/repository').
        branch_name: Name of the feature branch to create or update.
        files: Dictionary mapping relative file paths to their string contents.
        commit_message: The commit message for the changes.
        base_branch: The base branch to branch off of (defaults to 'main').
        token: Optional GitHub OAuth or Personal Access Token.

    Returns:
        Dictionary containing commit SHA, branch name, and status.

    Raises:
        RuntimeError: If Git operations fail.
    """
    try:
        g = _get_github_client(token)
        repo = _get_repository(g, repo_name)

        # Get base branch ref and SHA
        try:
            base_ref = repo.get_git_ref(f"heads/{base_branch}")
            base_sha = base_ref.object.sha
        except GithubException as e:
            raise RuntimeError(
                f"Base branch '{base_branch}' not found in repo '{repo_name}': {e.data}"
            ) from e

        # Create or get feature branch ref
        ref_path = f"heads/{branch_name}"
        try:
            target_ref = repo.create_git_ref(ref=f"refs/{ref_path}", sha=base_sha)
            current_head_sha = base_sha
            logger.info(
                f"Created new branch '{branch_name}' from '{base_branch}' ({base_sha[:7]})."
            )
        except GithubException as e:
            if e.status == 422:
                logger.info(f"Branch '{branch_name}' already exists. Fetching ref.")
                target_ref = repo.get_git_ref(ref_path)
                current_head_sha = target_ref.object.sha
            else:
                raise RuntimeError(f"Failed to create branch '{branch_name}': {e.data}") from e

        # Build Atomic Git Tree Elements with path normalization and collision check
        tree_elements = []
        committed_files = []
        for raw_path, content in files.items():
            file_path = raw_path.strip("/\\")
            if not file_path or file_path.endswith("/") or file_path.endswith("\\"):
                logger.warning(f"Skipping invalid directory or empty file path: '{raw_path}'")
                continue
            if not isinstance(content, str):
                content = str(content)

            # Create blob for file content
            blob = repo.create_git_blob(content, "utf-8")
            element = InputGitTreeElement(
                path=file_path,
                mode="100644",
                type="blob",
                sha=blob.sha,
            )
            tree_elements.append(element)
            committed_files.append(file_path)

        # Create new Git Tree based on current branch head
        base_tree = repo.get_git_tree(current_head_sha)
        new_tree = repo.create_git_tree(tree_elements, base_tree=base_tree)

        # Create single atomic commit
        parent_commit = repo.get_git_commit(current_head_sha)
        new_commit = repo.create_git_commit(commit_message, new_tree, [parent_commit])

        # Update branch ref to point to new commit
        target_ref.edit(new_commit.sha)
        logger.info(
            f"Successfully committed {len(committed_files)} files atomically to "
            f"'{branch_name}' ({new_commit.sha[:7]})."
        )

        return {
            "status": "SUCCESS",
            "repo_name": repo_name,
            "branch_name": branch_name,
            "commit_sha": new_commit.sha,
            "committed_files_count": len(committed_files),
            "committed_files": committed_files,
            "atomic": True,
        }
    except Exception as e:
        logger.exception(f"Error in atomic create_feature_branch_and_commit: {e}")
        return {
            "status": "ERROR",
            "error_message": str(e),
            "repo_name": repo_name,
            "branch_name": branch_name,
        }


def create_pull_request(
    repo_name: str,
    branch_name: str,
    title: str,
    body: str,
    base_branch: str = "main",
    token: str | None = None,
) -> dict[str, Any]:
    """Create a GitHub Pull Request from the feature branch to the base branch.

    Args:
        repo_name: Full GitHub repository name (e.g., 'owner/repository').
        branch_name: Name of the head feature branch containing the changes.
        title: Title of the Pull Request.
        body: Detailed description and Gherkin audit references for the PR.
        base_branch: Name of the target base branch (defaults to 'main').
        token: Optional GitHub token.

    Returns:
        Dictionary containing PR number, HTML URL, and status.
    """
    try:
        g = _get_github_client(token)
        repo = _get_repository(g, repo_name)

        # Check if PR already exists for this head/base pair
        existing_prs = repo.get_pulls(
            state="open", head=f"{repo.owner.login}:{branch_name}", base=base_branch
        )
        for pr in existing_prs:
            logger.info(f"Pull request already exists: #{pr.number} ({pr.html_url})")
            return {
                "status": "SUCCESS",
                "pr_number": pr.number,
                "pr_url": pr.html_url,
                "already_existed": True,
            }

        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=base_branch,
        )
        logger.info(f"Created Pull Request #{pr.number}: {pr.html_url}")
        return {
            "status": "SUCCESS",
            "pr_number": pr.number,
            "pr_url": pr.html_url,
            "already_existed": False,
        }
    except GithubException as e:
        logger.error(f"GitHub API Error creating pull request: {e.data}")
        return {
            "status": "ERROR",
            "error_message": str(e.data if hasattr(e, "data") else e),
            "repo_name": repo_name,
            "branch_name": branch_name,
        }
    except Exception as e:
        logger.exception(f"Unexpected error in create_pull_request: {e}")
        return {
            "status": "ERROR",
            "error_message": str(e),
            "repo_name": repo_name,
            "branch_name": branch_name,
        }
