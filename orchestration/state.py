"""Shared State Definitions for Google ADK Multi-Agent Scrum Workflows.

Defines `ScrumSessionState` using Pydantic and TypedDict for type-safe state sharing across
`product_architect`, `cloud_backend`, `frontend`, and `qa_sec` personas executing inside
Google Vertex AI Agent Engine.
"""

from typing import Any, TypedDict

from pydantic import BaseModel, Field


class ScrumSessionState(TypedDict, total=False):
    """TypedDict representation of the multi-agent Scrum session state for ADK tool binding."""

    ticket_id: str
    feature_name: str
    ticket_type: str | None
    repo_name: str | None
    branch_name: str | None
    base_branch: str | None
    pr_url: str | None
    frontend_pr_url: str | None
    backend_pr_url: str | None
    pr_number: int | None
    ci_passed: bool
    retry_count: int
    feedback: str
    failed_criteria: list[str]
    status: str
    openapi_spec_path: str | None
    architecture_summary: str | None
    prd_content: str | None
    arch_spec_content: str | None
    iteration_history: list[dict[str, Any]]


class ScrumSessionStateModel(BaseModel):
    """Pydantic model representing state across iterative Scrum sprint loops."""

    ticket_id: str = Field(
        ...,
        description="Unique execution ticket ID (e.g., TICKET-BACKEND-001 or TICKET-FRONTEND-001).",
    )
    feature_name: str = Field(
        ..., description="Human-readable name of the feature being developed."
    )
    ticket_type: str = Field(
        default="BACKEND", description="Ticket category: BACKEND, FRONTEND, or FULLSTACK."
    )
    repo_name: str | None = Field(
        default=None, description="Full GitHub target repository (e.g., 'owner/repo')."
    )
    branch_name: str | None = Field(default=None, description="Feature branch name.")
    base_branch: str | None = Field(default="main", description="Base branch for PR creation.")
    pr_url: str | None = Field(
        default=None, description="URL of the generated GitHub Pull Request."
    )
    frontend_pr_url: str | None = Field(
        default=None, description="URL of the generated Frontend Pull Request."
    )
    backend_pr_url: str | None = Field(
        default=None, description="URL of the generated Backend Pull Request."
    )
    pr_number: int | None = Field(default=None, description="Pull Request number.")
    ci_passed: bool = Field(
        default=False, description="Whether automated CI/CD checks have passed."
    )
    retry_count: int = Field(
        default=0, ge=0, description="Number of QA audit or CI failure retries."
    )
    feedback: str = Field(
        default="", description="Latest actionable feedback from qa_sec or CI logs."
    )
    failed_criteria: list[str] = Field(
        default_factory=list,
        description="List of specific Gherkin or security criteria that failed.",
    )
    status: str = Field(
        default="IN_PROGRESS",
        description="Current sprint state: IN_PROGRESS, PASS, FAIL, CIRCUIT_BROKEN.",
    )
    openapi_spec_path: str | None = Field(
        default=None, description="Path to generated OpenAPI contract."
    )
    architecture_summary: str | None = Field(
        default=None, description="Summary of architectural decision."
    )
    prd_content: str | None = Field(
        default=None, description="Full text or summary of generated PRD."
    )
    arch_spec_content: str | None = Field(
        default=None, description="Full text or summary of 6-domain architecture spec."
    )
    iteration_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Historical audit log of all sprint iterations to prevent repeating defects.",
    )

    def record_iteration(self, persona: str, action: str, result: str, feedback: str = "") -> None:
        """Record an iteration entry in the retrospective state history."""
        self.iteration_history.append(
            {
                "retry_count": self.retry_count,
                "persona": persona,
                "action": action,
                "result": result,
                "feedback": feedback,
            }
        )

    def to_typed_dict(self) -> ScrumSessionState:
        """Convert Pydantic model instance to an ADK-compatible TypedDict."""
        return {
            "ticket_id": self.ticket_id,
            "feature_name": self.feature_name,
            "ticket_type": self.ticket_type,
            "repo_name": self.repo_name,
            "branch_name": self.branch_name,
            "base_branch": self.base_branch,
            "pr_url": self.pr_url,
            "frontend_pr_url": self.frontend_pr_url,
            "backend_pr_url": self.backend_pr_url,
            "pr_number": self.pr_number,
            "ci_passed": self.ci_passed,
            "retry_count": self.retry_count,
            "feedback": self.feedback,
            "failed_criteria": self.failed_criteria,
            "status": self.status,
            "openapi_spec_path": self.openapi_spec_path,
            "architecture_summary": self.architecture_summary,
            "prd_content": self.prd_content,
            "arch_spec_content": self.arch_spec_content,
            "iteration_history": self.iteration_history,
        }

    @classmethod
    def from_typed_dict(cls, data: dict[str, Any]) -> "ScrumSessionStateModel":
        """Instantiate Pydantic model from an ADK state dictionary."""
        return cls(**data)
