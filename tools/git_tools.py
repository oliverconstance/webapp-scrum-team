"""Git and GitHub operation tools using PyGithub for Google ADK Agents.

Provides robust, typed functions to create feature branches, commit multiple files,
and open pull requests against GitHub repositories with full error handling.
"""
import logging
import os
from typing import Any, Dict, Optional

from github import Github, GithubException
from github.Repository import Repository

logger = logging.getLogger(__name__)


def _get_github_client(token: Optional[str] = None) -> Github:
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
        # Check if we should fallback or raise an error
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
    files: Dict[str, str],
    commit_message: str,
    base_branch: str = "main",
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new feature branch from base branch and commit a set of files.

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
            repo.create_git_ref(ref=f"refs/{ref_path}", sha=base_sha)
            logger.info(f"Created new branch '{branch_name}' from '{base_branch}' ({base_sha[:7]}).")
        except GithubException as e:
            if e.status == 422:
                logger.info(f"Branch '{branch_name}' already exists. Updating existing branch.")
            else:
                raise RuntimeError(f"Failed to create branch '{branch_name}': {e.data}") from e

        # Commit files sequentially or via git tree
        committed_files = []
        latest_sha = base_sha
        for file_path, content in files.items():
            try:
                # Check if file already exists on branch
                existing_file = repo.get_contents(file_path, ref=branch_name)
                if not isinstance(existing_file, list):
                    # Update file
                    res = repo.update_file(
                        path=file_path,
                        message=commit_message,
                        content=content,
                        sha=existing_file.sha,
                        branch=branch_name,
                    )
                    latest_sha = res["commit"].sha
                    committed_files.append(file_path)
            except GithubException as e:
                if e.status == 404:
                    # Create file
                    res = repo.create_file(
                        path=file_path,
                        message=commit_message,
                        content=content,
                        branch=branch_name,
                    )
                    latest_sha = res["commit"].sha
                    committed_files.append(file_path)
                else:
                    raise RuntimeError(f"Failed to commit file '{file_path}': {e.data}") from e

        return {
            "status": "SUCCESS",
            "repo_name": repo_name,
            "branch_name": branch_name,
            "commit_sha": latest_sha,
            "committed_files_count": len(committed_files),
            "committed_files": committed_files,
        }
    except Exception as e:
        logger.exception(f"Error in create_feature_branch_and_commit: {e}")
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
    token: Optional[str] = None,
) -> Dict[str, Any]:
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
        existing_prs = repo.get_pulls(state="open", head=f"{repo.owner.login}:{branch_name}", base=base_branch)
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
