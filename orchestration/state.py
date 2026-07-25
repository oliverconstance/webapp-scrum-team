"""Shared State Definitions for Google ADK Multi-Agent Scrum Workflows.

Defines `ScrumSessionState` using Pydantic and TypedDict for type-safe state sharing across
`product_architect`, `cloud_backend`, `frontend`, and `qa_sec` personas executing inside
Google Vertex AI Agent Engine.
"""
from typing import Any, Dict, List, Optional, TypedDict
from pydantic import BaseModel, Field


class ScrumSessionState(TypedDict, total=False):
    """TypedDict representation of the multi-agent Scrum session state for ADK tool binding."""

    ticket_id: str
    feature_name: str
    pr_url: Optional[str]
    pr_number: Optional[int]
    ci_passed: bool
    retry_count: int
    feedback: str
    failed_criteria: List[str]
    status: str
    openapi_spec_path: Optional[str]
    architecture_summary: Optional[str]


class ScrumSessionStateModel(BaseModel):
    """Pydantic model representing state across iterative Scrum sprint loops."""

    ticket_id: str = Field(..., description="Unique execution ticket ID (e.g., TICKET-BACKEND-001).")
    feature_name: str = Field(..., description="Human-readable name of the feature being developed.")
    pr_url: Optional[str] = Field(default=None, description="URL of the generated GitHub Pull Request.")
    pr_number: Optional[int] = Field(default=None, description="Pull Request number.")
    ci_passed: bool = Field(default=False, description="Whether automated CI/CD checks have passed.")
    retry_count: int = Field(default=0, ge=0, description="Number of QA audit or CI failure retries.")
    feedback: str = Field(default="", description="Latest actionable feedback from qa_sec or CI logs.")
    failed_criteria: List[str] = Field(
        default_factory=list, description="List of specific Gherkin or security criteria that failed."
    )
    status: str = Field(
        default="IN_PROGRESS",
        description="Current sprint state: IN_PROGRESS, PASS, FAIL, CIRCUIT_BROKEN.",
    )
    openapi_spec_path: Optional[str] = Field(default=None, description="Path to generated OpenAPI contract.")
    architecture_summary: Optional[str] = Field(default=None, description="Summary of architectural decision.")

    def to_typed_dict(self) -> ScrumSessionState:
        """Convert Pydantic model instance to an ADK-compatible TypedDict."""
        return {
            "ticket_id": self.ticket_id,
            "feature_name": self.feature_name,
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "ci_passed": self.ci_passed,
            "retry_count": self.retry_count,
            "feedback": self.feedback,
            "failed_criteria": self.failed_criteria,
            "status": self.status,
            "openapi_spec_path": self.openapi_spec_path,
            "architecture_summary": self.architecture_summary,
        }

    @classmethod
    def from_typed_dict(cls, data: Dict[str, Any]) -> "ScrumSessionStateModel":
        """Instantiate Pydantic model from an ADK state dictionary."""
        return cls(**data)
