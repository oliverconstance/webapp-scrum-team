"""CI/CD Workflow and Pull Request check status monitoring tools for Google ADK Agents.

Provides real-time inspection of GitHub Actions build statuses, test suites,
and linter checks for feature pull requests.
"""

import logging
from typing import Any

from github import GithubException

from tools.git_tools import _get_github_client, _get_repository

logger = logging.getLogger(__name__)

# Check run conclusions that indicate explicit failure
FAILURE_CONCLUSIONS = {"failure", "timed_out", "cancelled", "action_required"}


def check_ci_status(repo_name: str, pr_number: int, token: str | None = None) -> dict[str, Any]:
    """Check the CI/CD build and check run status of a specific Pull Request.

    Differentiates explicit failures (failure, timed_out, cancelled) from benign states
    (success, skipped, neutral).

    Args:
        repo_name: Full GitHub repository name (e.g., 'owner/repository').
        pr_number: Pull Request number.
        token: Optional GitHub authentication token.

    Returns:
        Dictionary summarizing CI pass/fail status, check runs, and commit SHA.
    """
    try:
        g = _get_github_client(token)
        repo = _get_repository(g, repo_name)
        pr = repo.get_pull(pr_number)

        head_sha = pr.head.sha
        commit = repo.get_commit(head_sha)

        # Retrieve Combined Status (legacy status API) and Check Runs (GitHub Actions)
        combined_status = commit.get_combined_status().state  # 'success', 'failure', 'pending'
        check_runs = commit.get_check_runs()

        total_checks = 0
        passed_checks = 0
        skipped_checks = 0
        failed_checks = 0
        pending_checks = 0
        check_details = []

        for check in check_runs:
            total_checks += 1
            conclusion = (check.conclusion or "").lower()

            if check.status != "completed":
                pending_checks += 1
            elif conclusion in FAILURE_CONCLUSIONS:
                failed_checks += 1
            elif conclusion in ("skipped", "neutral", "stale"):
                skipped_checks += 1
            else:
                # Includes 'success'
                passed_checks += 1

            check_details.append(
                {
                    "name": check.name,
                    "status": check.status,
                    "conclusion": check.conclusion,
                    "html_url": check.html_url,
                }
            )

        # Determine overall boolean CI passed state
        if total_checks > 0:
            ci_passed = (failed_checks == 0) and (pending_checks == 0)
            state_summary = (
                "SUCCESS" if ci_passed else ("PENDING" if pending_checks > 0 else "FAILURE")
            )
        else:
            # Fallback to combined commit status if no check runs found
            ci_passed = combined_status == "success"
            state_summary = combined_status.upper()

        logger.info(
            f"CI status for PR #{pr_number} ({head_sha[:7]}): {state_summary} ({passed_checks} passed, {skipped_checks} skipped, {failed_checks} failed)"
        )

        return {
            "status": "SUCCESS",
            "repo_name": repo_name,
            "pr_number": pr_number,
            "head_sha": head_sha,
            "ci_passed": ci_passed,
            "state_summary": state_summary,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "skipped_checks": skipped_checks,
            "failed_checks": failed_checks,
            "pending_checks": pending_checks,
            "check_details": check_details,
        }
    except GithubException as e:
        logger.error(f"GitHub API error retrieving CI status for PR #{pr_number}: {e.data}")
        return {
            "status": "ERROR",
            "error_message": str(e.data if hasattr(e, "data") else e),
            "repo_name": repo_name,
            "pr_number": pr_number,
            "ci_passed": False,
        }
    except Exception as e:
        logger.exception(f"Unexpected error in check_ci_status: {e}")
        return {
            "status": "ERROR",
            "error_message": str(e),
            "repo_name": repo_name,
            "pr_number": pr_number,
            "ci_passed": False,
        }
