"""Unit and integration tests for Google ADK Agent Orchestration and Circuit Breaker handoffs.

Verifies state serialization, QA JSON evaluation, retry counter incrementation, circuit
breaker tripping, iteration recording, dynamic config loading, and sequential/loop execution.
"""

from typing import Any, cast

import pytest

from orchestration.circuit_breaker import (
    CircuitBreakerTrippedError,
    evaluate_qa_feedback_and_break,
)
from orchestration.scrum_master import (
    LlmAgent,
    LoopAgent,
    create_scrum_team_orchestrator,
)
from orchestration.state import ScrumSessionStateModel


@pytest.mark.unit
def test_scrum_session_state_model_serialization() -> None:
    """Test Pydantic model serialization and TypedDict conversion with expanded fields."""
    state = ScrumSessionStateModel(
        ticket_id="TICKET-BACKEND-001",
        feature_name="Order Processing API",
        ticket_type="BACKEND",
        repo_name="owner/repo",
        branch_name="feature/orders",
        status="IN_PROGRESS",
    )
    assert state.retry_count == 0
    assert state.ci_passed is False
    assert state.ticket_type == "BACKEND"

    state.record_iteration("cloud_backend", "commit", "SUCCESS", "Pushed commit")
    assert len(state.iteration_history) == 1
    assert state.iteration_history[0]["persona"] == "cloud_backend"

    typed_dict = state.to_typed_dict()
    assert typed_dict["ticket_id"] == "TICKET-BACKEND-001"
    assert typed_dict["repo_name"] == "owner/repo"

    restored = ScrumSessionStateModel.from_typed_dict(cast(dict[str, Any], typed_dict))
    assert restored.ticket_id == state.ticket_id
    assert restored.branch_name == "feature/orders"


@pytest.mark.unit
def test_evaluate_qa_feedback_pass() -> None:
    """Test that a QA PASS verdict immediately terminates the sprint loop."""
    state = ScrumSessionStateModel(ticket_id="TEST-001", feature_name="Test Feature")
    qa_output = (
        '```json\n{\n  "status": "PASS",\n  "failed_criteria": [],\n'
        '  "actionable_feedback": "Looks great."\n}\n```'
    )

    should_continue, updated = evaluate_qa_feedback_and_break(state, qa_output, max_retries=3)
    assert should_continue is False
    assert updated.status == "PASS"
    assert updated.ci_passed is True
    assert updated.retry_count == 0
    assert len(updated.iteration_history) == 1


@pytest.mark.unit
def test_evaluate_qa_feedback_nested_json_parsing() -> None:
    """Test QA output with nested JSON structures parses correctly without regex truncation."""
    state = ScrumSessionStateModel(ticket_id="TEST-002", feature_name="Nested JSON Test")
    qa_output = """
    ```json
    {
      "status": "FAIL",
      "failed_criteria": [
        "Scenario 1: Endpoint returned 500 error",
        "Security: Raw SQL string interpolation found"
      ],
      "details": {
        "error_code": "ERR_500",
        "nested_info": {
          "field": "user_id"
        }
      },
      "actionable_feedback": "Fix parameterized queries and catch auth error."
    }
    ```
    """
    should_continue, updated = evaluate_qa_feedback_and_break(state, qa_output, max_retries=3)
    assert should_continue is True
    assert updated.status == "FAIL"
    assert updated.retry_count == 1
    assert len(updated.failed_criteria) == 2


@pytest.mark.unit
def test_evaluate_qa_feedback_circuit_breaker_tripped() -> None:
    """Test that exceeding max_retries trips the circuit breaker exception."""
    state = ScrumSessionStateModel(ticket_id="TEST-001", feature_name="Test Feature", retry_count=2)
    qa_output = (
        '{"status": "FAIL", "failed_criteria": ["Still failing."], '
        '"actionable_feedback": "Try again."}'
    )

    with pytest.raises(CircuitBreakerTrippedError) as exc_info:
        evaluate_qa_feedback_and_break(state, qa_output, max_retries=3)

    assert exc_info.value.state.status == "CIRCUIT_BROKEN"
    assert exc_info.value.state.retry_count == 3


@pytest.mark.unit
def test_loop_agent_frontend_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that LoopAgent correctly executes frontend persona when ticket_type is FRONTEND."""
    monkeypatch.setenv("MOCK_QA_IMMEDIATE_PASS", "true")

    backend_agent = LlmAgent(
        name="cloud_backend", role="Backend Dev", model="gemini-3.1-pro", instructions="Dev"
    )
    frontend_agent = LlmAgent(
        name="frontend", role="Frontend Dev", model="gemini-3.1-flash", instructions="Frontend"
    )
    qa_agent = LlmAgent(
        name="qa_sec", role="QA Auditor", model="gemini-3.1-flash", instructions="QA"
    )

    loop = LoopAgent(
        name="test_loop", sub_agents=[backend_agent, frontend_agent, qa_agent], max_iterations=3
    )

    state = ScrumSessionStateModel(
        ticket_id="TICKET-FRONTEND-001", feature_name="React Dashboard UI", ticket_type="FRONTEND"
    )
    final_state = loop.run(state)

    assert final_state.status == "PASS"
    assert final_state.ci_passed is True


@pytest.mark.unit
def test_full_sequential_orchestration_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full sequential pipeline (product_architect -> dev_qa_loop with dynamic configs)."""
    monkeypatch.setenv("MOCK_QA_IMMEDIATE_PASS", "true")

    orchestrator = create_scrum_team_orchestrator(max_loop_iterations=3)
    state = ScrumSessionStateModel(
        ticket_id="TEST-SEQ-1", feature_name="Sequential Test", ticket_type="BACKEND"
    )

    final_state = orchestrator.run(state)

    assert final_state.openapi_spec_path == "api-spec-v1.yaml"
    assert final_state.pr_url is not None
    assert final_state.status == "PASS"
    assert final_state.ci_passed is True


@pytest.mark.unit
def test_specialized_backend_and_frontend_qa_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test specialized backend_qa_loop and frontend_qa_loop exposed on the orchestrator."""
    monkeypatch.setenv("MOCK_QA_IMMEDIATE_PASS", "true")
    orchestrator = create_scrum_team_orchestrator(max_loop_iterations=2)

    # 1. Test Backend QA Loop
    backend_state = ScrumSessionStateModel(
        ticket_id="TEST-BE-1", feature_name="BE API", ticket_type="BACKEND"
    )
    be_result = orchestrator.backend_qa_loop.run(backend_state)  # type: ignore
    assert be_result.status == "PASS"
    assert be_result.ci_passed is True
    assert any(item["persona"] == "cloud_backend" for item in be_result.iteration_history)

    # 2. Test Frontend QA Loop
    frontend_state = ScrumSessionStateModel(
        ticket_id="TEST-FE-1", feature_name="FE UI", ticket_type="FRONTEND"
    )
    fe_result = orchestrator.frontend_qa_loop.run(frontend_state)  # type: ignore
    assert fe_result.status == "PASS"
    assert fe_result.ci_passed is True
    assert any(item["persona"] == "frontend" for item in fe_result.iteration_history)


@pytest.mark.unit
def test_dual_track_frontend_orchestration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that full sequential orchestration correctly routes FRONTEND ticket to dev_qa_loop."""
    monkeypatch.setenv("MOCK_QA_IMMEDIATE_PASS", "true")
    orchestrator = create_scrum_team_orchestrator(max_loop_iterations=3)
    state = ScrumSessionStateModel(
        ticket_id="TEST-FE-SEQ", feature_name="React Dashboard", ticket_type="FRONTEND"
    )

    final_state = orchestrator.run(state)

    assert final_state.openapi_spec_path == "api-spec-v1.yaml"
    assert final_state.pr_url is not None
    assert final_state.status == "PASS"
    assert any(item["persona"] == "frontend" for item in final_state.iteration_history)
